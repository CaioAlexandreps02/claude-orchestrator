# claude-orchestrator

Plugin unico de Claude Code que junta 3 ideias:

1. **Roteamento de modelo por complexidade** (Haiku/Sonnet/Opus) pra mensagens simples.
2. **Geracao de plano** pra pedidos vagos/grandes, no mesmo estilo do deep-plan.
3. **Decomposicao do plano em etapas**, cada uma com seu proprio modelo escolhido por
   complexidade, rodando em sequencia ou paralelo conforme dependencia entre elas — aprovado
   via Plan Mode nativo do Claude Code antes de executar.

Design completo em `docs/design.md`. Plano de fases em `docs/plano-implementacao.md`.

## Creditos

Este projeto adapta trechos (todos MIT) de:

- [claude-router](https://github.com/bmersereau/claude-router) — Dan Monteiro
- [claude-code-workflow-orchestration](https://github.com/barkain/claude-code-workflow-orchestration) — Nadav Barkai
- [deep-plan](https://github.com/piercelamb/deep-plan) — Pierce Lamb

## Status

Em construcao. Ver `docs/plano-implementacao.md` pra fase atual.
