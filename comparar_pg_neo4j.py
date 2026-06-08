#!/usr/bin/env python3
"""
comparar_pg_neo4j.py — Comparação em tempo real entre PostgreSQL (Zabbix) e Neo4j
Uso: python3 comparar_pg_neo4j.py
"""
import os, sys, time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from neo4j import GraphDatabase

load_dotenv("config.env")

OK    = "\033[92m✔\033[0m"
FAIL  = "\033[91m✘\033[0m"
WARN  = "\033[93m~\033[0m"
RESET = "\033[0m"
BOLD  = "\033[1m"
CYAN  = "\033[96m"
GRAY  = "\033[90m"
INFO  = "\033[94mℹ\033[0m"

DIAS_HIST = int(os.getenv("DIAS_HISTORICO", "7"))


def pg_connect():
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


def neo4j_connect():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS"))
    )


def linha(label, pg_val, neo_val, tolerancia=0, info=None):
    pg_val  = int(pg_val  or 0)
    neo_val = int(neo_val or 0)
    diff = abs(pg_val - neo_val)

    if diff == 0:
        icone, cor = OK, "\033[92m"
    elif diff <= tolerancia:
        icone, cor = WARN, "\033[93m"
    else:
        icone, cor = FAIL, "\033[91m"

    sufixo = f"  {GRAY}(diff: {diff}){RESET}" if diff > 0 else ""
    if info:
        sufixo += f"  {GRAY}[{info}]{RESET}"

    print(f"  {icone} {BOLD}{label:<40}{RESET}  "
          f"PG: {BOLD}{cor}{str(pg_val):>8}{RESET}  "
          f"Neo4j: {BOLD}{cor}{str(neo_val):>8}{RESET}{sufixo}")


def secao(titulo):
    print(f"\n{CYAN}{BOLD}{'─'*60}{RESET}")
    print(f"{CYAN}{BOLD}  {titulo}{RESET}")
    print(f"{CYAN}{BOLD}{'─'*60}{RESET}")


def run_pg(cur, sql, params=None):
    cur.execute(sql, params or ())
    row = cur.fetchone()
    if row is None:
        return 0
    return list(row.values())[0] or 0


def run_neo(session, cypher, params=None):
    result = session.run(cypher, params or {})
    record = result.single()
    if record is None:
        return 0
    val = list(record.values())[0]
    return val if val is not None else 0


