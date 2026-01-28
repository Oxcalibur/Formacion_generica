import streamlit as st
import os
from config import CLIENT_CONFIG, SECURITY_CONFIG, apply_custom_styles
from logic import get_current_belt, generate_quiz_questions, evaluate_quiz, get_chat_response, load_knowledge_base, generate_dynamic_roles, generate_dynamic_topics, check_credentials, load_user_progress, save_user_progress

# --- Configuración de Página ---
st.set_page_config(page_title=CLIENT_CONFIG["client_name"], page_icon="🎓")
apply_custom_styles()

# --- Inicialización de Estado ---
if "user_role" not in st.session_state:
    st.session_state.user_role = "Estudiante"
if "score" not in st.session_state:
    st.session_state.score = 0
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "quiz_active" not in st.session_state:
    st.session_state.quiz_active = False
if "current_questions" not in st.session_state:
    st.session_state.current_questions = []
if "knowledge_base" not in st.session_state or not st.session_state.knowledge_base:
    # Cargar documentos al inicio de la sesión
    kb_path = CLIENT_CONFIG.get("knowledge_base_folder", "knowledge_base")
    # Asegurar ruta absoluta para evitar errores de contexto tras el login
    if not os.path.isabs(kb_path):
        kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), kb_path)
    st.session_state.knowledge_base = load_knowledge_base(kb_path)
if "dynamic_roles" not in st.session_state:
    st.session_state.dynamic_roles = []
if "dynamic_topics" not in st.session_state:
    st.session_state.dynamic_topics = []

# --- Control de Acceso (Login) ---
if SECURITY_CONFIG.get("enable_auth", False):
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        
    if not st.session_state.logged_in:
        st.title("🔐 Acceso a Formación")
        with st.form("login_form"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar"):
                if check_credentials(u, p):
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.session_state.score = load_user_progress(u) # Cargar nivel guardado
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas")
        st.stop() # Detiene la ejecución si no está logueado

# --- Sidebar: Perfil y Navegación ---
with st.sidebar:
    if os.path.exists(CLIENT_CONFIG.get("logo_path", "")):
        st.image(CLIENT_CONFIG["logo_path"], width=100)
    else:
        st.warning("⚠️ Logo no encontrado en images/logo.png")
    st.title(CLIENT_CONFIG["client_name"])
    
    if st.session_state.get("logged_in"):
        st.caption(f"Usuario: {st.session_state.username}")
        if st.button("Cerrar Sesión"):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()
            
    # Indicador de estado de la Base de Conocimiento
    if st.session_state.knowledge_base:
        st.success(f"📚 Base de conocimiento conectada")
    else:
        st.warning("⚠️ Base de conocimiento vacía")
    
    # Generar roles dinámicos si no existen
    if not st.session_state.dynamic_roles:
        if st.session_state.knowledge_base:
            with st.spinner("Analizando contenido para definir niveles..."):
                st.session_state.dynamic_roles = generate_dynamic_roles(st.session_state.knowledge_base)
        else:
            st.session_state.dynamic_roles = ["Principiante", "Intermedio", "Avanzado", "Experto"]

    # Selector de Rol
    st.session_state.user_role = st.selectbox(
        "Tu Nivel / Rol", 
        st.session_state.dynamic_roles
    )
    
    st.divider()
    
    # Estado del Cinturón
    belt = get_current_belt(st.session_state.score)
    st.markdown(f"### 🥋 Nivel Actual")
    st.markdown(f"**{belt['name']}**")
    st.progress(min(1.0, st.session_state.score / (belt['threshold'] + 200))) # Barra de progreso visual
    st.caption(f"Puntos: {st.session_state.score}")
    
    st.divider()
    mode = st.radio("Navegación", ["Asistente Formativo", "Dojo (Ponerse a prueba)"])

# --- Pantalla 1: Asistente Formativo (Chat) ---
if mode == "Asistente Formativo":
    st.header(f"Bienvenido, {st.session_state.user_role}")
    st.caption("Pregunta cualquier duda sobre tus materiales de formación.")

    # Mostrar historial
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input de usuario
    if prompt := st.chat_input("¿En qué puedo ayudarte hoy?"):
        # Guardar y mostrar mensaje usuario
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generar respuesta
        with st.chat_message("assistant"):
            with st.spinner("Consultando base de conocimiento..."):
                system_prompt = CLIENT_CONFIG["system_prompt"].format(client_name=CLIENT_CONFIG["client_name"])
                response = get_chat_response(st.session_state.chat_history, prompt, system_prompt, st.session_state.knowledge_base)
                st.markdown(response)
        
        st.session_state.chat_history.append({"role": "assistant", "content": response})

# --- Pantalla 2: Dojo (Quiz) ---
elif mode == "Dojo (Ponerse a prueba)":
    st.header("🥋 El Dojo")
    st.write("Demuestra tu conocimiento para subir de cinturón.")

    if not st.session_state.quiz_active:
        # Generar temas dinámicos si no existen
        if not st.session_state.dynamic_topics:
            if st.session_state.knowledge_base:
                with st.spinner("Identificando temas clave para el examen..."):
                    st.session_state.dynamic_topics = generate_dynamic_topics(st.session_state.knowledge_base)
            else:
                st.session_state.dynamic_topics = ["Conocimiento General"]

        col1, col2 = st.columns(2)
        with col1:
            topic = st.selectbox("Tema del examen", st.session_state.dynamic_topics)
        with col2:
            difficulty = st.select_slider("Dificultad", options=["Fácil", "Medio", "Difícil"])
            
        if st.button("Comenzar Desafío"):
            with st.spinner("El Sensei (IA) está preparando tus preguntas..."):
                questions = generate_quiz_questions(topic, difficulty, st.session_state.user_role, st.session_state.knowledge_base)
                if questions:
                    st.session_state.current_questions = questions
                    st.session_state.quiz_active = True
                    st.rerun()
    
    else:
        # Mostrar Formulario de Quiz
        with st.form("quiz_form"):
            user_answers = {}
            for i, q in enumerate(st.session_state.current_questions):
                st.subheader(f"Pregunta {i+1}")
                st.write(q["question"])
                user_answers[i] = st.radio(
                    "Selecciona una opción:", 
                    q["options"], 
                    key=f"q_{i}",
                    index=None
                )
                st.divider()
            
            submitted = st.form_submit_button("Entregar Examen")
            
        if submitted:
            # Validar que todo esté respondido
            if any(a is None for a in user_answers.values()):
                st.warning("Por favor responde todas las preguntas antes de entregar.")
            else:
                points, results = evaluate_quiz(st.session_state.current_questions, user_answers)
                st.session_state.score += points
                # Guardar progreso automáticamente
                if st.session_state.get("username"):
                    save_user_progress(st.session_state.username, st.session_state.score)
                st.session_state.quiz_active = False
                st.session_state.current_questions = [] # Limpiar
                
                # Mostrar resultados
                st.success(f"¡Examen completado! Has ganado {points} puntos.")
                with st.expander("Ver detalles"):
                    for res in results:
                        color = "green" if res["is_correct"] else "red"
                        st.markdown(f":{color}[{res['question']}]")
                        st.write(f"Tu respuesta: {res['user_answer']}")
                        if not res["is_correct"]:
                            st.write(f"Correcta: {res['correct_answer']}")
                
                if st.button("Volver al Dojo"):
                    st.rerun()
