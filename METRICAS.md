# 📊 Coleta de Métricas Históricas - Guia Completo

## O que foi implementado

Agora o sistema coleta e armazena **valores históricos** de CPU, Memória e Disco no Neo4j, permitindo criar relatórios com dados reais.

### Antes (apenas metadados)
```
Neo4j tinha:
- Host "servidor1"
- Item "CPU Utilization (%)"
- Trigger "CPU > 80%"
- Evento "Trigger acionou em tal horário"
❌ Mas SEM saber que CPU foi 30%, 45%, 70% em cada momento
```

### Depois (com histórico)
```
Neo4j tem TUDO ACIMA + 
✅ Nós :Metrica com valores reais
✅ Relacionando Host -[:TEVE_METRICA]-> Metrica
✅ Relacionando Item -[:REGISTROU]-> Metrica
✅ Timestamps para análise temporal
```

---

## Como funciona

### 1. **Coleta no Zabbix** (zabbix_reader.py)

Três novas funções buscam dados da tabela `history` do PostgreSQL:

#### `get_metricas_historico(cur, dias=1)`
Coleta CPU última 24h
```python
# Busca items com palavras-chave: cpu, processor
# Retorna últimos 24 horas (configurável)
# Exemplo de dados:
[
  {
    'hostid': 10084,
    'host': 'Zabbix server',
    'itemid': 23456,
    'name': 'CPU utilization',
    'key_': 'system.cpu.util',
    'units': '%',
    'value_type': 3,
    'value': '30',      # ← 30%
    'clock': 1710797400 # ← Timestamp Unix
  },
  ...
]
```

#### `get_metricas_memoria(cur, dias=1)`
Coleta memória (memory, ram, available)

#### `get_metricas_disco(cur, dias=1)`
Coleta disco (disk, fs)

---

### 2. **Armazenamento no Neo4j** (neo4j_writer.py)

Função `write_metricas_batch()` cria:

**Estrutura no Neo4j:**
```
(Host:Zabbix server)
  |
  +-[:TEVE_METRICA]-> (Metrica)
  |                      properties:
  |                      - tipo: "cpu"
  |                      - valor: 30.0
  |                      - units: "%"
  |                      - clock: 1710797400
  |                      - timestamp: "2025-03-18T14:30:00"
  |                      - host: "Zabbix server"
  |                      - item_name: "CPU utilization"
  |
(Item:CPU Utilization)
  |
  +-[:REGISTROU]-> (Metrica)
```

---

## Como Consultar dados no Neo4j

### **Query 1: CPU média de um host nas últimas 24h**
```cypher
MATCH (h:Host {host: 'Zabbix server'})-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
RETURN h.host, 
       AVG(m.valor) AS cpu_media,
       MIN(m.valor) AS cpu_minima,
       MAX(m.valor) AS cpu_maxima,
       COUNT(m) AS num_amostras
```

**Resultado esperado:**
```
h.host           | cpu_media | cpu_minima | cpu_maxima | num_amostras
"Zabbix server"  | 35.42     | 12.0       | 68.5       | 1440
```

---

### **Query 2: Comparar CPU entre hosts**
```cypher
MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
WITH h, m
RETURN h.host, 
       AVG(m.valor) AS media,
       ROUND(STDEV(m.valor), 2) AS desvio_padrao
ORDER BY media DESC
```

---

### **Query 3: Picos de CPU (> 80%)**
```cypher
MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.valor > 80
RETURN h.host, m.timestamp, m.valor, m.item_name
ORDER BY m.timestamp DESC
LIMIT 20
```

---

### **Query 4: Memória disponível vs usada**
```cypher
MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'memoria'})
RETURN h.host, 
       COUNT(m) AS num_amostras,
       AVG(m.valor) AS media_valor,
       m.item_name
LIMIT 10
```

---

### **Query 5: Timeline de CPU com 1h de dados**
```cypher
MATCH (h:Host {host: 'Zabbix server'})-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.clock > datetime.now().add('duration {hours: -1}').epochSeconds
RETURN m.timestamp, m.valor
ORDER BY m.clock DESC
LIMIT 60
```

---

## Interpretação de Valores

### **CPU (em porcentagem)**
| Valor | Interpretação | Ação |
|-------|---------------|------|
| < 20% | Muito ocioso | ✅ OK - Servidor subutilizado |
| 20-50% | Saudável | ✅ OK - Normal |
| 50-80% | Atenção | ⚠️ INVESTIGAR - Próximo ao limite |
| 80-95% | Critico | 🔴 ALERTA - Otimizar carga |
| > 95% | Saturado | 🔴 CRITICO - Risco de degradação |

**Dica:** Neo4j ideal é < 70% em pico. Se sustentado > 80%, aumentar recursos.

