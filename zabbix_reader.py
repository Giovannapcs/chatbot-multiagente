#!/usr/bin/env python3
import os, psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv("config.env")

def get_connection():
    conn = psycopg2.connect(
        host=os.getenv("ZABBIX_DB_HOST"),
        port=int(os.getenv("ZABBIX_DB_PORT","5432")),
        dbname=os.getenv("ZABBIX_DB_NAME"),
        user=os.getenv("ZABBIX_DB_USER"),
        password=os.getenv("ZABBIX_DB_PASS"),
        cursor_factory=RealDictCursor
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn

def get_hosts(cur):
    cur.execute("""
        SELECT h.hostid, h.host, h.name, h.status,
               COALESCE(i.ip,'') AS ip,
               COALESCE(i.dns,'') AS dns,
               COALESCE(i.port,'') AS porta
        FROM hosts h
        LEFT JOIN interface i ON i.hostid=h.hostid AND i.main=1
        WHERE h.flags=0
        ORDER BY h.hostid
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
    cur.execute("""
        SELECT eventid, objectid AS triggerid,
               clock, value, severity
        FROM events
        WHERE source=0 AND object=0
          AND clock > %s
        ORDER BY clock DESC LIMIT 2000
    """, (desde_ts,))
    return cur.fetchall()

def get_problemas_ativos(cur):
    cur.execute("""
        SELECT eventid, objectid AS triggerid,
               clock, severity, name
        FROM problem WHERE source=0
        ORDER BY severity DESC, clock DESC
    """)
    return cur.fetchall()

def get_metricas_recentes(cur, limite=5000):
    cur.execute("""
        SELECT DISTINCT ON (itemid)
               itemid, clock,
               ROUND(value::numeric,4) AS value,
               'float' AS tipo
        FROM history
        ORDER BY itemid, clock DESC
        LIMIT %s
    """, (limite,))
    floats = cur.fetchall()
    cur.execute("""
        SELECT DISTINCT ON (itemid)
               itemid, clock,
               value::numeric AS value,
               'uint' AS tipo
        FROM history_uint
        ORDER BY itemid, clock DESC
        LIMIT %s
    """, (limite,))
    uints = cur.fetchall()
    return floats + uints
