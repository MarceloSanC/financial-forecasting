"""Unit test do subcomando `production-round` (Stage 8.4, Task 06).

Composition root real em `tmp_path` (o lock é o `JsonCohortProgressLedger` de verdade);
materialização, spec da rodada, corrida e `verify` trocados por espiões. Prova: ordem
das etapas; `Settings` da rodada com `data_root`, `artifacts_root` e
`mlflow_tracking_uri` dentro dela mesmo com overrides; validações antes de qualquer
escrita (nome, bruto ausente, raiz sobre `data/cohorts`, também com outra caixa ou
contendo-a); lock da raiz ocupado; materialização pulada com a marca (com aviso de
bruto divergente) e refeita do zero sem ela; `verify` divergente não publica; lock
liberado em erro.
"""

from __future__ import annotations

import dataclasses
import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from financial_forecasting import cli
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    RunConfirmatoryCohortCommand,
    RunConfirmatoryCohortResult,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.unit.features.modeling.adapters.in_.test_cohort_file import _frozen, cohort_file

production: Any = cli.importlib.import_module(cli._PRODUCTION_COMMANDS)

_ROUND = "2026-01-02"
_EXIT_ERROR = 2
_EXIT_MISMATCH = 1
_ASSET = "AAPL"


class _World:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.repo = tmp_path / "repo"
        self.repo.mkdir()
        self.production_root = tmp_path / "production"
        self.round_root = self.production_root / "rounds" / _ROUND
        self.raw = tmp_path / "raw"
        for rel in cli._RAW_INPUTS:
            path = self.raw / rel.format(a=_ASSET)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(rel.encode())
        self.template = tmp_path / "aapl_production.toml"
        self.template.write_text(cohort_file.dump(_frozen()), encoding="utf-8")
        self.steps: list[str] = []
        self.settings: list[Settings] = []
        self.verify_code = 0
        self.overrides = {
            "_env_file": None,
            "repo_root": self.repo,
            "artifacts_root": tmp_path / "elsewhere-artifacts",
            "data_root": tmp_path / "elsewhere-data",
            "mlflow_tracking_uri": "sqlite:///elsewhere.db",
        }
        real_wire = cli.wire_dependencies

        def wire(settings: Settings, **kwargs: Any) -> Any:  # noqa: ANN401
            self.settings.append(settings)
            deps = real_wire(settings, **kwargs)
            return dataclasses.replace(deps, production_cohort_for=self._cohort_for)

        def materialize(deps: Any, **kwargs: Any) -> int:  # noqa: ANN401
            self.steps.append("materialize")
            (self.round_root / "bronze").mkdir(parents=True, exist_ok=True)
            (self.round_root / "bronze" / "x").write_text("x", encoding="utf-8")
            return 0

        def prepare(deps: Any, template: Path, path: Path, *, out: Any) -> Any:  # noqa: ANN401
            self.steps.append("spec")
            spec = _frozen()
            path.write_text(cohort_file.dump(spec), encoding="utf-8")
            return spec

        def verify(command_deps: Any, path: Path, *, out: Any) -> int:  # noqa: ANN401
            self.steps.append("verify")
            return self.verify_code

        monkeypatch.setattr(cli, "wire_dependencies", wire)
        monkeypatch.setattr(cli, "_materialize", materialize)
        monkeypatch.setattr(production, "prepare_round_spec", prepare)
        monkeypatch.setattr(
            cli, "_cohort_command_deps", lambda deps, cf: (SimpleNamespace(verify=verify), None)
        )

    def _cohort_for(self, template: Path, device: str) -> Any:  # noqa: ANN401
        def use_case(command: RunConfirmatoryCohortCommand) -> RunConfirmatoryCohortResult:
            self.steps.append("run")
            assert template == self.template
            return RunConfirmatoryCohortResult(cohort_id="prod-c", cohort_hash="h", outcomes=())

        return use_case

    def cli(
        self, *extra: str, root: Path | None = None, round_name: str = _ROUND
    ) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = [
            "production-round",
            "--production-root",
            str(root or self.production_root),
            "--round",
            round_name,
            "--raw-root",
            str(self.raw),
            "--cohort",
            str(self.template),
            *extra,
        ]
        wiring = cli.CliWiring(
            sentiment_model=InMemorySentimentModel(),
            runtime_probe_factory=lambda path, device: InMemoryRuntimeEnvironmentProbe(),
            settings_overrides=self.overrides,
        )
        code = cli.main(argv, wiring=wiring, out=out, err=err)
        return code, out.getvalue(), err.getvalue()


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _World:
    return _World(tmp_path, monkeypatch)


