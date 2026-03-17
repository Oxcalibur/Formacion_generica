import streamlit as st
import pandas as pd
import os
from config import CLIENT_CONFIG, SECURITY_CONFIG, apply_custom_styles
from logic import (
    get_current_belt, get_next_belt_data, generate_quiz_questions, evaluate_quiz, 
    get_chat_response, load_knowledge_base, generate_dynamic_roles, generate_dynamic_topics, 
    calculate_roi_metrics, CalculadoraROI, graficar_break_even, graficar_evolucion_roi, 
    graficar_impacto_aprendizaje, log_user_prompt, get_logged_prompts, analyze_prompt_patterns, graficar_patrones_prompts, 
    calculate_historical_improvement_rate, load_multimedia_resources
)
from auth import get_auth_manager

auth_manager = get_auth_manager()

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
                    user_data = auth_manager.get_user_profile(u) # Cargar datos guardados
                    st.session_state.score = user_data["score"]
                    st.session_state.active_sessions = user_data["active_sessions"]
                    st.session_state.user_role = user_data["job_role"]
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
        
        with st.expander("👤 Mi Puesto / Rol"):
            current_role = st.session_state.get("user_role", "Estudiante")
            new_role = st.text_input("Cargo en la empresa", value=current_role)
            if st.button("Guardar Cargo"):
                if auth_manager.update_user_job_role(st.session_state.username, new_role):
                    st.session_state.user_role = new_role
                    st.rerun()

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
    if st.session_state.get("knowledge_base"):
        st.success(f"📚 Base de conocimiento conectada")
    else:
        st.warning("⚠️ Base de conocimiento vacía")
    
    # Selector de Rol (Oculto por solicitud, ahora se gestiona en 'Mi Puesto / Rol')
    # st.session_state.user_role = st.selectbox(
    #     "Tu Nivel / Rol", 
    #     st.session_state.dynamic_roles
    # )
    
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
        nav_options.append("Registro de Prompts (Admin)")
    mode = st.radio("Navegación", nav_options)

# --- Pantalla 1: Asistente Formativo (Chat) ---
if mode == "Asistente Formativo":
    st.header(f"Bienvenido, {st.session_state.user_role}")
    st.caption("Pregunta cualquier duda sobre tus materiales de formación.")

    # Cargar recursos locales para poder recomendarlos
    kb_path = CLIENT_CONFIG.get("knowledge_base_folder", "knowledge_base")
    if not os.path.isabs(kb_path):
        kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), kb_path)
    local_resources = load_multimedia_resources(kb_path)
    if not local_resources:
        st.info("💡 **Admin Tip:** Para habilitar recomendaciones de contenido, crea un archivo `multimedia.csv` en la carpeta `knowledge_base` con las columnas: `Title, URL, Type, Description`.", icon="ℹ️")

    # Inicializar conversación si está vacía
    if not st.session_state.chat_history:
        current_role = st.session_state.get("user_role", "Estudiante")
        welcome_msg = f"Hola, soy {CLIENT_CONFIG['client_name']}. Entiendo que tu rol es **{current_role}**. ¿Cuál es tu reto para hoy?"
        st.session_state.chat_history.append({"role": "assistant", "content": welcome_msg})

    # Mostrar historial
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            # Revisa si hay recomendaciones en el mensaje y las muestra
            if msg.get("recommendations"):
                st.markdown("--- \n**Recursos recomendados:**")
                for rec in msg["recommendations"]:
                    st.markdown(f"- **[{rec.get('title', 'Recurso')}]({rec.get('url', '#')})**: {rec.get('reason', 'Recomendado para profundizar en el tema.')}")

    # Input de usuario
    if prompt := st.chat_input("¿En qué puedo ayudarte hoy?"):
        # Registrar prompt de forma anónima si está habilitado
        if CLIENT_CONFIG.get("log_prompts", False):
            worksheet = CLIENT_CONFIG.get("prompts_worksheet_name")
            if worksheet:
                log_user_prompt(prompt, worksheet, st.session_state.user_role)

        # Registrar interacción si es la primera de la sesión
        if st.session_state.get("logged_in") and not st.session_state.session_interaction_recorded:
            auth_manager.update_user_progress(st.session_state.username, increment_session=True)
            st.session_state.active_sessions += 1
            st.session_state.session_interaction_recorded = True

        # Guardar y mostrar mensaje usuario
        st.session_state.chat_history.append({"role": "user", "content": prompt})

        # Generar respuesta
        with st.spinner("Consultando base de conocimiento..."):
            # Prepara un historial limpio para la IA (sin recomendaciones previas para no contaminar contexto)
            clean_history = [{"role": m.get("role"), "content": m.get("content")} for m in st.session_state.chat_history]
            
            base_prompt = CLIENT_CONFIG["system_prompt"].replace("{client_name}", CLIENT_CONFIG["client_name"])
            current_role = st.session_state.get("user_role", "Estudiante")
            role_context = (
                f"\n\nCONTEXTO DEL USUARIO:\nCargo/Rol actual: {current_role}\n"
                f"INSTRUCCIÓN: El usuario YA tiene el rol '{current_role}'. NO preguntes por el rol. Ve directo a resolver el reto o tema planteado."
            )
            full_prompt = base_prompt + role_context
            
            response_data = get_chat_response(
                clean_history, 
                prompt, 
                full_prompt, 
                knowledge_context=st.session_state.knowledge_base,
                multimedia_index=local_resources
            )
            
            text_response = response_data.get("text", "No he podido generar una respuesta.")
            recommendations = response_data.get("recommendations", [])

        # Guardar la respuesta estructurada (texto + recomendaciones) en el historial
        st.session_state.chat_history.append({"role": "assistant", "content": text_response, "recommendations": recommendations})
        st.rerun()
