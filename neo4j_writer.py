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
                host.removido=false,
                host.data_desabilitado = CASE
                    WHEN host.status = 0 AND $status = 1 THEN $sync
                    WHEN $status = 0 THEN null
                    ELSE host.data_desabilitado
                END
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
    """
    session.run("""
        MATCH (pr:Problem)
        WHERE NOT pr.eventid IN $ids
        DETACH DELETE pr
    """, ids=list(event_ids_pg))


def write_acknowledgements(session, acks):
    """
    Grava nós :Acknowledge espelhando a tabela 'acknowledges' do Zabbix 1:1.
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


# =============================================================================
# QUERIES DE LEITURA — USO EXCLUSIVO NOS RELATORIOS (Lambda do Caike)
# =============================================================================


# -----------------------------------------------------------------------------
# RELATORIO: Incidentes Alto e Desastre no Zabbix (Mensal)
# -----------------------------------------------------------------------------

def query_incidentes_alto_desastre_totais(session, inicio_ts):
    result = session.run("""
        MATCH (pr:Problem)
        WHERE pr.clock IS NOT NULL
          AND toInteger(pr.clock) >= $inicio_ts
          AND toInteger(pr.severity) IN [4, 5]
        RETURN
            count(DISTINCT CASE
                WHEN toInteger(pr.severity) = 4 THEN pr
            END) AS total_alto,
            count(DISTINCT CASE
                WHEN toInteger(pr.severity) = 5 THEN pr
            END) AS total_desastre,
            count(DISTINCT pr) AS total_geral
    """, inicio_ts=inicio_ts)
    record = result.single()
    if not record:
        return {"total_alto": 0, "total_desastre": 0, "total_geral": 0}
    return {
        "total_alto":     int(record["total_alto"]     or 0),
        "total_desastre": int(record["total_desastre"] or 0),
        "total_geral":    int(record["total_geral"]    or 0),
    }


def query_incidentes_alto_desastre_tabela(session, inicio_ts, limite=50):
    rows = session.run("""
        MATCH (h:Host)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU_PROBLEMA]->(pr:Problem)
        WHERE pr.clock IS NOT NULL
          AND toInteger(pr.clock) >= $inicio_ts
          AND toInteger(pr.severity) IN [4, 5]
          AND (h.removido IS NULL OR h.removido = false)
        RETURN
            h.host                                          AS host,
            t.description                                   AS trigger,
            CASE toInteger(pr.severity)
                WHEN 4 THEN 'Alto'
                WHEN 5 THEN 'Desastre'
            END                                             AS severidade,
            datetime({epochSeconds: toInteger(pr.clock)}).toString()
                                                            AS data_hora,
            coalesce(pr.name, t.description)                AS nome_problema
        ORDER BY toInteger(pr.severity) DESC, toInteger(pr.clock) DESC
        LIMIT $limite
    """, inicio_ts=inicio_ts, limite=limite)
    return [
        {
            "host":          r["host"]          or "",
            "trigger":       r["trigger"]        or "",
            "severidade":    r["severidade"]     or "",
            "data_hora":     r["data_hora"]      or "",
            "nome_problema": r["nome_problema"]  or "",
        }
        for r in rows
    ]


def build_evidence_incidentes_alto_desastre(session, dias=30):
    import time
    inicio_ts = int(time.time()) - (dias * 86400)
    totais = query_incidentes_alto_desastre_totais(session, inicio_ts)
    tabela = query_incidentes_alto_desastre_tabela(session, inicio_ts, limite=50)
    return {
        "total_alto":        totais["total_alto"],
        "total_desastre":    totais["total_desastre"],
        "total_geral":       totais["total_geral"],
        "tabela_incidentes": tabela,
    }


# -----------------------------------------------------------------------------
# RELATORIO: Hosts Desabilitados no Zabbix (Mensal)
# -----------------------------------------------------------------------------

def query_hosts_desabilitados_total(session):
    result = session.run("""
        MATCH (h:Host)
        WHERE toInteger(h.status) = 1
          AND (h.removido IS NULL OR h.removido = false)
        RETURN count(h) AS total
    """)
    record = result.single()
    return int(record["total"] or 0) if record else 0


def query_hosts_desabilitados_tabela(session, limite=200):
    rows = session.run("""
        MATCH (h:Host)
        WHERE toInteger(h.status) = 1
          AND (h.removido IS NULL OR h.removido = false)
        OPTIONAL MATCH (h)-[:PERTENCE_A]->(g:Grupo)
        RETURN
            h.host                                  AS host,
            h.name                                  AS nome,
            coalesce(h.ip, '')                      AS ip,
            coalesce(h.porta, '')                   AS porta,
            coalesce(h.data_desabilitado, 'N/A')    AS data_desabilitado,
            collect(coalesce(g.name,''))             AS grupos_lista
        ORDER BY h.host
        LIMIT $limite
    """, limite=limite)

    resultado = []
    for r in rows:
        grupos = [g for g in r["grupos_lista"] if g]
        resultado.append({
            "host":               r["host"]              or "",
            "nome":               r["nome"]              or "",
            "ip":                 r["ip"]                or "",
            "porta":              r["porta"]             or "",
            "data_desabilitado":  r["data_desabilitado"] or "N/A",
            "grupos":             ", ".join(grupos) if grupos else "Sem grupo",
        })
    return resultado