def main():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    desde_ts = int((datetime.now() - timedelta(days=DIAS_HIST)).timestamp())

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  COMPARAÇÃO PostgreSQL × Neo4j   —   {agora}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    try:
        pg = pg_connect()
        cur = pg.cursor()
        print(f"  {OK} PostgreSQL conectado")
    except Exception as e:
        print(f"  {FAIL} PostgreSQL FALHOU: {e}")
        sys.exit(1)

    try:
        driver = neo4j_connect()
        neo_session = driver.session()
        print(f"  {OK} Neo4j conectado")
    except Exception as e:
        print(f"  {FAIL} Neo4j FALHOU: {e}")
        sys.exit(1)

    # ══════════════════════════════════════════════════════════════════════════
    secao("1. RESUMO DO AMBIENTE")

    # Hosts: mesma query do ETL (LEFT JOIN, sem filtro de IP)
    pg_hosts = run_pg(cur, """
        SELECT COUNT(*) FROM hosts h
        WHERE h.flags=0 AND h.status IN (0,1)
    """)
    neo_hosts = run_neo(neo_session, """
        MATCH (h:Host) WHERE h.removido IS NULL OR h.removido = false
        RETURN count(h)
    """)
    linha("Hosts monitorados", pg_hosts, neo_hosts)

    # Triggers: conta igual ao ETL (todos os status=0, incluindo LLD flags=4)
    pg_triggers = run_pg(cur, """
        SELECT COUNT(DISTINCT t.triggerid) FROM triggers t
        JOIN functions f ON f.triggerid=t.triggerid
        JOIN items i ON i.itemid=f.itemid
        JOIN hosts h ON h.hostid=i.hostid
        WHERE t.status=0
    """)
    neo_triggers = run_neo(neo_session, "MATCH (t:Trigger) RETURN count(t)")
    linha("Triggers ativos (PG)", pg_triggers, neo_triggers, tolerancia=200,
          info="inclui LLD")

    # Eventos: janela de 7 dias igual ao ETL
    pg_eventos = run_pg(cur, """
        SELECT COUNT(*) FROM events
        WHERE source=0 AND object=0 AND clock > %s
    """, (desde_ts,))
    neo_eventos = run_neo(neo_session, "MATCH (e:Evento) WHERE e.clock > $desde_ts RETURN count(e)", {"desde_ts": desde_ts})
    linha("Eventos (últimos 7 dias)", pg_eventos, neo_eventos, tolerancia=100,
          info="ambos filtrados por clock > 7 dias")

    # ══════════════════════════════════════════════════════════════════════════
    secao("2. PROBLEMAS (tabela problem)  ← CRÍTICO")

    pg_prob_total = run_pg(cur, "SELECT COUNT(*) FROM problem WHERE source=0")
    neo_prob_total = run_neo(neo_session, "MATCH (pr:Problem) RETURN count(pr)")
    linha("Total problemas", pg_prob_total, neo_prob_total, tolerancia=2,
          info="diff ≤2 = condição de corrida normal")

    pg_ativos = run_pg(cur, """
        SELECT COUNT(*) FROM problem WHERE source=0 AND r_eventid IS NULL
    """)
    neo_ativos = run_neo(neo_session, """
        MATCH (pr:Problem) WHERE pr.ativo = true RETURN count(pr)
    """)
    linha("Problemas ativos", pg_ativos, neo_ativos, tolerancia=2)

    pg_resolvidos = run_pg(cur, """
        SELECT COUNT(*) FROM problem WHERE source=0 AND r_eventid IS NOT NULL
    """)
    neo_resolvidos = run_neo(neo_session, """
        MATCH (pr:Problem) WHERE pr.ativo = false RETURN count(pr)
    """)
    linha("Problemas resolvidos", pg_resolvidos, neo_resolvidos, tolerancia=2)

    # ══════════════════════════════════════════════════════════════════════════
    secao("3. SEVERIDADE DOS PROBLEMAS ATIVOS  ← CRÍTICO")

    mapa_sev = {0: "Não classificado", 1: "Informação", 2: "Aviso",
                3: "Médio", 4: "Alto", 5: "Desastre"}

    for sev_id, sev_nome in sorted(mapa_sev.items(), reverse=True):
        pg_sev = run_pg(cur, """
            SELECT COUNT(*) FROM problem
            WHERE source=0 AND r_eventid IS NULL AND severity=%s
        """, (sev_id,))
        neo_sev = run_neo(neo_session, f"""
            MATCH (pr:Problem)
            WHERE pr.ativo = true AND pr.severity = {sev_id}
            RETURN count(pr)
        """)
        linha(f"  Severidade {sev_id} — {sev_nome}", pg_sev, neo_sev, tolerancia=1)

    # ══════════════════════════════════════════════════════════════════════════
    secao("4. RECONHECIMENTO (tabela acknowledges)  ← CRÍTICO")

    pg_acks = run_pg(cur, "SELECT COUNT(*) FROM acknowledges")
    neo_acks = run_neo(neo_session, "MATCH (a:Acknowledge) RETURN count(a)")
    linha("Total ACKs", pg_acks, neo_acks, tolerancia=2)

    pg_reconhecidos = run_pg(cur, """
        SELECT COUNT(*) FROM problem WHERE source=0 AND acknowledged=1
    """)
    neo_reconhecidos = run_neo(neo_session, """
        MATCH (pr:Problem) WHERE pr.acknowledged = true RETURN count(pr)
    """)
    linha("Problemas reconhecidos", pg_reconhecidos, neo_reconhecidos, tolerancia=1)

    pg_nao_rec = run_pg(cur, """
        SELECT COUNT(*) FROM problem
        WHERE source=0 AND r_eventid IS NULL AND acknowledged=0
    """)
    neo_nao_rec = run_neo(neo_session, """
        MATCH (pr:Problem)
        WHERE pr.ativo = true AND (pr.acknowledged IS NULL OR pr.acknowledged = false)
        RETURN count(pr)
    """)
    linha("Ativos sem reconhecimento", pg_nao_rec, neo_nao_rec, tolerancia=1)

    # ══════════════════════════════════════════════════════════════════════════
    secao("5. ITENS E GRUPOS")

    pg_items = run_pg(cur, "SELECT COUNT(*) FROM items WHERE flags=0 AND status=0")
    neo_items = run_neo(neo_session, "MATCH (i:Item) RETURN count(i)")
    linha("Itens ativos", pg_items, neo_items, tolerancia=50)

    pg_grupos = run_pg(cur, "SELECT COUNT(*) FROM hstgrp")
    neo_grupos = run_neo(neo_session, "MATCH (g:Grupo) RETURN count(g)")
    linha("Grupos", pg_grupos, neo_grupos, tolerancia=5)

    # ══════════════════════════════════════════════════════════════════════════
    secao("6. TOP 10 HOSTS COM MAIS PROBLEMAS  (mesma janela)")

    # NOTA: atribuicao de problema por host e feita via trigger->functions->items->host.
    # Triggers LLD podem ter multiplos itens/hosts associados, causando ambiguidade.
    # Usamos CTE com DISTINCT ON eventid para garantir exatamente 1 host por problema,
    # escolhendo o host real (flags=0, status ativo) com menor hostid.
    # Diferencas de +-1 em hosts com triggers LLD compartilhados sao esperadas.
    cur.execute("""
        WITH prob_host AS (
            SELECT DISTINCT p.eventid,
                   (SELECT i.hostid
                    FROM functions f
                    JOIN items i ON i.itemid = f.itemid
                    JOIN hosts h2 ON h2.hostid = i.hostid
                    WHERE f.triggerid = p.objectid
                      AND h2.flags = 0
                      AND h2.status IN (0,1)
                    ORDER BY i.hostid
                    LIMIT 1) AS hostid
            FROM problem p
            WHERE p.source = 0
        )
        SELECT h.host, COUNT(ph.eventid) AS total
        FROM prob_host ph
        JOIN hosts h ON h.hostid = ph.hostid
        WHERE ph.hostid IS NOT NULL
        GROUP BY h.host, h.hostid
        ORDER BY total DESC
        LIMIT 10
    """)
    pg_top = cur.fetchall()

    neo_top_result = neo_session.run("""
        MATCH (h:Host)-[:TEM_TRIGGER]->(t:Trigger)-[:GEROU_PROBLEMA]->(pr:Problem)
        WHERE h.removido IS NULL OR h.removido = false
        RETURN h.host AS host, count(pr) AS total
        ORDER BY total DESC LIMIT 10
    """)
    neo_top = list(neo_top_result)

    print(f"\n  {'HOST':<40} {'PG':>8} {'NEO4J':>8}")
    print(f"  {'-'*58}")

    pg_dict  = {r["host"]: r["total"] for r in pg_top}
    neo_dict = {r["host"]: r["total"] for r in neo_top}
    todos    = sorted(set(list(pg_dict.keys()) + list(neo_dict.keys())),
                      key=lambda x: pg_dict.get(x, 0), reverse=True)

    for host in todos:
        pv = pg_dict.get(host, 0)
        nv = neo_dict.get(host, 0)
        diff = abs(pv - nv)
        if diff == 0:
            icone, cor = OK, "\033[92m"
        elif diff <= 3:
            icone, cor = WARN, "\033[93m"
        else:
            icone, cor = FAIL, "\033[91m"
        print(f"  {icone} {host:<40} {cor}{BOLD}{pv:>8}{RESET}  {cor}{BOLD}{nv:>8}{RESET}")

    # ══════════════════════════════════════════════════════════════════════════
    secao("RESUMO FINAL  (métricas críticas do Lambda)")

    checks_criticos = [
        ("Total problemas",      pg_prob_total,   neo_prob_total,   2),
        ("Problemas ativos",     pg_ativos,        neo_ativos,       2),
        ("Problemas resolvidos", pg_resolvidos,    neo_resolvidos,   2),
        ("Problemas reconhec.",  pg_reconhecidos,  neo_reconhecidos, 1),
        ("Ativos s/ reconhec.",  pg_nao_rec,       neo_nao_rec,      1),
        ("Total ACKs",           pg_acks,          neo_acks,         2),
    ]

    ok_count   = sum(1 for _, p, n, t in checks_criticos if abs(p-n) <= t)
    fail_count = sum(1 for _, p, n, t in checks_criticos if abs(p-n) > t)

    for label, p, n, t in checks_criticos:
        diff = abs(p - n)
        if diff == 0:
            icone, cor = OK, "\033[92m"
        elif diff <= t:
            icone, cor = WARN, "\033[93m"
        else:
            icone, cor = FAIL, "\033[91m"
        print(f"  {icone} {label:<30} PG: {cor}{BOLD}{p:>6}{RESET}  Neo4j: {cor}{BOLD}{n:>6}{RESET}")

    print()
    if fail_count == 0:
        print(f"  {BOLD}\033[92m✔  Neo4j está sincronizado com o PostgreSQL.{RESET}")
        print(f"  {GRAY}(diferenças ≤2 são condição de corrida normal em sistema ao vivo){RESET}")
    else:
        print(f"  {FAIL}  {fail_count} métrica(s) com divergência real.")
        print(f"  {BOLD}⚠  Rode  python3 main.py  para ressincronizar.{RESET}")

    print(f"\n  {GRAY}Divergências esperadas por design:{RESET}")
    print(f"  {INFO} Eventos: ambos filtrados por clock > 7 dias — diff ≤100 é normal (limite 2000 por ciclo)")
    print(f"  {INFO} Triggers: Neo4j inclui LLD, comparador PG pode diferir levemente")
    print(f"\n{BOLD}{'='*60}{RESET}\n")

    cur.close()
    pg.close()
    neo_session.close()
    driver.close()


if __name__ == "__main__":
    main()
