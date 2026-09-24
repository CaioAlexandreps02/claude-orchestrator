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
from pathlib import Path
from datetime import datetime
# Cross-platform file locking
import platform
if platform.system() == "Windows":
    import msvcrt
    def lock_file(f, exclusive=False):
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK if exclusive else msvcrt.LK_LOCK, 1)
    def unlock_file(f):
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl
    def lock_file(f, exclusive=False):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
    def unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

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
PLAN_TRIGGER_PATTERNS = [
    r"\b(fa[çc]a|faz|cri[ae]|gera|monta|elabora)\s+um\s+plano\b",
    r"\bplano\s+de\s+implementa[çc][ãa]o\b",
    r"\bplaneja\b",
    r"\bquero\s+um\s+plano\b",
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
            with open(env_path, "r") as f:
                content = f.read()
                for line in content.split("\n"):
                    if line.startswith("ANTHROPIC_API_KEY="):
                        return line.strip().split("=", 1)[1].strip('"\'')
                if content.strip().startswith("sk-ant-"):
                    return content.strip()
        except (FileNotFoundError, PermissionError):
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
                with open(STATS_FILE, "r") as f:
                    lock_file(f, exclusive=False)
                    stats = json.load(f)
                    unlock_file(f)
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

        with open(STATS_FILE, "w") as f:
            lock_file(f, exclusive=True)
            json.dump(stats, f, indent=2)
            unlock_file(f)
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

    return {"route": "fast", "confidence": 0.5, "signals": ["no strong patterns"], "method": "rules"}


def classify_by_llm(prompt: str, api_key: str) -> dict:
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    client = Anthropic(api_key=api_key)
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
        result["method"] = "haiku-llm"
        return result
    except Exception as e:
        print(f"LLM classification error: {e}", file=sys.stderr)
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

    prompt = input_data.get("prompt", "")
    if not prompt or len(prompt) < 10:
        sys.exit(0)
    if prompt.strip().startswith("/"):
        sys.exit(0)

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
    subagent = subagent_map[route]
    model = model_map[route]
    signals_str = ", ".join(signals)

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


if __name__ == "__main__":
    main()