def build_evidence_hosts_desabilitados(session):
    total  = query_hosts_desabilitados_total(session)
    tabela = query_hosts_desabilitados_tabela(session, limite=200)
    return {
        "total_desabilitados": total,
        "tabela_hosts":        tabela,
    }


# -----------------------------------------------------------------------------
# RELATORIO: Top 100 Triggers no Zabbix (Mensal)
# -----------------------------------------------------------------------------

def query_top100_triggers_total(session, inicio_ts):
    result = session.run("""
        MATCH (t:Trigger)-[:GEROU]->(e:Evento)
        WHERE toInteger(e.clock) >= $inicio_ts
        RETURN count(e) AS total_disparos,
               count(DISTINCT t) AS total_triggers
    """, inicio_ts=inicio_ts)
    record = result.single()
    if not record:
        return {"total_disparos": 0, "total_triggers": 0}
    return {
        "total_disparos": int(record["total_disparos"] or 0),
        "total_triggers": int(record["total_triggers"] or 0),
    }


def query_top100_triggers_tabela(session, inicio_ts, limite=100):
    rows = session.run("""
        MATCH (h:Host)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU]->(e:Evento)
        WHERE toInteger(e.clock) >= $inicio_ts
          AND (h.removido IS NULL OR h.removido = false)
        WITH
            h.host          AS host,
            t.description   AS trigger,
            CASE toInteger(t.priority)
                WHEN 0 THEN 'Nao classificado'
                WHEN 1 THEN 'Informacao'
                WHEN 2 THEN 'Aviso'
                WHEN 3 THEN 'Medio'
                WHEN 4 THEN 'Alto'
                WHEN 5 THEN 'Desastre'
            END             AS severidade,
            count(e)        AS total_disparos
        ORDER BY total_disparos DESC
        LIMIT $limite
        RETURN host, trigger, severidade, total_disparos
    """, inicio_ts=inicio_ts, limite=limite)

    resultado = []
    for i, r in enumerate(rows, start=1):
        resultado.append({
            "posicao":        i,
            "host":           r["host"]          or "",
            "trigger":        r["trigger"]        or "",
            "severidade":     r["severidade"]     or "",
            "total_disparos": int(r["total_disparos"] or 0),
        })
    return resultado


def build_evidence_top100_triggers(session, dias=30):
    import time
    inicio_ts = int(time.time()) - (dias * 86400)
    totais = query_top100_triggers_total(session, inicio_ts)
    tabela = query_top100_triggers_tabela(session, inicio_ts, limite=100)
    return {
        "total_disparos_mes":    totais["total_disparos"],
        "total_triggers_ativas": totais["total_triggers"],
        "tabela_triggers":       tabela,
    }


# -----------------------------------------------------------------------------
# RELATORIO: Itens Nao Suportados no Zabbix (Mensal)
# -----------------------------------------------------------------------------

def query_itens_nao_suportados_total(session):
    result = session.run("""
        MATCH (h:Host)-[:TEM_ITEM]->(i:Item)
        WHERE (h.removido IS NULL OR h.removido = false)
          AND toInteger(h.status) = 0
          AND NOT (i)-[:TEM_VALOR]->(:Metrica)
        RETURN count(i) AS total_nao_suportados,
               count(DISTINCT h) AS total_hosts_afetados
    """)
    record = result.single()
    if not record:
        return {"total_nao_suportados": 0, "total_hosts_afetados": 0}
    return {
        "total_nao_suportados":  int(record["total_nao_suportados"]  or 0),
        "total_hosts_afetados":  int(record["total_hosts_afetados"]  or 0),
    }


def query_itens_nao_suportados_tabela(session, limite=200):
    rows = session.run("""
        MATCH (h:Host)-[:TEM_ITEM]->(i:Item)
        WHERE (h.removido IS NULL OR h.removido = false)
          AND toInteger(h.status) = 0
          AND NOT (i)-[:TEM_VALOR]->(:Metrica)
        RETURN
            h.host          AS host,
            i.name          AS item,
            i.key_          AS chave,
            coalesce(i.units, '') AS unidade
        ORDER BY h.host, i.name
        LIMIT $limite
    """, limite=limite)

    return [
        {
            "host":    r["host"]    or "",
            "item":    r["item"]    or "",
            "chave":   r["chave"]   or "",
            "unidade": r["unidade"] or "",
        }
        for r in rows
    ]


