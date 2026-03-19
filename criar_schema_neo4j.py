#!/usr/bin/env python3
"""criar_schema_neo4j.py — Schema otimizado para Zabbix 7.x"""
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv("config.env")

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
)

comandos = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (h:Host)      REQUIRE h.hostid    IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (g:Grupo)     REQUIRE g.groupid   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Item)      REQUIRE i.itemid    IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Trigger)   REQUIRE t.triggerid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Evento)    REQUIRE e.eventid   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Interface) REQUIRE n.interfaceid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Metrica)   REQUIRE m.id        IS UNIQUE",
    "CREATE INDEX IF NOT EXISTS FOR (h:Host)     ON (h.status)",
    "CREATE INDEX IF NOT EXISTS FOR (h:Host)     ON (h.host)",
    "CREATE INDEX IF NOT EXISTS FOR (h:Host)     ON (h.ip)",
    "CREATE INDEX IF NOT EXISTS FOR (i:Item)     ON (i.key_)",
    "CREATE INDEX IF NOT EXISTS FOR (i:Item)     ON (i.value_type)",
    "CREATE INDEX IF NOT EXISTS FOR (t:Trigger)  ON (t.value)",
    "CREATE INDEX IF NOT EXISTS FOR (t:Trigger)  ON (t.priority)",
    "CREATE INDEX IF NOT EXISTS FOR (e:Evento)   ON (e.severity)",
    "CREATE INDEX IF NOT EXISTS FOR (e:Evento)   ON (e.clock)",
    "CREATE INDEX IF NOT EXISTS FOR (m:Metrica)  ON (m.clock)",
    "CREATE INDEX IF NOT EXISTS FOR (g:Grupo)    ON (g.name)",
]

def extrair_nome(cmd):
    partes = cmd.split("(")
    if "CONSTRAINT" in cmd:
        try:
            no = partes[1].split(")")[0].strip()
            propriedade = cmd.split("REQUIRE")[1].strip()
            return f"{no} → {propriedade}"
        except IndexError:
            return cmd[:60]
    else:
        try:
            no = partes[1].split(")")[0].strip()
            campo = partes[2].split(")")[0].strip()
            return f"{no} → {campo}"
        except IndexError:
            return cmd[:60]

print("Criando schema no Neo4j...")
print("="*55)
with driver.session() as s:
    for cmd in comandos:
        s.run(cmd)
        tipo = "CONSTRAINT" if "CONSTRAINT" in cmd else "INDEX    "
        nome = extrair_nome(cmd)
        print(f"  OK [{tipo}]: {nome}")

print("="*55)
print()
print("Schema criado! Nos do grafo:")
print("  :Host       <- hosts")
print("  :Grupo      <- hstgrp + hosts_groups")
print("  :Interface  <- interface")
print("  :Template   <- hosts_templates")
print("  :Item       <- items + item_discovery")
print("  :Trigger    <- triggers + functions")
print("  :Evento     <- events + problem")
print("  :Metrica    <- history + history_uint")
print("  :Tendencia  <- trends + trends_uint")
print()
print("Relacionamentos:")
print("  (Host)-[:PERTENCE_A]->(Grupo)")
print("  (Host)-[:TEM]->(Interface)")
print("  (Host)-[:USA]->(Template)")
print("  (Host)-[:TEM_ITEM]->(Item)")
print("  (Host)-[:TEM_TRIGGER]->(Trigger)")
print("  (Item)-[:TEM_VALOR]->(Metrica)")
print("  (Item)-[:TEM_TREND]->(Tendencia)")
print("  (Trigger)-[:GEROU]->(Evento)")

driver.close()
