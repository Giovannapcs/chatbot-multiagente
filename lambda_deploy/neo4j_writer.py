#!/usr/bin/env python3
"""main.py — Sincronizacao Otimizada Zabbix 7.x -> Neo4j (IOS)"""

import time
import logging
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from zabbix_reader import (
    get_connection,
    get_hosts,
    get_host_tags,
    get_groups,
    get_interfaces,
    get_templates,
    get_items,
    get_triggers,
    get_eventos,
    get_problemas_ativos,
    get_metricas_recentes,
    get_acknowledgements
)

from neo4j_writer import (
    get_driver,
    write_hosts,
    marcar_hosts_removidos,
    write_host_tags,
    write_groups,
    write_interfaces,
    write_templates,
    write_items,
    write_triggers,
    write_eventos,
    write_problemas,
    write_metricas,
    write_acknowledgements
)

load_dotenv("config.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

log = logging.getLogger(__name__)

INTERVALO = int(os.getenv("INTERVALO_SEGUNDOS", "300"))
DIAS_HIST = int(os.getenv("DIAS_HISTORICO", "7"))


def ciclo(pg_conn, neo4j_driver, desde_ts, sync_metricas):
    cur = pg_conn.cursor()

    try:
        with neo4j_driver.session() as s:

            # 1. Estrutura da rede
            hosts = get_hosts(cur)
            write_hosts(s, hosts)

            host_ids_atuais = [h["hostid"] for h in hosts]
            marcar_hosts_removidos(s, host_ids_atuais)

            tags = get_host_tags(cur)
            write_host_tags(s, tags)

            groups = get_groups(cur)
            write_groups(s, groups)

            interfaces = get_interfaces(cur)
            write_interfaces(s, interfaces)

            templates = get_templates(cur)
            write_templates(s, templates)

            # 2. Monitoramento e alertas
            items = get_items(cur)
            write_items(s, items)

            triggers = get_triggers(cur)
            write_triggers(s, triggers)

            eventos = get_eventos(cur, desde_ts)
            write_eventos(s, eventos)

            problemas = get_problemas_ativos(cur)
            write_problemas(s, problemas)

            # 3. Reconhecimento de incidentes
            acknowledgements = get_acknowledgements(cur, desde_ts)

            if acknowledgements:
                log.info(f"Acknowledgements encontrados: {len(acknowledgements)}")
                write_acknowledgements(s, acknowledgements)
            else:
                log.info("Nenhum acknowledgement encontrado neste ciclo.")

            # 4. Métricas pesadas
            if sync_metricas:
                log.info("Buscando métricas pesadas no PostgreSQL...")
                metricas = get_metricas_recentes(cur, limite=1000)
                write_metricas(s, metricas)
                log.info(f"Métricas sincronizadas: {len(metricas)}")
            else:
                log.info("Ciclo de alertas: métricas ignoradas para poupar o banco.")

    finally:
        cur.close()

    return int(time.time())


def main():
    log.info("=" * 50)
    log.info("INICIANDO INTEGRADOR: Zabbix -> Neo4j")
    log.info(f"Intervalo: {INTERVALO}s | Métricas: a cada 15 min")
    log.info("=" * 50)

    pg_conn = get_connection()
    neo4j_driver = get_driver()

    desde_ts = int((datetime.now() - timedelta(days=DIAS_HIST)).timestamp())
    ciclo_num = 0

    while True:
        try:
            if pg_conn.closed:
                log.warning("Conexão Zabbix perdida. Reconectando...")
                pg_conn = get_connection()

            ciclo_num += 1
            agora = datetime.now().strftime("%H:%M:%S")
            log.info(f"--- Ciclo {ciclo_num} [{agora}] ---")

            # Alertas todo ciclo. Métricas a cada 3 ciclos.
            sync_metricas = ciclo_num == 1 or ciclo_num % 3 == 0

            desde_ts = ciclo(pg_conn, neo4j_driver, desde_ts, sync_metricas)

            log.info(f"OK! Aguardando {INTERVALO}s...")
            time.sleep(INTERVALO)

        except KeyboardInterrupt:
            log.info("Interrupção manual detectada. Encerrando...")
            break

        except Exception as e:
            log.error(f"Erro inesperado: {e}")
            time.sleep(20)

    pg_conn.close()
    neo4j_driver.close()
    log.info("Sistema encerrado com segurança.")


if __name__ == "__main__":
    main()
