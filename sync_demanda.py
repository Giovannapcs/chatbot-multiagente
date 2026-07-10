#!/usr/bin/env python3
"""
Sincronizacao rapida sob demanda.
Chamado antes de consultar o Neo4j para garantir dados atualizados.
Evita sincronizacoes repetidas respeitando um intervalo minimo entre chamadas.
"""
import time
import logging

log = logging.getLogger(__name__)

# Controle interno do tempo da ultima sincronizacao
_ultima_sync = 0
INTERVALO_MINIMO = 300  # segundos entre sincronizacoes (5 minutos)


def sincronizar_se_necessario(pg_conn, neo4j_driver, forcar=False):
    """
    Faz uma sincronizacao rapida Zabbix -> Neo4j se necessario.

    Parametros:
        pg_conn: conexao aberta com o PostgreSQL do Zabbix
        neo4j_driver: driver Neo4j inicializado
        forcar: se True, sincroniza mesmo que o intervalo nao tenha passado

    Retorna True se sincronizou, False se nao foi necessario.
    """
    global _ultima_sync
    agora = int(time.time())

    if not forcar and (agora - _ultima_sync) < INTERVALO_MINIMO:
        log.info(f"Sync ignorada (ultima ha {agora - _ultima_sync}s)")
        return False

    log.info("Iniciando sync rapida...")
    inicio = time.time()

    try:
        from zabbix_reader import (
            get_hosts, get_host_tags, get_groups,
            get_triggers, get_eventos, get_problemas_ativos,
            get_acknowledgements
        )
        from neo4j_writer import (
            write_hosts, write_host_tags, write_groups,
            write_triggers, write_eventos, write_problemas,
            write_acknowledgements
        )

        desde_ts = agora - (7 * 86400)  # janela dos ultimos 7 dias
        cur = pg_conn.cursor()

        with neo4j_driver.session() as s:
            # Estrutura: hosts e grupos
            write_hosts(s, get_hosts(cur))
            write_host_tags(s, get_host_tags(cur))
            write_groups(s, get_groups(cur))

            # Monitoramento: triggers e eventos recentes
            write_triggers(s, get_triggers(cur))
            write_eventos(s, get_eventos(cur, desde_ts))

            # Problems e acknowledgements
            write_problemas(s, get_problemas_ativos(cur))
            write_acknowledgements(s, get_acknowledgements(cur, desde_ts))

        cur.close()
        _ultima_sync = int(time.time())
        log.info(f"Sync concluida em {round(time.time() - inicio, 2)}s")
        return True

    except Exception as e:
        log.error(f"Erro na sync rapida: {e}")
        return False


def get_status_sync():
    """
    Retorna um dict com informacoes sobre a ultima sincronizacao.
    Util para o bot responder perguntas sobre atualizacao dos dados.
    """
    agora = int(time.time())

    if _ultima_sync == 0:
        return {"sincronizado": False, "mensagem": "Ainda nao sincronizado nesta sessao"}

    segundos = agora - _ultima_sync
    if segundos < 60:
        tempo = f"ha {segundos} segundos"
    elif segundos < 3600:
        tempo = f"ha {segundos // 60} minutos"
    else:
        tempo = f"ha {segundos // 3600} horas"

    return {
        "sincronizado": True,
        "ultima_sync_ts": _ultima_sync,
        "tempo_desde_sync": segundos,
        "mensagem": f"Ultima sincronizacao {tempo}"
    }
