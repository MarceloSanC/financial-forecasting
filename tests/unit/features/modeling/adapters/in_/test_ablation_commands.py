"""Comandos do cohort de ablação (Stage 7.3, Task 10; CA3, C1, C3; ADR 7.3.0004 item 2).

Deps fakes: o executor é o `RunAblationCohort` do harness de
`test_run_ablation_cohort.py` (fakes da 5.5), e o arquivo do spec vive em `tmp_path`.
O módulo vive sob `adapters/in/` (keyword `in`): carregado por `importlib` (LAYOUT §8).
"""

from __future__ import annotations

import importlib
import io
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.application.use_cases.cohort_unit_runner import (
    CohortNotFrozenError,
)
from financial_forecasting.features.modeling.application.use_cases.measure_ablation_cost import (
    AblationCostReport,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.unit.features.modeling.application.test_run_ablation_cohort import (
    _TORCH,
    _ablation,
    _base,
    _cohort_id,
    _Harness,
)

commands: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.ablation_commands"
)
ablation_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.ablation_cohort_file"
)

pytestmark = pytest.mark.unit

_UNITS = 5 * 2  # 5 configurações x 2 seeds
_SEED_COUNTS = 10


def _report() -> AblationCostReport:
    return AblationCostReport(
        configuration="full",
        seed=1,
        fold_index=5,
        wall_seconds=360.0,
        epochs_run=12,
        best_epoch=8,
        seconds_per_epoch=30.0,
        max_epochs=50,
        device="rocm",
        torch_build=_TORCH,
        ceiling_seconds={s: 5 * 6 * s * 50 * 30.0 for s in range(1, 11)},
        estimate_seconds={s: 5 * 6 * s * 360.0 for s in range(1, 11)},
    )


def _deps(path: Path, harness: _Harness | None = None, *, torch: str = _TORCH) -> Any:  # noqa: ANN401
    harness = harness or _Harness()

    def probe_for(file: Path, device: str) -> InMemoryRuntimeEnvironmentProbe:
        return InMemoryRuntimeEnvironmentProbe.with_gpu(device=device, torch=torch)

    def load_spec(file: Path) -> Any:  # noqa: ANN401
        return ablation_file.parse_ablation_cohort(file.read_text(encoding="utf-8")), _base()

    return commands.AblationCommandDeps(
        hasher=harness.use_case._hasher,
        ledger=harness.ledger,
        run_index=harness.index,
        load_spec=load_spec,
        dump_spec=ablation_file.dump_ablation_cohort,
        ablation_cohort_for=lambda file: harness.use_case,
        measure_ablation_cost_for=lambda file: lambda command: _report(),
        runtime_probe_for=probe_for,
        supported_devices=frozenset({"cpu", "rocm"}),
    )


def _file(tmp_path: Path, spec: Any) -> Path:  # noqa: ANN401
    path = tmp_path / "ablation.toml"
    path.write_text(ablation_file.dump_ablation_cohort(spec), encoding="utf-8")
    return path


def test_pilot_prints_the_report_with_ceiling_and_estimate(tmp_path: Path) -> None:
    path = _file(tmp_path, _ablation(seeds=(), torch_build=None))
    out = io.StringIO()

    assert commands.pilot(_deps(path), path, out=out) == 0

    lines = out.getvalue().splitlines()
    assert lines[0].startswith("pilot full seed 1 fold 5: wall 360.0s, epochs 12")
    assert "estimate" in lines[1]
    assert "ceiling" in lines[1]
    s_lines = [line for line in lines if line.startswith("S=")]
    assert len(s_lines) == _SEED_COUNTS
    assert s_lines[0] == "S=1: ceiling 12.5 h, estimate 3.0 h"
    assert s_lines[-1] == "S=10: ceiling 125.0 h, estimate 30.0 h"


def test_run_refuses_unfrozen_spec(tmp_path: Path) -> None:
    path = _file(tmp_path, _ablation(seeds=(), torch_build=None))
    harness = _Harness()

    with pytest.raises(CohortNotFrozenError):
        commands.run(_deps(path, harness), path, out=io.StringIO())
    assert harness.commands == []


