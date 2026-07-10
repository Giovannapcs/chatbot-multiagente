#!/usr/bin/env python3
"""
Modulo de RAG (Retrieval-Augmented Generation) com Text-to-Cypher.
Recebe uma pergunta em linguagem natural, gera automaticamente uma query
Cypher para o Neo4j usando o Bedrock, executa a query e retorna a resposta
em portugues gerada pela IA.

Uso basico:
    from lambda_rag_perguntas import responder_pergunta
    resposta = responder_pergunta(session, "Como esta o ambiente agora?")
"""
import json
import boto3

# Cliente Bedrock para geracao de texto
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# =============================================================================
# SCHEMA DO NEO4J
# Enviado ao Bedrock para que ele entenda a estrutura do banco ao gerar queries.
# Atualize este bloco sempre que novos nos ou relacionamentos forem adicionados.
# =============================================================================

SCHEMA_NEO4J = """
NOS disponíveis no banco:

(:Host)
  - hostid: string — identificador unico
  - host: string — nome tecnico
  - name: string — nome amigavel
  - status: integer — 0=ativo, 1=desabilitado
  - status_txt: string — "ativo" ou "inativo"
  - ip: string — endereco IP
  - porta: string — porta de monitoramento
  - removido: boolean — true se deletado do Zabbix
  - data_desabilitado: string — data em que foi desabilitado

(:Trigger)
  - triggerid: string
  - description: string — descricao da trigger
  - priority: integer — 0=NC, 1=Info, 2=Aviso, 3=Medio, 4=Alto, 5=Desastre
  - value: integer — 0=OK, 1=problema

(:Evento)
  - eventid: string
  - clock: integer — timestamp unix em SEGUNDOS
  - severity: integer — 0=NC, 1=Info, 2=Aviso, 3=Medio, 4=Alto, 5=Desastre
  - value: integer — 0=OK, 1=problema
  - acknowledged: boolean

(:Problem)
  - eventid: string
  - name: string — descricao do problema
  - severity: integer — 0 a 5
  - clock: integer — timestamp unix em SEGUNDOS de quando abriu
  - ativo: boolean — true se ainda esta em aberto
  - acknowledged: boolean

(:Acknowledge)
  - acknowledgeid: string
  - clock: integer — timestamp unix em SEGUNDOS
  - message: string — mensagem do operador
  - userid: string

(:Grupo)
  - groupid: string
  - name: string — nome do grupo ou cliente

RELACIONAMENTOS:
  (Host)-[:TEM_TRIGGER]->(Trigger)
  (Trigger)-[:GEROU]->(Evento)
  (Trigger)-[:GEROU_PROBLEMA]->(Problem)
  (Evento)-[:VIROU_PROBLEMA]->(Problem)
  (Problem)-[:TEM_ACK]->(Acknowledge)
  (Evento)-[:TEM_ACK]->(Acknowledge)
  (Host)-[:PERTENCE_A]->(Grupo)

REGRAS IMPORTANTES:
  - Campos clock estao em SEGUNDOS (unix timestamp)
  - Ultimos 7 dias:  toInteger(pr.clock) >= (timestamp()/1000) - (7*86400)
  - Ultimos 30 dias: toInteger(pr.clock) >= (timestamp()/1000) - (30*86400)
  - Sempre usar toInteger() ao comparar campos clock
  - Sempre filtrar hosts removidos: (h.removido IS NULL OR h.removido = false)
  - Severidade critica: toInteger(pr.severity) IN [4, 5]
"""

# Operacoes proibidas nas queries geradas pela IA
PALAVRAS_PROIBIDAS = [
    "DELETE", "DETACH DELETE", "REMOVE", "SET ",
    "CREATE ", "MERGE ", "DROP ", "CALL db."
]


def validar_query(query):
    """
    Verifica se a query gerada e segura para executar.
    Aceita apenas queries de leitura que comecem com MATCH.
    Retorna (True, "OK") ou (False, motivo).
    """
    query_upper = query.upper().strip()

    if not query_upper.startswith("MATCH"):
        return False, "Query deve comecar com MATCH"

    for palavra in PALAVRAS_PROIBIDAS:
        if palavra in query_upper:
            return False, f"Operacao proibida detectada: {palavra}"

    return True, "OK"


