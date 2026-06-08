from neo4j import GraphDatabase
import os
import json


def run_single(session, query, params=None):
    result = session.run(query, params or {})
    record = result.single()
    if record is None:
        return 0
    val = list(record.values())[0]
    return val if val is not None else 0


def lambda_handler(event, context):
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASS"])
    )

    relatorio = {
        "resumo_ambiente": {},
        "incidentes": {},
        "reconhecimento": {},
        "sla": {},
        "top_hosts": []
    }

    with driver.session() as session:

        # ── RESUMO DO AMBIENTE ────────────────────────────────────────────
        relatorio["resumo_ambiente"]["hosts_monitorados"] = run_single(session, """
            MATCH (h:Host)
            WHERE h.removido IS NULL OR h.removido = false
            RETURN count(h)
        """)

        relatorio["resumo_ambiente"]["total_triggers"] = run_single(session, """
            MATCH (t:Trigger)
            RETURN count(t)
        """)

        relatorio["resumo_ambiente"]["total_eventos"] = run_single(session, """
            MATCH (e:Evento)
            RETURN count(e)
        """)

        # ── PROBLEMAS (usa nó :Problem — espelho direto da tabela problem) ───
        relatorio["incidentes"]["total_problemas"] = run_single(session, """
            MATCH (pr:Problem)
            RETURN count(pr)
        """)

        relatorio["incidentes"]["ativos"] = run_single(session, """
            MATCH (pr:Problem)
            WHERE pr.ativo = true
            RETURN count(pr)
        """)

        relatorio["incidentes"]["resolvidos"] = run_single(session, """
            MATCH (pr:Problem)
            WHERE pr.ativo = false
            RETURN count(pr)
        """)

        # Severidade dos problemas ativos
        result_sev = session.run("""
            MATCH (pr:Problem)
            WHERE pr.ativo = true
            RETURN pr.severity AS severity, count(pr) AS total
            ORDER BY severity DESC
        """)
        severidades = {}
        mapa_sev = {0: "nao_classificado", 1: "informacao", 2: "aviso",
                    3: "medio", 4: "alto", 5: "desastre"}
        for rec in result_sev:
            label = mapa_sev.get(rec["severity"], f"severity_{rec['severity']}")
            severidades[label] = rec["total"]
        relatorio["incidentes"]["por_severidade"] = severidades

        # ── RECONHECIMENTO (usa nó :Acknowledge — espelho da tabela acknowledges) ──
        relatorio["reconhecimento"]["total_acks"] = run_single(session, """
            MATCH (ack:Acknowledge)
            RETURN count(ack)
        """)

        relatorio["reconhecimento"]["problemas_reconhecidos"] = run_single(session, """
            MATCH (pr:Problem)
            WHERE pr.acknowledged = true
            RETURN count(pr)
        """)

        relatorio["reconhecimento"]["problemas_nao_reconhecidos"] = run_single(session, """
            MATCH (pr:Problem)
            WHERE pr.ativo = true AND (pr.acknowledged IS NULL OR pr.acknowledged = false)
            RETURN count(pr)
        """)

        # MTTA — Tempo médio para o primeiro reconhecimento
        mtta = run_single(session, """
            MATCH (pr:Problem)-[:TEM_ACK]->(ack:Acknowledge)
            WITH pr, min(ack.clock) AS primeiro_ack
            WHERE primeiro_ack > pr.clock
            WITH avg(primeiro_ack - pr.clock) AS mtta_segundos
            RETURN round(mtta_segundos / 60.0 * 100) / 100
        """)
        relatorio["reconhecimento"]["mtta_minutos"] = mtta

        # ── DURAÇÃO DOS INCIDENTES ────────────────────────────────────────
        relatorio["incidentes"]["resolvidos_menor_5_min"] = run_single(session, """
            MATCH (t:Trigger)-[:GEROU]->(inicio:Evento {value: 1})
            MATCH (t)-[:GEROU]->(fim:Evento {value: 0})
            WHERE fim.clock > inicio.clock
            WITH inicio, min(fim.clock) AS fim_clock
            WITH (fim_clock - inicio.clock) AS duracao
            WHERE duracao < 300
            RETURN count(*)
        """)

        relatorio["incidentes"]["resolvidos_entre_5_e_15_min"] = run_single(session, """
            MATCH (t:Trigger)-[:GEROU]->(inicio:Evento {value: 1})
            MATCH (t)-[:GEROU]->(fim:Evento {value: 0})
            WHERE fim.clock > inicio.clock
            WITH inicio, min(fim.clock) AS fim_clock
            WITH (fim_clock - inicio.clock) AS duracao
            WHERE duracao >= 300 AND duracao <= 900
            RETURN count(*)
        """)

        relatorio["incidentes"]["resolvidos_maior_15_min"] = run_single(session, """
            MATCH (t:Trigger)-[:GEROU]->(inicio:Evento {value: 1})
            MATCH (t)-[:GEROU]->(fim:Evento {value: 0})
            WHERE fim.clock > inicio.clock
            WITH inicio, min(fim.clock) AS fim_clock
            WITH (fim_clock - inicio.clock) AS duracao
            WHERE duracao > 900
            RETURN count(*)
        """)

        resolvidos_com_historico = (
            relatorio["incidentes"]["resolvidos_menor_5_min"]
            + relatorio["incidentes"]["resolvidos_entre_5_e_15_min"]
            + relatorio["incidentes"]["resolvidos_maior_15_min"]
        )
        relatorio["incidentes"]["resolvidos_com_historico_completo"] = resolvidos_com_historico

        # ── SLA ───────────────────────────────────────────────────────────
        sla = run_single(session, """
            MATCH (t:Trigger)-[:GEROU]->(inicio:Evento {value: 1})
            MATCH (t)-[:GEROU]->(fim:Evento {value: 0})
            WHERE fim.clock > inicio.clock
            WITH inicio, min(fim.clock) AS fim_clock
            WITH (fim_clock - inicio.clock) AS downtime
            RETURN
                CASE
                    WHEN count(*) = 0 THEN 100.0
                    ELSE round((100 - (sum(downtime) / (count(*) * 86400.0)) * 100) * 100) / 100
                END
        """)
        relatorio["sla"]["percentual_aproximado"] = sla
        relatorio["sla"]["observacao"] = "SLA baseado em incidentes com histórico completo de início e fim."

        # ── TOP 5 HOSTS COM MAIS PROBLEMAS ────────────────────────────────
        result = session.run("""
            MATCH (h:Host)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU_PROBLEMA]->(pr:Problem)
            WHERE h.removido IS NULL OR h.removido = false
            RETURN h.host AS host, count(pr) AS total_problemas
            ORDER BY total_problemas DESC
            LIMIT 5
        """)
        relatorio["top_hosts"] = [
            {"host": r["host"], "total_problemas": r["total_problemas"]}
            for r in result
        ]

    driver.close()

    return {
        "statusCode": 200,
        "body": json.dumps(relatorio, ensure_ascii=False)
    }


# ── TESTE LOCAL ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.environ["NEO4J_URI"] = "bolt://boltneo4j.iosinformatica.com:7687"
    os.environ["NEO4J_USER"] = "neo4j"
    os.environ["NEO4J_PASS"] = "%aQx0CLR*<v>}8v0"
    resposta = lambda_handler({}, {})
    print(json.dumps(resposta, indent=2, ensure_ascii=False))

