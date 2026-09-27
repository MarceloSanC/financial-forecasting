"""Hook de triagem: só perguntas de preferência (classe P) chegam ao humano.

Registrado em `.claude/settings.json` para três eventos (docs: code.claude.com/docs/en/hooks):
- PreToolUse[AskUserQuestion]: nega a pergunta se algum `header` não começar com `P:`.
- Stop / SubagentStop: bloqueia o fim do turno se `last_assistant_message` tiver fork
  pendente ("a ratificar", ou rótulo B1/B-XYZ oferecido como pergunta) sem `[P]` na linha.

O `stop_hook_active` (e o teto de 8 continuações do Claude Code) impede laço: a segunda
tentativa de parar sempre passa. É função de forçar a triagem, não controle de segurança.
Protocolo que a razão aponta: skill `evidence-resolution`.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

SKILL_HINT = (
    "Rode a triagem da skill `evidence-resolution` "
    "(E/C: o agente resolve por evidência; P: humano)."
)
# Casa o MARCADOR de fork em aberto ("(a ratificar — B-…)", rótulo B oferecido como
# pergunta), não prosa sobre ratificação — narrar um caso passado não é fork pendente.
_PENDING_FORK = re.compile(
    r"\ba ratificar\b"
    r"|^\W*B(?:\d+|-[A-Z][A-Z0-9-]*)\b.*(?:\?|\(Recomendad[ao]\))",
    re.IGNORECASE | re.MULTILINE,
)
# Linha que declara o item fechado não é pendência, mesmo citando o marcador (caso real, #78:
# `As 11 bifurcações "a ratificar" estão fechadas`). Aspas não servem de critério: o
# verdadeiro positivo original também cita o marcador entre aspas.
_CLOSED = re.compile(r"fechad|decidid|resolvid|tratad|encerrad|conclu[ií]d", re.IGNORECASE)
_MAX_LINES_ECHOED = 5


def unclassified_questions(tool_input: dict[str, Any]) -> list[str]:
    return [
        str(q.get("question", ""))
        for q in tool_input.get("questions", [])
        if not str(q.get("header", "")).startswith("P:")
    ]


def pending_fork_lines(message: str) -> list[str]:
    lines = []
    for line in message.splitlines():
        if _PENDING_FORK.search(line) and "[P]" not in line and not _CLOSED.search(line):
            lines.append(line.strip()[:160])
    return lines


def decide(payload: dict[str, Any]) -> dict[str, Any] | None:
    event = payload.get("hook_event_name")
    if event == "PreToolUse" and payload.get("tool_name") == "AskUserQuestion":
        bad = unclassified_questions(payload.get("tool_input") or {})
        if not bad:
            return None
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Pergunta sem triagem: {bad[0][:120]!r}. {SKILL_HINT} "
                    "Se for mesmo P (escopo, prioridade, prazo/custo, claim, editorial, ação "
                    "externa irreversível), refaça com header `P:<tema>`."
                ),
            }
        }
    if event in ("Stop", "SubagentStop") and not payload.get("stop_hook_active"):
        lines = pending_fork_lines(str(payload.get("last_assistant_message") or ""))
        if not lines:
            return None
        shown = "\n".join(f"- {line}" for line in lines[:_MAX_LINES_ECHOED])
        return {
            "decision": "block",
            "reason": (
                f"Forks pendentes sem classificação:\n{shown}\n{SKILL_HINT} Decida os E/C e "
                "registre; entregue ao humano só os P, marcados com `[P]` na linha."
            ),
        }
    return None


def main() -> int:
    try:
        # bytes → UTF-8 explícito: no Windows o stdio do Python é cp1252
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0  # hook não deve derrubar a sessão por entrada inesperada
    out = decide(payload)
    if out is not None:
        print(json.dumps(out))  # ASCII-escapado: independe do encoding do console
    return 0


if __name__ == "__main__":
    sys.exit(main())
