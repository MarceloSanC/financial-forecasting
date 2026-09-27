"""Unit test do DTO `CohortSpec` (Stage 5.5, A1 / I1 / I2 / I10).

Prova: o hash do payload muda com CADA campo (tabela paramétrica) e não muda com
a seed dentro de `tft_params`; o payload é aceito pelo `CanonicalJsonHasher`
real; `is_frozen` exige todos os campos de congelamento; `cohort_id` e o scope id
dos sweeps têm o formato declarado; validações de forma; e, estruturalmente,
nenhum campo do spec nem da proveniência carrega predição ou métrica OOS (I10).
"""

from __future__ import annotations

import dataclasses
from dataclasses import fields, replace

import pytest

from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepPlan,
    SweepProvenance,
)
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
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

_HASHER = CanonicalJsonHasher()
_PLAN = SweepPlan(
    tft_space=(SearchDimension(name="hidden_size", low=10, high=320, kind="int", log=True),),
    tft_base_params=TftTrainingParams(seed=0),
    gbm_space=(SearchDimension(name="num_leaves", low=8, high=128, kind="int"),),
    gbm_base_params=GbmTrainingParams(seed=0),
    n_trials=30,
    sampler_seed=2026,
)
_PROVENANCE = SweepProvenance(
    tft_study_id="tft-study",
    tft_best_trial=4,
    tft_best_objective=0.0123,
    gbm_study_id="gbm-study",
    gbm_best_trial=7,
    gbm_best_objective=0.0111,
    dataset_fingerprint="a" * 64,
)


def _spec(**overrides: object) -> CohortSpec:
    base: dict[str, object] = {
        "name": "aapl_confirmatory",
        "revision": 0,
        "asset_id": "AAPL",
        "feature_set_name": "fs_all",
        "feature_set_hash": "f" * 64,
        "pipeline_version": "2",
        "horizons": (1, 7),
        "quantile_levels": (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98),
        "geometry": CohortGeometry(
            n_folds=6, test_size=252, val_size=252, calib_size=252, embargo=7
        ),
        "device": "cpu",
        "seeds": (11, 22, 33, 44, 55),
        "sweep": _PLAN,
        "tft_params": TftTrainingParams(seed=0, hidden_size=40),
        "gbm_params": GbmTrainingParams(seed=0, num_leaves=16),
        "baseline_specs": BaselineSpec.canonical_five(),
        "provenance": _PROVENANCE,
        "dataset_fingerprint": "a" * 64,
    }
    base.update(overrides)
    return CohortSpec(**base)  # type: ignore[arg-type]


def _hash(spec: CohortSpec) -> str:
    return CohortHash.compute(hasher=_HASHER, payload=spec.hash_payload()).value


# Um valor alterado por campo do spec: todos precisam mudar o hash (I2).
_CHANGES: dict[str, object] = {
    "name": "aapl_other",
    "revision": 1,
    "asset_id": "MSFT",
    "feature_set_name": "fs_other",
    "feature_set_hash": "e" * 64,
    "pipeline_version": "3",
    "horizons": (1,),
    "quantile_levels": (0.05, 0.5, 0.95),
    "geometry": CohortGeometry(n_folds=5, test_size=252, val_size=252, calib_size=252, embargo=7),
    "device": "rocm",
    "seeds": (11, 22, 33),
    "sweep": replace(_PLAN, n_trials=60),
    "tft_params": TftTrainingParams(seed=0, hidden_size=80),
    "gbm_params": GbmTrainingParams(seed=0, num_leaves=32),
    "baseline_specs": BaselineSpec.canonical_five(historical_quantiles_window=126),
    "provenance": replace(_PROVENANCE, tft_best_trial=5),
    "dataset_fingerprint": "b" * 64,
}


def test_change_table_covers_every_field() -> None:
    assert set(_CHANGES) == {field.name for field in fields(CohortSpec)}


@pytest.mark.parametrize(("field_name", "value"), list(_CHANGES.items()))
def test_every_field_changes_the_hash(field_name: str, value: object) -> None:
    assert _hash(_spec(**{field_name: value})) != _hash(_spec())


def test_seed_inside_tft_params_does_not_change_the_hash() -> None:
    """A seed do TFT é por unidade (cada seed do cohort roda com a sua)."""
    reseeded = _spec(tft_params=TftTrainingParams(seed=999, hidden_size=40))

    assert _hash(reseeded) == _hash(_spec())


def test_hash_is_stable_for_the_same_declaration() -> None:
    assert _hash(_spec()) == _hash(_spec())


