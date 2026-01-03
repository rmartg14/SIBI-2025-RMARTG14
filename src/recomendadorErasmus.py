
from neo4j import GraphDatabase
from llama_index.core.query_engine import BaseQueryEngine
from llama_index.core.callbacks import CallbackManager
import json
import re
from difflib import get_close_matches
from intenciones_matcher import extraer_intenciones, construir_clausulas_puntuacion, formatear_categorias_para_prompt
from rag_funciones import buscar_destinos_por_intenciones, enriquecer_con_puntuaciones, recomendar_con_llama, ajustar_puntos_por_cantidad_atractivos
from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()


NIVEL_MAPA = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4, 'C1': 5, 'C2': 6}
def nivel_a_numero(nivel):
    return NIVEL_MAPA.get(nivel.upper(), 0)

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "Contraseña1."
DATABASE = "neo4j"


CARRERAS_NEO4J = [
    "derecho", "ciencia de los alimentos", "veterinaria", "biología",
    "biotecnología", "ciencias ambientales", "ingles", "geografia",
    "historia", "historia del arte", "lengua y literatura", "ade",
    "comercio internacional", "economía", "finanzas", "marketing",
    "turismo", "rrll y rrhh", "ingenieria aeroespacial",
    "ingenieria de datos", "ingenieria electrica", "ingenieria industrial",
    "ingenieria informatica", "ingenieria mecanica", "topografia",
    "ingenieria de la energia", "ingenieria minera", "ingenieria agraria",
    "ingenieria forestal", "educacion infantil", "educacion primaria",
    "educacion social", "enfermeria", "fisioterapia", "podologia",
    "trabajo social", "ciencias del deporte"
]

ALIAS_CARRERAS = {
    "informatica": "ingenieria informatica",
    "ingeniería informática": "ingenieria informatica",
    "ing informatica": "ingenieria informatica",
    "industrial": "ingenieria industrial",
    "mecanica": "ingenieria mecanica",
    "electrica": "ingenieria electrica",
    "aeroespacial": "ingenieria aeroespacial",
    "datos": "ingenieria de datos",
    "minera": "ingenieria minera",
    "agraria": "ingenieria agraria",
    "forestal": "ingenieria forestal",
    "energia": "ingenieria de la energia",
    "administracion de empresas": "ade",
    "empresariales": "ade",
    "economia": "economía",
    "comercio": "comercio internacional",
    "infantil": "educacion infantil",
    "primaria": "educacion primaria",
    "magisterio": "educacion primaria",
    "pedagogia": "educacion social",
    "biologia": "biología",
    "bio": "biología",
    "biotecnologia": "biotecnología",
    "ambientales": "ciencias ambientales",
    "medio ambiente": "ciencias ambientales",
    "alimentos": "ciencia de los alimentos",
    "enfermeria": "enfermeria",
    "fisio": "fisioterapia",
    "podo": "podologia",
    "geografia": "geografia",
    "geo": "geografia",
    "filologia": "lengua y literatura",
    "lengua": "lengua y literatura",
    "arte": "historia del arte",
    "relaciones laborales": "rrll y rrhh",
    "recursos humanos": "rrll y rrhh",
    "rrhh": "rrll y rrhh",
    "trabajo social": "trabajo social",
    "ts": "trabajo social",
    "deporte": "ciencias del deporte",
    "deportes": "ciencias del deporte",
    "cafyd": "ciencias del deporte",
    "educacion fisica": "ciencias del deporte",
}

def normalizar_texto(texto):
    """Normaliza texto: minúsculas, sin tildes"""
    texto = texto.lower()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u'
    }
    for old, new in replacements.items():
        texto = texto.replace(old, new)
    return texto