def query_itens_total(session):
    result = session.run("""
        MATCH (i:Item) RETURN count(i) AS total
    """)
    record = result.single()
    return int(record["total"] or 0) if record else 0


def build_evidence_itens_nao_suportados(session):
    totais = query_itens_nao_suportados_total(session)
    tabela = query_itens_nao_suportados_tabela(session, limite=200)
    total_itens = query_itens_total(session)
    return {
        "total_nao_suportados": totais["total_nao_suportados"],
        "total_hosts_afetados": totais["total_hosts_afetados"],
        "total_itens":          total_itens,
        "tabela_itens":         tabela,
    }


# -----------------------------------------------------------------------------
# RELATORIO: Incidentes com mais de 60 dias em Problem Status (Mensal)
# -----------------------------------------------------------------------------

def query_incidentes_60dias_totais(session, limite_ts):
    result = session.run("""
        MATCH (pr:Problem)
        WHERE pr.clock IS NOT NULL
          AND toInteger(pr.clock) < $limite_ts
          AND pr.ativo = true
        RETURN
            count(pr) AS total_cronicos,
            count(CASE WHEN toInteger(pr.severity) IN [4,5] THEN pr END) AS total_criticos,
            min(toInteger(pr.clock)) AS mais_antigo_ts
    """, limite_ts=limite_ts)
    record = result.single()
    if not record:
        return {"total_cronicos": 0, "total_criticos": 0, "mais_antigo_dias": 0}
    import time
    mais_antigo_ts = record["mais_antigo_ts"]
    mais_antigo_dias = int((time.time() - mais_antigo_ts) / 86400) if mais_antigo_ts else 0
    return {
        "total_cronicos":   int(record["total_cronicos"]  or 0),
        "total_criticos":   int(record["total_criticos"]  or 0),
        "mais_antigo_dias": mais_antigo_dias,
    }


def query_incidentes_60dias_tabela(session, limite_ts, limite=100):
    import time
    agora = int(time.time())
    rows = session.run("""
        MATCH (pr:Problem)
        WHERE pr.clock IS NOT NULL
          AND toInteger(pr.clock) < $limite_ts
          AND pr.ativo = true
        OPTIONAL MATCH (t:Trigger)-[:GEROU_PROBLEMA]->(pr)
        OPTIONAL MATCH (h:Host)-[:TEM_TRIGGER]->(t)
        RETURN
            coalesce(h.host, 'N/A')         AS host,
            coalesce(t.description, 'N/A')  AS trigger,
            coalesce(pr.name, t.description, 'N/A') AS problema,
            CASE toInteger(pr.severity)
                WHEN 0 THEN 'Nao classificado'
                WHEN 1 THEN 'Informacao'
                WHEN 2 THEN 'Aviso'
                WHEN 3 THEN 'Medio'
                WHEN 4 THEN 'Alto'
                WHEN 5 THEN 'Desastre'
            END                             AS severidade,
            toInteger(pr.severity)          AS severity_num,
            toString(toInteger(pr.clock)) AS data_abertura,
            toInteger(pr.clock)             AS clock
        ORDER BY toInteger(pr.clock) ASC
        LIMIT $limite
    """, limite_ts=limite_ts, limite=limite)

    resultado = []
    for r in rows:
        dias = int((agora - r["clock"]) / 86400)
        from datetime import datetime
        ts = r["clock"]
        data_fmt = datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M") if ts else ""
        resultado.append({
            "host":          r["host"]         or "",
            "trigger":       r["trigger"]       or "",
            "problema":      r["problema"]      or "",
            "severidade":    r["severidade"]    or "",
            "data_abertura": data_fmt,
            "dias_aberto":   dias,
        })
    return resultado


def build_evidence_incidentes_60dias(session, dias=60):
    import time
    limite_ts = int(time.time()) - (dias * 86400)
    totais = query_incidentes_60dias_totais(session, limite_ts)
    tabela = query_incidentes_60dias_tabela(session, limite_ts, limite=100)
    return {
        "total_cronicos":   totais["total_cronicos"],
        "total_criticos":   totais["total_criticos"],
        "mais_antigo_dias": totais["mais_antigo_dias"],
        "tabela_cronicos":  tabela,
    }


# -----------------------------------------------------------------------------
# RELATORIO: Top 10 Hosts com Maior Volume de Alertas (Mensal)
# -----------------------------------------------------------------------------

def query_top10_hosts_totais(session, inicio_ts):
    result = session.run("""
        MATCH (h:Host)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU]->(e:Evento)
        WHERE toInteger(e.clock) >= $inicio_ts
          AND (h.removido IS NULL OR h.removido = false)
        RETURN
            count(e)            AS total_alertas,
            count(DISTINCT h)   AS total_hosts
    """, inicio_ts=inicio_ts)
    record = result.single()
    if not record:
        return {"total_alertas": 0, "total_hosts": 0}
    return {
        "total_alertas": int(record["total_alertas"] or 0),
        "total_hosts":   int(record["total_hosts"]   or 0),
    }


