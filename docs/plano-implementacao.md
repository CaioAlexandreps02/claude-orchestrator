# Plano de Implementação — Plugin Orquestrador

## Bugs encontrados e corrigidos (lista consolidada)

10 achados reais ao todo, entre auditoria de código e testes ao vivo com o plugin instalado.
Nenhum foi hipotético — todos reproduzidos antes do fix e revalidados depois. Tem também 1
"quase-achado" que investiguei a fundo e **não** confirmei — registrado embaixo pra não
esquecer que já foi checado.

| # | Onde | O que quebrava | Como achou | Fix |
|---|------|-----------------|------------|-----|
| 1 | `decompose-plan`, `execute-plan` | `subagent_type="geral"` não existe — `Task()` falharia | Auditoria de código | Trocado pelo agente nativo `general-purpose` |
| 2 | 8 agentes do roster (barkain) | Carregavam protocolo `DONE\|{path}` do harness original — nosso `execute-plan` não sabia ler isso, ia receber lixo em vez do resultado | Auditoria de código | Removido o bloco de protocolo, mantida só a identidade/expertise de cada agente |
| 3 | `task-completion-verifier.md` | Seção "MANIFEST-DRIVEN VERIFICATION" assumia manifesto que só o harness do barkain fornece | Auditoria de código | Removida |
| 4 | `code-reviewer.md` | Campo `activation_keywords` — mecanismo de dispatch por palavra-chave que a gente decidiu não usar (Fase 3 usa julgamento, não regex) | Auditoria de código | Removido |
| 5 | `generate-plan` | Faltava `EnterPlanMode` — só tinha `ExitPlanMode`, que falha sem entrar em plan mode antes | Teste real de ponta a ponta (bati o erro na hora) | Adicionado à skill |
| 6 | `decompose-plan` | Duas etapas no MESMO arquivo podiam ficar na mesma onda (paralelo) mesmo sem dependência lógica — risco de conflito de edição simultânea | Teste real (as 2 etapas do README) | Regra nova: mesmo arquivo = ondas separadas |
| 7 | `fast-executor.md` | Só tinha `Read, Grep, Glob` — mas o classificador marca comandos git como "fast", e sem Bash o agente não conseguia rodar o que prometia | Teste real (pedi `git log` pro fast-executor) | Adicionado `Bash` ao tools |
| 8 | `classify-prompt.py` | Tier **"standard" (Sonnet) inalcançável** sem `ANTHROPIC_API_KEY` — sem sinal forte, o default sempre caía em "fast", nunca em "standard" | Teste real ("implementa validação de CPF" foi pra Haiku) | Default do fallback trocado de "fast" pra "standard" |
| 9 | `classify-prompt.py` (PLAN_TRIGGER_PATTERNS) | "plano" sozinho em PT é ambíguo (implementação vs. assinatura/saúde/celular) — `"quero um plano mais barato de internet"` disparava o modo de plano | Bateria de 20 testes variados (stress test do classificador) | Removido o padrão solto `"quero um plano"`; os outros exigem verbo de criação + objeto (`de/para/pra`) |
| 10 | `classify-prompt.py` (robustez, 7 sub-fixes) | Hook podia travar a mensagem do usuário em vários cenários: exceção não tratada em `main()`; resposta da LLM fora do schema esperado (`KeyError`); chamada à API sem timeout (podia pendurar); escrita do stats file truncava antes do lock (corrompia em concorrência); leitura de `.env` sem encoding explícito (`UnicodeDecodeError`); payload do hook não validado como dict; erro de LLM logado cru no stderr | Code review dedicado (agente `code-reviewer`) pedido depois da bateria de testes, validado com 6 payloads malformados + 15 chamadas concorrentes de verdade | `try/except` amplo no `main()` (falha aberta, nunca bloqueia o prompt); validação de schema da resposta LLM; timeout de 5s na API; escrita atômica do stats via arquivo temp + `os.replace` (locking manual removido, virou redundante); encoding UTF-8 explícito na leitura do `.env`; validação de `input_data` como dict; log genérico em vez de exceção crua |

