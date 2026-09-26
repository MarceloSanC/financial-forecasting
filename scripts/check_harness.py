"""Valida o frontmatter do harness do Claude Code: skills e subagentes do projeto.

Uso: python scripts/check_harness.py   (exit 0 = ok, 1 = achados)

O Claude Code não reporta erro de frontmatter: YAML inválido carrega a skill "with no fields
set", campo desconhecido é ignorado em silêncio, e a descrição é truncada no listing em 1.536
caracteres (docs: code.claude.com/docs/en/skills, /sub-agents). Caso real que motivou o script:
` #` num valor sem aspas é comentário YAML — a descrição da `issue-audit` era lida com 150 dos
1.568 caracteres, sem aviso.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DESC_CAP = 1536
SKILL_FIELDS = {
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools", "disallowed-tools",
    "model", "effort", "context", "agent", "background", "hooks", "paths", "shell",
    "metadata", "license", "compatibility",
}  # fmt: skip
AGENT_FIELDS = {
    "name", "description", "tools", "disallowedTools", "model", "permissionMode", "maxTurns",
    "skills", "mcpServers", "hooks", "memory", "background", "omitClaudeMd", "effort",
    "isolation", "color", "initialPrompt", "experimental",
}  # fmt: skip


def _frontmatter(text: str) -> tuple[str, dict[str, Any]] | str:
    if not text.startswith("---"):
        return "sem frontmatter (o `---` de abertura precisa ser a 1ª linha)"
    parts = text.split("---", 2)
    if len(parts) < 3:  # noqa: PLR2004 — abertura + corpo do YAML + resto
        return "frontmatter sem `---` de fechamento"
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        return f"YAML inválido: {str(exc).splitlines()[0]}"
    if not isinstance(data, dict):
        return "frontmatter não é um mapa YAML"
    return parts[1], data


def _raw_value(raw_yaml: str, key: str) -> str:
    for line in raw_yaml.splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


def check_file(path: Path, allowed: set[str], required: tuple[str, ...]) -> list[str]:
    parsed = _frontmatter(path.read_text(encoding="utf-8"))
    if isinstance(parsed, str):
        return [parsed]
    raw_yaml, data = parsed
    problems = [f"campo obrigatório ausente: `{k}`" for k in required if not data.get(k)]
    problems += [
        f"campo desconhecido (ignorado em silêncio): `{k}`" for k in data if k not in allowed
    ]
    desc = str(data.get("description") or "")
    raw = _raw_value(raw_yaml, "description")
    plain = raw and not raw.startswith(('"', "'", ">", "|"))
    if plain and " #" in raw:  # YAML: ` #` em escalar sem aspas abre comentário
        problems.append(f"descrição truncada pelo YAML em ` #` ({len(desc)} chars lidos)")
    total = len(desc) + len(str(data.get("when_to_use") or ""))
    if total > DESC_CAP:
        problems.append(
            f"description+when_to_use = {total} > {DESC_CAP} (cauda cortada no listing)"
        )
    return problems


def check_overrides(settings: Path, skill_names: set[str]) -> list[str]:
    if not settings.exists():
        return []
    overrides = json.loads(settings.read_text(encoding="utf-8")).get("skillOverrides", {})
    return [
        f"skillOverrides aponta skill inexistente: `{n}`" for n in overrides if n not in skill_names
    ]


def main() -> int:
    findings: list[str] = []
    skills = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    for path in skills:
        findings += [f"{path.relative_to(ROOT)}: {p}" for p in check_file(path, SKILL_FIELDS, ())]
    for path in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        found = check_file(path, AGENT_FIELDS, ("name", "description"))
        findings += [f"{path.relative_to(ROOT)}: {p}" for p in found]
    settings = ROOT / ".claude" / "settings.json"
    findings += check_overrides(settings, {p.parent.name for p in skills})
    for line in findings:
        print(line)
    print(f"check_harness: {len(findings)} achado(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
