"""Contrato do port `InferenceManifest` (Stage 7.1, Task 10; ADR 7.1.0004 item 4).

Pernas: `fake` (`InMemoryInferenceManifest`) e `real` (`JsonInferenceManifest` sob
`tmp_path`). As duas mesclam pela MESMA `apply_run_entry` do port; a suíte prova
o comportamento observável: sem manifesto → `None`; campos de primeira escrita
nunca sobrescritos; os de última verificação substituídos; cabeçalho
`cohort_environment` gravado uma vez. Só na perna real (o fake não tem estado
fora da instância): persistência entre instâncias, `os.replace` que falha deixa o
arquivo anterior e o caminho `<data_root>/inference/<cohort_id>/manifest.json`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from financial_forecasting.features.inference.adapters.out.filesystem.json_inference_manifest import (  # noqa: E501
    JsonInferenceManifest,
)
from financial_forecasting.features.inference.application.ports.out.inference_manifest import (
    FIRST_WRITE_FIELDS,
    InferenceManifest,
)
from tests.fakes.features.inference.in_memory_inference_manifest import (
    InMemoryInferenceManifest,
)

pytestmark = pytest.mark.contract

_COHORT = "aapl_confirmatory-r0-abcdef123456"
_Open = Callable[[], InferenceManifest]


def _first_entry() -> dict[str, object]:
    return {
        "cohort_environment": {"torch": "2.13.0+cpu", "torch_threads": "6"},
        "checkpoint_sha256": "a" * 64,
        "first_write_environment": {"torch": "2.13.0+cpu"},
        "first_write_settings": {"batch_size": "64"},
        "first_written_at": "2026-10-06T10:00:00+00:00",
        "status": "started",
        "environment": {"torch": "2.13.0+cpu"},
        "max_abs_diff": 0.0,
    }


def _second_entry() -> dict[str, object]:
    return {
        "cohort_environment": {"torch": "OTHER"},
        "checkpoint_sha256": "b" * 64,
        "first_write_environment": {"torch": "OTHER"},
        "first_write_settings": {"batch_size": "1"},
        "first_written_at": "2026-10-07T10:00:00+00:00",
        "status": "completed",
        "environment": {"torch": "2.14.0+cpu"},
        "max_abs_diff": 1e-9,
        "verified_at": "2026-10-07T10:05:00+00:00",
    }


@pytest.fixture(params=["fake", "real"])
def open_manifest(request: pytest.FixtureRequest, tmp_path: Path) -> _Open:
    if request.param == "fake":
        fake = InMemoryInferenceManifest()
        return lambda: fake
    return lambda: JsonInferenceManifest(data_root=tmp_path / "data")


def _runs(manifest: InferenceManifest) -> dict[str, dict[str, object]]:
    document = manifest.recorded(_COHORT)
    assert document is not None
    runs = document["runs"]
    assert isinstance(runs, dict)
    return runs


def test_recorded_is_none_without_a_manifest(open_manifest: _Open) -> None:
    assert open_manifest().recorded(_COHORT) is None


def test_first_write_fields_are_never_overwritten(open_manifest: _Open) -> None:
    open_manifest().record_run(_COHORT, "run-1", _first_entry())
    open_manifest().record_run(_COHORT, "run-1", _second_entry())

    entry = _runs(open_manifest())["run-1"]

    for name in FIRST_WRITE_FIELDS:
        assert entry[name] == _first_entry()[name], name


def test_last_verification_fields_are_replaced(open_manifest: _Open) -> None:
    open_manifest().record_run(_COHORT, "run-1", _first_entry())
    open_manifest().record_run(_COHORT, "run-1", _second_entry())

    entry = _runs(open_manifest())["run-1"]

    assert entry["status"] == "completed"
    assert entry["environment"] == {"torch": "2.14.0+cpu"}
    assert entry["max_abs_diff"] == _second_entry()["max_abs_diff"]
    assert entry["verified_at"] == "2026-10-07T10:05:00+00:00"
    assert "cohort_environment" not in entry


def test_cohort_environment_header_written_once(open_manifest: _Open) -> None:
    open_manifest().record_run(_COHORT, "run-1", _first_entry())
    open_manifest().record_run(_COHORT, "run-2", _second_entry())

    document = open_manifest().recorded(_COHORT)

    assert document is not None
    assert document["cohort_id"] == _COHORT
    assert document["cohort_environment"] == _first_entry()["cohort_environment"]
    assert set(_runs(open_manifest())) == {"run-1", "run-2"}


# -- só a perna real ----------------------------------------------------------------


def test_persists_across_instances(tmp_path: Path) -> None:
    JsonInferenceManifest(data_root=tmp_path).record_run(_COHORT, "run-1", _first_entry())

    entry = _runs(JsonInferenceManifest(data_root=tmp_path))["run-1"]

    assert entry["status"] == "started"


def test_failed_replace_keeps_the_previous_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = JsonInferenceManifest(data_root=tmp_path)
    manifest.record_run(_COHORT, "run-1", _first_entry())
    before = manifest.path(_COHORT).read_bytes()

    def _crash(src: object, dst: object) -> None:
        raise OSError("simulated crash before replace")

    monkeypatch.setattr(os, "replace", _crash)
    with pytest.raises(OSError, match="simulated crash"):
        manifest.record_run(_COHORT, "run-2", _second_entry())

    assert manifest.path(_COHORT).read_bytes() == before
    assert sorted(p.name for p in manifest.path(_COHORT).parent.iterdir()) == ["manifest.json"]


_MALFORMED_RUNS = [
    pytest.param({"runs": []}, id="runs-list"),
    pytest.param({"runs": "text"}, id="runs-string"),
    pytest.param({"runs": None}, id="runs-null"),
    pytest.param({"runs": {"run-1": []}}, id="entry-list"),
    pytest.param({"runs": {"run-1": "text"}}, id="entry-string"),
    pytest.param({"runs": {"run-1": None}}, id="entry-null"),
]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{not json",
        "[]",
        '"text"',
        "null",
        "3",
        *(pytest.param(json.dumps(p.values[0]), id=p.id) for p in _MALFORMED_RUNS),
    ],
)
def test_corrupted_manifest_raises_instead_of_reading_as_absent(
    tmp_path: Path, content: str
) -> None:
    """Vazio, JSON inválido, topo que não é objeto ou `runs`/entrada que não é objeto:
    nunca lido como manifesto vazio (a entrada do run sumiria e a C10 não conferiria)."""
    manifest = JsonInferenceManifest(data_root=tmp_path)
    manifest.path(_COHORT).parent.mkdir(parents=True)
    manifest.path(_COHORT).write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="unreadable"):
        manifest.recorded(_COHORT)


@pytest.mark.parametrize("document", _MALFORMED_RUNS)
@pytest.mark.parametrize("leg", ["fake", "real"])
def test_record_run_refuses_malformed_runs(
    tmp_path: Path, leg: str, document: dict[str, object]
) -> None:
    """A mescla do port nunca reescreve um `runs` adulterado como se estivesse vazio."""
    manifest: InferenceManifest
    if leg == "fake":
        manifest = InMemoryInferenceManifest({_COHORT: document})
        expected = "malformed"  # recusa da `apply_run_entry` do port
    else:
        real = JsonInferenceManifest(data_root=tmp_path)
        real.path(_COHORT).parent.mkdir(parents=True)
        real.path(_COHORT).write_text(json.dumps(document), encoding="utf-8")
        manifest = real
        expected = "unreadable"  # a releitura do arquivo recusa antes da mescla

    with pytest.raises(ValueError, match=expected):
        manifest.record_run(_COHORT, "run-1", _first_entry())


def test_file_lives_under_data_root_inference_cohort(tmp_path: Path) -> None:
    JsonInferenceManifest(data_root=tmp_path).record_run(_COHORT, "run-1", _first_entry())

    path = tmp_path / "inference" / _COHORT / "manifest.json"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert json.loads(text)["runs"]["run-1"]["checkpoint_sha256"] == "a" * 64
    assert text == json.dumps(json.loads(text), sort_keys=True, indent=2)
