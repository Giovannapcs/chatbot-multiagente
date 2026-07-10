#!/usr/bin/env python3
"""
Script de diagnostico rapido do ambiente Zabbix.
Exibe um resumo dos hosts, triggers e problemas ativos.
Execute: python3 explorar_zabbix.py
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv("config.env")

conn = psycopg2.connect(
    host=os.getenv("ZABBIX_DB_HOST"),
    port=int(os.getenv("ZABBIX_DB_PORT", "5432")),
    dbname=os.getenv("ZABBIX_DB_NAME"),
    user=os.getenv("ZABBIX_DB_USER"),
    password=os.getenv("ZABBIX_DB_PASS"),
    sslmode=os.getenv("ZABBIX_DB_SSLMODE", "prefer"),
)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 55)
print("RESUMO DO AMBIENTE ZABBIX")
print("=" * 55)

# Hosts ativos e inativos
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE status=0) AS ativos,
        COUNT(*) FILTER (WHERE status=1) AS inativos
    FROM hosts WHERE flags=0
""")
r = cur.fetchone()
print(f"HOSTS: {r['ativos']} ativos | {r['inativos']} inativos")

# Triggers ativas
cur.execute("SELECT COUNT(*) AS total FROM triggers WHERE status=0 AND flags=0")
r = cur.fetchone()
print(f"TRIGGERS ativas: {r['total']}")

# Problems em aberto por severidade
cur.execute("""
    SELECT severity, COUNT(*) AS total
    FROM problem WHERE source=0
    GROUP BY severity ORDER BY severity DESC
""")
sev = {0:"NC", 1:"Info", 2:"Aviso", 3:"Medio", 4:"Alto", 5:"Desastre"}
print("PROBLEMS abertos:")
for row in cur.fetchall():
    print(f"  {sev.get(row['severity'], '?'):10s}: {row['total']}")

# ACKs registrados
cur.execute("SELECT COUNT(*) AS total FROM acknowledges")
r = cur.fetchone()
print(f"ACKNOWLEDGEMENTS: {r['total']}")

cur.close()
conn.close()
