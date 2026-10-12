"""Ponta a ponta da inferência pela CLI (Stage 7.1, Task 12; concept §11 "Integração").

Roda o `cli.main` de verdade sobre o dado bruto sintético da 5.5
(`tests/e2e/fixtures/cohort/raw_cohort_fixture.py`): `materialize` → `run` (cohort
congelado montado aqui, uma seed, geometria mínima, TFT real com uma época) →
`infer` → `verify` → segundo `infer`. Injetados pelo `CliWiring`: o sentimento fake
e um probe de foto fixa (`code_dirty = "false"`, `torch_threads` = o do processo), o
MESMO no `run` e no `infer` — então o modo esperado é `strict`, com |Δ| = 0.

A corrida inteira acontece uma vez (fixture do módulo); cada teste confere um
aspecto do resultado.
"""

from __future__ import annotations

import io
import json
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import torch

from financial_forecasting import cli
from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
)
from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepPlan,
    SweepProvenance,
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
from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    TFT_MODEL_VERSION,
    load_training_grid,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
    modeling_columns,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from tests.e2e.fixtures.cohort.raw_cohort_fixture import write_raw
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from financial_forecasting.features.market_data.domain.entities.news_article import (
        NewsArticle,
    )

pytestmark = [pytest.mark.integration, pytest.mark.slow]

cohort_file: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.cohort_file")

_ASSET = "AAPL"
_FIRST_SESSION = date(2019, 1, 2)
# A geometria do ponta a ponta da 5.5 (tests/e2e/test_cohort_cli.py): 560 sessões
# cobrem aquecimento, gaps, early stop, calib e dois folds de teste.
_N_SESSIONS = 560
_IDENTITY = ("run_id", "model_version", "asset", "feature_set_name", "schema_version")


@dataclass(frozen=True)
class _Outcome:
    """O que a corrida produziu: saídas da CLI e o silver depois do primeiro `infer`."""

    spec: CohortSpec
    cohort_id: str
    first_infer: str
    verify_code: int
    verify_out: str
    second_infer: str
    facts_after_first: tuple[Mapping[str, object], ...]
    facts_after_second: tuple[Mapping[str, object], ...]
    manifest: Mapping[str, Any]
    tft_runs: frozenset[str]


def _score(article: NewsArticle) -> float:
    return (sum(map(ord, article.article_id or "")) % 200 - 100) / 100.0


