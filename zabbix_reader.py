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
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn

def get_hosts(cur):
    cur.execute("""
        SELECT h.hostid, h.host, h.name, h.status,
               COALESCE(i.ip,"") AS ip, COALESCE(i.dns,"") AS dns
        FROM hosts h
        LEFT JOIN interface i ON i.hostid=h.hostid AND i.main=1
        WHERE h.flags=0 ORDER BY h.hostid
    """)
    return cur.fetchall()

def get_groups(cur):
    cur.execute("""
        SELECT hg.groupid, hg.name,
               ARRAY_AGG(hgh.hostid) AS host_ids
        FROM hostgroups hg
        LEFT JOIN hosts_groups hgh ON hgh.groupid=hg.groupid
        GROUP BY hg.groupid, hg.name
    """)
    return cur.fetchall()

def get_items(cur):
    cur.execute("""
        SELECT itemid, hostid, name, key_,
               value_type, COALESCE(units,"") AS units
        FROM items WHERE flags=0 AND status=0
    """)
    return cur.fetchall()

def get_triggers(cur):
    cur.execute("""
        SELECT DISTINCT t.triggerid, t.description,
               t.priority, t.value, h.hostid
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
        WHERE source=0 AND object=0 AND clock > %s
        ORDER BY clock DESC LIMIT 1000
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
