#!/usr/bin/env python3
"""
claude-orchestrator - UserPromptSubmit Hook

Classifies prompts:
1. Explicit plan request (regex) -> skip classification, go straight to plan mode.
2. Otherwise: rule-based fast/standard/deep classification (instant, free),
   Haiku LLM fallback for low-confidence cases (~$0.001).

Adapted from claude-router: https://github.com/bmersereau/claude-router (MIT, Dan Monteiro)
"""
import json
import sys
import os
import re
import tempfile
from pathlib import Path
from datetime import datetime

CONFIDENCE_THRESHOLD = 0.7
STATS_FILE = Path.home() / ".claude" / "orchestrator-stats.json"

COST_PER_1M = {
    "fast": {"input": 0.25, "output": 1.25},      # Haiku
    "standard": {"input": 3.0, "output": 15.0},   # Sonnet
    "deep": {"input": 15.0, "output": 75.0},      # Opus
}
AVG_INPUT_TOKENS = 1000
AVG_OUTPUT_TOKENS = 2000

# Explicit plan request -> skip classification entirely, go straight to plan mode.
# ponytail: "plano" sozinho e ambiguo em PT (plano de implementacao vs plano de
# assinatura/saude/celular) -- achado real em teste: "quero um plano mais barato
# de internet" disparava isso. So confia em padroes que amarram "plano" a um
# verbo de CRIACAO (fazer/gerar/planejar), nunca em "quero/preciso um plano"
# sozinho, que e ambiguo de verdade mesmo pra humano lendo frio.
PLAN_TRIGGER_PATTERNS = [
    r"\b(fa[çc]a|faz|cri[ae]|gera|monta|elabora)\s+um\s+plano\s+(de|para|pra)\b",
    r"\bplano\s+de\s+implementa[çc][ãa]o\b",
    r"\bplaneja\b",
    r"^/plan\b",
]

