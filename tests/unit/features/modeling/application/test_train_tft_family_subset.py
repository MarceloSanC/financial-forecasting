"""`TrainTft` por subconjunto de famílias (Stage 7.3, ablação LOCO; CA1, CA2, I1-I3, C1).

Reusa as fixtures de `test_train_tft.py`. O comando default tem de dar a mesma
identidade de antes da Stage (literais medidos no `$BASE`); a configuração sem uma
família lê e apara o grid pelo conjunto completo, troca o `feature_set_hash` do `run_id`
pelo do subconjunto e leva o `model_version` da configuração a tudo o que persiste.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    FEATURE_SPECS,
    list_feature_specs,
)
from financial_forecasting.features.modeling.application.pipeline_version import (
    PIPELINE_VERSION,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    MODEL_VERSION,
    TFT_FAMILIES,
    known_feature_names,
    load_tft_panel,
    loco_model_version,
    registry_family_partition,
    tft_feature_set_hash,
    unknown_feature_names,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.run_id import RunId
from tests.unit.features.modeling.application.test_train_tft import (
    _SCOPE,
    _SEED,
    _build,
    _command,
    _dataset_rows,
    _folds,
    _seeded_store,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
        FakeAnalyticsRepository,
    )

pytestmark = pytest.mark.unit

# Medidos no `$BASE` (0f461e1) com as fixtures de `test_train_tft.py`, antes da mudança.
_PINNED_FOLD0_RUN_ID = "ea8ed2e894acd8f3e4fb5bc1b65380bb66bee9e7419ff99bde58ff67e1e3216d"
_PINNED_FOLD1_RUN_ID = "640eb66bbf73d28aeec84c643ea32f116f9e30776f9ee7c4fc419e78c454f279"
_PINNED_CONFIG_SIGNATURE = "b5d077bd006f9f4508510c65cef3e9875cefc8b80291deea270dd13f40d04c62"
_PARTITION_SIZES = {"price": 17, "technical": 17, "sentiment": 11, "fundamental": 10}
_HASH_PREFIXES = {
    None: "7df0e1b4",
    "price": "7631c0ae",
    "technical": "b75eca48",
    "sentiment": "5f737061",
    "fundamental": "c58b322f",
}
_CONFIRMATORY_PHASE = "confirmatory_ready"
_WARMUP = 8


def _loco(family: str | None) -> dict[str, object]:
    configuration = "full" if family is None else f"minus_{family}"
    return {"excluded_family": family, "model_version": loco_model_version(configuration)}


def _dim_run(repo: FakeAnalyticsRepository) -> dict[str, dict[str, object]]:
    return {str(row["fold"]): dict(row) for row in repo.read(layer="silver", table="dim_run")}


def _warmup_rows(family: str) -> list[dict[str, object]]:
    """Dataset em que uma feature da família tem o maior aquecimento (prefixo nulo)."""
    rows = _dataset_rows()
    feature = registry_family_partition()[family][0]
    for row in rows[:_WARMUP]:
        row[feature] = None
    return rows


def test_default_command_keeps_the_pinned_run_id_and_config_signature(tmp_path: Path) -> None:
    use_case, repo, _, _ = _build(tmp_path)
    use_case(_command())
    table = _dim_run(repo)
    assert table["0"]["run_id"] == _PINNED_FOLD0_RUN_ID
    assert table["1"]["run_id"] == _PINNED_FOLD1_RUN_ID
    assert {row["config_signature"] for row in table.values()} == {_PINNED_CONFIG_SIGNATURE}
    assert {row["model_version"] for row in table.values()} == {MODEL_VERSION}


def test_registry_family_partition_is_17_17_11_10_in_registry_order() -> None:
    partition = registry_family_partition()
    assert tuple(partition) == TFT_FAMILIES
    assert {family: len(features) for family, features in partition.items()} == _PARTITION_SIZES
    registry_order = [spec.name for spec in list_feature_specs(enabled_only=True)]
    for features in partition.values():
        assert list(features) == [name for name in registry_order if name in set(features)]
    assert sorted(name for features in partition.values() for name in features) == sorted(
        registry_order
    )


def test_every_family_feature_is_unknown() -> None:
    unknown = set(unknown_feature_names())
    for features in registry_family_partition().values():
        assert set(features) <= unknown
        assert all(FEATURE_SPECS[name].tft_typing == "unknown" for name in features)


@pytest.mark.parametrize("family", TFT_FAMILIES)
def test_subset_panel_columns_are_registry_minus_family_in_order(family: str) -> None:
    full = load_tft_panel(store=_seeded_store(), asset_id=_SCOPE.asset_id)
    subset = load_tft_panel(store=_seeded_store(), asset_id=_SCOPE.asset_id, excluded_family=family)
    dropped = set(registry_family_partition()[family])
    assert subset.feature_names == tuple(n for n in full.feature_names if n not in dropped)
    assert subset.known_feature_names == known_feature_names()
    assert set(subset.known_feature_names) <= set(subset.feature_names)
    assert not dropped & set(subset.feature_names)


@pytest.mark.parametrize("family", TFT_FAMILIES)
def test_subset_grid_is_trimmed_on_the_full_column_set(tmp_path: Path, family: str) -> None:
    rows = _warmup_rows(family)
    full_panel = load_tft_panel(store=_seeded_store(rows), asset_id=_SCOPE.asset_id)
    subset_panel = load_tft_panel(
        store=_seeded_store(rows), asset_id=_SCOPE.asset_id, excluded_family=family
    )
    # o prefixo nulo da família removida corta o grid das duas configurações
    assert len(full_panel.timestamps) == len(rows) - _WARMUP
    assert subset_panel.timestamps == full_panel.timestamps
    assert subset_panel.sessions == full_panel.sessions

    full_uc, full_repo, full_trainer, _ = _build(tmp_path / "full", store=_seeded_store(rows))
    full_uc(_command(**_loco(None)))
    sub_uc, sub_repo, sub_trainer, _ = _build(tmp_path / "subset", store=_seeded_store(rows))
    sub_uc(_command(**_loco(family)))

    for key in ("train_decision_indices", "early_stop_decision_indices", "test_decision_indices"):
        assert [call[key] for call in sub_trainer.calls] == [
            call[key] for call in full_trainer.calls
        ]
    full_runs, sub_runs = _dim_run(full_repo), _dim_run(sub_repo)
    assert set(sub_runs) == set(full_runs)
    for fold in full_runs:
        assert sub_runs[fold]["split_fingerprint"] == full_runs[fold]["split_fingerprint"]


def test_subset_run_id_carries_subset_hash_and_loco_model_version(tmp_path: Path) -> None:
    use_case, repo, _, _ = _build(tmp_path)
    use_case(_command(**_loco("sentiment")))
    table = _dim_run(repo)
    for fold in _folds():
        row = table[str(fold.fold_index)]
        expected = RunId.compute(
            hasher=CanonicalJsonHasher(),
            asset=_SCOPE.asset_id,
            feature_set_hash=tft_feature_set_hash("sentiment"),
            trial_number=None,
            fold=str(fold.fold_index),
            seed=_SEED,
            model_version="tft_quantile_loco_minus_sentiment",
            config_signature=str(row["config_signature"]),
            split_signature=fold.fingerprint.value,
            pipeline_version=PIPELINE_VERSION,
        )
        assert row["run_id"] == expected.value
    assert tft_feature_set_hash("sentiment") != tft_feature_set_hash(None)


@pytest.mark.parametrize(("family", "prefix"), list(_HASH_PREFIXES.items()))
def test_tft_feature_set_hash_matches_the_measured_prefixes(
    family: str | None, prefix: str
) -> None:
    assert tft_feature_set_hash(family).startswith(prefix)


def test_loco_full_differs_from_candidate_only_in_model_version(tmp_path: Path) -> None:
    candidate_uc, candidate_repo, _, _ = _build(tmp_path / "candidate")
    candidate_uc(_command())
    full_uc, full_repo, _, _ = _build(tmp_path / "full")
    full_uc(_command(**_loco(None)))
    candidate, full = _dim_run(candidate_repo), _dim_run(full_repo)
    for fold in candidate:
        assert full[fold]["config_signature"] == candidate[fold]["config_signature"]
        assert full[fold]["split_fingerprint"] == candidate[fold]["split_fingerprint"]
        assert full[fold]["run_id"] != candidate[fold]["run_id"]
        assert full[fold]["model_version"] == "tft_quantile_loco_full"


def test_subset_rows_and_dim_run_carry_loco_model_version(tmp_path: Path) -> None:
    use_case, repo, _, _ = _build(tmp_path)
    result = use_case(_command(**_loco("price")))
    expected = "tft_quantile_loco_minus_price"
    predictions = repo.read(layer="silver", table="fact_oos_predictions")
    assert predictions
    assert {row["model_version"] for row in predictions} == {expected}
    assert {row["model_version"] for row in _dim_run(repo).values()} == {expected}
    assert {summary.model_version for summary in result.runs} == {expected}


def test_tracking_phase_tag_of_loco_runs(tmp_path: Path) -> None:
    """Decisão da Task 02 (§7): o run LOCO mantém `phase = confirmatory_ready`."""
    use_case, _, _, tracker = _build(tmp_path)
    result = use_case(_command(**_loco("technical")))
    for summary in result.runs:
        run = tracker._runs[summary.tracking_run_id]
        assert run.tags["phase"] == _CONFIRMATORY_PHASE
        assert run.tags["model_version"] == "tft_quantile_loco_minus_technical"
        assert run.params["model_version"] == "tft_quantile_loco_minus_technical"
        assert run.run_name == f"tft_quantile_loco_minus_technical-{summary.run_id}"


@pytest.mark.parametrize(
    ("excluded_family", "model_version"),
    [
        pytest.param("price", "tft_quantile_loco_minus_technical", id="other-family-version"),
        pytest.param("price", MODEL_VERSION, id="family-with-candidate-version"),
        pytest.param("price", "tft_quantile_loco_full", id="family-with-full-version"),
        pytest.param(None, "tft_quantile_loco_minus_price", id="none-with-minus-version"),
        pytest.param(None, "tft_quantile_other", id="none-with-unknown-version"),
        pytest.param("volatility", "tft_quantile_loco_minus_volatility", id="unknown-family"),
    ],
)
def test_model_version_pairing_refused_before_any_io(
    tmp_path: Path, excluded_family: str | None, model_version: str
) -> None:
    store = _seeded_store()
    use_case, _, trainer, _ = _build(tmp_path, store=store)
    with pytest.raises(ValueError, match=r"\(C2\)"):
        use_case(_command(excluded_family=excluded_family, model_version=model_version))
    assert store.read_calls == 0
    assert trainer.call_count == 0
