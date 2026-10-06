"""E2E dos perfis de séries novas sobre silver sintético, pelo grafo wirado (Stage 6.6 Task 20).

Reusa o silver, o dataset e o congelamento do e2e da 6.5
(`test_build_confirmatory_scorecard`): mesmo realizado e mesmos quantis por construção,
aqui com h ∈ {1, 7}, 2 folds e 2 seeds do candidato. O plano é gravado como cadeia
r0 → r1 (a r1 = r0 + emenda cega + `[profile_parameters]`), as duas revisões ancoradas.

Sequência: refresh pelo r0 → seis tabelas do I9 vazias, Monte Carlo e d_t cheios;
scorecard r0 → sete perfis `not_frozen_in_revision`. Refresh pela r1 → as oito tabelas
cheias, `profile_error_units == 0`, toda unidade `computed`; scorecard r1 → o perfil
completo, tudo `built` exceto o diagrama de nitidez.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_forecasting.composition_root import ApplicationDependencies, wire_dependencies
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    ProfileState,
    ScorecardResult,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CHRISTOFFERSEN_MONTE_CARLO,
    GOLD_DIFFERENTIAL_ACF,
    GOLD_DIFFERENTIAL_BREAKS,
    GOLD_DM_PROFILES,
    GOLD_DM_SEED_FRACTION,
    GOLD_LOSS_DIFFERENTIALS,
    GOLD_MCS_BLOCK_SENSITIVITY,
    GOLD_PARTIAL_DEGENERACY,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldPartition,
    RefreshGoldResult,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.integration.features.evaluation.test_build_confirmatory_scorecard import (
    _ANCHORED_AT,
    _ASSET,
    _FIRST_DECISION,
    _N_SESSIONS,
    _SILVER,
    _plan_payload,
    _quantiles,
    _seeds,
    _session,
    _write_dataset,
)
from tests.unit.features.evaluation._preregistration_payload import (
    R1_AMENDMENT,
    to_toml,
    with_leaf,
)
from tests.unit.features.evaluation._profile_parameters import profile_block

pytestmark = pytest.mark.integration

_COHORT = "e2e-profiles"
_HORIZONS = (1, 7)
_SEVEN = frozenset(
    {
        "mcs_block_h",
        "mcs_block_sqrt_t",
        "dm_per_fold",
        "dm_per_seed",
        "dm_per_tau",
        "dm_differential_stationarity",
        "partial_degeneracy_per_pair",
    }
)
_RULE_TABLES = (  # as seis do I9: vazias sem `[profile_parameters]`
    GOLD_DM_PROFILES.name,
    GOLD_DM_SEED_FRACTION.name,
    GOLD_MCS_BLOCK_SENSITIVITY.name,
    GOLD_PARTIAL_DEGENERACY.name,
    GOLD_DIFFERENTIAL_ACF.name,
    GOLD_DIFFERENTIAL_BREAKS.name,
)
_ALWAYS = (GOLD_CHRISTOFFERSEN_MONTE_CARLO.name, GOLD_LOSS_DIFFERENTIALS.name)
_STATUS_TABLES = (
    GOLD_DM_PROFILES,
    GOLD_MCS_BLOCK_SENSITIVITY,
    GOLD_CHRISTOFFERSEN_MONTE_CARLO,
    GOLD_PARTIAL_DEGENERACY,
    GOLD_DIFFERENTIAL_BREAKS,
)


def _write_silver(deps: ApplicationDependencies, prereg: Preregistration) -> None:
    """Silver do e2e da 6.5 nos horizontes do plano (2 folds, seeds do plano)."""
    sweep = prereg.cohort.cohort_id
    middle = (_FIRST_DECISION + _N_SESSIONS) // 2
    runs: list[dict[str, object]] = []
    facts: list[dict[str, object]] = []
    for model in prereg.models:
        for seed in _seeds(prereg, model, ()):
            for fold in ("f0", "f1"):
                runs.append(
                    {
                        "schema_version": 1,
                        "run_id": f"{sweep}-{model}-s{seed}-{fold}",
                        "asset": _ASSET,
                        "parent_sweep_id": sweep,
                        "feature_set_name": "fs-core",
                        "config_signature": f"sig-{model}",
                        "split_fingerprint": "split-e2e",
                        "fold": fold,
                        "seed": seed,
                        "model_version": model,
                    }
                )
            for horizon in prereg.horizons:
                for decision in range(_FIRST_DECISION, _N_SESSIONS - horizon):
                    fold = "f0" if decision < middle else "f1"
                    target = decision + horizon
                    values = _quantiles(model, seed, horizon, target)
                    for level, value in zip(prereg.quantile_levels, values, strict=True):
                        facts.append(
                            {
                                "schema_version": 1,
                                "run_id": f"{sweep}-{model}-s{seed}-{fold}",
                                "model_version": model,
                                "asset": _ASSET,
                                "feature_set_name": "fs-core",
                                "split": "test",
                                "horizon": horizon,
                                "decision_idx": decision,
                                "timestamp_utc": _session(decision),
                                "target_timestamp_utc": _session(target),
                                "quantile_level": level,
                                "value_raw": value,
                                "value_guardrail": value,
                                "guardrail_applied": 0,
                                "year": int(_session(target)[:4]),
                            }
                        )
    deps.analytics_repository.write(layer=_SILVER, table="dim_run", rows=runs)
    deps.analytics_repository.write(layer=_SILVER, table="fact_oos_predictions", rows=facts)


def _freeze(root: Path, payload: dict[str, object], revision: int) -> tuple[Preregistration, str]:
    plan = Preregistration.from_mapping(payload)
    reference = plan.reference(
        PreregistrationHash.compute(hasher=CanonicalJsonHasher(), payload=plan.as_payload())
    )
    folder = root / "config" / "preregistration"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{plan.name}-r{revision}.toml").write_text(to_toml(payload), encoding="utf-8")
    anchor = {
        "tag": f"preregistration/{reference}",
        "commit": "0123456789abcdef0123456789abcdef01234567",
        "comment_url": "https://github.com/example/repo/issues/1#issuecomment-1",
        "anchored_at": _ANCHORED_AT,
    }
    (folder / f"{plan.name}-r{revision}.anchor.toml").write_text(to_toml(anchor), encoding="utf-8")
    return plan, reference


@dataclass(frozen=True)
class _Run:
    refresh: RefreshGoldResult
    generation: GoldGeneration
    scorecard: ScorecardResult


@dataclass(frozen=True)
class _Scenario:
    r0: _Run
    r1: _Run


def _run(
    deps: ApplicationDependencies, plan: Preregistration, reference: str, revision: int
) -> _Run:
    refresh = deps.refresh_gold(refresh_command_from(plan, reference))
    generation = deps.refresh_gold._gold_store.read_generation(  # type: ignore[attr-defined]
        partition=GoldPartition(_ASSET, _COHORT)
    )
    scorecard = deps.build_confirmatory_scorecard(
        BuildConfirmatoryScorecardCommand(
            name=plan.name, revision=revision, preregistration_ref=reference
        )
    )
    return _Run(refresh=refresh, generation=generation, scorecard=scorecard)


@pytest.fixture(scope="module")
def scenario(tmp_path_factory: pytest.TempPathFactory) -> _Scenario:
    tmp = tmp_path_factory.mktemp("e2e-profiles")
    settings = Settings(
        _env_file=None,
        data_root=tmp / "data",
        repo_root=tmp,
        artifacts_root=tmp / "art",
        mlflow_tracking_uri=f"sqlite:///{tmp}/mlruns.db",
    )
    deps = wire_dependencies(settings=settings)
    fingerprint = _write_dataset(settings.data_root)
    r0_payload = with_leaf(_plan_payload("profiles_plan", _COHORT, fingerprint), "horizons", [1, 7])
    r0, r0_reference = _freeze(tmp, r0_payload, 0)
    r1_payload = {
        **r0_payload,
        **R1_AMENDMENT,
        "amends": r0_reference,
        "profile_parameters": profile_block(),
    }
    r1, r1_reference = _freeze(tmp, r1_payload, 1)
    _write_silver(deps, r0)
    first = _run(deps, r0, r0_reference, 0)
    second = _run(deps, r1, r1_reference, 1)
    return _Scenario(r0=first, r1=second)


def test_r0_writes_only_monte_carlo_and_differentials(scenario: _Scenario) -> None:
    run = scenario.r0
    assert run.refresh.status is RefreshStatus.COMPLETED
    assert run.refresh.profile_error_units == 0
    rows = run.refresh.rows_by_table
    assert all(rows[name] == 0 for name in _RULE_TABLES)
    assert all(rows[name] > 0 for name in _ALWAYS)


def test_r0_scorecard_states(scenario: _Scenario) -> None:
    states = dict(scenario.r0.scorecard.profile.profile_states)
    assert {p for p, s in states.items() if s is ProfileState.NOT_FROZEN_IN_REVISION} == _SEVEN
    assert states["christoffersen_monte_carlo_h1"] is ProfileState.BUILT


def test_r1_writes_every_profile_table_with_no_error(scenario: _Scenario) -> None:
    run = scenario.r1
    assert run.refresh.status is RefreshStatus.COMPLETED
    assert run.refresh.profile_error_units == 0
    assert all(run.refresh.rows_by_table[name] > 0 for name in (*_RULE_TABLES, *_ALWAYS))
    for schema in _STATUS_TABLES:
        statuses = {row["status"] for row in run.generation.table(schema).rows}
        assert statuses == {"computed"}, (schema.name, statuses)
    blocks = run.generation.table(GOLD_MCS_BLOCK_SENSITIVITY).rows
    assert {(row["horizon"], row["block_rule"]) for row in blocks} == {
        (h, rule) for h in _HORIZONS for rule in ("h", "sqrt_T")
    }


def test_r1_scorecard_has_the_full_profile(scenario: _Scenario) -> None:
    result = scenario.r1.scorecard
    assert result.revision_chain[-1] == result.preregistration_ref
    assert len(result.revision_chain) == 2  # noqa: PLR2004
    states = dict(result.profile.profile_states)
    assert {p for p, s in states.items() if s is not ProfileState.BUILT} == {"sharpness_diagram"}
    for horizon in result.profile.horizons:
        assert horizon.dm_subsets
        assert horizon.dm_seed_fractions
        assert horizon.mcs_block_sensitivity
        assert horizon.partial_degeneracy
        assert horizon.stationarity
        assert all(row.acf for row in horizon.stationarity)
        assert bool(horizon.monte_carlo) is (horizon.horizon == 1)
    assert {row.dimension for h in result.profile.horizons for row in h.dm_subsets} == {
        "fold",
        "seed",
        "tau",
    }


def test_profile_rules_do_not_change_the_verdict(scenario: _Scenario) -> None:
    """I12 de ponta a ponta: o veredito pela r1 é o mesmo do r0 (só os perfis mudam)."""
    assert scenario.r1.scorecard.verdict == scenario.r0.scorecard.verdict
