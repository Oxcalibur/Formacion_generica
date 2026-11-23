import streamlit as st

# Diccionario de traducciones. La clave es el código de idioma (ISO 639-1)
TRANSLATIONS = {
    "es": {
        # General
        "app_title": "Asesor Inmobiliario Integral",
        "sidebar_title": "Navegación",
        "nav_assistant": "Asesor Inmobiliario Integral",
        "nav_dojo": "Dojo Inmobiliario (Ponerse a prueba)",
        "nav_roi": "ROI Dashboard (Admin)",
        "nav_users": "Gestión de Usuarios (Admin)",
        "nav_prompts": "Registro de Prompts (Admin)",
        "language_selector_label": "Idioma",

        # Login
        "login_title": "⚖️ Acceso al Asesor Inmobiliario Integral",
        "login_user": "Usuario",
        "login_password": "Contraseña",
        "login_button": "Entrar",
        "login_error": "Credenciales incorrectas",

        # Sidebar
        "sidebar_role_expander": "👤 Mi Perfil",
        "sidebar_role_input": "Perfil (ej. Persona física, Sociedad/SL, Inversor)",
        "sidebar_role_button": "Guardar Perfil",
        "sidebar_password_expander": "🔐 Cambiar Contraseña",
        "sidebar_password_new": "Nueva contraseña",
        "sidebar_password_confirm": "Confirmar",
        "sidebar_password_update_button": "Actualizar",
        "sidebar_password_mismatch": "Las contraseñas no coinciden.",
        "sidebar_logout_button": "Cerrar Sesión",
        "sidebar_kb_connected": "📚 Base documental conectada",
        "sidebar_kb_empty": "⚠️ Base documental vacía",
        "sidebar_level_title": "🥋 Nivel Actual",
        "sidebar_points": "Puntos",
        "sidebar_sessions": "Sesiones",
        "sidebar_next_level": "Próximo",
        "sidebar_max_level": "¡Máximo nivel alcanzado!",

        # Asistente
        "assistant_welcome": "⚖️ Asesor Inmobiliario Integral — {user_role}",
        "assistant_caption": "Asesoramiento legal (LAU, Ley 12/2023, RDL 29/2026), fiscal (IRPF, ITP), financiación (LCCI, CIRBE) y estrategia de inversión en España.",
        "assistant_input_placeholder": "Pregunta sobre alquileres, contratos, impuestos (IRPF/ITP), hipotecas o estrategia de inversión...",
        "assistant_thinking": "Consultando normativa legal, fiscal, financiación y estrategia...",
        "assistant_welcome_msg": "Hola, soy tu **{client_name}**. Puedo ayudarte —tanto si actúas como persona física como si eres una empresa o entidad— con derecho de alquileres, fiscalidad (IRPF/ITP), hipotecas y financiación, o estrategia de inversión inmobiliaria en España. ¿En qué situación o decisión te ayudo hoy?",
        "doc_uploader_title": "📎 Adjuntar contrato o documento (solo para esta conversación)",
        "doc_privacy_note": "🔒 Privacidad: el documento se lee únicamente en memoria para esta consulta y NO se guarda ni se conserva para futuras conversaciones.",
        "doc_uploader_label": "Sube tu contrato, anexo, burofax o foto (PDF, Word, TXT o imagen)",
        "doc_loaded_msg": "📄 Documento activo solo en esta sesión: **{name}** ({summary})",
        "doc_remove_button": "🗑️ Quitar",
        "doc_new_chat_button": "🔄 Nueva consulta",
        "export_chat_button": "📋 Descargar chat",
        "doc_download_pdf_button": "📄 Descargar '{title}' en PDF",
        "response_download_pdf_button": "📥 Descargar respuesta en PDF",

        # Dojo
        "dojo_header": "🥋 Dojo Legal Inmobiliario",
        "dojo_caption": "Pon a prueba tus conocimientos sobre la normativa de alquiler en España.  \n**Perfil:** {user_role}",
        "dojo_topic_label": "Tema del examen",
        "dojo_difficulty_label": "Dificultad",
        "dojo_difficulty_levels": ["Fácil", "Medio", "Difícil"],
        "dojo_start_button": "Comenzar Desafío",
        "dojo_spinner_preparing": "Preparando tus preguntas sobre normativa inmobiliaria...",
        "dojo_question_header": "Pregunta {i}",
        "dojo_radio_label": "Selecciona una opción:",
        "dojo_submit_button": "Entregar Examen",
        "dojo_warning_all_questions": "Por favor responde todas las preguntas antes de entregar.",
        "dojo_success": "¡Examen completado! Has ganado {points} puntos.",
        "dojo_results_expander": "Ver detalles",
        "dojo_your_answer": "Tu respuesta:",
        "dojo_correct_answer": "Correcta:",
        "dojo_back_button": "Volver al Dojo",
        "dojo_general_knowledge": "Normativa de Arrendamientos Urbanos",
        "dojo_spinner_topics": "Identificando temas clave de la base documental...",
    },
    "en": {
        # General
        "app_title": "Comprehensive Real Estate Advisor",
        "sidebar_title": "Navigation",
        "nav_assistant": "Real Estate Advisor",
        "nav_dojo": "Real Estate Dojo (Test yourself)",
        "nav_roi": "ROI Dashboard (Admin)",
        "nav_users": "User Management (Admin)",
        "nav_prompts": "Prompt Log (Admin)",
        "language_selector_label": "Language",

        # Login
        "login_title": "⚖️ Real Estate Advisor Access",
        "login_user": "Username",
        "login_password": "Password",
        "login_button": "Login",
        "login_error": "Incorrect credentials",

        # Sidebar
        "sidebar_role_expander": "👤 My Profile",
        "sidebar_role_input": "Profile (e.g. Individual, Company/SL, Investor)",
        "sidebar_role_button": "Save Profile",
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

        # Assistant, Dojo, etc.
        "assistant_welcome": "⚖️ Comprehensive Real Estate Advisor — {user_role}",
        "assistant_caption": "Spanish real estate guidance: tenancy law (LAU, RDL 29/2026), taxation (IRPF, ITP), mortgages (LCCI, CIRBE) & investment strategy.",
        "assistant_input_placeholder": "Ask about leases, taxes (IRPF/ITP), mortgages, financing or real estate investment strategy...",
        "assistant_thinking": "Consulting legal, tax, financing and investment knowledge base...",
        "assistant_welcome_msg": "Hello, I'm your **{client_name}**. Whether you act as an individual or a company/entity, I can help you with Spanish tenancy law, real estate taxation (IRPF/ITP), mortgages & financing, and investment strategy. How can I help you today?",
        "doc_uploader_title": "📎 Attach contract or document (this conversation only)",
        "doc_privacy_note": "🔒 Privacy: your document is read strictly in memory for this chat and is NOT saved or kept for future conversations.",
        "doc_uploader_label": "Upload your lease, addendum, notice or photo (PDF, Word, TXT or image)",
        "doc_loaded_msg": "📄 Active for this session only: **{name}** ({summary})",
        "doc_remove_button": "🗑️ Remove",
        "doc_new_chat_button": "🔄 New chat",
        "export_chat_button": "📋 Export chat",
        "doc_download_pdf_button": "📄 Download '{title}' as PDF",
        "response_download_pdf_button": "📥 Download response as PDF",

        "dojo_header": "🥋 Real Estate Legal Dojo",
        "dojo_caption": "Test your knowledge of Spanish rental regulations.  \n**Profile:** {user_role}",
        "dojo_topic_label": "Exam Topic",
        "dojo_difficulty_label": "Difficulty",
        "dojo_difficulty_levels": ["Easy", "Medium", "Hard"],
        "dojo_start_button": "Start Challenge",
        "dojo_spinner_preparing": "Preparing your Spanish tenancy law questions...",
        "dojo_question_header": "Question {i}",
        "dojo_radio_label": "Select an option:",
        "dojo_submit_button": "Submit Exam",
        "dojo_warning_all_questions": "Please answer all questions before submitting.",
        "dojo_success": "Exam completed! You've earned {points} points.",
        "dojo_results_expander": "View details",
        "dojo_your_answer": "Your answer:",
        "dojo_correct_answer": "Correct:",
        "dojo_back_button": "Back to the Dojo",
        "dojo_general_knowledge": "Spanish Urban Tenancy Law",
        "dojo_spinner_topics": "Identifying key legal topics from the knowledge base...",
    }
}

def get_text(key):
    """Obtiene el texto traducido para una clave dada, usando el idioma de la sesión."""
    lang = st.session_state.get("language", "es")
    # Devolver la clave como fallback si no se encuentra la traducción
    return TRANSLATIONS.get(lang, {}).get(key, key)