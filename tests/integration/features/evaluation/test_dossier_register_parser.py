"""Parser do registro curado `dossier_register.toml` (Stage 8.3, Task 13; A13, A17).

Lê arquivos em `tmp_path` (integração: abre arquivo). O parser mora sob `adapters/in/`
(keyword `in`): `importlib`.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    DossierEntryKind,
)

_PARSER: Any = importlib.import_module(
    "financial_forecasting.features.evaluation.adapters.in.cli.dossier_register"
)


def _entry(**fields: str) -> str:
    values = {
        "kind": "deviation",
        "title": "Errata O1",
        "summary": "a corrida rodou em 060537fc",
        "pointer": "docs/stages/8.1-confirmatory-run/technical.md#o1",
        **fields,
    }
    return "[[entry]]\n" + "".join(f'{k} = "{v}"\n' for k, v in values.items()) + "\n"


def _load(tmp_path: Path, text: str) -> tuple[Any, ...]:
    path = tmp_path / "dossier_register.toml"
    path.write_text(text, encoding="utf-8")
    result: tuple[Any, ...] = _PARSER.load_register(path)
    return result


@pytest.mark.integration
def test_valid_register_parses_in_file_order(tmp_path: Path) -> None:
    text = (
        "# comentário de cabeçalho\n"
        + _entry(title="primeira")
        + _entry(
            kind="finding",
            title="achado",
            status="open",
            pointer="docs/stages/7.2-x/technical.md#f",
        )
        + _entry(kind="internal", title="interno", pointer="docs/reports/equivalence_audit.md")
    )
    entries = _load(tmp_path, text)
    assert [e.title for e in entries] == ["primeira", "achado", "interno"]
    assert [e.kind for e in entries] == [
        DossierEntryKind.DEVIATION,
        DossierEntryKind.FINDING,
        DossierEntryKind.INTERNAL,
    ]
    assert entries[1].status == "open"
    assert _load(tmp_path, "") == ()


@pytest.mark.integration
def test_unknown_kind_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="kind 'opinion'"):
        _load(tmp_path, _entry(kind="opinion"))


@pytest.mark.integration
def test_missing_field_raises(tmp_path: Path) -> None:
    text = '[[entry]]\nkind = "deviation"\ntitle = "t"\nsummary = "s"\n'
    with pytest.raises(ValueError, match=r"missing \['pointer'\]"):
        _load(tmp_path, text)


@pytest.mark.integration
def test_extra_field_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"unknown \['author'\]"):
        _load(tmp_path, _entry(author="x"))
    with pytest.raises(ValueError, match="top-level"):
        _load(tmp_path, 'version = "1"\n' + _entry())


@pytest.mark.integration
def test_finding_without_open_status_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="needs status"):
        _load(tmp_path, _entry(kind="finding"))
    with pytest.raises(ValueError, match="needs status"):
        _load(tmp_path, _entry(kind="finding", status="resolved"))


@pytest.mark.integration
def test_non_internal_forbidden_pointer_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="A17"):
        _load(tmp_path, _entry(pointer="docs/reports/prior_evidence_registry.toml"))
    with pytest.raises(ValueError, match="repo-relative"):
        _load(tmp_path, _entry(pointer="./docs/stages/8.2-equivalence-audit/concept.md"))


@pytest.mark.integration
def test_invalid_toml_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not valid TOML"):
        _load(tmp_path, '[[entry]\nkind = "deviation"\n')
    with pytest.raises(ValueError, match="must be a string"):
        _load(tmp_path, '[[entry]]\nkind = "deviation"\ntitle = 1\nsummary = "s"\npointer = "p"\n')
