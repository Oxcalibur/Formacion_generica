try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
try:
    import pypdf
except ImportError:
    pypdf = None
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    GSheetsConnection = None
try:
    from herramientas_busqueda import buscar_youtube_externo, requiere_video_post_oct_2026, POST_OCT_2026_PREFIX
except ImportError:
    buscar_youtube_externo = None
    requiere_video_post_oct_2026 = None
    POST_OCT_2026_PREFIX = "2026-11-01"
try:
    from fpdf import FPDF
except ImportError:
    FPDF = None
import io
import math
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
import json
import os
import random
import time
try:
    import plotly.graph_objects as go
except ImportError:
    go = None
from typing import List, Dict, Any, Optional
import datetime
from config import CLIENT_CONFIG

# Definición de Cinturones (Gamificación)
BELTS = [
    {"name": "Cinturón Blanco", "color": "#ffffff", "threshold": 0},
    {"name": "Cinturón Amarillo", "color": "#ffff00", "threshold": 50},
    {"name": "Cinturón Naranja", "color": "#ffa500", "threshold": 150},
    {"name": "Cinturón Verde", "color": "#008000", "threshold": 300},
    {"name": "Cinturón Azul", "color": "#0000ff", "threshold": 500},
    {"name": "Cinturón Marrón", "color": "#a52a2a", "threshold": 800},
    {"name": "Cinturón Negro", "color": "#000000", "threshold": 1200},
]

def get_current_belt(score):
    """Determina el cinturón actual basado en la puntuación."""
    current = BELTS[0]
    for belt in BELTS:
        if score >= belt["threshold"]:
            current = belt
        else:
            break
    return current

def get_next_belt_data(score):
    """Calcula el progreso relativo hacia el siguiente nivel."""
    current_belt = get_current_belt(score)
    next_belt = None
    
    for belt in BELTS:
        if belt["threshold"] > current_belt["threshold"]:
            next_belt = belt
            break
            
    if next_belt:
        # Calcular porcentaje completado del nivel actual
        range_span = next_belt["threshold"] - current_belt["threshold"]
        progress = (score - current_belt["threshold"]) / range_span
        return {"next_name": next_belt["name"], "threshold": next_belt["threshold"], "progress": progress}
    
    return {"next_name": "Maestría Total", "threshold": score, "progress": 1.0}

def init_gemini():
    """Inicializa la API de Gemini. Requiere st.secrets o variable de entorno."""
    if genai is None:
        st.error("La librería 'google-genai' no está instalada. Por favor ejecuta: pip install -r requirements.txt vOVM")
        return None

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GOOGLE_API_KEY")
        except Exception:
            api_key = None

    if not api_key:
        st.error("Falta la API Key de Google. Configúrala en .streamlit/secrets.toml o variables de entorno.")
        return None
    
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(api_version="v1beta")
    )

MULTIMEDIA_FILENAMES = {"multimedia.csv", "video_index.json", "recursos.csv", "resources.csv"}
SUPPORTED_KB_EXTENSIONS = (".md", ".txt", ".csv", ".json", ".pdf")
SPANISH_STOPWORDS = {
    "de", "la", "el", "en", "y", "a", "que", "los", "las", "un", "una", "unos", "unas",
    "por", "con", "para", "del", "al", "es", "su", "sus", "se", "lo", "como", "mas",
    "pero", "si", "no", "o", "u", "mi", "mis", "me", "te", "le", "les", "nos", "hay",
    "son", "ser", "fue", "esta", "este", "esto", "estos", "estas", "ese", "esa", "eso",
    "sobre", "entre", "sin", "todo", "toda", "todos", "todas", "muy", "ya", "ha", "han",
    "puede", "puedo", "pueden", "quiero", "tengo", "tiene", "tienen", "hacer", "hola",
    "gracias", "buenas", "buenos", "dias", "tardes", "favor", "porque", "cuando", "donde",
    "cual", "cuales", "como", "quien", "quienes", "caso", "tema", "duda", "consulta",
}


def _normalize_search_text(text: str) -> str:
    """Normaliza texto en español (minúsculas y sin tildes) para búsquedas."""
    if not text:
        return ""
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _tokenize_search(text: str) -> List[str]:
    """Extrae tokens útiles (incluyendo números de artículos/años) descartando stopwords."""
    norm = _normalize_search_text(text)
    raw_tokens = re.findall(r"[a-z0-9]+", norm)
    return [t for t in raw_tokens if len(t) >= 2 and t not in SPANISH_STOPWORDS]


def _extract_article_refs(text: str) -> List[str]:
    """Detecta referencias explícitas a artículos o normas (ej. 'art 11', '29/2026', '1566')."""
    norm = _normalize_search_text(text)
    refs = []
    for match in re.finditer(r"(?:articulo|art\.?)\s*(\d+(?:\.\d+)?)", norm):
        refs.append(f"articulo {match.group(1)}")
    for match in re.finditer(r"\b(\d{1,2}/\d{4})\b", norm):
        refs.append(match.group(1))
    return refs


def _split_document_into_sections(rel_path: str, folder: str, content: str) -> List[Dict[str, Any]]:
    """Divide un documento Markdown/texto en secciones lógicas (por encabezados/artículos)."""
    doc_meta = ""
    body = content

    # Extraer frontmatter YAML si existe
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, flags=re.DOTALL)
    if fm_match:
        doc_meta = fm_match.group(1).strip()
        body = content[fm_match.end():]

    # Dividir por encabezados Markdown (#, ##, ###)
    heading_pattern = re.compile(r"(?m)^(#{1,3}\s+.+)$")
    matches = list(heading_pattern.finditer(body))

    raw_sections = []
    if matches:
        preamble = body[:matches[0].start()].strip()
        if preamble:
            raw_sections.append(("Introducción", preamble))
        for idx, match in enumerate(matches):
            heading = match.group(1).strip()
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
            sec_text = body[start:end].strip()
            if sec_text:
                raw_sections.append((heading, sec_text))
    else:
        raw_sections.append((os.path.basename(rel_path), body.strip()))

    # Trocear secciones demasiado largas manteniendo límites de párrafo
    final_sections = []
    max_chunk_chars = 3500
    sec_counter = 0
    for heading, sec_text in raw_sections:
        if len(sec_text) <= max_chunk_chars:
            final_sections.append({
                "rel_path": rel_path,
                "folder": folder,
                "heading": heading,
                "doc_meta": doc_meta,
                "text": sec_text,
                "index": sec_counter,
            })
            sec_counter += 1
        else:
            paragraphs = sec_text.split("\n\n")
            current_chunk = ""
            part_num = 1
            for para in paragraphs:
                if current_chunk and len(current_chunk) + len(para) + 2 > max_chunk_chars:
                    final_sections.append({
                        "rel_path": rel_path,
                        "folder": folder,
                        "heading": f"{heading} (parte {part_num})",
                        "doc_meta": doc_meta,
                        "text": current_chunk.strip(),
                        "index": sec_counter,
                    })
                    sec_counter += 1
                    part_num += 1
                    current_chunk = f"{heading}\n{para}"
                else:
                    current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
            if current_chunk.strip():
                final_sections.append({
                    "rel_path": rel_path,
                    "folder": folder,
                    "heading": f"{heading} (parte {part_num})" if part_num > 1 else heading,
                    "doc_meta": doc_meta,
                    "text": current_chunk.strip(),
                    "index": sec_counter,
                })
                sec_counter += 1

    return final_sections


@st.cache_data(show_spinner=False)
def load_knowledge_base_structured(folder_path: str) -> Dict[str, Any]:
    """
    Recorre recursivamente todas las subcarpetas de knowledge_base en orden alfabético/prioritario
    (ej. 01_Normativa_Estatal_Vigente, 02_Jurisprudencia_y_Criterios, 03_Plantillas_Accionables,
    04_Datos_Volatiles_y_CCAA) y carga documentos + secciones indexadas.
    """
    result: Dict[str, Any] = {"folders": {}, "documents": [], "sections": [], "total_chars": 0}
    if not folder_path or not os.path.exists(folder_path):
        return result

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        files = sorted(f for f in files if not f.startswith("."))

        rel_dir = os.path.relpath(root, folder_path).replace("\\", "/")
        if rel_dir != "." and rel_dir not in result["folders"]:
            result["folders"][rel_dir] = []

        for filename in files:
            if filename.lower() in MULTIMEDIA_FILENAMES:
                continue
            if not filename.lower().endswith(SUPPORTED_KB_EXTENSIONS):
                continue

            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, folder_path).replace("\\", "/")
            folder_label = rel_dir if rel_dir != "." else "raiz"

            content = ""
            if filename.lower().endswith(".pdf"):
                if pypdf:
                    try:
                        reader = pypdf.PdfReader(file_path)
                        content = "\n".join((page.extract_text() or "") for page in reader.pages)
                    except Exception as e:
                        st.warning(f"No se pudo leer PDF {rel_path}: {e}")
                        continue
                else:
                    continue
            else:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception as e:
                    st.warning(f"No se pudo leer {rel_path}: {e}")
                    continue

            content = content.strip()
            if not content:
                continue

            result["folders"].setdefault(folder_label, []).append(rel_path)
            doc_sections = _split_document_into_sections(rel_path, folder_label, content)
            result["documents"].append({
                "rel_path": rel_path,
                "folder": folder_label,
                "filename": filename,
                "content": content,
                "char_count": len(content),
            })
            result["sections"].extend(doc_sections)
            result["total_chars"] += len(content)

    return result


@st.cache_data(show_spinner=False)
def load_knowledge_base(folder_path):
    """Lee recursivamente todos los documentos de knowledge_base y sus subcarpetas."""
    kb_data = load_knowledge_base_structured(folder_path)
    if not kb_data["documents"]:
        return ""

    parts = []
    for doc in kb_data["documents"]:
        parts.append(f"\n\n=== [{doc['folder']}] Documento: {doc['rel_path']} ===\n{doc['content']}")
    return "".join(parts)


def _build_kb_inventory(kb_data: Dict[str, Any]) -> str:
    """Construye un inventario compacto de carpetas y documentos reales disponibles en knowledge_base."""
    lines = ["=== INVENTARIO REAL DE DOCUMENTOS EN knowledge_base ==="]
    for folder, files in sorted(kb_data["folders"].items()):
        if files:
            lines.append(f"- {folder}/ ({len(files)} documentos): " + ", ".join(os.path.basename(f) for f in files))
        else:
            lines.append(f"- {folder}/: (carpeta actualmente vacía — no inventes documentos ni criterios de esta carpeta)")
    return "\n".join(lines)