def test_draft_payload_ignores_the_freeze_fields() -> None:
    draft = _spec(
        seeds=(), tft_params=None, gbm_params=None, provenance=None, dataset_fingerprint=None
    )

    assert draft.draft_payload() == _spec().draft_payload()


def test_n_trials_changes_the_draft_payload() -> None:
    """Rodadas de medição (`--n-trials 1`) caem noutro scope id que o sweep real (§1)."""
    measured = _spec(sweep=replace(_PLAN, n_trials=1))

    assert measured.draft_payload() != _spec().draft_payload()


def test_is_frozen_requires_every_freeze_field() -> None:
    assert _spec().is_frozen()
    for overrides in (
        {"seeds": ()},
        {"tft_params": None},
        {"gbm_params": None},
        {"provenance": None},
        {"dataset_fingerprint": None},
        {"sweep": replace(_PLAN, n_trials=None)},
    ):
        assert not _spec(**overrides).is_frozen(), overrides


def test_ids_and_scope_have_the_declared_format() -> None:
    spec = _spec(revision=2)
    cohort_hash = CohortHash.compute(hasher=_HASHER, payload=spec.hash_payload())
    draft_hash = CohortHash.compute(hasher=_HASHER, payload=spec.draft_payload())

    cohort_id = spec.cohort_id(cohort_hash)
    scope = spec.scope(cohort_id)

    assert cohort_id == f"aapl_confirmatory-r2-{cohort_hash.value[:12]}"
    assert spec.exploratory_scope_id(draft_hash) == (
        f"aapl_confirmatory-r2-sweep-{draft_hash.value[:12]}"
    )
    assert scope.cohort_id == cohort_id
    assert scope.max_horizon == 7  # noqa: PLR2004 — max(horizons)


def test_spec_is_frozen_dataclass() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _spec().revision = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"name": ""}, "name"),
        ({"device": ""}, "device"),
        ({"revision": -1}, "revision"),
        ({"horizons": ()}, "horizons"),
        ({"horizons": (7, 1)}, "horizons"),
        ({"quantile_levels": (0.5, 0.1)}, "quantile_levels"),
        ({"quantile_levels": (0.0, 0.5)}, "quantile_levels"),
        ({"seeds": (1, 1)}, "seeds"),
        ({"baseline_specs": ()}, "baseline_specs"),
    ],
)
def test_invalid_spec_is_rejected(overrides: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _spec(**overrides)


def test_sweep_plan_validation() -> None:
    with pytest.raises(ValueError, match="non-empty space"):
        replace(_PLAN, gbm_space=())
    with pytest.raises(ValueError, match="n_trials"):
        replace(_PLAN, n_trials=0)


def test_sweep_plan_rejects_a_dimension_of_the_wrong_model_at_load() -> None:
    """Erro na borda: nome de dimensão inválido barrado ao carregar o plano (A6)."""
    with pytest.raises(ValueError, match="não é campo de GbmTrainingParams"):
        replace(_PLAN, gbm_space=(SearchDimension(name="hidden_size", low=8, high=64, kind="int"),))


def test_no_field_carries_oos_predictions_or_metrics() -> None:
    """I10 (estrutural): nada no spec nem na proveniência vem de predição OOS.

    Os únicos insumos vindos de treino são HPs e objetivos de early_stop
    exploratório (`*_best_objective`); nomes que sugerem avaliação OOS
    (pinball de teste, cobertura, métrica, predição) não podem existir.
    """
    forbidden = ("oos", "test_", "coverage", "metric", "prediction", "pinball", "crps")
    names = [field.name for field in fields(CohortSpec)] + [
        field.name for field in fields(SweepProvenance)
    ]

    assert not [name for name in names if any(token in name for token in forbidden)]


@pytest.mark.unit
def test_equal_specs_hash_equal_even_when_a_number_is_int_in_one_and_float_in_the_other() -> None:
    """Lido do arquivo, `low = 8` vira `8.0` (tipo declarado); em memória pode ser `8`."""
    as_int = _spec()
    as_float = _spec(
        sweep=replace(
            _PLAN,
            tft_space=(
                SearchDimension(name="hidden_size", low=10.0, high=320.0, kind="int", log=True),
            ),
            gbm_space=(SearchDimension(name="num_leaves", low=8.0, high=128.0, kind="int"),),
        ),
    )

    assert as_int == as_float
    assert _hash(as_int) == _hash(as_float)
    assert as_int.draft_payload() == as_float.draft_payload()


@pytest.mark.unit
def test_a_non_integral_float_still_changes_the_hash() -> None:
    changed = _spec(tft_params=TftTrainingParams(seed=0, hidden_size=40, dropout=0.15))

    assert _hash(changed) != _hash(_spec())
