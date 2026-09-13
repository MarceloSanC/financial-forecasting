"""Identidade do run em `RunBaselines` — `RunId`/`ConfigSignature` como caminho único.

Issue #65 / ADR 5.2.0004. Reusa as fixtures de `test_run_baselines.py` (mesmo
padrão de `test_train_tft_tracking.py`). Prova, por esta ordem:

- `schema_version` NÃO muda `run_id` nem `config_signature` (é o teste que É a
  issue), e continua gravado como coluna de `dim_run`;
- o `run_id` persistido é EXATAMENTE `RunId.compute` sobre os 9 slots que o
  use case declara (oráculo por linha de `dim_run` — mata mutante em qualquer
  slot fixo: `trial_number`, `seed`, `fold` como `str`, `pipeline_version`,
  `feature_set_hash` do registry);
- cada slot variável do use case muda o `run_id` (asset, feature_set_hash,
  fold, model_version, config, split, pipeline_version);
- `max_horizon` entra na identidade MESMO quando a `split_fingerprint` não muda
  (aliasing medido `gap = max_horizon + embargo` — ADR 5.2.0004);
- `config_signature` é a mesma para todos os folds de uma spec (é config, não
  fold).
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
from financial_forecasting.features.modeling.application.use_cases import (
    run_baselines as run_baselines_module,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.run_id import RunId
from tests.unit.features.modeling.application.test_run_baselines import (
    _COHORT_ID,
    _SCOPE,
    _SESSIONS,
    _build,
    _command,
    _CountingStore,
    _dataset_rows,
    _returns,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
        RunBaselinesCommand,
    )

# (model_version, fold) -> (run_id, config_signature, split_fingerprint)
_Identity = dict[tuple[str, str], tuple[str, str, str]]


def _identity_of(command: RunBaselinesCommand, *, asset: str | None = None) -> _Identity:
    """Roda o use case (estado zerado) e indexa `dim_run` por (model_version, fold)."""
    store: _CountingStore | None = None
    if asset is not None:
        store = _CountingStore()
        store.seed_read_only(
            layer="processed",
            table="dataset_tft",
            asset=asset,
            rows=_dataset_rows(_SESSIONS, _returns()),
        )
    use_case, repo = _build(store=store)
    use_case(command)
    table: _Identity = {}
    for row in repo.read(layer="silver", table="dim_run"):
        key = (str(row["model_version"]), str(row["fold"]))
        table[key] = (
            str(row["run_id"]),
            str(row["config_signature"]),
            str(row["split_fingerprint"]),
        )
    return table


def _run_ids(table: _Identity) -> dict[tuple[str, str], str]:
    return {key: value[0] for key, value in table.items()}


def _assert_all_run_ids_differ(base: _Identity, changed: _Identity) -> None:
    """Toda chave presente nos dois lados tem `run_id` diferente (nenhuma colide)."""
    common = set(base) & set(changed)
    assert common, "os dois cenários precisam compartilhar pelo menos um (spec, fold)"
    for key in common:
        assert base[key][0] != changed[key][0], f"run_id não mudou para {key}"


# -- o teste que É a issue ---------------------------------------------------------


@pytest.mark.unit
def test_run_id_invariant_under_schema_version_change() -> None:
    """Bump de `schema_version` NÃO muda `run_id` nem `config_signature` (#65 (a))."""
    v1 = _identity_of(_command(schema_version=1))
    v2 = _identity_of(_command(schema_version=2))

    assert v1 == v2


@pytest.mark.unit
def test_schema_version_is_still_a_dim_run_column() -> None:
    """`schema_version` sai da CHAVE, não da LINHA: proveniência continua gravada."""
    use_case, repo = _build()

    use_case(_command(schema_version=7))

    rows = repo.read(layer="silver", table="dim_run")
    assert rows
    assert all(row["schema_version"] == 7 for row in rows)  # noqa: PLR2004


# -- oráculo: o run_id persistido É RunId.compute sobre os 9 slots declarados ------


@pytest.mark.unit
def test_persisted_run_id_is_run_id_compute_over_the_nine_declared_slots() -> None:
    """Recalcula `RunId.compute` a partir da linha de `dim_run` e bate com `run_id`.

    Fixa os slots que o use case NÃO expõe como coluna: `trial_number=None`,
    `seed=None` (baselines), `fold=str(fold_index)`, `feature_set_hash` do
    registry e `pipeline_version` da constante. Qualquer desvio num slot
    (ex.: `trial_number=0`, `fold` como int, hash de outra fonte) reprova.
    """
    use_case, repo = _build()
    hasher = CanonicalJsonHasher()

    use_case(_command())

    rows = repo.read(layer="silver", table="dim_run")
    assert rows
    for row in rows:
        expected = RunId.compute(
            hasher=hasher,
            asset=str(row["asset"]),
            feature_set_hash=feature_set_hash(),
            trial_number=None,
            fold=str(row["fold"]),
            seed=None,
            model_version=str(row["model_version"]),
            config_signature=str(row["config_signature"]),
            split_signature=str(row["split_fingerprint"]),
            pipeline_version=PIPELINE_VERSION,
        )
        assert row["run_id"] == expected.value
        assert row["seed"] is None
        assert row["parent_sweep_id"] == _COHORT_ID


# -- cada slot variável muda o run_id -----------------------------------------------


@pytest.mark.unit
def test_slot_asset_changes_run_id() -> None:
    base = _identity_of(_command())
    other_scope = ScopeSpec(
        asset_id="OTHER",
        feature_set_name=_SCOPE.feature_set_name,
        max_horizon=_SCOPE.max_horizon,
        cohort_id=_SCOPE.cohort_id,
    )
    changed = _identity_of(_command(scope=other_scope), asset="OTHER")

    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_slot_feature_set_hash_changes_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry diferente -> run_id diferente, mesmo sem baseline consumir feature."""
    base = _identity_of(_command())
    monkeypatch.setattr(run_baselines_module, "feature_set_hash", lambda: "other-registry")
    changed = _identity_of(_command())

    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_slot_fold_and_model_version_separate_runs() -> None:
    """Dentro de UMA execução: folds distintos e specs distintas nunca colidem."""
    table = _identity_of(_command())

    run_ids = list(_run_ids(table).values())
    assert len(run_ids) == len(set(run_ids))
    versions = {key[0] for key in table}
    folds = {key[1] for key in table}
    assert len(versions) > 1 and len(folds) > 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"quantile_levels": (0.25, 0.5, 0.75)},
        {"horizons": (1,)},
        {
            "scope": ScopeSpec(
                asset_id=_SCOPE.asset_id,
                feature_set_name=_SCOPE.feature_set_name,
                max_horizon=_SCOPE.max_horizon,
                cohort_id="another-cohort",
            )
        },
        {
            "scope": ScopeSpec(
                asset_id=_SCOPE.asset_id,
                feature_set_name="fs_other",
                max_horizon=_SCOPE.max_horizon,
                cohort_id=_SCOPE.cohort_id,
            )
        },
    ],
    ids=["quantile_levels", "horizons", "cohort_id", "feature_set_name"],
)
def test_slot_config_signature_changes_run_id(overrides: Mapping[str, object]) -> None:
    """Grade, horizontes, cohort e nome do feature set vivem em `config_signature`."""
    base = _identity_of(_command())
    changed = _identity_of(_command(**overrides))

    for key in set(base) & set(changed):
        assert base[key][1] != changed[key][1], f"config_signature não mudou para {key}"
    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_slot_split_signature_changes_run_id() -> None:
    """Embargo diferente -> fingerprint diferente -> run_id diferente (config igual)."""
    base = _identity_of(_command(embargo=1))
    changed = _identity_of(_command(embargo=2))

    for key in set(base) & set(changed):
        assert base[key][2] != changed[key][2], "split_fingerprint deveria mudar"
        assert base[key][1] == changed[key][1], "config_signature NÃO deveria mudar"
    _assert_all_run_ids_differ(base, changed)


@pytest.mark.unit
def test_slot_pipeline_version_changes_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bump de `PIPELINE_VERSION` muda TODO run_id — é a descontinuidade explícita."""
    base = _identity_of(_command())
    monkeypatch.setattr(run_baselines_module, "PIPELINE_VERSION", "999")
    changed = _identity_of(_command())

    _assert_all_run_ids_differ(base, changed)


# -- evidência da ADR 5.2.0004: max_horizon não está na split_fingerprint ------------


@pytest.mark.unit
def test_max_horizon_enters_identity_even_when_split_fingerprint_is_unchanged() -> None:
    """`(max_horizon=2, embargo=2)` e `(3, 1)` têm o MESMO gap e a MESMA impressão.

    Sem `max_horizon` em `config_signature`, os dois cenários colidiriam em
    `run_id`. O teste fixa a medição que motivou a decisão (A) da ADR.
    """
    scope_2 = ScopeSpec(
        asset_id=_SCOPE.asset_id, feature_set_name=_SCOPE.feature_set_name, max_horizon=2
    )
    scope_3 = ScopeSpec(
        asset_id=_SCOPE.asset_id, feature_set_name=_SCOPE.feature_set_name, max_horizon=3
    )
    gap_via_embargo = _identity_of(_command(scope=scope_2, embargo=2))
    gap_via_horizon = _identity_of(_command(scope=scope_3, embargo=1))

    for key in set(gap_via_embargo) & set(gap_via_horizon):
        assert gap_via_embargo[key][2] == gap_via_horizon[key][2], "impressões deveriam colidir"
    _assert_all_run_ids_differ(gap_via_embargo, gap_via_horizon)


@pytest.mark.unit
def test_config_signature_is_the_same_across_folds_of_a_spec() -> None:
    """`config_signature` é da configuração, não do fold: igual em todos os folds."""
    table = _identity_of(_command())

    by_version: dict[str, set[str]] = {}
    for (version, _fold), (_run_id, config_signature, _split) in table.items():
        by_version.setdefault(version, set()).add(config_signature)
    assert all(len(signatures) == 1 for signatures in by_version.values())
    # ...e diferente entre specs (a spec É a config dos baselines).
    all_signatures = [next(iter(s)) for s in by_version.values()]
    assert len(all_signatures) == len(set(all_signatures))
