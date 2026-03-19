#!/usr/bin/env python3
"""
Script de setup inicial - criar índices e constraints no Neo4j
Executa: python3 setup_neo4j.py
"""
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv("config.env")

def main():
    print("\n" + "="*70)
    print("SETUP NEO4J - Criando Índices e Constraints")
    print("="*70)
    
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
    )
    
    queries = [
        # Índices em Metrica (para queries rápidas)
        ("CREATE INDEX idx_metrica_tipo IF NOT EXISTS FOR (m:Metrica) ON (m.tipo)", 
         "Índice de tipo de métrica"),
        ("CREATE INDEX idx_metrica_clock IF NOT EXISTS FOR (m:Metrica) ON (m.clock)",
         "Índice de timestamp de métrica"),
        ("CREATE INDEX idx_metrica_hostid IF NOT EXISTS FOR (m:Metrica) ON (m.hostid)",
         "Índice hostid em metrica"),
        
        # Índices em Host
        ("CREATE INDEX idx_host_name IF NOT EXISTS FOR (h:Host) ON (h.host)",
         "Índice de nome de host"),
        
        # Índices em Item
        ("CREATE INDEX idx_item_id IF NOT EXISTS FOR (i:Item) ON (i.itemid)",
         "Índice de item id"),
        
        # Unique constraints
        ("CREATE CONSTRAINT uq_metrica_unique IF NOT EXISTS FOR (m:Metrica) REQUIRE (m.hostid, m.itemid, m.clock) IS UNIQUE",
         "Constraint de unicidade em Metrica"),
        
        # Constraints em Host
        ("CREATE CONSTRAINT uq_host_id IF NOT EXISTS FOR (h:Host) REQUIRE h.hostid IS UNIQUE",
         "Constraint hostid único"),
    ]
    
    with driver.session() as session:
        for query, descricao in queries:
            try:
                print(f"\n✅ {descricao}")
                print(f"   Query: {query[:60]}...")
                result = session.run(query)
                print(f"   OK")
            except Exception as e:
                # Algumas versões do Neo4j não suportam IF NOT EXISTS
                if "already exists" in str(e).lower() or "constraint already" in str(e).lower():
                    print(f"   ℹ️ Já existe")
                else:
                    print(f"   ⚠️ Aviso: {e}")
    
    driver.close()
    
    print("\n" + "="*70)
    print("SETUP CONCLUÍDO")
    print("Índices criados para performance otimizada!")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
