"""Evidências da reprodução da 8.2 por código versionado e testado (CB-7 do Checkpoint B).

Só stdlib — não importa `financial_forecasting` (roda em qualquer árvore e no host).

    python scripts/reproduction_evidence.py env-equal <ATTEMPTS.jsonl> <foto.json> \\
        --preregistration-ref <ref>
    python scripts/reproduction_evidence.py ast-equal <rev_a> <rev_b> [--paths src/ ...]

`env-equal` (base de A2/I4): compara a ÚLTIMA linha `phase = started` do `ATTEMPTS.jsonl`
da `--preregistration-ref` (obrigatória — CC2-2, CC3-1) com a foto do ambiente gravada
pelo driver (`environment.json` ou o stdout do `--check`):
`commit` igual; `code_dirty` e `preregistration_dirty` da foto = `"false"`; o conjunto e os
valores das chaves `code.*` = `code` da linha e das `env.*` = `environment`. Imprime
`ENV_EQUAL` e sai 0, ou uma linha por divergência (`missing`/`extra`/`different`/`dirty`/
`unexpected`) e sai 1.

`ast-equal` (base de A7, R-BIT-COMMIT): roda um auto-teste embutido (docstrings diferentes ⇒
igual; `x = 1` contra `x = 2` ⇒ diferente; f-strings adjacentes unidas ⇒ igual) e então,
para cada arquivo modificado (`M`) de `git diff --name-status -M <a> <b> -- <paths>`,
compara o `ast.dump` das duas versões (`git show`) com o docstring removido do corpo de todo
`Module`/`ClassDef`/`FunctionDef`/`AsyncFunctionDef` (`pass` se o corpo esvaziar) e as
partes constantes adjacentes de cada f-string fundidas. Imprime `AST_EQUAL`/`AST_DIFF` por
arquivo, os `A`/`D`/`R` à parte (`ADDED`/`DELETED`/`RENAMED`) e `files <n> ast_diff <n>`;
sai 1 se `ast_diff > 0` ou houver A/D/R. Arquivo não-`.py` modificado conta como diferença
de AST se os bytes diferem. O git roda no diretório corrente (respeita `GIT_DIR`).
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, TextIO

ENV_EQUAL: Final = "ENV_EQUAL"
STARTED: Final = "started"
COMMIT_KEY: Final = "commit"
DIRTY_KEYS: Final = ("code_dirty", "preregistration_dirty")
CODE_PREFIX: Final = "code."
ENV_PREFIX: Final = "env."
EXIT_DIFFERENT: Final = 1


# --- env-equal ----------------------------------------------------------------------------


def started_line(attempts: str, preregistration_ref: str) -> dict[str, object]:
    """A última linha `phase = started` da referência no `ATTEMPTS.jsonl`.

    Raises:
        ValueError: nenhuma linha `started` (da referência).
    """
    lines = [json.loads(line) for line in attempts.splitlines() if line.strip()]
    started: list[dict[str, object]] = [
        line
        for line in lines
        if line.get("phase") == STARTED and line.get("preregistration_ref") == preregistration_ref
    ]
    if not started:
        raise ValueError(f"ATTEMPTS.jsonl has no started line of {preregistration_ref}")
    return started[-1]


def _compare_map(expected: object, snapshot: dict[str, str], prefix: str) -> list[str]:
    attempt = dict(expected) if isinstance(expected, dict) else {}
    taken = {key: value for key, value in snapshot.items() if key.startswith(prefix)}
    problems = [f"missing {key}" for key in sorted(set(attempt) - set(taken))]
    problems += [f"extra {key}" for key in sorted(set(taken) - set(attempt))]
    problems += [
        f"different {key} attempt {attempt[key]} snapshot {taken[key]}"
        for key in sorted(set(attempt) & set(taken))
        if attempt[key] != taken[key]
    ]
    return problems


def env_differences(started: dict[str, object], snapshot: dict[str, str]) -> list[str]:
    """As divergências entre a linha `started` e a foto (vazio = iguais)."""
    problems: list[str] = []
    if snapshot.get(COMMIT_KEY) != started.get(COMMIT_KEY):
        problems.append(
            f"different {COMMIT_KEY} attempt {started.get(COMMIT_KEY)} "
            f"snapshot {snapshot.get(COMMIT_KEY)}"
        )
    problems += [
        f"dirty {key} {snapshot.get(key)}" for key in DIRTY_KEYS if snapshot.get(key) != "false"
    ]
    problems += _compare_map(started.get("code"), snapshot, CODE_PREFIX)
    problems += _compare_map(started.get("environment"), snapshot, ENV_PREFIX)
    known = (COMMIT_KEY, *DIRTY_KEYS)
    problems += [
        f"unexpected {key}"
        for key in sorted(snapshot)
        if key not in known and not key.startswith((CODE_PREFIX, ENV_PREFIX))
    ]
    return problems


def env_equal(
    attempts_path: Path,
    snapshot_path: Path,
    out: TextIO,
    preregistration_ref: str,
) -> int:
    """`ENV_EQUAL` e 0, ou as divergências e 1."""
    started = started_line(attempts_path.read_text(encoding="utf-8"), preregistration_ref)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    problems = env_differences(started, snapshot)
    out.write("".join(f"{line}\n" for line in problems or [ENV_EQUAL]))
    return EXIT_DIFFERENT if problems else 0


# --- ast-equal ----------------------------------------------------------------------------

_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


class _Normalize(ast.NodeTransformer):
    """Remove docstrings e funde as partes constantes adjacentes das f-strings."""

    def generic_visit(self, node: ast.AST) -> ast.AST:
        node = super().generic_visit(node)
        if isinstance(node, _DOCSTRING_OWNERS):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
        if isinstance(node, ast.JoinedStr):
            merged: list[ast.expr] = []
            for part in node.values:
                if (
                    merged
                    and isinstance(part, ast.Constant)
                    and isinstance(merged[-1], ast.Constant)
                ):
                    merged[-1] = ast.Constant(value=str(merged[-1].value) + str(part.value))
                else:
                    merged.append(part)
            node.values = merged
        return node


def normalized_dump(source: str) -> str:
    """O `ast.dump` sem docstrings e com as f-strings fundidas (sem posições)."""
    return ast.dump(_Normalize().visit(ast.parse(source)), include_attributes=False)


_SELF_TEST: Final = (
    ('"""a."""\nx = 1\n', '"""b."""\nx = 1\n', True),
    ("x = 1\n", "x = 2\n", False),
    ('def f(y):\n    """doc."""\n', "def f(y):\n    pass\n", True),
    ('s = f"a" f"b{x}"\n', 's = f"ab{x}"\n', True),
)


def self_test() -> None:
    """O normalizador decide como esperado nos casos de referência.

    Raises:
        AssertionError: algum caso decide errado.
    """
    for left, right, expected in _SELF_TEST:
        if (normalized_dump(left) == normalized_dump(right)) is not expected:
            raise AssertionError(f"ast-equal self-test failed on {left!r} vs {right!r}")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def _show(revision: str, path: str) -> str:
    return _git("show", f"{revision}:{path}")


def ast_equal(rev_a: str, rev_b: str, paths: Sequence[str], out: TextIO) -> int:
    """`AST_EQUAL`/`AST_DIFF` por arquivo `M`, A/D/R à parte e o total; 1 se algo difere."""
    self_test()
    status = _git("diff", "--name-status", "-M", rev_a, rev_b, "--", *paths)
    lines: list[str] = []
    apart: list[str] = []
    files = differ = 0
    for row in status.splitlines():
        fields = row.split("\t")
        code = fields[0][:1]
        if code == "M":
            path = fields[1]
            files += 1
            before, after = _show(rev_a, path), _show(rev_b, path)
            equal = (
                normalized_dump(before) == normalized_dump(after)
                if path.endswith(".py")
                else before == after
            )
            differ += 0 if equal else 1
            lines.append(f"{'AST_EQUAL' if equal else 'AST_DIFF'} {path}")
        elif code == "A":
            apart.append(f"ADDED {fields[1]}")
        elif code == "D":
            apart.append(f"DELETED {fields[1]}")
        elif code == "R":
            apart.append(f"RENAMED {fields[1]} -> {fields[2]}")
        else:
            apart.append(f"OTHER {row}")
    out.write("".join(f"{line}\n" for line in [*lines, *apart, f"files {files} ast_diff {differ}"]))
    return EXIT_DIFFERENT if differ or apart else 0


def main(argv: Sequence[str] | None = None, *, out: TextIO | None = None) -> int:
    """Despacha `env-equal` ou `ast-equal`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    env = commands.add_parser("env-equal")
    env.add_argument("attempts", type=Path)
    env.add_argument("snapshot", type=Path)
    env.add_argument("--preregistration-ref", required=True)
    tree = commands.add_parser("ast-equal")
    tree.add_argument("rev_a")
    tree.add_argument("rev_b")
    tree.add_argument("--paths", nargs="+", default=["src/"])
    args = parser.parse_args(argv)
    stream = out or sys.stdout
    if args.command == "env-equal":
        return env_equal(args.attempts, args.snapshot, stream, args.preregistration_ref)
    return ast_equal(args.rev_a, args.rev_b, args.paths, stream)


if __name__ == "__main__":
    sys.exit(main())
