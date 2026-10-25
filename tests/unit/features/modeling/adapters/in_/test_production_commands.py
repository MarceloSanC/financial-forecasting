"""Unit test dos comandos da rodada de produção (Stage 8.4, Task 05).

Prova: nomes de rodada válidos e inválidos (CA7); o spec da rodada é o modelo
congelado com a impressão digital do grid da rodada, mantido se igual e recusado se
adulterado (I4, CA3); o ponteiro tem exatamente as duas linhas absolutas, é
monotônico (I9) e a troca falha sem tocar o anterior nem deixar temporário (I3,
CA4); e o módulo não importa `features.evaluation` (I8, CA8).
"""

from __future__ import annotations

import ast
import importlib
import inspect
import io
import os
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepProvenance,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore
from tests.unit.features.modeling.adapters.in_ import test_cohort_commands as base

production: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.production_commands"
)
cohort_file: Any = base.cohort_file


def _model() -> CohortSpec:
    return base._draft(
        name="aapl_production",
        tft_params=TftTrainingParams(seed=0, hidden_size=24),
        gbm_params=GbmTrainingParams(seed=7, num_leaves=9),
        provenance=SweepProvenance(
            tft_study_id="tft-study",
            tft_best_trial=1,
            tft_best_objective=0.2,
            gbm_study_id="gbm-study",
            gbm_best_trial=0,
            gbm_best_objective=0.4,
            dataset_fingerprint="e" * 64,
        ),
    )


class _World:
    def __init__(self, tmp_path: Path, rows: list[dict[str, object]] | None = None) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.template = tmp_path / "aapl_production.toml"
        self.template.write_text(cohort_file.dump(_model()), encoding="utf-8")
        store = FakeMedallionStore()
        self.rows = rows if rows is not None else base._rows()
        store.seed_read_only(
            layer="processed", table="dataset_tft", asset=base._ASSET, rows=self.rows
        )
        self.deps = production.ProductionCommandDeps(
            store=store,
            hasher=base._HASHER,
            modeling_columns=modeling_columns(),
            load_spec=cohort_file.load,
            parse_spec=cohort_file.parse,
            dump_spec=cohort_file.dump,
        )
        self.production_root = tmp_path / "production"
        self.round_root = self.production_root / "rounds" / "2026-01-02"
        self.round_root.mkdir(parents=True)
        self.round_spec = self.round_root / "cohort.toml"
        self.out = io.StringIO()

    def prepare(self) -> CohortSpec:
        spec: CohortSpec = production.prepare_round_spec(
            self.deps, self.template, self.round_spec, out=self.out
        )
        return spec


# -- nome da rodada ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-10-25", (date(2026, 10, 25), 0)),
        ("2026-10-25.1", (date(2026, 10, 25), 1)),
        ("2026-10-25.12", (date(2026, 10, 25), 12)),
    ],
)
def test_round_names_parse_to_date_and_suffix(text: str, expected: tuple[date, int]) -> None:
    assert production.parse_round_name(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "..",
        ".",
        "x",
        "2026-13-01",
        "2026-02-30",
        "2026-10-25.0",
        "2026-10-25.01",
        "2026-1-1",
        "2026-10-25/..",
        " 2026-10-25",
        "2026-10-25.",
        "",
    ],
)
def test_invalid_round_names_are_refused(text: str) -> None:
    with pytest.raises(ValueError, match="round name"):
        production.parse_round_name(text)


def test_round_names_order_by_date_then_suffix() -> None:
    names = ["2026-10-25.2", "2026-10-26", "2026-10-25", "2026-10-25.10"]
    ordered = sorted(names, key=production.parse_round_name)
    assert ordered == ["2026-10-25", "2026-10-25.2", "2026-10-25.10", "2026-10-26"]


# -- spec da rodada ----------------------------------------------------------------------


def test_round_spec_is_the_model_frozen_with_the_grid_fingerprint(tmp_path: Path) -> None:
    world = _World(tmp_path)

    spec = world.prepare()

    assert spec == _model().production_round(base._fingerprint(world.rows))
    assert spec.is_frozen()
    assert cohort_file.load(world.round_spec) == spec
    assert "round spec written" in world.out.getvalue()
    assert [p.name for p in world.round_root.iterdir()] == ["cohort.toml"]