def validar_carrera(texto_usuario):
    """Valida y mapea la entrada del usuario a una carrera oficial"""
    texto_limpio = texto_usuario.strip().lower()
    texto_normalizado = normalizar_texto(texto_limpio)
    
   
    for carrera in CARRERAS_NEO4J:
        if texto_limpio == carrera or texto_normalizado == normalizar_texto(carrera):
            return carrera, carrera.title()
    
  
    if texto_normalizado in ALIAS_CARRERAS:
        carrera_oficial = ALIAS_CARRERAS[texto_normalizado]
        return carrera_oficial, carrera_oficial.title()
    
  
    for carrera in CARRERAS_NEO4J:
        if texto_normalizado in normalizar_texto(carrera):
            return carrera, carrera.title()
        if normalizar_texto(carrera) in texto_normalizado:
            return carrera, carrera.title()
    
   
    carreras_normalizadas = [normalizar_texto(c) for c in CARRERAS_NEO4J]
    matches = get_close_matches(texto_normalizado, carreras_normalizadas, n=1, cutoff=0.7)
    
    if matches:
        idx = carreras_normalizadas.index(matches[0])
        carrera_oficial = CARRERAS_NEO4J[idx]
        return carrera_oficial, carrera_oficial.title()
    
    return None, None

print("🔄 Conectando a Neo4j...")
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
print("✅ Driver de Neo4j inicializado.")
print("🔄 Inicializando LLM (Groq Llama-3.1)...")


groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


class GroqLLM:
    def __init__(self, client, model="llama-3.1-8b-instant"):
        self.client = client
        self.model = model
    
    def complete(self, prompt):
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        
        class Response:
            def __init__(self, text):
                self.text = text
        
        return Response(completion.choices[0].message.content)

llm = GroqLLM(groq_client, model="llama-3.1-8b-instant")
print("✅ LLM (Groq Llama-3.1-8b-instant) listo.")