def test_round_runs_the_steps_in_order_and_publishes(world: _World) -> None:
    code, out, err = world.cli()

    assert code == 0, err
    assert world.steps == ["materialize", "spec", "run", "verify"]
    assert out.rstrip().endswith(
        f"published prod-c → {world.production_root.resolve() / 'serving.env'}"
    )
    assert (world.round_root / ".materialized").exists()
    for rel in cli._RAW_INPUTS:
        assert (world.round_root / rel.format(a=_ASSET)).read_bytes() == rel.encode()
    assert not (world.production_root / ".writer.lock").exists()


def test_round_settings_point_inside_the_round_even_with_overrides(world: _World) -> None:
    assert world.cli()[0] == 0

    (settings,) = world.settings
    round_root = world.round_root.resolve()
    assert Path(settings.data_root) == round_root
    assert Path(settings.artifacts_root) == round_root / "artifacts"
    assert settings.mlflow_tracking_uri == f"sqlite:///{(round_root / 'mlruns.db').as_posix()}"


@pytest.mark.parametrize("name", ["..", ".", "x", "2026-13-01", "2026-01-02.0"])
def test_invalid_round_name_writes_nothing(world: _World, name: str) -> None:
    code, _, err = world.cli(round_name=name)

    assert code == _EXIT_ERROR
    assert "round name" in err
    assert not world.production_root.exists()
    assert world.steps == []


def test_missing_raw_input_writes_nothing(world: _World) -> None:
    (world.raw / cli._RAW_INPUTS[1].format(a=_ASSET)).unlink()

    code, _, err = world.cli()

    assert code == _EXIT_ERROR
    assert "raw input not found" in err
    assert "news_AAPL.parquet" in err
    assert not world.production_root.exists()


@pytest.mark.parametrize(
    "relative", ["data/cohorts", "data/cohorts/prod", "Data/Cohorts/prod", "data", "."]
)
def test_production_root_overlapping_the_cohorts_is_refused(world: _World, relative: str) -> None:
    root = world.repo / relative
    before = sorted(p.as_posix() for p in world.repo.rglob("*"))

    code, _, err = world.cli(root=root)

    assert code == _EXIT_ERROR
    assert "ProductionRoundError" in err
    assert "overlaps" in err
    assert sorted(p.as_posix() for p in world.repo.rglob("*")) == before
    assert world.steps == []


def test_held_production_lock_refuses_without_touching_the_round(world: _World) -> None:
    world.round_root.mkdir(parents=True)
    (world.round_root / "bronze").mkdir()
    (world.production_root / ".writer.lock").write_text(
        json.dumps({"pid": 424242, "host": "elsewhere", "started_at": "t", "token": "o"}),
        encoding="utf-8",
    )

    code, _, err = world.cli()

    assert code == _EXIT_ERROR
    assert "CohortRunLockedError" in err
    assert (world.round_root / "bronze").exists()
    assert world.steps == []


def test_marked_round_skips_materialization_and_warns_on_changed_inputs(world: _World) -> None:
    assert world.cli()[0] == 0
    world.steps.clear()
    (world.raw / cli._RAW_INPUTS[0].format(a=_ASSET)).write_bytes(b"newer candles")

    code, out, _ = world.cli()

    assert code == 0
    assert world.steps == ["spec", "run", "verify"]
    assert "warning: --raw-root differs" in out
    assert "candles_AAPL_1d.parquet" in out
    copied = world.round_root / cli._RAW_INPUTS[0].format(a=_ASSET)
    assert copied.read_bytes() == cli._RAW_INPUTS[0].encode()


def test_unmarked_round_is_redone_from_scratch(world: _World) -> None:
    stale = world.round_root / "bronze" / "stale.parquet"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    leftover = world.round_root / "processed" / "dataset_tft" / "old.parquet"
    leftover.parent.mkdir(parents=True)
    leftover.write_text("old", encoding="utf-8")

    code, _, err = world.cli()

    assert code == 0, err
    assert not stale.exists()
    assert not leftover.exists()
    assert world.steps[0] == "materialize"


def test_diverging_verify_does_not_publish(world: _World) -> None:
    world.verify_code = _EXIT_MISMATCH

    code, out, _ = world.cli()

    assert code == _EXIT_MISMATCH
    assert "published" not in out
    assert not (world.production_root / "serving.env").exists()
    assert not (world.production_root / ".writer.lock").exists()


def test_failure_releases_the_production_lock(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(deps: Any, template: Path, path: Path, *, out: Any) -> Any:  # noqa: ANN401
        raise production.ProductionRoundError("boom")

    monkeypatch.setattr(production, "prepare_round_spec", broken)

    code, _, err = world.cli()

    assert code == _EXIT_ERROR
    assert "boom" in err
    assert not (world.production_root / ".writer.lock").exists()