# NOTE: o Caio escreve em portugues (BR) quase sempre. As listas abaixo tem par
# PT/EN pra cada sinal -- classificador so-em-ingles sub-classifica tudo como
# "fast" por falta de sinal, e foi exatamente isso que vimos ao vivo com o
# claude-router original durante a conversa que definiu esse design.
PATTERNS = {
    "fast": [
        r"^what (is|are|does) ",
        r"^how (do|does|to) ",
        r"^(show|list|get) .{0,30}$",
        r"\b(format|lint|prettify|beautify)\b",
        r"\bgit (status|log|diff|add|commit|push|pull)\b",
        r"\b(json|yaml|yml)\b.{0,20}$",
        r"\bregex\b",
        r"\bsyntax (for|of)\b",
        r"^(what|how).{0,50}\?$",
        # PT
        r"^o que (é|e|são|sao) ",
        r"^qual (é|e|são|sao) ",
        r"^como (fa[çc]o|funciona) ",
        r"^(mostra|lista|pega) .{0,30}$",
        r"\b(formata|padroniza)\b",
        r"^(o que|qual|como).{0,50}\?$",
        # ponytail: confirmacao/continuacao curta -- achado real (25/09): sem
        # isso, toda mensagem de "sim", "pode seguir", "atualizei pode testar"
        # cai no default "standard" (Sonnet) por falta de sinal, empurrando o
        # custo medio pra cima sem necessidade (a mensagem em si e trivial).
        # O `.{0,25}$` limita ao TOTAL da mensagem ficar curto -- uma frase tipo
        # "ok, mas antes disso implementa X" tem muito mais que 25 chars depois
        # de "ok" e NAO bate aqui, cai pro classificador normal como deveria.
        r"^(sim|n[ãa]o|ok|okay|beleza|blz|perfeito|certo|exato|isso|combinado|fechado|show|top)\b.{0,25}$",
        r"^(pode (seguir|continuar|testar)|continua|segue|pr[óo]ximo)\b.{0,25}$",
        r"^(atualizei|feito|pronto|conclu[ií]do)\b.{0,25}$",
        r"^(funcionou|deu certo|terminou|j[áa] foi)\??\b.{0,15}$",
    ],
    "deep": [
        r"\b(architect|architecture|design pattern|system design)\b",
        r"\bscalable?\b",
        r"\b(security|vulnerab|audit|penetration|exploit)\b",
        r"\b(across|multiple|all) (files?|components?|modules?)\b",
        r"\brefactor.{0,20}(codebase|project|entire)\b",
        r"\b(trade-?offs?|compare|pros? (and|&) cons?)\b",
        r"\b(analyze|evaluate|assess).{0,30}(option|approach|strateg)\b",
        r"\b(complex|intricate|sophisticated)\b",
        r"\boptimiz(e|ation).{0,20}(performance|speed|memory)\b",
        r"\b(multi-?phase|extraction|standalone repo|migration)\b",
        # PT
        r"\b(arquitet(ura|ar)|padr[ãa]o de projeto)\b",
        r"\bescal[áa]vel\b",
        r"\b(seguran[çc]a|vulnerabilidade|auditoria|pentest)\b",
        r"\b(v[áa]rios|m[úu]ltiplos|todos os) (arquivos?|componentes?|m[óo]dulos?)\b",
        r"\brefator.{0,20}(codebase|projeto|inteiro)\b",
        r"\b(compara|pr[óo]s? e contras?)\b",
        r"\b(analis[ae]|avali[ae]|avaliar).{0,30}(op[çc][ãa]o|abordagem|estrat[ée]gia)\b",
        r"\b(complexo|intrincado|sofisticado)\b",
        r"\botimiza[çc][ãa]o.{0,20}(performance|velocidade|mem[óo]ria)\b",
        r"\b(multi-?fase|migra[çc][ãa]o)\b",
    ],
}
# ponytail: cobertura de padroes PT e o "fast" comeca de frase (^) e nao
# meio de frase ("me ajuda a ver como funciona" nao bate com "^como funciona").
# Cobre os casos testados nesta sessao; ampliar padroes conforme aparecerem
# falsos "fast" no uso real, em vez de tentar prever tudo agora.


def is_plan_request(prompt: str) -> bool:
    lower = prompt.lower()
    return any(re.search(p, lower) for p in PLAN_TRIGGER_PATTERNS)


def get_api_key():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return api_key
    search_paths = [
        Path.cwd() / ".env",
        Path.cwd() / "server" / ".env",
        Path.home() / ".anthropic" / "api_key",
        Path.home() / ".config" / "anthropic" / "key",
    ]
    for env_path in search_paths:
        try:
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                for line in content.split("\n"):
                    if line.startswith("ANTHROPIC_API_KEY="):
                        return line.strip().split("=", 1)[1].strip('"\'')
                if content.strip().startswith("sk-ant-"):
                    return content.strip()
        except (FileNotFoundError, PermissionError, OSError):
            continue
    return None


def calculate_cost(route: str, input_tokens: int = AVG_INPUT_TOKENS, output_tokens: int = AVG_OUTPUT_TOKENS) -> float:
    costs = COST_PER_1M[route]
    return (input_tokens / 1_000_000) * costs["input"] + (output_tokens / 1_000_000) * costs["output"]


