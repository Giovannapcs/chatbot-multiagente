#!/usr/bin/env python3
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv("config.env")

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
)

query = """
MATCH (t:Trigger)-[:GEROU]->(e:Evento)
RETURN 
    t.triggerid AS triggerid,
    e.eventid AS eventid,
    e.value AS value,
    e.severity AS severity,
    e.clock AS clock,
    e.timestamp AS timestamp,
    e.name AS name,
    e.ativo AS ativo
ORDER BY e.clock DESC
LIMIT 30
"""

with driver.session() as session:
    for row in session.run(query):
        print(dict(row))

driver.close()