def gerar_query_cypher(pergunta):
    """
    Envia a pergunta e o schema ao Bedrock e recebe a query Cypher gerada.
    Retorna a query como string limpa (sem markdown).
    """
    prompt = f"""Voce e um especialista em Neo4j Cypher.

Schema do banco de dados:
{SCHEMA_NEO4J}

Gere UMA query Cypher para responder:
"{pergunta}"

REGRAS OBRIGATORIAS:
- Retorne APENAS a query Cypher, sem explicacao, sem markdown, sem comentarios
- A query DEVE comecar com MATCH
- Use LIMIT 50 no maximo para listas
- Sempre use toInteger() ao comparar campos clock
- Filtre hosts removidos: (h.removido IS NULL OR h.removido = false)
- Para problemas ativos use: WHERE pr.ativo = true
- Nao use DELETE, SET, CREATE, MERGE ou qualquer operacao de escrita
"""

    response = bedrock.converse(
        modelId="amazon.nova-pro-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 500, "temperature": 0.1}
    )

    query = response["output"]["message"]["content"][0]["text"].strip()

    # Remove blocos de markdown se a IA incluir ```cypher ... ```
    if "```" in query:
        linhas = query.split("\n")
        query = "\n".join(
            l for l in linhas
            if not l.strip().startswith("```")
        ).strip()

    return query


def executar_query(session, query):
    """
    Executa a query no Neo4j e retorna os resultados como lista de dicts.
    Converte tipos especificos do Neo4j para tipos Python nativos.
    """
    resultado = session.run(query)
    rows = []

    for record in resultado:
        row = {}
        for key in record.keys():
            valor = record[key]
            if isinstance(valor, list):
                row[key] = [str(v) for v in valor]
            else:
                row[key] = valor
        rows.append(row)

    return rows


def gerar_resposta_natural(pergunta, query, dados):
    """
    Envia os dados brutos ao Bedrock e recebe a resposta em portugues.
    Limita o tamanho dos dados para nao exceder o contexto do modelo.
    """
    dados_str = json.dumps(dados, ensure_ascii=False, indent=2, default=str)

    if len(dados_str) > 8000:
        dados_str = dados_str[:8000] + "\n... (dados truncados)"

    prompt = f"""Voce e um analista de NOC (Network Operations Center).

Responda a pergunta abaixo em portugues do Brasil, de forma objetiva e profissional,
baseando-se APENAS nos dados fornecidos.

Pergunta: "{pergunta}"

Query executada:
{query}

Dados retornados:
{dados_str}

REGRAS:
- Responda de forma direta e objetiva
- Se os dados estiverem vazios, informe que nao ha registros
- Nao invente informacoes que nao estao nos dados
- Se houver incidentes criticos (Alto ou Desastre), destaque-os
- Maximo de 10 linhas na resposta
- Nao mencione detalhes tecnicos do banco na resposta
"""

    response = bedrock.converse(
        modelId="amazon.nova-pro-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 1000, "temperature": 0.3}
    )

    return response["output"]["message"]["content"][0]["text"].strip()


def responder_pergunta(session, pergunta):
    """
    Funcao principal do modulo RAG.
    Recebe uma sessao Neo4j e uma pergunta em linguagem natural.
    Retorna a resposta em texto para enviar ao usuario.

    Fluxo:
        1. Bedrock gera a query Cypher a partir da pergunta
        2. Query e validada (somente leitura)
        3. Query e executada no Neo4j
        4. Bedrock gera resposta em portugues com os dados retornados

    Uso:
        from lambda_rag_perguntas import responder_pergunta
        resposta = responder_pergunta(session, mensagem_do_usuario)
    """
    try:
        # Passo 1: gera a query
        query = gerar_query_cypher(pergunta)

        # Passo 2: valida seguranca
        valida, motivo = validar_query(query)
        if not valida:
            return f"Nao foi possivel processar essa pergunta. ({motivo})"

        # Passo 3: executa no Neo4j
        dados = executar_query(session, query)

        # Passo 4: gera resposta em portugues
        resposta = gerar_resposta_natural(pergunta, query, dados)

        return resposta

    except Exception as e:
        print(f"Erro no RAG: {str(e)}")
        return (
            "Nao foi possivel responder essa pergunta no momento. "
            "Tente reformular ou use um dos comandos de relatorio disponiveis."
        )