def log_routing_decision(route: str, confidence: float, method: str, signals: list):
    try:
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        stats = {
            "version": "1.0", "total_queries": 0,
            "routes": {"fast": 0, "standard": 0, "deep": 0, "plan": 0},
            "estimated_savings": 0.0, "sessions": [], "last_updated": None,
        }
        if STATS_FILE.exists():
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    stats = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        stats["total_queries"] += 1
        stats["routes"].setdefault(route, 0)
        stats["routes"][route] += 1

        if route in COST_PER_1M:
            savings = calculate_cost("deep") - calculate_cost(route)
            stats["estimated_savings"] += savings

        today = datetime.now().strftime("%Y-%m-%d")
        session = next((s for s in stats.get("sessions", []) if s["date"] == today), None)
        if not session:
            session = {"date": today, "queries": 0, "routes": {"fast": 0, "standard": 0, "deep": 0, "plan": 0}, "savings": 0.0}
            stats.setdefault("sessions", []).append(session)
        session["queries"] += 1
        session["routes"].setdefault(route, 0)
        session["routes"][route] += 1

        stats["sessions"] = sorted(stats["sessions"], key=lambda x: x["date"], reverse=True)[:30]
        stats["last_updated"] = datetime.now().isoformat()

        # ponytail: escreve em arquivo temp + os.replace (atomico) em vez de
        # abrir STATS_FILE direto em "w" -- isso trunca o arquivo ANTES do lock
        # ser adquirido, entao dois hooks concorrentes (duas sessoes abertas)
        # podiam deixar o stats vazio/corrompido. os.replace nunca deixa o
        # arquivo num estado parcial, nao depende da granularidade do lock.
        fd, tmp_path = tempfile.mkstemp(dir=STATS_FILE.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(stats, f, indent=2)
            os.replace(tmp_path, STATS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        pass  # stats logging must never fail the hook


def classify_by_rules(prompt: str) -> dict:
    prompt_lower = prompt.lower()
    signals = []
    for pattern in PATTERNS["deep"]:
        match = re.search(pattern, prompt_lower)
        if match:
            signals.append(match.group(0))
            if len(signals) >= 2:
                return {"route": "deep", "confidence": 0.9, "signals": signals[:3], "method": "rules"}
    if signals:
        return {"route": "deep", "confidence": 0.7, "signals": signals, "method": "rules"}

    fast_signals = []
    for pattern in PATTERNS["fast"]:
        match = re.search(pattern, prompt_lower)
        if match:
            fast_signals.append(match.group(0))
            if len(fast_signals) >= 2:
                return {"route": "fast", "confidence": 0.9, "signals": fast_signals[:3], "method": "rules"}
    if fast_signals:
        return {"route": "fast", "confidence": 0.7, "signals": fast_signals, "method": "rules"}

    # ponytail: sem sinal forte de fast nem deep, o default e "standard" (Sonnet),
    # nao "fast" -- a maior parte do trabalho de codigo sem marcador especial e
    # implementacao normal, nao tarefa mecanica. "fast" continua alcancavel, so
    # precisa de sinal de verdade (regex ou LLM fallback com ANTHROPIC_API_KEY).
    return {"route": "standard", "confidence": 0.5, "signals": ["no strong patterns"], "method": "rules"}


def classify_by_llm(prompt: str, api_key: str) -> dict:
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    # timeout curto: isso e so uma sugestao de rota, nao vale travar a mensagem
    # do usuario esperando rede lenta -- fix real de teste ao vivo (code-reviewer)
    client = Anthropic(api_key=api_key, timeout=5.0)
    classification_prompt = f"""Classify this coding query into exactly one route. Return ONLY valid JSON, no other text.

Query: "{prompt}"

Routes:
- "fast": Simple factual questions, syntax lookups, formatting, git status, JSON/YAML manipulation
- "standard": Bug fixes, feature implementation, code review, refactoring, test writing
- "deep": Architecture decisions, system design, security audits, multi-file refactors, trade-off analysis, complex debugging

Return JSON only:
{{"route": "fast|standard|deep", "confidence": 0.0-1.0, "signals": ["signal1", "signal2"]}}"""
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=100,
            messages=[{"role": "user", "content": classification_prompt}],
        )
        response_text = message.content[0].text.strip()
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:].strip()
        result = json.loads(response_text)
        # ponytail: a LLM pode alucinar fora do schema (route invalido, campo
        # faltando, confidence como string) -- validar antes de devolver, senao
        # o main() quebra tentando indexar subagent_map[route] com KeyError.
        if not isinstance(result, dict) or result.get("route") not in ("fast", "standard", "deep"):
            return None
        result.setdefault("confidence", 0.5)
        result.setdefault("signals", ["llm classification"])
        if not isinstance(result["confidence"], (int, float)):
            result["confidence"] = 0.5
        if not isinstance(result["signals"], list):
            result["signals"] = [str(result["signals"])]
        result["method"] = "haiku-llm"
        return result
    except Exception:
        # nao logar a excecao crua -- evita vazar detalhe de erro de cliente
        # HTTP que a lib pode mudar no futuro
        print("LLM classification error (fallback to rules)", file=sys.stderr)
        return None


