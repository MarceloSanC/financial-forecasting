"""E2E do refresh de H3 sobre silver sintético, pelo grafo wirado (Stage 7.3, Task 31).

Reusa o mundo do e2e conformal da 7.2 (`test_conformal_refresh_end_to_end`): dataset,
realizado e silver da 6.4 com h em {1, 7}, folds inteiros `"0"`/`"1"` e o candidato
`tft_quantile` com as seeds 1 e 2; a cadeia r0 → r1 → r2 congelada e ancorada. Sobre ele,
este módulo grava o silver de atribuição sintético:

- `fact_permuted_predictions`: a identidade é a grade do candidato; cada (família, k)
  desloca a grade por um efeito por família e horizonte (a permutação piora a previsão);
- `fact_vsn_weights`: pesos por decisão para as features da partição sintética;
- a ablação: um `dim_run` e linhas de teste em `fs_all_ablation` por cohort de ablação
  (um `cohort_id` sintético por cenário), com o efeito LOCO por família e horizonte.

A r3 é a r2 + emenda + `[h3]` (o `h3_block()` sintético com K_p = 2 e as seeds 1 e 2),
com `cohort_id` da ablação e `partition_hash` por cenário. Nenhum teste lê o cohort real.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.composition_root import ApplicationDependencies, wire_dependencies
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    ScorecardResult,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_H3_IMPORTANCE,
    GOLD_H3_READING,
    GOLD_H3_SHARES,
    GOLD_H3_VSN,
    GOLD_SCHEMAS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldGenerationCorruptError,
    GoldPartition,
    RefreshGoldResult,
    RefreshStatus,
    Row,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    RefreshGold,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
    LOCO_REFERENCE_MODEL,
    loco_model_of,
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
    _ASSET,
    _N_SESSIONS,
    _SILVER,
    _plan_payload,
    _session,
    _write_dataset,
)
from tests.integration.features.evaluation.test_conformal_refresh_end_to_end import (
    _COHORT,
    _MIDDLE,
    _TEST_FIRST,
    _grids,
    _write_silver,
)
from tests.integration.features.evaluation.test_profiles_end_to_end import _freeze
from tests.unit.features.evaluation._conformal_parameters import conformal_block
from tests.unit.features.evaluation._h3_parameters import SYNTHETIC_PARTITION, h3_block
from tests.unit.features.evaluation._preregistration_payload import (
    R1_AMENDMENT,
    R2_AMENDMENT,
    R3_AMENDMENT,
    with_leaf,
)
from tests.unit.features.evaluation._profile_parameters import profile_block

pytestmark = pytest.mark.integration

_HORIZONS = (1, 7)
_SEEDS = (1, 2)
_FOLDS = ("0", "1")
_ABLATION_FS = "fs_all_ablation"
_H3_TABLES = (GOLD_H3_IMPORTANCE.name, GOLD_H3_SHARES.name, GOLD_H3_READING.name, GOLD_H3_VSN.name)
_VARIABLES = {
    **{f: family for family, features in SYNTHETIC_PARTITION.items() for f in features},
    "relative_time_idx": "none",
}
Effect = Mapping[tuple[str, int], float]  # (família, h) → deslocamento da grade

# A sentimento pesa mais em h+7 que em h+1; as outras, igual nos dois horizontes.
_SUSTAINED: Effect = {
    **{(f, h): 0.01 for f in H3_FAMILIES for h in _HORIZONS},
    ("sentiment", 1): 0.002,
    ("sentiment", 7): 0.03,
}
_OPPOSITE: Effect = {
    **_SUSTAINED,
    ("sentiment", 1): 0.03,
    ("sentiment", 7): 0.002,
}
_NULL: Effect = {
    (f, h): shift
    for f, shift in zip(H3_FAMILIES, (0.008, 0.01, 0.012, 0.014), strict=True)
    for h in _HORIZONS
}


# --- silver de atribuição ----------------------------------------------------------------


def _fold_of(decision: int) -> str:
    return "0" if decision < _MIDDLE else "1"


def _test_points() -> list[tuple[int, int]]:
    return [(h, d) for h in _HORIZONS for d in range(_TEST_FIRST, _N_SESSIONS - h)]


def _shifted(grid: list[float], shift: float) -> list[float]:
    return [value + shift for value in grid]


def _write_attribution(
    deps: ApplicationDependencies, plan: Preregistration, effect: Effect, partition_hash: str
) -> None:
    """Permutadas e VSN de cada run do candidato (efeito por família e horizonte)."""
    sweep = plan.cohort.cohort_id
    permuted: list[dict[str, object]] = []
    vsn: list[dict[str, object]] = []
    for seed in _SEEDS:
        for horizon, decision in _test_points():
            run_id = f"{sweep}-{plan.candidate}-s{seed}-{_fold_of(decision)}"
            grid = _grids(plan, plan.candidate, seed, horizon, decision)[1]
            labels = [("none", 0, 0.0)] + [
                (f, k, effect[(f, horizon)] * (1 + 0.1 * k)) for f in H3_FAMILIES for k in (1, 2)
            ]
            for family, k, shift in labels:
                for level, value in zip(plan.quantile_levels, _shifted(grid, shift), strict=True):
                    permuted.append(
                        {
                            "schema_version": 1,
                            "run_id": run_id,
                            "model_version": plan.candidate,
                            "asset": _ASSET,
                            "feature_set_name": "fs-core",
                            "permuted_family": family,
                            "permutation_index": k,
                            "permutation_seed": 130,
                            "permutation_algorithm": "fisher_yates_random_random_v1",
                            "partition_hash": partition_hash,
                            "horizon": horizon,
                            "decision_idx": decision,
                            "timestamp_utc": _session(decision),
                            "target_timestamp_utc": _session(decision + horizon),
                            "quantile_level": level,
                            "value_raw": value,
                            "value_guardrail": value,
                            "guardrail_applied": 0,
                            "year": int(_session(decision)[:4]),
                        }
                    )
        decisions = sorted({d for _, d in _test_points()})
        for decision in decisions:
            share = 1.0 / len(_VARIABLES)
            vsn.extend(
                {
                    "schema_version": 1,
                    "run_id": f"{sweep}-{plan.candidate}-s{seed}-{_fold_of(decision)}",
                    "model_version": plan.candidate,
                    "asset": _ASSET,
                    "feature_set_name": "fs-core",
                    "decision_idx": decision,
                    "timestamp_utc": _session(decision),
                    "variable": variable,
                    "family": family,
                    "weight": share * (1 + 0.01 * ((decision + seed) % 3)) / 1.01,
                    "year": int(_session(decision)[:4]),
                }
                for variable, family in _VARIABLES.items()
            )
    deps.analytics_repository.write(layer=_SILVER, table="fact_permuted_predictions", rows=permuted)
    deps.analytics_repository.write(layer=_SILVER, table="fact_vsn_weights", rows=vsn)


def _write_ablation(
    deps: ApplicationDependencies,
    plan: Preregistration,
    cohort_id: str,
    effect: Effect,
    *,
    skip: str | None = None,
) -> None:
    """O cohort de ablação `cohort_id`: a referência é o candidato; cada LOCO piora."""
    configurations = {LOCO_REFERENCE_MODEL: None, **{loco_model_of(f): f for f in H3_FAMILIES}}
    runs: list[dict[str, object]] = []
    facts: list[dict[str, object]] = []
    for model, family in configurations.items():
        if model == skip:
            continue
        for seed in _SEEDS:
            for fold in _FOLDS:
                runs.append(
                    {
                        "schema_version": 1,
                        "run_id": f"{cohort_id}-{model}-s{seed}-{fold}",
                        "asset": _ASSET,
                        "parent_sweep_id": cohort_id,
                        "feature_set_name": _ABLATION_FS,
                        "config_signature": f"sig-{model}",
                        "split_fingerprint": "split-e2e",
                        "fold": fold,
                        "seed": seed,
                        "model_version": model,
                    }
                )
            for horizon, decision in _test_points():
                grid = _grids(plan, plan.candidate, seed, horizon, decision)[1]
                shift = 0.0 if family is None else effect[(family, horizon)]
                for level, value in zip(plan.quantile_levels, _shifted(grid, shift), strict=True):
                    facts.append(
                        {
                            "schema_version": 1,
                            "run_id": f"{cohort_id}-{model}-s{seed}-{_fold_of(decision)}",
                            "model_version": model,
                            "asset": _ASSET,
                            "feature_set_name": _ABLATION_FS,
                            "split": "test",
                            "horizon": horizon,
                            "decision_idx": decision,
                            "timestamp_utc": _session(decision),
                            "target_timestamp_utc": _session(decision + horizon),
                            "quantile_level": level,
                            "value_raw": value,
                            "value_guardrail": value,
                            "guardrail_applied": 0,
                            "year": int(_session(decision)[:4]),
                        }
                    )
    deps.analytics_repository.write(layer=_SILVER, table="dim_run", rows=runs)
    deps.analytics_repository.write(layer=_SILVER, table="fact_oos_predictions", rows=facts)


# --- mundo e planos ------------------------------------------------------------------------


@dataclass(frozen=True)
class _World:
    deps: ApplicationDependencies
    plans: tuple[Preregistration, ...]  # r0, r1, r2
    references: tuple[str, ...]
    r2_payload: dict[str, object]


@dataclass(frozen=True)
class _Run:
    refresh: RefreshGoldResult
    generation: GoldGeneration


def _world(root: Path, *, drop: tuple[int, int, int] | None = None) -> _World:
    settings = Settings(
        _env_file=None,
        data_root=root / "data",
        repo_root=root,
        artifacts_root=root / "art",
        mlflow_tracking_uri=f"sqlite:///{root}/mlruns.db",
    )
    deps = wire_dependencies(settings=settings)
    fingerprint = _write_dataset(settings.data_root)
    r0_payload = with_leaf(_plan_payload("h3_plan", _COHORT, fingerprint), "horizons", [1, 7])
    r0, r0_reference = _freeze(root, r0_payload, 0)
    r1_payload = {**r0_payload, **R1_AMENDMENT, "amends": r0_reference}
    r1_payload["profile_parameters"] = profile_block()
    r1, r1_reference = _freeze(root, r1_payload, 1)
    r2_payload = {**r1_payload, **R2_AMENDMENT, "amends": r1_reference}
    r2_payload["conformal"] = conformal_block()
    r2, r2_reference = _freeze(root, r2_payload, 2)
    _write_silver(deps, r0, drop=drop)
    return _World(deps, (r0, r1, r2), (r0_reference, r1_reference, r2_reference), r2_payload)


def _r3(world: _World, *, cohort_id: str, partition_hash: str | None = None) -> tuple[Any, str]:
    block: dict[str, Any] = copy.deepcopy(h3_block())
    block["k_p"] = 2
    block["ablation"]["seeds"] = list(_SEEDS)
    block["ablation"]["cohort_id"] = cohort_id
    if partition_hash is not None:
        block["partition"]["partition_hash"] = partition_hash
    payload = {**world.r2_payload, **R3_AMENDMENT, "amends": world.references[2], "h3": block}
    plan = Preregistration.from_mapping(payload)
    reference = plan.reference(
        PreregistrationHash.compute(hasher=CanonicalJsonHasher(), payload=plan.as_payload())
    )
    return plan, reference


def _refresh(world: _World, plan: Preregistration, reference: str) -> _Run:
    refresh = world.deps.refresh_gold(refresh_command_from(plan, reference))
    generation = world.deps.refresh_gold._gold_store.read_generation(  # type: ignore[attr-defined]
        partition=GoldPartition(_ASSET, _COHORT)
    )
    return _Run(refresh=refresh, generation=generation)


def _rows(run: _Run, name: str) -> tuple[Row, ...]:
    return run.generation.table(GOLD_SCHEMAS[name]).rows


def _reading(run: _Run) -> Row:
    [row] = _rows(run, GOLD_H3_READING.name)
    return row


_HASH = h3_block()["partition"]["partition_hash"]  # type: ignore[index]


@dataclass(frozen=True)
class _Scenario:
    world: _World
    r2: _Run
    sustained: _Run
    opposite: _Run
    undefined: _Run
    mismatch: _Run
    r2_scorecard: ScorecardResult
    r3_scorecard: ScorecardResult


@pytest.fixture(scope="module")
def scenario(tmp_path_factory: pytest.TempPathFactory) -> _Scenario:
    root = tmp_path_factory.mktemp("e2e-h3")
    world = _world(root)
    r2_plan = world.plans[2]
    _write_attribution(world.deps, r2_plan, _SUSTAINED, str(_HASH))
    _write_ablation(world.deps, r2_plan, "ablation-sustained", _SUSTAINED)
    _write_ablation(world.deps, r2_plan, "ablation-opposite", _OPPOSITE)
    _write_ablation(
        world.deps, r2_plan, "ablation-missing", _SUSTAINED, skip=loco_model_of("fundamental")
    )
    r2 = _refresh(world, r2_plan, world.references[2])
    r2_scorecard = _scorecard(world, r2_plan, world.references[2], 2)
    plan, reference = _r3(world, cohort_id="ablation-sustained")
    _freeze(root, {**plan.as_payload()}, 3)
    sustained = _refresh(world, plan, reference)
    r3_scorecard = _scorecard(world, plan, reference, 3)
    opposite = _refresh(world, *_r3(world, cohort_id="ablation-opposite"))
    undefined = _refresh(world, *_r3(world, cohort_id="ablation-missing"))
    mismatch = _refresh(
        world, *_r3(world, cohort_id="ablation-sustained", partition_hash="d4" * 32)
    )
    return _Scenario(
        world, r2, sustained, opposite, undefined, mismatch, r2_scorecard, r3_scorecard
    )


def _scorecard(
    world: _World, plan: Preregistration, reference: str, revision: int
) -> ScorecardResult:
    return world.deps.build_confirmatory_scorecard(
        BuildConfirmatoryScorecardCommand(
            name=plan.name, revision=revision, preregistration_ref=reference
        )
    )


# --- testes -----------------------------------------------------------------------------


def test_known_effect_family_is_sustained(scenario: _Scenario) -> None:
    reading = _reading(scenario.sustained)
    assert reading["status"] == "ok", reading
    assert reading["sustained"] is True
    assert "sentiment" in str(reading["agreeing_families"]).split(",")
    for method in ("permutation", "loco"):
        [share] = [
            r
            for r in _rows(scenario.sustained, GOLD_H3_SHARES.name)
            if (r["method"], r["family"]) == (method, "sentiment")
        ]
        assert share["delta"] > 0, share
        assert share["excludes_zero"] is True, share


def test_null_case_both_methods_ok_and_not_sustained(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    world = _world(tmp_path_factory.mktemp("e2e-h3-null"))
    _write_attribution(world.deps, world.plans[2], _NULL, str(_HASH))
    _write_ablation(world.deps, world.plans[2], "ablation-null", _NULL)
    run = _refresh(world, *_r3(world, cohort_id="ablation-null"))
    reading = _reading(run)
    shares = _rows(run, GOLD_H3_SHARES.name)
    assert {r["method_status"] for r in shares} == {"ok"}
    assert reading["sustained"] is False
    assert reading["status"] == "ok"


def test_opposite_sides_between_methods_not_sustained_ok(scenario: _Scenario) -> None:
    reading = _reading(scenario.opposite)
    assert reading["status"] == "ok"
    assert reading["sustained"] is False
    assert reading["agreeing_families"] == ""
    sides = {
        r["method"]: r["side"]
        for r in _rows(scenario.opposite, GOLD_H3_SHARES.name)
        if r["family"] == "sentiment"
    }
    assert sides == {"permutation": 1, "loco": -1}


def test_undefined_method_gives_undefined_reading_with_reason(scenario: _Scenario) -> None:
    reading = _reading(scenario.undefined)
    assert reading["status"] == "undefined"
    assert reading["sustained"] is False
    assert "loco:" in str(reading["reason"])
    assert "has no run" in str(reading["reason"])
    loco = [r for r in _rows(scenario.undefined, GOLD_H3_SHARES.name) if r["method"] == "loco"]
    assert {r["method_status"] for r in loco} == {"undefined"}


def test_partition_hash_mismatch_makes_permutation_undefined(scenario: _Scenario) -> None:
    shares = _rows(scenario.mismatch, GOLD_H3_SHARES.name)
    permutation = [r for r in shares if r["method"] == "permutation"]
    assert {r["method_status"] for r in permutation} == {"undefined"}
    assert all("(I17)" in str(r["method_reason"]) for r in permutation)
    assert _reading(scenario.mismatch)["status"] == "undefined"


def test_completed_generation_has_the_four_tables_and_h3_in_manifest(
    scenario: _Scenario,
) -> None:
    run = scenario.sustained
    assert run.refresh.status is RefreshStatus.COMPLETED
    assert all(run.refresh.rows_by_table[name] > 0 for name in _H3_TABLES)
    parameters = run.generation.manifest.as_mapping()["parameters"]
    h3 = parameters["h3_parameters"]  # type: ignore[index]
    assert h3["ablation"]["cohort_id"] == "ablation-sustained"  # type: ignore[index]


def test_shares_level_is_0_9875(scenario: _Scenario) -> None:
    ok = [r for r in _rows(scenario.sustained, GOLD_H3_SHARES.name) if r["status"] == "ok"]
    assert ok
    assert {r["level"] for r in ok} == {0.9875}


def test_r2_plan_writes_empty_h3_tables(scenario: _Scenario) -> None:
    run = scenario.r2
    assert run.refresh.status is RefreshStatus.COMPLETED
    assert all(run.refresh.rows_by_table[name] == 0 for name in _H3_TABLES)
    assert run.generation.manifest.parameters.h3_parameters is None


def test_blocked_generation_has_no_h3_tables(tmp_path_factory: pytest.TempPathFactory) -> None:
    world = _world(tmp_path_factory.mktemp("e2e-h3-blocked"), drop=(1, 1, _TEST_FIRST + 10))
    _write_attribution(world.deps, world.plans[2], _SUSTAINED, str(_HASH))
    _write_ablation(world.deps, world.plans[2], "ablation-blocked", _SUSTAINED)
    run = _refresh(world, *_r3(world, cohort_id="ablation-blocked"))
    assert run.refresh.status is RefreshStatus.BLOCKED
    assert all(run.refresh.rows_by_table.get(name, 0) == 0 for name in _H3_TABLES)


def _without_ref(rows: tuple[Row, ...]) -> list[dict[str, object]]:
    return [{k: v for k, v in row.items() if k != "preregistration_ref"} for row in rows]


def test_r2_and_r3_same_verdict_and_same_previous_tables(scenario: _Scenario) -> None:
    """I16: o bloco de H3 não toca no veredito nem nas tabelas da 6.4-7.2."""
    assert scenario.r3_scorecard.verdict == scenario.r2_scorecard.verdict
    for name in GOLD_SCHEMAS:
        if name in _H3_TABLES:
            continue
        assert _without_ref(_rows(scenario.sustained, name)) == _without_ref(
            _rows(scenario.r2, name)
        ), name


def test_manifest_before_this_stage_is_unreadable(scenario: _Scenario) -> None:
    """C10: um manifesto sem `h3_parameters` (anterior à 7.3) não lê."""
    generation = scenario.sustained.generation
    manifest = generation.manifest.as_mapping()
    parameters = {
        k: v
        for k, v in manifest["parameters"].items()  # type: ignore[union-attr]
        if k != "h3_parameters"
    }
    with pytest.raises(GoldGenerationCorruptError, match="h3_parameters"):
        GoldGeneration.from_stored(
            {**manifest, "parameters": parameters}, {}, partition=GoldPartition(_ASSET, _COHORT)
        )


def test_real_use_cases_through_the_composition_root(scenario: _Scenario) -> None:
    """O refresh do `wire_dependencies` é o `RefreshGold` real com os builders de H3."""
    refresh = scenario.world.deps.refresh_gold
    assert isinstance(refresh, RefreshGold)
    assert {f"gold_{name}" for name in refresh.build_order} >= set(_H3_TABLES)
    vsn = _rows(scenario.sustained, GOLD_H3_VSN.name)
    assert {r["name"] for r in vsn if r["kind"] == "family"} == set(H3_FAMILIES)
    importance = _rows(scenario.sustained, GOLD_H3_IMPORTANCE.name)
    seeds = {r["seed"] for r in importance if r["method"] == "permutation"}
    assert seeds == {None, *_SEEDS}
    ks = {r["permutation_index"] for r in importance if r["method"] == "permutation"}
    assert ks == {None, 1, 2}


def test_vsn_summary_ok_with_label_and_a_known_p50(scenario: _Scenario) -> None:
    """C8-4: a VSN sai `ok`, com o rótulo exato e o p50 da família price conhecido."""
    from financial_forecasting.features.evaluation.domain.services.family_contribution import (  # noqa: PLC0415
        linear_quantile,
    )

    rows = _rows(scenario.sustained, GOLD_H3_VSN.name)
    assert {r["status"] for r in rows} == {"ok"}
    assert {r["label"] for r in rows} == {
        "horizonte-invariante; descreve quanto o modelo usa cada família"
    }
    share = 1.0 / len(_VARIABLES)
    decisions = sorted({d for _, d in _test_points()})

    def weight(decision: int, seed: int) -> float:
        return share * (1 + 0.01 * ((decision + seed) % 3)) / 1.01

    members = [f for f, family in _VARIABLES.items() if family == "price"]
    sums = [
        sum(sum(weight(d, s) for s in _SEEDS) / len(_SEEDS) for _ in members) for d in decisions
    ]
    [price] = [r for r in rows if (r["kind"], r["name"]) == ("family", "price")]
    assert price["p50"] == pytest.approx(linear_quantile(sums, 0.5))
    assert price["n_decisions"] == len(decisions)