def retrieve_relevant_knowledge(
    folder_path: str,
    query: str,
    history: Optional[list] = None,
    max_chars: int = 90000,
) -> str:
    """
    Recupera contexto documental relevante recorriendo TODAS las carpetas de knowledge_base
    (01_Normativa_Estatal_Vigente, 02_Jurisprudencia_y_Criterios, 03_Plantillas_Accionables,
    04_Datos_Volatiles_y_CCAA), evitando truncamientos ciegos.
    """
    kb_data = load_knowledge_base_structured(folder_path)
    if not kb_data["documents"]:
        return "No hay documentos cargados en knowledge_base."

    inventory = _build_kb_inventory(kb_data)

    # Si toda la base documental cabe holgadamente en el presupuesto, devolverla íntegra
    if kb_data["total_chars"] <= max_chars:
        full_docs = "\n\n".join(
            f"=== [{doc['folder']}] Documento: {doc['rel_path']} ===\n{doc['content']}"
            for doc in kb_data["documents"]
        )
        return f"{inventory}\n\n{full_docs}"

    # Combinar la consulta actual con los últimos mensajes del usuario (triaje + pregunta inicial)
    user_texts = [query or ""]
    if history:
        recent_user_msgs = [m.get("content", "") for m in history[-8:] if m.get("role") == "user"]
        user_texts.extend(recent_user_msgs[-4:])
    combined_query = " ".join(user_texts)
    query_tokens = _tokenize_search(combined_query)
    query_token_set = set(query_tokens)
    article_refs = _extract_article_refs(combined_query)

    sections = kb_data["sections"]
    num_sections = max(1, len(sections))

    # Calcular frecuencia documental por token (IDF simple)
    doc_freq: Dict[str, int] = {}
    section_token_sets: List[set] = []
    section_heading_sets: List[set] = []
    section_norms: List[str] = []

    for sec in sections:
        sec_norm = _normalize_search_text(f"{sec['heading']}\n{sec['doc_meta']}\n{sec['text']}")
        sec_tokens = set(_tokenize_search(sec_norm))
        head_tokens = set(_tokenize_search(f"{sec['folder']} {sec['rel_path']} {sec['heading']} {sec['doc_meta']}"))
        section_norms.append(sec_norm)
        section_token_sets.append(sec_tokens)
        section_heading_sets.append(head_tokens)
        for tok in sec_tokens:
            doc_freq[tok] = doc_freq.get(tok, 0) + 1

    # Detectar intención de fiscalidad / financiación / inversión para priorizar 05_ y 06_
    norm_combined_query = _normalize_search_text(combined_query)
    fiscal_fin_inv_terms = (
        "irpf", "itp", "ajd", "impuesto", "amortizacion", "deducir", "deducible",
        "reduccion", "base imponible", "valor de referencia", "hipoteca", "lcci",
        "fein", "cirbe", "dti", "ltv", "prestamo", "apalancamiento", "financiacion",
        "inversion", "rentabilidad", "roce", "cash flow", "ticket bajo", "patrimonial",
        "sociedad", "persona juridica", "comprar piso", "gastos de compra"
    )
    is_fiscal_fin_inv = any(term in norm_combined_query for term in fiscal_fin_inv_terms)

    # Documentos compactos clave (<= 12 KB, ej. RDL 29/2026, guías de estrategia/IRPF/ITP/financiación, datos CCAA)
    always_include_paths = {doc["rel_path"] for doc in kb_data["documents"] if doc["char_count"] <= 12000}

    scored = []
    for idx, sec in enumerate(sections):
        score = 0.0
        sec_tokens = section_token_sets[idx]
        head_tokens = section_heading_sets[idx]
        sec_norm = section_norms[idx]

        for tok in query_token_set:
            if tok in sec_tokens:
                idf = math.log((num_sections + 1) / (doc_freq.get(tok, 1) + 1)) + 1.0
                score += idf
                if tok in head_tokens:
                    score += idf * 1.5

        for ref in article_refs:
            if ref in sec_norm:
                score += 12.0

        # Bonificación contextual según carpeta documental (01_ a 06_)
        if is_fiscal_fin_inv and (sec["folder"].startswith("05_") or sec["folder"].startswith("06_")):
            score += 2.5
        elif sec["folder"].startswith("01_"):
            score += 0.4
        elif sec["folder"].startswith("02_"):
            score += 0.3
        elif sec["folder"].startswith("03_"):
            score += 0.25
        elif sec["folder"].startswith("04_"):
            score += 0.2
        elif sec["folder"].startswith("05_"):
            score += 0.35
        elif sec["folder"].startswith("06_"):
            score += 0.35

        if sec["rel_path"] in always_include_paths:
            score += 100.0

        scored.append((score, idx, sec))

    scored.sort(key=lambda x: x[0], reverse=True)

    selected_indices = set()
    used_chars = len(inventory) + 200

    # Garantizar al menos 2 secciones representativas de cada carpeta no vacía
    populated_folders = [f for f, files in sorted(kb_data["folders"].items()) if files]
    for folder_name in populated_folders:
        added_for_folder = 0
        for score, idx, sec in scored:
            if sec["folder"] == folder_name and idx not in selected_indices:
                sec_len = len(sec["text"]) + 120
                if used_chars + sec_len <= max_chars:
                    selected_indices.add(idx)
                    used_chars += sec_len
                    added_for_folder += 1
                if added_for_folder >= 2:
                    break

    # Rellenar el resto del presupuesto con las secciones más relevantes globalmente
    for score, idx, sec in scored:
        if idx in selected_indices:
            continue
        sec_len = len(sec["text"]) + 120
        if used_chars + sec_len > max_chars:
            continue
        selected_indices.add(idx)
        used_chars += sec_len

    # Ordenar secciones seleccionadas por carpeta, documento y posición natural
    selected_sections = [sections[i] for i in sorted(selected_indices)]
    blocks = [inventory, "\n=== FRAGMENTOS RECUPERADOS DE LA BASE DOCUMENTAL (POR PRIORIDAD Y RELEVANCIA) ==="]
    for sec in selected_sections:
        blocks.append(f"\n--- [{sec['folder']}] {sec['rel_path']} | {sec['heading']} ---\n{sec['text']}")

    return "\n".join(blocks)