class CypherQueryEngine(BaseQueryEngine):
    def __init__(self, driver, database):
        self.driver = driver
        self.database = database
        super().__init__(callback_manager=CallbackManager())
    
    def _get_prompt_modules(self):
        return {}
    
    async def _aquery(self, query_bundle):
        return self._query(query_bundle)
    
    def _query_data(self, cypher_query: str, params: dict):
        with self.driver.session(database=self.database) as session:
            result = session.run(cypher_query, params).data()
        return result
    
    def _query(self, query_bundle):
        try:
            llm_params = json.loads(query_bundle.query)
        except json.JSONDecodeError:
            return json.dumps({"error": "JSON inválido"})
        
        carrera_input = llm_params.get("carrera", "").lower()
        certificados_input = llm_params.get("certificados")
        tamano_ciudad = llm_params.get("tamano_ciudad")
        region_europa = llm_params.get("region_europa")
        preferencia_clima = llm_params.get("preferencia_clima")
        
        if not carrera_input:
            return json.dumps({"error": "Falta carrera"})
    
        params = {"carrera_input": carrera_input}
        where_idioma_clause = []
    
        
        if certificados_input == "NO":
            where_idioma_clause.append("o.cert_obligatorio = 'NO'")
    
        
        elif isinstance(certificados_input, list) and certificados_input:
            opciones = ["o.cert_obligatorio = 'NO'"]
            for cert in certificados_input:
                user_idioma = normalizar_texto(cert.get('idioma', ''))
                if user_idioma:
                    opciones.append(
                        f"(o.cert_obligatorio = 'SI' AND toLower(o.nivel_requerido) CONTAINS '{user_idioma}')"
                    )
            where_idioma_clause.append('(' + ' OR '.join(opciones) + ')')
    
        filtro_idioma_final = " AND ".join(where_idioma_clause) if where_idioma_clause else "1=1"
    
    
        if tamano_ciudad == 'grande':
            puntos_ciudad = "CASE WHEN l.poblacion >= 156000 THEN 70 ELSE 0 END"
        elif tamano_ciudad == 'pequena':
            puntos_ciudad = "CASE WHEN l.poblacion < 156000 THEN 70 ELSE 0 END"
        else:
            puntos_ciudad = "0"
    
       
        if region_europa:
            puntos_region = f"CASE WHEN p.localizacion = '{region_europa}' THEN 70 ELSE 0 END"
        else:
            puntos_region = "0"
        
       
        if preferencia_clima == 'frio':
            puntos_clima = "CASE WHEN p.temp_media_anual < 11.4 THEN 50 ELSE 0 END"
        elif preferencia_clima == 'calor':
            puntos_clima = "CASE WHEN p.temp_media_anual >= 11.4 THEN 50 ELSE 0 END"
        else:
            puntos_clima = "0"
    
        query = f"""
            MATCH (c:Carrera {{nombre: $carrera_input}})
                -[o:OFERTA]->(u:Universidad)
            MATCH (u)-[:SITUADA_EN]->(l:Ciudad)-[:UBICADA_EN]->(p:Pais)
            WHERE toInteger(o.numero_de_plazas) > 0
              AND ({filtro_idioma_final})
            WITH u, o, p, l,
                ((toFloat(686 - u.ranking_uni)*0.1) + (u.exchange_score * 0.2) 
                 + ({puntos_ciudad}) + ({puntos_region}) + ({puntos_clima})) AS PuntuacionCompuesta
            RETURN DISTINCT u.nombre AS Universidad,
                   p.nombre AS Pais,
                   p.localizacion AS Localizacion_Pais,
                   p.temp_media_anual AS Temperatura_Media,
                   l.nombre AS Ciudad,
                   l.poblacion AS Poblacion,
                   o.numero_de_plazas AS Plazas_Disponibles,
                   o.duracion_de_estancia AS Duracion_Meses,
                   o.cert_obligatorio AS Certificado_Obligatorio,
                   o.nivel_requerido AS Nivel_Requerido,
                   PuntuacionCompuesta
            ORDER BY PuntuacionCompuesta DESC
        """
    
        resultados = self._query_data(query, params)
        
        if isinstance(certificados_input, list) and certificados_input:
            resultados_filtrados = []
            for uni in resultados:
                if uni.get('Certificado_Obligatorio') == 'NO':
                    resultados_filtrados.append(uni)
                    continue
    
                nivel_req = uni.get('Nivel_Requerido', '').strip().lower()
                matches = re.findall(r'([abc][12])\s+([a-z]+)', nivel_req)
    
                acepta = False
                for cert in certificados_input:
                    user_idioma = normalizar_texto(cert.get('idioma', ''))
                    user_nivel = cert.get('nivel', '').upper()
                    user_nivel_num = NIVEL_MAPA.get(user_nivel, 0)
                    for nivel_req_str, idioma_req in matches:
                        nivel_req_num = NIVEL_MAPA.get(nivel_req_str.upper(), 0)
                        if idioma_req == user_idioma and user_nivel_num >= nivel_req_num:
                            acepta = True
                            break
                    if acepta:
                        break
                if acepta:
                    resultados_filtrados.append(uni)
            resultados = resultados_filtrados
    
        return json.dumps(resultados, indent=2, ensure_ascii=False)



cypher_engine = CypherQueryEngine(driver=driver, database=DATABASE)
print("✅ Motor de búsqueda listo.\n")

