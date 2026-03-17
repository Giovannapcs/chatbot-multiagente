#!/usr/bin/env python3
import os
from datetime import datetime
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv("config.env")

def get_driver():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
    )

def write_hosts(session, hosts):
    for h in hosts:
        session.run("""
            MERGE (host:Host {hostid: $hid})
            SET host.host=$host, host.name=$name,
                host.status=$status, host.ip=$ip,
                host.dns=$dns, host.sync=$sync
        """, hid=h["hostid"], host=h["host"], name=h["name"],
             status=h["status"], ip=h["ip"], dns=h["dns"],
             sync=datetime.now().isoformat())

def write_groups(session, groups):
    for g in groups:
        session.run("MERGE (grp:Grupo {groupid: $gid}) SET grp.name=$name",
            gid=g["groupid"], name=g["name"])
        if g["host_ids"]:
            for hid in g["host_ids"]:
                if hid:
                    session.run("""
                        MATCH (h:Host {hostid: $hid})
                        MATCH (g:Grupo {groupid: $gid})
                        MERGE (h)-[:PERTENCE_A]->(g)
                    """, hid=hid, gid=g["groupid"])

def write_items(session, items):
    for i in items:
        session.run("""
            MERGE (item:Item {itemid: $iid})
            SET item.name=$name, item.key_=$key,
                item.value_type=$vtype, item.units=$units
            WITH item
            MATCH (h:Host {hostid: $hid})
            MERGE (h)-[:TEM_ITEM]->(item)
        """, iid=i["itemid"], name=i["name"], key=i["key_"],
             vtype=i["value_type"], units=i["units"], hid=i["hostid"])

def write_triggers(session, triggers):
    for t in triggers:
        session.run("""
            MERGE (trig:Trigger {triggerid: $tid})
            SET trig.description=$desc,
                trig.priority=$priority, trig.value=$value
            WITH trig
            MATCH (h:Host {hostid: $hid})
            MERGE (h)-[:TEM_TRIGGER]->(trig)
        """, tid=t["triggerid"], desc=t["description"],
             priority=t["priority"], value=t["value"], hid=t["hostid"])

def write_eventos(session, eventos):
    for e in eventos:
        ts = datetime.fromtimestamp(e["clock"]).isoformat()
        session.run("""
            MERGE (ev:Evento {eventid: $eid})
            SET ev.clock=$clock, ev.severity=$sev,
                ev.value=$val, ev.timestamp=$ts
            WITH ev
            MATCH (t:Trigger {triggerid: $tid})
            MERGE (t)-[:GEROU]->(ev)
        """, eid=e["eventid"], clock=e["clock"],
             sev=e["severity"], val=e["value"],
             ts=ts, tid=e["triggerid"])

def write_problemas(session, problemas):
    for p in problemas:
        ts = datetime.fromtimestamp(p["clock"]).isoformat()
        session.run("""
            MERGE (prob:Problema {eventid: $eid})
            SET prob.name=$name, prob.severity=$sev,
                prob.clock=$clock, prob.timestamp=$ts
            WITH prob
            MATCH (t:Trigger {triggerid: $tid})
            MERGE (t)-[:GEROU_PROBLEMA]->(prob)
        """, eid=p["eventid"], name=p["name"],
             sev=p["severity"], clock=p["clock"],
             ts=ts, tid=p["triggerid"])
