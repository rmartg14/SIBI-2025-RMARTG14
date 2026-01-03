import streamlit as st
import time
from recomendadorErasmus import ErasmAIAssistant, cypher_engine, llm

st.markdown(
    """
    <div style='width:100%; display:flex; flex-direction:column; align-items:flex-start; margin-top:1.5em; margin-bottom:1.2em;'>
        <div style='display: flex; align-items: center; gap: 0.6em;'>
            <span style="font-size:2em;">🧑‍🎓</span>
            <span style="font-size:2.3em; font-weight:900; color:#7B44D1; line-height:1.0;">
              Erasm<span style="color:#F6C200;">AI</span>
            </span>
        </div>
        <span style="font-size:1.3em; font-weight:400; margin-left:2.7em; margin-top: -.1em; color:#FFA500;">
            El Asistente Erasmus de la Universidad de León
        </span>
    </div>
    """,
    unsafe_allow_html=True
)


with st.sidebar:
    st.markdown(
       """
       <div style='display: flex; flex-direction: column; align-items: center; justify-content: flex-start; margin-top: -24px; margin-bottom: 1.1em;'>
           <span style="font-size:2.7em; line-height: 1;">🧑‍🎓</span>
           <span style="font-size:2.15em; font-weight:900; margin-top: -0.12em;">
               <span style="color:#7B44D1;">Erasm</span><span style="color:#F6C200;">AI</span>
           </span>
       </div>
       """, unsafe_allow_html=True
   )
    
    st.markdown("""<hr style='margin-top: 0.4em; margin-bottom: 1.2em; border: 0; border-top: 2px solid #333;'/>""", unsafe_allow_html=True)
    
    st.markdown(
        """
        <div style='display: flex; align-items: center; gap: 0.6em; margin-bottom: 0.5em;'>
            <span style="font-size: 1.5em;">⚙️</span>
            <span style="font-size:1.08em; font-weight:bold;">Configuraciones</span>
        </div>
        """, unsafe_allow_html=True
    )
    
    reiniciar = st.button("🔄 Reiniciar conversación", use_container_width=True, key="btn_reiniciar", help="Pulsa para empezar una nueva conversación")
  

    with st.expander("ℹ️ Ayuda rápida"):
        st.markdown(
            """
            - Pulsa arriba para reiniciar la conversación.
            - ErasmAI te guiará paso a paso para encontrar tu destino Erasmus ideal.
            - ¿Dudas? Pregunta en el chat.
            """
        )
        
    st.markdown("""<hr style='margin: 1.8em 0 1.1em 0; border: 0; border-top: 1.5px solid #333;'/>""", unsafe_allow_html=True)

    st.markdown(
        """
        <div style='display: flex; align-items: center; gap: 0.5em; margin-bottom: 0.4em;'>
            <span style="font-size: 1.35em;">📚</span>
            <span style="font-size:1.09em; font-weight: bold;">Más información</span>
        </div>
        """, unsafe_allow_html=True
    )
    if st.button("🌐 Ver destinos Erasmus ULE", use_container_width=True, key="btn_destinos"):
        st.markdown("[Ir a la web de destinos Erasmus de la ULE](https://www.unileon.es/internacional/estudiantes/movilidad-internacional-salientes/erasmus-estudio/plazas)", unsafe_allow_html=True)
    st.info(
        "Consulta todos los destinos Erasmus disponibles en la web oficial de la Universidad de León.",
        icon="🌍"
    )

    



# -- Lógica de reinicio fuera del with sidebar --
if reiniciar:
    st.session_state.erasmai = ErasmAIAssistant(llm, cypher_engine)
    bienvenida = st.session_state.erasmai.procesar_mensaje("")
    st.session_state.messages = [
        {"role": "assistant", "content": bienvenida}
    ]



if "erasmai" not in st.session_state:
    st.session_state.erasmai = ErasmAIAssistant(llm, cypher_engine)
    bienvenida = st.session_state.erasmai.procesar_mensaje("")
    st.session_state.messages = [
        {"role": "assistant", "content": bienvenida}
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Escribe tu mensaje aquí...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    # Simular "ErasmAI está escribiendo..."
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("ErasmAI está escribiendo...")
        time.sleep(2)  # Delay visual
        respuesta = st.session_state.erasmai.procesar_mensaje(prompt)
        placeholder.markdown(respuesta)
    st.session_state.messages.append({"role": "assistant", "content": respuesta})
