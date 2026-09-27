"""Ponta a ponta do runner do cohort confirmatório (Stage 5.5, Task 31 / A6).

Roda o CLI de verdade (`cli.main`) sobre um dado bruto sintético mínimo, com
treinos reais (baselines, GBM, TFT com poucas épocas) e o probe real do git num
repositório descartável: `materialize` → `sweep` → `freeze` → commit → `run`
→ `verify`; segunda execução pula tudo (ledger e checkpoints no disco); lock
órfão recusa e `--break-stale-lock` libera; unidade parcial no silver →
`PartialCohortUnitError` → `revision += 1` → `run` conclui. E os erros de §6 do
concept: TOML inválido, brutos ausentes e gate de qualidade rejeitando.

Só o sentimento é fake (injetado no composition root pelo `CliWiring`): o
FinBERT exige o extra `sentiment`, que o CI não instala.
"""

from __future__ import annotations

import io
import json
import subprocess
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from financial_forecasting import cli
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
)
from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepPlan,
)
from financial_forecasting.features.modeling.application.pipeline_version import PIPELINE_VERSION
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)
from tests.e2e.fixtures.cohort.raw_cohort_fixture import write_raw
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)

if TYPE_CHECKING:
    from financial_forecasting.features.market_data.domain.entities.news_article import (
        NewsArticle,
    )

pytestmark = pytest.mark.e2e

cohort_file: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.cohort_file")

_ASSET = "AAPL"
_FIRST_SESSION = date(2019, 1, 2)
# Aquecimento (252) + 3 gaps (3 x 8) + early_stop (20) + calib (20) + 2 x teste
# (40) + treino folgado para o encoder do TFT: 560 sessões → ~308 no grid útil.
_N_SESSIONS = 560
_COHORT_REL = Path("config") / "cohorts" / "e2e.toml"
_EXIT_ERROR = 2
_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")


def _score(article: NewsArticle) -> float:
    return (sum(map(ord, article.article_id or "")) % 200 - 100) / 100.0


def _draft() -> CohortSpec:
    return CohortSpec(
        name="e2e",
        revision=0,
        asset_id=_ASSET,
        feature_set_name="e2e",
        feature_set_hash=feature_set_hash(),
        pipeline_version=PIPELINE_VERSION,
        horizons=(1, 7),
        quantile_levels=(0.1, 0.5, 0.9),
        geometry=CohortGeometry(n_folds=2, test_size=20, val_size=20, calib_size=20, embargo=1),
        device="cpu",
        seeds=(11,),
        sweep=SweepPlan(
            tft_space=(SearchDimension(name="dropout", low=0.0, high=0.2, kind="float"),),
            tft_base_params=TftTrainingParams(
                seed=0,
                max_encoder_length=10,
                hidden_size=4,
                attention_head_size=1,
                hidden_continuous_size=2,
                max_epochs=1,
                patience=1,
                batch_size=32,
            ),
            gbm_space=(SearchDimension(name="num_leaves", low=4, high=16, kind="int"),),
            gbm_base_params=GbmTrainingParams(seed=7, num_boost_round_max=20),
            n_trials=1,
            sampler_seed=2026,
        ),
        tft_params=None,
        gbm_params=None,
        baseline_specs=BaselineSpec.canonical_five(historical_quantiles_window=20),
        provenance=None,
        dataset_fingerprint=None,
    )