def query_top10_hosts_tabela(session, inicio_ts, limite=10):
    rows = session.run("""
        MATCH (h:Host)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU]->(e:Evento)
        WHERE toInteger(e.clock) >= $inicio_ts
          AND (h.removido IS NULL OR h.removido = false)
        WITH
            h.host          AS host,
            coalesce(h.ip, '') AS ip,
            count(e)        AS total_alertas,
            count(DISTINCT t) AS triggers_distintos,
            count(DISTINCT CASE
                WHEN toInteger(t.priority) IN [4, 5] THEN e
            END)            AS alertas_criticos
        ORDER BY total_alertas DESC
        LIMIT $limite
        RETURN host, ip, total_alertas, triggers_distintos, alertas_criticos
    """, inicio_ts=inicio_ts, limite=limite)

    resultado = []
    for i, r in enumerate(rows, start=1):
        resultado.append({
            "posicao":            i,
            "host":               r["host"]              or "",
            "ip":                 r["ip"]                or "",
            "total_alertas":      int(r["total_alertas"]      or 0),
            "alertas_criticos":   int(r["alertas_criticos"]   or 0),
            "triggers_distintos": int(r["triggers_distintos"] or 0),
        })
    return resultado


def build_evidence_top10_hosts_alertas(session, dias=30):
    import time
    inicio_ts = int(time.time()) - (dias * 86400)
    totais = query_top10_hosts_totais(session, inicio_ts)
    tabela = query_top10_hosts_tabela(session, inicio_ts, limite=10)
    return {
        "total_alertas_mes":       totais["total_alertas"],
        "total_hosts_com_alerta":  totais["total_hosts"],
        "tabela_top10":            tabela,
    }


# -----------------------------------------------------------------------------
# RELATORIO: Tendencia de Reducao de Incidentes (Trimestral)
# -----------------------------------------------------------------------------

def query_tendencia_por_mes(session, inicio_ts):
    rows = session.run("""
        MATCH (pr:Problem)
        WHERE pr.clock IS NOT NULL
          AND toInteger(pr.clock) >= $inicio_ts
        WITH
            datetime({epochSeconds: toInteger(pr.clock)}) AS dt,
            pr
        WITH
            dt.year  AS ano,
            dt.month AS mes,
            pr
        RETURN
            ano,
            mes,
            count(pr)                                           AS total,
            count(CASE WHEN toInteger(pr.severity) IN [4,5]
                       THEN pr END)                            AS criticos,
            count(CASE WHEN pr.ativo = true THEN pr END)       AS ainda_abertos
        ORDER BY ano ASC, mes ASC
    """, inicio_ts=inicio_ts)

    return [
        {
            "ano":           r["ano"],
            "mes":           r["mes"],
            "total":         int(r["total"]         or 0),
            "criticos":      int(r["criticos"]       or 0),
            "ainda_abertos": int(r["ainda_abertos"]  or 0),
        }
        for r in rows
    ]


def build_evidence_tendencia_reducao(session, dias=90):
    import time
    inicio_ts = int(time.time()) - (dias * 86400)
    meses = query_tendencia_por_mes(session, inicio_ts)

    total_trimestre = sum(m["total"] for m in meses)

    def variacao(anterior, atual):
        if anterior == 0:
            return "+100%" if atual > 0 else "0%"
        pct = round(((atual - anterior) / anterior) * 100, 1)
        return f"+{pct}%" if pct > 0 else f"{pct}%"

    tabela = []
    for i, m in enumerate(meses):
        var = variacao(meses[i-1]["total"], m["total"]) if i > 0 else "-"
        tabela.append({
            "mes":           f"{m['ano']}-{str(m['mes']).zfill(2)}",
            "total":         m["total"],
            "criticos":      m["criticos"],
            "ainda_abertos": m["ainda_abertos"],
            "variacao":      var,
        })

    variacao_m1_m2 = variacao(meses[0]["total"], meses[1]["total"]) if len(meses) >= 2 else "0%"
    variacao_m2_m3 = variacao(meses[1]["total"], meses[2]["total"]) if len(meses) >= 3 else "0%"

    if len(meses) >= 2:
        diff = meses[-1]["total"] - meses[0]["total"]
        tendencia_geral = "Reducao" if diff < 0 else "Aumento" if diff > 0 else "Estavel"
    else:
        tendencia_geral = "Estavel"

    return {
        "total_trimestre": total_trimestre,
        "variacao_m1_m2":  variacao_m1_m2,
        "variacao_m2_m3":  variacao_m2_m3,
        "tendencia_geral": tendencia_geral,
        "tabela_mensal":   tabela,
    }


