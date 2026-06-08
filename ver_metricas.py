#!/usr/bin/env python3
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv("config.env")

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
)

queries = {
    "Total de métricas": """
        MATCH (m:Metrica)
        RETURN count(m) AS total
    """,

    "Tipos de métricas": """
        MATCH (m:Metrica)
        RETURN m.tipo AS tipo, count(m) AS total
        ORDER BY total DESC
    """,

    "Amostra de métricas": """
        MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica)
        RETURN 
            h.host AS host,
            m.tipo AS tipo,
            m.value AS valor,
            m.clock AS clock,
            m.timestamp AS timestamp
        ORDER BY m.clock DESC
        LIMIT 20
    """,

    "Itens que geram métricas": """
        MATCH (i:Item)-[:TEM_VALOR]->(m:Metrica)
        RETURN 
            i.name AS item,
            i.key_ AS chave,
            i.units AS unidade,
            m.tipo AS tipo,
            count(m) AS total
        ORDER BY total DESC
        LIMIT 20
    """
}

with driver.session() as session:
    for titulo, query in queries.items():
        print("\n" + "=" * 70)
        print(titulo)
        print("=" * 70)

        result = session.run(query)
        for row in result:
            print(dict(row))

driver.close()
