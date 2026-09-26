"""Custo de uma sessão do Claude Code medido do transcript — sem autorrelato do agente.

Uso (stdlib; roda no host):
    python scripts/session_cost.py <session-id | caminho.jsonl> [...] [--json]

Soma a sessão principal e os subagentes (`<sessão>/subagents/*.jsonl`). Métricas:
- tokens por classe (input, cache_creation, cache_read, output);
- requisições à API (deduplicadas por `requestId`: o transcript repete a mesma `usage` em
  cada bloco de streaming — somar entradas infla o custo ~2-3x);
- tempo de parede (1º → último evento) e tempo humano (soma dos intervalos entre a última
  resposta do agente e cada mensagem do humano — limite superior: inclui ausência), turnos
  humanos e `AskUserQuestion`.

Comparação justa: mesmo modelo e esforço (as classes de token têm preços diferentes entre si;
compare classe a classe, ou use o `total_cost_usd` do `claude -p --output-format json`).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECTS = Path.home() / ".claude" / "projects"
TOKEN_CLASSES = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                 "output_tokens")  # fmt: skip


@dataclass
class Cost:
    requests: int = 0
    tokens: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TOKEN_CLASSES, 0))
    wall_clock_s: float = 0.0
    human_s: float = 0.0
    human_turns: int = 0
    ask_user_question: int = 0
    models: list[str] = field(default_factory=list)


def resolve(arg: str) -> Path:
    path = Path(arg)
    if path.is_file():
        return path
    matches = list(PROJECTS.glob(f"*/{arg}.jsonl"))
    if len(matches) != 1:
        raise SystemExit(f"sessão não encontrada (ou ambígua) em {PROJECTS}: {arg}")
    return matches[0]


def _ts(entry: dict[str, Any]) -> datetime | None:
    raw = entry.get("timestamp")
    return datetime.fromisoformat(raw.replace("Z", "+00:00")) if isinstance(raw, str) else None


def _is_human(entry: dict[str, Any]) -> bool:
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return not content.startswith("<")  # comandos locais / lembretes do sistema
    blocks = content if isinstance(content, list) else []
    kinds = {b.get("type") for b in blocks if isinstance(b, dict)}
    return "text" in kinds and "tool_result" not in kinds


def measure(entries: list[dict[str, Any]], cost: Cost) -> None:
    seen: set[str] = set()
    last_agent: datetime | None = None
    stamps = [t for t in (_ts(e) for e in entries) if t]
    if stamps:
        cost.wall_clock_s += (max(stamps) - min(stamps)).total_seconds()
    for entry in entries:
        message = entry.get("message") or {}
        if entry.get("type") == "assistant":
            last_agent = _ts(entry) or last_agent
            for block in message.get("content") or []:
                name = block.get("name") if isinstance(block, dict) else None
                cost.ask_user_question += name == "AskUserQuestion"
            request = entry.get("requestId") or entry.get("uuid")
            if request in seen or not message.get("usage"):
                continue
            seen.add(request)
            usage = message["usage"]
            cost.requests += 1
            for key in TOKEN_CLASSES:
                cost.tokens[key] += int(usage.get(key) or 0)
            model = message.get("model")
            if model and model not in cost.models:
                cost.models.append(model)
        elif _is_human(entry):
            cost.human_turns += 1
            now = _ts(entry)
            if now and last_agent and now > last_agent:
                cost.human_s += (now - last_agent).total_seconds()


def _load(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def session_cost(path: Path) -> Cost:
    cost = Cost()
    measure(_load(path), cost)
    for sub in sorted((path.parent / path.stem / "subagents").glob("*.jsonl")):
        sub_cost = Cost()
        measure(_load(sub), sub_cost)  # tempo do subagente já está dentro do da sessão
        cost.requests += sub_cost.requests
        for key in TOKEN_CLASSES:
            cost.tokens[key] += sub_cost.tokens[key]
        cost.models += [m for m in sub_cost.models if m not in cost.models]
    return cost


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sessions", nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    results = {s: session_cost(resolve(s)) for s in args.sessions}
    if args.json:
        print(json.dumps({s: asdict(c) for s, c in results.items()}, indent=2))
        return 0
    for name, c in results.items():
        t = c.tokens
        print(
            f"{name}: {c.requests} req | in {t['input_tokens']:,} | cache_w "
            f"{t['cache_creation_input_tokens']:,} | cache_r {t['cache_read_input_tokens']:,} | "
            f"out {t['output_tokens']:,} | parede "
            f"{c.wall_clock_s / 60:.1f} min | humano {c.human_s / 60:.1f} min em "
            f"{c.human_turns} turnos | AskUserQuestion {c.ask_user_question} | {','.join(c.models)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
