#!/usr/bin/env python3
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv("config.env")

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
)

comandos = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (h:Host)     REQUIRE h.hostid    IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (g:Grupo)    REQUIRE g.groupid   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Item)     REQUIRE i.itemid    IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Trigger)  REQUIRE t.triggerid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Evento)   REQUIRE e.eventid   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Problema) REQUIRE p.eventid   IS UNIQUE",
    "CREATE INDEX IF NOT EXISTS FOR (h:Host)    ON (h.status)",
    "CREATE INDEX IF NOT EXISTS FOR (h:Host)    ON (h.host)",
    "CREATE INDEX IF NOT EXISTS FOR (e:Evento)  ON (e.severity)",
    "CREATE INDEX IF NOT EXISTS FOR (t:Trigger) ON (t.value)",
    "CREATE INDEX IF NOT EXISTS FOR (t:Trigger) ON (t.priority)",
]

print("Criando schema no Neo4j Aura...")
with driver.session() as s:
    for cmd in comandos:
        s.run(cmd)
        print(f"  OK: {cmd[7:55]}...")

print("Schema criado!")
driver.close()
