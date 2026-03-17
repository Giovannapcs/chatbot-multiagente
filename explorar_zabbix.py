#!/usr/bin/env python3
import os, psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv("config.env")

conn = psycopg2.connect(
    host=os.getenv("ZABBIX_DB_HOST"),
    port=int(os.getenv("ZABBIX_DB_PORT","5432")),
    dbname=os.getenv("ZABBIX_DB_NAME"),
    user=os.getenv("ZABBIX_DB_USER"),
    password=os.getenv("ZABBIX_DB_PASS"),
)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("="*55)
print("MAPEAMENTO DO AMBIENTE ZABBIX")
print("="*55)

cur.execute("SELECT COUNT(*) FILTER (WHERE status=0) AS ativos, COUNT(*) FILTER (WHERE status=1) AS inativos FROM hosts WHERE flags=0")
r = cur.fetchone()
print(f"HOSTS: {r['ativos']} ativos | {r['inativos']} inativos")
conn.close()