def classify_hybrid(prompt: str) -> dict:
    result = classify_by_rules(prompt)
    if result["confidence"] < CONFIDENCE_THRESHOLD:
        api_key = get_api_key()
        if api_key:
            llm_result = classify_by_llm(prompt, api_key)
            if llm_result:
                return llm_result
    return result


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # ponytail: payload pode vir malformado (lista, string, numero) em vez de
    # dict -- .get() direto quebraria com AttributeError
    if not isinstance(input_data, dict):
        sys.exit(0)

    prompt = input_data.get("prompt", "")
    if not isinstance(prompt, str) or not prompt or len(prompt) < 10:
        sys.exit(0)
    if prompt.strip().startswith("/"):
        sys.exit(0)

    # ponytail: tudo daqui pra frente e classificacao best-effort -- qualquer
    # excecao nao prevista NUNCA deve travar/quebrar a mensagem do usuario.
    # Falha aberta (sys.exit(0), sem sugestao de rota) em vez de propagar.
    try:
        if is_plan_request(prompt):
            log_routing_decision("plan", 1.0, "plan-trigger", ["explicit plan request"])
            context = """[claude-orchestrator] PLAN MODE TRIGGERED
Explicit plan request detected. Skip the fast/standard/deep classifier.

Use the generate-plan skill to produce the plan, then decompose-plan to break
it into steps with a model tier and dependencies each, then execute-plan
(after ExitPlanMode approval) to run it."""
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}))
            sys.exit(0)

        result = classify_hybrid(prompt)
        route = result["route"]
        confidence = result["confidence"]
        signals = result["signals"]
        method = result.get("method", "rules")

        log_routing_decision(route, confidence, method, signals)

        subagent_map = {"fast": "fast-executor", "standard": "standard-executor", "deep": "deep-executor"}
        model_map = {"fast": "Haiku", "standard": "Sonnet", "deep": "Opus"}
        subagent = subagent_map.get(route, "standard-executor")
        model = model_map.get(route, "Sonnet")
        signals_str = ", ".join(str(s) for s in signals)

        if route == "deep":
            context = f"""[claude-orchestrator] ROUTING SUGGESTION
Route: deep | Confidence: {confidence:.0%} | Method: {method}
Signals: {signals_str}

This looks complex. Two sub-cases -- judge which one, the classifier can't:
- Vague / underspecified (no concrete steps yet) -> use generate-plan, then
  decompose-plan, then execute-plan (after ExitPlanMode approval).
- Already has a clear scope with named steps -> skip generate-plan, go
  straight to decompose-plan on what the user already described.
- Actually a single standalone deep task, not plan-shaped -> spawn
  "claude-orchestrator:deep-executor" via Task instead.
Skip all of this for: questions about the orchestrator itself, or mid-plan work."""
        else:
            context = f"""[claude-orchestrator] ROUTING SUGGESTION
Route: {route} | Model: {model} | Confidence: {confidence:.0%} | Method: {method}
Signals: {signals_str}

If this looks right for a standalone task, use the Task tool to spawn the
"claude-orchestrator:{subagent}" subagent instead of responding directly.
Skip this for: questions about the orchestrator itself, mid-plan work, or
anything requiring judgment this classifier can't see (short/ambiguous
prompts default to "fast" even when the real task is bigger)."""

        output = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}
        print(json.dumps(output))
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        # nunca travar/bloquear a mensagem do usuario por falha do classificador
        sys.exit(0)


if __name__ == "__main__":
    main()
