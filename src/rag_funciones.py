"""
Funciones para el sistema RAG final: búsqueda por intenciones y recomendación con Phi
"""

from intenciones_matcher import construir_clausulas_puntuacion, formatear_categorias_para_prompt
import re


def buscar_destinos_por_intenciones(cypher_engine, destinos_filtrados, intenciones):
    """
    Filtra y puntúa destinos según intenciones detectadas
    """
    print("\n🔍 Analizando características en la base de datos...")
    
    clausulas = construir_clausulas_puntuacion(intenciones)

    print("🛠️ Cláusulas Cypher generadas:")
    print(f"   Puntos Atractivos: {clausulas['puntos_atractivos'][:100]}...")
    print(f"   Puntos País: {clausulas['puntos_pais'][:100]}...")
    
    universidades_validas = [d['Universidad'] for d in destinos_filtrados]
    uni_list = "', '".join(universidades_validas)
    
    query = f"""
        MATCH (u:Universidad)-[:SITUADA_EN]->(l:Ciudad)-[:UBICADA_EN]->(p:Pais)
        WHERE u.nombre IN ['{uni_list}']
        
        // Calcular puntos por país (coste, fiesta, edad)
        WITH u, l, p,
             ({clausulas['puntos_pais']}) AS PuntosPais
        
        // Calcular puntos por atractivos
        WITH u, l, p, PuntosPais,
             ({clausulas['puntos_atractivos']}) AS PuntosAtractivos
        
        // Sumar ambos
        WITH u, l, p,
             PuntosAtractivos + PuntosPais AS PuntosCaracteristicas
        
        // Ahora obtener atractivos destacados
        OPTIONAL MATCH (p)-[:TIENE_ATRACTIVO]->(a:Atractivo)
        WITH u, l, p, PuntosCaracteristicas, a
        ORDER BY a.rating DESC
        
        WITH u, l, p, PuntosCaracteristicas,
             collect(a)[0..10] AS atractivos_top
        
        RETURN u.nombre AS Universidad,
               p.nombre AS Pais,
               p.localizacion AS Localizacion,
               l.nombre AS Ciudad,
               l.poblacion AS Poblacion,
               p.coste_vida AS Coste_Vida,
               p.ambiente_fiesta AS Ambiente_Fiesta,
               p.comidas_tipicas AS Comidas_Tipicas,
               p.temp_media_anual AS Temperatura,
               p.edad_media AS Edad_Media,
               PuntosCaracteristicas,
               [a IN atractivos_top | {{
                   nombre: a.nombre,
                   rating: a.rating,
                   categorias: a.categorias,
                   descripcion: a.descripcion,
                   visitantes: a.visitantes_anuales
               }}] AS Atractivos_Destacados
    """
    
    with cypher_engine.driver.session(database=cypher_engine.database) as session:
        resultados = session.run(query).data()
    
    print(f"✅ Encontrados {len(resultados)} destinos que cumplen características")
    
    return resultados

def ajustar_puntos_por_cantidad_atractivos(candidatos_neo4j, intenciones):
    """
    Ajusta puntos según la cantidad de veces que aparece la categoría solicitada
    entre los 10 principales atractivos de cada país (collect(a)[0..10]).
    Bonus: +10 puntos por cada aparición.
    """
    categorias_buscadas = intenciones['categorias_atractivos']
    if not categorias_buscadas:
        return candidatos_neo4j

    for candidato in candidatos_neo4j:
        atractivos = candidato.get('Atractivos_Destacados', [])  
        bonus = 0
        for cat in categorias_buscadas:
            count = 0
            for atr in atractivos:
                for c in atr.get('categorias', []):
                    if cat in c.lower():
                        count += 1
            bonus += count * 10
        candidato['PuntosCaracteristicas'] = candidato.get('PuntosCaracteristicas', 0) + bonus

    return candidatos_neo4j



