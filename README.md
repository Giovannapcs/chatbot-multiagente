# Chatbot Multiagente

Pipeline de dados em tempo real para monitoramento via WhatsApp usando IA.

## Fluxo
```
PostgreSQL (Zabbix) -> Python -> Neo4j Aura -> AWS Lambda -> WhatsApp
```

## Status do Projeto
| Etapa | Status |
|-------|--------|
| VM Ubuntu Azure + SSH | Concluido |
| Python + Bibliotecas | Concluido |
| Neo4j Aura conectado | Concluido |
| Acesso PostgreSQL Zabbix | Aguardando credenciais |
| Scripts Python | Concluido Ajustar |
| Schema Neo4j | Pendente (aguarda Zabbix) |
| AWS Lambda + WhatsApp | Pendente |

## Configuracao
```bash
cp config.env.exemplo config.env
nano config.env  # preencher com credenciais reais
```

## Arquivos
| Arquivo | Funcao | Quando rodar |
|---------|--------|--------------|
| explorar_zabbix.py | Mapeia o banco Zabbix | Uma vez |
| criar_schema_neo4j.py | Cria indices no Neo4j | Uma vez |
| zabbix_reader.py | Leitura do PostgreSQL | Importado pelo main |
| neo4j_writer.py | Escrita no Neo4j | Importado pelo main |
| main.py | Loop de sincronizacao | Continuamente |

## Como executar
```bash
# 1. Explorar o Zabbix (requer credenciais PostgreSQL)
python3 explorar_zabbix.py

# 2. Criar schema Neo4j (uma vez)
python3 criar_schema_neo4j.py

# 3. Sincronizacao continua
python3 main.py
```

## Schema do Neo4j 
Aguardando

## Infraestrutura
- VM: Ubuntu 24.04 Azure
- Banco origem: PostgreSQL (Zabbix)
- Banco grafo: Neo4j Aura (nuvem)
- Linguagem: Python 3.12

## Proximos passos
- [ ] Receber credenciais PostgreSQL do Zabbix
- [ ] Explorar schema real do Zabbix
- [ ] Popular o Neo4j com dados reais
- [ ] Configurar AWS Lambda
- [ ] Integrar WhatsApp via Twilio