class ErasmAIAssistant:
    def __init__(self, llm, cypher_engine):
        self.llm = llm
        self.cypher_engine = cypher_engine
        self.estado = "INICIO"
        self.carrera_neo4j = None
        self.carrera_display = None
        self.certificados = None
        self.tamano_ciudad = None
        self.region_europa = None 
        self.preferencia_clima = None
        self.destinos_filtrados = []
        self.preferencias = {} 
        
    def extraer_certificados(self, texto):
        """Extrae certificados del texto del usuario"""
        texto_lower = texto.lower()
        
        if "no" in texto_lower and ("tengo" in texto_lower or "certificado" in texto_lower):
            return "NO"
        if texto_lower.strip() == "no":
            return "NO"
        
        certificados = []
        idiomas = {
            'ingles': 'ingles', 'inglés': 'ingles', 'english': 'ingles',
            'frances': 'frances', 'francés': 'frances', 'french': 'frances',
            'aleman': 'aleman', 'alemán': 'aleman', 'german': 'aleman',
            'italiano': 'italiano', 'italian': 'italiano',
            'portugues': 'portugues', 'português': 'portugues', 'portuguese': 'portugues'
        }
        
        patron = r'([ABC][12])\s*(?:de\s+)?(\w+)'
        matches = re.findall(patron, texto, re.IGNORECASE)
        
        for nivel, idioma in matches:
            idioma_lower = idioma.lower()
            if idioma_lower in idiomas:
                certificados.append({
                    'idioma': idiomas[idioma_lower],
                    'nivel': nivel.upper()
                })
        
        return certificados if certificados else None
    
    def procesar_mensaje(self, user_input):
        if self.estado == "INICIO":
            self.estado = "CARRERA"
            return (
                "¡Hola! Soy **ErasmAI** 👋, el asistente diseñado para ayudarte a elegir tu destino Erasmus en la **Universidad de León**.\n\n"
                "Mi objetivo es encontrar tu lugar ideal:\n"
                "* Te haré preguntas clave sobre tus **preferencias** y **características personales**.\n"
                "* Juntos definiremos el **destino perfecto** para tu experiencia. 🎯\n\n"
                "Para iniciar el proceso, ¿me podrías indicar **qué carrera estudias**? 🎓"
            )
            
        elif self.estado == "CARRERA":
            carrera_neo4j, carrera_display = validar_carrera(user_input)
            
            if carrera_neo4j:
                self.carrera_neo4j = carrera_neo4j
                self.carrera_display = carrera_display
                self.estado = "CERTIFICADOS"
                return (
                    f"¡Genial! Veo que estudias **{carrera_display}**  ✅\n\n"
                    f"Ahora vamos con las **habilidades lingüísticas** . Dime, ¿cuentas con certificados de idioma?\n\n"
                    f"➡️ **Indica el Nivel y el Idioma:** (Ejemplo: `B2 de Inglés`, `B1 de Italiano`).\n\n"
                    f"➡️ **Si tienes varios, usa 'y':** (Ejemplo: `B1 Inglés y A1 Italiano`).\n\n"
                    f"➡️ **Si no tienes ninguno, escribe:** `NO`."
                )
            else:
                return (
                    "Lo siento, no he podido identificar tu carrera.\n\n"
                    "Algunas carreras disponibles son:\n"
                    "- Derecho, Medicina, Veterinaria\n"
                    "- Ingenierías (Informática, Industrial, Mecánica...)\n"
                    "- ADE, Economía, Marketing, Turismo\n"
                    "- Educación Infantil, Educación Primaria\n"
                    "- Biología, Biotecnología, Ciencias Ambientales\n"
                    "- Enfermería, Fisioterapia, Trabajo Social\n\n"
                    "¿Qué carrera estudias?"
                )
        
        elif self.estado == "CERTIFICADOS":
            certificados_detectados = self.extraer_certificados(user_input)
            
            if certificados_detectados == "NO":
                self.certificados = "NO"
                self.estado = "PREF_CIUDAD"
                return (
                    f"Perfecto. Ya sé que estudias {self.carrera_display} y que no cuentas con certificados de idioma.\n"
                    "Con esta información ya puedo reducir la lista de destinos disponibles.\n\n"
                    "Ahora te voy a hacer unas pocas preguntas para afinar al máximo mi recomendación "
                    "y elegir el destino que mejor se ajuste a ti.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "**Primera pregunta:** ¿Qué tipo de ciudad prefieres?\n\n"
                    "🏙️ **Ciudad grande:** Capitales o ciudades principales con más de 150.000 habitantes. "
                    "Más oportunidades culturales, vida nocturna activa, mejor conexión de transporte, "
                    "pero también más movimiento y ritmo acelerado.\n\n"
                    "🏘️ **Ciudad pequeña:** Localidades más tranquilas con menos de 150.000 habitantes. "
                    "Ambiente más acogedor, menor coste de vida, "
                    "pero con menos opciones de ocio y servicios.\n\n"
                    "Responde: **grande** o **pequeña**"
                )
            
            elif certificados_detectados:
                self.certificados = certificados_detectados
                self.estado = "PREF_CIUDAD" 
                certs_texto = ", ".join([f"{cert['nivel']} de {cert['idioma'].title()}" 
                                 for cert in certificados_detectados])
                return (
                    f"Excelente. Ya sé que estudias {self.carrera_display} y que cuentas con certificados de: {certs_texto}.\n"
                    "Con esta información ya puedo reducir significativamente la lista de destinos disponibles.\n\n"
                    "Ahora te voy a hacer unas pocas preguntas para afinar al máximo mi recomendación "
                    "y elegir el destino que mejor se ajuste a ti.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "**Primera pregunta:** ¿Qué tipo de ciudad prefieres?\n\n"
                    "🏙️ **Ciudad grande:** Capitales o ciudades principales con más de 150.000 habitantes. "
                    "Más oportunidades culturales, vida nocturna activa, mejor conexión de transporte, "
                    "pero también más movimiento y ritmo acelerado.\n\n"
                    "🏘️ **Ciudad pequeña:** Localidades más tranquilas con menos de 150.000 habitantes. "
                    "Ambiente más acogedor, menor coste de vida, más fácil integrarse, "
                    "pero con menos opciones de ocio y servicios.\n\n"
                    "Responde: **grande** o **pequeña**"
                )
            
            else:
                return (
                    "Lo siento, no he podido entender tus certificados de idioma.\n\n"
                    "Por favor, responde de una de estas formas:\n"
                    "- 'B2 de Inglés' o 'B2 Inglés'\n"
                    "- 'B2 de Inglés y B1 de Italiano'\n"
                    "- 'NO' si no tienes certificados\n\n"
                    "¿Qué certificados de idioma tienes?"
                )
        
        elif self.estado == "PREF_CIUDAD":
            tamano = user_input.lower().strip()
            
            if tamano in ['grande', 'grandes']:
                self.tamano_ciudad = 'grande'
                self.estado = "PREF_REGION"
            elif tamano in ['pequeña', 'pequena', 'pequeñas', 'pequenas', 'pequeño', 'pequeno']:
                self.tamano_ciudad = 'pequena'
                self.estado = "PREF_REGION"
            else:
                return "Por favor responde: 'grande' o 'pequeña'"
            
            return (
                "¡Genial! Ahora que sé tu preferencia de tamaño de ciudad, vamos a personalizar aún más tu destino.\n\n"
                "¿A qué parte de Europa preferías ir?\n\n"
                "🌍 **Opciones (responde una):**\n"
                "- **norte** de Europa (ej: Noruega, Suecia, Dinamarca)\n"
                "- **sur** de Europa (ej: Italia, Portugal, Grecia)\n"
                "- **este** de Europa (ej: Polonia, Hungría, Chequia, Rumanía)\n"
                "- **oeste** de Europa (ej: Francia, Alemania, Bélgica, Países Bajos)\n\n"
                "Responde: norte, sur, este o oeste"
            )
            
        elif self.estado == "PREF_REGION":
            region = user_input.lower().strip()
            
            regiones_validas = {
                'norte': 'norte de europa',
                'sur': 'sur de europa',
                'este': 'este de europa',
                'oeste': 'oeste de europa'
            }
            
            if region in regiones_validas:
                self.region_europa = regiones_validas[region]
                self.estado = "PREF_CLIMA"
                return (
                    "¡Perfecto! Ya tengo clara la región que prefieres.\n\n"
                    "**Última pregunta antes de buscar:** ¿Eres más de frío o de calor?\n\n"
                    "❄️ **Frío:** Destinos con temperatura media anual menor a 11.4°C "
                    "(ej: países nórdicos, zonas de montaña)\n\n"
                    "☀️ **Calor:** Destinos con temperatura media anual mayor a 11.4°C "
                    "(ej: países mediterráneos, sur de Europa)\n\n"
                    "Responde: **frio** o **calor**"
                )
            else:
                return (
                    "Por favor responde exactamente alguna de estas opciones: "
                    "'norte', 'sur', 'este' o 'oeste'.\n"
                    "Ejemplo: sur"
                )
        
        elif self.estado == "PREF_CLIMA":
            clima = user_input.lower().strip()
            
            if clima in ['frio', 'frío']:
                self.preferencia_clima = 'frio'
                self.estado = "BUSQUEDA"
                return self.realizar_busqueda()
            
            elif clima in ['calor']:
                self.preferencia_clima = 'calor'
                self.estado = "BUSQUEDA"
                return self.realizar_busqueda()
            
            else:
                return (
                    "Por favor responde: 'frio' o 'calor'\n\n"
                    "Ejemplo: calor"
                )
        

        elif self.estado == "RAG_DESCRIPCION":
            descripcion_usuario = user_input
            
            print("\n🤖 Analizando tu descripción...")
            
    
            intenciones = extraer_intenciones(descripcion_usuario)
            categorias_texto = formatear_categorias_para_prompt(intenciones['categorias_atractivos'])
            print(f"✅ Categorías: {categorias_texto}")
            

            candidatos_neo4j = buscar_destinos_por_intenciones(
                self.cypher_engine, 
                self.destinos_filtrados, 
                intenciones
            )
            
            if not candidatos_neo4j:
                self.estado = "FINALIZADO"
                return (
                    "😔 No encontré destinos que cumplan esas características.\n"
                    "Intenta con una descripción más flexible.\n\n"
                )
            
            candidatos_neo4j = ajustar_puntos_por_cantidad_atractivos(candidatos_neo4j, intenciones)
            
            candidatos_finales = enriquecer_con_puntuaciones(
                candidatos_neo4j, 
                self.destinos_filtrados
            )
            
            recomendacion = recomendar_con_llama(
               self.llm, 
               descripcion_usuario, 
               candidatos_finales, 
               intenciones,
               self.preferencias
            )
      
            self.estado = "FINALIZADO"
            return (
                f"\n{recomendacion}\n\n{'='*70}\n\n"
                f"🎉 ¡Recomendación Finalizada! 🎉\n\n"
                f"---"
                f"Espero que esta sugerencia se ajuste a lo que buscabas. Si deseas explorar otras opciones, "
                f"puedes reiniciar la conversación pulsando el botón **'Reiniciar conversación'** en el menú lateral. ¡Mucha suerte! 🍀"
            )

        return (
            "La recomendación ya ha sido realizada. Si deseas explorar otras opciones, "
            "puedes reiniciar la conversación pulsando el botón **'Reiniciar conversación'** en el menú lateral."
        )
    
    def realizar_busqueda(self):
        print("\n🔍 Buscando destinos en la base de datos...")
        
        self.preferencias = {
            'Idioma': f"{self.certificados}" if self.certificados != "NO" else "Sin certificados",
            'Clima': self.preferencia_clima.title() if self.preferencia_clima else "No especificado",
            'Region': self.region_europa.replace('de europa', 'de Europa') if self.region_europa else "No especificada",
            'TamanoCiudad': 'Grande (>150k hab.)' if self.tamano_ciudad == 'grande' else 'Pequeña (<150k hab.)' if self.tamano_ciudad else "No especificado"
        }
        
        query_json = {
            "carrera": self.carrera_neo4j,
            "certificados": self.certificados,
            "tamano_ciudad": self.tamano_ciudad,
            "region_europa": self.region_europa,
            "preferencia_clima": self.preferencia_clima
        }
        
        class FakeQueryBundle:
            def __init__(self, query):
                self.query = query
        
        query_bundle = FakeQueryBundle(json.dumps(query_json))
        resultado_json = self.cypher_engine._query(query_bundle)
        
        try:
            resultados = json.loads(resultado_json)
        except Exception as e:
            return f"❌ Error al procesar resultados: {str(e)}"
        
        if not resultados:
            return (
                f"😔 Lo siento, no he encontrado destinos Erasmus para {self.carrera_display} "
                f"con tus requisitos.\n\n"
                "Te recomiendo contactar con la oficina de Relaciones Internacionales."
            )
        
        self.destinos_filtrados = resultados
        
        num_total = len(resultados)
        mostrar = resultados[:5] if num_total > 5 else resultados
        
        respuesta = f"\n🎉 ¡Excelente! He encontrado {num_total} destinos en tu carrera y que se ajustan a tus características.\n\n"
        if num_total > 5:
            respuesta += "Aquí te muestro 5 ejemplos que se ajustan a lo que buscas:\n\n"
        else:
            respuesta += "\n"
        
        respuesta += "🏆 TOP DESTINOS:\n"
        respuesta += "=" * 70 + "\n\n"
        
        for i, dest in enumerate(mostrar, 1):
            pob = f"{dest['Poblacion']:,}".replace(',', '.')
            temp = dest.get('Temperatura_Media', 'N/A')
            respuesta += f"{i}. 🎓 **{dest['Universidad']}**\n\n"
            respuesta += f"   📍 {dest['Ciudad']} ({pob} hab.), {dest['Pais']}\n\n"
            respuesta += f"   🌍 Región: {dest.get('Localizacion_Pais', 'N/A').replace('de europa', 'de Europa')}\n\n"
            respuesta += f"   🌡️ Temperatura media: {temp}°C\n"
        
        respuesta += "=" * 70 + "\n\n"
        
        self.estado = "RAG_DESCRIPCION"
        respuesta += (
            "Ahora descríbeme libremente qué tipo de experiencia buscas en tu destino Erasmus.\n\n"
            "**Ejemplos:**\n"
            "- 'Quiero un destino con mucha vida nocturna, aventuras y que sea económico'\n"
            "- 'Busco un lugar tranquilo con naturaleza, historia y buena gastronomía'\n"
            "- 'Me gustaría playas, castillos medievales y ambiente joven'\n\n"
            "📝 **Tu descripción:**"
        )
        
        return respuesta




def cli_loop():
    assistant = ErasmAIAssistant(llm, cypher_engine)
    print("=" * 70)
    print("  🎓 ERASMAI - ASISTENTE DE RECOMENDACIÓN ERASMUS 🌍")
    print("     Universidad de León")
    print("=" * 70)
    print("\nComandos: Ctrl+C para salir\n")

    print(f"🤖 ErasmAI: {assistant.procesar_mensaje('')}\n")

    while True:
        try:
            user_input = input("👤 Tú: ").strip()
            if not user_input:
                continue
            respuesta = assistant.procesar_mensaje(user_input)
            print(f"\n🤖 ErasmAI: {respuesta}\n")
            print("-" * 70)
            print()
        except KeyboardInterrupt:
            print("\n\n⚠️ Interrumpido")
            break
        except Exception as e:
            print(f"\n❌ ERROR: {e}\n")
            import traceback
            traceback.print_exc()
    driver.close()
    print("\n✅ Sesión cerrada. ¡Gracias por usar ErasmAI!\n")

if __name__ == "__main__":
    cli_loop()

