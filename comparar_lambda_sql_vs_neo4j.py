import os
import psycopg2
from neo4j import GraphDatabase
from dotenv import load_dotenv

# CARREGA CONFIGURAÇÕES

load_dotenv("config.env")

POSTGRES = {
    "host": os.getenv("ZABBIX_DB_HOST"),
    "port": int(os.getenv("ZABBIX_DB_PORT", 5432)),
    "database": os.getenv("ZABBIX_DB_NAME"),
    "user": os.getenv("ZABBIX_DB_USER"),
    "password": os.getenv("ZABBIX_DB_PASS"),
    "sslmode": os.getenv("ZABBIX_DB_SSLMODE", "prefer")
}

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASS")

# CONSULTAS SQL

SQL_QUERIES = {

    "hosts_total": """
        SELECT COUNT(DISTINCT hostid)
        FROM hosts
        WHERE status = 0;
    """,

    "triggers_total": """
        SELECT COUNT(*)
        FROM triggers;
    """,

    "incidentes_totais_7d": """
        SELECT COUNT(*)
        FROM events
        WHERE value = 1
        AND clock >= EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days');
    """,

    "incidentes_reconhecidos_7d": """
        SELECT COUNT(DISTINCT e.eventid)
        FROM events e
        INNER JOIN acknowledges a
            ON a.eventid = e.eventid
        WHERE e.value = 1
        AND e.clock >= EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days');
    """,

    "incidentes_ativos_7d": """
        SELECT COUNT(*)
        FROM events
        WHERE value = 1
        AND (
            r_eventid IS NULL
            OR r_eventid = 0
        )
        AND clock >= EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days');
    """,

    "dias_com_incidentes": """
        SELECT COUNT(*)
        FROM (
            SELECT DATE(TO_TIMESTAMP(clock))
            FROM events
            WHERE value = 1
            AND clock >= EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days')
            GROUP BY DATE(TO_TIMESTAMP(clock))
        ) x;
    """
}

# CONSULTAS CYPHER

CYPHER_QUERIES = {

    "hosts_total": """
        MATCH (h:Host)
        WHERE coalesce(h.removido,false)=false
        RETURN count(DISTINCT h) AS total
    """,

    "triggers_total": """
        MATCH (t:Trigger)
        RETURN count(DISTINCT t) AS total
    """,

    "incidentes_totais_7d": """
        MATCH (e:Evento)
        WHERE toInteger(e.value)=1
        AND toInteger(e.clock) >= toInteger(timestamp()/1000)-604800
        RETURN count(e) AS total
    """,

    "incidentes_reconhecidos_7d": """
        MATCH (e:Evento)
        WHERE toInteger(e.value)=1
        AND (
            coalesce(toInteger(e.acknowledged),0)=1
            OR coalesce(toInteger(e.ack),0)=1
            OR coalesce(toInteger(e.reconhecido),0)=1
        )
        RETURN count(DISTINCT e) AS total
    """,

    "incidentes_ativos_7d": """
        MATCH (e:Evento)
        WHERE toInteger(e.value)=1
        AND (
            e.r_eventid IS NULL
            OR toString(e.r_eventid)="0"
            OR toString(e.r_eventid)=""
        )
        RETURN count(e) AS total
    """,

    "dias_com_incidentes": """
        MATCH (e:Evento)
        WHERE toInteger(e.value)=1
        AND toInteger(e.clock) >= toInteger(timestamp()/1000)-604800
        WITH date(datetime({epochSeconds:toInteger(e.clock)})) AS dia
        RETURN count(DISTINCT dia) AS total
    """
}

# EXECUTA SQL

def executar_sql():

    print("\nConectando PostgreSQL...")

    conn = psycopg2.connect(**POSTGRES)

    cur = conn.cursor()

    resultados = {}

    for nome, query in SQL_QUERIES.items():

        cur.execute(query)

        valor = cur.fetchone()[0]

        resultados[nome] = valor

    cur.close()
    conn.close()

    return resultados

# EXECUTA NEO4J

def executar_neo4j():

    print("Conectando Neo4j...")

    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASS)
    )

    resultados = {}

    with driver.session() as session:

        for nome, query in CYPHER_QUERIES.items():

            record = session.run(query).single()

            resultados[nome] = record["total"]

    driver.close()

    return resultados

# MAIN

def main():

    print("\n" + "=" * 80)
    print("VALIDAÇÃO SQL x NEO4J")
    print("=" * 80)

    print("\nCONFIGURAÇÃO")
    print("-" * 80)
    print(f"Postgres Host : {POSTGRES['host']}")
    print(f"Postgres DB   : {POSTGRES['database']}")
    print(f"Postgres User : {POSTGRES['user']}")
    print(f"Neo4j URI     : {NEO4J_URI}")
    print("-" * 80)

    try:
        sql = executar_sql()
    except Exception as e:
        print("\nERRO AO CONECTAR NO POSTGRES")
        print(str(e))
        return

    try:
        neo = executar_neo4j()
    except Exception as e:
        print("\nERRO AO CONECTAR NO NEO4J")
        print(str(e))
        return

    divergencias = 0

    print("\nRESULTADOS")
    print("=" * 80)

    for chave in sql.keys():

        sql_valor = sql[chave]
        neo_valor = neo.get(chave)

        status = "OK"

        if sql_valor != neo_valor:
            status = "DIVERGENTE"
            divergencias += 1

        print(f"\n{chave}")
        print(f"  SQL   : {sql_valor}")
        print(f"  Neo4j : {neo_valor}")
        print(f"  Status: {status}")

    print("\n" + "=" * 80)

    if divergencias == 0:
        print("RESULTADO FINAL: TUDO CONSISTENTE")
    else:
        print(f"RESULTADO FINAL: {divergencias} DIVERGÊNCIA(S) ENCONTRADA(S)")

    print("=" * 80)

# =====================================================

if __name__ == "__main__":
    main()
