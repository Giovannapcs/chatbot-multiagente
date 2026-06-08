from dotenv import load_dotenv
import os
import psycopg2

load_dotenv("config.env")

conn = psycopg2.connect(
    host=os.getenv("ZABBIX_DB_HOST"),
    port=os.getenv("ZABBIX_DB_PORT"),
    database=os.getenv("ZABBIX_DB_NAME"),
    user=os.getenv("ZABBIX_DB_USER"),
    password=os.getenv("ZABBIX_DB_PASS"),
    sslmode=os.getenv("ZABBIX_DB_SSLMODE")
)

cur = conn.cursor()

print("\nCOLUNAS DA TABELA EVENTS\n")

cur.execute("""
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name='events'
ORDER BY ordinal_position
""")

for coluna, tipo in cur.fetchall():
    print(f"{coluna:<30} {tipo}")

print("\nTABELAS COM PROBLEM / EVENT\n")

cur.execute("""
SELECT table_name
FROM information_schema.tables
WHERE table_schema='public'
AND (
    table_name LIKE '%event%'
    OR table_name LIKE '%problem%'
    OR table_name LIKE '%ack%'
)
ORDER BY table_name
""")

for row in cur.fetchall():
    print(row[0])

cur.close()
conn.close()
