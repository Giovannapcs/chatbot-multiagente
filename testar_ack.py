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
MATCH (e:Evento)
RETURN 
    count(e.acknowledged) AS tem_ack,
    count(e) AS total
"""

with driver.session() as session:
    result = session.run(query)
    for row in result:
        print(dict(row))

driver.close()
