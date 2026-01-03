# 🗄️ Configuración de la Base de Datos Neo4j

Este documento explica cómo crear desde cero la base de datos usada por ErasmAI y contiene **todas las queries Cypher necesarias**, en el orden en que deben ejecutarse.

---

## 1️⃣ Preparación inicial

1. Crear una base de datos nueva y vacía en Neo4j.
2. Copiar los CSV de la carpeta `data/` del proyecto a la carpeta `import` de Neo4j.  
   Ejemplo en Windows:  
   `C:\Neo4j\relate-data\dbmss\neo4j\<tu_instancia>\import\`

   Archivos necesarios:
   - `datasetSibi.csv`
   - `añadirCosas.csv`
   - `atractivos_FINALES.csv`

3. Abrir **Neo4j Browser** y ejecutar, en orden, los bloques de este archivo:
   1. Restricciones únicas
   2. Creación de nodos base
   3. Creación de relaciones
   4. Limpieza (si hace falta)
   5. Enriquecimiento de países
   6. Creación de atractivos

---

## 2️⃣ Creación de restricciones únicas

```cypher
// Nodo: Carrera
CREATE CONSTRAINT ON (c:Carrera) ASSERT c.nombre IS UNIQUE;

// Nodo: Universidad
CREATE CONSTRAINT ON (u:Universidad) ASSERT u.nombre IS UNIQUE;

// Nodo: País
CREATE CONSTRAINT ON (p:Pais) ASSERT p.nombre IS UNIQUE;

// Nodo: Ciudad
CREATE CONSTRAINT ON (l:Ciudad) ASSERT l.nombre IS UNIQUE;

// Nodo: Nivel_de_Idioma
CREATE CONSTRAINT ON (i:Nivel_de_Idioma) ASSERT i.nombre IS UNIQUE;

// NUEVO: Nodo Atractivo
CREATE CONSTRAINT ON (a:Atractivo) ASSERT a.nombre IS UNIQUE;
```

---

## 3️⃣ Bloque A: creación de nodos estandarizados

```cypher
// -- Bloque A: CREACIÓN DE NODOS ESTANDARIZADOS --
LOAD CSV WITH HEADERS FROM 'file:///datasetSibi.csv' AS row

WITH row,
    trim(toLower(row.carrera)) AS carrera_std,
    trim(toLower(row.universidad_destino)) AS universidad_std,
    trim(toLower(row.pais_destino)) AS pais_std,
    trim(toLower(row.ciudad_destino)) AS ciudad_std,
    [s IN split(row.nivel_idioma, ' o ') | trim(toLower(s))] AS idiomas_std

// 1. Carrera
MERGE (c:Carrera {nombre: carrera_std})

// 2. Universidad
MERGE (u:Universidad {nombre: universidad_std})
SET u.ranking_uni = toInteger(row.ranking_uni),
    u.exchange_score = toFloat(row.exchange_score)

// 3. País
MERGE (p:Pais {nombre: pais_std})

// 4. Ciudad
MERGE (l:Ciudad {nombre: ciudad_std})

// 5. Niveles de idioma
WITH row, idiomas_std
UNWIND idiomas_std AS idioma
MERGE (i:Nivel_de_Idioma {nombre: idioma})

RETURN count(row) AS total_nodos_creados;
```

---

## 4️⃣ Bloque B: creación de todas las relaciones

```cypher
// -- Bloque B: CREACIÓN DE TODAS LAS RELACIONES --
LOAD CSV WITH HEADERS FROM 'file:///datasetSibi.csv' AS row

WITH row, 
     toInteger(row.plazas) AS plazas_int, 
     toInteger(row.meses) AS meses_int, 
     [s IN split(row.nivel_idioma, ' o ') | trim(toLower(s))] AS idiomas_split,
     trim(toLower(row.carrera)) AS carrera_std,
     trim(toLower(row.universidad_destino)) AS universidad_std,
     trim(toLower(row.pais_destino)) AS pais_std,
     trim(toLower(row.ciudad_destino)) AS ciudad_std

// 1. Ciudad -> País
MATCH (l:Ciudad {nombre: ciudad_std})
MATCH (p:Pais {nombre: pais_std})
MERGE (l)-[:UBICADA_EN]->(p)
WITH row, plazas_int, meses_int, idiomas_split, carrera_std, universidad_std, ciudad_std, pais_std

// 2. Universidad -> Ciudad
MATCH (u:Universidad {nombre: universidad_std})
MATCH (l:Ciudad {nombre: ciudad_std})
MERGE (u)-[:SITUADA_EN]->(l)
WITH row, plazas_int, meses_int, idiomas_split, carrera_std, universidad_std, ciudad_std, pais_std

