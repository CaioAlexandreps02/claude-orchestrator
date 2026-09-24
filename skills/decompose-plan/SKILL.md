---
name: decompose-plan
description: Decompoe um plano de implementacao ja aprovado (ou em rascunho) em etapas com complexidade, modelo e dependencia por etapa. Usar depois que um plano tiver passos concretos, antes de despachar qualquer agente. Nao usar pra tarefa unica simples -- isso ja vai direto pro roteador.
---

# Decompor plano em etapas

Pega um plano com passos concretos e devolve, pra cada passo: descricao, especialidade
sugerida, tier de modelo, e dependencias. Julgamento direto -- sem regex, sem chamar o
classifier.py. Isso porque a etapa costuma ser uma frase curta ("criar endpoint de auth"),
e um classificador de regex feito pra mensagem de usuario erra por falta de contexto; aqui
ja se tem o plano inteiro pra julgar direito.

## Tiers de complexidade (mesma taxonomia do roteador, aplicada por julgamento)

- **fast / Haiku**: mecanico, sem decisao real. Renomear, formatar, CRUD trivial seguindo
  padrao ja existente no projeto, comando git, ajuste de config, documentacao simples.
- **standard / Sonnet**: implementacao normal. Escrever uma funcao/componente/endpoint
  seguindo um padrao ja estabelecido no codebase, bug fix tipico, fatia de feature comum.
- **deep / Opus**: decisao de design de verdade, codigo sensivel a seguranca, problema
  ambiguo/novo sem padrao pra seguir, mudanca que atravessa varios sistemas, algoritmo
  critico de performance.

## Especialidade sugerida

Mapear pro roster de agentes quando fizer sentido (Fase 4 do projeto): tech-lead-architect
(decisao de arquitetura), code-reviewer, codebase-context-analyzer, dependency-manager,
devops-experience-architect, documentation-expert, task-completion-verifier,
code-cleanup-optimizer. Se nenhum encaixar, usar o agente nativo `general-purpose` -- nao
forcar categoria, e nao inventar nome de agente que nao existe no roster nem e nativo.

## Dependencia entre etapas

Etapa B depende de A quando B usa algo que A produz e que nao existe antes de A rodar
(tabela, funcao, arquivo, endpoint, tipo). Sinais praticos: B menciona "usa X criado em",
"depois de", ou opera em cima de algo que so a etapa A cria. Etapas sem essa relacao entre
si sao independentes.

## Agrupar em ondas (pra Fase 6 -- sequencia vs paralelo)

Onda 1 = etapas sem dependencia pendente (todas rodam em paralelo). Onda 2 = etapas cujas
dependencias estao todas satisfeitas pela onda 1. E assim por diante. Uma etapa nunca entra
numa onda antes de todas as suas dependencias.

## Formato de saida

Pra cada etapa:

```
Etapa N: <descricao curta>
  Especialidade: <agente ou "general-purpose">
  Complexidade: fast | standard | deep
  Modelo: haiku | sonnet | opus
  Depende de: nenhuma | Etapa X, Etapa Y
  Onda: <numero>
```

## Apresentar para aprovacao (ExitPlanMode)

Depois de decompor, chamar `ExitPlanMode` com o plano formatado assim -- agrupado por onda
(cada onda = um bloco sequencial; etapas dentro da mesma onda rodam em paralelo entre si),
com agente e modelo visiveis por etapa, e um resumo de quantas etapas vao pra cada modelo
(serve de sinal de custo pro Caio decidir na hora de aprovar):

```markdown
## Plano: <titulo>

### Onda 1
- **Etapa 1**: <descricao> -- agente: <especialidade> -- modelo: <Haiku|Sonnet|Opus>

### Onda 2
- **Etapa 2**: <descricao> -- agente: <especialidade> -- modelo: <...>

### Onda 3 (em paralelo)
- **Etapa 3**: <descricao> -- agente: <especialidade> -- modelo: <...>
- **Etapa 4**: <descricao> -- agente: <especialidade> -- modelo: <...>

**Resumo de modelo**: <N>x Haiku, <N>x Sonnet, <N>x Opus
```

Nunca despachar nenhum agente antes do `ExitPlanMode` voltar aprovado. Se o usuario pedir
mudanca no plano ou no modelo de alguma etapa na aprovacao, re-decompor com o ajuste e
apresentar de novo -- nao segue com a versao antiga.
