#!/usr/bin/env python3
"""main.py — Sincronizacao completa Zabbix 7.x -> Neo4j"""
import time, logging, os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from zabbix_reader import (get_connection, get_hosts, get_groups,
                            get_interfaces, get_templates, get_items,
                            get_triggers, get_eventos,
                            get_problemas_ativos, get_metricas_recentes)
from neo4j_writer  import (get_driver, write_hosts, write_groups,
                            write_interfaces, write_templates,
                            write_items, write_triggers,
                            write_eventos, write_problemas,
                            write_metricas)

load_dotenv("config.env")
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

INTERVALO = int(os.getenv("INTERVALO_SEGUNDOS","30"))
DIAS_HIST = int(os.getenv("DIAS_HISTORICO","7"))

def ciclo(pg_conn, neo4j_driver, desde_ts, primeira):
    cur = pg_conn.cursor()
    with neo4j_driver.session() as s:
        # Estrutura da rede
        hosts = get_hosts(cur)
        write_hosts(s, hosts)
        log.info(f"Hosts: {len(hosts)}")

        groups = get_groups(cur)
        write_groups(s, groups)
        log.info(f"Grupos: {len(groups)}")

        interfaces = get_interfaces(cur)
        write_interfaces(s, interfaces)
        log.info(f"Interfaces: {len(interfaces)}")

        templates = get_templates(cur)
        write_templates(s, templates)
        log.info(f"Templates: {len(templates)}")

        # Monitoramento
        items = get_items(cur)
        write_items(s, items)
        log.info(f"Itens: {len(items)}")

        triggers = get_triggers(cur)
        write_triggers(s, triggers)
        log.info(f"Triggers: {len(triggers)}")

        # Eventos e alertas
        eventos = get_eventos(cur, desde_ts)
        write_eventos(s, eventos)
        log.info(f"Eventos novos: {len(eventos)}")

        problemas = get_problemas_ativos(cur)
        write_problemas(s, problemas)
        log.info(f"Problemas ativos: {len(problemas)}")

        # Metricas (apenas na primeira execucao ou a cada 5 min)
        if primeira:
            metricas = get_metricas_recentes(cur)
            write_metricas(s, metricas)
            log.info(f"Metricas: {len(metricas)}")

    return int(time.time())

def main():
    log.info("="*50)
    log.info("INICIANDO: Zabbix 7.x -> Neo4j")
    log.info(f"Intervalo: {INTERVALO}s | Historico: {DIAS_HIST} dias")
    log.info("="*50)

    pg_conn = get_connection()
    neo4j_driver = get_driver()
    desde_ts = int((datetime.now()-timedelta(days=DIAS_HIST)).timestamp())
    primeira = True
    ciclo_num = 0

    while True:
        try:
            ciclo_num += 1
            log.info(f"--- Ciclo {ciclo_num} [{datetime.now().strftime("%H:%M:%S")}] ---")
            # Metricas a cada 10 ciclos (~5 min)
            sync_metricas = primeira or ciclo_num % 10 == 0
            desde_ts = ciclo(pg_conn, neo4j_driver, desde_ts, sync_metricas)
            primeira = False
            log.info(f"OK! Aguardando {INTERVALO}s...")
            time.sleep(INTERVALO)
        except KeyboardInterrupt:
            log.info("Encerrando (Ctrl+C)...")
            break
        except Exception as e:
            log.error(f"Erro: {e}")
            time.sleep(15)

    pg_conn.close()
    neo4j_driver.close()
    log.info("Encerrado.")

if __name__ == "__main__":
    main()