# --- Pantalla 2: Dojo (Quiz) ---
elif mode == "Dojo (Ponerse a prueba)":
    st.header("🥋 El Dojo")
    st.markdown(f"Demuestra tu conocimiento para subir de cinturón.  \n**Perfil de evaluación:** {st.session_state.user_role}")

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
        
        # --- RECALCULATION WITH ROUNDED VALUES FOR DISPLAY CONSISTENCY ---
        f_rounded = round(metrics.get('F', 0), 1)
        me_rounded = round(metrics.get('Me', 1.0), 2)
        me_avg_rounded = round(metrics.get('Me_avg', 1.0), 2)
        
        # Recalculate AH_op and Total_Value using the rounded display values
        ah_op_display = (metrics['N'] * metrics['P']) * (f_rounded * ts)
        total_value_display = (ah_op_display * me_avg_rounded) * ch
        # --- END RECALCULATION ---

        # 1. Ahorro Operativo
        st.subheader("1. Ahorro Operativo ($AH_{op}$)")
        st.latex(r"AH_{op} = (N \cdot P) \cdot (F \cdot T_s)")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Usuarios (N)", metrics["N"])
        c2.metric("Tasa Part. (P)", f"{metrics['P']:.1%}", help=f"{metrics['active_count']} usuarios con >= {threshold} usos")
        c3.metric("Frecuencia (F)", f"{f_rounded:.1f}", help="Media de sesiones de usuarios activos")
        c4.metric("Ahorro Base", f"{ah_op_display:.1f} h")
        
        # 2. Multiplicador
        st.subheader("2. Multiplicador de Evolución ($M_e$)")
        st.latex(r"M_e = 1 + \left( \frac{\text{Nivel Actual} - 1}{\text{Nivel Máximo}} \right)")
        st.metric("Multiplicador Actual", f"x{me_rounded:.2f}", help="Nivel de eficiencia que tienen los usuarios HOY.")
        
        # 3. Total
        st.subheader("3. Valor Total Generado")
        st.latex(r"\text{Valor} = (AH_{op} \cdot M_{avg}) \cdot C_h")
        
        st.metric("Ahorro Económico Total", f"{total_value_display:,.2f} €", help=f"Calculado usando la eficiencia media histórica (x{me_avg_rounded}) para compensar la curva de aprendizaje.")
        
        if show_graphs:
            # --- PROYECCIÓN FINANCIERA ---
            st.divider()
            st.header("🚀 Proyección Financiera (Motor de ROI)")
            st.caption("Simulación basada en la evolución del aprendizaje de los usuarios.")
            
            # Cálculo de tasa sugerida basada en histórico
            suggested_rate = calculate_historical_improvement_rate(metrics["Me"], metrics["F"], proj_freq)
            suggested_rate_pct = suggested_rate * 100.0
            st.info(f"💡 **Dato Histórico:** Basado en el uso actual, tus usuarios mejoran su eficiencia un **{suggested_rate_pct:.1f}%** al mes.")
            
            # Input adicional para el modelo de aprendizaje (Preconfigurado con el dato histórico)
            default_rate = max(0.0, min(15.0, float(suggested_rate_pct)))
            tasa_mejora = st.slider("Tasa de Mejora Mensual (%)", 0.0, 15.0, default_rate, 0.1, help="Incremento lineal de eficiencia acumulado cada mes (Mes × Tasa)") / 100.0
            
            # Cálculo del nivel inicial basado en el multiplicador actual (Me)
            # Me va de 1.0 a 2.0 aprox. Mapeamos a nivel 1-10.
            nivel_inicial = (me_rounded - 1) * 10 # Usamos el valor redondeado y sin convertir a int
            if nivel_inicial < 0: nivel_inicial = 0.0
            
            # Instanciar Motor Lógico
            calculadora = CalculadoraROI(
                n_usuarios=metrics["N"],
                coste_hora=ch,
                inversion_inicial=investment,
                tiempo_ahorrado_mins=ts * 60,
                frecuencia_uso_mensual=proj_freq,
                tasa_adopcion_pct=metrics["P"], # Se mantiene la precisión para la proyección
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

# --- Pantalla 5: Registro de Prompts (Admin) ---
elif mode == "Registro de Prompts (Admin)":
    st.header("📋 Registro de Prompts")
    st.markdown("Visualización de las consultas realizadas por los usuarios (Anónimo).")
    
    with st.expander("📘 Guía Funcional: Ejemplo de Interpretación"):
        st.markdown("""
        ### Caso de Uso: Detección de Brechas en Formación de Liderazgo
        
        **1. La Situación (El Dato):**
        Lanzas un curso para nuevos managers. En el **Mapa de Inquietudes**, detectas que el bloque más grande es *"Gestión de Conflictos"*, con preguntas específicas sobre *"Cómo dar feedback a ex-compañeros"*.
        
        **2. La Interpretación (El Insight):**
        El sistema te revela que la **teoría** (los manuales) se ha entendido, pero existe una barrera **emocional/práctica** en la ejecución real.
        
        **3. La Decisión (El Valor):**
        Gracias al **Plan de Acción** generado por la IA, decides no añadir más teoría, sino crear una **"Hoja de Guiones (Scripts)"** para situaciones tensas.
        
        *Resultado: Transformas una formación genérica en una solución quirúrgica para un problema real detectado en días, no meses.*
        """)
    
    worksheet_name = CLIENT_CONFIG.get("prompts_worksheet_name")
    if worksheet_name:
        with st.spinner("Cargando registros..."):
            df_prompts = get_logged_prompts(worksheet_name)
        
        if not df_prompts.empty:
            if "timestamp" in df_prompts.columns:
                df_prompts["timestamp"] = pd.to_datetime(df_prompts["timestamp"])
                df_prompts = df_prompts.sort_values(by="timestamp", ascending=False)
            
            st.subheader("☁️ Análisis de Tendencias (IA)")
            st.markdown("Agrupación inteligente de inquietudes por temática.")
            
            # Botón para refrescar análisis (limpiar caché)
            if st.button("🔄 Refrescar Análisis IA"):
                if "patterns_cache" in st.session_state:
                    del st.session_state.patterns_cache
                st.rerun()

            if "patterns_cache" not in st.session_state:
                with st.spinner("Detectando patrones en las consultas..."):
                    # Preparamos la lista incluyendo el rol si existe para mejor contexto
                    if "role" in df_prompts.columns:
                        prompts_list = [f"[{row['role']}] {row['prompt']}" for _, row in df_prompts.dropna(subset=['prompt']).iterrows()]
                    else:
                        prompts_list = df_prompts["prompt"].dropna().tolist()
                    
                    st.session_state.patterns_cache = analyze_prompt_patterns(prompts_list)
            
            patterns = st.session_state.patterns_cache
            
            if patterns:
                # 1. Controles de Filtrado (Mueven el Mapa y el Plan)
                if "trend_filter" not in st.session_state:
                    st.session_state.trend_filter = "Global (Visión General)"

                current_filter = st.session_state.trend_filter

                def update_filter_from_combo():
                    st.session_state.trend_filter = st.session_state.combo_selection

                roles_detected = sorted(list(set(p.get('rol', 'General') for p in patterns)))
                topics_detected = sorted(list(set(p.get('tematica', 'Varios') for p in patterns)))
                
                # Generación Dinámica de Opciones (Simplificada para navegación fluida)
                # Mostramos siempre todas las opciones para evitar problemas de refresco o navegación
                base_options = ["Global (Visión General)"]
                dynamic_options = base_options + [f"Rol: {r}" for r in roles_detected] + [f"Tema: {t}" for t in topics_detected]
                
                col_sel, col_btn = st.columns([3, 1])
                
                # Asegurar que la selección actual esté en las opciones (por seguridad)
                if current_filter not in dynamic_options:
                    dynamic_options.append(current_filter)
                    
                try:
                    sel_index = dynamic_options.index(current_filter)
                except ValueError:
                    sel_index = 0

                with col_sel:
                    selection = st.selectbox(
                        "🔍 Filtrar Mapa y Plan por:", 
                        dynamic_options, 
                        index=sel_index,
                        key="combo_selection",
                        on_change=update_filter_from_combo
                    )

                # 2. Filtrar Datos (Sincronización)
                filtered_patterns = patterns
                if selection.startswith("Rol: "):
                    role_key = selection.replace("Rol: ", "")
                    filtered_patterns = [p for p in patterns if p.get('rol', 'General') == role_key]
                elif selection.startswith("Tema: "):
                    topic_key = selection.replace("Tema: ", "")
                    filtered_patterns = [p for p in patterns if p.get('tematica', 'Varios') == topic_key]

                # 3. Generar Mapa Dinámico
                fig = graficar_patrones_prompts(filtered_patterns)
                if fig:
                    fig.update_layout(title=f"<b>Mapa de Inquietudes ({selection})</b>")
                    
                    # Capturar evento de clic en el gráfico
                    # Añadimos key dinámica para forzar refresco correcto al cambiar selección
                    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key=f"map_{selection}")
                    
                    # Lógica: Si se toca el mapa, actualizar el filtro (Maestro)
                    if event and event.get("selection") and event["selection"]["points"]:
                        clicked_point = event["selection"]["points"][0]
                        # customdata contiene la etiqueta formateada (ej: "Rol: Director")
                        clicked_val = clicked_point.get("customdata")
                        
                        # Validar si lo clickeado es una opción válida de filtro (Rol o Tema)
                        # Nota: Las "Inquietudes" (hojas) no suelen ser filtros de alto nivel, pero si se desea, se puede adaptar.
                        # Aquí asumimos que si clickea Rol o Tema, filtramos.
                        if clicked_val and (clicked_val.startswith("Rol: ") or clicked_val.startswith("Tema: ") or clicked_val == "Global (Visión General)"):
                            if clicked_val != st.session_state.trend_filter:
                                st.session_state.trend_filter = clicked_val
                                st.rerun()
                    
                    # --- Plan de Acción Recomendado ---
                    st.divider()
                    st.subheader("🧠 Plan de Acción Recomendado (IA)")
                    st.caption("Genera una estrategia de formación basada en las inquietudes detectadas en el mapa.")

                    with col_btn:
                        # Espaciado para alinear con el selectbox
                        st.write("") 
                        st.write("")
                        if st.button("Generar Plan", use_container_width=True):
                            st.session_state.gen_plan_clicked = True
                    
                    # Mostrar resultado si se ha solicitado (o usar estado si se prefiere persistencia simple)
                    if st.session_state.get("gen_plan_clicked", False):
                        with st.spinner(f"Diseñando estrategia para: {selection}..."):
                            from logic import generate_action_plan
                            kb_path = CLIENT_CONFIG.get("knowledge_base_folder", "knowledge_base")
                            if not os.path.isabs(kb_path):
                                kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), kb_path)
                            # Pasamos la base de conocimiento para que la IA reconozca metodologías específicas (ej. SCARF)
                            plan = generate_action_plan(filtered_patterns, focus=selection, knowledge_context=st.session_state.knowledge_base)
                            st.info(f"Estrategia generada para: **{selection}**")
                            st.markdown(plan)
                            st.session_state.gen_plan_clicked = False # Reset para permitir regenerar
            else:
                st.warning("No se pudieron identificar patrones suficientes.")
        else:
            st.info("No hay prompts registrados aún.")
    else:
        st.warning("No se ha configurado la hoja de registro de prompts.")
