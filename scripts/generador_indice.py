import os
import json
import pandas as pd
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("⚠️ Advertencia: 'requests' y/o 'beautifulsoup4' no están instaladas. El scraping web no funcionará.")
    requests = None
    BeautifulSoup = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: La librería 'google-genai' no está instalada.")
    genai = None

# --- CONFIGURACIÓN ---
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not GEMINI_API_KEY:
    try:
        import streamlit as st
        GEMINI_API_KEY = st.secrets.get("GOOGLE_API_KEY")
    except Exception:
        pass

# Rutas relativas asumiendo ejecución desde la raíz del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(BASE_DIR) == "scripts":
    BASE_DIR = os.path.dirname(BASE_DIR)

# Búsqueda robusta del archivo multimedia.csv
possible_paths = [
    os.path.join(BASE_DIR, "knowledge_base", "multimedia.csv"),
    os.path.join(BASE_DIR, "knowledge_Base", "multimedia.csv"),
    os.path.join(BASE_DIR, "data", "multimedia.csv")
]

DATA_FILE = next((p for p in possible_paths if os.path.exists(p)), possible_paths[0])
OUTPUT_INDEX = os.path.join(os.path.dirname(DATA_FILE), "video_index.json")

def get_youtube_id(url):
    """Extrae el ID de video de una URL de YouTube estándar."""
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return None

def extract_generic_metadata(url):
    """Extrae el título y la descripción de páginas web usando scraping básico."""
    if requests is None or BeautifulSoup is None:
        return f"URL: {url}\n(No se pudo inspeccionar la web por falta de librerías. Intenta deducir de qué trata por el link)."
        
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        title = soup.title.string if soup.title else "Sin título"
        
        # Buscar meta descripción estándar o de OpenGraph (redes sociales)
        meta_desc = soup.find("meta", attrs={"name": "description"}) or \
                    soup.find("meta", property="og:description")
                    
        description = meta_desc["content"] if meta_desc else "Sin descripción disponible."

        return f"TÍTULO WEB: {title}\nDESCRIPCIÓN OFICIAL: {description}"
    except Exception as e:
        return f"Error de lectura web: {e}"

