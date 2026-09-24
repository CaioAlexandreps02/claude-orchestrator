---
name: router-stats
description: Mostra estatisticas de uso do claude-orchestrator -- quantas mensagens foram classificadas, pra qual modelo cada uma foi, e a economia estimada. Usar quando o usuario pedir "estatisticas do roteador", "quanto ta economizando", "quantas vezes rodou", ou similar. Global entre todos os projetos (o arquivo de stats nao e por-repo).
---

# Estatisticas do orquestrador

Ler `~/.claude/orchestrator-stats.json` (path exato: `Path.home() / ".claude" /
"orchestrator-stats.json"`, mesmo arquivo que `hooks/classify-prompt.py` escreve).
Se o arquivo nao existir ainda, avisar que nenhuma classificacao rodou ainda -- nao e erro.

## O que reportar

1. **Total de mensagens classificadas** (`total_queries`) e a distribuicao por rota
   (`routes`: fast/standard/deep/plan) -- em numero E em porcentagem.
2. **Economia estimada** (`estimated_savings`, em dolares) -- mas SEMPRE com a ressalva:
   isso e "quanto teria economizado se toda sugestao do roteador tivesse sido seguida",
   comparado contra usar Opus pra tudo. Nao mede se a sugestao foi realmente seguida (o
   Claude pode ter ignorado a sugestao com julgamento) nem compara contra o habito real
   anterior do usuario (que pode nao ter sido Opus-pra-tudo). E teto teorico, nao numero
   garantido -- dizer isso todo vez, nao só na primeira.
3. **Ultimos dias de uso** (`sessions`, ate 30 dias) -- resumo rapido de tendencia, nao
   precisa detalhar dia a dia a nao ser que o usuario peca.
4. **Ultima atualizacao** (`last_updated`) -- pra saber se os dados sao recentes.

## Formato

Direto, tabela ou lista curta, sem enfeite. Exemplo:

```
Estatisticas do claude-orchestrator (desde <data mais antiga em sessions> ate <last_updated>)

Total: 142 mensagens classificadas
  fast (Haiku):     58  (41%)
  standard (Sonnet): 61  (43%)
  deep (Opus):       15  (11%)
  plan:               8  (6%)

Economia estimada: $2.14 -- teto teorico (vs. usar Opus pra tudo), nao conta se a
sugestao foi realmente seguida.

Ultimos 7 dias: 34 mensagens, media de ~5/dia.
```

Se `total_queries` for baixo (ex: <20) ou o periodo coberto for curto (poucos dias em
`sessions`), avisar que a amostra ainda e pequena pra tirar conclusao confiavel sobre
economia real -- nao apresentar 3 dias de uso como prova definitiva de nada.
