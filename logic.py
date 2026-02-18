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
import pandas as pd
import streamlit as st
import json
import os
from config import CLIENT_CONFIG, SECURITY_CONFIG

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
    
    return genai.Client(api_key=api_key)

def load_knowledge_base(folder_path):
    """Lee archivos de texto de la carpeta especificada para crear el contexto."""
    context_text = ""
    if not os.path.exists(folder_path):
        return ""
        
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        # Filtramos por extensiones de texto comunes
        if os.path.isfile(file_path):
            if filename.endswith(('.txt', '.md', '.csv', '.json', '.py')):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        context_text += f"\n\n--- Documento: {filename} ---\n{f.read()}"
                except Exception as e:
                    st.warning(f"No se pudo leer {filename}: {e}")
            elif filename.endswith('.pdf') and pypdf:
                try:
                    reader = pypdf.PdfReader(file_path)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    context_text += f"\n\n--- Documento PDF: {filename} ---\n{text}"
                except Exception as e:
                    st.warning(f"No se pudo leer PDF {filename}: {e}")
    return context_text

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

    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.0-flash")

    prompt = f"""
    Actúa como un generador de exámenes experto y dinámico.
    Tu objetivo es crear un test de evaluación de 5 preguntas adaptado a los contenidos proporcionados.
    
    BASE DE CONOCIMIENTO (CONTENIDO FUENTE):
    {knowledge_context if knowledge_context.strip() else "No hay documentos cargados. Usa conocimiento general."}
    
    CONFIGURACIÓN DEL EXAMEN:
    - Tema sugerido: '{topic}'
    - Dificultad: {difficulty}
    - Rol del usuario: {role}
    
    REGLAS DE GENERACIÓN:
    1. PRIORIDAD DE CONTENIDO: Si hay texto en la Base de Conocimiento, las preguntas deben basarse EXCLUSIVAMENTE en esa información. Si el 'Tema sugerido' no está en el texto, ignóralo y pregunta sobre los conceptos clave del documento.
    2. DINAMISMO: Evita preguntas repetitivas. Varía entre definiciones, casos de uso y análisis según el contenido.
    3. FORMATO DE SALIDA: Responde ÚNICAMENTE con un JSON válido (lista de objetos).
    
    Ejemplo de estructura JSON requerida:
    [
        {{"question": "¿Qué es X?", "options": ["A", "B", "C"], "answer": "A"}}
    ]
    """
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        text_response = response.text
        return json.loads(text_response)
    except Exception as e:
        st.error(f"Error generando preguntas: {e}")
        return []

def evaluate_quiz(questions, user_answers):
    """Evalúa las respuestas y devuelve la puntuación."""
    score = 0
    results = []
    
    for i, q in enumerate(questions):
        correct = q["answer"]
        user_ans = user_answers.get(i)
        is_correct = user_ans == correct
        
        if is_correct:
            score += 10 # 10 puntos por respuesta correcta
            
        results.append({
            "question": q["question"],
            "user_answer": user_ans,
            "correct_answer": correct,
            "is_correct": is_correct
        })
        
    return score, results

def get_chat_response(history, user_input, system_instruction, knowledge_context=""):
    """Obtiene respuesta del chat de Gemini."""
    client = init_gemini()
    if not client:
        return "Modo demostración: Configura tu API Key para chatear con Gemini real."
    
    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.0-flash")
    
    full_prompt = f"Instrucción del sistema: {system_instruction}\n\nInformación de Contexto (Base de Conocimiento):\n{knowledge_context}\n\nUsuario: {user_input}"
    # Construir historial estructurado para Gemini
    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["content"])]
            )
        )
    
    full_system_instruction = f"{system_instruction}\n\nInformación de Contexto (Base de Conocimiento):\n{knowledge_context}"
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=full_system_instruction
            )
        )
        return response.text
    except Exception as e:
        return f"⚠️ **Error de conexión con la IA:** {e}.\n\nPor favor, verifica que tu API Key en `.streamlit/secrets.toml` sea correcta y válida."

def generate_dynamic_roles(knowledge_context):
    """Genera roles/niveles jerárquicos basados en el contenido."""
    client = init_gemini()
    # Roles por defecto si falla la IA o no hay contenido
    default_roles = ["Principiante", "Intermedio", "Avanzado", "Experto"]
    
    if not client or not knowledge_context.strip():
        return default_roles

    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.0-flash")
    
    prompt = f"""
    Analiza el siguiente contenido educativo y define 4 niveles o roles jerárquicos adecuados para un estudiante de este material.
    Los roles deben ser temáticos y específicos al contenido proporcionado.
    Deben ir de menor a mayor experiencia.
    
    CONTENIDO (Muestra):
    {knowledge_context[:50000]} 
    
    Responde ÚNICAMENTE con un JSON válido que sea una lista de 4 strings.
    Ejemplo: ["Aprendiz de Cocina", "Cocinero de Línea", "Sous Chef", "Chef Ejecutivo"]
    """
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        roles = json.loads(response.text)
        if isinstance(roles, list) and len(roles) > 0:
            return roles
        return default_roles
    except Exception as e:
        print(f"Error generando roles dinámicos: {e}")
        return default_roles

def generate_dynamic_topics(knowledge_context):
    """Genera temas de examen basados en el contenido."""
    client = init_gemini()
    default_topics = ["Conocimiento General"]
    
    if not client or not knowledge_context.strip():
        return default_topics

    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.0-flash")
    
    prompt = f"""
    Analiza el siguiente contenido educativo y extrae una lista de 5 a 8 temas principales sobre los que se podría evaluar al usuario.
    Los temas deben ser breves, descriptivos y cubrir diferentes aspectos del contenido.
    
    CONTENIDO (Muestra):
    {knowledge_context[:50000]} 
    
    Responde ÚNICAMENTE con un JSON válido que sea una lista de strings.
    Ejemplo: ["Historia", "Conceptos Básicos", "Metodología", "Casos de Uso"]
    """
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        topics = json.loads(response.text)
        if isinstance(topics, list) and len(topics) > 0:
            return topics
        return default_topics
    except Exception as e:
        print(f"Error generando temas dinámicos: {e}")
        return default_topics

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
        Me = sum_me / n_active
    else:
        Me = 1.0
        
    # Valor Total
    total_value = (AH_op * Me) * cost_per_hour
    
    return {
        "N": N,
        "P": P,
        "F": avg_freq,
        "AH_op": AH_op,
        "Me": Me,
        "Total_Value": total_value,
        "active_count": n_active
    }