### **Memória Disponível**
| Valor | Interpretação |
|-------|---------------|
| > 50% livre | ✅ Saudável |
| 30-50% livre | ⚠️ Aceitável |
| < 30% livre | 🔴 Crítico - Risco de swap |

### **Disco**
| Valor | Interpretação |
|-------|---------------|
| < 70% usado | ✅ OK |
| 70-85% usado | ⚠️ Limpeza em breve |
| > 85% usado | 🔴 Crítico - Sem espaço |

---

## Exemplos de Relatórios

### **Relatório Diário de Saúde do Neo4j**

```cypher
MATCH (h:Host {host: 'neo4j-prod'})-[:TEVE_METRICA]->(m:Metrica)
WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
WITH h, m.tipo as tipo, m.valor as valor
RETURN tipo, 
       ROUND(AVG(valor), 2) as media,
       ROUND(MIN(valor), 2) as minimo,
       ROUND(MAX(valor), 2) as maximo,
       CASE 
         WHEN tipo = 'cpu' AND AVG(valor) > 70 THEN '🔴 ALERTA'
         WHEN tipo = 'memoria' AND AVG(valor) > 80 THEN '🔴 ALERTA'
         WHEN tipo = 'disco' AND AVG(valor) > 85 THEN '🔴 ALERTA'
         ELSE '✅ OK'
       END as status
```

---

### **Alertar se CPU crescente (tendência)**

```cypher
MATCH (h:Host {host: 'Zabbix server'})-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.clock > datetime.now().add('duration {hours: -4}').epochSeconds
WITH h, m, ROW_NUMBER() OVER (ORDER BY m.clock) as seq
WITH collect({seq: seq, valor: m.valor}) as dados
WITH dados[0].valor as primeira_24h, dados[-1].valor as ultima_24h
WHERE ultima_24h > primeira_24h * 1.5
RETURN "⚠️ CPU em crescimento exponencial! De " + toString(primeira_24h) + "% para " + toString(ultima_24h) + "%"
```

---

## Configurações no config.env

Você pode controlar:

```bash
INTERVALO_SEGUNDOS=30    # A cada 30s coleta novo ciclo (incluindo métricas)
DIAS_HISTORICO=7         # Eventos mantém 7 dias (não afeta métricas)
```

Métricas são coletadas dos últimos **1 dia** (24h) a cada ciclo, limpando dados muito antigos automaticamente no Neo4j para não saturar.

---

## Limitações Atuais

1. **Coleta apenas últimas 24h** - Para economizar bandwidth, só busca última 1 dia
   - Solução: Aumentar `dias=7` em `get_metricas_historico()` se quiser mais história

2. **Apenas history_uint (valores inteiros)** - CPU em % é uint64
   - Para flutuantes (float histórico), seria preciso tabela `history` em vez de `history_uint`

3. **Sem limpeza automática antiga** - Neo4j acumula dados indefinidamente
   - Solução: Adicionar query de housekeeping para apagar métricas > 30 dias

---

## Próximos Passos Sugeridos

### ✅ **1. Criar índices no Neo4j** (performance)
```cypher
CREATE INDEX ON :Metrica(tipo);
CREATE INDEX ON :Metrica(clock);
CREATE INDEX ON :Host(host);
CREATE INDEX ON :Item(itemid);
CREATE CONSTRAINT ON (m:Metrica) ASSERT m.hostid IS UNIQUE;
```

### ✅ **2. Dashboard Grafana/Kibana** pronto para consumir dados Neo4j

### ✅ **3. Alertas automáticos** via Telegram/WhatsApp quando:
- CPU > 80% por > 10 min
- Memória < 30% livre
- Disco > 85% usado

### ✅ **4. Exportar relatórios em PDF** com gráficos das métricas

---

## Debug

Se não vir métricas no Neo4j:

```bash
# 1. Verificar se PostgreSQL tem dados
psql zabbix -U zabbix -c "
  SELECT COUNT(*) FROM history_uint 
  WHERE clock > (EXTRACT(EPOCH FROM NOW()) - 86400);"

# 2. Ver que items existem do tipo CPU
psql zabbix -U zabbix -c "
  SELECT name, key_ FROM items 
  WHERE name ILIKE '%cpu%' 
  AND status=0 LIMIT 10;"

# 3. Executar main.py com DEBUG
DEBUG=1 python3 main.py

# 4. Verificar Neo4j diretamente
# No navegador: http://neo4j.iosinformatica.com:7474
# Query: MATCH (m:Metrica) LIMIT 5 RETURN m
```

---

## Pronto! 🚀

O sistema agora coleta, armazena e permite consultar métricas históricas. 
Você pode gerar relatórios reais sobre desempenho do Neo4j e servidores!

