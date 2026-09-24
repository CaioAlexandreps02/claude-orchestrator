# Plano de Implementação — Plugin Orquestrador

Baseado no design fechado em `2026-09-24-grill.md`. Licenças checadas: claude-router (bmersereau),
barkain/claude-code-workflow-orchestration e piercelamb/deep-plan são todos MIT — dá pra reaproveitar
e adaptar código deles, mantendo crédito no README do plugin novo.

**Nome de trabalho**: `claude-orchestrator` (pode mudar). **Local**: novo repo próprio, fora do
`C:\Caio\app` (não é código da Embrepoli) — sugestão `C:\Caio\claude-orchestrator`.

## Fase 0 — Esqueleto do plugin
- Criar `C:\Caio\claude-orchestrator` como repo git próprio.
- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` (mesmo formato que vimos nos 3
  originais — nome, versão, source "./").
- `README.md` com crédito aos 3 projetos originais (MIT exige manter aviso de copyright deles nos
  trechos reaproveitados).
- `LICENSE` (MIT, mesmo padrão dos 3).

## Fase 1 — Classificador base (reaproveitando claude-router)
- Portar `classify-prompt.py` do bmersereau/claude-router como ponto de partida (já é
  Windows-compatible, já testamos).
- Adicionar a nova ramificação: detectar pedido explícito de plano ("faça um plano pra",
  "planeja", "quero um plano de") → pula classificação, vai direto pro modo plano.
- Manter o resto do comportamento (fast/standard/deep por regex) igual pra mensagens simples.

## Fase 2 — Geração de plano (CONCLUÍDA, escopo revisado)
Investigando o deep-plan de verdade: é um sistema de 22 passos com task-list persistente,
divisão em lotes, e revisão externa via API do Gemini/OpenAI — precisa de `uv` (não instalado)
e chaves que o Caio não tem. Portar isso inteiro duplicaria o que já temos: a parte de
entrevista já é o `grill-me` (já instalado), a parte de seccionar já é o `decompose-plan`
(Fase 3). O Caio perguntou direto: "não tem como o Claude só gerar o plano em vez de tentar
reproduzir isso?" — e é exatamente isso, porque gerar plano já é comportamento nativo em modo
de planejamento. Virou a skill `generate-plan`: sem motor próprio, só reforça grill-me quando
falta contexto e Explore quando precisa entender código existente, sem infraestrutura nova.

**Achado extra nessa fase**: o hook da Fase 1 só cobria pedido explícito de plano — faltava o
terceiro caminho do design original (mensagem "deep" só por ser vaga, sem pedir plano
explicitamente). Corrigido: rota "deep" agora apresenta os 3 sub-casos (vago→gera plano,
já tem escopo→decompõe direto, tarefa única→deep-executor) pra julgamento na hora, já que o
classificador de regex não consegue distinguir isso sozinho.

## Fase 3 — Decomposição + classificação por etapa
- Adaptar a lógica de decomposição do barkain (detecção de fases, correspondência de
  especialidade) — mas trocar o classificador de "palavra-chave por agente" pelo classificador de
  complexidade por etapa definido no grill: julgamento direto com o plano inteiro como contexto,
  não regex isolado por frase curta.
- Cada etapa sai com: descrição, agente/especialidade sugerida, tier de modelo (haiku/sonnet/opus),
  e lista de dependências (quais etapas ela precisa esperar).

## Fase 4 — Roster de agentes (merge barkain + router)
- Portar os 8 agentes do barkain (tech-lead-architect, code-reviewer, codebase-context-analyzer,
  dependency-manager, devops-experience-architect, documentation-expert,
  task-completion-verifier, code-cleanup-optimizer).
- Remover o `model:` fixo que 2 deles têm hoje — o modelo passa a ser atribuído na hora do
  despacho (Fase 3), não fixo no arquivo do agente.

## Fase 5 — Aprovação via Plan Mode nativo
- Montar o texto do plano (saída da Fase 2+3) no formato que o `ExitPlanMode` espera, com o modelo
  de cada etapa escrito junto (ex: "Etapa 2: Criar endpoint de auth — modelo: Sonnet").
- Sem tela própria — usa o fluxo de aprovação que o Claude Code já tem.

## Fase 6 — Execução (sequencial/paralelo por dependência)
- Ler as dependências marcadas na Fase 3: etapas sem dependência pendente entram na mesma leva
  paralela (múltiplos `Task` de uma vez); etapas dependentes esperam a leva anterior terminar.
- Cada etapa despachada como subagente do roster (Fase 4) no modelo definido (Fase 3).

## Auditoria (24/09/2026, antes da Fase 7)
Pedida pelo Caio antes de testar de ponta a ponta. 4 achados reais, todos corrigidos:

1. **Bug de execução real**: `decompose-plan` e `execute-plan` usavam `"geral"` como
   especialidade/subagent_type pra etapa sem papel específico — não existe agente com esse
   nome, `Task(subagent_type="geral", ...)` teria falhado. Trocado pelo agente nativo
   `general-purpose`, que existe de verdade.
2. **Bug de integração sistêmico**: os 8 agentes portados do barkain carregavam protocolo
   próprio do harness original deles — `RETURN FORMAT: DONE|{path}`, `$CLAUDE_SCRATCHPAD_DIR`,
   modo "Teammate"/`SendMessage`/`TeamCreate`, checklist de CLI. Nosso `execute-plan` faz
   `Task()` simples e espera resposta normal — esses agentes ficariam retornando só
   `DONE|caminho` em vez do resultado de verdade. Removido esse bloco dos 8 arquivos, mantido
   só a identidade/expertise de cada papel.
3. Uma sub-seção só do `task-completion-verifier` ("MANIFEST-DRIVEN VERIFICATION") também
   assumia um manifesto que só o harness do barkain fornece — removida junto.
4. Campo `activation_keywords` (mecanismo de dispatch por palavra-chave do barkain, que a
   gente decidiu não usar desde a Fase 3) ainda sobrava no `code-reviewer.md` — removido, sem
   uso no nosso design.

Revalidado depois dos 4 fixes: script compila, JSON válido, frontmatter dos 11 agentes íntegro,
os 4 testes de regressão (simples/plano-explícito/deep-PT/deep-vago-3-casos) passando.

## Fase 7 — Teste manual
- Caminho simples: mandar mensagem direta tipo "corrige esse typo" → confirmar que vai reto pro
  roteador, sem passar por plano.
- Caminho plano explícito: "faz um plano pra X" → confirmar que pula a análise de complexidade.
- Caminho plano por complexidade: pedido vago e grande → confirmar que decompõe, classifica por
  etapa, mostra aprovação com modelo por etapa, executa respeitando dependência.

## Fase 8 — Empacotar e instalar
- Commit + push pro repo novo.
- `/plugin marketplace add <seu-usuário>/claude-orchestrator` + `/plugin install
  claude-orchestrator@claude-orchestrator`.
- Depois de validar que funciona, desinstalar os 3 originais (`claude-router`, e os outros 2 se
  também tiverem sido instalados) pra não ter hooks duplicados brigando.

## Ordem sugerida
0 → 1 → 3 (só a parte de decomposição, sem geração ainda, testando com plano escrito à mão) → 4 →
5 → 6 → 2 (geração automática do plano entra por último, é a parte mais nova/arriscada) → 7 → 8.

Testar a tubulação de decomposição→modelo→execução com planos que você mesmo escrever à mão
primeiro é mais rápido de validar do que já start com geração automática de plano no meio —
isola onde quebra.
