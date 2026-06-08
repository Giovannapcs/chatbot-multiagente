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

cur.execute("""
SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name='problem'
ORDER BY ordinal_position
""")

for coluna, tipo in cur.fetchall():
    print(f"{coluna:<30} {tipo}")

cur.close()
conn.close()
