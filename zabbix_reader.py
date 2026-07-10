#!/usr/bin/env python3
"""
Leitura dos dados do Zabbix via PostgreSQL.
Todas as funcoes recebem um cursor aberto e retornam listas de dicts.
A conexao e gerenciada externamente (em main.py ou sync_demanda.py).
"""
import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv("config.env")


def get_connection():
    """Abre e retorna uma conexao de leitura com o banco do Zabbix."""
    conn = psycopg2.connect(
        host=os.getenv("ZABBIX_DB_HOST"),
        port=int(os.getenv("ZABBIX_DB_PORT", "5432")),
        dbname=os.getenv("ZABBIX_DB_NAME"),
        user=os.getenv("ZABBIX_DB_USER"),
        password=os.getenv("ZABBIX_DB_PASS"),
        sslmode=os.getenv("ZABBIX_DB_SSLMODE", "prefer"),
        cursor_factory=RealDictCursor
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


def get_hosts(cur):
    """Retorna todos os hosts ativos e desabilitados com IP principal."""
    cur.execute("""
        SELECT h.hostid, h.host, h.name, h.status,
               COALESCE(i.ip,'')   AS ip,
               COALESCE(i.dns,'')  AS dns,
               COALESCE(i.port,'') AS porta,
               CASE WHEN h.status=0 THEN 'ativo' ELSE 'inativo' END AS status_txt
        FROM hosts h
        INNER JOIN interface i ON i.hostid=h.hostid AND i.main=1
        WHERE h.flags = 0
          AND h.status IN (0, 1)
          AND i.ip IS NOT NULL
          AND i.ip <> ''
        ORDER BY h.host
    """)
    return cur.fetchall()


def get_host_tags(cur):
    """Retorna as tags (chave=valor) de todos os hosts ativos."""
    cur.execute("""
        SELECT h.hostid, h.host, ht.tag, ht.value
        FROM hosts h
        JOIN host_tag ht ON h.hostid = ht.hostid
        WHERE h.flags = 0
          AND h.status = 0
        ORDER BY h.host, ht.tag
    """)
    return cur.fetchall()


def get_groups(cur):
    """Retorna os grupos de hosts com a lista de hostids de cada grupo."""
    cur.execute("""
        SELECT hg.groupid, hg.name,
               ARRAY_AGG(hgh.hostid) AS host_ids
        FROM hstgrp hg
        LEFT JOIN hosts_groups hgh ON hgh.groupid=hg.groupid
        GROUP BY hg.groupid, hg.name
    """)
    return cur.fetchall()


def get_interfaces(cur):
    """Retorna todas as interfaces de rede dos hosts."""
    cur.execute("""
        SELECT interfaceid, hostid,
               COALESCE(ip,'')   AS ip,
               COALESCE(dns,'')  AS dns,
               COALESCE(port,'') AS port,
               type, main
        FROM interface
    """)
    return cur.fetchall()


def get_templates(cur):
    """Retorna os templates vinculados a cada host."""
    cur.execute("""
        SELECT ht.hostid, ht.templateid,
               t.host AS template_nome
        FROM hosts_templates ht
        JOIN hosts t ON t.hostid=ht.templateid
    """)
    return cur.fetchall()


def get_items(cur):
    """Retorna os itens de monitoramento ativos (status=0)."""
    cur.execute("""
        SELECT i.itemid, i.hostid, i.name,
               i.key_, i.value_type,
               COALESCE(i.units,'') AS units,
               i.status
        FROM items i
        WHERE i.flags=0 AND i.status=0
    """)
    return cur.fetchall()


def get_triggers(cur):
    """Retorna as triggers ativas vinculadas a hosts reais."""
    cur.execute("""
        SELECT DISTINCT t.triggerid, t.description,
               t.priority, t.value, t.status,
               h.hostid
        FROM triggers t
        JOIN functions f ON f.triggerid=t.triggerid
        JOIN items i ON i.itemid=f.itemid
        JOIN hosts h ON h.hostid=i.hostid
        WHERE t.flags=0 AND t.status=0
    """)
    return cur.fetchall()


def get_eventos(cur, desde_ts):
    """
    Retorna eventos ocorridos a partir de desde_ts (unix timestamp em segundos).
    Limitado a 10000 registros para nao sobrecarregar o banco.
    """
    cur.execute("""
        SELECT eventid, objectid AS triggerid,
               clock, value, severity
        FROM events
        WHERE source=0 AND object=0
          AND clock > %s
        ORDER BY clock DESC LIMIT 10000
    """, (desde_ts,))
    return cur.fetchall()


def get_problemas_ativos(cur):
    """Retorna todos os problems atualmente em aberto no Zabbix."""
    cur.execute("""
        SELECT eventid, objectid AS triggerid,
               clock, severity, name
        FROM problem WHERE source=0
        ORDER BY severity DESC, clock DESC
    """)
    return cur.fetchall()


def get_metricas_recentes(cur, limite=5000):
    """
    Retorna o valor mais recente de cada item coletado nos ultimos 10 minutos.
    Busca em history (float) e history_uint (inteiro sem sinal) separadamente.
    """
    dez_min_atras = int(time.time()) - 600

    cur.execute("""
        SELECT DISTINCT ON (itemid)
               itemid, clock,
               ROUND(value::numeric,4) AS value,
               'float' AS tipo
        FROM history
        WHERE clock > %s
        ORDER BY itemid, clock DESC
        LIMIT %s
    """, (dez_min_atras, limite))
    floats = cur.fetchall()

    cur.execute("""
        SELECT DISTINCT ON (itemid)
               itemid, clock,
               value::numeric AS value,
               'uint' AS tipo
        FROM history_uint
        WHERE clock > %s
        ORDER BY itemid, clock DESC
        LIMIT %s
    """, (dez_min_atras, limite))
    uints = cur.fetchall()

    return floats + uints


def get_acknowledgements(cur, desde_ts=None):
    """
    Retorna os acknowledgements a partir de desde_ts.
    Usado para calcular SLA, MTTA e metricas de desempenho do NOC.
    """
    if desde_ts is None:
        desde_ts = int(time.time()) - (300 * 86400)

    cur.execute("""
        SELECT acknowledgeid, eventid, userid, clock, message,
               action, old_severity, new_severity, suppress_until, taskid
        FROM acknowledges
        WHERE clock >= %s
        ORDER BY clock DESC
    """, (desde_ts,))
    return cur.fetchall()


def get_problemas_historico(cur, desde_ts=None):
    """
    Retorna o historico de problems (ativos e resolvidos) a partir de desde_ts.
    Usado para relatorios de tendencia, comparativo de SLA e desempenho do NOC.
    """
    if desde_ts is None:
        desde_ts = int(time.time()) - (300 * 86400)

    cur.execute("""
        SELECT p.eventid, p.objectid AS triggerid, p.clock,
               p.severity, p.name, p.acknowledged, p.r_eventid,
               CASE WHEN p.r_eventid IS NOT NULL THEN false ELSE true END AS ativo
        FROM problem p
        WHERE p.source = 0 AND p.clock >= %s
        ORDER BY p.clock DESC
    """, (desde_ts,))
    return cur.fetchall()