# -----------------------------------------------------------------------------
# RELATORIO: Comparativo de SLA (Trimestral)
# -----------------------------------------------------------------------------

def query_sla_por_mes(session, inicio_ts, sla_minutos=15):
    sla_segundos = sla_minutos * 60
    rows = session.run("""
        MATCH (pr:Problem)
        WHERE pr.clock IS NOT NULL
          AND toInteger(pr.clock) >= $inicio_ts
        OPTIONAL MATCH (pr)-[:TEM_ACK]->(ack:Acknowledge)
        WITH
            datetime({epochSeconds: toInteger(pr.clock)}) AS dt,
            pr,
            min(toInteger(ack.clock)) AS primeiro_ack
        WITH
            dt.year  AS ano,
            dt.month AS mes,
            pr,
            primeiro_ack,
            CASE
                WHEN primeiro_ack IS NOT NULL
                 AND primeiro_ack >= toInteger(pr.clock)
                THEN (primeiro_ack - toInteger(pr.clock)) / 60.0
                ELSE NULL
            END AS mtta_min
        RETURN
            ano,
            mes,
            count(DISTINCT pr)                              AS total,
            count(DISTINCT CASE
                WHEN primeiro_ack IS NOT NULL THEN pr
            END)                                            AS reconhecidos,
            round(avg(mtta_min), 2)                         AS mtta_medio,
            count(DISTINCT CASE
                WHEN primeiro_ack IS NULL
                  OR (primeiro_ack - toInteger(pr.clock)) > $sla_seg
                THEN pr
            END)                                            AS acima_sla
        ORDER BY ano ASC, mes ASC
    """, inicio_ts=inicio_ts, sla_seg=sla_segundos)

    resultado = []
    for r in rows:
        total    = int(r["total"]       or 0)
        ac_sla   = int(r["acima_sla"]   or 0)
        sla_pct  = round(((total - ac_sla) / total) * 100, 2) if total > 0 else 100.0
        resultado.append({
            "ano":          r["ano"],
            "mes":          r["mes"],
            "total":        total,
            "reconhecidos": int(r["reconhecidos"] or 0),
            "mtta_medio":   round(float(r["mtta_medio"] or 0), 2),
            "acima_sla":    ac_sla,
            "sla_percentual": sla_pct,
        })
    return resultado


def build_evidence_comparativo_sla(session, dias=90, sla_minutos=15):
    import time
    inicio_ts = int(time.time()) - (dias * 86400)
    meses = query_sla_por_mes(session, inicio_ts, sla_minutos)

    tabela = [
        {
            "mes":            f"{m['ano']}-{str(m['mes']).zfill(2)}",
            "total":          m["total"],
            "reconhecidos":   m["reconhecidos"],
            "mtta_medio":     m["mtta_medio"],
            "acima_sla":      m["acima_sla"],
            "sla_percentual": m["sla_percentual"],
        }
        for m in meses
    ]

    total_trimestre  = sum(m["total"] for m in meses)
    sla_medio        = round(sum(m["sla_percentual"] for m in meses) / len(meses), 2) if meses else 0.0
    mtta_vals        = [m["mtta_medio"] for m in meses if m["mtta_medio"] > 0]
    mtta_medio       = round(sum(mtta_vals) / len(mtta_vals), 2) if mtta_vals else 0.0

    return {
        "sla_medio_trimestre":  sla_medio,
        "mtta_medio_trimestre": mtta_medio,
        "total_trimestre":      total_trimestre,
        "tabela_sla_mensal":    tabela,
    }


# -----------------------------------------------------------------------------
# RELATORIO: Desempenho do NOC (Trimestral)
# -----------------------------------------------------------------------------