class _World:
    """Repositório git descartável + raízes de dado e artefatos em `tmp_path`."""

    def __init__(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "repo"
        self.data = tmp_path / "data"
        self.artifacts = tmp_path / "artifacts"
        self.cohort = self.repo / _COHORT_REL
        self.wiring = cli.CliWiring(
            sentiment_model=InMemorySentimentModel(score_fn=_score),
            settings_overrides={
                "_env_file": None,
                "artifacts_root": self.artifacts,
                "repo_root": self.repo,
                "mlflow_tracking_uri": f"sqlite:///{tmp_path / 'mlruns.db'}",
            },
        )
        for rel, text in {"src/pkg/__init__.py": "x = 1\n", "uv.lock": "lock\n"}.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.write_spec(_draft())
        self.git("init", "-q")
        self.commit("init")

    def git(self, *args: str) -> None:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )

    def commit(self, message: str) -> None:
        self.git("add", ".")
        self.git("commit", "-q", "-m", message)

    def write_spec(self, spec: CohortSpec) -> None:
        self.cohort.parent.mkdir(parents=True, exist_ok=True)
        self.cohort.write_text(cohort_file.dump(spec), encoding="utf-8")

    def spec(self) -> CohortSpec:
        spec: CohortSpec = cohort_file.load(self.cohort)
        return spec

    def cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        command, *rest = args
        argv = [command, "--data-root", str(self.data), "--cohort", str(self.cohort), *rest]
        code = cli.main(argv, wiring=self.wiring, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def ok(self, *args: str) -> str:
        code, out, err = self.cli(*args)
        assert code == 0, f"{args}: exit {code}\n{out}\n{err}"
        return out


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _World:
    # O `make check` roda com GIT_DIR/GIT_WORK_TREE da worktree; o repo aqui é outro.
    for variable in _GIT_ENV:
        monkeypatch.delenv(variable, raising=False)
    return _World(tmp_path)


def _unit_statuses(run_output: str) -> dict[str, str]:
    statuses = {}
    for line in run_output.splitlines()[1:]:
        unit, rest = line.strip().split(": ", 1)
        statuses[unit] = rest.split(" ", 1)[0]
    return statuses


def _halve_one_run(data_root: Path, run_id: str) -> None:
    """Apaga metade dos fatos de um run no silver (queda no meio da gravação)."""
    touched = 0
    for path in sorted((data_root / "silver" / "fact_oos_predictions").rglob("*.parquet")):
        table = pq.ParquetFile(path).read()  # só o arquivo: sem inferir partições do caminho
        idx = np.flatnonzero(np.asarray(table.column("run_id").to_pylist()) == run_id)
        if idx.size == 0:
            continue
        keep = np.ones(table.num_rows, dtype=bool)
        keep[idx[: idx.size // 2]] = False
        pq.write_table(table.filter(pa.array(keep)), path)
        touched += 1
    assert touched, f"run {run_id} not found in the silver facts"


def _forget_unit(artifacts_root: Path, cohort_id: str, unit: str) -> dict[str, int]:
    progress = artifacts_root / "cohorts" / cohort_id / "progress.json"
    state = json.loads(progress.read_text(encoding="utf-8"))
    removed: dict[str, int] = state["units"].pop(unit)
    progress.write_text(json.dumps(state), encoding="utf-8")
    return removed


def test_cohort_runner_end_to_end(world: _World) -> None:
    write_raw(world.data, asset=_ASSET, first=_FIRST_SESSION, n_sessions=_N_SESSIONS)

    # materialize → sweep → freeze → commit → run → verify
    assert "dataset rows" in world.ok("materialize")
    world.ok("sweep", "--n-trials", "1")
    frozen_out = world.ok("freeze")
    assert world.spec().is_frozen()
    cohort_id = frozen_out.split()[1]
    world.commit("freeze")
    first = _unit_statuses(world.ok("run"))
    assert set(first.values()) == {"ran"}
    assert list(first) == ["baselines", "gbm", "tft:seed=11"]
    assert world.ok("verify").rstrip().endswith("OK")

    # segunda execução, ledger e checkpoints no disco: pula tudo
    assert set(_unit_statuses(world.ok("run")).values()) == {"skipped_completed"}

    # lock órfão: recusa; --break-stale-lock libera
    (world.data / ".writer.lock").write_text(
        json.dumps({"pid": 999999, "host": "dead", "started_at": "t", "token": "orphan"}),
        encoding="utf-8",
    )
    code, _, err = world.cli("run")
    assert code == _EXIT_ERROR
    assert "CohortRunLockedError" in err
    world.ok("run", "--break-stale-lock")
    assert not (world.data / ".writer.lock").exists()

    # unidade parcial fora do ledger → erro; remediação por nova revisão
    gbm_runs = _forget_unit(world.artifacts, cohort_id, "gbm")
    _halve_one_run(world.data, sorted(gbm_runs)[0])
    code, _, err = world.cli("run")
    assert code == _EXIT_ERROR
    assert "PartialCohortUnitError" in err
    world.write_spec(replace(world.spec(), revision=1))
    world.commit("revision 1")
    assert set(_unit_statuses(world.ok("run")).values()) == {"ran"}
    assert world.ok("verify").rstrip().endswith("OK")


def test_invalid_cohort_file_is_an_error_naming_the_field(world: _World) -> None:
    world.cohort.write_text(
        world.cohort.read_text(encoding="utf-8").replace("revision = 0", "revision = -1"),
        encoding="utf-8",
    )

    code, _, err = world.cli("verify")

    assert code == _EXIT_ERROR
    assert "CohortFileError" in err
    assert "revision" in err


def test_missing_raw_data_is_an_error_naming_the_file(world: _World) -> None:
    code, _, err = world.cli("materialize")

    assert code == _EXIT_ERROR
    assert "Raw candle source not found" in err
    assert not (world.data / ".writer.lock").exists()


def test_quality_gate_rejection_is_an_error(world: _World) -> None:
    write_raw(
        world.data,
        asset=_ASSET,
        first=_FIRST_SESSION,
        n_sessions=_N_SESSIONS,
        fundamentals_lead_days=-200,
    )

    code, _, err = world.cli("materialize")

    assert code == _EXIT_ERROR
    assert "DatasetQualityError" in err
