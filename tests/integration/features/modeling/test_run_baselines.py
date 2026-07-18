"""Integração ponta-a-ponta do `RunBaselines` — adapters REAIS em `tmp_path`.

Task 09 da Stage 5.2 (A5/A2/C6/C8 do technical §1): semeia um dataset TFT
sintético no layout físico da 3.5 (`processed/dataset_tft/<asset>/*.parquet`,
grade densa de sessões XNYS reais com `timestamp` tz-aware + `target_return`)
e roda o use case saído do `wire_dependencies` — ou seja, o grafo REAL:
`ParquetMedallionStore` (par read-only D3), `WalkForwardSplitter` sobre o
`TradingCalendar` da janela ampla fixa (F-T1 opção A),
`StatsforecastBaselineForecaster`, `PersistPredictions` +
`ParquetAnalyticsRepository` (silver) e `CanonicalJsonHasher`.

Prova (concept 5.2 §11; specs com `historical_quantiles_window` reduzido —
override de teste sancionado pelo ADR 5.2.0003):

- A5/I2: `fact_oos_predictions` com linhas LONG para as 5
  `model_version='baseline_*'`, `split="test"`, grade completa por decisão x
  horizonte e `target_timestamp_utc == dataset_timestamps[decision_idx + h]`
  (alinhamento resolvido SÓ pelo persister 4.3);
- I10: `dim_run` com 1 linha por (spec x fold), `run_id` referenciado pelas
  predições, `seed=None`, `parent_sweep_id` do cohort;
- A2/I5: grade degenerada (`zero_return`/`historical_mean`) persiste com
  `value_guardrail` IDÊNTICO em todas as linhas de `quantile_level` de uma
  mesma decisão x horizonte e `guardrail_applied == 0` (schema LONG — sem
  colunas q_low/q_high);
- C6: decisões da cauda sem janela completa → `rows_skipped > 0` e NENHUMA
  linha fabricada;
- C8: reexecução da mesma invocação → `DuplicateKeyError` propaga.

O pipeline roda UMA vez (fixture module-scoped) — as asserções leem o MESMO
estado persistido; o caso C8 reexecuta por cima sem alterar contagens (o
`dim_run` é upsert; o fact colide ANTES de gravar linha nova).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from financial_forecasting.composition_root import wire_dependencies
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    RunBaselinesCommand,
    RunBaselinesResult,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)
from financial_forecasting.shared.adapters.out.calendar.exchange_calendars_provider import (
    ExchangeCalendarsProvider,
)
from financial_forecasting.shared.domain.exceptions.base import DuplicateKeyError
from financial_forecasting.shared.infrastructure.config.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from financial_forecasting.composition_root import ApplicationDependencies
    from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
        Row,
    )

# Geometria pequena (mesma dos units da Task 06), sobre sessões XNYS REAIS:
# 120 sessões, 2 folds de test na cauda (blocos 114-116 e 117-119), gap =
# max_horizon + embargo = 3. Decisões 118/119 estouram a grade p/ h=2/h={1,2}
# → C6 observável no último fold.
_ASSET = "TEST"
_FEATURE_SET = "fs_e2e"
_COHORT_ID = "cohort-e2e-52"
_N_SESSIONS = 120
_LEVELS = (0.1, 0.5, 0.9)
_HORIZONS = (1, 2)
_MAX_HORIZON = 2
_HQ_WINDOW = 20  # override de teste do W=252 (ADR 5.2.0003)
_N_FOLDS = 2
_TEST_SIZE = 3
_VAL_SIZE = 5
_CALIB_SIZE = 5
_EMBARGO = 1
_SCHEMA_VERSION = 1
_N_SPECS = 5
_DEGENERATE_VERSIONS = frozenset({"baseline_zero_return", "baseline_historical_mean"})

_SILVER = "silver"
_FACTS = "fact_oos_predictions"
_DIM_RUN = "dim_run"


def _xnys_sessions() -> tuple[date, ...]:
    """120 sessões XNYS REAIS a partir de 2021-01-04 (grade densa da 3.5)."""
    window = ExchangeCalendarsProvider().sessions(
        start=date(2021, 1, 4), end=date(2021, 7, 30)
    )
    assert len(window.sessions) >= _N_SESSIONS
    return window.sessions[:_N_SESSIONS]


def _returns(n: int) -> tuple[float, ...]:
    """Série determinística com variação suficiente para o fit do AR(1)."""
    rng = random.Random(11)
    return tuple(0.001 + rng.gauss(0.0, 0.01) for _ in range(n))


def _seed_dataset(data_root: Path, sessions: Sequence[date]) -> None:
    """Materializa o parquet no layout físico da 3.5 (diretório-por-asset)."""
    frame = pd.DataFrame(
        {
            "timestamp": [
                datetime(day.year, day.month, day.day, tzinfo=UTC) for day in sessions
            ],
            "asset_id": [_ASSET] * len(sessions),
            "target_return": list(_returns(len(sessions))),
        }
    )
    target_dir = data_root / "processed" / "dataset_tft" / _ASSET
    target_dir.mkdir(parents=True)
    frame.to_parquet(target_dir / f"dataset_tft_{_ASSET}.parquet", index=False)


def _command() -> RunBaselinesCommand:
    return RunBaselinesCommand(
        scope=ScopeSpec(
            asset_id=_ASSET,
            feature_set_name=_FEATURE_SET,
            max_horizon=_MAX_HORIZON,
            cohort_id=_COHORT_ID,
        ),
        specs=BaselineSpec.canonical_five(historical_quantiles_window=_HQ_WINDOW),
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
        n_folds=_N_FOLDS,
        test_size=_TEST_SIZE,
        val_size=_VAL_SIZE,
        calib_size=_CALIB_SIZE,
        embargo=_EMBARGO,
        schema_version=_SCHEMA_VERSION,
    )


@dataclass(frozen=True)
class _PipelineRun:
    """Estado compartilhado da execução única do pipeline (fixture module-scoped)."""

    deps: ApplicationDependencies
    result: RunBaselinesResult
    iso_timestamps: tuple[str, ...]

    def facts(self) -> Sequence[Row]:
        return self.deps.analytics_repository.read(layer=_SILVER, table=_FACTS)

    def dim_run(self) -> Sequence[Row]:
        return self.deps.analytics_repository.read(layer=_SILVER, table=_DIM_RUN)


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> _PipelineRun:
    """Semeia o dataset, wireia o grafo real e roda o `RunBaselines` UMA vez."""
    data_root = tmp_path_factory.mktemp("e2e-run-baselines")
    sessions = _xnys_sessions()
    _seed_dataset(data_root, sessions)

    deps = wire_dependencies(
        settings=Settings(
            _env_file=None,
            data_root=data_root,
            mlflow_tracking_uri=f"sqlite:///{data_root}/mlruns.db",
        )
    )
    result = deps.run_baselines(_command())
    iso = tuple(
        datetime(day.year, day.month, day.day, tzinfo=UTC).isoformat() for day in sessions
    )
    return _PipelineRun(deps=deps, result=result, iso_timestamps=iso)


# -- A5/I2: predições LONG alinhadas, grade completa ------------------------------


@pytest.mark.integration
def test_e2e_facts_have_all_five_specs_split_test(pipeline: _PipelineRun) -> None:
    """As 5 `model_version='baseline_*'` persistem em `split="test"` (A5/I7)."""
    rows = pipeline.facts()

    assert rows, "expected persisted prediction rows"
    assert all(str(r["split"]) == "test" for r in rows)
    assert {str(r["model_version"]) for r in rows} == {
        f"baseline_{spec.family}" for spec in _command().specs
    }


@pytest.mark.integration
def test_e2e_grid_complete_per_decision_horizon(pipeline: _PipelineRun) -> None:
    """Cada (run, decisão, horizonte) persistido tem TODOS os níveis da grade."""
    grids: dict[tuple[str, int, int], set[float]] = {}
    for row in pipeline.facts():
        key = (str(row["run_id"]), int(str(row["decision_idx"])), int(str(row["horizon"])))
        grids.setdefault(key, set()).add(float(str(row["quantile_level"])))

    assert grids
    assert all(levels == set(_LEVELS) for levels in grids.values())


@pytest.mark.integration
def test_e2e_alignment_i2_target_timestamp_by_session_index(
    pipeline: _PipelineRun,
) -> None:
    """I2: `target_timestamp_utc == dataset_timestamps[decision_idx + horizon]`.

    Resolvido exclusivamente pelo persister 4.3 (indexação por sessão de pregão,
    ADR 4.3.0001) — o e2e confere contra a grade REAL semeada.
    """
    iso = pipeline.iso_timestamps
    for row in pipeline.facts():
        decision_idx = int(str(row["decision_idx"]))
        horizon = int(str(row["horizon"]))
        assert str(row["timestamp_utc"]) == iso[decision_idx]
        assert str(row["target_timestamp_utc"]) == iso[decision_idx + horizon]


# -- I10: dim_run por (spec x fold), referenciado pelas predições ------------------


@pytest.mark.integration
def test_e2e_dim_run_one_row_per_spec_fold(pipeline: _PipelineRun) -> None:
    """`dim_run` tem 5 specs x 2 folds com `seed=None` e `parent_sweep_id` do cohort."""
    rows = pipeline.dim_run()

    assert len(rows) == _N_SPECS * _N_FOLDS
    assert {str(r["model_version"]) for r in rows} == {
        f"baseline_{spec.family}" for spec in _command().specs
    }
    assert {str(r["fold"]) for r in rows} == {"0", "1"}
    assert all(r["seed"] is None for r in rows)
    assert all(str(r["parent_sweep_id"]) == _COHORT_ID for r in rows)
    assert all(str(r["split_fingerprint"]) for r in rows)


@pytest.mark.integration
def test_e2e_run_ids_link_facts_to_dim_run(pipeline: _PipelineRun) -> None:
    """I10: todo `run_id` dos summaries e das predições existe em `dim_run`."""
    dim_run_ids = {str(r["run_id"]) for r in pipeline.dim_run()}

    assert {summary.run_id for summary in pipeline.result.runs} == dim_run_ids
    assert {str(r["run_id"]) for r in pipeline.facts()} <= dim_run_ids


# -- A2/I5: grade degenerada atravessa o guardrail ---------------------------------


@pytest.mark.integration
def test_e2e_degenerate_grid_identical_guardrail_and_flag_zero(
    pipeline: _PipelineRun,
) -> None:
    """A2/I5: `zero_return`/`historical_mean` persistem a grade degenerada intacta.

    `value_guardrail` IDÊNTICO em todas as linhas de `quantile_level` de uma
    mesma decisão x horizonte e `guardrail_applied == 0` (o guardrail 4.3 nunca
    rejeita quantis colapsados — schema LONG, sem q_low/q_high).
    """
    degenerate = [
        row for row in pipeline.facts() if str(row["model_version"]) in _DEGENERATE_VERSIONS
    ]
    assert degenerate, "expected degenerate-grid rows"
    assert all(int(str(row["guardrail_applied"])) == 0 for row in degenerate)

    values: dict[tuple[str, int, int], set[float]] = {}
    for row in degenerate:
        key = (str(row["run_id"]), int(str(row["decision_idx"])), int(str(row["horizon"])))
        values.setdefault(key, set()).add(float(str(row["value_guardrail"])))
    assert all(len(grid_values) == 1 for grid_values in values.values())

    # zero_return é degenerada EM 0.0 (doc de domínio §3.2).
    zero_rows = [r for r in degenerate if str(r["model_version"]) == "baseline_zero_return"]
    assert all(float(str(r["value_guardrail"])) == 0.0 for r in zero_rows)


# -- C6: cauda sem janela completa pula e conta ------------------------------------


@pytest.mark.integration
def test_e2e_c6_tail_skips_counted_and_nothing_fabricated(pipeline: _PipelineRun) -> None:
    """C6: último fold pula horizontes que estouram a grade; nada é fabricado."""
    last_fold = [s for s in pipeline.result.runs if s.fold_index == _N_FOLDS - 1]
    assert last_fold
    assert all(summary.rows_skipped > 0 for summary in last_fold)

    rows = pipeline.facts()
    max_idx = _N_SESSIONS - 1
    assert all(
        int(str(r["decision_idx"])) + int(str(r["horizon"])) <= max_idx for r in rows
    )
    # Contagem exata: o que está no silver é o que os summaries reportam (A5).
    assert len(rows) == sum(summary.rows_written for summary in pipeline.result.runs)


# -- C8: reprocessamento colide e propaga ------------------------------------------


@pytest.mark.integration
def test_e2e_c8_rerun_of_same_invocation_raises_duplicate_key(
    pipeline: _PipelineRun,
) -> None:
    """C8: reexecutar a MESMA invocação propaga `DuplicateKeyError` (I9 — mesmos
    run_ids determinísticos → mesma PK lógica no fact append-only)."""
    with pytest.raises(DuplicateKeyError):
        pipeline.deps.run_baselines(_command())
