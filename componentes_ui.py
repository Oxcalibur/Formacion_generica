import streamlit as st

try:
    from streamlit_mic_recorder import speech_to_text
except ImportError:
    speech_to_text = None

def hybrid_chat_input(placeholder="¿En qué puedo ayudarte hoy?"):
    """
    Componente modular que combina la entrada de teclado tradicional (st.chat_input)
    con la entrada por voz usando la API web del navegador.
    Retorna el string de texto ingresado por cualquiera de los medios.
    """
    # 1. Entrada de Teclado clásica
    prompt_teclado = st.chat_input(placeholder)
    
    # 2. Entrada por Voz flotante
    prompt_voz = None
    if speech_to_text:
        col_espacio, col_mic = st.columns([5, 1])
        with col_mic:
            prompt_voz = speech_to_text(
                language='es-ES',
                start_prompt="🎙️ Usar Voz",
                stop_prompt="🛑 Detener",
                just_once=True,
                use_container_width=True, # Aprovechamos novedad de v0.0.8
                key='stt_input'
            )
    else:
        st.error("⚠️ La librería de voz no está instalada. Abre la terminal y ejecuta: pip install streamlit-mic-recorder==0.0.8")
            
    return prompt_teclado or prompt_voz