def enriquecer_con_puntuaciones(candidatos_neo4j, destinos_filtrados):
    """
    Suma puntuación base + puntos características y devuelve TOP 5
    """
    candidatos_enriquecidos = []
    
    for candidato in candidatos_neo4j:
        for dest_original in destinos_filtrados:
            if dest_original['Universidad'] == candidato['Universidad']:
                puntuacion_base = dest_original['PuntuacionCompuesta']
                puntos_caracteristicas = candidato.get('PuntosCaracteristicas', 0)
                
                candidato['PuntuacionBase'] = puntuacion_base
                candidato['PuntosCaracteristicas'] = puntos_caracteristicas
                candidato['PuntuacionTotal'] = puntuacion_base + puntos_caracteristicas
                
                candidatos_enriquecidos.append(candidato)
                break
    
    candidatos_enriquecidos.sort(
        key=lambda x: x.get('PuntuacionTotal', 0), 
        reverse=True
    )
    
    print(f"✅ TOP 5 candidatos finales seleccionados")
    
    print("\n" + "="*70)
    print("🔍 DEBUG: TOP 5 DESTINOS CON PUNTUACIONES")
    print("="*70)
    
    top5 = candidatos_enriquecidos[:5]
    
    for i, dest in enumerate(top5, 1):
        print(f"\n{i}. {dest['Universidad']} - {dest['Ciudad']}, {dest['Pais']}")
        print(f"   📊 Puntuación Base: {dest.get('PuntuacionBase', 0):.2f} pts")
        print(f"   ➕ Puntos Características: {dest.get('PuntosCaracteristicas', 0):.0f} pts")
        print(f"   🏆 TOTAL: {dest.get('PuntuacionTotal', 0):.2f} pts")
        print(f"   💰 Coste: {dest.get('Coste_Vida', 'N/A')}")
        print(f"   🎉 Fiesta: {dest.get('Ambiente_Fiesta', 'N/A')}")
        print(f"   👥 Edad media: {dest.get('Edad_Media', 'N/A')} años")
        print(f"   🌡️ Temperatura: {dest.get('Temperatura', 'N/A')}°C")
        
        if dest.get('Atractivos_Destacados'):
            print(f"   🏛️ Atractivos ({len(dest['Atractivos_Destacados'])}):")
            for atr in dest['Atractivos_Destacados'][:3]:
                print(f"      • {atr['nombre']} ({atr['rating']}/5) - {', '.join(atr['categorias'][:3])}")
    
    print("\n" + "="*70 + "\n")
    
    return top5



def filtrar_input_usuarios(texto):
    """Filtra patrones sospechosos para prevenir prompt injection"""
    patrones_prohibidos = [
        # Frases típicas de ataque
        r"ignore (all )?previous instructions",
        r"ignore (the )?above",
        r"disregard (the )?above",
        r"overwrite instructions",
        r"reset (the )?conversation",
        r"do as user says",
        r"as a system prompt",
        r"as an ai language model",
        # Instrucciones para cambiar rol
        r"you are now ",
        r"from now on ",
        r"pretend to be ",
        # Instrucciones para saltarse restricciones
        r"bypass restrictions",
        r"break character",
        r"respond in [A-Za-z]+ (only)?",
        # Inyección de delimitadores o código
        r"``````",        # Bloques de código markdown extensos
        r"<.*?>",            # Posibles etiquetas HTML o delimitadores
        r"{.*?}",            # Posibles instrucciones envolviendo payloads
        r"\[.*?]",           # Delimitadores inusuales
        # Comandos peligrosos/llamadas de función
        r"exit\(\)",
        r"quit",
        r"run (this )?code",
        r"execute (the )?following",
        # Instrucciones directas de manipulación
        r"repeat after me",
        r"ignore safety",
        r"respond with",
        r"write a prompt",
    ]
    texto_filtrado = texto
    for pat in patrones_prohibidos:
        texto_filtrado = re.sub(pat, "", texto_filtrado, flags=re.IGNORECASE|re.DOTALL)
    return texto_filtrado.strip()


