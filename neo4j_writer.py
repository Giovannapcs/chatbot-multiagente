#!/usr/bin/env python3
"""
neo4j_writer.py — Escrita fiel no Neo4j espelhando o PostgreSQL Zabbix 1:1

Estrutura de grafo:
  (:Host)-[:TEM_TRIGGER]->(:Trigger)-[:GEROU]->(:Evento)
  (:Evento)-[:VIROU_PROBLEMA]->(:Problem)
  (:Trigger)-[:GEROU_PROBLEMA]->(:Problem)
  (:Evento)-[:TEM_ACK]->(:Acknowledge)
  (:Problem)-[:TEM_ACK]->(:Acknowledge)
"""
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
            MERGE (host:Host {hostid:$hid})
            SET host.host=$host,
                host.name=$name,
                host.status=$status,
                host.status_txt=$status_txt,
                host.ip=$ip,
                host.dns=$dns,
                host.porta=$porta,
                host.sync=$sync,
                host.removido=false
        """,
        hid=h["hostid"],
        host=h["host"],
        name=h["name"],
        status=h["status"],
        status_txt=h["status_txt"],
        ip=h["ip"] or "",
        dns=h["dns"] or "",
        porta=h["porta"] or "",
        sync=datetime.now().isoformat())


def marcar_hosts_removidos(session, host_ids_atuais):
    session.run("""
        MATCH (h:Host)
        WHERE NOT toString(h.hostid) IN $ids
        SET h.removido=true
    """, ids=[str(i) for i in host_ids_atuais])


def write_host_tags(session, tags):
    for t in tags:
        session.run("""
            MATCH (h:Host {hostid:$hid})
            MERGE (tag:Tag {chave:$chave, valor:$valor})
            MERGE (h)-[:TEM_TAG]->(tag)
        """,
        hid=t["hostid"],
        chave=t["tag"],
        valor=t["value"] or "")


def write_groups(session, groups):
    for g in groups:
        session.run("""
            MERGE (grp:Grupo {groupid:$gid})
            SET grp.name=$name
        """,
        gid=g["groupid"],
        name=g["name"])

        if g["host_ids"]:
            for hid in g["host_ids"]:
                if hid:
                    session.run("""
                        MATCH (h:Host {hostid:$hid})
                        MATCH (grp:Grupo {groupid:$gid})
                        MERGE (h)-[:PERTENCE_A]->(grp)
                    """,
                    hid=hid,
                    gid=g["groupid"])


def write_interfaces(session, interfaces):
    for i in interfaces:
        session.run("""
            MERGE (n:Interface {interfaceid:$iid})
            SET n.ip=$ip,
                n.dns=$dns,
                n.port=$port,
                n.type=$type,
                n.main=$main
            WITH n
            MATCH (h:Host {hostid:$hid})
            MERGE (h)-[:TEM]->(n)
        """,
        iid=i["interfaceid"],
        ip=i["ip"] or "",
        dns=i["dns"] or "",
        port=i["port"] or "",
        type=i["type"],
        main=i["main"],
        hid=i["hostid"])


def write_templates(session, templates):
    for t in templates:
        session.run("""
            MERGE (tmpl:Template {templateid:$tid})
            SET tmpl.nome=$nome
            WITH tmpl
            MATCH (h:Host {hostid:$hid})
            MERGE (h)-[:USA]->(tmpl)
        """,
        tid=t["templateid"],
        nome=t["template_nome"],
        hid=t["hostid"])


def write_items(session, items):
    for i in items:
        session.run("""
            MERGE (item:Item {itemid:$iid})
            SET item.name=$name,
                item.key_=$key,
                item.value_type=$vtype,
                item.units=$units
            WITH item
            MATCH (h:Host {hostid:$hid})
            MERGE (h)-[:TEM_ITEM]->(item)
        """,
        iid=i["itemid"],
        name=i["name"],
        key=i["key_"],
        vtype=i["value_type"],
        units=i["units"],
        hid=i["hostid"])


def write_triggers(session, triggers):
    for t in triggers:
        session.run("""
            MERGE (trig:Trigger {triggerid:$tid})
            SET trig.description=$desc,
                trig.priority=$priority,
                trig.value=$value
            WITH trig
            MATCH (h:Host {hostid:$hid})
            MERGE (h)-[:TEM_TRIGGER]->(trig)
        """,
        tid=t["triggerid"],
        desc=t["description"],
        priority=t["priority"],
        value=t["value"],
        hid=t["hostid"])


def write_eventos(session, eventos):
    for e in eventos:
        ts = datetime.fromtimestamp(e["clock"]).isoformat()
        session.run("""
            MERGE (ev:Evento {eventid:$eid})
            SET ev.clock=$clock,
                ev.severity=$sev,
                ev.value=$val,
                ev.timestamp=$ts
            WITH ev
            MATCH (t:Trigger {triggerid:$tid})
            MERGE (t)-[:GEROU]->(ev)
        """,
        eid=e["eventid"],
        clock=e["clock"],
        sev=e["severity"],
        val=e["value"],
        ts=ts,
        tid=e["triggerid"])


def write_problemas(session, problemas):
    """
    Grava nós :Problem espelhando a tabela 'problem' do Zabbix 1:1.
    """
    for p in problemas:
        ts = datetime.fromtimestamp(p["clock"]).isoformat()
        acknowledged = bool(p.get("acknowledged", 0))
        ativo = bool(p.get("ativo", True))

        # Garante que o :Evento existe
        session.run("""
            MERGE (ev:Evento {eventid:$eid})
            ON CREATE SET
                ev.clock=$clock,
                ev.timestamp=$ts,
                ev.severity=$sev,
                ev.value=1
        """,
        eid=p["eventid"],
        clock=p["clock"],
        ts=ts,
        sev=p["severity"])

        # Cria/atualiza o :Problem
        session.run("""
            MATCH (ev:Evento {eventid:$eid})
            MERGE (pr:Problem {eventid:$eid})
            SET pr.name=$name,
                pr.severity=$sev,
                pr.clock=$clock,
                pr.timestamp=$ts,
                pr.ativo=$ativo,
                pr.acknowledged=$acknowledged,
                pr.r_eventid=$r_eventid
            MERGE (ev)-[:VIROU_PROBLEMA]->(pr)
            WITH pr
            MATCH (t:Trigger {triggerid:$tid})
            MERGE (t)-[:GEROU_PROBLEMA]->(pr)
        """,
        eid=p["eventid"],
        name=p["name"],
        sev=p["severity"],
        clock=p["clock"],
        ts=ts,
        ativo=ativo,
        acknowledged=acknowledged,
        r_eventid=p.get("r_eventid"),
        tid=p["triggerid"])


def limpar_problemas_obsoletos(session, event_ids_pg):
    """
    Remove do Neo4j nós :Problem que não existem mais no PostgreSQL.
    Garante que o Neo4j não tenha mais registros do que o Postgres.
    """
    session.run("""
        MATCH (pr:Problem)
        WHERE NOT pr.eventid IN $ids
        DETACH DELETE pr
    """, ids=list(event_ids_pg))


def write_acknowledgements(session, acks):
    """
    Grava nós :Acknowledge espelhando a tabela 'acknowledges' do Zabbix 1:1.
    Usa MERGE no :Evento para garantir que ACKs de eventos fora da janela
    de 7 dias também sejam gravados corretamente.
    """
    for a in acks:
        ts = datetime.fromtimestamp(a["clock"]).isoformat()

        session.run("""
            MERGE (ev:Evento {eventid:$eid})
            ON CREATE SET
                ev.clock=$clock,
                ev.timestamp=$ts,
                ev.value=1,
                ev.severity=0
            MERGE (ack:Acknowledge {acknowledgeid:$ackid})
            SET ack.eventid=$eid,
                ack.userid=$userid,
                ack.clock=$clock,
                ack.timestamp=$ts,
                ack.message=$message,
                ack.action=$action,
                ack.old_severity=$old_severity,
                ack.new_severity=$new_severity,
                ack.suppress_until=$suppress_until,
                ack.taskid=$taskid
            MERGE (ev)-[:TEM_ACK]->(ack)
            SET ev.acknowledged=true,
                ev.last_ack_clock=$clock,
                ev.last_ack_timestamp=$ts,
                ev.last_ack_userid=$userid,
                ev.last_ack_message=$message
            WITH ev, ack
            OPTIONAL MATCH (ev)-[:VIROU_PROBLEMA]->(pr:Problem)
            FOREACH (p IN CASE WHEN pr IS NOT NULL THEN [pr] ELSE [] END |
                MERGE (p)-[:TEM_ACK]->(ack)
                SET p.acknowledged=true
            )
        """,
        ackid=a["acknowledgeid"],
        eid=a["eventid"],
        userid=a["userid"],
        clock=a["clock"],
        ts=ts,
        message=a["message"] or "",
        action=a["action"],
        old_severity=a["old_severity"],
        new_severity=a["new_severity"],
        suppress_until=a["suppress_until"],
        taskid=a["taskid"])


def limpar_acks_obsoletos(session, ack_ids_pg):
    """
    Remove do Neo4j nós :Acknowledge que não existem mais no PostgreSQL.
    """
    session.run("""
        MATCH (ack:Acknowledge)
        WHERE NOT ack.acknowledgeid IN $ids
        DETACH DELETE ack
    """, ids=list(ack_ids_pg))


def write_metricas(session, metricas):
    for m in metricas:
        uid = f"{m['itemid']}_{m['clock']}"
        ts = datetime.fromtimestamp(m["clock"]).isoformat()
        try:
            valor = float(m["value"])
        except Exception:
            valor = 0.0

        session.run("""
            MERGE (met:Metrica {id:$uid})
            SET met.clock=$clock,
                met.value=$val,
                met.tipo=$tipo,
                met.timestamp=$ts
            WITH met
            MATCH (i:Item {itemid:$iid})
            MERGE (i)-[:TEM_VALOR]->(met)
            WITH met, i
            MATCH (h:Host)-[:TEM_ITEM]->(i)
            MERGE (h)-[:TEVE_METRICA]->(met)
        """,
        uid=uid,
        clock=m["clock"],
        val=valor,
        tipo=m["tipo"],
        ts=ts,
        iid=m["itemid"])
