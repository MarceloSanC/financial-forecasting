"""Regressão do escopo do mypy (issue #204).

As suítes de contrato provam que fake e real satisfazem o Protocol do consumidor por
fixtures tipadas pelo port; a prova só existe se o `make typecheck` roda sobre elas e
resolve `financial_forecasting` de verdade. Três formas de ela sumir em silêncio:

- tirar `tests/contract` ou `tests/fakes` de `[tool.mypy] files`;
- tirar `mypy_path = "src"`: o pacote vira `Any` para um arquivo de `tests/` checado
  sozinho (o `.pth` do editable install não tem `py.typed`) e nada é conferido;
- o alvo `typecheck` do Makefile passar caminhos ao mypy, que ignora `files` quando
  recebe argumentos posicionais.

E uma forma de a frase voltar a mentir: um teste fora dos caminhos checados citar o
mypy como prova no docstring do módulo.
"""

from __future__ import annotations

import ast
import tomllib
import warnings
from pathlib import Path

import pytest
from mypy import api

_ROOT = Path(__file__).resolve().parents[2]
_PROOF_ROOTS = ("tests/contract", "tests/fakes")


def _mypy_config() -> dict[str, object]:
    config = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    mypy: dict[str, object] = config["tool"]["mypy"]
    return mypy


def _typecheck_recipe() -> list[str]:
    lines = (_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    start = lines.index("typecheck:")
    recipe: list[str] = []
    for line in lines[start + 1 :]:
        if not line.startswith("\t"):
            break
        recipe.append(line.strip())
    return recipe


def _checked(path: Path) -> bool:
    relative = path.relative_to(_ROOT).as_posix()
    return any(relative.startswith(f"{root}/") for root in _PROOF_ROOTS)


@pytest.mark.parametrize("root", ["src", *_PROOF_ROOTS])
def test_mypy_files_cover_the_proof_roots(root: str) -> None:
    files = _mypy_config()["files"]
    assert isinstance(files, list)
    assert root in files


def test_mypy_resolves_the_package_from_src() -> None:
    assert _mypy_config()["mypy_path"] == "src"


def test_typecheck_target_defers_to_pyproject_files() -> None:
    assert _typecheck_recipe() == ["uv run mypy"]


def test_mypy_claims_live_under_checked_paths() -> None:
    claims = []
    for path in sorted((_ROOT / "tests").rglob("*.py")):
        if path.relative_to(_ROOT).as_posix().startswith("tests/architecture/") or _checked(path):
            continue
        source = path.read_text(encoding="utf-8")
        if "mypy" not in source:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            docstring = ast.get_docstring(ast.parse(source)) or ""
        if "mypy" in docstring:
            claims.append(path.relative_to(_ROOT).as_posix())
    assert claims == []


_PORT_PROBE = """
from collections.abc import Mapping, Sequence

from financial_forecasting.features.evaluation.application.ports.out.silver_table_reader import (
    SilverTableReader,
)


class Conforming:
    def read(
        self, *, layer: str, table: str, filters: Mapping[str, object] | None = None
    ) -> Sequence[Mapping[str, object]]:
        return ()


class Drifted:
    def read(self, *, layer: str, table: str) -> Sequence[Mapping[str, object]]:
        return ()


def conforming() -> SilverTableReader:
    return Conforming()


def drifted() -> SilverTableReader:
    return Drifted()
"""


def test_project_mypy_rejects_a_fixture_that_drifts_from_the_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fim a fim: com a config do projeto, o port resolve e a fixture fora dele erra.

    Se `financial_forecasting` voltasse a `Any`, `drifted()` passaria em silêncio.
    """
    probe = tmp_path / "port_probe.py"
    probe.write_text(_PORT_PROBE, encoding="utf-8")
    monkeypatch.chdir(_ROOT)
    stdout, _, status = api.run(
        [
            "--config-file",
            str(_ROOT / "pyproject.toml"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--no-error-summary",
            str(probe),
        ]
    )
    errors = [line for line in stdout.splitlines() if ": error:" in line]
    assert status == 1
    assert len(errors) == 1
    drifted_line = _PORT_PROBE.splitlines().index("    return Drifted()") + 1
    assert f"port_probe.py:{drifted_line}:" in errors[0]
    assert "[return-value]" in errors[0]


def test_checked_predicate_matches_only_the_proof_roots() -> None:
    assert _checked(_ROOT / "tests/contract/features/inference/x.py")
    assert _checked(_ROOT / "tests/fakes/shared/x.py")
    assert not _checked(_ROOT / "tests/unit/features/inference/x.py")
    assert not _checked(_ROOT / "tests/contractual/x.py")