def _draft() -> CohortSpec:
    """Uma seed, dois folds, TFT mínimo; calib (16) != val (20) para pegar trocas."""
    tft_base = TftTrainingParams(
        seed=0,
        max_encoder_length=10,
        hidden_size=4,
        attention_head_size=1,
        hidden_continuous_size=2,
        max_epochs=1,
        patience=1,
        batch_size=32,
    )
    return CohortSpec(
        name="inference-e2e",
        revision=0,
        asset_id=_ASSET,
        feature_set_name="e2e",
        feature_set_hash=feature_set_hash(),
        pipeline_version=PIPELINE_VERSION,
        horizons=(1, 7),
        quantile_levels=(0.1, 0.5, 0.9),
        geometry=CohortGeometry(n_folds=2, test_size=20, val_size=20, calib_size=16, embargo=1),
        device="cpu",
        seeds=(11,),
        sweep=SweepPlan(
            tft_space=(SearchDimension(name="dropout", low=0.0, high=0.2, kind="float"),),
            tft_base_params=tft_base,
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


def _frozen(data_root: Path) -> CohortSpec:
    grid = load_training_grid(
        store=ParquetMedallionStore(data_root=data_root),
        asset_id=_ASSET,
        columns=modeling_columns(),
    )
    fingerprint = grid_fingerprint(grid, hasher=CanonicalJsonHasher(), asset_id=_ASSET)
    draft = _draft()
    return replace(
        draft,
        tft_params=replace(draft.sweep.tft_base_params, dropout=0.1),
        gbm_params=GbmTrainingParams(seed=7, num_boost_round_max=20, num_leaves=8),
        provenance=SweepProvenance(
            tft_study_id="tft-study",
            tft_best_trial=0,
            tft_best_objective=0.01,
            gbm_study_id="gbm-study",
            gbm_best_trial=0,
            gbm_best_objective=0.01,
            dataset_fingerprint=fingerprint,
        ),
        dataset_fingerprint=fingerprint,
    )


def _facts(data_root: Path) -> tuple[Mapping[str, object], ...]:
    repository = ParquetAnalyticsRepository(data_root=data_root, clock=SystemClock())
    return tuple(
        repository.read(layer="silver", table="fact_oos_predictions", filters={"asset": _ASSET})
    )


@pytest.fixture(scope="module")
def outcome(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_Outcome]:
    root = tmp_path_factory.mktemp("inference_e2e")
    data, cohort = root / "data", root / "cohort.toml"
    probe = InMemoryRuntimeEnvironmentProbe(
        torch_threads=str(torch.get_num_threads()), device="cpu"
    )
    wiring = cli.CliWiring(
        sentiment_model=InMemorySentimentModel(score_fn=_score),
        runtime_probe_factory=lambda path, device: probe,
        settings_overrides={
            "_env_file": None,
            "artifacts_root": root / "artifacts",
            "repo_root": root,
            "mlflow_tracking_uri": f"sqlite:///{root / 'mlruns.db'}",
        },
    )

    def call(command: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = [command, "--data-root", str(data), "--cohort", str(cohort)]
        code = cli.main(argv, wiring=wiring, out=out, err=err)
        return code, out.getvalue() + err.getvalue()

    def ok(command: str) -> str:
        code, text = call(command)
        assert code == 0, f"{command}: exit {code}\n{text}"
        return text

    write_raw(data, asset=_ASSET, first=_FIRST_SESSION, n_sessions=_N_SESSIONS)
    cohort.write_text(cohort_file.dump(_draft()), encoding="utf-8")
    ok("materialize")
    spec = _frozen(data)
    cohort.write_text(cohort_file.dump(spec), encoding="utf-8")
    ok("run")
    first_infer = ok("infer")
    facts_after_first = _facts(data)
    verify_code, verify_out = call("verify")
    second_infer = ok("infer")
    cohort_id = first_infer.strip().splitlines()[-1].split()[1].rstrip(":")
    manifest_path = data / "inference" / cohort_id / "manifest.json"
    yield _Outcome(
        spec=spec,
        cohort_id=cohort_id,
        first_infer=first_infer,
        verify_code=verify_code,
        verify_out=verify_out,
        second_infer=second_infer,
        facts_after_first=facts_after_first,
        facts_after_second=_facts(data),
        manifest=json.loads(manifest_path.read_text(encoding="utf-8")),
        tft_runs=frozenset(
            str(f["run_id"])
            for f in facts_after_first
            if f["model_version"] == TFT_MODEL_VERSION and f["split"] == "test"
        ),
    )


def _run_lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("run ")]


def _expected_calib_rows(spec: CohortSpec) -> int:
    return int(spec.geometry.calib_size) * len(spec.horizons) * len(spec.quantile_levels)


def _test_rows_by_run(outcome: _Outcome) -> dict[str, int]:
    """Valores de teste de cada run TFT no silver: o que o `infer` tem de comparar.

    Não é `test_size x |horizontes| x |níveis|` em todo fold: o último bloco de teste
    perde as decisões cujo alvo cai além do fim da série (na geometria daqui, 96 em
    vez de 120). A contagem vem da referência gravada pelo treino.
    """
    counts = Counter(
        str(f["run_id"])
        for f in outcome.facts_after_first
        if f["split"] == "test" and str(f["run_id"]) in outcome.tft_runs
    )
    return dict(counts)


def _compared(line: str) -> tuple[str, int]:
    words = line.split()
    return words[1], int(words[words.index("compared") + 1])


def _expected_runs(spec: CohortSpec) -> int:
    return int(spec.geometry.n_folds) * len(spec.seeds)


def _multiset(facts: Sequence[Mapping[str, object]]) -> Counter[tuple[tuple[str, object], ...]]:
    """As linhas inteiras (PK, valores e identidade), com repetição."""
    return Counter(tuple(sorted(fact.items())) for fact in facts)


def test_infer_reproduces_every_run_strict_with_zero_diff(outcome: _Outcome) -> None:
    lines = _run_lines(outcome.first_infer)

    assert len(lines) == _expected_runs(outcome.spec)
    assert {line.split()[1] for line in lines} == outcome.tft_runs
    calib = _expected_calib_rows(outcome.spec)
    reference = _test_rows_by_run(outcome)
    assert set(reference) == outcome.tft_runs
    assert min(reference.values()) > 0
    assert dict(_compared(line) for line in lines) == reference  # cada valor de teste
    for line in lines:
        assert ": strict compared " in line, line
        assert " max|d| 0.000e+00 max|d|/s 0.000e+00 " in line, line
        assert line.endswith(f"calib written {calib} verified 0"), line
    summary = outcome.first_infer.strip().splitlines()[-1]
    total = len(lines)
    assert summary == (
        f"inference {outcome.cohort_id}: {total} runs ({total} strict, 0 tolerance); "
        f"calib rows written {total * calib}, verified 0"
    )


def test_calib_rows_expected_per_run_with_training_identity(outcome: _Outcome) -> None:
    calib = [f for f in outcome.facts_after_first if f["split"] == "calib"]
    by_run: dict[str, list[Mapping[str, object]]] = {}
    for fact in calib:
        by_run.setdefault(str(fact["run_id"]), []).append(fact)

    assert set(by_run) == outcome.tft_runs  # só os runs TFT ganham calib
    for run_id, rows in by_run.items():
        assert len(rows) == _expected_calib_rows(outcome.spec), run_id
        test_row = next(
            f for f in outcome.facts_after_first if f["run_id"] == run_id and f["split"] == "test"
        )
        for row in rows:
            for field in _IDENTITY:
                assert row[field] == test_row[field], (run_id, field)
        _assert_guardrail_monotone(rows)


def _assert_guardrail_monotone(rows: Sequence[Mapping[str, object]]) -> None:
    grids: dict[tuple[object, object], list[tuple[float, float]]] = {}
    for row in rows:
        key = (row["decision_idx"], row["horizon"])
        level = float(str(row["quantile_level"]))
        grids.setdefault(key, []).append((level, float(str(row["value_guardrail"]))))
    for key, grid in grids.items():
        values = [value for _, value in sorted(grid)]
        assert values == sorted(values), key


def test_verify_is_green_after_infer(outcome: _Outcome) -> None:
    assert outcome.verify_code == 0, outcome.verify_out
    assert outcome.verify_out.rstrip().endswith("OK")


def test_second_infer_writes_zero_rows(outcome: _Outcome) -> None:
    lines = _run_lines(outcome.second_infer)
    expected = _expected_calib_rows(outcome.spec)

    assert len(lines) == _expected_runs(outcome.spec)
    assert {line.split()[1] for line in lines} == outcome.tft_runs
    assert dict(_compared(line) for line in lines) == _test_rows_by_run(outcome)
    for line in lines:
        assert ": strict compared " in line, line
        assert " max|d| 0.000e+00 max|d|/s 0.000e+00 " in line, line
        assert line.endswith(f"calib written 0 verified {expected}"), line
    summary = outcome.second_infer.strip().splitlines()[-1]
    assert summary.endswith(f"calib rows written 0, verified {len(lines) * expected}")
    # nada reescrito nem duplicado: o silver é o MESMO multiconjunto de linhas inteiras
    assert _multiset(outcome.facts_after_second) == _multiset(outcome.facts_after_first)


def test_manifest_is_complete(outcome: _Outcome) -> None:
    manifest = outcome.manifest
    runs = manifest["runs"]

    assert manifest["cohort_id"] == outcome.cohort_id
    assert manifest["cohort_environment"]
    assert set(runs) == outcome.tft_runs
    for run_id, entry in runs.items():
        assert entry["status"] == "completed", run_id
        assert entry["reproduction_mode"] == "strict"
        assert entry["max_abs_diff"] == 0.0
        assert len(entry["checkpoint_sha256"]) == 64  # noqa: PLR2004 — hex do sha256
        assert entry["calib_rows_written"] == 0  # a última verificação foi o 2º infer
        assert entry["calib_rows_verified"] == _expected_calib_rows(outcome.spec)
        for field in ("first_write_environment", "first_write_settings", "first_written_at"):
            assert entry[field], (run_id, field)
