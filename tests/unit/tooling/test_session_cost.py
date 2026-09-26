"""Unit de `scripts/session_cost.py` — custo medido do transcript."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "session_cost.py"
_OUT = 10
_CACHE_READ = 100
_HUMAN_WAIT_S = 30.0


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("session_cost", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sc = _load()


def _assistant(req: str, ts: str, blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    usage = {"input_tokens": 1, "output_tokens": _OUT, "cache_read_input_tokens": _CACHE_READ}
    return {
        "type": "assistant",
        "requestId": req,
        "timestamp": ts,
        "message": {"model": "m", "usage": usage, "content": blocks or []},
    }


def _human(ts: str, text: str = "oi") -> dict[str, Any]:
    return {"type": "user", "timestamp": ts, "message": {"content": text}}


def _write(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return path


def test_streaming_blocks_of_one_request_count_once(tmp_path: Path) -> None:
    # o transcript repete a mesma `usage` em cada bloco de streaming da requisição
    entries = [_assistant("r1", "2026-01-01T00:00:00Z")] * 3 + [
        _assistant("r2", "2026-01-01T00:00:05Z")
    ]
    cost = sc.session_cost(_write(tmp_path / "s.jsonl", entries))
    assert cost.requests == len({"r1", "r2"})
    assert cost.tokens["output_tokens"] == 2 * _OUT


def test_human_time_turns_and_questions(tmp_path: Path) -> None:
    ask = [{"type": "tool_use", "name": "AskUserQuestion"}]
    entries = [
        _human("2026-01-01T00:00:00Z", "tarefa"),
        _assistant("r1", "2026-01-01T00:01:00Z", ask),
        _human("2026-01-01T00:01:30Z", "resposta"),
        {
            "type": "user",
            "timestamp": "2026-01-01T00:02:00Z",
            "message": {"content": [{"type": "tool_result"}]},
        },
        _human("2026-01-01T00:02:10Z", "<command-name>/cost</command-name>"),
    ]
    cost = sc.session_cost(_write(tmp_path / "s.jsonl", entries))
    assert cost.human_turns == len(["tarefa", "resposta"])
    assert cost.human_s == _HUMAN_WAIT_S
    assert cost.ask_user_question == 1


def test_subagent_tokens_are_added(tmp_path: Path) -> None:
    main = _write(tmp_path / "s.jsonl", [_assistant("r1", "2026-01-01T00:00:00Z")])
    (tmp_path / "s" / "subagents").mkdir(parents=True)
    _write(tmp_path / "s" / "subagents" / "a.jsonl", [_assistant("x1", "2026-01-01T00:00:01Z")])
    cost = sc.session_cost(main)
    assert cost.requests == len(["r1", "x1"])
    assert cost.tokens["cache_read_input_tokens"] == 2 * _CACHE_READ
