# Plugin Orquestrador (junta claude-router + deep-plan + workflow-orchestration): Grill / Discovery Notes
Date: 2026-09-24 · Goal: definir o design de um plugin próprio que linka os 3 plugins (roteamento de modelo, transformação de prompt vago em plano, decomposição do plano em fases/agentes), mantendo o comportamento de cada um, antes de começar a construir.

## Summary / key decisions
Design fechado e confirmado pelo Caio em 24/09/2026. Plugin único, absorvido (self-contained),
que substitui os 3 originais (claude-router, deep-plan, barkain/claude-code-workflow-orchestration).

1. **Gatilho**: toda mensagem passa por análise de complexidade. Exceção: pedido explícito de
   plano ("faça um plano pra X") pula a análise e vai direto pro modo plano.
2. **Tarefa simples**: vai direto pro roteador de modelo (Haiku/Sonnet/Opus), sem plano nem
   decomposição.
3. **Precisa de plano**: (1) gera o plano no estilo deep-plan (pesquisa/entrevista/revisão) → (2)
   separa em etapas e classifica a complexidade de CADA etapa por julgamento direto (não regex —
   já tem o plano inteiro como contexto) → (3) roteador escolhe o modelo por etapa → (4)
   **aprovação humana via Plan Mode nativo do Claude Code** (ExitPlanMode), com o modelo de cada
   etapa já escrito no plano apresentado → (5) etapas aprovadas disparam pra agentes no modelo
   definido.
4. **Execução das etapas**: análise de dependência automática decide sequência vs paralelo
   (dependente de outra = sequencial; independentes = paralelo). Não é escolha manual.
5. **Roster de agentes**: os 8 papéis especializados do barkain (tech-lead-architect,
   code-reviewer, etc.) + modelo de cada execução decidido dinamicamente pelo classificador, em
   vez do modelo fixo que só 2 dos 8 tinham originalmente.
6. **Arquitetura**: absorvido, não camada-cola. Motivo confirmado ao vivo nesta sessão: o hook do
   claude-router é "MANDATORY, do NOT respond directly" e disputa toda mensagem — uma cola por
   cima brigaria com isso a cada mensagem. Também resolve a inconsistência de `model:` entre os
   agentes do barkain/deep-plan (nem todos tinham).

## Q&A log

### Q1 — Gatilho: o que decide o caminho da mensagem (rotear direto / virar plano / decompor direto)
- Asked: quando uma mensagem chega, o que decide se ela vai direto pro roteador, vira plano primeiro, ou já entra decomposta?
- Captured: "Precisamos que a IA analise a complexidade daquilo para identificar se aquilo vai precisar de plano completo ou se é tarefa simples que pode ser feita direta. A não ser que esteja no pedido para virar um plano, aí vai direto." Fluxo completo: simples → roteador direto. Precisa de plano → gera plano (estilo deep-plan) → separa em etapas com complexidade cada uma → roteador escolhe modelo por etapa → aprovação humana → dispara agentes por etapa no modelo escolhido.
- Flags: sequência vs paralelo na execução das etapas do plano → Caio, ainda sem decisão (provável próxima pergunta).

### Q2 — Execução das etapas: sequencial ou paralela
- Asked: sequencial fixo, paralelo fixo, ou análise de dependência (como o barkain já faz)?
- Captured: Confirmado — análise de dependência automática na montagem do plano (etapa que depende do resultado de outra roda em sequência; etapas independentes rodam em paralelo). Não é escolha manual do Caio a cada vez.
- Flags: nenhuma.

### Q3 — Plugin absorvido (self-contained) ou plugin-cola (camada fina sobre os 3 instalados)
- Asked: vantagens/desvantagens de cada um, pedido pra dar opinião real.
- Captured: Recomendação dada — **absorvido**. Motivo concreto observado ao vivo nesta sessão: o hook do claude-router é "MANDATORY, do NOT respond directly" e disputa toda mensagem; uma cola por cima teria que brigar contra esse comportamento a cada mensagem, de forma frágil. Também: os agentes do barkain e do deep-plan não têm `model:` consistente entre si — colar não resolve isso. Absorvido = 1 ponto de instalação/atualização, sem depender de 3 projetos de terceiros continuarem compatíveis entre si. Custo: mais trabalho de construção agora, perde updates automáticos dos 3 originais.
- Decisão do Caio: pediu a opinião, ainda não confirmou explicitamente — assumir absorvido como default a menos que ele corrija.
- Flags: confirmar com o Caio se aceita "absorvido" como decisão final.

### Q4 — Roster de agentes
- Asked: reaproveitar agentes do barkain, do router, ou os dois?
- Captured: "acho que podemos reaproveitar, tentar usar os dois." Abordagem: papel/especialidade dos 8 agentes do barkain (tech-lead-architect, code-reviewer, etc.) + o modelo de cada execução decidido dinamicamente pelo classificador de complexidade (não fixo por agente como hoje) — une os dois sistemas em vez de escolher um.
- Flags: nenhuma.

### Q5 — Classificador por etapa do plano
- Asked: como resolver o viés do classificador de regex (favorece "fast" pra frases curtas, e etapas de plano tendem a ser frases curtas).
- Captured: Caio delegou a solução ("vamos resolver de alguma forma"). Proposta: mensagens soltas do dia a dia continuam com o classificador leve por regex (rápido, sem custo de IA). Dentro do fluxo de plano, a classificação de complexidade por etapa é feita com julgamento direto (já tem o plano inteiro como contexto, não só a frase isolada da etapa) na mesma passada que já gera/revisa o plano — não reaproveita a regex crua ajustada pra outro contexto.
- Flags: confirmar se essa abordagem serve.

### Q6 — Onde a aprovação acontece
- Asked: pediu minha opinião sobre o que roda melhor.
- Captured: Recomendação — usar o **Plan Mode nativo do Claude Code** (ExitPlanMode), que já existe e já é a interface conhecida, em vez de construir uma tela própria. Adição necessária: o plano apresentado pro ExitPlanMode já vem com o modelo atribuído por etapa escrito junto (ex: "Etapa 1: Criar schema do banco — modelo: Sonnet"), então uma aprovação só cobre plano + atribuição de modelo.
- Flags: confirmar se essa abordagem serve.

## Open flags (pending input)
Nenhum — Caio confirmou os 4 pontos em aberto (Q3, Q4, Q5, Q6) em 24/09/2026 ("perfeito").
Design fechado. Próximo passo: plano de implementação (ver arquivo separado
`2026-09-24-plano-implementacao.md` na mesma pasta).
