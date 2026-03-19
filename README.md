# Chatbot Multiagente

Pipeline de dados em tempo real para monitoramento via WhatsApp usando IA.

## Fluxo
```
PostgreSQL (Zabbix) -> Python -> Neo4j Aura -> AWS Lambda -> WhatsApp
```

## 📊 Status do Projeto
| Etapa | Status |
|-------|--------|
| VM Ubuntu Azure + SSH | ✅ Concluído |
| Python + Bibliotecas | ✅ Concluído |
| Neo4j Aura conectado | ✅ Concluído |
| Coleta de Hosts/Grupos/Triggers | ✅ Concluído |
| **Coleta de Métricas Históricas (CPU/Memória/Disco)** | ✅ **NOVO!** |
| Relatórios de Desempenho | ✅ **NOVO!** |
| AWS Lambda + WhatsApp | 📋 Próximo passo |

## Configuração
```bash
cp config.env.exemplo config.env
nano config.env  # preencher com credenciais reais
```

## 📁 Arquivos Principais
| Arquivo | Função | Quando rodar |
|---------|--------|--------------|
| **main.py** | 🔄 Loop principal de coleta | `python3 main.py` (contínuo) |
| zabbix_reader.py | Leitura PostgreSQL + **histórico de métricas** | Importado |
| neo4j_writer.py | Escrita Neo4j + **armazenamento de métricas** | Importado |
| **teste_metricas.py** | 🧪 Validação da coleta (novo!) | `python3 teste_metricas.py` |
| **setup_neo4j.py** | 🚀 Criar índices Neo4j (novo!) | `python3 setup_neo4j.py` |
| explorar_zabbix.py | Mapeia estrutura do Zabbix | Uma vez (exploração) |

## 📚 Documentação
| Documento | Descrição |
|-----------|-----------|
| [METRICAS.md](METRICAS.md) | 📖 Guia completo de métricas e interpretação |
| [QUERIES_RELATORIOS.cypher](QUERIES_RELATORIOS.cypher) | 🔍 10 queries prontas para relatórios |

## ⚡ Como Executar

### 1️⃣ Setup Inicial (executar uma vez)
```bash
# Criar índices no Neo4j para performance
python3 setup_neo4j.py
```

### 2️⃣ Testar Coleta de Métricas
```bash
# Validar se PostgreSQL e Neo4j estão prontos
python3 teste_metricas.py
```

### 3️⃣ Iniciar Coleta Contínua
```bash
# Começa a coletar dados a cada 30 segundos
python3 main.py
```

Você verá algo como:
```
==== INICIANDO: Zabbix -> Neo4j ====
Intervalo: 30s | Historico: 7 dias
--- Ciclo [14:30:45] ---
Hosts: 12
Grupos: 5
Itens: 342
Triggers: 87
Eventos: 24
Problemas: 3
Métricas CPU: 156
Métricas Memória: 145
Métricas Disco: 134
OK. Aguardando 30s...
```

## 📊 Schema do Neo4j

### Nós e Relacionamentos
```
┌─────────────────────────────────────────────────────┐
│                   Hosts                             │
│         (ex: Zabbix server)                        │
└──────────┬──────────────────┬──────────────────────┘
           │                  │
    ┌──────▼─────────┐   ┌───▼──────────┐
    │  TEM_ITEM      │   │  TEVE_METRICA │◄────────────┐
    │                │   │               │             │
    ▼                ▼   ▼               ▼             │
  Items         Métricas                │             │
  (ex:CPU       (ex: 30%                │           ┌─┴──────────┐
   Util)        em 14:30)               │           │  Histórico │
                                                     │  24 horas  │
                │                                    └────────────┘
                └────REGISTROU────────────┘
```

### Tipos de Métricas Coletadas
| Tipo | Source | Exemplos | Unidade |
|------|--------|----------|---------|
| **cpu** | history_uint | CPU Utilization, Processor Load | % |
| **memoria** | history_uint | Memory Available, Memory Used | %, MB |
| **disco** | history_uint | Disk Space Used, Free Disk | % |

## 🔍 Como Gerar Relatórios

### Opção 1: Usar Neo4j Browser
1. Abrir: http://boltneo4j.iosinformatica.com:7474
2. Copiar query de [QUERIES_RELATORIOS.cypher](QUERIES_RELATORIOS.cypher)
3. Executar e analisar resultados

### Opção 2: Exemplo - CPU média de um host
```cypher
MATCH (h:Host {host: 'Zabbix server'})-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
RETURN ROUND(AVG(m.valor), 2) as cpu_media_porcento
```

**Resultado:**
```
cpu_media_porcento
35.42
```

Isso significa: CPU rodando em média **35%, saudável** ✅

### Opção 3: Picos de CPU
```cypher
MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.valor > 80
RETURN h.host, m.timestamp, m.valor
ORDER BY m.clock DESC LIMIT 10
```

## ⚠️ Interpretação de Métricas

### CPU
- **0-30%**: ✅ **Ótimo** - Servidor ocioso
- **30-60%**: ✅ **Bom** - Operação normal
- **60-80%**: ⚠️ **Atenção** - Próximo ao limite
- **80-95%**: 🔴 **Crítico** - Risco de problema
- **>95%**: 🔴 **Saturado** - Performance degradada

### Memória Disponível
- **>50%**: ✅ Saudável
- **30-50%**: ⚠️ Aceitável
- **<30%**: 🔴 Risco de swap, crítico

### Espaço em Disco
- **<70% usado**: ✅ OK
- **70-85% usado**: ⚠️ Limpeza em breve
- **>85% usado**: 🔴 Crítico, sem espaço

## 🚀 Próximos Passos

- [ ] Dashboard em Grafana/Power BI consumindo Neo4j
- [ ] Alertas automáticos via Telegram/WhatsApp
- [ ] Exportar relatórios em PDF
- [ ] Machine Learning para prever picos
- [ ] Integrar com AWS Lambda

## 👨‍💻 Suporte
Consulte [METRICAS.md](METRICAS.md) para troubleshooting e debug.


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

