#!/usr/bin/env python3
"""importar_zabbix_neo4j.py — Importa dados do Zabbix (PostgreSQL) para o Neo4j"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv("config.env")

# ── Conexões ──────────────────────────────────────────────────────────────────
pg = psycopg2.connect(
    host=os.getenv("ZABBIX_DB_HOST"),
    port=int(os.getenv("ZABBIX_DB_PORT", "5432")),
    dbname=os.getenv("ZABBIX_DB_NAME"),
    user=os.getenv("ZABBIX_DB_USER"),
    password=os.getenv("ZABBIX_DB_PASS"),
    cursor_factory=RealDictCursor
)
neo = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
)

cur = pg.cursor()

def run(session, query, batch):
    if batch:
        session.run(query, rows=batch)

# ── 1. GRUPOS ─────────────────────────────────────────────────────────────────
print("\n[1/5] Importando Grupos...")
cur.execute("SELECT groupid, name FROM hstgrp WHERE flags = 0")
grupos = list(cur.fetchall())
with neo.session() as s:
    s.run("""
        UNWIND $rows AS r
        MERGE (g:Grupo {groupid: toString(r.groupid)})
        SET g.name = r.name
    """, rows=[dict(r) for r in grupos])
print(f"  OK: {len(grupos)} grupos")

# ── 2. HOSTS ──────────────────────────────────────────────────────────────────
print("\n[2/5] Importando Hosts...")
cur.execute("""
    SELECT h.hostid, h.host, h.name, h.status, h.flags
    FROM hosts h
    WHERE h.flags = 0 AND h.status IN (0, 1)
""")
hosts = list(cur.fetchall())
with neo.session() as s:
    s.run("""
        UNWIND $rows AS r
        MERGE (h:Host {hostid: toString(r.hostid)})
        SET h.host   = r.host,
            h.name   = r.name,
            h.status = r.status
    """, rows=[dict(r) for r in hosts])
print(f"  OK: {len(hosts)} hosts")

# ── 3. HOST → GRUPO ───────────────────────────────────────────────────────────
print("\n[3/5] Criando relacionamentos Host → Grupo...")
cur.execute("""
    SELECT hg.hostid, hg.groupid
    FROM hosts_groups hg
    JOIN hosts h ON h.hostid = hg.hostid
    WHERE h.flags = 0 AND h.status IN (0, 1)
""")
rels = list(cur.fetchall())
with neo.session() as s:
    s.run("""
        UNWIND $rows AS r
        MATCH (h:Host  {hostid:  toString(r.hostid)})
        MATCH (g:Grupo {groupid: toString(r.groupid)})
        MERGE (h)-[:PERTENCE_A]->(g)
    """, rows=[dict(r) for r in rels])
print(f"  OK: {len(rels)} relacionamentos")

# ── 4. INTERFACES ─────────────────────────────────────────────────────────────
print("\n[4/5] Importando Interfaces...")
cur.execute("""
    SELECT i.interfaceid, i.hostid, i.ip, i.dns, i.port, i.type, i.main
    FROM interface i
    JOIN hosts h ON h.hostid = i.hostid
    WHERE h.flags = 0 AND h.status IN (0, 1)
""")
ifaces = list(cur.fetchall())
with neo.session() as s:
    s.run("""
        UNWIND $rows AS r
        MERGE (n:Interface {interfaceid: toString(r.interfaceid)})
        SET n.ip   = r.ip,
            n.dns  = r.dns,
            n.port = r.port,
            n.type = r.type,
            n.main = r.main
        WITH n, r
        MATCH (h:Host {hostid: toString(r.hostid)})
        MERGE (h)-[:TEM]->(n)
    """, rows=[dict(r) for r in ifaces])
print(f"  OK: {len(ifaces)} interfaces")

# ── 5. TAGS DOS HOSTS ─────────────────────────────────────────────────────────
print("\n[5/5] Importando Tags dos Hosts...")
cur.execute("""
    SELECT ht.hostid, ht.tag, ht.value
    FROM host_tag ht
    JOIN hosts h ON h.hostid = ht.hostid
    WHERE h.flags = 0 AND h.status IN (0, 1)
""")
tags = list(cur.fetchall())
with neo.session() as s:
    s.run("""
        UNWIND $rows AS r
        MATCH (h:Host {hostid: toString(r.hostid)})
        SET h[$r.tag] = r.value
    """, rows=[dict(r) for r in tags])
print(f"  OK: {len(tags)} tags aplicadas nos hosts")

# ── RESUMO ────────────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("Importação concluída! Resumo no Neo4j:")
with neo.session() as s:
    for label in ["Host", "Grupo", "Interface"]:
        r = s.run(f"MATCH (n:{label}) RETURN count(n) AS total").single()
        print(f"  :{label:12s} → {r['total']} nós")
    r = s.run("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY c DESC")
    for rec in r:
        print(f"  [{rec['t']:20s}] → {rec['c']} relacionamentos")
print("="*55)

cur.close()
pg.close()
neo.close()
