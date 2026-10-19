"""Ponta a ponta do `attribute` pela CLI (Stage 7.3, Task 20; CA9, I9, base do CA15).

Roda o `cli.main` de verdade sobre o dado bruto sintético da 5.5, no padrão do e2e do
`infer` (`test_run_inference.py`): `materialize` → `run` (cohort confirmatório
congelado montado aqui, uma seed, geometria mínima, TFT real com uma época) →
`attribute` → segundo `attribute`. O `[partition]` vem de um arquivo de ablação em
rascunho que declara esse cohort como base (o `cli.py` o lê pelo loader do `modeling`).
O probe é o MESMO no `run` e no `attribute`, então o modo esperado é `strict`, com
|Δ| = 0 na identidade. Silver em Parquet real sob `tmp_path` — nada do cohort real.

A corrida inteira acontece uma vez (fixture do módulo); cada teste confere um aspecto.
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
from financial_forecasting.features.inference.domain.value_objects.permutation_plan import K_P
from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
    ABLATION_CONFIGURATIONS,
    ABLATION_FEATURE_SET_NAME,
    AblationCohortSpec,
    AblationConfiguration,
    excluded_family_of,
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
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    registry_family_partition,
    tft_feature_set_hash,
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
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
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
ablation_file: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.ablation_cohort_file")

_ASSET = "AAPL"
_FIRST_SESSION = date(2019, 1, 2)
_N_SESSIONS = 560  # a geometria do e2e da 5.5 e do `infer`: dois folds de teste
_BASE_FILE = "cohort.toml"  # relativo ao `repo_root` do wiring (o `tmp_path` da corrida)
# identidade + cada (família, k) do plano: 1 + |famílias| x K_p = 41 linhas por valor de teste
_PERMUTED_PER_TEST_VALUE = 1 + len(registry_family_partition()) * K_P


@dataclass(frozen=True)
class _Outcome:
    """O que a corrida produziu: saídas da CLI, silver e manifesto."""

    spec: CohortSpec
    cohort_id: str
    first: str
    second: str
    oos: tuple[Mapping[str, object], ...]
    permuted_after_first: tuple[Mapping[str, object], ...]
    permuted_after_second: tuple[Mapping[str, object], ...]
    vsn_after_first: tuple[Mapping[str, object], ...]
    vsn_after_second: tuple[Mapping[str, object], ...]
    manifest: Mapping[str, Any]
    tft_runs: frozenset[str]
    data_root: Path


def _score(article: NewsArticle) -> float:
    return (sum(map(ord, article.article_id or "")) % 200 - 100) / 100.0


def _draft() -> CohortSpec:
    """Uma seed, dois folds, TFT mínimo (o rascunho do e2e do `infer`)."""
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
        name="attribute-e2e",
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


def _ablation(base: CohortSpec) -> AblationCohortSpec:
    """Rascunho de ablação cuja base é o cohort congelado da corrida (fonte do `[partition]`)."""
    base_hash = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=base.hash_payload())
    return AblationCohortSpec(
        name="attribute_e2e_ablation",
        revision=0,
        base_cohort_file=_BASE_FILE,
        base_cohort_id=base.cohort_id(base_hash),
        base_cohort_hash=base_hash.value,
        feature_set_name=ABLATION_FEATURE_SET_NAME,
        configurations=tuple(
            AblationConfiguration.of(
                name, feature_set_hash=tft_feature_set_hash(excluded_family_of(name))
            )
            for name in ABLATION_CONFIGURATIONS
        ),
        family_partition=registry_family_partition(),
        seeds=(),
        device="cpu",
        torch_build=None,
    )


def _read(data_root: Path, table: str) -> tuple[Mapping[str, object], ...]:
    repository = ParquetAnalyticsRepository(data_root=data_root, clock=SystemClock())
    return tuple(repository.read(layer="silver", table=table, filters={"asset": _ASSET}))


@pytest.fixture(scope="module")
def outcome(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_Outcome]:
    root = tmp_path_factory.mktemp("attribute_e2e")
    data, cohort, ablation = root / "data", root / _BASE_FILE, root / "ablation.toml"
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

    def ok(command: str, *extra: str) -> str:
        out, err = io.StringIO(), io.StringIO()
        argv = [command, "--data-root", str(data), "--cohort", str(cohort), *extra]
        code = cli.main(argv, wiring=wiring, out=out, err=err)
        text = out.getvalue() + err.getvalue()
        assert code == 0, f"{command}: exit {code}\n{text}"
        return out.getvalue()

    write_raw(data, asset=_ASSET, first=_FIRST_SESSION, n_sessions=_N_SESSIONS)
    cohort.write_text(cohort_file.dump(_draft()), encoding="utf-8")
    ok("materialize")
    spec = _frozen(data)
    cohort.write_text(cohort_file.dump(spec), encoding="utf-8")
    ok("run")
    ablation.write_text(ablation_file.dump_ablation_cohort(_ablation(spec)), encoding="utf-8")
    first = ok("attribute", "--ablation-cohort", str(ablation))
    permuted_after_first = _read(data, "fact_permuted_predictions")
    vsn_after_first = _read(data, "fact_vsn_weights")
    second = ok("attribute", "--ablation-cohort", str(ablation))
    cohort_id = first.strip().splitlines()[-1].split()[1].rstrip(":")
    manifest_path = data / "inference" / cohort_id / "attribution_manifest.json"
    oos = _read(data, "fact_oos_predictions")
    yield _Outcome(
        spec=spec,
        cohort_id=cohort_id,
        first=first,
        second=second,
        oos=oos,
        permuted_after_first=permuted_after_first,
        permuted_after_second=_read(data, "fact_permuted_predictions"),
        vsn_after_first=vsn_after_first,
        vsn_after_second=_read(data, "fact_vsn_weights"),
        manifest=json.loads(manifest_path.read_text(encoding="utf-8")),
        tft_runs=frozenset(
            str(f["run_id"])
            for f in oos
            if f["model_version"] == TFT_MODEL_VERSION and f["split"] == "test"
        ),
        data_root=data,
    )


def _run_lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("run ")]


def _test_rows(outcome: _Outcome) -> dict[str, list[Mapping[str, object]]]:
    by_run: dict[str, list[Mapping[str, object]]] = {}
    for fact in outcome.oos:
        if fact["split"] == "test" and str(fact["run_id"]) in outcome.tft_runs:
            by_run.setdefault(str(fact["run_id"]), []).append(fact)
    return by_run


def _test_decisions(outcome: _Outcome) -> dict[str, int]:
    return {
        run_id: len({int(str(r["decision_idx"])) for r in rows})
        for run_id, rows in _test_rows(outcome).items()
    }


def _word_after(line: str, *words: str) -> int:
    tokens = line.split()
    for index in range(len(tokens) - len(words)):
        if tuple(tokens[index : index + len(words)]) == words:
            return int(tokens[index + len(words)])
    raise AssertionError(f"{words} not in {line!r}")


def _by_run(rows: Sequence[Mapping[str, object]]) -> Counter[str]:
    return Counter(str(row["run_id"]) for row in rows)


def _multiset(rows: Sequence[Mapping[str, object]]) -> Counter[tuple[tuple[str, object], ...]]:
    """As linhas inteiras (PK, valores e identidade), com repetição."""
    return Counter(tuple(sorted(row.items())) for row in rows)


def test_attribute_writes_every_run_strict_with_zero_diff(outcome: _Outcome) -> None:
    lines = _run_lines(outcome.first)
    reference = {run_id: len(rows) for run_id, rows in _test_rows(outcome).items()}

    assert len(lines) == int(outcome.spec.geometry.n_folds) * len(outcome.spec.seeds)
    assert {line.split()[1] for line in lines} == outcome.tft_runs
    assert set(reference) == outcome.tft_runs
    assert min(reference.values()) > 0
    for line in lines:
        run_id = line.split()[1]
        assert ": strict identity compared " in line, line
        assert _word_after(line, "identity", "compared") == reference[run_id], line
        assert " max|d| 0.000e+00 max|d|/s 0.000e+00 " in line, line
        assert _word_after(line, "permuted", "written") > 0, line
        assert _word_after(line, "vsn", "written") > 0, line
    total = len(lines)
    permuted = sum(_word_after(line, "permuted", "written") for line in lines)
    vsn = sum(_word_after(line, "vsn", "written") for line in lines)
    assert outcome.first.strip().splitlines()[-1] == (
        f"attribution {outcome.cohort_id}: {total} runs ({total} strict, 0 tolerance); "
        f"permuted rows written {permuted}, verified 0; vsn rows written {vsn}, verified 0"
    )


def test_row_counts_are_41_times_test_rows_and_vsn_decisions_times_variables(
    outcome: _Outcome,
) -> None:
    test_rows = {run_id: len(rows) for run_id, rows in _test_rows(outcome).items()}
    permuted = _by_run(outcome.permuted_after_first)
    vsn_rows = outcome.vsn_after_first

    assert _PERMUTED_PER_TEST_VALUE == 41  # noqa: PLR2004 — 1 + 4 famílias x K_p = 10
    assert dict(permuted) == {r: _PERMUTED_PER_TEST_VALUE * n for r, n in test_rows.items()}
    partition = registry_family_partition()
    family_of = {feature: family for family, features in partition.items() for feature in features}
    decisions = _test_decisions(outcome)
    for run_id in outcome.tft_runs:
        rows = [row for row in vsn_rows if str(row["run_id"]) == run_id]
        variables = {str(row["variable"]) for row in rows}
        assert len(rows) == decisions[run_id] * len(variables), run_id
        assert len({(row["decision_idx"], row["variable"]) for row in rows}) == len(rows)
        assert {int(str(row["decision_idx"])) for row in rows} == {
            int(str(r["decision_idx"])) for r in _test_rows(outcome)[run_id]
        }
        # a família de cada variável é a da MESMA partição do `partition_hash` (C4-3)
        for row in rows:
            assert row["family"] == family_of.get(str(row["variable"]), "none"), row
        assert set(family_of) <= variables, run_id
    for row in outcome.permuted_after_first:
        assert row["permutation_seed"] == 130  # noqa: PLR2004 — PERMUTATION_SEED
        assert row["permutation_algorithm"] == "fisher_yates_random_random_v1"


def test_second_attribute_verifies_all_and_writes_zero(outcome: _Outcome) -> None:
    lines = _run_lines(outcome.second)
    permuted = _by_run(outcome.permuted_after_first)
    vsn = _by_run(outcome.vsn_after_first)

    assert {line.split()[1] for line in lines} == outcome.tft_runs
    for line in lines:
        run_id = line.split()[1]
        assert ": strict identity compared 0 " in line, line
        assert " max|d| 0.000e+00 max|d|/s 0.000e+00 " in line, line
        assert line.endswith(
            f"permuted verified {permuted[run_id]} vsn verified {vsn[run_id]}"
        ), line
    total = len(lines)
    assert outcome.second.strip().splitlines()[-1] == (
        f"attribution {outcome.cohort_id}: {total} runs ({total} strict, 0 tolerance); "
        f"permuted rows written 0, verified {sum(permuted.values())}; "
        f"vsn rows written 0, verified {sum(vsn.values())}"
    )
    # nada reescrito nem duplicado: o silver é o MESMO multiconjunto de linhas inteiras
    assert _multiset(outcome.permuted_after_second) == _multiset(outcome.permuted_after_first)
    assert _multiset(outcome.vsn_after_second) == _multiset(outcome.vsn_after_first)


def test_manifest_is_complete(outcome: _Outcome) -> None:
    manifest = outcome.manifest
    runs = manifest["runs"]
    permuted = _by_run(outcome.permuted_after_first)
    vsn = _by_run(outcome.vsn_after_first)
    partition_hash = {str(row["partition_hash"]) for row in outcome.permuted_after_first}

    assert manifest["cohort_id"] == outcome.cohort_id
    assert set(runs) == outcome.tft_runs
    assert len(partition_hash) == 1
    decisions = _test_decisions(outcome)
    for run_id, entry in runs.items():
        assert entry["status"] == "completed", run_id
        assert entry["mode"] == "strict"
        assert entry["max_abs_diff"] == 0.0
        assert len(entry["checkpoint_sha256"]) == 64  # noqa: PLR2004 — hex do sha256
        assert entry["permuted_rows"] == permuted[run_id]
        assert entry["vsn_rows"] == vsn[run_id]
        assert entry["k_p"] == K_P
        assert entry["n_decisions"] == decisions[run_id]
        assert entry["partition_hash"] in partition_hash
        assert entry["family_partition"] == {
            family: list(features) for family, features in registry_family_partition().items()
        }
        for field in ("first_write_environment", "settings", "started_at", "completed_at"):
            assert entry[field], (run_id, field)


def test_no_gold_directory_created(outcome: _Outcome) -> None:
    """I9: o `attribute` só grava predições no silver — nenhum gold, nada do evaluation."""
    assert not (outcome.data_root / "gold").exists()
