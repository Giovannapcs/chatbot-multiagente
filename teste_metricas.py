#!/usr/bin/env python3
"""
Script de teste para validar coleta de métricas
Executa: python3 teste_metricas.py
"""
import os, sys
from datetime import datetime
from dotenv import load_dotenv
from zabbix_reader import (get_connection, get_metricas_historico, 
                            get_metricas_memoria, get_metricas_disco)
from neo4j_writer import get_driver, write_metricas_batch

load_dotenv("config.env")

def main():
    print("\n" + "="*70)
    print("TESTE DE COLETA DE MÉTRICAS")
    print("="*70)
    
    # 1. Conectar ao Zabbix
    print("\n[1] Conectando ao PostgreSQL (Zabbix)...")
    try:
        pg_conn = get_connection()
        cur = pg_conn.cursor()
        print("    ✅ Conectado!")
    except Exception as e:
        print(f"    ❌ Erro: {e}")
        return
    
    # 2. Coletar CPU
    print("\n[2] Coletando métricas de CPU (últimas 24h)...")
    try:
        metricas_cpu = get_metricas_historico(cur, dias=1)
        print(f"    ✅ Coletadas {len(metricas_cpu)} amostras de CPU")
        if metricas_cpu:
            m = metricas_cpu[0]
            print(f"       Exemplo: {m['host']} -> {m['name']} = {m['value']} {m['units']}")
            print(f"       Timestamp: {datetime.fromtimestamp(m['clock']).isoformat()}")
    except Exception as e:
        print(f"    ❌ Erro: {e}")
        metricas_cpu = []
    
    # 3. Coletar Memória
    print("\n[3] Coletando métricas de Memória (últimas 24h)...")
    try:
        metricas_mem = get_metricas_memoria(cur, dias=1)
        print(f"    ✅ Coletadas {len(metricas_mem)} amostras de Memória")
        if metricas_mem:
            m = metricas_mem[0]
            print(f"       Exemplo: {m['host']} -> {m['name']} = {m['value']} {m['units']}")
    except Exception as e:
        print(f"    ❌ Erro: {e}")
        metricas_mem = []
    
    # 4. Coletar Disco
    print("\n[4] Coletando métricas de Disco (últimas 24h)...")
    try:
        metricas_disk = get_metricas_disco(cur, dias=1)
        print(f"    ✅ Coletadas {len(metricas_disk)} amostras de Disco")
        if metricas_disk:
            m = metricas_disk[0]
            print(f"       Exemplo: {m['host']} -> {m['name']} = {m['value']} {m['units']}")
    except Exception as e:
        print(f"    ❌ Erro: {e}")
        metricas_disk = []
    
    cur.close()
    pg_conn.close()
    
    # 5. Conectar ao Neo4j e armazenar
    print("\n[5] Conectando ao Neo4j...")
    try:
        neo4j_driver = get_driver()
        with neo4j_driver.session() as session:
            print("    ✅ Conectado!")
            
            # Testar se consegue fazer uma query simples
            result = session.run("RETURN 'Neo4j OK' as msg").single()
            print(f"    Teste: {result['msg']}")
            
            # Armazenar métricas
            if metricas_cpu:
                print(f"\n[6] Armazenando {len(metricas_cpu)} métricas de CPU...")
                try:
                    write_metricas_batch(session, metricas_cpu, tipo_metrica="cpu")
                    print("    ✅ CPUs armazenadas!")
                except Exception as e:
                    print(f"    ❌ Erro ao escrever: {e}")
            
            if metricas_mem:
                print(f"[7] Armazenando {len(metricas_mem)} métricas de Memória...")
                try:
                    write_metricas_batch(session, metricas_mem, tipo_metrica="memoria")
                    print("    ✅ Memórias armazenadas!")
                except Exception as e:
                    print(f"    ❌ Erro ao escrever: {e}")
            
            if metricas_disk:
                print(f"[8] Armazenando {len(metricas_disk)} métricas de Disco...")
                try:
                    write_metricas_batch(session, metricas_disk, tipo_metrica="disco")
                    print("    ✅ Discos armazenados!")
                except Exception as e:
                    print(f"    ❌ Erro ao escrever: {e}")
            
            # Contar nós Metrica criados
            print("\n[9] Estatísticas no Neo4j:")
            result = session.run("""
                MATCH (m:Metrica) 
                RETURN COUNT(m) as total,
                       COUNT(DISTINCT m.tipo) as tipos,
                       COUNT(DISTINCT m.host) as hosts
            """).single()
            
            print(f"    Total de nós :Metrica: {result['total']}")
            print(f"    Tipos de métricas: {result['tipos']}")
            print(f"    Hosts monitorados: {result['hosts']}")
            
            # Amostra
            print("\n[10] Amostra de dados no Neo4j:")
            result = session.run("""
                MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica)
                WITH h, m LIMIT 3
                RETURN h.host, m.tipo, m.valor, m.units, m.timestamp
            """)
            
            for row in result:
                print(f"    {row['h.host']:20s} {row['m.tipo']:10s} {str(row['m.valor']):8s} {row['m.units']:5s} [{row['m.timestamp']}]")
        
        neo4j_driver.close()
    
    except Exception as e:
        print(f"    ❌ Erro: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*70)
    print("TESTE CONCLUÍDO")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
