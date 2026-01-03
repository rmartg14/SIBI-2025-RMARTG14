"""
Sistema de detección de intenciones y matching con categorías de Neo4j
"""

# ========================================
# DICCIONARIO DE KEYWORDS → CATEGORÍAS
# ========================================

KEYWORDS_EXPERIENCIA = {
    'aventura': ['aventura', 'deporte', 'escalada', 'senderismo', 'montañismo', 'rafting', 'buceo', 'surf'],
    'gastronomia': ['gastronomía', 'gastronomia', 'comida', 'cocina', 'restaurante', 'culinaria', 'comer'],
    'relax': ['relax', 'relajarse', 'descansar', 'tranquilo', 'spa', 'termas'],
    'compras': ['compras', 'shopping', 'tiendas', 'comercio', 'bazar', 'mercado'],
    'parque_tematico': ['parque temático', 'parque tematico', 'atracciones', 'diversión'],
    'salud': ['salud', 'bienestar', 'wellness', 'aguas termales']
}

KEYWORDS_CULTURAL = {
    'historia': ['historia', 'histórico', 'historico', 'antiguo', 'pasado', 'medieval', 'monumento', 'arqueologia'],
    'religion': ['religión', 'religion', 'iglesia', 'catedral', 'mezquita', 'templo', 'sagrado'],
    'cultura': ['cultura', 'cultural', 'tradición', 'tradicion', 'costumbres'],
    'arte': ['arte', 'museo', 'galería', 'galeria', 'pintura', 'escultura', 'exposición', 'exposicion'],
    'patrimonio': ['patrimonio', 'unesco', 'patrimonio unesco', 'monumento', 'ruina'],
    'arquitectura': ['arquitectura', 'edificio', 'construcción', 'construccion', 'diseño', 'diseno']
}

KEYWORDS_GEOGRAFIA = {
    'playa': ['playa', 'costa', 'mar', 'océano', 'oceano', 'litoral'],
    'isla': ['isla', 'archipiélago', 'archipielago'],
    'montaña': ['montaña', 'montana', 'monte', 'pico', 'sierra', 'cordillera', 'escalada'],
    'naturaleza': ['naturaleza', 'natural', 'bosque', 'parque natural', 'reserva', 'fauna', 'flora', 'verde'],
    'lago': ['lago', 'laguna', 'río', 'rio', 'agua dulce'],
    'rural': ['rural', 'campo', 'pueblo', 'aldea']
}

KEYWORDS_CONSTRUCCION = {
    'castillo': ['castillo', 'fortaleza', 'alcázar', 'alcazar', 'fortificación', 'fortificacion'],
    'palacio': ['palacio', 'residencia real', 'villa'],
    'museo': ['museo', 'galería', 'galeria', 'exposición', 'exposicion'],
    'iglesia': ['iglesia', 'catedral', 'basílica', 'basilica', 'capilla'],
    'cueva': ['cueva', 'gruta', 'caverna']
}

KEYWORDS_PAIS = {
    'barato': [
        'barato', 'económico', 'economico', 'bajo coste', 'presupuesto', 
        'asequible', 'low cost', 'no sea caro', 'que no sea caro', 
        'sin gastar mucho', 'precio bajo', 'accesible', 'no muy caro', 
    ],
    'caro': ['caro', 'costoso', 'lujo', 'premium', 'alto coste'],
    'fiesta_alta': [
        'fiesta', 'vida nocturna', 'discoteca', 'bares', 'ocio nocturno', 
        'salir de fiesta', 'ambiente festivo', 'ambiente de fiesta',
        'marcha', 'ambiente animado', 'diversión nocturna'
    ],
    'joven': [
        'joven', 'juvenil', 'estudiante', 'universitario', 'ambiente joven', 
        'gente joven', 'población joven', 'jovenes', 'jóvenes'
    ]
}

# ========================================
# FUNCIONES DE MATCHING
# ========================================

