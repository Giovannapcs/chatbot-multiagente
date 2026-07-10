#!/usr/bin/env python3
"""
Servico de sincronizacao continua: Zabbix (PostgreSQL) -> Neo4j.
Roda em loop a cada INTERVALO_SEGUNDOS, atualizando hosts, triggers,
eventos, problemas, acknowledgements e metricas no grafo.
"""
import time
import logging
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from zabbix_reader import (
    get_connection, get_hosts, get_host_tags, get_groups,
    get_interfaces, get_templates, get_items,
    get_triggers, get_eventos,
    get_problemas_ativos, get_metricas_recentes,
    get_acknowledgements, get_problemas_historico
)
from neo4j_writer import (
    get_driver, write_hosts, write_host_tags, write_groups,
    write_interfaces, write_templates,
    write_items, write_triggers,
    write_eventos, write_problemas,
    write_acknowledgements, limpar_acks_obsoletos,
    limpar_problemas_obsoletos, write_metricas
)

load_dotenv("config.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# Intervalo entre ciclos e janela de historico (configurados no config.env)
INTERVALO = int(os.getenv("INTERVALO_SEGUNDOS", "300"))
DIAS_HIST = int(os.getenv("DIAS_HISTORICO", "7"))


def ciclo(pg_conn, neo4j_driver, desde_ts, sync_metricas):
    """
    Executa um ciclo completo de sincronizacao.
    Cada ciclo abre um cursor novo e o fecha ao terminar para nao travar o banco.
    Retorna o timestamp atual para ser usado como inicio do proximo ciclo.
    """
    cur = pg_conn.cursor()
    try:
        with neo4j_driver.session() as s:

            # 1. Estrutura de rede (atualiza todo ciclo)
            write_hosts(s, get_hosts(cur))
            write_host_tags(s, get_host_tags(cur))
            write_groups(s, get_groups(cur))
            write_interfaces(s, get_interfaces(cur))

            # 2. Monitoramento e alertas
            write_items(s, get_items(cur))
            write_triggers(s, get_triggers(cur))
            write_eventos(s, get_eventos(cur, desde_ts))

            # 2a. Problems ativos (snapshot atual)
            write_problemas(s, get_problemas_ativos(cur))

            # 2b. Historico de problems (necessario para relatorios de tendencia e SLA)
            write_problemas(s, get_problemas_historico(cur, desde_ts))

            # 2c. Acknowledgements (necessario para calcular SLA, MTTA e NOC)
            acks = get_acknowledgements(cur, desde_ts)
            write_acknowledgements(s, acks)
            log.info(f"ACKs sincronizados: {len(acks)}")

            # 3. Metricas pesadas (apenas a cada 3 ciclos, ~15 minutos)
            if sync_metricas:
                log.info("Buscando metricas do PostgreSQL...")
                metricas = get_metricas_recentes(cur, limite=5000)
                write_metricas(s, metricas)
                log.info(f"Metricas sincronizadas: {len(metricas)}")
            else:
                log.info("Ciclo de alertas: metricas ignoradas para poupar o banco.")

    finally:
        cur.close()

    return int(time.time())


def main():
    log.info("=" * 50)
    log.info("INICIANDO SINCRONIZACAO: Zabbix -> Neo4j")
    log.info(f"Intervalo: {INTERVALO}s | Metricas: a cada 15 min")
    log.info("=" * 50)

    pg_conn = get_connection()
    neo4j_driver = get_driver()
    desde_ts = int((datetime.now() - timedelta(days=DIAS_HIST)).timestamp())
    ciclo_num = 0

    while True:
        try:
            # Reconecta ao Zabbix se a conexao foi perdida
            if pg_conn.closed:
                log.warning("Conexao com o Zabbix perdida. Reconectando...")
                pg_conn = get_connection()

            ciclo_num += 1
            log.info(f"--- Ciclo {ciclo_num} [{datetime.now().strftime('%H:%M:%S')}] ---")

            # Metricas pesadas a cada 3 ciclos (15 min), alertas todo ciclo (5 min)
            sync_metricas = (ciclo_num == 1 or ciclo_num % 3 == 0)

            desde_ts = ciclo(pg_conn, neo4j_driver, desde_ts, sync_metricas)

            log.info(f"OK! Aguardando {INTERVALO}s...")
            time.sleep(INTERVALO)

        except KeyboardInterrupt:
            log.info("Encerramento solicitado. Finalizando...")
            break
        except Exception as e:
            log.error(f"Erro no ciclo: {e}")
            time.sleep(20)

    pg_conn.close()
    neo4j_driver.close()
    log.info("Servico encerrado.")


if __name__ == "__main__":
    main()
