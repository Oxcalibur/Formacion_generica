import streamlit as st

# Diccionario de traducciones. La clave es el código de idioma (ISO 639-1)
TRANSLATIONS = {
    "es": {
        # General
        "app_title": "Asistente de Formación",
        "sidebar_title": "Navegación",
        "nav_assistant": "Asistente Formativo",
        "nav_dojo": "Dojo (Ponerse a prueba)",
        "nav_roi": "ROI Dashboard (Admin)",
        "nav_users": "Gestión de Usuarios (Admin)",
        "nav_prompts": "Registro de Prompts (Admin)",
        "language_selector_label": "Idioma",

        # Login
        "login_title": "🔐 Acceso a Formación",
        "login_user": "Usuario",
        "login_password": "Contraseña",
        "login_button": "Entrar",
        "login_error": "Credenciales incorrectas",

        # Sidebar
        "sidebar_role_expander": "👤 Mi Puesto / Rol",
        "sidebar_role_input": "Cargo en la empresa",
        "sidebar_role_button": "Guardar Cargo",
        "sidebar_password_expander": "🔐 Cambiar Contraseña",
        "sidebar_password_new": "Nueva contraseña",
        "sidebar_password_confirm": "Confirmar",
        "sidebar_password_update_button": "Actualizar",
        "sidebar_password_mismatch": "Las contraseñas no coinciden.",
        "sidebar_logout_button": "Cerrar Sesión",
        "sidebar_kb_connected": "📚 Base de conocimiento conectada",
        "sidebar_kb_empty": "⚠️ Base de conocimiento vacía",
        "sidebar_level_title": "🥋 Nivel Actual",
        "sidebar_points": "Puntos",
        "sidebar_sessions": "Sesiones",
        "sidebar_next_level": "Próximo",
        "sidebar_max_level": "¡Máximo nivel alcanzado!",

        # Asistente
        "assistant_welcome": "Bienvenido, {user_role}",
        "assistant_caption": "Pregunta cualquier duda sobre tus materiales de formación.",
        "assistant_input_placeholder": "¿En qué puedo ayudarte hoy?",
        "assistant_thinking": "Consultando base de conocimiento...",
        "assistant_welcome_msg": "Hola, soy {client_name}. Entiendo que tu rol es **{user_role}**. ¿Cuál es tu reto para hoy?",

        # Dojo
        "dojo_header": "🥋 El Dojo",
        "dojo_caption": "Demuestra tu conocimiento para subir de cinturón.  \n**Perfil de evaluación:** {user_role}",
        "dojo_topic_label": "Tema del examen",
        "dojo_difficulty_label": "Dificultad",
        "dojo_difficulty_levels": ["Fácil", "Medio", "Difícil"],
        "dojo_start_button": "Comenzar Desafío",
        "dojo_spinner_preparing": "El Sensei (IA) está preparando tus preguntas...",
        "dojo_question_header": "Pregunta {i}",
        "dojo_radio_label": "Selecciona una opción:",
        "dojo_submit_button": "Entregar Examen",
        "dojo_warning_all_questions": "Por favor responde todas las preguntas antes de entregar.",
        "dojo_success": "¡Examen completado! Has ganado {points} puntos.",
        "dojo_results_expander": "Ver detalles",
        "dojo_your_answer": "Tu respuesta:",
        "dojo_correct_answer": "Correcta:",
        "dojo_back_button": "Volver al Dojo",
        "dojo_general_knowledge": "Conocimiento General",
        "dojo_spinner_topics": "Identificando temas clave para el examen...",
    },
    "en": {
        # General
        "app_title": "Training Assistant",
        "sidebar_title": "Navigation",
        "nav_assistant": "Training Assistant",
        "nav_dojo": "Dojo (Test yourself)",
        "nav_roi": "ROI Dashboard (Admin)",
        "nav_users": "User Management (Admin)",
        "nav_prompts": "Prompt Log (Admin)",
        "language_selector_label": "Language",

        # Login
        "login_title": "🔐 Training Access",
        "login_user": "Username",
        "login_password": "Password",
        "login_button": "Login",
        "login_error": "Incorrect credentials",

        # Sidebar
        "sidebar_role_expander": "👤 My Position / Role",
        "sidebar_role_input": "Role in the company",
        "sidebar_role_button": "Save Role",
        "sidebar_password_expander": "🔐 Change Password",
        "sidebar_password_new": "New password",
        "sidebar_password_confirm": "Confirm",
        "sidebar_password_update_button": "Update",
        "sidebar_password_mismatch": "Passwords do not match.",
        "sidebar_logout_button": "Logout",
        "sidebar_kb_connected": "📚 Knowledge base connected",
        "sidebar_kb_empty": "⚠️ Knowledge base empty",
        "sidebar_level_title": "🥋 Current Level",
        "sidebar_points": "Points",
        "sidebar_sessions": "Sessions",
        "sidebar_next_level": "Next",
        "sidebar_max_level": "Maximum level reached!",

        # Assistant, Dojo, etc. (se pueden añadir el resto de traducciones aquí)
        "assistant_welcome": "Welcome, {user_role}",
        "assistant_caption": "Ask any questions about your training materials.",
        "assistant_input_placeholder": "How can I help you today?",
        "assistant_thinking": "Consulting knowledge base...",
        "assistant_welcome_msg": "Hi, I'm {client_name}. I see your role is **{user_role}**. What is your challenge for today?",

        "dojo_header": "🥋 The Dojo",
        "dojo_caption": "Show your knowledge to level up your belt.  \n**Evaluation profile:** {user_role}",
        "dojo_topic_label": "Exam Topic",
        "dojo_difficulty_label": "Difficulty",
        "dojo_difficulty_levels": ["Easy", "Medium", "Hard"],
        "dojo_start_button": "Start Challenge",
        "dojo_spinner_preparing": "The Sensei (AI) is preparing your questions...",
        "dojo_question_header": "Question {i}",
        "dojo_radio_label": "Select an option:",
        "dojo_submit_button": "Submit Exam",
        "dojo_warning_all_questions": "Please answer all questions before submitting.",
        "dojo_success": "Exam completed! You've earned {points} points.",
        "dojo_results_expander": "View details",
        "dojo_your_answer": "Your answer:",
        "dojo_correct_answer": "Correct:",
        "dojo_back_button": "Back to the Dojo",
        "dojo_general_knowledge": "General Knowledge",
        "dojo_spinner_topics": "Identifying key topics for the exam...",
    }
}

def get_text(key):
    """Obtiene el texto traducido para una clave dada, usando el idioma de la sesión."""
    lang = st.session_state.get("language", "es")
    # Devolver la clave como fallback si no se encuentra la traducción
    return TRANSLATIONS.get(lang, {}).get(key, key)