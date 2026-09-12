"""Identidade do run em `TrainTft` — `RunId`/`ConfigSignature` como caminho único.

Issue #65 / ADR 5.2.0004. Reusa as fixtures de `test_train_tft.py`. Mesma
bateria de `test_train_gbm_quantile_identity.py`, mais o que só o TFT tem: a
tipagem known/unknown dentro de `config_signature` (I10) e `max_horizon` como
comprimento do decodificador (ADR 5.4.0002) — o teste de aliasing aqui prova
que dois modelos DIFERENTES (decodificador 2 vs 3 passos) nunca colidem em
`run_id`, mesmo com a `split_fingerprint` idêntica.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    feature_set_hash,
)
from financial_forecasting.features.modeling.application.pipeline_version import (
    PIPELINE_VERSION,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases import train_tft as tft_module
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.run_id import RunId
from tests.unit.features.modeling.application.test_train_tft import (
    _COHORT_ID,
    _ENCODER_LENGTH,
    _SCOPE,
    _SEED,
    _build,
    _command,
    _CountingStore,
    _dataset_rows,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from financial_forecasting.features.modeling.application.use_cases.train_tft import (
        TrainTftCommand,
    )

# fold -> (run_id, config_signature, split_fingerprint)
_Identity = dict[str, tuple[str, str, str]]


def _identity_of(
    tmp_path: Path, command: TrainTftCommand, *, asset: str | None = None
) -> _Identity:
    store: _CountingStore | None = None
    if asset is not None:
        store = _CountingStore()
        store.seed_read_only(
            layer="processed", table="dataset_tft", asset=asset, rows=_dataset_rows()
        )
    use_case, repo, _, _ = _build(tmp_path, store=store)
    use_case(command)
    table: _Identity = {}
    for row in repo.read(layer="silver", table="dim_run"):
        table[str(row["fold"])] = (
            str(row["run_id"]),
            str(row["config_signature"]),
            str(row["split_fingerprint"]),
        )
    return table


def _assert_all_run_ids_differ(base: _Identity, changed: _Identity) -> None:
    common = set(base) & set(changed)
    assert common
    for key in common:
        assert base[key][0] != changed[key][0], f"run_id não mudou para fold {key}"


def _params(**overrides: object) -> TftTrainingParams:
    base: dict[str, object] = {
        "seed": _SEED,
        "max_encoder_length": _ENCODER_LENGTH,
        "max_epochs": 3,
    }
    base.update(overrides)
    return TftTrainingParams(**base)  # type: ignore[arg-type]


def _scope(**overrides: object) -> ScopeSpec:
    base: dict[str, object] = {
        "asset_id": _SCOPE.asset_id,
        "feature_set_name": _SCOPE.feature_set_name,
        "max_horizon": _SCOPE.max_horizon,
        "cohort_id": _SCOPE.cohort_id,
    }
    base.update(overrides)
    return ScopeSpec(**base)  # type: ignore[arg-type]


# -- o teste que É a issue ---------------------------------------------------------


@pytest.mark.unit
def test_run_id_invariant_under_schema_version_change(tmp_path: Path) -> None:
    """Bump de `schema_version` NÃO muda `run_id` nem `config_signature` (#65 (a))."""
    v1 = _identity_of(tmp_path / "v1", _command(schema_version=1))
    v2 = _identity_of(tmp_path / "v2", _command(schema_version=2))

    assert v1 == v2


@pytest.mark.unit
def test_schema_version_is_still_a_dim_run_column(tmp_path: Path) -> None:
    use_case, repo, _, _ = _build(tmp_path)

    use_case(_command(schema_version=7))

    rows = repo.read(layer="silver", table="dim_run")
    assert rows
    assert all(row["schema_version"] == 7 for row in rows)  # noqa: PLR2004


# -- oráculo dos 9 slots ------------------------------------------------------------


@pytest.mark.unit
def test_persisted_run_id_is_run_id_compute_over_the_nine_declared_slots(
    tmp_path: Path,
) -> None:
    use_case, repo, _, _ = _build(tmp_path)
    hasher = CanonicalJsonHasher()

    result = use_case(_command())

    rows = repo.read(layer="silver", table="dim_run")
    assert rows
    for row in rows:
        expected = RunId.compute(
            hasher=hasher,
            asset=str(row["asset"]),
            feature_set_hash=feature_set_hash(),
            trial_number=None,
            fold=str(row["fold"]),
            seed=_SEED,
            model_version="tft_quantile",
            config_signature=str(row["config_signature"]),
            split_signature=str(row["split_fingerprint"]),
            pipeline_version=PIPELINE_VERSION,
        )
        assert row["run_id"] == expected.value
        assert row["seed"] == _SEED
        assert row["parent_sweep_id"] == _COHORT_ID
    # O diretório do artefato (D9) segue derivado do run_id canônico.
    for summary in result.runs:
        assert summary.run_id in summary.artifact_path


# -- cada slot variável muda o run_id -----------------------------------------------


@pytest.mark.unit
def test_slot_asset_changes_run_id(tmp_path: Path) -> None:
    base = _identity_of(tmp_path / "a", _command())
    changed = _identity_of(tmp_path / "b", _command(scope=_scope(asset_id="OTHER")), asset="OTHER")

    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_slot_feature_set_hash_changes_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _identity_of(tmp_path / "a", _command())
    monkeypatch.setattr(tft_module, "feature_set_hash", lambda: "other-registry")
    changed = _identity_of(tmp_path / "b", _command())

    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_slot_seed_changes_run_id_but_not_config_signature(tmp_path: Path) -> None:
    base = _identity_of(tmp_path / "a", _command())
    changed = _identity_of(tmp_path / "b", _command(params=_params(seed=_SEED + 1)))

    for key in set(base) & set(changed):
        assert base[key][1] == changed[key][1], "config_signature NÃO deveria mudar com seed"
    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_slot_fold_separates_runs(tmp_path: Path) -> None:
    table = _identity_of(tmp_path, _command())

    run_ids = [value[0] for value in table.values()]
    assert len(run_ids) > 1
    assert len(run_ids) == len(set(run_ids))


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"params": _params(hidden_size=8)},
        {"params": _params(dropout=0.2)},
        {"quantile_levels": (0.25, 0.5, 0.75)},
        {"horizons": (1,)},
        {"scope": _scope(cohort_id="another-cohort")},
        {"scope": _scope(feature_set_name="fs_other")},
    ],
    ids=["hidden_size", "dropout", "quantile_levels", "horizons", "cohort_id", "fs_name"],
)
def test_slot_config_signature_changes_run_id(
    tmp_path: Path, overrides: Mapping[str, object]
) -> None:
    base = _identity_of(tmp_path / "a", _command())
    changed = _identity_of(tmp_path / "b", _command(**overrides))

    for key in set(base) & set(changed):
        assert base[key][1] != changed[key][1], f"config_signature não mudou (fold {key})"
    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_slot_split_signature_changes_run_id(tmp_path: Path) -> None:
    base = _identity_of(tmp_path / "a", _command(embargo=1))
    changed = _identity_of(tmp_path / "b", _command(embargo=2))

    for key in set(base) & set(changed):
        assert base[key][2] != changed[key][2]
        assert base[key][1] == changed[key][1]
    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_slot_pipeline_version_changes_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _identity_of(tmp_path / "a", _command())
    monkeypatch.setattr(tft_module, "PIPELINE_VERSION", "999")
    changed = _identity_of(tmp_path / "b", _command())

    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_max_horizon_enters_identity_even_when_split_fingerprint_is_unchanged(
    tmp_path: Path,
) -> None:
    """Decodificador de 2 vs 3 passos com a MESMA impressão de split: run_ids distintos."""
    gap_via_embargo = _identity_of(tmp_path / "a", _command(scope=_scope(max_horizon=2), embargo=2))
    gap_via_horizon = _identity_of(tmp_path / "b", _command(scope=_scope(max_horizon=3), embargo=1))

    for key in set(gap_via_embargo) & set(gap_via_horizon):
        assert gap_via_embargo[key][2] == gap_via_horizon[key][2]
    _assert_all_run_ids_differ(gap_via_embargo, gap_via_horizon)


@pytest.mark.unit
def test_known_typing_is_inside_config_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I10: mover uma coluna de unknown para known muda a `config_signature`.

    A ÚLTIMA unknown vira a PRIMEIRA known: `feature_names = unknown + known`
    fica byte a byte igual e `feature_set_hash` (registry) também — quem
    distingue os dois cenários é só `known_feature_names` dentro da config.
    """
    base = _identity_of(tmp_path / "a", _command())
    unknown = tft_module.unknown_feature_names()
    known = tft_module.known_feature_names()
    moved = unknown[-1]
    monkeypatch.setattr(tft_module, "unknown_feature_names", lambda: unknown[:-1])
    monkeypatch.setattr(tft_module, "known_feature_names", lambda: (moved, *known))
    assert (*unknown[:-1], moved, *known) == (*unknown, *known)
    changed = _identity_of(tmp_path / "b", _command())

    for key in set(base) & set(changed):
        assert base[key][1] != changed[key][1]
    _assert_all_run_ids_differ(base, changed)