def _sample_knowledge_for_training(folder_path: Optional[str], knowledge_context: str = "", max_chars: int = 24000) -> str:
    """Obtiene una muestra equilibrada de todos los documentos de knowledge_base para exámenes y temas del Dojo."""
    if folder_path and os.path.exists(folder_path):
        kb_data = load_knowledge_base_structured(folder_path)
        docs = kb_data["documents"]
        if docs:
            per_doc = max(2000, max_chars // len(docs))
            parts = []
            for doc in docs:
                parts.append(f"=== [{doc['folder']}] {doc['rel_path']} ===\n{doc['content'][:per_doc]}")
            return "\n\n".join(parts)[:max_chars]
    return knowledge_context[:max_chars] if knowledge_context else ""

@st.cache_data(show_spinner=False)
def load_multimedia_resources(folder_path):
    """Carga el índice de recursos multimedia desde un CSV en la base de conocimiento."""
    if not os.path.exists(folder_path):
        return []
        
    # Prioridad: Índice enriquecido (JSON) generado por generador_indice.py
    json_index_path = os.path.join(folder_path, "video_index.json")
    if os.path.exists(json_index_path):
        try:
            with open(json_index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return list(data.values()) # Convertir a lista para el prompt
        except Exception as e:
            print(f"Error leyendo video_index.json: {e}")

    possible_files = ["multimedia.csv", "recursos.csv", "resources.csv"]
    
    for filename in possible_files:
        file_path = os.path.join(folder_path, filename)
        if os.path.exists(file_path):
            try:
                # Se espera un CSV con cabeceras: Title, URL, Type, Description (opcional)
                df = pd.read_csv(file_path)
                # Rellenar nulos para evitar errores en JSON
                df = df.fillna("")
                return df.to_dict(orient="records")
            except Exception as e:
                print(f"Error leyendo {filename}: {e}")
    return []

def generate_quiz_questions(topic, difficulty, role, knowledge_context=""):
    """Genera 5 preguntas usando Gemini en formato JSON."""
    client = init_gemini()
    if not client:
        # Retorno Mock si no hay API Key para que la app no rompa al probar
        return [
            {"question": "Pregunta de prueba 1 (Configura API Key)", "options": ["A", "B", "C"], "answer": "A"},
            {"question": "Pregunta de prueba 2", "options": ["A", "B", "C"], "answer": "B"},
            {"question": "Pregunta de prueba 3", "options": ["A", "B", "C"], "answer": "C"},
            {"question": "Pregunta de prueba 4", "options": ["A", "B", "C"], "answer": "A"},
            {"question": "Pregunta de prueba 5", "options": ["A", "B", "C"], "answer": "B"},
        ]

    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.5-flash")

    kb_folder = CLIENT_CONFIG.get("knowledge_base_folder")
    if topic and kb_folder and os.path.exists(kb_folder):
        sampled_context = retrieve_relevant_knowledge(kb_folder, topic, max_chars=24000)
    else:
        sampled_context = _sample_knowledge_for_training(kb_folder, knowledge_context, max_chars=24000)

    prompt = f"""
    Actúa como un generador de exámenes experto en derecho de arrendamientos urbanos en España para propietarios particulares.
    Tu objetivo es crear un test de evaluación de 5 preguntas prácticas y exactas basado en la documentación legal proporcionada.
    
    BASE DE CONOCIMIENTO (CONTENIDO FUENTE):
    {sampled_context if sampled_context.strip() else "No hay documentos cargados. Usa conocimiento general de la LAU en España."}
    
    CONFIGURACIÓN DEL EXAMEN:
    - Tema sugerido: '{topic}'
    - Dificultad: {difficulty}
    - Perfil del usuario: {role}
    
    REGLAS DE GENERACIÓN:
    1. ENFOQUE PRÁCTICO PARA PROPIETARIOS: Diseña preguntas claras, sin jerga innecesaria, sobre situaciones reales de alquiler en España (contratos, fianzas, subidas de renta, prórrogas, desistimiento, desahucios, comunidad de propietarios, RDL 29/2026).
    2. PRIORIDAD DE CONTENIDO: Basa las preguntas EXCLUSIVAMENTE en la Base de Conocimiento proporcionada. Nunca inventes artículos, porcentajes ni plazos que no figuren en los documentos.
    3. DINAMISMO: Varía entre casos prácticos breves, plazos legales y verificación de derechos/obligaciones del propietario.
    4. FORMATO DE SALIDA: Responde ÚNICAMENTE con un JSON válido (lista de objetos).
    
    Ejemplo de estructura JSON requerida:
    [
        {{"question": "¿Qué plazo mínimo de preaviso...?", "options": ["A", "B", "C"], "answer": "A"}}
    ]
    """
    
    try:
        response = llamar_gemini_con_rotacion_y_reintento(
            model_name=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        text_response = response.text
        return json.loads(text_response)
    except (json.JSONDecodeError, Exception) as e:
        st.error(f"Error generando preguntas: {e}")
        return []

def evaluate_quiz(questions, user_answers):
    """Evalúa las respuestas y devuelve la puntuación."""
    score = 0
    results = []
    
    for i, q in enumerate(questions):
        correct_answer_key = q.get("answer")
        options = q.get("options", [])
        user_ans = user_answers.get(i)

        # Lógica de comparación robusta
        # Si la respuesta es una letra (A, B, C...), la convierte al texto de la opción
        correct_answer_text = correct_answer_key
        if isinstance(correct_answer_key, str) and len(correct_answer_key) == 1 and 'A' <= correct_answer_key.upper() <= 'Z':
            try:
                # Convertir 'A' -> 0, 'B' -> 1, etc.
                option_index = ord(correct_answer_key.upper()) - ord('A')
                if 0 <= option_index < len(options):
                    correct_answer_text = options[option_index]
            except (TypeError, IndexError):
                pass # Mantener la clave original si algo falla
        is_correct = (user_ans == correct_answer_text)
        
        if is_correct:
            score += 10 # 10 puntos por respuesta correcta
            
        results.append({
            "question": q["question"],
            "user_answer": user_ans,
            "correct_answer": correct_answer_text,
            "is_correct": is_correct
        })
        
    return score, results

def llamar_gemini_con_rotacion_y_reintento(model_name, contents, config=None, max_retries=3):
    """Intenta enviar la petición rotando entre múltiples API Keys si recibe un Error 429."""
    api_keys = []
    try:
        for key in st.secrets:
            if key.startswith("GOOGLE_API_KEY"):
                api_keys.append(st.secrets[key])
    except Exception:
        pass
        
    if not api_keys:
        single_key = os.environ.get("GOOGLE_API_KEY")
        if single_key:
            api_keys.append(single_key)
            
    if not api_keys:
        raise ValueError("No se encontraron API Keys configuradas.")

    last_error = None
    for attempt in range(max_retries):
        random.shuffle(api_keys)
        for key in api_keys:
            try:
                print(f"🔄 GEMINI API: Intentando con API Key terminada en ...{key[-4:]}")
                client_temp = genai.Client(
                    api_key=key,
                    http_options=types.HttpOptions(api_version="v1beta")
                )
                return client_temp.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
            except Exception as e:
                error_str = str(e).upper()
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "QUOTA" in error_str:
                    print(f"⚠️ Cuota agotada para la key ...{key[-4:]}. Saltando a otra...")
                    last_error = e
                    continue
                else:
                    raise e
        
        if attempt < max_retries - 1:
            sleep_time = 3 * (attempt + 1)
            print(f"⏳ Todas las llaves agotadas. Esperando {sleep_time}s antes de reintentar...")
            time.sleep(sleep_time)
            
    raise last_error or Exception("Cuota agotada en TODAS las API Keys.")


LEGAL_DISCLAIMER_PDF = (
    "Orientación jurídica, fiscal y financiera automatizada basada en la normativa española vigente. "
    "No sustituye el asesoramiento personalizado de un abogado colegiado, asesor fiscal o entidad financiera."
)


def _sanitize_pdf_text(text: str, allow_euro_cp1252: bool = False) -> str:
    """Limpia sintaxis Markdown básica, comillas tipográficas y emojis para evitar errores de codificación PDF."""
    if not text:
        return ""
    replacements = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "…": "...",
        "•": "-",
        "▪": "-",
        "\u00a0": " ",
        "\t": "    ",
    }
    if not allow_euro_cp1252:
        replacements["€"] = "EUR"
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # Quitar formato inline de Markdown (**negrita**, *cursiva*, `código`)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Quitar enlaces Markdown [texto](url) dejando el texto visible
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)

    encoding = "cp1252" if allow_euro_cp1252 else "latin-1"
    cleaned_chars = []
    for ch in text:
        try:
            ch.encode(encoding)
            cleaned_chars.append(ch)
        except UnicodeEncodeError:
            # Descartar emojis u otros caracteres fuera del juego de la fuente
            continue
    return "".join(cleaned_chars)


def _slugify_filename(title: str, default: str = "documento_legal") -> str:
    """Genera un nombre de archivo PDF limpio y seguro."""
    norm = _normalize_search_text(title or default)
    slug = re.sub(r"[^a-z0-9]+", "_", norm).strip("_")
    return f"{slug[:60] or default}.pdf"


def _generate_simple_pdf_bytes(title: str, markdown_text: str, include_disclaimer: bool = True) -> bytes:
    """
    Generador PDF 1.4 puro en Python (sin dependencias externas) con WinAnsiEncoding.
    Sirve como respaldo automático si fpdf2 no está instalado en el entorno.
    """
    import textwrap

    def _pdf_escape(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    safe_title = _sanitize_pdf_text(title or "Documento Legal", allow_euro_cp1252=True)
    fecha_str = datetime.datetime.now().strftime("%d/%m/%Y")

    # Preparar líneas con estilo: (texto, font_name, font_size, line_height)
    styled_lines: List[tuple] = [
        (safe_title, "F2", 14, 20),
        (f"Asesor Legal Inmobiliario  |  Fecha: {fecha_str}", "F1", 9, 14),
        ("-" * 88, "F1", 9, 14),
    ]

    for raw_line in (markdown_text or "").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            styled_lines.append(("", "F1", 10, 8))
            continue
        if stripped in ("---", "***", "___"):
            styled_lines.append(("-" * 88, "F1", 9, 12))
            continue

        if stripped.startswith("### "):
            txt = _sanitize_pdf_text(stripped[4:], allow_euro_cp1252=True)
            for w in textwrap.wrap(txt, width=78) or [""]:
                styled_lines.append((w, "F2", 11, 15))
        elif stripped.startswith("## "):
            txt = _sanitize_pdf_text(stripped[3:], allow_euro_cp1252=True)
            styled_lines.append(("", "F1", 10, 4))
            for w in textwrap.wrap(txt, width=74) or [""]:
                styled_lines.append((w, "F2", 12, 16))
        elif stripped.startswith("# "):
            txt = _sanitize_pdf_text(stripped[2:], allow_euro_cp1252=True)
            styled_lines.append(("", "F1", 10, 6))
            for w in textwrap.wrap(txt, width=68) or [""]:
                styled_lines.append((w, "F2", 13, 18))
        else:
            is_bullet = stripped.startswith(("- ", "* "))
            prefix = "  - " if is_bullet else ""
            body = stripped[2:] if is_bullet else stripped
            txt = _sanitize_pdf_text(body, allow_euro_cp1252=True)
            wrapped = textwrap.wrap(txt, width=82 if is_bullet else 86) or [""]
            for i, w in enumerate(wrapped):
                styled_lines.append(((prefix if i == 0 else ("    " if is_bullet else "")) + w, "F1", 10, 14))

    if include_disclaimer:
        styled_lines.append(("", "F1", 10, 10))
        styled_lines.append(("-" * 88, "F1", 8, 12))
        for w in textwrap.wrap(LEGAL_DISCLAIMER_PDF, width=95):
            styled_lines.append((w, "F1", 8, 11))

    # Paginación A4 (595 x 842 pt)
    page_w, page_h = 595, 842
    margin_x, top_y, bottom_y = 50, 790, 55
    pages_lines: List[List[tuple]] = []
    cur_page: List[tuple] = []
    y = top_y

    for line_item in styled_lines:
        lh = line_item[3]
        if y - lh < bottom_y and cur_page:
            pages_lines.append(cur_page)
            cur_page = []
            y = top_y
        cur_page.append((line_item[0], line_item[1], line_item[2], y))
        y -= lh
    if cur_page:
        pages_lines.append(cur_page)

    # Ensamblar objetos PDF 1.4
    objects: List[bytes] = []

    def add_obj(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    font1_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font2_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

    page_ids = []
    total_pages = len(pages_lines)
    pages_placeholder_id = add_obj(b"")  # Se rellena al final

    for page_idx, plines in enumerate(pages_lines, start=1):
        cmds = ["BT"]
        for txt, fname, fsize, ypos in plines:
            if txt:
                safe_cmd_txt = _pdf_escape(txt)
                cmds.append(f"/{fname} {fsize} Tf 1 0 0 1 {margin_x} {ypos} Tm ({safe_cmd_txt}) Tj")
        footer_txt = _pdf_escape(f"Pagina {page_idx} de {total_pages}")
        cmds.append(f"/F1 8 Tf 1 0 0 1 {page_w - 110} 30 Tm ({footer_txt}) Tj")
        cmds.append("ET")
        stream_bytes = "\n".join(cmds).encode("cp1252", errors="replace")
        stream_obj = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream"
        )
        content_id = add_obj(stream_obj)
        page_obj = (
            f"<< /Type /Page /Parent {pages_placeholder_id} 0 R "
            f"/MediaBox [0 0 {page_w} {page_h}] "
            f"/Resources << /Font << /F1 {font1_id} 0 R /F2 {font2_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")
        page_ids.append(add_obj(page_obj))

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_placeholder_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    catalog_id = add_obj(f"<< /Type /Catalog /Pages {pages_placeholder_id} 0 R >>".encode("ascii"))

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode("ascii"))
        out.write(obj)
        out.write(b"\nendobj\n")

    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode("ascii"))
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return out.getvalue()


