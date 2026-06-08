#!/usr/bin/env python3
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
import json

load_dotenv("config.env")

def main():
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
    )

    relatorio = {}

    with driver.session() as session:
        print("=" * 50)
        print("CONSULTA NEO4J EM JSON")
        print("=" * 50)

        # Total de hosts
        result = session.run("MATCH (h:Host) RETURN count(h) AS total")
        relatorio["total_hosts"] = result.single()["total"]

        # Total de triggers
        result = session.run("MATCH (t:Trigger) RETURN count(t) AS total")
        relatorio["total_triggers"] = result.single()["total"]

        # Total de eventos
        result = session.run("MATCH (e:Evento) RETURN count(e) AS total")
        relatorio["total_eventos"] = result.single()["total"]

        # Lista de 5 hosts
        result = session.run("""
            MATCH (h:Host)
            RETURN DISTINCT h.host AS host
            ORDER BY host
            LIMIT 5
        """)
        relatorio["hosts"] = [record["host"] for record in result]

        # Top 5 hosts com mais eventos
        result = session.run("""
            MATCH (h:Host)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU]->(e:Evento)
            RETURN h.host AS host, COUNT(e) AS total_eventos
            ORDER BY total_eventos DESC
            LIMIT 5
        """)
        relatorio["top_hosts_eventos"] = [
            {
                "host": record["host"],
                "total_eventos": record["total_eventos"]
            }
            for record in result
        ]

    driver.close()

    print(json.dumps(relatorio, indent=2, ensure_ascii=False))
    print("\nConsulta finalizada com sucesso.")

if __name__ == "__main__":
    main()