def test_run_prints_one_line_per_unit(tmp_path: Path) -> None:
    path = _file(tmp_path, _ablation())
    out = io.StringIO()

    assert commands.run(_deps(path), path, out=out) == 0

    lines = out.getvalue().splitlines()
    assert sum(line.startswith("unit tft:") for line in lines) == _UNITS
    assert lines[-1].startswith(f"ablation {_cohort_id(_ablation())}: cohort_hash ")


def test_verify_counts_runs_and_rows(tmp_path: Path) -> None:
    path = _file(tmp_path, _ablation())
    harness = _Harness()
    harness.run()
    out = io.StringIO()

    assert commands.verify(_deps(path, harness), path, out=out) == 0

    head, tail = out.getvalue().splitlines()
    base = _base()
    per_run = sum(
        base.geometry.expected_prediction_rows(
            fold_index=f, horizons=base.horizons, n_levels=len(base.quantile_levels)
        )
        for f in range(base.geometry.n_folds)
    )
    rows = per_run * 5 * 2
    assert head == (
        f"ablation {_cohort_id(_ablation())}: 5 configurations x 2 folds x 2 seeds = 20 runs; "
        f"rows expected {rows}, observed {rows}"
    )
    assert tail == "OK"


def test_verify_reports_a_missing_unit(tmp_path: Path) -> None:
    path = _file(tmp_path, _ablation())
    out = io.StringIO()

    assert commands.verify(_deps(path), path, out=out) == commands.EXIT_MISMATCH
    assert "MISMATCH ledger: unit 'tft:full:seed=1' is not marked completed" in out.getvalue()


def test_freeze_writes_seeds_and_the_observed_torch_build_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _file(tmp_path, _ablation(seeds=(), torch_build=None))
    replaced: list[tuple[Path, Path]] = []
    original = os.replace

    def spy(src: Any, dst: Any) -> None:  # noqa: ANN401
        replaced.append((Path(src), Path(dst)))
        original(src, dst)

    monkeypatch.setattr(commands.os, "replace", spy)
    out = io.StringIO()

    assert commands.freeze(_deps(path, torch="2.13.0+rocm6.4"), path, out=out, seeds=(1, 2, 3)) == 0

    frozen = ablation_file.parse_ablation_cohort(path.read_text(encoding="utf-8"))
    assert frozen.seeds == (1, 2, 3)
    assert frozen.torch_build == "2.13.0+rocm6.4"
    assert frozen == _ablation(seeds=(1, 2, 3), torch_build="2.13.0+rocm6.4")
    assert len(replaced) == 1
    assert replaced[0][1] == path
    assert replaced[0][0].parent == path.parent
    assert not replaced[0][0].exists()
    assert re.fullmatch(
        rf"frozen {re.escape(_cohort_id(frozen))}: cohort_hash [0-9a-f]{{64}}; seeds 3; "
        r"torch_build 2\.13\.0\+rocm6\.4",
        out.getvalue().strip(),
    )


def test_freeze_refuses_when_already_frozen(tmp_path: Path) -> None:
    path = _file(tmp_path, _ablation())
    before = path.read_text(encoding="utf-8")

    with pytest.raises(commands.AblationCommandError, match="already frozen"):
        commands.freeze(_deps(path), path, out=io.StringIO(), seeds=(4,))
    assert path.read_text(encoding="utf-8") == before


def test_freeze_refuses_a_device_outside_the_supported_ones(tmp_path: Path) -> None:
    """C3-6: device fora do mapa recusado antes do probe e da escrita."""
    path = _file(tmp_path, _ablation(seeds=(), torch_build=None, device="cuda"))
    before = path.read_text(encoding="utf-8")

    def never(file: Path, device: str) -> Any:  # noqa: ANN401
        raise AssertionError("the probe must not be opened")

    deps = replace(_deps(path), runtime_probe_for=never)
    with pytest.raises(commands.AblationCommandError, match="not supported"):
        commands.freeze(deps, path, out=io.StringIO(), seeds=(1, 2))
    assert path.read_text(encoding="utf-8") == before
    assert list(path.parent.iterdir()) == [path]
