#!/usr/bin/env python3
"""
Cria constraints e indices no Neo4j para otimizar as queries do projeto.
Execute uma vez antes de iniciar a sincronizacao.
"""
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv("config.env")

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
)

# Constraints garantem unicidade; indices aceleram buscas por propriedade
comandos = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (h:Host)      REQUIRE h.hostid      IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (g:Grupo)     REQUIRE g.groupid     IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Item)      REQUIRE i.itemid      IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Trigger)   REQUIRE t.triggerid   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Evento)    REQUIRE e.eventid     IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Interface) REQUIRE n.interfaceid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Metrica)   REQUIRE m.id          IS UNIQUE",
    "CREATE INDEX IF NOT EXISTS FOR (h:Host)    ON (h.status)",
    "CREATE INDEX IF NOT EXISTS FOR (h:Host)    ON (h.host)",
    "CREATE INDEX IF NOT EXISTS FOR (h:Host)    ON (h.ip)",
    "CREATE INDEX IF NOT EXISTS FOR (i:Item)    ON (i.key_)",
    "CREATE INDEX IF NOT EXISTS FOR (i:Item)    ON (i.value_type)",
    "CREATE INDEX IF NOT EXISTS FOR (t:Trigger) ON (t.value)",
    "CREATE INDEX IF NOT EXISTS FOR (t:Trigger) ON (t.priority)",
    "CREATE INDEX IF NOT EXISTS FOR (e:Evento)  ON (e.severity)",
    "CREATE INDEX IF NOT EXISTS FOR (e:Evento)  ON (e.clock)",
    "CREATE INDEX IF NOT EXISTS FOR (m:Metrica) ON (m.clock)",
    "CREATE INDEX IF NOT EXISTS FOR (g:Grupo)   ON (g.name)",
]


def extrair_nome(cmd):
    """Extrai um nome legivel do comando para exibir no log."""
    partes = cmd.split("(")
    try:
        if "CONSTRAINT" in cmd:
            no = partes[1].split(")")[0].strip()
            prop = cmd.split("REQUIRE")[1].strip()
            return f"{no} -> {prop}"
        else:
            no = partes[1].split(")")[0].strip()
            campo = partes[2].split(")")[0].strip()
            return f"{no} -> {campo}"
    except IndexError:
        return cmd[:60]


print("Criando schema no Neo4j...")
print("=" * 55)

with driver.session() as s:
    for cmd in comandos:
        s.run(cmd)
        tipo = "CONSTRAINT" if "CONSTRAINT" in cmd else "INDEX    "
        print(f"  OK [{tipo}]: {extrair_nome(cmd)}")

print("=" * 55)
print()
print("Nos do grafo:")
for no, origem in [
    (":Host",      "hosts"),
    (":Grupo",     "hstgrp + hosts_groups"),
    (":Interface", "interface"),
    (":Template",  "hosts_templates"),
    (":Item",      "items"),
    (":Trigger",   "triggers + functions"),
    (":Evento",    "events + problem"),
    (":Metrica",   "history + history_uint"),
]:
    print(f"  {no:<14} <- {origem}")

print()
print("Relacionamentos principais:")
for rel in [
    "(Host)-[:PERTENCE_A]->(Grupo)",
    "(Host)-[:TEM_TRIGGER]->(Trigger)-[:GEROU]->(Evento)",
    "(Trigger)-[:GEROU_PROBLEMA]->(Problem)",
    "(Evento)-[:VIROU_PROBLEMA]->(Problem)",
    "(Problem)-[:TEM_ACK]->(Acknowledge)",
    "(Item)-[:TEM_VALOR]->(Metrica)",
]:
    print(f"  {rel}")

driver.close()