**Investigado e NÃO confirmado** — o agente `deep-executor` (rodado no mesmo lote do achado
#10) alegou que `sys.stdin` no Windows lê em cp1252 e corrompe todo acento em português,
citando "faça um plano de migração" como reprodução ("saiu standard, não disparou plano").
Reproduzi a alegação da forma mais fiel possível (pipe de bytes UTF-8 reais via `subprocess`,
simulando exatamente como o host chama o hook) e o resultado saiu **correto** em todos os
casos — inclusive o exato que o agente citou. Conferi byte a byte (hex dump) pra não confiar só
na exibição no terminal (que de fato mostra `�` por conta de um problema de rendering do
Git Bash neste Windows, não por corrupção real do dado). Ou seja: o achado do agente não se
sustentou sob verificação independente — registrado aqui como alerta de que até relatório de
agente precisa ser conferido antes de virar fix, não só confiado.

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

## Fase 8 — Empacotar e instalar (CONCLUÍDA)
Repo criado em `github.com/CaioAlexandreps02/claude-orchestrator` (não `CaioEmbrepoli` —
`gh` só tinha a conta MeuJudi logada; testado com `ssh -T` qual chave autentica como qual
conta antes de escolher). Commit + push feitos, `/plugin marketplace add` + `/plugin install`
rodados pelo Caio (esse passo só ele consegue fazer — registro de confiança de plugin é
bloqueado pra mim por design). Instalado com sucesso, os dois hooks (claude-router antigo +
claude-orchestrator novo) dispararam juntos na primeira mensagem depois — não desinstalamos
os 3 originais ainda, só depois de validar a Fase 7.

## Fase 7 — Teste manual (CONCLUÍDA, depois da Fase 8 por necessidade)
Corrigida a ordem do plano original: testar despacho real nos agentes `claude-orchestrator:*`
exige o plugin instalado primeiro (sem isso, `Task(subagent_type="claude-orchestrator:X")`
falha por o Claude Code não conhecer o agente). Feito depois da Fase 8, com o plugin de
verdade instalado:

- **Caminho simples**: testado via script direto (Fase 1) — confirmado.
- **Caminho plano explícito**: testado via script direto (Fase 1) — confirmado.
- **Caminho completo de ponta a ponta, ao vivo**: usado o próprio README do projeto como
  teste real (dogfooding) — `claude-orchestrator:documentation-expert` revisou o README e
  achou gaps reais (faltava instalação/uso/roster) → `EnterPlanMode` → plano com 2 etapas
  decompostas → `ExitPlanMode` aprovado pelo Caio → Onda 1 (Sonnet, `general-purpose`) →
  esperou terminar → Onda 2 (Haiku, `claude-orchestrator:documentation-expert`) → README
  final coerente, descrições dos 8 agentes batendo com o frontmatter real de cada um.

**2 achados novos, só apareceram testando ao vivo (não dava pra pegar só lendo código):**
1. `generate-plan` não mencionava `EnterPlanMode` (só `ExitPlanMode`) — sem isso a aprovação
   falha. Corrigido na skill.
2. Duas etapas no MESMO arquivo precisam ficar em ondas separadas mesmo sem dependência
   lógica de conteúdo — edição simultânea no mesmo arquivo por dois agentes é risco de
   conflito de escrita. Virou regra explícita no `decompose-plan`.

## Ordem sugerida
0 → 1 → 3 (só a parte de decomposição, sem geração ainda, testando com plano escrito à mão) → 4 →
5 → 6 → 2 (geração automática do plano entra por último, é a parte mais nova/arriscada) → 7 → 8.

Testar a tubulação de decomposição→modelo→execução com planos que você mesmo escrever à mão
primeiro é mais rápido de validar do que já start com geração automática de plano no meio —
isola onde quebra.
