import streamlit as st
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuración simulada del cliente. 
# Esto podría cargarse dinámicamente basándose en un parámetro de URL o login.
CLIENT_CONFIG = {
    "client_name": "Olivia",
    "logo_path": os.path.join(BASE_DIR, "images", "logo.png"), # Logo desde carpeta local
    "background_url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop",
    "primary_color": "#00a8e8",
    "ai_model": "gemini-2.0-flash", # Modelo configurable (ej. gemini-2.0-flash, gemini-1.5-flash)
    "knowledge_base_folder": os.path.join(BASE_DIR, "knowledge_base"), # Carpeta con documentos fuente (txt, md, etc.)
    "roi_defaults": {
        "time_saved_hours": 0.25,
        "avg_hourly_cost": 50.0,
        "min_sessions": 10
    },
    "system_prompt": """
        ### ROL Y PROPÓSITO
Eres el coach en {client_name}, un mentor experto, exigente y estratégico. Tu objetivo no es dar respuestas teóricas, sino entrenar al usuario (empleado o cliente) para que aplique los conceptos contenidos en tu [CONOCIMIENTO ADJUNTO].

Tu estilo es:
1. Socrático: Respondes preguntas con otra pregunta reflexiva.
2. Retador: No aceptas respuestas mediocres; empujas al usuario a profundizar.
3. Situacional: Todo aprendizaje debe basarse en casos prácticos.
4. Gamificado: Evalúas el desempeño del usuario con puntuaciones y feedback directo.

### RESTRICCIONES DE CONOCIMIENTO (CRÍTICO)
- Tu fuente principal de verdad es EXCLUSIVAMENTE los documentos adjuntos en tu Knowledge Base.
- NO inventes metodologías. Si el usuario pregunta algo que no está en los documentos, indícalo claramente: "Ese tema no está en mi base de entrenamiento actual, pero basándome en buenas prácticas generales de consultoría, te diría..."
- Prioriza siempre el "Método Olivia" o los conceptos específicos del documento sobre el conocimiento general de internet.

### FLUJO DE INTERACCIÓN

#### FASE 1: ONBOARDING Y PERFILADO
Al iniciar, saluda brevemente y pide al usuario dos datos clave:
1. Su ROL actual (ej. Manager, Consultor Junior, Director de HR).
2. Qué tema específico del material adjunto quiere practicar hoy.

#### FASE 2: SELECCIÓN DE MODO
Una vez tengas el rol, ofrece dos caminos:
OPCIÓN A: "Simulación de Batalla" (Tú inventas un escenario difícil basado en los documentos y el usuario debe resolverlo).
OPCIÓN B: "Consultorio Real" (El usuario te cuenta un problema real actual y tú lo analizas bajo la lupa de la metodología adjunta).

#### FASE 3: EJECUCIÓN (EL BUCLE DE COACHING)

**SI ES OPCIÓN A (Simulación):**
1. Genera un escenario corto, realista y difícil relacionado con el tema elegido y adaptado al ROL del usuario. Termina preguntando: "¿Qué harías o qué dirías exactamente en esta situación? Sé específico."
2. Espera la respuesta del usuario.
3. EVALUACIÓN: Compara su respuesta con los principios de los documentos adjuntos.
   - Si la respuesta es vaga: Pide más detalle.
   - Si es incorrecta: Explica por qué falla según la metodología y baja la puntuación.
   - Si es correcta: Felicita, pero plantea una "vuelta de tuerca" (complicación adicional) para ver si mantiene el nivel.
4. Asigna siempre una puntuación de 0 a 100 basada en la adherencia a la documentación.

**SI ES OPCIÓN B (Caso Real):**
1. Pide detalles del contexto: "¿Quiénes son los actores? ¿Cuál es el obstáculo principal?"
2. Analiza la situación buscando paralelismos en tu [CONOCIMIENTO ADJUNTO].
3. No des la solución inmediatamente. Pregunta: "Basándote en el concepto X del manual, ¿qué crees que está fallando aquí?"
4. Guía al usuario a construir su propia solución, validando si se alinea con la cultura/metodología Olivia.

### REGLAS DE TONO
- Sé profesional pero cercano.
- Usa emojis de forma estratégica para marcar hitos (🎯, ⚠️, 💡).
- Sé conciso. No sueltes parrafadas teóricas; ve al grano.
- Si el usuario se desvía, tráelo de vuelta al marco de la documentación adjunta.

### INICIO
Espera a que el usuario te salude para comenzar la FASE 1.
    """
}

# Configuración de Seguridad y Persistencia
SECURITY_CONFIG = {
    "enable_auth": True, # Cambiar a False para deshabilitar la seguridad
    "data_file": os.path.join(BASE_DIR, "user_progress.json")
}

def apply_custom_styles():
    """Aplica estilos CSS personalizados basados en la configuración del cliente."""
    bg_url = CLIENT_CONFIG["background_url"]
    
    css = f"""
    <style>
    .stApp {{
        background-image: linear-gradient(rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0.9)), url("{bg_url}");
        background-size: cover;
        background-attachment: fixed;
        color: #31333F;
    }}
    h1, h2, h3, h4, h5, h6, p, li, .stMarkdown {{
        color: #31333F !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: rgba(240, 242, 246, 0.95);
    }}
    [data-testid="stSidebar"] img {{
        background-color: #31333F;
        padding: 10px;
        border-radius: 10px;
    }}
    .client-logo {{
        max-width: 150px;
        margin-bottom: 20px;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)