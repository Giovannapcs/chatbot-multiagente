// ============================================================================
// QUERIES PRONTAS PARA RELATÓRIOS DE MÉTRICAS
// Copie e cole uma query por vez no navegador Neo4j
// Link: http://boltneo4j.iosinformatica.com:7474
// ============================================================================

// ────────────────────────────────────────────────────────────────────────────
// 1️⃣ RELATÓRIO GERAL - SAÚDE DE TODOS OS HOSTS (últimas 24h)
// ────────────────────────────────────────────────────────────────────────────

MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica)
WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
WITH h.host as host, m.tipo as tipo, m.valor as valor
RETURN host, 
       tipo,
       ROUND(AVG(valor), 2) as media,
       ROUND(MIN(valor), 2) as minimo,
       ROUND(MAX(valor), 2) as maximo,
       COUNT(valor) as num_amostras,
       CASE 
         WHEN tipo = 'cpu' AND AVG(valor) > 70 THEN '🔴 ALERTA'
         WHEN tipo = 'memoria' AND AVG(valor) > 80 THEN '🔴 ALERTA'
         WHEN tipo = 'disco' AND AVG(valor) > 85 THEN '🔴 ALERTA'
         ELSE '✅ OK'
       END as status
ORDER BY host, tipo;


// ────────────────────────────────────────────────────────────────────────────
// 2️⃣ CPU MÉDIA POR HOST
// ────────────────────────────────────────────────────────────────────────────

MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
WITH h.host, 
     AVG(m.valor) as cpu_media,
     MIN(m.valor) as cpu_min,
     MAX(m.valor) as cpu_max,
     STDEV(m.valor) as cpu_desvio,
     COUNT(m) as amostras
RETURN h.host as host,
       ROUND(cpu_media, 2) as cpu_media_percent,
       ROUND(cpu_min, 2) as cpu_minima,
       ROUND(cpu_max, 2) as cpu_maxima,
       ROUND(cpu_desvio, 2) as desvio_padrao,
       amostras
ORDER BY cpu_media DESC;


// ────────────────────────────────────────────────────────────────────────────
// 3️⃣ PICOS DE CPU > 80% (alertas)
// ────────────────────────────────────────────────────────────────────────────

MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.valor > 80
RETURN h.host as host,
       m.timestamp as horario,
       m.valor as cpu_percent,
       m.item_name as metrica
ORDER BY m.clock DESC
LIMIT 30;


// ────────────────────────────────────────────────────────────────────────────
// 4️⃣ ESPAÇO EM DISCO - UTILIZAÇÃO
// ────────────────────────────────────────────────────────────────────────────

MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'disco'})
WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
WITH h.host, m.item_name, 
     AVG(m.valor) as uso_medio,
     MAX(m.valor) as uso_maximo
RETURN h.host as host,
       m.item_name as particao,
       ROUND(uso_medio, 2) as uso_medio_percent,
       ROUND(uso_maximo, 2) as uso_maximo_percent,
       CASE
         WHEN uso_maximo > 85 THEN '🔴 CRÍTICO'
         WHEN uso_maximo > 70 THEN '⚠️ ALERTA'
         ELSE '✅ OK'
       END as status
ORDER BY uso_maximo DESC;


// ────────────────────────────────────────────────────────────────────────────
// 5️⃣ TENDÊNCIA DE CPU (crescimento ou queda nas últimas 6h)
// ────────────────────────────────────────────────────────────────────────────

MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.clock > datetime.now().add('duration {hours: -6}').epochSeconds
WITH h.host, m.clock, m.valor,
     ROW_NUMBER() OVER (PARTITION BY h.hostid ORDER BY m.clock) as seq,
     COUNT(*) OVER (PARTITION BY h.hostid) as total_amostras
WITH h.host, seq, total_amostras, m.valor,
     FIRST(collect(m.valor)) OVER (PARTITION BY h.hostid ORDER BY m.clock) as primeira,
     LAST(collect(m.valor)) OVER (PARTITION BY h.hostid ORDER BY m.clock) as ultima
WHERE seq = 1 OR seq = total_amostras
WITH h.host, 
     COLLECT(m.valor)[0] as primeira_amostra,
     COLLECT(m.valor)[-1] as ultima_amostra
RETURN h.host as host,
       ROUND(primeira_amostra, 2) as cpu_inicial,
       ROUND(ultima_amostra, 2) as cpu_final,
       ROUND((ultima_amostra - primeira_amostra), 2) as diferenca,
       CASE
         WHEN ultima_amostra > primeira_amostra THEN '📈 CRESCENTE'
         WHEN ultima_amostra < primeira_amostra THEN '📉 DECRESCENTE'
         ELSE '➡️ ESTÁVEL'
       END as tendencia
ORDER BY diferenca DESC;


// ────────────────────────────────────────────────────────────────────────────
// 6️⃣ COMPARAÇÃO ENTRE HOSTS - QUAL ESTÁ MAIS PESADO?
// ────────────────────────────────────────────────────────────────────────────

MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica)
WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
WITH h.host,
     SUM(CASE WHEN m.tipo = 'cpu' THEN m.valor ELSE 0 END) / COUNT(DISTINCT CASE WHEN m.tipo = 'cpu' THEN m.clock END) as cpu_media,
     SUM(CASE WHEN m.tipo = 'memoria' THEN m.valor ELSE 0 END) / COUNT(DISTINCT CASE WHEN m.tipo = 'memoria' THEN m.clock END) as mem_media,
     SUM(CASE WHEN m.tipo = 'disco' THEN m.valor ELSE 0 END) / COUNT(DISTINCT CASE WHEN m.tipo = 'disco' THEN m.clock END) as disco_media
RETURN h.host as host,
       ROUND(COALESCE(cpu_media, 0), 2) as cpu_media,
       ROUND(COALESCE(mem_media, 0), 2) as mem_media,
       ROUND(COALESCE(disco_media, 0), 2) as disco_media
ORDER BY cpu_media DESC;


// ────────────────────────────────────────────────────────────────────────────
// 7️⃣ TIMELINE DE CPU - ÚLTIMAS 12 HORAS (para gráfico)
// ────────────────────────────────────────────────────────────────────────────

MATCH (h:Host {host: 'Zabbix server'})-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.clock > datetime.now().add('duration {hours: -12}').epochSeconds
RETURN datetime({epochSeconds: m.clock}).formatted as horario,
       m.valor as cpu_percent,
       m.item_name as metrica
ORDER BY m.clock ASC
LIMIT 720;  // ~12 horas com coleta a cada minuto


// ────────────────────────────────────────────────────────────────────────────
// 8️⃣ ALERTAS AUTOMÁTICOS - CPU > 70% por mais de 1 hora
// ────────────────────────────────────────────────────────────────────────────

MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.clock > datetime.now().add('duration {hours: -1}').epochSeconds
WITH h.host, COUNT(m) as amostras_alta_cpu, AVG(m.valor) as cpu_media
WHERE cpu_media > 70 AND amostras_alta_cpu > 30  // Mais de 30 amostras > 70%
RETURN h.host as host,
       ROUND(cpu_media, 2) as cpu_media_percent,
       "🔴 ALERTA: CPU ALTA SUSTENTADA!" as alerta,
       amostras_alta_cpu as minutos_com_cpu_alta;


// ────────────────────────────────────────────────────────────────────────────
// 9️⃣ RESUMO EXECUTIVO - TUDO QUE PRECISA SABER
// ────────────────────────────────────────────────────────────────────────────

CALL {
  MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica)
  WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
  WITH COUNT(DISTINCT h) as total_hosts
  RETURN total_hosts
} 
CALL {
  MATCH (m:Metrica)
  WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
  WITH COUNT(m) as total_metricas
  RETURN total_metricas
}
CALL {
  MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
  WHERE m.valor > 80
  WITH COUNT(m) as picos_cpu
  RETURN picos_cpu
}
CALL {
  MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'disco'})
  WHERE m.valor > 85
  WITH COUNT(DISTINCT h) as hosts_disco_critico
  RETURN hosts_disco_critico
}
RETURN {
  total_hosts_monitorados: total_hosts,
  total_metricas_24h: total_metricas,
  picos_cpu_acima_80: picos_cpu,
  hosts_com_disco_critico: hosts_disco_critico,
  timestamp: datetime.now().formatted()
} as resumo;


// ────────────────────────────────────────────────────────────────────────────
// 🔟 DISTRIBUIÇÃO DE CARGA - QUAL HOST ESTÁ SENDO MAIS USADO?
// ────────────────────────────────────────────────────────────────────────────

MATCH (h:Host)-[:TEVE_METRICA]->(m:Metrica {tipo: 'cpu'})
WHERE m.timestamp > datetime.now().add('duration {days: -1}').formatted()
WITH h.host, m.valor,
     CASE
       WHEN m.valor > 80 THEN 'CRÍTICO'
       WHEN m.valor > 60 THEN 'ALTO'
       WHEN m.valor > 40 THEN 'MÉDIO'
       WHEN m.valor > 20 THEN 'BAIXO'
       ELSE 'OCIOSO'
     END as categoria
RETURN h.host as host,
       categoria,
       COUNT(*) as quantidade
ORDER BY h.host, categoria;


// ────────────────────────────────────────────────────────────────────────────
// DICAS DE USO:
// ────────────────────────────────────────────────────────────────────────────
// 
// - Substituir 'Zabbix server' pelo nome real do seu host
// - Ajustar as datas: 'duration {days: -1}' = últimas 24h
//   Opções: hours, days, weeks, months, years
// - Copiar resultado → Excel/Google Sheets para gráficos
// - LIMIT X para limitar número de resultados
//
// ────────────────────────────────────────────────────────────────────────────