def generate_pdf_bytes(title: str, markdown_text: str, include_disclaimer: bool = True) -> bytes:
    """
    Genera un documento PDF en memoria (bytes) listo para descargar en Streamlit.
    Usa fpdf2 cuando está disponible y un generador PDF 1.4 puro como respaldo automático.
    """
    if FPDF is None:
        return _generate_simple_pdf_bytes(title, markdown_text, include_disclaimer=include_disclaimer)

    safe_title = _sanitize_pdf_text(title or "Documento Legal", allow_euro_cp1252=False)
    fecha_str = datetime.datetime.now().strftime("%d/%m/%Y")

    class LegalPDF(FPDF):
        def header(self):
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "B", 12)
            self.set_text_color(30, 58, 95)
            self.multi_cell(self.epw, 6.5, safe_title[:110], align="L")
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(110, 110, 110)
            self.multi_cell(self.epw, 4.5, f"Asesor Legal Inmobiliario  |  Fecha: {fecha_str}", align="L")
            self.set_draw_color(200, 210, 220)
            y_line = self.get_y() + 1.5
            self.line(self.l_margin, y_line, self.w - self.r_margin, y_line)
            self.set_y(y_line + 4.5)
            self.set_x(self.l_margin)

        def footer(self):
            self.set_y(-18)
            self.set_draw_color(220, 220, 220)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.set_y(-16)
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(120, 120, 120)
            if include_disclaimer:
                self.multi_cell(self.epw - 22, 3.5, _sanitize_pdf_text(LEGAL_DISCLAIMER_PDF), align="L")
            self.set_y(-11)
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "", 8)
            self.cell(self.epw, 5, f"Página {self.page_no()}/{{nb}}", 0, 0, "R")

    def _write_block(pdf_obj, text_val: str, line_h: float = 5.5, indent: float = 0.0, align: str = "L"):
        """Escribe un bloque de texto forzando siempre el cursor al margen izquierdo (evita desbordamiento en fpdf2)."""
        pdf_obj.set_x(pdf_obj.l_margin + indent)
        pdf_obj.multi_cell(pdf_obj.epw - indent, line_h, text_val, align=align)
        pdf_obj.set_x(pdf_obj.l_margin)

    try:
        pdf = LegalPDF(orientation="P", unit="mm", format="A4")
        pdf.alias_nb_pages()
        pdf.set_auto_page_break(auto=True, margin=22)
        pdf.set_margins(18, 16, 18)
        pdf.add_page()

        for raw_line in (markdown_text or "").splitlines():
            stripped = raw_line.strip()
            pdf.set_x(pdf.l_margin)

            if not stripped:
                pdf.ln(3)
                continue

            if stripped in ("---", "***", "___"):
                pdf.ln(2)
                pdf.set_draw_color(210, 210, 210)
                y_hr = pdf.get_y()
                pdf.line(pdf.l_margin, y_hr, pdf.w - pdf.r_margin, y_hr)
                pdf.set_y(y_hr + 3)
                pdf.set_x(pdf.l_margin)
                continue

            # Detectar línea completa en negrita (**TÍTULO** o **PRIMERA. OBJETO.**)
            is_full_bold = (
                stripped.startswith("**")
                and stripped.endswith("**")
                and stripped.count("**") == 2
                and len(stripped) > 4
            )

            if stripped.startswith("# "):
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_text_color(25, 45, 75)
                _write_block(pdf, _sanitize_pdf_text(stripped[2:]), line_h=7)
                pdf.ln(1.5)
            elif stripped.startswith("## "):
                pdf.ln(2.5)
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(30, 58, 95)
                _write_block(pdf, _sanitize_pdf_text(stripped[3:]), line_h=6.5)
                pdf.ln(1)
            elif stripped.startswith("### "):
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 10.5)
                pdf.set_text_color(40, 65, 100)
                _write_block(pdf, _sanitize_pdf_text(stripped[4:]), line_h=6)
                pdf.ln(0.5)
            elif is_full_bold:
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 10.5)
                pdf.set_text_color(30, 50, 80)
                _write_block(pdf, _sanitize_pdf_text(stripped[2:-2]), line_h=6)
                pdf.ln(0.5)
            elif stripped.startswith(("- ", "* ")):
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(40, 40, 40)
                _write_block(pdf, "- " + _sanitize_pdf_text(stripped[2:]), line_h=5.5, indent=4.0)
                pdf.ln(0.8)
            else:
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(40, 40, 40)
                _write_block(pdf, _sanitize_pdf_text(stripped), line_h=5.5)
                pdf.ln(1.2)

        output = pdf.output()
        return bytes(output) if isinstance(output, (bytes, bytearray)) else output.encode("latin-1")
    except Exception:
        return _generate_simple_pdf_bytes(title, markdown_text, include_disclaimer=include_disclaimer)


def _extract_generated_documents(text: str) -> tuple:
    """
    Extrae bloques [DOCUMENT title="..."]...[/DOCUMENT] de la respuesta del modelo.
    Devuelve (texto_limpio_para_chat, lista_de_documentos).
    """
    documents = []
    pattern = re.compile(
        r'\[DOCUMENT(?:\s+title\s*=\s*"([^"]+)")?\s*\](.*?)\[/DOCUMENT\]',
        flags=re.DOTALL | re.IGNORECASE,
    )

    def _replace_match(match):
        raw_title = (match.group(1) or "Documento_Legal").strip()
        doc_body = (match.group(2) or "").strip()
        if not doc_body:
            return ""
        clean_title = raw_title.replace("_", " ").strip()
        documents.append({
            "title": clean_title,
            "filename": _slugify_filename(raw_title),
            "content": doc_body,
        })
        return f"\n\n---\n### 📄 {clean_title}\n\n{doc_body}\n---\n"

    cleaned_text = pattern.sub(_replace_match, text).strip()
    return cleaned_text, documents


MAX_EPHEMERAL_FILE_BYTES = 15 * 1024 * 1024  # 15 MB máximo en memoria


def extract_ephemeral_document(uploaded_file) -> Dict[str, Any]:
    """
    Lee un documento subido por el usuario ÚNICAMENTE en memoria (sin guardarlo en disco ni en caché)
    para usarlo solo durante la conversación actual.
    Soporta PDF (texto o escaneado), DOCX, TXT, MD e imágenes (PNG/JPG/WEBP).
    """
    if uploaded_file is None:
        return {}

    filename = getattr(uploaded_file, "name", "documento")
    ext = os.path.splitext(filename)[1].lower()
    raw_bytes = uploaded_file.getvalue()

    if not raw_bytes:
        return {"error": "El archivo está vacío."}
    if len(raw_bytes) > MAX_EPHEMERAL_FILE_BYTES:
        return {"error": "El archivo supera el límite de 15 MB para lectura en memoria."}

    # 1. Imágenes (fotos de contrato, anexos o burofax)
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        return {
            "name": filename,
            "mode": "binary",
            "mime_type": mime_map[ext],
            "raw_bytes": raw_bytes,
            "text": "",
            "summary": f"Imagen adjunta en memoria ({len(raw_bytes) // 1024} KB)",
        }

    # 2. PDF (extracción de texto en memoria; si es escaneado, se pasa binario a Gemini)
    if ext == ".pdf":
        extracted_text = ""
        if pypdf:
            try:
                reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
                extracted_text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
            except Exception:
                extracted_text = ""

        if len(extracted_text) >= 40:
            return {
                "name": filename,
                "mode": "text",
                "mime_type": "application/pdf",
                "raw_bytes": None,
                "text": extracted_text,
                "summary": f"PDF leído en memoria ({len(extracted_text):,} caracteres)",
            }
        return {
            "name": filename,
            "mode": "binary",
            "mime_type": "application/pdf",
            "raw_bytes": raw_bytes,
            "text": "",
            "summary": f"PDF escaneado listo para lectura visual en memoria ({len(raw_bytes) // 1024} KB)",
        }

    # 3. Word (.docx) usando solo librería estándar (zipfile + ElementTree)
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                xml_content = zf.read("word/document.xml")
            root = ET.fromstring(xml_content)
            paragraphs = []
            for p in root.iter():
                if p.tag.endswith("}p"):
                    texts = [node.text for node in p.iter() if node.tag.endswith("}t") and node.text]
                    if texts:
                        paragraphs.append("".join(texts))
            extracted_text = "\n".join(paragraphs).strip()
            if not extracted_text:
                return {"error": "No se pudo extraer texto del documento Word (.docx)."}
            return {
                "name": filename,
                "mode": "text",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "raw_bytes": None,
                "text": extracted_text,
                "summary": f"Word leído en memoria ({len(extracted_text):,} caracteres)",
            }
        except Exception as e:
            return {"error": f"No se pudo leer el archivo Word (.docx): {e}"}

    # 4. Texto plano (.txt, .md)
    if ext in (".txt", ".md"):
        try:
            extracted_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            extracted_text = raw_bytes.decode("latin-1", errors="replace")
        extracted_text = extracted_text.strip()
        if not extracted_text:
            return {"error": "El archivo de texto está vacío."}
        return {
            "name": filename,
            "mode": "text",
            "mime_type": "text/plain",
            "raw_bytes": None,
            "text": extracted_text,
            "summary": f"Texto leído en memoria ({len(extracted_text):,} caracteres)",
        }

    return {"error": f"Formato no soportado ({ext}). Usa PDF, DOCX, TXT, MD o imagen (PNG/JPG)."}


DEFAULT_SESSION_PROFILE: Dict[str, Any] = {
    "arquetipo_detectado": None,
    "titularidad": None,
    "gran_tenedor": None,
    "residencia_fiscal_ccaa": None,
    "ubicacion_inmueble_ccaa": None,
    "municipio_inmueble": None,
    "zona_tensionada": None,
    "modalidad_alquiler": None,
    "no_residente": None,
    "fecha_inicio_contrato": None,
    "hechos_clave": [],
}

ALLOWED_PROFILE_KEYS = set(DEFAULT_SESSION_PROFILE.keys())


def get_default_session_profile() -> Dict[str, Any]:
    """Devuelve una copia limpia del perfil de memoria de sesión."""
    return {
        k: (list(v) if isinstance(v, list) else v)
        for k, v in DEFAULT_SESSION_PROFILE.items()
    }