def query_noc_por_mes(session, inicio_ts, sla_minutos=15):
    sla_segundos = sla_minutos * 60
    rows = session.run("""
        MATCH (pr:Problem)
        WHERE pr.clock IS NOT NULL
          AND toInteger(pr.clock) >= $inicio_ts
        OPTIONAL MATCH (pr)-[:TEM_ACK]->(ack:Acknowledge)
        OPTIONAL MATCH (t:Trigger)-[:GEROU_PROBLEMA]->(pr)
        OPTIONAL MATCH (t)-[:GEROU]->(fim:Evento {value: 0})
        WHERE fim.clock IS NOT NULL
          AND toInteger(fim.clock) > toInteger(pr.clock)
        WITH
            datetime({epochSeconds: toInteger(pr.clock)}) AS dt,
            pr,
            min(toInteger(ack.clock)) AS primeiro_ack,
            min(toInteger(fim.clock)) AS fim_clock
        WITH
            dt.year  AS ano,
            dt.month AS mes,
            pr,
            primeiro_ack,
            CASE
                WHEN fim_clock IS NOT NULL
                THEN fim_clock - toInteger(pr.clock)
                ELSE NULL
            END AS duracao_seg
        RETURN
            ano,
            mes,
            count(DISTINCT pr)                              AS total,
            count(DISTINCT CASE
                WHEN primeiro_ack IS NOT NULL THEN pr
            END)                                            AS reconhecidos,
            count(DISTINCT CASE
                WHEN primeiro_ack IS NOT NULL
                 AND (primeiro_ack - toInteger(pr.clock)) < 300
                THEN pr
            END)                                            AS ack_menor_5min,
            count(DISTINCT CASE
                WHEN primeiro_ack IS NOT NULL
                 AND (primeiro_ack - toInteger(pr.clock)) >= 300
                 AND (primeiro_ack - toInteger(pr.clock)) <= 900
                THEN pr
            END)                                            AS ack_5_a_15min,
            count(DISTINCT CASE
                WHEN primeiro_ack IS NOT NULL
                 AND (primeiro_ack - toInteger(pr.clock)) > 900
                THEN pr
            END)                                            AS ack_maior_15min,
            round(avg(CASE
                WHEN primeiro_ack IS NOT NULL
                 AND primeiro_ack >= toInteger(pr.clock)
                THEN (primeiro_ack - toInteger(pr.clock)) / 60.0
            END), 2)                                        AS mtta_medio,
            count(DISTINCT CASE
                WHEN duracao_seg IS NOT NULL
                 AND duracao_seg <= $sla_seg
                THEN pr
            END)                                            AS resolvidos_15min,
            count(DISTINCT CASE
                WHEN duracao_seg IS NULL
                  OR duracao_seg > $sla_seg
                THEN pr
            END)                                            AS nao_resolvidos_15min
        ORDER BY ano ASC, mes ASC
    """, inicio_ts=inicio_ts, sla_seg=sla_segundos)

    resultado = []
    for r in rows:
        total = int(r["total"] or 0)
        rec   = int(r["reconhecidos"] or 0)
        taxa  = round((rec / total) * 100, 1) if total > 0 else 0.0
        resultado.append({
            "ano":                    r["ano"],
            "mes":                    r["mes"],
            "total":                  total,
            "reconhecidos":           rec,
            "taxa_reconhecimento_pct": taxa,
            "ack_menor_5min":         int(r["ack_menor_5min"]      or 0),
            "ack_5_a_15min":          int(r["ack_5_a_15min"]       or 0),
            "ack_maior_15min":        int(r["ack_maior_15min"]      or 0),
            "mtta_medio":             round(float(r["mtta_medio"]   or 0), 2),
            "resolvidos_15min":       int(r["resolvidos_15min"]     or 0),
            "nao_resolvidos_15min":   int(r["nao_resolvidos_15min"] or 0),
        })
    return resultado


def build_evidence_desempenho_noc(session, dias=90, sla_minutos=15):
    import time
    inicio_ts = int(time.time()) - (dias * 86400)
    meses = query_noc_por_mes(session, inicio_ts, sla_minutos)

    tabela = [
        {
            "mes":                    f"{m['ano']}-{str(m['mes']).zfill(2)}",
            "total":                  m["total"],
            "reconhecidos":           m["reconhecidos"],
            "taxa_reconhecimento_pct": m["taxa_reconhecimento_pct"],
            "ack_menor_5min":         m["ack_menor_5min"],
            "ack_5_a_15min":          m["ack_5_a_15min"],
            "ack_maior_15min":        m["ack_maior_15min"],
            "mtta_medio":             m["mtta_medio"],
            "resolvidos_15min":       m["resolvidos_15min"],
            "nao_resolvidos_15min":   m["nao_resolvidos_15min"],
        }
        for m in meses
    ]

    total_trimestre = sum(m["total"] for m in meses)
    taxa_rec        = round(sum(m["taxa_reconhecimento_pct"] for m in meses) / len(meses), 1) if meses else 0.0
    mtta_vals       = [m["mtta_medio"] for m in meses if m["mtta_medio"] > 0]
    mtta_medio      = round(sum(mtta_vals) / len(mtta_vals), 2) if mtta_vals else 0.0

    return {
        "total_trimestre":      total_trimestre,
        "taxa_reconhecimento":  taxa_rec,
        "mtta_medio_trimestre": mtta_medio,
        "tabela_noc_mensal":    tabela,
    }


# =============================================================================
# QUERIES DE DASHBOARD
# =============================================================================


