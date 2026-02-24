import streamlit as st
import pandas as pd
import os
from config import CLIENT_CONFIG, SECURITY_CONFIG, apply_custom_styles
from logic import get_current_belt, get_next_belt_data, generate_quiz_questions, evaluate_quiz, get_chat_response, load_knowledge_base, generate_dynamic_roles, generate_dynamic_topics, calculate_roi_metrics, CalculadoraROI, graficar_break_even, graficar_evolucion_roi, graficar_impacto_aprendizaje
from auth import auth_manager

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
                if auth_manager.authenticate(u, p):
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    user_data = auth_manager.get_user_progress(u) # Cargar datos guardados
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
        
        with st.expander("🔐 Cambiar Contraseña"):
            with st.form("change_pass_form_sidebar"):
                new_pass = st.text_input("Nueva contraseña", type="password")
                confirm_pass = st.text_input("Confirmar", type="password")
                if st.form_submit_button("Actualizar"):
                    if new_pass and new_pass == confirm_pass:
                        success, msg = auth_manager.change_password(st.session_state.username, new_pass)
                        if success: st.success(msg)
                        else: st.error(msg)
                    else:
                        st.error("Las contraseñas no coinciden.")

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
        nav_options.append("Gestión de Usuarios (Admin)")
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
            auth_manager.update_user_progress(st.session_state.username, increment_session=True)
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
                    auth_manager.update_user_progress(st.session_state.username, score=st.session_state.score, increment_session=increment)
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
    
    show_graphs = st.toggle("📊 Ver Informe Completo", value=False)
    
    roi_conf = CLIENT_CONFIG.get("roi_defaults", {"time_saved_hours": 0.25, "avg_hourly_cost": 50.0, "min_sessions": 10})
    
    # Parámetros Operativos
    col1, col2, col3 = st.columns(3)
    with col1:
        ts = st.number_input("Tiempo ahorrado por interacción (h)", value=float(roi_conf["time_saved_hours"]), step=0.05, format="%.2f", key="roi_time_input")
    with col2:
        ch = st.number_input("Coste hora promedio (€)", value=float(roi_conf["avg_hourly_cost"]), step=5.0, format="%.2f", key="roi_cost_input")
    with col3:
        threshold = st.number_input("Mín. sesiones para ROI", value=int(roi_conf["min_sessions"]), min_value=1, step=1, key="roi_threshold_input")
    
    # Parámetros Financieros (Proyección)
    c_inv, c_time, c_freq = st.columns(3)
    with c_inv:
        investment = st.number_input("Inversión Inicial (€)", value=5000.0, step=500.0)
    with c_time:
        months = st.number_input("Horizonte (Meses)", value=12, min_value=1, max_value=60)
    with c_freq:
        proj_freq = st.number_input("Sesiones/Mes (Est.)", value=4.0, step=0.5, help="Frecuencia estimada de uso mensual por usuario activo")
        
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
        
        if show_graphs:
            # --- PROYECCIÓN FINANCIERA ---
            st.divider()
            st.header("🚀 Proyección Financiera (Motor de ROI)")
            st.caption("Simulación basada en la evolución del aprendizaje de los usuarios.")
            
            # Input adicional para el modelo de aprendizaje
            tasa_mejora = st.slider("Tasa de Mejora Mensual (%)", 0.0, 15.0, 5.0, 0.5, help="Incremento mensual de eficiencia por aprendizaje") / 100.0
            
            # Cálculo del nivel inicial basado en el multiplicador actual (Me)
            # Me va de 1.0 a 2.0 aprox. Mapeamos a nivel 1-10.
            nivel_inicial = int((metrics["Me"] - 1) * 10)
            if nivel_inicial < 1: nivel_inicial = 1
            
            # Instanciar Motor Lógico
            calculadora = CalculadoraROI(
                n_usuarios=metrics["N"],
                coste_hora=ch,
                inversion_inicial=investment,
                tiempo_ahorrado_mins=ts * 60,
                frecuencia_uso_mensual=proj_freq,
                tasa_adopcion_pct=metrics["P"],
                nivel_promedio_inicial=nivel_inicial,
                tasa_mejora_mensual=tasa_mejora
            )
            
            # Ejecutar Proyección
            datos_proyeccion = calculadora.proyectar_ahorro_temporal(int(months))
            df_proj = pd.DataFrame(datos_proyeccion)
            
            if not df_proj.empty:
                # 1. Gráfico de Break Even
                st.plotly_chart(graficar_break_even(df_proj), use_container_width=True)
                
                # KPI de Break Even
                if df_proj['break_even_alcanzado'].any():
                    mes_be = df_proj[df_proj['break_even_alcanzado']].iloc[0]['mes']
                    st.success(f"✅ **Punto de Equilibrio alcanzado en el mes {mes_be}**")
                else:
                    st.warning(f"⚠️ La inversión no se recupera en el horizonte de {months} meses.")

                # 2. Gráficos de Detalle (ROI e Impacto)
                c1, c2 = st.columns(2)
                with c1:
                    st.plotly_chart(graficar_evolucion_roi(df_proj), use_container_width=True)
                with c2:
                    st.plotly_chart(graficar_impacto_aprendizaje(df_proj), use_container_width=True)
                
                # Resumen Final
                total_saved = df_proj.iloc[-1]["ahorro_acumulado"]
                roi_final = df_proj.iloc[-1]["roi_perc"]
                st.metric("Ahorro Acumulado Final", f"{total_saved:,.2f} €", f"ROI Final {roi_final:.1f}%")

    else:
        st.warning("No hay datos de usuarios suficientes para calcular el ROI.")

# --- Pantalla 4: Gestión de Usuarios (Admin) ---
elif mode == "Gestión de Usuarios (Admin)":
    tab_crear, tab_reset = st.tabs(["Crear Nuevo Usuario", "Resetear Contraseña"])
    
    with tab_crear:
        with st.form("admin_add_user"):
            new_u = st.text_input("Nombre de usuario")
            new_p = st.text_input("Contraseña inicial", type="password")
            new_role = st.selectbox("Rol", ["user", "admin"])
            if st.form_submit_button("Crear Usuario"):
                if new_u and new_p:
                    success, msg = auth_manager.add_user(new_u, new_p, new_role)
                    if success: st.success(msg)
                    else: st.error(msg)
                else:
                    st.error("Por favor completa todos los campos.")

    with tab_reset:
        users_list = auth_manager.get_all_users()
        user_to_edit = st.selectbox("Seleccionar Usuario", users_list)
        new_p_reset = st.text_input("Nueva Contraseña", type="password", key="admin_reset_pass")
        if st.button("Cambiar Contraseña"):
            success, msg = auth_manager.change_password(user_to_edit, new_p_reset)
            if success: st.success(msg)
            else: st.error(msg)
