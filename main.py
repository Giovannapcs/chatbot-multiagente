#!/usr/bin/env python3
"""
main.py — Sincronização Zabbix -> Neo4j com paridade 1:1

Fluxo:
  1. Estrutura: hosts (todos, inclusive sem IP), grupos, interfaces, templates, items, triggers
  2. Eventos recentes (janela deslizante)
  3. Problemas: TODOS da tabela problem
  4. Limpeza: remove :Problem do Neo4j que não existem mais no Postgres
  5. ACKs: busca TODOS os ACKs (primeiro ciclo) ou recentes (ciclos seguintes)
  6. Métricas (a cada 3 ciclos)
"""
import time, logging, os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from zabbix_reader import (
    get_connection, get_hosts, get_host_tags, get_groups,
    get_interfaces, get_templates, get_items,
    get_triggers, get_eventos,
    get_problemas_ativos, get_acknowledgements,
    get_acknowledgements_por_eventos,
    get_todos_acknowledgements,
    get_todos_event_ids_problemas,
    get_metricas_recentes
)

from neo4j_writer import (
    get_driver, write_hosts, marcar_hosts_removidos,
    write_host_tags, write_groups,
    write_interfaces, write_templates,
    write_items, write_triggers,
    write_eventos, write_problemas,
    limpar_problemas_obsoletos,
    write_acknowledgements,
    limpar_acks_obsoletos,
    write_metricas
)

load_dotenv("config.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

INTERVALO  = int(os.getenv("INTERVALO_SEGUNDOS", "300"))
DIAS_HIST  = int(os.getenv("DIAS_HISTORICO", "7"))
primeiro_ciclo = True


def ciclo(pg_conn, neo4j_driver, desde_ts, sync_metricas):
    global primeiro_ciclo
    cur = pg_conn.cursor()

    try:
        with neo4j_driver.session() as s:

            # ── Estrutura base ──────────────────────────────────────────
            hosts = get_hosts(cur)
            write_hosts(s, hosts)
            log.info(f"Hosts: {len(hosts)}")

            host_ids = [h["hostid"] for h in hosts]
            marcar_hosts_removidos(s, host_ids)

            write_host_tags(s, get_host_tags(cur))
            write_groups(s, get_groups(cur))
            write_interfaces(s, get_interfaces(cur))
            write_templates(s, get_templates(cur))

            # ── Monitoramento ───────────────────────────────────────────
            items = get_items(cur)
            write_items(s, items)

            triggers = get_triggers(cur)
            write_triggers(s, triggers)
            log.info(f"Triggers: {len(triggers)}")

            # ── Eventos (janela deslizante) ─────────────────────────────
            eventos = get_eventos(cur, desde_ts)
            write_eventos(s, eventos)
            log.info(f"Eventos sincronizados: {len(eventos)}")

            # ── Problemas (TODOS — paridade 1:1 com tabela problem) ─────
            problemas = get_problemas_ativos(cur)
            write_problemas(s, problemas)
            log.info(f"Problemas (tabela problem): {len(problemas)}")

            ativos       = sum(1 for p in problemas if p.get("ativo"))
            reconhecidos = sum(1 for p in problemas if p.get("acknowledged"))
            log.info(f"  Ativos: {ativos} | Reconhecidos no Postgres: {reconhecidos}")

            # ── Limpeza de :Problem obsoletos ───────────────────────────
            # Remove do Neo4j problemas que foram deletados do Postgres
            event_ids_pg = get_todos_event_ids_problemas(cur)
            limpar_problemas_obsoletos(s, event_ids_pg)
            log.info(f"Limpeza de :Problem obsoletos concluída")

            # ── ACKs ────────────────────────────────────────────────────
            if primeiro_ciclo:
                # Primeiro ciclo: busca TODOS os ACKs do histórico completo
                log.info("Primeiro ciclo — buscando TODOS os ACKs históricos...")
                todos_acks = get_todos_acknowledgements(cur)
                if todos_acks:
                    write_acknowledgements(s, todos_acks)
                    log.info(f"ACKs históricos sincronizados: {len(todos_acks)}")

                    # Limpeza de ACKs obsoletos
                    ack_ids_pg = [a["acknowledgeid"] for a in todos_acks]
                    limpar_acks_obsoletos(s, ack_ids_pg)
                    log.info("Limpeza de :Acknowledge obsoletos concluída")

                primeiro_ciclo = False
            else:
                # Ciclos seguintes: ACKs dos problemas ativos + recentes
                event_ids_ativos = [p["eventid"] for p in problemas if p.get("ativo")]
                if event_ids_ativos:
                    acks_ativos = get_acknowledgements_por_eventos(cur, event_ids_ativos)
                    if acks_ativos:
                        write_acknowledgements(s, acks_ativos)
                        log.info(f"ACKs de problemas ativos: {len(acks_ativos)}")

                acks_recentes = get_acknowledgements(cur, desde_ts)
                if acks_recentes:
                    write_acknowledgements(s, acks_recentes)
                    log.info(f"ACKs recentes adicionais: {len(acks_recentes)}")

            # ── Métricas (a cada 3 ciclos) ──────────────────────────────
            if sync_metricas:
                log.info("Buscando métricas...")
                metricas = get_metricas_recentes(cur, limite=10000)
                write_metricas(s, metricas)
                log.info(f"Métricas sincronizadas: {len(metricas)}")

    finally:
        cur.close()

    # Retorna sempre 7 dias atrás para garantir janela completa em cada ciclo
    return int((datetime.now() - timedelta(days=DIAS_HIST)).timestamp())


def main():
    log.info("=" * 50)
    log.info("INICIANDO INTEGRADOR ZABBIX → NEO4J v2")
    log.info("=" * 50)

    pg_conn      = get_connection()
    neo4j_driver = get_driver()

    desde_ts = int((datetime.now() - timedelta(days=DIAS_HIST)).timestamp())
    ciclo_num = 0

    while True:
        try:
            if pg_conn.closed:
                log.warning("Reconectando Zabbix...")
                pg_conn = get_connection()

            ciclo_num += 1
            log.info(f"--- Ciclo {ciclo_num} ---")

            sync_metricas = (ciclo_num == 1 or ciclo_num % 3 == 0)

            desde_ts = ciclo(pg_conn, neo4j_driver, desde_ts, sync_metricas)

            time.sleep(INTERVALO)

        except KeyboardInterrupt:
            log.info("Encerrado manualmente.")
            break

        except Exception as e:
            log.error(f"Erro: {e}")
            time.sleep(20)

    pg_conn.close()
    neo4j_driver.close()


if __name__ == "__main__":
    main()
