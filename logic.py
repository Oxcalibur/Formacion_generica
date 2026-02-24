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
try:
    import plotly.graph_objects as go
except ImportError:
    go = None
from typing import List, Dict, Any
import datetime

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
                    print(f"Advertencia: No se pudo leer {filename}: {e}")
            elif filename.endswith('.pdf') and pypdf:
                try:
                    reader = pypdf.PdfReader(file_path)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    context_text += f"\n\n--- Documento PDF: {filename} ---\n{text}"
                except Exception as e:
                    print(f"Advertencia: No se pudo leer PDF {filename}: {e}")
    return context_text

def generate_quiz_questions(topic, difficulty, role, knowledge_context=""):
    """Genera 5 preguntas usando Gemini en formato JSON."""
    from config import CLIENT_CONFIG
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
    from config import CLIENT_CONFIG
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
    from config import CLIENT_CONFIG
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
    from config import CLIENT_CONFIG
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

def log_user_prompt(prompt_text: str, worksheet_name: str, role: str = "User"):
    """
    Registra el prompt de un usuario en una hoja de cálculo de Google Sheets.
    
    Args:
        prompt_text (str): El texto del prompt introducido por el usuario.
        worksheet_name (str): El nombre de la hoja de cálculo donde se guardará el prompt.
        role (str): El rol del usuario que realiza la consulta.
    """
    if GSheetsConnection is None:
        print("GSheetsConnection no disponible. Saltando registro de prompt.")
        return

    if not prompt_text or not worksheet_name:
        return

    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        new_prompt_df = pd.DataFrame([
            {"timestamp": datetime.datetime.now(), "role": role, "prompt": prompt_text}
        ])

        try:
            existing_df = conn.read(worksheet=worksheet_name, ttl=0)
            if existing_df.empty or ("Unnamed: 0" in existing_df.columns and len(existing_df.columns) == 1):
                existing_df = pd.DataFrame(columns=["timestamp", "role", "prompt"])
        except Exception:  # La hoja probablemente no existe
            existing_df = pd.DataFrame(columns=["timestamp", "role", "prompt"])

        updated_df = pd.concat([existing_df, new_prompt_df], ignore_index=True)
        conn.update(worksheet=worksheet_name, data=updated_df)

    except Exception as e:
        # Fallo silencioso para no impactar la experiencia de usuario
        print(f"Error al registrar prompt en Google Sheets: {e}")

def get_logged_prompts(worksheet_name: str):
    """Recupera los prompts registrados desde Google Sheets."""
    if GSheetsConnection is None:
        return pd.DataFrame()

    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet=worksheet_name, ttl=0)
        return df
    except Exception as e:
        print(f"Error leyendo prompts: {e}")
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
        nivel_promedio_inicial: int,
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
            multiplicador_evolucion = 1 + (self.nivel_promedio_inicial / 10.0) * factor_aprendizaje

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
    from config import CLIENT_CONFIG
    client = init_gemini()
    if not client or not prompts_list:
        return []

    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.0-flash")
    
    # Tomamos una muestra representativa si son muchos para no saturar el contexto
    sample_prompts = prompts_list[:150] if len(prompts_list) > 150 else prompts_list
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
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
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
    
    # Nodo Raíz
    root_id = "ROOT"
    ids.append(root_id)
    labels.append("Temáticas")
    parents.append("")
    values.append(0) # Se calculará automáticamente o se ignora en visualización
    hover_text.append("Total")

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
            
        # 2. Nivel TEMÁTICA (Única por Rol)
        topic_id = f"TOPIC_{rol}_{tematica}"
        if topic_id not in topics_added:
            ids.append(topic_id)
            labels.append(tematica)
            parents.append(role_id)
            values.append(0)
            hover_text.append(f"Temática: {tematica}")
            topics_added.add(topic_id)

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

    fig = go.Figure(go.Treemap(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        textinfo="label",
        hovertext=hover_text,
        hoverinfo="text",
        marker=dict(colorscale='Teal')
    ))
    
    fig.update_layout(
        title="<b>Mapa de Inquietudes (Jerarquía: Rol > Temática > Inquietud)</b>",
        margin=dict(t=50, l=0, r=0, b=0)
    )
    return fig