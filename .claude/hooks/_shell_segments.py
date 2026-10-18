"""Segmentação de comando de shell comum aos hooks PreToolUse (`git_guard`, `publish_guard`).

A permissão do Claude Code é avaliada por subcomando, então o hook precisa ver cada um:
- separadores: `&&`, `||`, `;`, `|`, `&` (inclusive o operador de chamada do PowerShell) e
  quebra de linha;
- antes do executável saem `(`, `{`, `$(`, atribuição `VAR=x` e wrappers/palavras de shell
  (`env`, `sudo`, `then`, `do`…); `)`/`}` de grupo saem do fim de cada token;
- bloco do PowerShell depois de palavra de controle (`if (…) { cmd }`, `foreach (…) { cmd }`): o
  `cmd` é o subcomando (só o primeiro bloco do segmento);
- diretório efetivo = `cwd` do hook, seguido de `cd`/`Set-Location`/`pushd` anteriores no mesmo
  comando (`popd` volta) e de `git -C <dir>`. `cd` dentro de `( … )`/`$( … )` vale só até o `)`:
  subshell no bash; no PowerShell o `cd` persistiria, e esquecê-lo erra para o lado de recusar.

Fora do alcance (o classificador cobre): `bash -c`/`pwsh -c`/`cmd /c`, `eval`, aliases, scripts.
Não é hook: o nome com `_` o deixa fora de `.claude/settings.json`.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterator
from pathlib import Path, PureWindowsPath

SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|&\n]")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = {"env", "command", "time", "nohup", "sudo", "exec", "xargs"}
_WRAPPERS |= {"then", "do", "else", "elif", "if", "while", "until", "!"}  # palavra de shell
_GROUP_OPEN = "({$"
_SUBSHELL_LEAD = " \t\r$("
_BLOCK_KEYWORDS = {"if", "elseif", "else", "foreach", "for", "while", "switch", "do", "try"}
_CD = ("cd", "Set-Location", "pushd", "Push-Location")
_PUSH = ("pushd", "Push-Location")
_POP = ("popd", "Pop-Location")
_GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def tokens(segment: str) -> list[str]:
    try:  # posix=False preserva `\` de caminho Windows; aspas e `)`/`}` de grupo removidos à mão
        raw = (t.rstrip(")}").strip("\"'") for t in shlex.split(segment, posix=False))
        return [t for t in raw if t]  # `)`/`}` soltos viram token vazio
    except ValueError:
        return segment.split()


def _strip_prefix(toks: list[str]) -> list[str]:
    while toks and (
        _ENV_ASSIGN.match(toks[0]) or toks[0] in _WRAPPERS or not toks[0].lstrip(_GROUP_OPEN)
    ):
        toks = toks[1:]
    if toks:
        toks[0] = toks[0].lstrip(_GROUP_OPEN)
    return toks


def _block(toks: list[str]) -> list[str]:
    """`if (…) { cmd }` do PowerShell → `cmd`; sem palavra de controle seguida de `{`, intacto."""
    if not toks or toks[0].lower() not in _BLOCK_KEYWORDS:
        return toks
    block = next((i for i, t in enumerate(toks) if t.startswith("{")), None)
    return toks if block is None else toks[block:]  # o `{` sai em `_strip_prefix`


def commands(command: str, cwd: Path) -> Iterator[tuple[Path, list[str]]]:
    """(diretório efetivo, tokens desde o executável) por subcomando; `cd` não é emitido."""
    here = cwd
    subshells: list[Path] = []  # diretório de fora de cada `(` aberto
    pushed: list[Path] = []
    for segment in SEGMENT_SPLIT.split(command):
        opens = segment[: len(segment) - len(segment.lstrip(_SUBSHELL_LEAD))].count("(")
        subshells += [here] * opens
        toks = _strip_prefix(_block(tokens(segment)))
        if toks and toks[0] in _CD:
            if toks[0] in _PUSH:
                pushed.append(here)
            dirs = [t for t in toks[1:] if t not in ("-Path", "-LiteralPath")]
            here = (here / dirs[0]).resolve() if dirs else here
        elif toks and toks[0] in _POP:
            here = pushed.pop() if pushed else here
        elif toks:
            yield here, toks
        for _ in range(segment.count(")") - segment.count("(") + opens):  # `)` que fecha subshell
            here = subshells.pop() if subshells else here


def executable(toks: list[str]) -> str:
    """`git`, `/usr/bin/git` e `C:\\Git\\bin\\git.exe` → `git` (em qualquer SO)."""
    return PureWindowsPath(toks[0]).stem.lower()  # separa por `/` e por `\`


def git_invocation(toks: list[str], here: Path) -> tuple[Path, list[str], list[str]]:
    """`git <opções globais> <sub> ...` → (diretório do `-C`, valores de `-c`, `<sub> ...`)."""
    target, i, config = here, 1, []
    while i < len(toks) and toks[i].startswith("-"):
        if toks[i] == "-C" and i + 1 < len(toks):
            target = (here / toks[i + 1]).resolve()
        if toks[i] == "-c" and i + 1 < len(toks):
            config.append(toks[i + 1])
        i += 2 if toks[i] in _GIT_OPTS_WITH_VALUE else 1
    return target, config, toks[i:]
