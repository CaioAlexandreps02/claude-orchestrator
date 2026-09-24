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

## Instalacao

```
/plugin marketplace add <user>/claude-orchestrator
/plugin install claude-orchestrator@claude-orchestrator
```

## Atualizar depois de uma mudanca

O cache do plugin e organizado por numero de versao (`.claude-plugin/plugin.json`), entao toda
mudanca real precisa de um bump de versao, senao o Claude Code acha que ja tem e nao busca de
novo -- reinstalar sem bumpar a versao nao resolve.

Depois do bump + commit + push, pra puxar a versao nova sem precisar desinstalar: na tela de
Plugins (Configuracoes -> Plugins), **entra no plugin** (nao so o menu de tres pontinhos da
lista) -- a opcao de atualizar aparece dentro da tela de detalhe dele.

## Requisitos

- Claude Code
- Python 3
- `ANTHROPIC_API_KEY` (opcional) — so usada pro fallback de classificacao via Haiku quando a confianca da regra e baixa
- pacote `anthropic` (opcional, `pip install anthropic`) — so necessario se configurar a chave acima; sem ele, o fallback fica desativado silenciosamente e o classificador continua so por regra

## Como funciona no dia a dia

- **Mensagem simples/objetiva** → vai direto pro roteador de modelo, que escolhe Haiku, Sonnet ou Opus conforme a complexidade.
- **Mensagem vaga ou de escopo grande** → vira plano automaticamente: gera plano → decompoe em etapas → aprovacao via Plan Mode → executa.
- **Pedido explicito ("faz um plano pra X")** → pula direto pro modo de plano, sem passar pela analise de complexidade.

## Agentes disponíveis

### Executores simples (modelo fixo, para mensagem solta)

- **fast-executor** — Respostas rápidas usando Haiku para tarefas leves e diretas.
- **standard-executor** — Tarefas padrão de programação usando Sonnet com ferramenta completa.
- **deep-executor** — Análise profunda usando Opus para problemas complexos que precisam de raciocínio aprofundado.

### Agentes especializados (modelo escolhido dinamicamente pela decomposição do plano)

- **tech-lead-architect** — Desenha abordagens de implementação, pesquisa melhores práticas, avalia escolhas tecnológicas e arquiteta soluções.
- **code-reviewer** — Revisão de código especializada em boas práticas, qualidade, manutenibilidade e segurança.
- **codebase-context-analyzer** — Compreende estrutura do código, padrões, dependências e arquitetura da base.
- **dependency-manager** — Gerencia dependências Python, atualiza pacotes, resolve conflitos e valida compatibilidade.
- **devops-experience-architect** — Configura ambientes, pipelines CI/CD, gestão de secrets, containerização e infraestrutura de deployment.
- **documentation-expert** — Cria, atualiza ou revisa documentação de código, arquitetura e APIs.
- **task-completion-verifier** — Valida que entregas atendem requisitos, critérios de aceitação e casos extremos.
- **code-cleanup-optimizer** — Remove débito técnico, melhora qualidade e elimina redundância após implementação verificada.

## Status

Em construcao. Ver `docs/plano-implementacao.md` pra fase atual.
