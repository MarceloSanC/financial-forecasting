"""Hook PreToolUse (Bash/PowerShell): `gh issue create` exige BC e dependências no corpo.

Issue avulsa não tem linha no `docs/roadmap.md`; a sessão executora tira o BC/camada e as
dependências do corpo da issue. Este hook recusa `gh issue create` cujo corpo não traga as
seções `### BC / camada` e `### Depende de` (as mesmas que os Issue Forms de
`.github/ISSUE_TEMPLATE/` geram), cada uma seguida de valor. Não valem como valor: vazio,
`_No response_` (o que o GitHub grava para campo em branco) e placeholder `<...>`;
`nenhuma` vale.

Origem do corpo:
- inline: `--body`/`-b` (aspas, heredoc bash `$(cat <<'EOF' ... EOF)` ou here-string
  PowerShell `@' ... '@`);
- arquivo: `--body-file`/`-F <path>`, relativo ao `cwd` do hook e a `cd <dir>` anteriores no
  mesmo comando (como no `git_guard`);
- `--web`/`-w` passa: abre o formulário, que já obriga os campos;
- `-F -` (stdin) não é verificável: recusa, pedindo um arquivo.

Regra: docs/GIT-WORKFLOW.md §Etapa 1 (Criar issue).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ("BC / camada", "Depende de")
_FORMAT = (
    "o corpo precisa das seções `### BC / camada` e `### Depende de`, cada uma seguida de "
    "valor numa linha própria (vazio, `_No response_` e placeholder `<...>` não valem; "
    "`nenhuma` vale) — GIT-WORKFLOW §Etapa 1."
)
REASON_STDIN = (
    "`gh issue create -F -` (corpo via stdin) não é verificável pelo hook `issue_guard`: "
    "grave o corpo num arquivo (ferramenta Write) e passe `--body-file <arquivo>`; " + _FORMAT
)
REASON_NO_BODY = "`gh issue create` sem `--body`/`--body-file` (nem `--web`): " + _FORMAT
REASON_UNPARSEABLE = (
    "Não consegui ler o comando `gh issue create` (aspas desbalanceadas?): grave o corpo num "
    "arquivo (ferramenta Write) e passe `--body-file <arquivo>`; " + _FORMAT
)

_PUNCTUATION = ";&|()<>\n"
# o shlex funde pontuação vizinha (`);`, `)\n`, `>&`): token só de pontuação com separador ou
# parêntese é fronteira de comando; `<`/`>` sozinhos (redirecionamento) não são
_BOUNDARY_CHARS = set(";&|()\n")
_CD = {"cd", "Set-Location", "pushd"}
_NO_VALUE = {"", "_No response_"}
_PLACEHOLDER = re.compile(r"<[^<>]*>")
_HEADING = re.compile(r"\s{0,3}#{1,6}\s")
# heredoc bash: `<<'EOF'` (resto da linha) ... linha só com `EOF`
_HEREDOC = re.compile(
    r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n(?:(.*?)\n)??[ \t]*\2[ \t]*(?=\n|$)", re.DOTALL
)
# here-string PowerShell: `@'` ... `'@` (ou com aspas duplas), delimitadores em linhas próprias
_HERESTRING = re.compile(r"@(['\"])[ \t]*\r?\n(.*?)\r?\n\1@", re.DOTALL)
_DOC = re.compile(r"__ISSUE_GUARD_DOC_(\d+)__")
_EQUALS_FLAG = re.compile(r"(--body-file|--body)=")
_MSYS_DRIVE = re.compile(r"^/([a-zA-Z])/")


def _read_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def missing_fields(body: str) -> list[str]:
    """Campos obrigatórios ausentes ou sem valor válido no corpo."""
    lines = body.splitlines()
    missing = []
    for field in REQUIRED_FIELDS:
        header = re.compile(rf"\s{{0,3}}###\s+{re.escape(field)}\s*")
        starts = [i for i, line in enumerate(lines) if header.fullmatch(line)]
        if not starts or not any(_has_value(lines[i + 1 :]) for i in starts):
            missing.append(field)
    return missing


def _has_value(after: list[str]) -> bool:
    value: list[str] = []
    for line in after:
        if _HEADING.match(line):
            break
        value.append(line.strip())
    text = "\n".join(v for v in value if v)
    return text not in _NO_VALUE and not _PLACEHOLDER.fullmatch(text)


def _extract_docs(command: str) -> tuple[str, list[str]]:
    """Troca heredocs/here-strings por marcadores (o tokenizador não entende o conteúdo)."""
    docs: list[str] = []

    def heredoc(m: re.Match[str]) -> str:
        docs.append(m.group(4) or "")
        return f"__ISSUE_GUARD_DOC_{len(docs) - 1}__{m.group(3)}"

    def herestring(m: re.Match[str]) -> str:
        docs.append(m.group(2))
        return f"__ISSUE_GUARD_DOC_{len(docs) - 1}__"

    return _HERESTRING.sub(herestring, _HEREDOC.sub(heredoc, command)), docs


def _unquote(token: str) -> str:
    if len(token) > 1 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _inline_body(value: str, docs: list[str]) -> str:
    found = [docs[int(i)] for i in _DOC.findall(value)]
    return "\n".join(found) if found else _unquote(value)


def _native(raw: str, windows: bool) -> str:
    """`/c/Users/...` (Git Bash) vira `c:/Users/...` quando o hook roda no Windows."""
    return _MSYS_DRIVE.sub(r"\1:/", raw) if windows else raw


def _body_source(args: list[str]) -> tuple[str, str] | None:
    """('web'|'body'|'file', valor) da última opção de corpo; None se não houver."""
    source: tuple[str, str] | None = None
    for i, arg in enumerate(args):
        value = args[i + 1] if i + 1 < len(args) else ""
        if arg in ("--web", "-w"):
            return ("web", "")
        if arg in ("--body", "-b"):
            source = ("body", value)
        elif arg in ("--body-file", "-F"):
            source = ("file", value)
    return source


def _check_create(
    args: list[str],
    here: Path,
    docs: list[str],
    read_file: Callable[[Path], str | None],
    windows: bool,
) -> str | None:
    source = _body_source(args)
    if source is None:
        return REASON_NO_BODY
    kind, value = source
    if kind == "web":
        return None
    if kind == "body":
        body = _inline_body(value, docs)
    else:
        raw = _unquote(value)
        if raw == "-":
            return REASON_STDIN
        content = read_file(here / _native(raw, windows))
        if content is None:
            return (
                f"`gh issue create --body-file {raw}`: arquivo não encontrado no momento do "
                "comando (o hook lê antes de executar; crie o arquivo num passo anterior); "
                + _FORMAT
            )
        body = content
    missing = missing_fields(body)
    if not missing:
        return None
    absent = ", ".join(f"`### {f}`" for f in missing)
    return f"`gh issue create` recusado — sem valor válido em {absent}: " + _FORMAT


def _is_issue_create(words: list[str]) -> bool:
    return bool(words) and Path(words[0]).stem.lower() == "gh" and words[1:3] == ["issue", "create"]


def check(
    command: str,
    cwd: Path,
    read_file: Callable[[Path], str | None] = _read_file,
    windows: bool = os.name == "nt",
) -> str | None:
    """Motivo da recusa, ou None se o comando pode seguir."""
    text, docs = _extract_docs(command)
    text = _EQUALS_FLAG.sub(r"\1 ", text)
    # quebra de linha fora de aspas separa comandos, como `;`
    lexer = shlex.shlex(text, posix=False, punctuation_chars=_PUNCTUATION)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:  # posix=False preserva `\` de caminho Windows; aspas removidas à mão
        tokens = list(lexer)
    except ValueError:
        return REASON_UNPARSEABLE if re.search(r"\bgh\b.*\bissue\s+create\b", text) else None
    commands: list[list[str]] = [[]]
    for token in tokens:
        if set(token) <= set(_PUNCTUATION) and set(token) & _BOUNDARY_CHARS:
            commands.append([])
        else:
            commands[-1].append(token)
    here = cwd
    for words in commands:
        if len(words) > 1 and words[0] in _CD:
            here = (here / _native(_unquote(words[1]), windows)).resolve()
        elif _is_issue_create(words):
            reason = _check_create(words[3:], here, docs, read_file, windows)
            if reason is not None:
                return reason
    return None


def main() -> int:
    try:
        payload: dict[str, Any] = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    command = str((payload.get("tool_input") or {}).get("command") or "")
    cwd = Path(str(payload.get("cwd") or "."))
    reason = check(command, cwd) if command else None
    if reason is not None:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
