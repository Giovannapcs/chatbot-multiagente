#!/usr/bin/env python3
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
    cursor_factory=RealDictCursor
)

cur = conn.cursor()

print("\n=== Verificando tabelas de reconhecimento ===")
cur.execute("""
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name ILIKE '%ack%'
ORDER BY table_name
""")
for row in cur.fetchall():
    print(row)

print("\n=== Colunas da tabela acknowledges ===")
cur.execute("""
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'acknowledges'
ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(row)

print("\n=== Amostra de acknowledges ===")
try:
    cur.execute("""
    SELECT *
    FROM acknowledges
    ORDER BY clock DESC
    LIMIT 10
    """)
    for row in cur.fetchall():
        print(row)
except Exception as e:
    print("Erro ao consultar acknowledges:", e)

cur.close()
conn.close()
