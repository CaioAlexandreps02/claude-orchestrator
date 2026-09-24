---
name: generate-plan
description: Gera um plano de implementacao pra um pedido vago ou grande. Disparado pelo hook do orquestrador (pedido explicito de plano, ou complexidade alta). Nao reproduz um motor de planejamento -- usa o que o Claude ja faz nativamente em modo de planejamento, mais grill-me quando faltar contexto e Explore quando precisar entender codigo existente.
---

# Gerar plano

Sem maquina propria de sessao/arquivo -- so o fluxo normal de planejamento, com dois reforcos
quando fazem falta.

## 1. Falta contexto de verdade?

Se o pedido e vago (poucos detalhes concretos, "quero um sistema de X" sem dizer como) e o
usuario nao respondeu a nenhuma pergunta ainda -- oferecer ou rodar `grill-me` primeiro. Nao
reinventa entrevista: usa o skill que ja existe. Se o pedido ja vier com escopo razoavel,
pula essa etapa e vai direto pra pesquisa.

## 2. Precisa entender codigo/padrao existente?

Se o pedido toca um projeto que ja existe, rodar `Task(subagent_type="Explore")` pra mapear
o que ja existe antes de propor algo -- evita plano que ignora convencao ja estabelecida
(ex: "tudo em page.tsx" no MKT-Embrepoli, RLS por organization_id no Supabase).

## 3. Escrever o plano

Chamar `EnterPlanMode` antes de explorar/escrever (exigido pelo Claude Code -- sem isso o
`ExitPlanMode` do passo de aprovacao falha). Prosa clara, sem implementacao de codigo completa
(isso e trabalho da execucao, nao do plano): o que vai ser feito, por que, e como, legivel por
alguem sem contexto previo. Esse texto e o que a proxima etapa (`decompose-plan`) vai ler.

## 4. Revisao (opcional, so se o plano for grande/arriscado)

Pra plano pequeno, pula. Pra plano com risco real (mexe em producao, schema de banco,
autenticacao, dado sensivel) -- um agente Opus revisa antes de seguir pra decomposicao,
igual o `deep-executor` ja faz pra tarefa complexa avulsa. Sem chamada externa de API de
outro provedor -- so um segundo olhar do proprio Claude, mais barato e sem dependencia nova.

## 5. Handoff

Plano pronto vai direto pra skill `decompose-plan` -- nao passa por nenhum sistema de
arquivo/task-list proprio no meio.
