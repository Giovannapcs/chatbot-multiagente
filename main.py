#!/usr/bin/env python3
import time, logging, os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from zabbix_reader import (get_connection, get_hosts, get_groups,
                            get_items, get_triggers,
                            get_eventos, get_problemas_ativos)
from neo4j_writer  import (get_driver, write_hosts, write_groups,
                            write_items, write_triggers,
                            write_eventos, write_problemas)

load_dotenv("config.env")
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

INTERVALO = int(os.getenv("INTERVALO_SEGUNDOS","30"))
DIAS_HIST = int(os.getenv("DIAS_HISTORICO","7"))

def ciclo(pg_conn, neo4j_driver, desde_ts):
    cur = pg_conn.cursor()
    with neo4j_driver.session() as session:
        hosts = get_hosts(cur);       write_hosts(session, hosts);       log.info(f"Hosts: {len(hosts)}")
        groups = get_groups(cur);     write_groups(session, groups);     log.info(f"Grupos: {len(groups)}")
        items = get_items(cur);       write_items(session, items);       log.info(f"Itens: {len(items)}")
        triggers = get_triggers(cur); write_triggers(session, triggers); log.info(f"Triggers: {len(triggers)}")
        eventos = get_eventos(cur, desde_ts); write_eventos(session, eventos); log.info(f"Eventos: {len(eventos)}")
        problemas = get_problemas_ativos(cur); write_problemas(session, problemas); log.info(f"Problemas: {len(problemas)}")
    return int(time.time())

def main():
    log.info("="*50)
    log.info("INICIANDO: Zabbix -> Neo4j")
    log.info(f"Intervalo: {INTERVALO}s | Historico: {DIAS_HIST} dias")
    log.info("="*50)
    pg_conn      = get_connection()
    neo4j_driver = get_driver()
    desde_ts = int((datetime.now()-timedelta(days=DIAS_HIST)).timestamp())
    while True:
        try:
            log.info(f"--- Ciclo [{datetime.now().strftime('%H:%M:%S')}] ---")
            desde_ts = ciclo(pg_conn, neo4j_driver, desde_ts)
            log.info(f"OK. Aguardando {INTERVALO}s...")
            time.sleep(INTERVALO)
        except KeyboardInterrupt:
            log.info("Encerrando (Ctrl+C)...")
            break
        except Exception as e:
            log.error(f"Erro: {e}")
            time.sleep(15)
    pg_conn.close()
    neo4j_driver.close()

if __name__ == "__main__":
    main()