def generate_index():
    """
    Lee el CSV, extrae contexto real (transcripciones o scraping) y usa Gemini
    para estructurar un JSON de indexación determinista y sin alucinaciones.
    """
    if not GEMINI_API_KEY:
        print("❌ Error Crítico: Falta la variable de entorno GOOGLE_API_KEY.")
        return

    if not os.path.exists(DATA_FILE):
        print(f"❌ Error: No se encuentra el archivo de datos: {DATA_FILE}")
        return

    print(f"📂 Leyendo inventario desde {DATA_FILE}...")
    try:
        df = pd.read_csv(DATA_FILE)
        df = df.fillna("") # Práctica defensiva para evitar NaN en cadenas
    except Exception as e:
        print(f"❌ Error leyendo CSV: {e}")
        return

    if 'Tipo' in df.columns:
        videos = df[df['Tipo'] == 'Video']
    else:
        print("⚠️ Advertencia: Columna 'Tipo' no encontrada, procesando todo el CSV.")
        videos = df

    master_index = {}
    client = genai.Client(api_key=GEMINI_API_KEY)
    formatter = TextFormatter()

    print(f"🔍 Procesando {len(videos)} enlaces para indexación semántica...")

    for _, row in videos.iterrows():
        resource_id = str(row.get('ID_Recurso', '')).strip()
        url = str(row.get('URL', row.get('Ruta_o_URL', ''))).strip()
        
        if not url:
            continue

        yt_id = get_youtube_id(url)

        # Autogenerar un ID robusto si el usuario solo subió la URL
        if not resource_id:
            resource_id = f"VID-{yt_id if yt_id else url.split('/')[-1][:15]}"

        print(f"\n   🌐 Procesando ID: {resource_id} | URL: {url}")
        
        contexto_extraido = ""

        # 1. Motor de Extracción Híbrido
        if yt_id:
            print("      ▶️ Detectado YouTube. Extrayendo transcripción...")
            try:
                # Soporte dual: API estándar vs API instanciada (wrapper específico de tu entorno)
                if hasattr(YouTubeTranscriptApi, 'get_transcript'):
                    transcript = YouTubeTranscriptApi.get_transcript(yt_id, languages=['es', 'en'])
                else:
                    yt_api = YouTubeTranscriptApi()
                    fetched = yt_api.fetch(yt_id, languages=['es', 'en'])
                    transcript = fetched.to_raw_data() if hasattr(fetched, 'to_raw_data') else fetched
                
                try:
                    contexto_extraido = formatter.format_transcript(transcript)
                except Exception:
                    contexto_extraido = " ".join([t.get('text', '') for t in transcript])
            except Exception as e:
                print(f"      ⚠️ Subtítulos no disponibles. Activando scraping de respaldo... ({e})")
                contexto_extraido = extract_generic_metadata(url)
        else:
            print("      🎤 URL externa detectada. Ejecutando web scraping...")
            contexto_extraido = extract_generic_metadata(url)

        # Truncar para no exceder la ventana de contexto de manera innecesaria
        contexto_extraido = contexto_extraido[:30000]

        # 2. Generación determinista con Gemini
        prompt = f"""
        Analiza la siguiente información extraída en tiempo real de un recurso multimedia de formación corporativa.
        Genera metadatos JSON estrictos para que un sistema RAG pueda recomendar este recurso.
        
        INFORMACIÓN EXTRAÍDA DE LA URL:
        {contexto_extraido} 
        
        INSTRUCCIONES ESTRUCTURALES:
        1. Identifica el 'tema_clave' principal.
        2. Extrae una lista de 'conceptos_secundarios'.
        3. Define el 'nivel_dificultad' (Principiante, Intermedio, Avanzado).
        4. Define el 'perfil_ideal' (ej. Manager, Consultor, Liderazgo, Equipo General).
        5. Explica el 'contexto_uso' (En qué situación corporativa específica se debe prescribir este recurso).
        6. Extrae 'timestamp_inicio' y 'timestamp_fin' SOLO si la información extraída contiene tiempos claros. Si no los hay, devuelve "". NUNCA te inventes los tiempos.
        7. Genera un 'resumen_ejecutivo' de 2 líneas y un 'resumen_detallado' de 1 párrafo.
        8. Genera los 'parametros_url' (ej. "&t=120s") SOLO si aplica. Si no, devuelve "".
        9. Devuelve SOLO JSON con las claves exactas: tema_clave, conceptos_secundarios (lista), nivel_dificultad, perfil_ideal, contexto_uso, timestamp_inicio, timestamp_fin, parametros_url, resumen_ejecutivo, resumen_detallado.
        """

        try:
            print("      🧠 Sintetizando JSON con Gemini 2.0 Flash...")
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            datos_gemini = json.loads(response.text)
            
            if isinstance(datos_gemini, list):
                if len(datos_gemini) > 0:
                    metadata = datos_gemini[0]
                else:
                    raise ValueError("Gemini devolvió una lista JSON vacía.")
            else:
                metadata = datos_gemini

            metadata["original_url"] = url
            metadata["full_url"] = f"{url}{metadata.get('parametros_url', '')}"
            
            master_index[resource_id] = metadata
            print(f"      ✅ Indexado: {metadata.get('tema_clave', 'Tema no definido')}")

        except Exception as e:
            print(f"      ❌ Fallo al procesar la inferencia: {e}")

    # Guardar el índice maestro
    os.makedirs(os.path.dirname(OUTPUT_INDEX), exist_ok=True)
    with open(OUTPUT_INDEX, 'w', encoding='utf-8') as f:
        json.dump(master_index, f, indent=4, ensure_ascii=False)
    
    print(f"\n✨ Índice generado y blindado contra alucinaciones en: {OUTPUT_INDEX}")

if __name__ == "__main__":
    generate_index()