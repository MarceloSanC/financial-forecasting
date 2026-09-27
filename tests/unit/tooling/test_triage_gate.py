"""Unit do hook `.claude/hooks/triage_gate.py`.

Casos reais: as mensagens de fim de turno vêm das sessões da Stage 5.4 e da #78
(forks "a ratificar" que chegaram ao humano sendo convenção metodológica).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "triage_gate.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("triage_gate", _HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass resolve o módulo pelo nome
    spec.loader.exec_module(module)
    return module


tg = _load()


def _ask(*headers: str) -> dict[str, Any]:
    questions = [{"question": f"q{i}?", "header": h, "options": []} for i, h in enumerate(headers)]
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": questions},
    }


def _stop(message: str, *, active: bool = False, event: str = "Stop") -> dict[str, Any]:
    return {"hook_event_name": event, "stop_hook_active": active, "last_assistant_message": message}


def test_ask_with_all_p_headers_passes() -> None:
    assert tg.decide(_ask("P:Escopo", "P:Prazo")) is None


def test_ask_with_unclassified_header_is_denied() -> None:
    out = tg.decide(_ask("P:Escopo", "B2 — Horizon"))
    assert out is not None
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "q1?" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_other_tools_are_ignored() -> None:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {}}
    assert tg.decide(payload) is None


@pytest.mark.parametrize("event", ["Stop", "SubagentStop"])
def test_stop_blocks_on_pending_ratification(event: str) -> None:
    msg = '2. **8 forks para você ratificar** (marcados "a ratificar — B-…" no §10): B-CRPS'
    out = tg.decide(_stop(msg, event=event))
    assert out is not None and out["decision"] == "block"


def test_stop_blocks_on_b_label_offered_as_question() -> None:
    assert tg.decide(_stop('## B2 — Gate H1 (que teste único decide "calibrado"?)')) is not None


def test_stop_passes_when_fork_is_tagged_p() -> None:
    assert tg.decide(_stop("**B1 [P]** — a busca de hiperparâmetros cabe nesta Stage?")) is None


def test_stop_passes_on_resolved_fork_narration() -> None:
    msg = (
        "Sobre B4: sem limite de tarefas, o varredor Optuna permanece na Stage.\nSegui com **B1**."
    )
    assert tg.decide(_stop(msg)) is None


def test_stop_passes_on_prose_about_ratification() -> None:
    # falso positivo real (sessão de criação do hook): narrar o caso da #78
    msg = "- O agente citou Eq./página e devolveu 11 convenções para você ratificar (B-CRPS)."
    assert tg.decide(_stop(msg)) is None


def test_stop_passes_when_line_declares_the_forks_closed() -> None:
    # falso positivo real (sessão que fechou a #78): o marcador citado como nome
    msg = '- **As 11 bifurcações "a ratificar" estão fechadas**, com registro em §10.1 do doc.'
    assert tg.decide(_stop(msg)) is None


@pytest.mark.parametrize(
    "msg",
    [
        "B-HORIZON (a ratificar): ainda não decidido",
        "3 forks a ratificar, a ser resolvido por você",
        "(a ratificar — B-GATE) será tratado no próximo PR",
        'As bifurcações "a ratificar" não estão fechadas',
    ],
)
def test_stop_still_blocks_when_closing_word_is_negated_or_future(msg: str) -> None:
    # a palavra de fechamento sozinha não basta: pendência negada/futura segue bloqueando
    out = tg.decide(_stop(msg))
    assert out is not None and out["decision"] == "block"


def test_stop_never_blocks_twice() -> None:
    assert tg.decide(_stop("B-GATE a ratificar", active=True)) is None