// 3. Carrera -> Universidad (OFERTA)
MATCH (c:Carrera {nombre: carrera_std})
MATCH (u:Universidad {nombre: universidad_std})
MERGE (c)-[:OFERTA {
    numero_de_plazas: plazas_int,
    duracion_de_estancia: meses_int
}]->(u)
WITH row, plazas_int, meses_int, idiomas_split, carrera_std, universidad_std, ciudad_std, pais_std

// 4. Universidad -> Nivel_de_Idioma (REQUIERE_IDIOMA)
UNWIND idiomas_split AS idioma
MATCH (u:Universidad {nombre: universidad_std})
MATCH (i:Nivel_de_Idioma {nombre: idioma})
MERGE (u)-[:REQUIERE_IDIOMA {
    Certificado_Requerido: row.cert_idioma
}]->(i)

RETURN count(row) AS total_relaciones_creadas;
```

---

## 5️⃣ (Opcional) Limpieza de datos por conflicto

```cypher
// 1. Eliminar relaciones REQUIERE_IDIOMA
MATCH ()-[r:REQUIERE_IDIOMA]->() DELETE r;

// 2. Eliminar nodos de idioma
MATCH (i:Nivel_de_Idioma) DETACH DELETE i;

// 3. Eliminar restricción obsoleta (si hace falta)
DROP CONSTRAINT ON (i:Nivel_de_Idioma) ASSERT i.nombre IS UNIQUE;
```

---

## 6️⃣ Actualización de relaciones existentes (idioma en OFERTA)

```cypher
LOAD CSV WITH HEADERS FROM 'file:///datasetSibi.csv' AS row

WITH row,
     trim(toLower(row.carrera)) AS carrera_std,
     trim(toLower(row.universidad_destino)) AS universidad_std,
     trim(row.cert_idioma) AS cert_req,
     trim(row.nivel_idioma) AS nivel_req

MATCH (c:Carrera {nombre: carrera_std})-[o:OFERTA]->(u:Universidad {nombre: universidad_std})

SET o.cert_obligatorio = cert_req,
    o.nivel_requerido = nivel_req

RETURN count(o) AS total_ofertas_actualizadas;
```

---

## 7️⃣ Bloque C.1: enriquecimiento de nodos País (`añadirCosas.csv`)

```cypher
LOAD CSV WITH HEADERS FROM 'file:///añadirCosas.csv' AS row

WITH 
    trim(toLower(row.pais_destino)) AS pais_std,
    trim(toLower(row.localizacion_pais)) AS localizacion_val,
    trim(row.moneda) AS moneda_val,
    trim(row.capital) AS capital_val,
    trim(row.coste_vida) AS coste_val,
    trim(row.comidas_tipicas) AS comidas_val,
    trim(row.ambiente_fiesta) AS fiesta_val,
    toFloat(row.temp_med) AS temp_val,
    toFloat(row.edad_media) AS edad_val,
    toInteger(row.poblacion) AS poblacion_val 

MATCH (p:Pais {nombre: pais_std})

SET p.localizacion = localizacion_val,
    p.moneda = moneda_val,
    p.capital = capital_val,
    p.coste_vida = coste_val,
    p.comidas_tipicas = comidas_val,
    p.ambiente_fiesta = fiesta_val, 
    p.poblacion_total = poblacion_val, 
    p.temp_media_anual = temp_val, 
    p.edad_media = edad_val

RETURN count(p) AS total_paises_actualizados;
```

---

## 8️⃣ Bloque C.2: corrección Turquía + atractivos turísticos

```cypher
// 1. Renombrar 'turquía' -> 'turquia'
MATCH (p:Pais {nombre: 'turquía'})
SET p.nombre = 'turquia'
RETURN p AS Pais_Renombrado;
```

```cypher
// 2. Crear nodos :Atractivo y relación :TIENE_ATRACTIVO
LOAD CSV WITH HEADERS FROM 'file:///atractivos_FINALES.csv' AS row

WITH row,
     trim(toLower(row.pais_destino)) AS pais_std,
     trim(row.Atraccion) AS atractivo_nombre_val,
     toInteger(row.turistas_anuales) AS visitantes_val,
     toFloat(row.rating) AS rating_val,
     split(toLower(row.categoria), ',') AS categorias_raw 

WITH row, pais_std, atractivo_nombre_val, visitantes_val, rating_val, 
     [c IN categorias_raw | trim(replace(c, '"', ''))] AS categorias_list

MATCH (p:Pais {nombre: pais_std})

MERGE (a:Atractivo {nombre: atractivo_nombre_val})

SET a.visitantes_anuales = visitantes_val,
    a.mejor_estacion = trim(row.mejor_estacion),
    a.rating = rating_val,
    a.categorias = categorias_list,
    a.descripcion = trim(row.descripcion) 

MERGE (p)-[:TIENE_ATRACTIVO]->(a)

RETURN count(a) AS Total_Atractivos_Creados_o_Actualizados;
```

