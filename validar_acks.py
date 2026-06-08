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

print("\nPROBLEM\n")

cur.execute("""
SELECT
    COUNT(*) total,
    SUM(CASE WHEN acknowledged = 1 THEN 1 ELSE 0 END) reconhecidos,
    SUM(CASE WHEN r_eventid IS NULL THEN 1 ELSE 0 END) ativos,
    SUM(CASE WHEN r_eventid IS NOT NULL THEN 1 ELSE 0 END) resolvidos
FROM problem
""")

row = cur.fetchone()

print("Total       :", row[0])
print("Reconhecidos:", row[1])
print("Ativos      :", row[2])
print("Resolvidos  :", row[3])

print("\nACKNOWLEDGES\n")

cur.execute("""
SELECT COUNT(*)
FROM acknowledges
""")

print("Total ACKs:", cur.fetchone()[0])

cur.close()
conn.close()
