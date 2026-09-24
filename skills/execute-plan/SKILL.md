---
name: execute-plan
description: Executa um plano ja decomposto e aprovado via ExitPlanMode (saida da skill decompose-plan). Despacha cada onda como agentes Task em paralelo, no modelo definido por etapa, esperando a onda inteira terminar antes de passar pra proxima. So usar depois de aprovacao -- nunca antes.
---

# Executar plano decomposto

## Regra de ouro

So comeca depois do `ExitPlanMode` voltar aprovado. Se o usuario pediu ajuste na aprovacao,
o plano decomposto muda e essa versao nova e a que executa -- nunca a antiga.

## Por onda, em ordem

Pra cada onda (1, 2, 3...), nessa sequencia:

1. Despachar **todas** as etapas dessa onda como chamadas `Task` na mesma resposta (paralelo
   de verdade, nao uma de cada vez) -- `subagent_type` = agente definido na decomposicao,
   `model` = modelo definido na decomposicao (sobrescreve o que tiver no arquivo do agente).
2. Esperar TODAS as etapas da onda terminarem antes de despachar a onda seguinte. Uma onda
   nunca comeca com a anterior ainda rodando -- e assim que a dependencia e respeitada.
3. Reportar em 1-2 linhas o que a onda entregou antes de seguir pra proxima (igual qualquer
   outra atualizacao de progresso -- nao silencioso, nao um relatorio longo).

## Se uma etapa falhar

Nao segue pra proxima onda que dependa dela. Para, mostra o que quebrou, e pergunta como
seguir (tentar de novo, pular com ajuste manual, ou parar o plano inteiro) -- nunca assume
sozinho que da pra continuar com uma dependencia quebrada.

## Exemplo (dry-run, sem executar de verdade)

Plano de 5 etapas em 4 ondas (ver decompose-plan):

```
Onda 1: Task(subagent_type="general-purpose", model="sonnet", prompt="Etapa 1: ...")
  -- esperar terminar --
Onda 2: Task(subagent_type="general-purpose", model="sonnet", prompt="Etapa 2: ...")
  -- esperar terminar --
Onda 3 (paralelo, 2 chamadas na mesma resposta):
  Task(subagent_type="general-purpose", model="haiku", prompt="Etapa 3: ...")
  Task(subagent_type="claude-orchestrator:task-completion-verifier", model="sonnet", prompt="Etapa 4: ...")
  -- esperar as DUAS terminarem --
Onda 4: Task(subagent_type="claude-orchestrator:documentation-expert", model="haiku", prompt="Etapa 5: ...")
```