def extraer_intenciones(descripcion_usuario):
    """
    Extrae todas las intenciones detectadas en la descripción del usuario
    
    Args:
        descripcion_usuario: str con la descripción libre del usuario
    
    Returns:
        dict con estructura:
        {
            'categorias_atractivos': ['aventura', 'historia', 'playa', ...],
            'caracteristicas_pais': {
                'coste_bajo': bool,
                'fiesta_alta': bool,
                'ambiente_joven': bool
            }
        }
    """
    texto_lower = descripcion_usuario.lower()
    
    categorias_detectadas = set()
    caracteristicas_pais = {
        'coste_bajo': False,
        'fiesta_alta': False,
        'ambiente_joven': False
    }
    
    for categoria, keywords in {**KEYWORDS_EXPERIENCIA, **KEYWORDS_CULTURAL, 
                                **KEYWORDS_GEOGRAFIA, **KEYWORDS_CONSTRUCCION}.items():
        if any(kw in texto_lower for kw in keywords):
            categorias_detectadas.add(categoria)
    
    if any(kw in texto_lower for kw in KEYWORDS_PAIS['barato']):
        caracteristicas_pais['coste_bajo'] = True
    
    if any(kw in texto_lower for kw in KEYWORDS_PAIS['fiesta_alta']):
        caracteristicas_pais['fiesta_alta'] = True
    
    if any(kw in texto_lower for kw in KEYWORDS_PAIS['joven']):
        caracteristicas_pais['ambiente_joven'] = True
    
    return {
        'categorias_atractivos': list(categorias_detectadas),
        'caracteristicas_pais': caracteristicas_pais
    }


def construir_clausulas_puntuacion(intenciones):
    """
    Construye las cláusulas CASE de Cypher para puntuar según intenciones
    
    Args:
        intenciones: dict retornado por extraer_intenciones()
    
    Returns:
        dict con:
        {
            'puntos_atractivos': str (cláusula Cypher),
            'puntos_pais': str (cláusula Cypher),
            'categorias_buscar': list (para referencia)
        }
    """
    categorias = intenciones['categorias_atractivos']
    caracteristicas = intenciones['caracteristicas_pais']
   
    condiciones_atractivos = []
    for cat in categorias:
        condiciones_atractivos.append(f"""
            CASE WHEN EXISTS {{
                MATCH (p)-[:TIENE_ATRACTIVO]->(a:Atractivo)
                WHERE any(c IN a.categorias WHERE toLower(c) CONTAINS '{cat}')
            }} THEN 100 ELSE 0 END
        """)
        

    
    puntos_atractivos = " + ".join(condiciones_atractivos) if condiciones_atractivos else "0"
    
    condiciones_pais = []
    
    if caracteristicas['coste_bajo']:
        condiciones_pais.append("CASE WHEN p.coste_vida IN ['Bajo', 'Muy Bajo'] THEN 100 ELSE 0 END")
    
    if caracteristicas['fiesta_alta']:
        condiciones_pais.append("CASE WHEN p.ambiente_fiesta IN ['Alto', 'Muy Alto'] THEN 100 ELSE 0 END")
    
    if caracteristicas['ambiente_joven']:
     
        condiciones_pais.append("CASE WHEN p.edad_media < 40 THEN 100 ELSE 0 END")
    
    puntos_pais = " + ".join(condiciones_pais) if condiciones_pais else "0"
    
    return {
        'puntos_atractivos': puntos_atractivos,
        'puntos_pais': puntos_pais,
        'categorias_buscar': categorias
    }


def formatear_categorias_para_prompt(categorias):
    """
    Formatea las categorías detectadas de forma legible para mostrar al usuario
    
    Args:
        categorias: list de categorías detectadas
    
    Returns:
        str con emojis y nombres legibles
    """
    if not categorias:
        return "Ninguna categoría específica detectada"
    
    nombres_legibles = {
        'aventura': '🏔️ Aventura',
        'gastronomia': '🍽️ Gastronomía',
        'relax': '🧘 Relax',
        'vida_nocturna': '🎉 Vida nocturna',
        'compras': '🛍️ Compras',
        'parque_tematico': '🎢 Parques temáticos',
        'salud': '💆 Salud y bienestar',
        'historia': '🏛️ Historia',
        'religion': '⛪ Religión',
        'cultura': '🎭 Cultura',
        'arte': '🎨 Arte',
        'patrimonio': '🏺 Patrimonio',
        'arquitectura': '🏗️ Arquitectura',
        'playa': '🏖️ Playa',
        'isla': '🏝️ Isla',
        'montaña': '⛰️ Montaña',
        'naturaleza': '🌳 Naturaleza',
        'lago': '🌊 Lagos y ríos',
        'rural': '🌾 Rural',
        'castillo': '🏰 Castillos',
        'palacio': '👑 Palacios',
        'museo': '🖼️ Museos',
        'iglesia': '⛪ Iglesias',
        'cueva': '🕳️ Cuevas'
    }
    
    return ", ".join([nombres_legibles.get(cat, cat.title()) for cat in categorias])
