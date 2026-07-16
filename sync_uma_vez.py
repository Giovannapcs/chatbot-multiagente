#!/usr/bin/env python3
"""
Executa UM UNICO ciclo de sincronizacao Zabbix -> Neo4j e encerra.
Feito para ser chamado via cron (diariamente ou a cada poucas horas),
evitando manter o processo (e o Neo4j) rodando continuamente.

Reaproveita as mesmas funcoes de leitura/escrita do projeto original.
"""
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

DIAS_HIST = int(os.getenv("DIAS_HISTORICO", "7"))


def main():
    log.info("=" * 50)
    log.info("SINCRONIZACAO UNICA: Zabbix -> Neo4j")
    log.info(f"Janela de historico: {DIAS_HIST} dias")
    log.info("=" * 50)

    pg_conn = get_connection()
    neo4j_driver = get_driver()
    desde_ts = int((datetime.now() - timedelta(days=DIAS_HIST)).timestamp())

    cur = pg_conn.cursor()
    try:
        with neo4j_driver.session() as s:
            log.info("Sincronizando estrutura de rede...")
            write_hosts(s, get_hosts(cur))
            write_host_tags(s, get_host_tags(cur))
            write_groups(s, get_groups(cur))
            write_interfaces(s, get_interfaces(cur))

            log.info("Sincronizando monitoramento e alertas...")
            write_items(s, get_items(cur))
            write_triggers(s, get_triggers(cur))
            write_eventos(s, get_eventos(cur, desde_ts))

            write_problemas(s, get_problemas_ativos(cur))
            write_problemas(s, get_problemas_historico(cur, desde_ts))

            acks = get_acknowledgements(cur, desde_ts)
            write_acknowledgements(s, acks)
            log.info(f"ACKs sincronizados: {len(acks)}")

            log.info("Buscando metricas do PostgreSQL...")
            metricas = get_metricas_recentes(cur, limite=5000)
            write_metricas(s, metricas)
            log.info(f"Metricas sincronizadas: {len(metricas)}")


        log.info("Ciclo unico concluido com sucesso.")

    except Exception as e:
        log.error(f"Erro durante a sincronizacao: {e}")
        raise
    finally:
        cur.close()
        pg_conn.close()
        neo4j_driver.close()
        log.info("Conexoes encerradas. Script finalizado.")


if __name__ == "__main__":
    main()
