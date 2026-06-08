#!/usr/bin/env python3
"""
zabbix_reader.py — Leitura fiel do PostgreSQL Zabbix para o Neo4j
Garante paridade 1:1 entre problem/acknowledges do Postgres e Neo4j
"""
import os, psycopg2, time
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv("config.env")


def get_connection():
    conn = psycopg2.connect(
        host=os.getenv("ZABBIX_DB_HOST"),
        port=int(os.getenv("ZABBIX_DB_PORT", "5432")),
        dbname=os.getenv("ZABBIX_DB_NAME"),
        user=os.getenv("ZABBIX_DB_USER"),
        password=os.getenv("ZABBIX_DB_PASS"),
        cursor_factory=RealDictCursor
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


def get_hosts(cur):
    """
    Busca todos os hosts monitorados.
    Inclui hosts sem interface (LEFT JOIN) para não perder hosts que
    existem no Zabbix mas sem IP cadastrado.
    """
    cur.execute("""
        SELECT h.hostid, h.host, h.name, h.status,
               COALESCE(i.ip,'') AS ip,
               COALESCE(i.dns,'') AS dns,
               COALESCE(i.port,'') AS porta,
               CASE WHEN h.status=0 THEN 'ativo' ELSE 'inativo' END AS status_txt
        FROM hosts h
        LEFT JOIN interface i ON i.hostid=h.hostid AND i.main=1
        WHERE h.flags = 0
          AND h.status IN (0, 1)
        ORDER BY h.host
    """)
    return cur.fetchall()


def get_host_tags(cur):
    cur.execute("""
        SELECT h.hostid, h.host, ht.tag, ht.value
        FROM host_tag ht
        JOIN hosts h ON h.hostid = ht.hostid
        WHERE h.flags = 0
          AND h.status IN (0, 1)
        ORDER BY h.host, ht.tag
    """)
    return cur.fetchall()


def get_groups(cur):
    cur.execute("""
        SELECT hg.groupid, hg.name,
               ARRAY_AGG(hgh.hostid) AS host_ids
        FROM hstgrp hg
        LEFT JOIN hosts_groups hgh ON hgh.groupid=hg.groupid
        GROUP BY hg.groupid, hg.name
    """)
    return cur.fetchall()


def get_interfaces(cur):
    cur.execute("""
        SELECT interfaceid, hostid,
               COALESCE(ip,'') AS ip,
               COALESCE(dns,'') AS dns,
               COALESCE(port,'') AS port,
               type, main
        FROM interface
    """)
    return cur.fetchall()


def get_templates(cur):
    cur.execute("""
        SELECT ht.hostid, ht.templateid,
               t.host AS template_nome
        FROM hosts_templates ht
        JOIN hosts t ON t.hostid=ht.templateid
    """)
    return cur.fetchall()


def get_items(cur):
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
    cur.execute("""
        SELECT DISTINCT t.triggerid, t.description,
               t.priority, t.value, t.status, t.flags,
               h.hostid
        FROM triggers t
        JOIN functions f ON f.triggerid=t.triggerid
        JOIN items i ON i.itemid=f.itemid
        JOIN hosts h ON h.hostid=i.hostid
        WHERE t.status=0
    """)
    return cur.fetchall()


def get_eventos(cur, desde_ts):
    cur.execute("""
        SELECT eventid, objectid AS triggerid,
               clock, value, severity
        FROM events
        WHERE source=0 AND object=0
          AND clock > %s
        ORDER BY clock DESC
    """, (desde_ts,))
    return cur.fetchall()


def get_problemas_ativos(cur):
    """
    Busca TODOS os problemas da tabela 'problem'.
    - acknowledged=1 significa reconhecido no Zabbix
    - r_eventid IS NULL significa problema ainda ativo
    """
    cur.execute("""
        SELECT
            p.eventid,
            p.objectid AS triggerid,
            p.clock,
            p.severity,
            COALESCE(p.name, '') AS name,
            p.acknowledged,
            p.r_eventid,
            CASE WHEN p.r_eventid IS NULL THEN true ELSE false END AS ativo
        FROM problem p
        WHERE p.source = 0
        ORDER BY p.severity DESC, p.clock DESC
    """)
    return cur.fetchall()


def get_todos_acknowledgements(cur):
    """
    Busca TODOS os ACKs sem filtro de data.
    Usado na sincronização inicial para garantir paridade 1:1 com o Postgres.
    """
    cur.execute("""
        SELECT
            a.acknowledgeid,
            a.eventid,
            a.userid,
            a.clock,
            COALESCE(a.message, '') AS message,
            a.action,
            a.old_severity,
            a.new_severity,
            a.suppress_until,
            a.taskid
        FROM acknowledges a
        ORDER BY a.clock DESC
    """)
    return cur.fetchall()


def get_acknowledgements_por_eventos(cur, event_ids):
    """
    Busca TODOS os ACKs para uma lista de eventids.
    """
    if not event_ids:
        return []
    cur.execute("""
        SELECT
            a.acknowledgeid,
            a.eventid,
            a.userid,
            a.clock,
            COALESCE(a.message, '') AS message,
            a.action,
            a.old_severity,
            a.new_severity,
            a.suppress_until,
            a.taskid
        FROM acknowledges a
        WHERE a.eventid = ANY(%s)
        ORDER BY a.clock DESC
    """, (list(event_ids),))
    return cur.fetchall()


def get_acknowledgements(cur, desde_ts):
    """
    Busca ACKs recentes para sincronização incremental.
    """
    cur.execute("""
        SELECT
            a.acknowledgeid,
            a.eventid,
            a.userid,
            a.clock,
            COALESCE(a.message, '') AS message,
            a.action,
            a.old_severity,
            a.new_severity,
            a.suppress_until,
            a.taskid
        FROM acknowledges a
        WHERE a.clock > %s
        ORDER BY a.clock DESC
        LIMIT 5000
    """, (desde_ts,))
    return cur.fetchall()


def get_todos_event_ids_problemas(cur):
    """
    Retorna todos os eventids da tabela problem.
    Usado para limpar nós :Problem obsoletos do Neo4j.
    """
    cur.execute("SELECT eventid FROM problem WHERE source=0")
    return [r["eventid"] for r in cur.fetchall()]


def get_metricas_recentes(cur, limite=10000):
    """
    Busca as métricas mais recentes de cada item.
    Usa DISTINCT ON (itemid) para pegar apenas o valor mais recente por item.
    limite=10000 por tipo (float + uint) para cobrir todos os itens monitorados.
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
