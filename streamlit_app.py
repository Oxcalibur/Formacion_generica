import streamlit as st
import os
from config import CLIENT_CONFIG, SECURITY_CONFIG, apply_custom_styles
from logic import get_current_belt, get_next_belt_data, generate_quiz_questions, evaluate_quiz, get_chat_response, load_knowledge_base, generate_dynamic_roles, generate_dynamic_topics, check_credentials, load_user_progress, save_user_progress, calculate_roi_metrics

# --- Configuración de Página ---
st.set_page_config(page_title=CLIENT_CONFIG["client_name"], page_icon="🎓")
apply_custom_styles()

# --- Inicialización de Estado ---
if "user_role" not in st.session_state:
    st.session_state.user_role = "Estudiante"
if "score" not in st.session_state:
    st.session_state.score = 0
if "active_sessions" not in st.session_state:
    st.session_state.active_sessions = 0
if "session_interaction_recorded" not in st.session_state:
    st.session_state.session_interaction_recorded = False
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
                    user_data = load_user_progress(u) # Cargar datos guardados
                    st.session_state.score = user_data["score"]
                    st.session_state.active_sessions = user_data["active_sessions"]
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
            # Limpiar variables de sesión para asegurar que el próximo usuario cargue datos limpios
            keys_to_reset = ["logged_in", "username", "score", "active_sessions", "chat_history", 
                             "quiz_active", "current_questions", "session_interaction_recorded", "user_role"]
            for key in keys_to_reset:
                if key in st.session_state:
                    del st.session_state[key]
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
    progress_data = get_next_belt_data(st.session_state.score)
    
    st.markdown(f"### 🥋 Nivel Actual")
    st.markdown(f"**{belt['name']}**")
    st.progress(min(1.0, st.session_state.score / (belt['threshold'] + 200))) # Barra de progreso visual
    st.caption(f"Puntos: {st.session_state.score} | Sesiones: {st.session_state.active_sessions}")
    st.progress(min(1.0, max(0.0, progress_data["progress"]))) # Barra de progreso visual
    
    if progress_data["progress"] < 1.0:
        st.caption(f"Próximo: {progress_data['next_name']} ({st.session_state.score}/{progress_data['threshold']} pts)")
    else:
        st.caption(f"¡Máximo nivel alcanzado! ({st.session_state.score} pts)")
    
    st.divider()
    
    nav_options = ["Asistente Formativo", "Dojo (Ponerse a prueba)"]
    if st.session_state.get("username") == "admin":
        nav_options.append("ROI Dashboard (Admin)")
    mode = st.radio("Navegación", nav_options)

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
        # Registrar interacción si es la primera de la sesión
        if st.session_state.get("logged_in") and not st.session_state.session_interaction_recorded:
            save_user_progress(st.session_state.username, increment_session=True)
            st.session_state.active_sessions += 1
            st.session_state.session_interaction_recorded = True

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
                    increment = not st.session_state.session_interaction_recorded
                    save_user_progress(st.session_state.username, score=st.session_state.score, increment_session=increment)
                    if increment:
                        st.session_state.active_sessions += 1
                        st.session_state.session_interaction_recorded = True
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

# --- Pantalla 3: ROI Dashboard (Admin) ---
elif mode == "ROI Dashboard (Admin)":
    st.header("💰 Calculadora de ROI - Olivia España")
    st.markdown("Análisis de impacto económico basado en adopción y evolución de conocimiento.")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        ts = st.number_input("Tiempo ahorrado por interacción (h)", value=0.25, step=0.05, format="%.2f")
    with col2:
        ch = st.number_input("Coste hora promedio (€)", value=50.0, step=5.0, format="%.2f")
    with col3:
        threshold = st.number_input("Mín. sesiones para ROI", value=10, min_value=1, step=1)
        
    metrics = calculate_roi_metrics(ts, ch, threshold)
    
    if metrics:
        st.divider()
        
        # 1. Ahorro Operativo
        st.subheader("1. Ahorro Operativo ($AH_{op}$)")
        st.latex(r"AH_{op} = (N \cdot P) \cdot (F \cdot T_s)")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Usuarios (N)", metrics["N"])
        c2.metric("Tasa Part. (P)", f"{metrics['P']:.1%}", help=f"{metrics['active_count']} usuarios con >= {threshold} usos")
        c3.metric("Frecuencia (F)", f"{metrics['F']:.1f}", help="Media de sesiones de usuarios activos")
        c4.metric("Ahorro Base", f"{metrics['AH_op']:.1f} h")
        
        # 2. Multiplicador
        st.subheader("2. Multiplicador de Evolución ($M_e$)")
        st.latex(r"M_e = 1 + \left( \frac{\text{Nivel Actual} - 1}{\text{Nivel Máximo}} \right)")
        st.metric("Multiplicador Promedio", f"x{metrics['Me']:.2f}", help="Basado en el nivel de cinturón de los usuarios activos")
        
        # 3. Total
        st.subheader("3. Valor Total Generado")
        st.latex(r"\text{Valor} = (AH_{op} \cdot M_e) \cdot C_h")
        
        final_val = metrics["Total_Value"]
        st.metric("Ahorro Económico Total", f"{final_val:,.2f} €", delta="ROI Estimado")
    else:
        st.warning("No hay datos de usuarios suficientes para calcular el ROI.")