def recomendar_con_llama(llm, descripcion_usuario, candidatos_finales, intenciones, preferencias_iniciales=None):
    """
    Llama-3 analiza el TOP 5 y recomienda el mejor destino con razonamiento profundo
    """
    contexto_candidatos = ""
    for i, dest in enumerate(candidatos_finales, 1):
        pob = f"{dest['Poblacion']:,}".replace(',', '.')
        contexto_candidatos += f"\n{'='*70}\n"
        contexto_candidatos += f"**OPCIÓN {i}: {dest['Universidad']}**\n"
        contexto_candidatos += f"📍 {dest['Ciudad']} ({pob} hab.), {dest['Pais']} ({dest.get('Localizacion', 'N/A')})\n\n"
        
        contexto_candidatos += f"**📊 PUNTUACIONES (solo orientativas):**\n"
        contexto_candidatos += f"- Base (preferencias iniciales): {dest.get('PuntuacionBase', 0):.0f} pts\n"
        contexto_candidatos += f"- Características descritas: +{dest.get('PuntosCaracteristicas', 0):.0f} pts\n"
        contexto_candidatos += f"- Total: {dest.get('PuntuacionTotal', 0):.0f} pts\n\n"
        
        contexto_candidatos += f"**🌍 CARACTERÍSTICAS DEL PAÍS:**\n"
        contexto_candidatos += f"- Temperatura media: {dest.get('Temperatura', 'N/A')}°C\n"
        contexto_candidatos += f"- Coste de vida: {dest.get('Coste_Vida', 'N/A')}\n"
        contexto_candidatos += f"- Ambiente festivo: {dest.get('Ambiente_Fiesta', 'N/A')}\n"
        contexto_candidatos += f"- Edad media población: {dest.get('Edad_Media', 'N/A')} años\n"
        contexto_candidatos += f"- Gastronomía típica: {dest.get('Comidas_Tipicas', 'N/A')}\n\n"
        
        if dest.get('Atractivos_Destacados'):
            contexto_candidatos += f"**🏛️ ATRACTIVOS TURÍSTICOS DESTACADOS:**\n"
            for j, atr in enumerate(dest['Atractivos_Destacados'][:5], 1):
                contexto_candidatos += f"\n{j}. **{atr['nombre']}** ⭐ {atr['rating']}/5\n"
                contexto_candidatos += f"   Categorías: {', '.join(atr['categorias'][:4])}\n"
                if atr.get('visitantes'):
                    vis = f"{atr['visitantes']:,}".replace(',', '.')
                    contexto_candidatos += f"   {vis} visitantes/año\n"
                contexto_candidatos += f"   {atr['descripcion'][:180]}...\n"
        
        contexto_candidatos += "\n"
    
    categorias_texto = formatear_categorias_para_prompt(intenciones['categorias_atractivos'])
    
    contexto_preferencias = ""
    if preferencias_iniciales:
        contexto_preferencias = "\n**PREFERENCIAS INICIALES DEL ESTUDIANTE (del cuestionario previo):**\n"
        if preferencias_iniciales.get('Idioma'):
            contexto_preferencias += f"- Nivel de idioma: {preferencias_iniciales['Idioma']}\n"
        if preferencias_iniciales.get('Clima'):
            contexto_preferencias += f"- Clima preferido: {preferencias_iniciales['Clima']}\n"
        if preferencias_iniciales.get('Region'):
            contexto_preferencias += f"- Región preferida: {preferencias_iniciales['Region']}\n"
        if preferencias_iniciales.get('TamanoCiudad'):
            contexto_preferencias += f"- Tamaño de ciudad: {preferencias_iniciales['TamanoCiudad']}\n"
        contexto_preferencias += "\n"
    
    
    descripcion_usuario_filtrada = filtrar_input_usuarios(descripcion_usuario)
    prompt = f"""Eres un asistente experto en recomendaciones Erasmus que ayuda a estudiantes españoles a elegir su mejor destino.

{contexto_preferencias}
**LO QUE EL ESTUDIANTE BUSCA (descripción libre final):**
"{descripcion_usuario_filtrada}"

**CARACTERÍSTICAS DETECTADAS EN LA DESCRIPCIÓN:**
- Atractivos deseados: {categorias_texto if categorias_texto != "Ninguna categoría específica detectada" else "No especificados"}
- Coste bajo: {'Sí' if intenciones['caracteristicas_pais']['coste_bajo'] else 'No'}
- Ambiente festivo: {'Sí' if intenciones['caracteristicas_pais']['fiesta_alta'] else 'No'}
- Ambiente joven: {'Sí' if intenciones['caracteristicas_pais']['ambiente_joven'] else 'No'}

**TOP 5 DESTINOS CANDIDATOS:**
{contexto_candidatos}

**INSTRUCCIONES IMPORTANTES:**

1. La puntuación total solo es una guía orientativa, NO el criterio definitivo.
2. Analiza profundamente qué destino cumple mejor:
    - Las preferencias iniciales del cuestionario
    - Lo que describió en su búsqueda libre
    - La calidad y relevancia de los atractivos turísticos
    - La experiencia Erasmus típica en ese país
3. Explica tu razonamiento conectando TODAS las piezas: preferencias iniciales, descripción libre y características del destino.
4. **Sé completamente honesto. Si el destino NO cumple completamente con alguna preferencia importante del usuario (clima, región, idioma, tamaño de ciudad, etc.), DEBES indicarlo claramente antes de justificar la elección. Prohibido omitir o suavizar estos incumplimientos.**
5. **Nunca inventes ni exageres características. Si un criterio objetivo no se cumple según los datos, dilo claramente y nunca afirmes que sí cumple. Evita frases vagas como “es algo más frío que tu preferencia” o “te hará sentir en el norte”.**
6. **Antes de justificar la recomendación, realiza un apartado explícito (Desventajas a considerar”) donde enumeres uno a uno los requisitos del usuario que NO se cumplen (por ejemplo: “El destino NO cumple la preferencia de clima frío, pues su temperatura media es 16.9°C, mayor que el umbral de 13°C”; “Esta ciudad no es realmente pequeña, pues tiene 530.000 habitantes”). Solo tras ese apartado, explica por qué se recomienda igualmente.**
7. **No adaptes ni cambies los valores numéricos. Utiliza los datos tal cual: si la temperatura, población o región no coinciden plenamente con lo solicitado, decláralo sin camuflarlo en la argumentación.**
8. Guía para criterios objetivos (aplícalos siempre tal cual):
    - Clima frío: solo si la temperatura media anual es menor o igual a 13°C.
    - Ciudad pequeña: solo si la población es menor o igual a 150.000 habitantes. Por ejemplo 300.000 habitantes es una ciudad grande y 120000 habitantes una ciudad pequeña.
    - Región, idioma y requisitos: comparar si lo que ha puesto el usuario se coresponde con los datos exactos proporcionados.
    - Si existen diferencias relevantes, indícalas claramente. Ejemplo:  
      “Este destino NO cumple tu preferencia de clima frío, ya que la temperatura media es 16.9°C (clima templado)...”
    - Si todo se cumple, indícalo explícitamente: “El destino cumple todos los requisitos objetivos del usuario.”
9. Si el usuario especificó que NO desea algún país, ciudad o destino concreto (“no quiero ir a Polonia”, “cualquier sitio menos Italia”), jamás recomiendes ese destino, aunque se ajuste a otras preferencias.

**Revisa todos estos puntos antes de generar tu recomendación final. Es obligatorio reflejar los criterios no cumplidos antes de justificar la elección.**

🎓 **DESTINO RECOMENDADO:**
[Universidad] en [Ciudad], [País]


🎯 **POR QUÉ ES PERFECTO PARA TI:**
[IMPORTANTE: Conecta explícitamente con sus preferencias iniciales del cuestionario. Ejemplo: "Te recomiendo este destino porque cumple con tu nivel de [idioma], tu preferencia por [clima], [región] y [tamaño de ciudad]. Además, basándome en tu descripción donde buscabas [X, Y, Z]..."]
[IMPORTANTE: Si no cumple con alguna característica también se debe detallar. Ejemplo: "Aunque no se encuentre en la [región] y el [clima] no se corresponda con tu preferencia, lo sigo considerando la mejor opción analizando tu descripción donde buscabas [X, Y, Z] "]
[Continúa explicando en 4-5 líneas cómo este destino específico cumple o no con clima, localización, coste, ambiente, edad de la población y por qué encaja perfectamente con sus preferencias.]



🏛️ **ATRACTIVOS IMPERDIBLES DEL PAÍS:**
[Lista 3-4 atractivos turísticos específicos del país, explicando brevemente por qué son relevantes para lo que el estudiante busca]

🌍 **SOBRE EL PAÍS Y LA CIUDAD:**
- **Localización:** {dest.get('Localizacion')} - [Contexto geográfico y cultural]
- **Clima:** {dest.get('Temperatura')}°C de media anual - [Qué significa esto para la experiencia]
- **Tamaño ciudad:** {dest['Poblacion']} habitantes - [Ambiente urbano/tranquilo]
- **Cultura y estilo de vida:** [Describe el ambiente típico del país, costumbres, mentalidad]

💰 **COSTE DE VIDA:**
Nivel: {dest.get('Coste_Vida')}
[Explica qué significa esto en la práctica para un estudiante Erasmus español: alojamiento, comida, transporte, ocio]

🎉 **VIDA ESTUDIANTIL Y AMBIENTE:**
- **Ambiente festivo:** {dest.get('Ambiente_Fiesta')}
- **Edad media población:** {dest.get('Edad_Media')} años
- **Comunidad Erasmus:** [Describe el ambiente universitario, vida nocturna, actividades típicas]
- **Gastronomía:** {dest.get('Comidas_Tipicas')} - [Destaca platos que no puede perderse]

💡 **CONSEJO FINAL:**
[Un consejo personalizado basado en todo lo anterior]
"""
    
    print(f"🤖 Llama-3 generando recomendación personalizada...\n")
    response = llm.complete(prompt)
    return response.text