def _extract_explicit_facts_from_user_text(user_text: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Respaldo determinista (cero asunciones): extrae SOLO datos explícitamente mencionados
    por el usuario en su mensaje si el modelo no emitió [PROFILE_UPDATE] en ese turno.
    """
    if not user_text:
        return profile

    updated = {k: (list(v) if isinstance(v, list) else v) for k, v in profile.items()}
    norm = _normalize_search_text(user_text)

    # 1. Municipios y CCAA explícitos (con estado oficial de zona tensionada)
    municipios_map = {
        "talavera de la reina": ("Talavera de la Reina", "Castilla-La Mancha", False),
        "talavera": ("Talavera de la Reina", "Castilla-La Mancha", False),
        "guadalajara": ("Guadalajara", "Castilla-La Mancha", False),
        "toledo": ("Toledo", "Castilla-La Mancha", False),
        "alcala de henares": ("Alcalá de Henares", "Comunidad de Madrid", False),
        "terrassa": ("Terrassa", "Cataluña", True),
        "sabadell": ("Sabadell", "Cataluña", True),
        "barcelona": ("Barcelona", "Cataluña", True),
        "badalona": ("Badalona", "Cataluña", True),
        "hospitalet": ("L'Hospitalet de Llobregat", "Cataluña", True),
        "girona": ("Girona", "Cataluña", True),
        "tarragona": ("Tarragona", "Cataluña", True),
        "lleida": ("Lleida", "Cataluña", True),
        "pamplona": ("Pamplona", "Navarra", True),
        "donostia": ("Donostia / San Sebastián", "País Vasco", True),
        "san sebastian": ("Donostia / San Sebastián", "País Vasco", True),
        "bilbao": ("Bilbao", "País Vasco", True),
        "errenteria": ("Errenteria", "País Vasco", True),
        "a coruna": ("A Coruña", "Galicia", True),
        "valencia": ("Valencia", "Comunidad Valenciana", False),
        "alicante": ("Alicante", "Comunidad Valenciana", False),
        "sevilla": ("Sevilla", "Andalucía", False),
        "malaga": ("Málaga", "Andalucía", False),
        "zaragoza": ("Zaragoza", "Aragón", False),
        "murcia": ("Murcia", "Región de Murcia", False),
    }

    # Distinguir "vivo en X" (residencia fiscal) vs ubicación del inmueble
    res_match = re.search(r"\b(?:vivo|resido|soy residente)\s+en\s+([a-z\s]{3,30})", norm)
    if res_match and not updated.get("residencia_fiscal_ccaa"):
        lugar_res = res_match.group(1).strip()
        if any(w in lugar_res for w in ("extranjero", "fuera de espana", "londres", "francia", "alemania", "eeuu", "suiza", "dubai")):
            updated["no_residente"] = True
            updated["residencia_fiscal_ccaa"] = "Extranjero"
        elif "madrid" in lugar_res:
            updated["residencia_fiscal_ccaa"] = "Comunidad de Madrid"
            updated["no_residente"] = False
        elif "cataluna" in lugar_res or "barcelona" in lugar_res:
            updated["residencia_fiscal_ccaa"] = "Cataluña"
            updated["no_residente"] = False
        elif "valencia" in lugar_res:
            updated["residencia_fiscal_ccaa"] = "Comunidad Valenciana"
            updated["no_residente"] = False
        elif "andalucia" in lugar_res or "sevilla" in lugar_res or "malaga" in lugar_res:
            updated["residencia_fiscal_ccaa"] = "Andalucía"
            updated["no_residente"] = False

    if "no residente" in norm or "vivo fuera de espana" in norm or "resido fuera de espana" in norm:
        updated["no_residente"] = True
    elif "residente en espana" in norm or "residente fiscal en espana" in norm:
        updated["no_residente"] = False

    for kw, (muni, ccaa, zt) in municipios_map.items():
        if re.search(rf"\b{re.escape(kw)}\b", norm):
            # Evitar pisar inmueble si solo se mencionó tras "vivo en <ciudad>"
            if res_match and kw in res_match.group(1) and not re.search(rf"(?:piso|vivienda|inmueble|comprar|alquilar).{{0,35}}\b{re.escape(kw)}\b", norm):
                continue
            updated["municipio_inmueble"] = muni
            updated["ubicacion_inmueble_ccaa"] = ccaa
            updated["zona_tensionada"] = zt
            break

    if not updated.get("ubicacion_inmueble_ccaa") and re.search(r"(?:piso|vivienda|inmueble|comprar|alquilar).{0,35}\bmadrid\b", norm):
        updated["municipio_inmueble"] = "Madrid"
        updated["ubicacion_inmueble_ccaa"] = "Comunidad de Madrid"
        updated["zona_tensionada"] = False

    # 2. Modalidad de alquiler explícita
    if re.search(r"\bhabitacion(?:es)?\b", norm):
        updated["modalidad_alquiler"] = "habitaciones"
    elif "vivienda habitual" in norm:
        updated["modalidad_alquiler"] = "vivienda_habitual"
    elif "alquiler de temporada" in norm or "alquiler temporal" in norm:
        updated["modalidad_alquiler"] = "temporada"
    elif re.search(r"\blocal(?:es)?\s+comercial", norm):
        updated["modalidad_alquiler"] = "local"

    # 3. Titularidad explícita (solo si el usuario la declara)
    if any(p in norm for p in ("persona fisica", "a titulo personal", "como particular", "a mi nombre")):
        updated["titularidad"] = "persona_fisica"
    elif any(p in norm for p in ("persona juridica", "a traves de una sl", "mediante una sl", "como sl", "mi sociedad", "una sociedad limitada", "empresa sl")):
        updated["titularidad"] = "persona_juridica"
    elif "comunidad de bienes" in norm:
        updated["titularidad"] = "comunidad_bienes"

    # 4. Arquetipo inicial solo cuando hay señal clara en lo dicho
    if not updated.get("arquetipo_detectado"):
        if updated.get("no_residente") is True:
            updated["arquetipo_detectado"] = "inversor_no_residente"
        elif updated.get("titularidad") == "persona_juridica":
            updated["arquetipo_detectado"] = "sociedad_inmobiliaria"
        elif updated.get("gran_tenedor") is True and updated.get("titularidad") == "persona_fisica":
            updated["arquetipo_detectado"] = "gran_tenedor_particular"
        elif any(p in norm for p in ("comprar un piso", "invertir", "inversion", "prestamo personal", "roce", "rentabilidad", "otro piso", "segundo piso")):
            updated["arquetipo_detectado"] = "inversor_crecimiento"

    return updated


def _extract_and_merge_profile(raw_text: str, current_profile: Optional[Dict[str, Any]] = None) -> tuple:
    """
    Extrae el bloque oculto [PROFILE_UPDATE] {...} de la respuesta del modelo,
    lo elimina del texto visible y fusiona los campos confirmados en la memoria de sesión.
    """
    merged = get_default_session_profile()
    if isinstance(current_profile, dict):
        for k in ALLOWED_PROFILE_KEYS:
            if k in current_profile and current_profile[k] is not None:
                merged[k] = list(current_profile[k]) if isinstance(current_profile[k], list) else current_profile[k]

    if not raw_text or "[PROFILE_UPDATE]" not in raw_text:
        return raw_text, merged

    idx = raw_text.find("[PROFILE_UPDATE]")
    before = raw_text[:idx]
    after = raw_text[idx + len("[PROFILE_UPDATE]"):]

    # Limpiar posible bloque markdown ```json ... ``` inmediatamente después de la etiqueta
    after_stripped = after.lstrip()
    fence_end_offset = 0
    parse_src = after_stripped
    if after_stripped.startswith("```"):
        newline_pos = after_stripped.find("\n")
        if newline_pos != -1:
            parse_src = after_stripped[newline_pos + 1:]

    brace_idx = parse_src.find("{")
    if brace_idx != -1:
        try:
            decoder = json.JSONDecoder()
            update_obj, end_pos = decoder.raw_decode(parse_src[brace_idx:])
            if isinstance(update_obj, dict):
                for k, v in update_obj.items():
                    if k not in ALLOWED_PROFILE_KEYS or v is None:
                        continue
                    if k == "hechos_clave":
                        if isinstance(v, list):
                            existing = list(merged.get("hechos_clave") or [])
                            for fact in v:
                                fact_str = str(fact).strip()
                                if fact_str and fact_str not in existing:
                                    existing.append(fact_str)
                            merged["hechos_clave"] = existing[-12:]
                    else:
                        if isinstance(v, str) and not v.strip():
                            continue
                        merged[k] = v

            # Conservar cualquier texto posterior al bloque JSON (ej. [RESOURCES] si venía después)
            remainder = parse_src[brace_idx + end_pos:].lstrip()
            if remainder.startswith("```"):
                remainder = remainder[3:].lstrip()
            cleaned_text = f"{before.rstrip()}\n\n{remainder}".strip() if remainder else before.strip()
            return cleaned_text, merged
        except Exception as e:
            print(f"No se pudo parsear [PROFILE_UPDATE]: {e}")

    # Si no había JSON válido, eliminar igualmente la etiqueta residual para no ensuciar el chat
    return before.strip(), merged


def get_chat_response(
    history: list,
    user_input: str,
    system_instruction: str,
    knowledge_context: str = "",
    multimedia_index: Optional[list] = None,
    kb_folder: Optional[str] = None,
    ephemeral_doc: Optional[Dict[str, Any]] = None,
    session_profile: Optional[Dict[str, Any]] = None,
) -> dict:
    """Obtiene respuesta del chat de Gemini con memoria de perfil, coherencia multi-turno y recuperación multi-carpeta."""
    current_profile = get_default_session_profile()
    if isinstance(session_profile, dict):
        for k in ALLOWED_PROFILE_KEYS:
            if k in session_profile and session_profile[k] is not None:
                current_profile[k] = list(session_profile[k]) if isinstance(session_profile[k], list) else session_profile[k]

    client = init_gemini()
    if not client:
        return {
            "text": "Modo demostración: Configura tu API Key para chatear con Gemini real.",
            "recommendations": [],
            "documents": [],
            "updated_profile": current_profile,
        }
    
    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.5-flash")
    
    # Serializar e inyectar el índice multimedia y la memoria de perfil de sesión en el prompt del sistema
    local_resources_str = json.dumps(multimedia_index, ensure_ascii=False) if multimedia_index else "No hay recursos locales disponibles."
    profile_json_str = json.dumps(current_profile, ensure_ascii=False, indent=2)
    system_instruction = (
        system_instruction
        .replace("{multimedia_index_placeholder}", local_resources_str)
        .replace("{session_profile_placeholder}", profile_json_str)
    )
    if "<memoria_perfil_sesion>" not in system_instruction:
        system_instruction += f"\n\n<memoria_perfil_sesion>\n{profile_json_str}\n</memoria_perfil_sesion>"

    # Reglas técnicas de búsqueda externa válidas para TODOS los ámbitos del asistente
    external_hint = (
        "\n\n[MECANISMO DE BÚSQUEDA EXTERNA DE VÍDEOS — TODOS LOS ÁMBITOS INMOBILIARIOS]\n"
        "- Nunca inventes URLs ni incluyas vídeos durante la Fase 1 (triaje).\n"
        "- En la Fase 3 (o si el usuario pide profundizar u oír a un especialista), puedes incluir al final el bloque `[RESOURCES]` con un JSON válido para cualquier ámbito del asistente en España: derecho de arrendamientos (LAU/LPH/LEC), fiscalidad inmobiliaria (IRPF/ITP/amortización), financiación e hipotecas (LCCI/CIRBE/DTI) o estrategia de inversión (rentabilidad/ROCE/mercado).\n"
        "- Si el vídeo trata sobre subidas de renta, prórrogas, alquiler temporal o alquiler de habitaciones, utiliza `\"url\": \"SEARCH_EXTERNAL_POST_OCT2026: <consulta en español>\"` para exigir vídeos publicados después de octubre de 2026.\n"
        "- Para el resto de temas (fiscalidad IRPF/ITP, hipotecas LCCI, financiación/CIRBE, inversión/ROCE, fianza, obras, comunidad), utiliza `\"url\": \"SEARCH_EXTERNAL: <consulta precisa en español>\"`.\n"
        "- Si no es necesario un vídeo o no existe ninguno actualizado, omite completamente el bloque `[RESOURCES]`."
    )

    # Construir historial estructurado para Gemini (Últimas 20 interacciones para mantener coherencia completa)
    contents = []
    expected_role = "user"
    for msg in history[-20:]:
        role = "user" if msg["role"] == "user" else "model"
        
        # Regla estricta de Gemini: Debe empezar por 'user' y alternar
        if role == expected_role:
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg["content"])]
                )
            )
            expected_role = "model" if role == "user" else "user"

    # Enriquecer la query de recuperación documental con el perfil ya confirmado (coherencia entre temas)
    profile_keywords = " ".join(
        str(v) for k, v in current_profile.items()
        if v is not None and k != "hechos_clave" and not isinstance(v, bool)
    )
    if current_profile.get("hechos_clave"):
        profile_keywords += " " + " ".join(current_profile["hechos_clave"][-5:])

    # Inyectar documento temporal del usuario (solo en memoria para esta sesión; nunca persistido)
    ephemeral_doc_block = ""
    retrieval_query = f"{user_input or ''} {profile_keywords}".strip()
    if ephemeral_doc and not ephemeral_doc.get("error"):
        doc_name = ephemeral_doc.get("name", "documento_usuario")
        if ephemeral_doc.get("mode") == "text" and ephemeral_doc.get("text"):
            doc_text = ephemeral_doc["text"][:60000]
            ephemeral_doc_block = (
                f"\n\n<documento_usuario_solo_esta_sesion nombre=\"{doc_name}\">\n"
                f"{doc_text}\n"
                "</documento_usuario_solo_esta_sesion>\n"
                "NOTA: Este documento ha sido adjuntado por el usuario SOLO para esta conversación (no se almacena). "
                "Úsalo para extraer fechas, tipo de alquiler, ubicación y cláusulas exactas sin volver a preguntarle datos que ya aparezcan en él."
            )
            retrieval_query = f"{retrieval_query} {doc_text[:1500]}"
        elif ephemeral_doc.get("mode") == "binary" and ephemeral_doc.get("raw_bytes") and contents:
            # Adjuntar el archivo binario (PDF escaneado o foto) al último mensaje del usuario
            last_user_idx = next((i for i in range(len(contents) - 1, -1, -1) if contents[i].role == "user"), None)
            if last_user_idx is not None:
                contents[last_user_idx].parts.append(
                    types.Part.from_bytes(
                        data=ephemeral_doc["raw_bytes"],
                        mime_type=ephemeral_doc.get("mime_type", "application/pdf"),
                    )
                )
                ephemeral_doc_block = (
                    f"\n\nNOTA SOBRE ARCHIVO ADJUNTO ('{doc_name}'): El usuario ha adjuntado este documento/imagen "
                    "SOLO en memoria para esta conversación (no se almacena). Léelo directamente y extrae los datos "
                    "relevantes (fechas, cláusulas, importes, ubicación) sin pedir al usuario datos que ya figuren en el archivo."
                )
    
    resolved_kb_folder = kb_folder or CLIENT_CONFIG.get("knowledge_base_folder")
    if resolved_kb_folder and os.path.exists(resolved_kb_folder):
        contexto_seguro = retrieve_relevant_knowledge(
            resolved_kb_folder,
            retrieval_query,
            history=history,
            max_chars=90000,
        )
    else:
        contexto_seguro = knowledge_context[:90000] if knowledge_context else "No hay documentos cargados."

    fecha_hoy_str = datetime.datetime.now().strftime("%d/%m/%Y")
    fecha_block = (
        f"\n\n[FECHA ACTUAL DE REFERENCIA]\n"
        f"Hoy es {fecha_hoy_str}. Utiliza SIEMPRE esta fecha para verificar años transcurridos, "
        f"vencimientos de prórroga obligatoria (5 años persona física / 7 años persona jurídica) y plazos de preaviso.\n\n"
        "[ACTUALIZACIÓN OBLIGATORIA DE MEMORIA DE PERFIL — INCLUIDA FASE 1]\n"
        "Al FINAL de tu respuesta (incluso si todavía estás en Fase 1 haciendo preguntas de triaje), SIEMPRE que el usuario "
        "haya mencionado CUALQUIER dato concreto (municipio, CCAA, modalidad de alquiler, titularidad, residencia, intención de inversión, "
        "fecha de contrato o hechos clave), DEBES incluir el bloque oculto:\n"
        "[PROFILE_UPDATE]\n"
        '{"campo_confirmado": "valor"}\n'
        "Incluye ÚNICAMENTE datos explícitamente confirmados por el usuario o su documento (NUNCA supongas titularidad ni gran_tenedor si no lo dijo)."
    )

    full_system_instruction = (
        f"{system_instruction}{fecha_block}{external_hint}{ephemeral_doc_block}\n\n"
        f"Información de Contexto (Base Documental en knowledge_base):\n{contexto_seguro}"
    )

    recent_user_context = " ".join(
        [user_input or ""] + [m.get("content", "") for m in history[-6:] if m.get("role") == "user"]
    )
    needs_post_oct_2026 = bool(requiere_video_post_oct_2026 and requiere_video_post_oct_2026(recent_user_context))
    
    try:
        gen_config_kwargs: Dict[str, Any] = {
            "system_instruction": full_system_instruction,
            "temperature": 0.15,
        }
        # Activar razonamiento interno en modelos Gemini 2.5 para verificar fechas, plazos y lógica legal
        if "2.5" in str(model_name) and hasattr(types, "ThinkingConfig"):
            gen_config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=2048)

        try:
            response = llamar_gemini_con_rotacion_y_reintento(
                model_name=model_name,
                contents=contents,
                config=types.GenerateContentConfig(**gen_config_kwargs)
            )
        except Exception as cfg_err:
            if "thinking" in str(cfg_err).lower() and "thinking_config" in gen_config_kwargs:
                gen_config_kwargs.pop("thinking_config", None)
                response = llamar_gemini_con_rotacion_y_reintento(
                    model_name=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(**gen_config_kwargs)
                )
            else:
                raise cfg_err
        raw_response = response.text

        # 1. Extraer y fusionar actualización de perfil de sesión [PROFILE_UPDATE] + respaldo determinista
        base_with_explicit = _extract_explicit_facts_from_user_text(user_input, current_profile)
        text_part, updated_profile = _extract_and_merge_profile(raw_response, base_with_explicit)
        recommendations = []
        
        if "[RESOURCES]" in text_part:
            parts = text_part.split("[RESOURCES]", 1)
            text_part = parts[0].strip()
            try:
                json_str = parts[1].strip()

                # Limpieza de bloques de código Markdown si el modelo los añade
                if "```" in json_str:
                    json_str = json_str.replace("```json", "").replace("```", "").strip()

                # Buscar el inicio de la lista JSON y usar raw_decode para ignorar texto extra
                start_idx = json_str.find('[')
                if start_idx != -1:
                    json_data_str = json_str[start_idx:]
                    decoder = json.JSONDecoder()
                    initial_recs, _ = decoder.raw_decode(json_data_str)
                    
                    # Mapa rápido de recursos locales para validar fecha de publicación si aplica
                    local_by_url = {
                        item.get("full_url"): item
                        for item in (multimedia_index or [])
                        if isinstance(item, dict) and item.get("full_url")
                    }

                    # Procesar y expandir búsquedas externas
                    for rec in initial_recs:
                        url = rec.get("url", "")
                        if isinstance(url, str) and "SEARCH_EXTERNAL_POST_OCT2026:" in url:
                            query = url.split("SEARCH_EXTERNAL_POST_OCT2026:", 1)[1].strip()
                            external_results = (
                                buscar_youtube_externo(query, solo_post_oct_2026=True, contexto_consulta=recent_user_context)
                                if buscar_youtube_externo else None
                            )
                            if isinstance(external_results, list) and len(external_results) > 0:
                                recommendations.extend(external_results)
                        elif isinstance(url, str) and "SEARCH_EXTERNAL:" in url:
                            query = url.split("SEARCH_EXTERNAL:", 1)[1].strip()
                            # Aplicar filtro post-octubre 2026 solo si la consulta del vídeo toca esas materias reformadas
                            query_needs_post_oct = bool(
                                requiere_video_post_oct_2026 and requiere_video_post_oct_2026(query)
                            )
                            external_results = (
                                buscar_youtube_externo(
                                    query,
                                    solo_post_oct_2026=query_needs_post_oct,
                                    contexto_consulta=recent_user_context,
                                )
                                if buscar_youtube_externo else None
                            )
                            if isinstance(external_results, list) and len(external_results) > 0:
                                recommendations.extend(external_results)
                        else:
                            # Si el tema exige vídeo post-octubre 2026, validar fecha en recursos locales
                            if needs_post_oct_2026 and url in local_by_url:
                                fecha_pub = str(
                                    local_by_url[url].get("fecha_publicacion")
                                    or local_by_url[url].get("published_at")
                                    or ""
                                ).strip()
                                if not fecha_pub or fecha_pub[:10] < POST_OCT_2026_PREFIX:
                                    continue
                            recommendations.append(rec)
                else:
                    pass # No se encontró un array JSON válido
            except (json.JSONDecodeError, IndexError) as e:
                print(f"No se pudo parsear los recursos de la respuesta: {e}")
        
        # Extraer documentos descargables [DOCUMENT title="..."]...[/DOCUMENT] si los hay
        text_part, generated_docs = _extract_generated_documents(text_part)

        return {
            "text": text_part,
            "recommendations": recommendations,
            "documents": generated_docs,
            "updated_profile": updated_profile,
        }
    except Exception as e:
        return {
            "text": f"⚠️ **Error inesperado:** `{e}`",
            "recommendations": [],
            "documents": [],
            "updated_profile": current_profile,
        }

@st.cache_data(show_spinner=False, ttl=86400)
def generate_dynamic_roles(knowledge_context):
    """Genera roles/niveles jerárquicos basados en el contenido."""
    client = init_gemini()
    # Roles por defecto si falla la IA o no hay contenido
    default_roles = ["Principiante", "Intermedio", "Avanzado", "Experto"]
    
    if not client or not knowledge_context.strip():
        return default_roles

    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.5-flash")
    
    prompt = f"""
    Analiza el siguiente contenido educativo y define 4 niveles o roles jerárquicos adecuados para un estudiante de este material.
    Los roles deben ser temáticos y específicos al contenido proporcionado.
    Deben ir de menor a mayor experiencia.
    
    CONTENIDO (Muestra):
    {knowledge_context[:12000]} 
    
    Responde ÚNICAMENTE con un JSON válido que sea una lista de 4 strings.
    Ejemplo: ["Aprendiz de Cocina", "Cocinero de Línea", "Sous Chef", "Chef Ejecutivo"]
    """
    
    try:
        response = llamar_gemini_con_rotacion_y_reintento(
            model_name=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        roles = json.loads(response.text)
        if isinstance(roles, list) and len(roles) > 0:
            return roles
        return default_roles
    except Exception as e:
        print(f"Error generando roles dinámicos: {e}")
        return default_roles

@st.cache_data(show_spinner=False, ttl=86400)
def generate_dynamic_topics(knowledge_context):
    """Genera temas de examen basados en el contenido."""
    client = init_gemini()
    default_topics = ["Conocimiento General"]
    
    if not client or not knowledge_context.strip():
        return default_topics

    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.5-flash")
    sampled_context = _sample_knowledge_for_training(
        CLIENT_CONFIG.get("knowledge_base_folder"),
        knowledge_context,
        max_chars=24000,
    )
    
    prompt = f"""
    Analiza la siguiente documentación sobre derecho de arrendamientos urbanos, fiscalidad inmobiliaria (IRPF/ITP), financiación hipotecaria (LCCI/CIRBE) y estrategia de inversión inmobiliaria en España, y extrae una lista de 6 a 10 temas principales sobre los que se podría evaluar a propietarios, inversores o entidades.
    Los temas deben ser breves, descriptivos y cubrir diferentes carpetas/normas presentes en la base documental (LAU, Ley 12/2023, RDL 29/2026, Código Civil, LEC, LPH, IRPF alquileres, ITP/AJD compra, LCCI hipotecas, financiación/CIRBE y rentabilidad/estrategia de inversión).
    
    CONTENIDO (Muestra de todos los documentos):
    {sampled_context} 
    
    Responde ÚNICAMENTE con un JSON válido que sea una lista de strings.
    Ejemplo: ["Duración y prórrogas (persona física vs. jurídica)", "Actualización de renta e IRAV", "IRPF del alquiler: gastos, amortización 3% y reducciones", "ITP y valor de referencia en la compra", "Hipotecas (LCCI), DTI y riesgo CIRBE", "Rentabilidad neta, ROCE y estrategia de inversión"]
    """
    
    try:
        response = llamar_gemini_con_rotacion_y_reintento(
            model_name=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        topics = json.loads(response.text)
        if isinstance(topics, list) and len(topics) > 0:
            return topics
        return default_topics
    except Exception as e:
        print(f"Error generando temas dinámicos: {e}")
        return default_topics

def _get_gsheets_spreadsheet_url() -> Optional[str]:
    """Obtiene de forma segura la URL del Google Sheet desde st.secrets si está configurada."""
    try:
        return st.secrets["connections"]["gsheets"]["spreadsheet"]
    except Exception:
        return None


def log_user_prompt(
    prompt_text: str,
    worksheet_name: str,
    role: str = "User",
    response_text: str = "",
    session_id: str = "",
    doc_attached: Any = False,
    arquetipo: str = "",
):
    """
    Registra un turno completo de conversación (prompt + respuesta del asistente + session_id + arquetipo)
    en Google Sheets para auditoría y mejora de calidad (QA).
    Nunca registra el contenido de documentos adjuntados por el usuario (solo 'Sí (nombre)' o 'No').
    """
    if GSheetsConnection is None:
        print("GSheetsConnection no disponible. Saltando registro de conversación.")
        return

    if not prompt_text or not worksheet_name:
        return

    target_cols = ["session_id", "timestamp", "role", "arquetipo", "prompt", "response", "doc_attached"]

    if isinstance(doc_attached, str) and doc_attached.strip():
        doc_flag = f"Sí ({doc_attached.strip()})" if doc_attached.strip() not in ("Sí", "No") else doc_attached.strip()
    elif doc_attached:
        doc_flag = "Sí"
    else:
        doc_flag = "No"

    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        url = _get_gsheets_spreadsheet_url()
        
        new_prompt_df = pd.DataFrame([
            {
                "session_id": session_id or "sin_sesion",
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "role": role,
                "arquetipo": arquetipo or "",
                "prompt": prompt_text,
                "response": (response_text or "")[:15000],
                "doc_attached": doc_flag,
            }
        ])

        try:
            existing_df = (
                conn.read(spreadsheet=url, worksheet=worksheet_name, ttl=0)
                if url else conn.read(worksheet=worksheet_name, ttl=0)
            )
            if existing_df is None or existing_df.empty:
                existing_df = pd.DataFrame(columns=target_cols)
            else:
                existing_df = existing_df.dropna(how="all")
                if "prompt" not in existing_df.columns:
                    existing_df = pd.DataFrame(columns=target_cols)
                else:
                    for col in target_cols:
                        if col not in existing_df.columns:
                            existing_df[col] = ""
                    existing_df = existing_df[target_cols]
        except Exception:
            existing_df = pd.DataFrame(columns=target_cols)

        updated_df = pd.concat([existing_df, new_prompt_df], ignore_index=True)
        if url:
            conn.update(spreadsheet=url, worksheet=worksheet_name, data=updated_df)
        else:
            conn.update(worksheet=worksheet_name, data=updated_df)

    except Exception as e:
        # Fallo silencioso para no impactar la experiencia de usuario
        print(f"Error al registrar conversación en Google Sheets ({worksheet_name}): {e}")


def get_logged_prompts(worksheet_name: str):
    """Recupera los prompts registrados desde Google Sheets."""
    if GSheetsConnection is None:
        return pd.DataFrame()

    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        url = _get_gsheets_spreadsheet_url()
        df = (
            conn.read(spreadsheet=url, worksheet=worksheet_name, ttl=0)
            if url else conn.read(worksheet=worksheet_name, ttl=0)
        )
        if df is None or df.empty:
            return pd.DataFrame()
        return df.dropna(how="all")
    except Exception as e:
        print(f"Error leyendo prompts ({worksheet_name}): {e}")
        return pd.DataFrame()

def calculate_roi_metrics(time_saved_per_interaction, cost_per_hour, participation_threshold=10):
    """Calcula las métricas de ROI basado en la fórmula de Olivia España."""
    data = {}
    try:
        if GSheetsConnection:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet="Users", ttl=0)
            
            url = None
            try:
                url = st.secrets["connections"]["gsheets"]["spreadsheet"]
            except Exception:
                pass
            
            df = conn.read(spreadsheet=url, worksheet="Users", ttl=0) if url else conn.read(worksheet="Users", ttl=0)
            
            if not df.empty and "username" in df.columns:
                data = df.set_index("username").to_dict(orient="index")
    except Exception:
        pass

    if not data:
        return None

    # Excluir admin del cálculo para medir solo usuarios reales
    users = [u for k, u in data.items() if k != 'admin']
    N = len(users)
    
    if N == 0:
        return {"N": 0, "P": 0, "F": 0, "AH_op": 0, "Me": 1.0, "Total_Value": 0.0, "active_count": 0}

    # P: Tasa de participación (usuarios con >= 10 usos)
    # Usamos 'active_sessions' como métrica de uso
    active_users = [u for u in users if u.get("active_sessions", 0) >= participation_threshold]
    n_active = len(active_users)
    P = n_active / N
    
    # F: Frecuencia media (de los usuarios activos)
    if n_active > 0:
        avg_freq = sum(u.get("active_sessions", 0) for u in active_users) / n_active
    else:
        avg_freq = 0
        
    # AH_op = (N * P) * (F * Ts)
    AH_op = (N * P) * (avg_freq * time_saved_per_interaction)
    
    # Me: Multiplicador de Evolución
    # Promedio del multiplicador de los usuarios activos
    max_level_idx = len(BELTS) - 1
    if max_level_idx < 1: max_level_idx = 1
    
    sum_me = 0
    sum_me_hist = 0
    if n_active > 0:
        for u in active_users:
            score = u.get("score", 0)
            # Encontrar índice del cinturón (0 a 6)
            idx = 0
            for i, belt in enumerate(BELTS):
                if score >= belt["threshold"]:
                    idx = i
                else:
                    break
            
            # Fórmula: 1 + (Nivel Actual - 1) / Nivel Máximo
            # Dado que idx es base 0, equivale a (Nivel Actual - 1)
            me_user = 1 + (idx / max_level_idx)
            sum_me += me_user
            # Para el histórico, asumimos evolución lineal: Promedio entre inicio (1.0) y actual
            sum_me_hist += (1.0 + me_user) / 2
        Me = sum_me / n_active
        Me_avg = sum_me_hist / n_active
    else:
        Me = 1.0
        Me_avg = 1.0
        
    # Valor Total
    # Usamos Me_avg para el cálculo histórico porque los usuarios no empezaron siendo expertos
    total_value = (AH_op * Me_avg) * cost_per_hour
    
    return {
        "N": N,
        "P": P,
        "F": avg_freq,
        "AH_op": AH_op,
        "Me": Me,
        "Me_avg": Me_avg,
        "Total_Value": total_value,
        "active_count": n_active
    }

def calculate_historical_improvement_rate(current_me, avg_sessions, freq_monthly):
    """
    Calcula una tasa de mejora mensual sugerida basada en el histórico real.
    Estima cuánto ha mejorado el usuario promedio por mes de uso.
    """
    if freq_monthly <= 0 or avg_sessions <= 0:
        return 0.0
    
    # Estimar meses que llevan usando la herramienta (Sesiones Totales / Frecuencia Mensual)
    estimated_months = avg_sessions / freq_monthly
    if estimated_months < 1.0: estimated_months = 1.0
    
    # Mejora total obtenida hasta ahora (Me actual - Base 1.0)
    total_improvement = current_me - 1.0
    if total_improvement < 0: total_improvement = 0.0
    
    # Tasa mensual lineal
    return total_improvement / estimated_months

# --- MOTOR DE CÁLCULO ROI Y VISUALIZACIÓN ---

class CalculadoraROI:
    """
    Motor lógico para el cálculo de ROI en proyectos de gestión del cambio.
    Modela el impacto financiero basado en la adopción y la evolución del aprendizaje.
    """

    def __init__(
        self,
        n_usuarios: int,
        coste_hora: float,
        inversion_inicial: float,
        tiempo_ahorrado_mins: float,
        frecuencia_uso_mensual: float,
        tasa_adopcion_pct: float,
        nivel_promedio_inicial: float,
        tasa_mejora_mensual: float
    ) -> None:
        self.n_usuarios = n_usuarios
        self.coste_hora = coste_hora
        self.inversion_inicial = inversion_inicial
        self.tiempo_ahorrado_hours = tiempo_ahorrado_mins / 60.0
        self.frecuencia_uso_mensual = frecuencia_uso_mensual
        self.tasa_adopcion_pct = tasa_adopcion_pct
        self.nivel_promedio_inicial = nivel_promedio_inicial
        self.tasa_mejora_mensual = tasa_mejora_mensual

    def proyectar_ahorro_temporal(self, meses: int) -> List[Dict[str, Any]]:
        proyeccion = []
        ahorro_acumulado = 0.0

        # Cálculo del Ahorro Base (Constante operativa)
        usuarios_activos = self.n_usuarios * self.tasa_adopcion_pct
        ahorro_base_mensual = (
            usuarios_activos * 
            self.frecuencia_uso_mensual * 
            self.tiempo_ahorrado_hours * 
            self.coste_hora
        )

        for t in range(1, meses + 1):
            # 1. Calcular Multiplicador de Evolución (Me)
            factor_aprendizaje = 1 + (t * self.tasa_mejora_mensual)
            # Aplicamos el factor de aprendizaje a la eficiencia total (Base + Bonus Nivel)
            # Antes solo aplicaba al bonus, lo que anulaba el efecto en usuarios principiantes
            multiplicador_evolucion = (1 + (self.nivel_promedio_inicial / 10.0)) * factor_aprendizaje

            # 2. Calcular Ahorros
            ahorro_total_mensual = ahorro_base_mensual * multiplicador_evolucion
            ahorro_extra_evolucion = ahorro_total_mensual - ahorro_base_mensual
            
            # 3. Acumulados y ROI
            ahorro_acumulado += ahorro_total_mensual
            roi_perc = ((ahorro_acumulado - self.inversion_inicial) / self.inversion_inicial) * 100 if self.inversion_inicial > 0 else 0
            break_even_alcanzado = ahorro_acumulado >= self.inversion_inicial

            registro_mes = {
                "mes": t,
                "ahorro_base": round(ahorro_base_mensual, 2),
                "ahorro_extra_evolucion": round(ahorro_extra_evolucion, 2),
                "ahorro_total_mensual": round(ahorro_total_mensual, 2),
                "ahorro_acumulado": round(ahorro_acumulado, 2),
                "inversion_objetivo": self.inversion_inicial,
                "roi_perc": round(roi_perc, 2),
                "break_even_alcanzado": break_even_alcanzado
            }
            proyeccion.append(registro_mes)

        return proyeccion

def graficar_break_even(df: pd.DataFrame):
    if go is None:
        st.error("La librería 'plotly' no está instalada. Ejecuta: pip install plotly")
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['mes'], y=df['inversion_objetivo'], mode='lines', name='Inversión Inicial', line=dict(color='firebrick', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=df['mes'], y=df['ahorro_acumulado'], mode='lines+markers', name='Ahorro Acumulado', line=dict(color='mediumseagreen', width=3), fill='tozeroy', fillcolor='rgba(60, 179, 113, 0.1)'))
    fig.update_layout(title="<b>Punto de Equilibrio (Break Even)</b><br><sup>Cruce de Inversión vs Retorno Acumulado</sup>", xaxis_title="Meses", yaxis_title="Valor (€)", template="plotly_white", hovermode="x unified")
    return fig

def graficar_evolucion_roi(df: pd.DataFrame):
    if go is None:
        return None
    colors = ['crimson' if val < 0 else 'forestgreen' for val in df['roi_perc']]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['mes'], y=df['roi_perc'], marker_color=colors, text=df['roi_perc'].apply(lambda x: f"{x}%"), textposition='auto'))
    fig.update_layout(title="<b>Evolución del ROI (%)</b><br><sup>Retorno sobre la Inversión mes a mes</sup>", xaxis_title="Meses", yaxis_title="ROI (%)", template="plotly_white", shapes=[dict(type="line", x0=0, x1=max(df['mes'])+0.5, y0=0, y1=0, line=dict(color="black", width=1))])
    return fig

def graficar_impacto_aprendizaje(df: pd.DataFrame):
    if go is None:
        return None
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['mes'], y=df['ahorro_base'], name='Ahorro Operativo Base', marker_color='steelblue'))
    fig.add_trace(go.Bar(x=df['mes'], y=df['ahorro_extra_evolucion'], name='Ahorro por Evolución (Me)', marker_color='darkorange'))
    fig.update_layout(title="<b>Impacto Económico de la Evolución</b><br><sup>Diferencia entre uso básico y experto</sup>", xaxis_title="Meses", yaxis_title="Ahorro Mensual (€)", barmode='stack', template="plotly_white", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

def analyze_prompt_patterns(prompts_list):
    """Analiza una lista de prompts para identificar patrones, temáticas e inquietudes."""
    client = init_gemini()
    if not client or not prompts_list:
        return []

    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.5-flash")
    
    # Tomamos una muestra representativa si son muchos para no saturar el contexto
    sample_prompts = prompts_list[:50] if len(prompts_list) > 50 else prompts_list
    text_data = "\n".join([f"- {p}" for p in sample_prompts]) 

    prompt = f"""
    Analiza la siguiente lista de prompts.
    Formato de entrada: "[ROL] Texto del prompt".

    INSTRUCCIONES:
    1. FILTRADO ESTRICTO: Ignora saludos, despedidas, frases genéricas ("hola", "gracias"), respuestas cortas de tests (ej. "a", "b", "c", "si", "no"), monosílabos y textos sin sentido semántico o valor de análisis.
    2. JERARQUÍA: Identifica ROL -> TEMÁTICA -> INQUIETUD.
    3. AGRUPACIÓN:
       - Agrupa por ROL primero.
       - Dentro del rol, agrupa por TEMÁTICA.
       - Dentro de la temática, agrupa por INQUIETUD semántica (si preguntan lo mismo con otras palabras).
       - Si dos roles preguntan lo mismo, deben aparecer como entradas separadas (una para cada rol).
    
    LISTA:
    {text_data}
    
    SALIDA JSON (Lista de objetos):
    [
        {{
            "rol": "Manager",
            "tematica": "Gestión de Stakeholders",
            "inquietud": "Mapa de Empatía",
            "frecuencia": 2,
            "ejemplos": ["prompt 1", "prompt 2"]
        }}
    ]
    """

    try:
        response = llamar_gemini_con_rotacion_y_reintento(
            model_name=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error analizando patrones: {e}")
        return []

def graficar_patrones_prompts(data):
    """Genera un Treemap jerárquico: Rol -> Temática -> Inquietud."""
    if go is None or not data:
        return None
    
    ids = []
    labels = []
    parents = []
    values = []
    hover_text = []
    customdata = []
    
    # Nodo Raíz
    root_id = "ROOT"
    ids.append(root_id)
    labels.append("Temáticas")
    parents.append("")
    values.append(0) # Se calculará automáticamente o se ignora en visualización
    hover_text.append("Total")
    customdata.append("Global (Visión General)")

    # Estructuras auxiliares para evitar duplicados de nodos padres
    roles_added = set()
    topics_added = set()

    for item in data:
        rol = item.get('rol', 'General')
        tematica = item.get('tematica', 'Varios')
        # Asegurar que tematica no sea nula
        if not tematica: tematica = "Varios"
        
        # 1. Nivel ROL
        role_id = f"ROLE_{rol}"
        if role_id not in roles_added:
            ids.append(role_id)
            labels.append(rol)
            parents.append(root_id)
            values.append(0)
            hover_text.append(f"Rol: {rol}")
            roles_added.add(role_id)
            customdata.append(f"Rol: {rol}")
            
        # 2. Nivel TEMÁTICA (Única por Rol)
        topic_id = f"TOPIC_{rol}_{tematica}"
        if topic_id not in topics_added:
            ids.append(topic_id)
            labels.append(tematica)
            parents.append(role_id)
            values.append(0)
            hover_text.append(f"Temática: {tematica}")
            topics_added.add(topic_id)
            customdata.append(f"Tema: {tematica}")

    # 3. Nivel INQUIETUD (Hojas)
    for i, item in enumerate(data):
        rol = item.get('rol', 'General')
        tematica = item.get('tematica', 'Varios')
        if not tematica: tematica = "Varios"
        inquietud = item.get('inquietud', 'Consulta')
        freq = item.get('frecuencia', 1)
        ejemplos = "<br>".join([f"- {ex}" for ex in item.get('ejemplos', [])[:3]])
        
        topic_id = f"TOPIC_{rol}_{tematica}"
        leaf_id = f"LEAF_{i}" # ID único simple
        
        ids.append(leaf_id)
        labels.append(f"{inquietud} ({freq})")
        parents.append(topic_id)
        values.append(freq)
        hover_text.append(f"<b>{inquietud}</b><br>Frecuencia: {freq}<br>Ejemplos:<br>{ejemplos}")
        customdata.append(f"Inquietud: {inquietud}")

    fig = go.Figure(go.Treemap(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        textinfo="label",
        hovertext=hover_text,
        hoverinfo="text",
        marker=dict(colorscale='Teal'),
        customdata=customdata
    ))
    
    fig.update_layout(
        title="<b>Mapa de Inquietudes (Jerarquía: Rol > Temática > Inquietud)</b>",
        margin=dict(t=50, l=0, r=0, b=0)
    )
    return fig

def generate_action_plan(patterns, focus="Global", knowledge_context=""):
    """Genera un plan de acción estratégico basado en los patrones de inquietudes."""
    client = init_gemini()
    if not client:
        return "⚠️ Error: No se pudo conectar con el motor de IA para generar el plan."

    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.5-flash")
    
    # Serializar patrones (limitado para no saturar contexto si hay muchos)
    patterns_summary = json.dumps(patterns[:30], indent=2, ensure_ascii=False)
    
    prompt = f"""
    Actúa como un Consultor Estratégico de Formación y Desarrollo (L&D).
    Analiza los siguientes patrones de consultas de usuarios (inquietudes detectadas en la plataforma):
    
    CONTEXTO DE LA BASE DE CONOCIMIENTO (Referencia):
    {knowledge_context[:10000] if knowledge_context else "No disponible."}
    
    DATOS DE TENDENCIAS:
    {patterns_summary}
    
    TU TAREA:
    Diseñar un PLAN DE ACCIÓN recomendado para mejorar la capacitación.
    
    ENFOQUE DEL ANÁLISIS: {focus}
    
    INSTRUCCIONES:
    1. PRIORIZACIÓN POR PESO: Observa la 'frecuencia' de cada inquietud. Tu plan DEBE priorizar y dar más peso a los temas con mayor frecuencia (mayor número de interacciones).
    2. Si el enfoque es 'Global', identifica las brechas de conocimiento más críticas en toda la organización.
    3. Si el enfoque es un 'Rol' o 'Tema' específico, propón soluciones tácticas para ese segmento.
    4. FORMATO: Usa Markdown. Estructura: "Diagnóstico (Priorizado por Peso)", "Acciones Inmediatas (Quick Wins)" y "Propuesta de Contenido a Largo Plazo".
    5. Sé ejecutivo, directo y orientado a resultados.
    """
    
    try:
        response = llamar_gemini_con_rotacion_y_reintento(
            model_name=model_name,
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Error generando el plan de acción: {e}"