def query_status_hosts(session):
    result = session.run("""
        MATCH (h:Host)
        WHERE h.removido IS NULL OR h.removido = false
        OPTIONAL MATCH (h)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU_PROBLEMA]->(pr:Problem)
        WHERE pr.ativo = true
        WITH
            h,
            count(pr) AS problemas_ativos
        RETURN
            count(h)                                        AS total_hosts,
            count(CASE WHEN toInteger(h.status)=0 THEN h END) AS hosts_ativos,
            count(CASE WHEN toInteger(h.status)=1 THEN h END) AS hosts_inativos,
            count(CASE WHEN problemas_ativos > 0 THEN h END)  AS hosts_com_problema
    """)
    record = result.single()
    if not record:
        return {"total_hosts": 0, "hosts_ativos": 0, "hosts_inativos": 0, "hosts_com_problema": 0}
    return {
        "total_hosts":        int(record["total_hosts"]        or 0),
        "hosts_ativos":       int(record["hosts_ativos"]       or 0),
        "hosts_inativos":     int(record["hosts_inativos"]     or 0),
        "hosts_com_problema": int(record["hosts_com_problema"] or 0),
    }


def query_incidentes_abertos(session):
    result = session.run("""
        MATCH (pr:Problem)
        WHERE pr.ativo = true
        RETURN
            count(pr) AS total,
            count(CASE WHEN toInteger(pr.severity)=5 THEN pr END) AS desastre,
            count(CASE WHEN toInteger(pr.severity)=4 THEN pr END) AS alto,
            count(CASE WHEN toInteger(pr.severity)=3 THEN pr END) AS medio,
            count(CASE WHEN toInteger(pr.severity)=2 THEN pr END) AS aviso,
            count(CASE WHEN toInteger(pr.severity)=1 THEN pr END) AS informacao,
            count(CASE WHEN toInteger(pr.severity)=0 THEN pr END) AS nao_classificado,
            count(CASE WHEN pr.acknowledged=true THEN pr END)     AS reconhecidos
    """)
    record = result.single()
    if not record:
        return {}
    total = int(record["total"] or 0)
    rec   = int(record["reconhecidos"] or 0)
    return {
        "total":             total,
        "desastre":          int(record["desastre"]         or 0),
        "alto":              int(record["alto"]             or 0),
        "medio":             int(record["medio"]            or 0),
        "aviso":             int(record["aviso"]            or 0),
        "informacao":        int(record["informacao"]       or 0),
        "nao_classificado":  int(record["nao_classificado"] or 0),
        "reconhecidos":      rec,
        "nao_reconhecidos":  total - rec,
        "taxa_reconhecimento_pct": round((rec / total) * 100, 1) if total > 0 else 0.0,
    }


def query_top10_hosts_problema(session):
    rows = session.run("""
        MATCH (h:Host)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU_PROBLEMA]->(pr:Problem)
        WHERE pr.ativo = true
          AND (h.removido IS NULL OR h.removido = false)
        WITH
            h.host      AS host,
            h.ip        AS ip,
            count(pr)   AS total_problemas,
            count(CASE WHEN toInteger(pr.severity) IN [4,5] THEN pr END) AS criticos
        ORDER BY total_problemas DESC
        LIMIT 10
        RETURN host, ip, total_problemas, criticos
    """)
    return [
        {
            "host":            r["host"]            or "",
            "ip":              r["ip"]              or "",
            "total_problemas": int(r["total_problemas"] or 0),
            "criticos":        int(r["criticos"]        or 0),
        }
        for r in rows
    ]


def query_ultimos_incidentes(session, limite=10):
    import time
    agora = int(time.time())
    rows = session.run("""
        MATCH (pr:Problem)
        WHERE pr.ativo = true AND pr.clock IS NOT NULL
        OPTIONAL MATCH (t:Trigger)-[:GEROU_PROBLEMA]->(pr)
        OPTIONAL MATCH (h:Host)-[:TEM_TRIGGER]->(t)
        RETURN
            coalesce(h.host, 'N/A')                 AS host,
            coalesce(pr.name, t.description, 'N/A') AS problema,
            toInteger(pr.severity)                   AS severity,
            CASE toInteger(pr.severity)
                WHEN 0 THEN 'Nao classificado'
                WHEN 1 THEN 'Informacao'
                WHEN 2 THEN 'Aviso'
                WHEN 3 THEN 'Medio'
                WHEN 4 THEN 'Alto'
                WHEN 5 THEN 'Desastre'
            END                                      AS severidade,
            pr.acknowledged                          AS reconhecido,
            toInteger(pr.clock)                      AS clock
        ORDER BY toInteger(pr.clock) DESC
        LIMIT $limite
    """, limite=limite)

    resultado = []
    for r in rows:
        from datetime import datetime
        clock = r["clock"]
        mins  = int((agora - clock) / 60) if clock else 0
        resultado.append({
            "host":       r["host"]       or "",
            "problema":   r["problema"]   or "",
            "severidade": r["severidade"] or "",
            "severity":   int(r["severity"] or 0),
            "reconhecido": bool(r["reconhecido"]),
            "ha_minutos": mins,
            "data_hora":  datetime.fromtimestamp(clock).strftime("%d/%m %H:%M") if clock else "",
        })
    return resultado


