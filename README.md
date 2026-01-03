# ErasmAI – Recomendador Erasmus con IA

## ¿Qué es este proyecto?

ErasmAI es un asistente que ayuda a recomendar un único destino Erasmus al estudiante, 
usando una combinación de:
- Base de datos de grafos en Neo4j.
- Un sistema RAG con Llama Index.
- Un modelo de lenguaje (Llama 3 vía Groq).
- Una interfaz web hecha con Streamlit.

## ¿Qué hay en cada carpeta?

- `src/`  
  Contiene todo el código de Python:
  - `app.py`: aplicación principal en Streamlit.
  - `recomendadorErasmus.py`: lógica de recomendación y filtrado.
  - `intenciones_matcher.py`: diccionario y detección de peticiones del usuario.
  - `rag_funciones.py`: funciones relacionadas con RAG y el LLM.

- `data/`  
  Contiene los datasets y la guía para montar Neo4j:
  - `datasetSibi.csv`
  - `añadirCosas.csv`
  - `atractivos_FINALES.csv`
  - `neo4j_setup.md`: explicación de cómo crear la base de datos desde cero y todas las queries Cypher.

- `docs/`  
  Documentación generada durante el proyecto:
  - `Memoria_ErasmAI.pdf`
  - `Presentacion_ErasmAI.pdf`
  - `Video_ErasmAI.mp4`

## Listado de avances en el desarrollo:
https://osf.io/6qr4b/wiki?wiki=39t8g

## Instalación (resumen)

1. Crear entorno e instalar dependencias:
  pip install -r requirements.txt

2. Configurar Neo4j siguiendo data/neo4j_setup.txt.

3. Crear un archivo .env donde almacenar la APIKEY necesaria para Groq. La puedes obtener en https://console.groq.com/home

Ejecutar la app:
**streamlit run src/app.py**