def test_round_spec_is_kept_when_equal(tmp_path: Path) -> None:
    world = _World(tmp_path)
    first = world.prepare()
    before = world.round_spec.read_bytes()

    again = world.prepare()

    assert again == first
    assert world.round_spec.read_bytes() == before
    assert "round spec kept" in world.out.getvalue()


def test_tampered_round_spec_is_refused_and_left_intact(tmp_path: Path) -> None:
    world = _World(tmp_path)
    spec = world.prepare()
    world.round_spec.write_text(cohort_file.dump(replace(spec, revision=3)), encoding="utf-8")
    tampered = world.round_spec.read_bytes()

    with pytest.raises(production.ProductionRoundError, match="derived, never edited"):
        world.prepare()

    assert world.round_spec.read_bytes() == tampered


def test_round_spec_changes_with_the_data(tmp_path: Path) -> None:
    first = _World(tmp_path / "a").prepare()
    second = _World(tmp_path / "b", rows=base._rows(shift=0.5)).prepare()

    assert first.dataset_fingerprint != second.dataset_fingerprint


def test_frozen_template_is_refused(tmp_path: Path) -> None:
    world = _World(tmp_path)
    world.template.write_text(
        cohort_file.dump(replace(_model(), dataset_fingerprint="a" * 64)), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="already declares a dataset_fingerprint"):
        world.prepare()
    assert not world.round_spec.exists()


# -- ponteiro --------------------------------------------------------------------------


def _publish(world: _World, name: str) -> bool:
    root = world.production_root / "rounds" / name
    root.mkdir(parents=True, exist_ok=True)
    published: bool = production.publish_serving_pointer(
        world.production_root, name, root, root / "cohort.toml", out=world.out
    )
    return published


def _pointer(world: _World) -> Path:
    return world.production_root / "serving.env"


def test_pointer_has_exactly_the_two_absolute_lines(tmp_path: Path) -> None:
    world = _World(tmp_path)

    assert _publish(world, "2026-01-02")

    lines = _pointer(world).read_text(encoding="utf-8").splitlines()
    round_root = (world.production_root / "rounds" / "2026-01-02").resolve().as_posix()
    assert lines == [f"DATA_ROOT={round_root}", f"SERVING_COHORT_FILE={round_root}/cohort.toml"]
    assert sorted(p.name for p in world.production_root.iterdir()) == ["rounds", "serving.env"]


def test_pointer_moves_forward_and_never_back(tmp_path: Path) -> None:
    world = _World(tmp_path)
    assert _publish(world, "2026-01-02")
    assert _publish(world, "2026-01-09")
    newer = _pointer(world).read_bytes()

    assert not _publish(world, "2026-01-02")
    assert _pointer(world).read_bytes() == newer
    assert "not published: round 2026-01-02 is older than the published 2026-01-09" in (
        world.out.getvalue()
    )

    assert _publish(world, "2026-01-09")  # a mesma rodada regrava o mesmo conteúdo
    assert _pointer(world).read_bytes() == newer
    assert _publish(world, "2026-01-09.1")
    assert "2026-01-09.1" in _pointer(world).read_text(encoding="utf-8")


def test_hand_edited_pointer_that_names_no_round_is_refused(tmp_path: Path) -> None:
    world = _World(tmp_path)
    world.production_root.mkdir(parents=True, exist_ok=True)
    _pointer(world).write_text("DATA_ROOT=/somewhere/else\n", encoding="utf-8")

    with pytest.raises(production.ProductionRoundError, match="not a round"):
        _publish(world, "2026-01-02")
    assert _pointer(world).read_text(encoding="utf-8") == "DATA_ROOT=/somewhere/else\n"


def test_failed_replace_keeps_the_previous_pointer_and_no_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _World(tmp_path)
    assert _publish(world, "2026-01-02")
    before = _pointer(world).read_bytes()

    def broken_replace(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError, match="disk full"):
        _publish(world, "2026-01-09")

    assert _pointer(world).read_bytes() == before
    assert sorted(p.name for p in world.production_root.iterdir()) == ["rounds", "serving.env"]


# -- fronteira ---------------------------------------------------------------------------


def test_module_does_not_import_evaluation() -> None:
    tree = ast.parse(inspect.getsource(production))
    imported = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert not [name for name in imported if "features.evaluation" in name]