def get_dashboard_operacional(session):
    return {
        "hosts":              query_status_hosts(session),
        "incidentes":         query_incidentes_abertos(session),
        "top10_hosts":        query_top10_hosts_problema(session),
        "ultimos_incidentes": query_ultimos_incidentes(session, limite=10),
    }


def query_billing_por_grupo(session, inicio_ts, sla_minutos=15):
    rows = session.run("""
        MATCH (g:Grupo)<-[:PERTENCE_A]-(h:Host)
        WHERE (h.removido IS NULL OR h.removido = false)
        WITH g, h
        OPTIONAL MATCH (h)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU]->(e:Evento)
        WHERE toInteger(e.clock) >= $inicio_ts
        WITH g, h, count(e) AS alertas_host
        OPTIONAL MATCH (h)-[:TEM_TRIGGER]->(t2:Trigger)-[:GEROU_PROBLEMA]->(pr:Problem)
        WHERE pr.ativo = true
        WITH g, h, alertas_host, count(pr) AS problemas_ativos,
             count(CASE WHEN toInteger(pr.severity) IN [4,5] THEN pr END) AS criticos_ativos
        WITH
            g.name          AS grupo,
            count(h)        AS total_hosts,
            count(CASE WHEN toInteger(h.status)=0 THEN h END) AS hosts_ativos,
            count(CASE WHEN toInteger(h.status)=1 THEN h END) AS hosts_inativos,
            sum(alertas_host)    AS alertas_periodo,
            sum(problemas_ativos) AS incidentes_ativos,
            sum(criticos_ativos)  AS criticos_ativos
        ORDER BY alertas_periodo DESC
        RETURN grupo, total_hosts, hosts_ativos, hosts_inativos,
               alertas_periodo, incidentes_ativos, criticos_ativos
    """, inicio_ts=inicio_ts)

    resultado = []
    for r in rows:
        resultado.append({
            "grupo":             r["grupo"]             or "Sem grupo",
            "total_hosts":       int(r["total_hosts"]       or 0),
            "hosts_ativos":      int(r["hosts_ativos"]      or 0),
            "hosts_inativos":    int(r["hosts_inativos"]    or 0),
            "alertas_periodo":   int(r["alertas_periodo"]   or 0),
            "incidentes_ativos": int(r["incidentes_ativos"] or 0),
            "criticos_ativos":   int(r["criticos_ativos"]   or 0),
        })
    return resultado


def query_sla_por_grupo(session, inicio_ts, sla_minutos=15):
    sla_seg = sla_minutos * 60
    rows = session.run("""
        MATCH (g:Grupo)<-[:PERTENCE_A]-(h:Host)
        WHERE (h.removido IS NULL OR h.removido = false)
        MATCH (h)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU_PROBLEMA]->(pr:Problem)
        WHERE toInteger(pr.clock) >= $inicio_ts
        OPTIONAL MATCH (pr)-[:TEM_ACK]->(ack:Acknowledge)
        WITH
            g.name AS grupo,
            pr,
            min(toInteger(ack.clock)) AS primeiro_ack
        WITH
            grupo,
            count(DISTINCT pr) AS total,
            count(DISTINCT CASE
                WHEN primeiro_ack IS NULL
                  OR (primeiro_ack - toInteger(pr.clock)) > $sla_seg
                THEN pr
            END) AS acima_sla,
            round(avg(CASE
                WHEN primeiro_ack IS NOT NULL
                 AND primeiro_ack >= toInteger(pr.clock)
                THEN (primeiro_ack - toInteger(pr.clock)) / 60.0
            END), 2) AS mtta_medio
        RETURN grupo, total, acima_sla, mtta_medio
        ORDER BY grupo
    """, inicio_ts=inicio_ts, sla_seg=sla_seg)

    resultado = {}
    for r in rows:
        total    = int(r["total"] or 0)
        ac_sla   = int(r["acima_sla"] or 0)
        sla_pct  = round(((total - ac_sla) / total) * 100, 1) if total > 0 else 100.0
        resultado[r["grupo"]] = {
            "total_incidentes": total,
            "sla_percentual":   sla_pct,
            "mtta_medio":       round(float(r["mtta_medio"] or 0), 2),
        }
    return resultado


def get_dashboard_billing(session, dias=30, sla_minutos=15):
    import time
    inicio_ts = int(time.time()) - (dias * 86400)

    grupos   = query_billing_por_grupo(session, inicio_ts, sla_minutos)
    sla_data = query_sla_por_grupo(session, inicio_ts, sla_minutos)

    for g in grupos:
        sla = sla_data.get(g["grupo"], {})
        g["total_incidentes"] = sla.get("total_incidentes", 0)
        g["sla_percentual"]   = sla.get("sla_percentual",   100.0)
        g["mtta_medio"]       = sla.get("mtta_medio",       0.0)

    return grupos
