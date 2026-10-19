"""Unit da `AttributionAssembly` e das reduções por run (Stage 7.3, Task 24).

Concept 7.3 §4, I7, I10, I11, I17, I19; C9; ADR 7.3.0001 item 1. Dois tipos de entrada:
reduções construídas à mão (valores que se conferem de cabeça) e o cohort sintético da
fábrica do gold com os registros de atribuição (`with_permuted`, `with_ablation`).
"""

from __future__ import annotations

import copy
import dataclasses
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import pytest

from financial_forecasting.features.evaluation.domain.services.attribution_assembly import (
    AttributionAssembly,
    AttributionAssemblyResult,
    UndefinedRunReduction,
    merge_ablation_run,
    reduce_ablation_run,
    reduce_permuted_run,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import pinball_loss
from financial_forecasting.features.evaluation.domain.value_objects.ablation_run_losses import (
    AblationRunLosses,
    AblationRunPart,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AlignmentFinding,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.family_loss_differentials import (  # noqa: E501
    FamilyLossDifferentials,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
    H3Parameters,
    loco_model_of,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_forecast_record import (  # noqa: E501
    PermutedForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_run_losses import (
    PermutedRunLosses,
)
from tests.unit.features.evaluation._h3_parameters import h3_block
from tests.unit.features.evaluation.gold._cohort_factory import (
    GOLD_LEVELS,
    PARTITION_HASH,
    Cohort,
    make_cohort,
    session,
    with_ablation,
    with_permuted,
)

pytestmark = pytest.mark.unit

_HORIZONS = (1, 7)
_SEEDS = (1, 2)
_T = (session(10), session(11), session(12))
_REFERENCE = "tft_quantile_loco_full"


def _params(**changes: Any) -> H3Parameters:  # noqa: ANN401
    block: dict[str, Any] = copy.deepcopy(h3_block())
    block["k_p"] = 2
    block["ablation"]["seeds"] = list(_SEEDS)
    block.update(changes)
    return H3Parameters.from_mapping(block)


# --- entradas construídas à mão --------------------------------------------------------


def _candidate_run(seed: int) -> CohortRun:
    return CohortRun(
        run_id=f"tft-s{seed}-0",
        model="tft",
        seed=seed,
        fold="0",
        feature_set_name="fs",
        config_signature="sig-tft",
    )


def _permuted(seed: int, identity: Sequence[float], price: Sequence[Sequence[float]]) -> Any:  # noqa: ANN401
    """Identidade igual nos dois horizontes; `price[k-1]` por k, as outras famílias = id."""
    permuted: dict[tuple[str, int, int], tuple[float, ...]] = {}
    for family in H3_FAMILIES:
        for k in (1, 2):
            values = tuple(price[k - 1]) if family == "price" else tuple(identity)
            for h in _HORIZONS:
                permuted[(family, k, h)] = values
    return PermutedRunLosses(
        run_id=f"tft-s{seed}-0",
        seed=seed,
        fold_index=0,
        permutation_seed=130,
        permutation_algorithm="fisher_yates_random_random_v1",
        partition_hash=PARTITION_HASH,
        decision_timestamps=_T,
        identity={h: tuple(identity) for h in _HORIZONS},
        permuted=permuted,
    )


def _hand_permuted() -> list[PermutedRunLosses]:
    return [
        _permuted(1, (1.0, 2.0, 3.0), ((2.0, 2.0, 5.0), (3.0, 4.0, 3.0))),
        _permuted(2, (2.0, 2.0, 2.0), ((2.0, 3.0, 2.0), (4.0, 2.0, 2.0))),
    ]


def _ablation_run(model: str, seed: int) -> CohortRun:
    return CohortRun(
        run_id=f"{model}-s{seed}-0",
        model=model,
        seed=seed,
        fold="0",
        feature_set_name="fs_all_ablation",
        config_signature=f"sig-{model}",
    )


def _hand_ablation() -> tuple[list[CohortRun], list[AblationRunLosses]]:
    values = {
        (_REFERENCE, 1): (1.0, 1.0, 1.0),
        (_REFERENCE, 2): (3.0, 3.0, 3.0),
        (loco_model_of("price"), 1): (2.0, 1.0, 1.0),
        (loco_model_of("price"), 2): (3.0, 5.0, 3.0),
    }
    runs, losses = [], []
    for model in (_REFERENCE, *(loco_model_of(f) for f in H3_FAMILIES)):
        for seed in _SEEDS:
            run = _ablation_run(model, seed)
            series = values.get((model, seed), values[(_REFERENCE, seed)])
            runs.append(run)
            losses.append(
                AblationRunLosses(
                    run_id=run.run_id,
                    model_version=model,
                    seed=seed,
                    fold_index=0,
                    decision_timestamps=_T,
                    losses={h: series for h in _HORIZONS},
                )
            )
    return runs, losses


def _assemble(
    *,
    permuted: Sequence[Any] | None = None,
    candidate_runs: Sequence[CohortRun] | None = None,
    ablation: tuple[Sequence[CohortRun], Sequence[Any]] | None = None,
    parameters: H3Parameters | None = None,
    seeds: tuple[int, ...] = _SEEDS,
) -> AttributionAssemblyResult:
    ablation_runs, ablation_losses = ablation if ablation is not None else _hand_ablation()
    return AttributionAssembly.assemble(
        candidate_runs=(
            [_candidate_run(s) for s in _SEEDS] if candidate_runs is None else candidate_runs
        ),
        permuted=_hand_permuted() if permuted is None else permuted,
        ablation_runs=ablation_runs,
        ablation_losses=ablation_losses,
        parameters=parameters or _params(),
        candidate="tft",
        candidate_seeds=seeds,
        horizons=_HORIZONS,
    )


def _defined(result: AttributionAssemblyResult) -> tuple[Any, Any]:
    assert result.permutation is not None, result.permutation_reason
    assert result.ablation is not None, result.ablation_reason
    return result.permutation, result.ablation


def test_permutation_d_t_equals_the_hand_computed_value() -> None:
    """2 seeds, K_p = 2, 3 decisões: média nas seeds da média nas k de L^perm - L^id."""
    permutation, _ = _defined(_assemble())

    # seed 1: gaps k1 (1, 0, 2), k2 (2, 2, 0) → média em k (1.5, 1, 1)
    # seed 2: gaps k1 (0, 1, 0), k2 (2, 0, 0) → média em k (1, 0.5, 0)
    for h in _HORIZONS:
        assert permutation.differentials[("price", h)] == pytest.approx((1.25, 0.75, 0.5))
        for family in ("technical", "sentiment", "fundamental"):
            assert permutation.differentials[(family, h)] == (0.0, 0.0, 0.0)
    assert permutation.decision_timestamps == _T
    assert permutation.method == "permutation"


def test_loco_d_t_is_seed_mean_minus_seed_mean() -> None:
    """O valor de d_t do LOCO, à mão.

    Não distingue a média das diferenças por seed pareada: com as mesmas seeds em toda
    configuração (exigido pela montagem, I11) as duas fórmulas são iguais — mutante
    equivalente, registrado na §7 do technical (C6-5).
    """
    _, ablation = _defined(_assemble())

    # média nas seeds de L^{-price} (2.5, 3, 2) - média nas seeds de L^{full} (2, 2, 2)
    assert ablation.differentials[("price", 1)] == pytest.approx((0.5, 1.0, 0.0))
    assert ablation.differentials[("sentiment", 7)] == (0.0, 0.0, 0.0)
    assert ablation.method == "loco"
    assert dict(ablation.permutation_importances) == {}


def test_seed_and_k_profiles() -> None:
    permutation, ablation = _defined(_assemble())

    assert permutation.seed_importances[("price", 1, 1)] == pytest.approx(3.5 / 3)
    assert permutation.seed_importances[("price", 1, 2)] == pytest.approx(0.5)
    assert permutation.permutation_importances[("price", 7, 1)] == pytest.approx(2 / 3)
    assert permutation.permutation_importances[("price", 7, 2)] == pytest.approx(1.0)
    assert permutation.seed_importances[("technical", 1, 2)] == 0.0
    assert ablation.seed_importances[("price", 1, 1)] == pytest.approx(1 / 3)
    assert ablation.seed_importances[("price", 1, 2)] == pytest.approx(2 / 3)
    assert len(permutation.seed_importances) == 4 * 2 * 2  # f x h x s
    assert len(permutation.permutation_importances) == 4 * 2 * 2  # f x h x k


def test_decision_sets_differ_between_methods_is_undefined() -> None:
    runs, losses = _hand_ablation()
    shifted = [
        dataclasses.replace(loss, decision_timestamps=(session(10), session(11), session(13)))
        for loss in losses
    ]

    result = _assemble(ablation=(runs, shifted))

    assert result.permutation is None
    assert result.ablation is None
    assert result.permutation_reason == result.ablation_reason
    assert "decision sets differ" in str(result.permutation_reason)


def _drop_key(reduction: PermutedRunLosses, key: tuple[str, int, int]) -> PermutedRunLosses:
    return dataclasses.replace(
        reduction, permuted={k: v for k, v in reduction.permuted.items() if k != key}
    )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("seed", "seed 2 of the candidate has no attribution run"),
        ("run", "run tft-s2-0 has no attribution reduction"),
        ("k", "misses (family, k, h) ['price', 2, 1]"),
        ("family", "misses (family, k, h) ['sentiment', 1, 7]"),
        ("configuration", "configuration tft_quantile_loco_minus_fundamental seed 1"),
    ],
)
def test_missing_seed_k_family_or_configuration_is_undefined(case: str, message: str) -> None:
    permuted = _hand_permuted()
    candidate_runs = [_candidate_run(s) for s in _SEEDS]
    runs, losses = _hand_ablation()
    if case == "seed":
        permuted, candidate_runs = permuted[:1], candidate_runs[:1]
    elif case == "run":
        permuted = permuted[:1]
    elif case == "k":
        permuted[0] = _drop_key(permuted[0], ("price", 2, 1))
    elif case == "family":
        permuted[1] = _drop_key(permuted[1], ("sentiment", 1, 7))
    else:
        keep = [r.model != loco_model_of("fundamental") or r.seed != 1 for r in runs]
        runs = [r for r, k in zip(runs, keep, strict=True) if k]
        losses = [x for x, k in zip(losses, keep, strict=True) if k]

    result = _assemble(permuted=permuted, candidate_runs=candidate_runs, ablation=(runs, losses))

    reason = result.ablation_reason if case == "configuration" else result.permutation_reason
    assert reason is not None and message in reason, reason
    defined = result.permutation if case == "configuration" else result.ablation
    assert defined is not None  # o outro método não é afetado


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("permutation_seed", 131, "permutation_seed 131 != 130 of [h3] (C9)"),
        ("permutation_algorithm", "random_shuffle_v1", "permutation_algorithm 'random_shuffle_v1'"),
    ],
)
def test_wrong_permutation_seed_or_algorithm_is_undefined(
    field: str, value: object, message: str
) -> None:
    permuted = _hand_permuted()
    permuted[1] = dataclasses.replace(permuted[1], **{field: value})

    result = _assemble(permuted=permuted)

    assert result.permutation is None
    assert message in str(result.permutation_reason)


def test_partition_hash_mismatch_is_undefined() -> None:
    """I17: o hash das linhas é comparado com o literal de `[h3.partition]`."""
    block = copy.deepcopy(h3_block())
    block["partition"]["partition_hash"] = "d4" * 32  # type: ignore[index]
    block["k_p"] = 2
    block["ablation"]["seeds"] = list(_SEEDS)  # type: ignore[index]

    result = _assemble(parameters=H3Parameters.from_mapping(block))

    assert result.permutation is None
    assert "partition_hash a1a1a1a1a1a1 != d4d4d4d4d4d4 of [h3.partition] (I17)" in str(
        result.permutation_reason
    )
    assert result.ablation is not None


def test_raw_construction_of_family_loss_differentials_refused() -> None:
    valid, _ = _defined(_assemble())
    cases: list[tuple[dict[str, Any], str]] = [
        ({"differentials": {**valid.differentials, ("price", 1): (0.1, 0.2)}}, "has 2 losses"),
        ({"horizons": (1, 30)}, "horizons must be"),
        ({"families": ("price", "technical", "sentiment", "volatility")}, "families must be"),
        ({"method": "shap"}, "method must be one of"),
        ({"seed_importances": {("volatility", 1, 1): 0.0}}, "outside the families"),
    ]
    for changes, message in cases:
        with pytest.raises(ValueError, match=message):
            dataclasses.replace(valid, **changes)
    _, loco = _defined(_assemble())
    with pytest.raises(ValueError, match="must be empty in the loco method"):
        dataclasses.replace(loco, permutation_importances={("price", 1, 1): 0.0})


# --- reduções sobre o cohort sintético -----------------------------------------------


def _cohort() -> Cohort:
    base = make_cohort(seeds={"tft": _SEEDS}, horizons=_HORIZONS)
    return with_ablation(with_permuted(base), seeds=_SEEDS)


def _permuted_reductions(
    cohort: Cohort, records: Sequence[PermutedForecastRecord] | None = None
) -> list[Any]:
    by_run: dict[str, list[PermutedForecastRecord]] = defaultdict(list)
    for record in cohort.permuted if records is None else records:
        by_run[record.run_id].append(record)
    return [
        reduce_permuted_run(by_run[run_id], realized=cohort.realized, levels=GOLD_LEVELS)
        for run_id in sorted(by_run)
    ]


def _ablation_reductions(cohort: Cohort) -> list[Any]:
    return [
        merge_ablation_run(
            [
                reduce_ablation_run(
                    [r for r in cohort.ablation_records if r.run_id == run.run_id],
                    run=run,
                    realized=cohort.realized,
                    levels=GOLD_LEVELS,
                )
            ]
        )
        for run in cohort.ablation_runs
    ]


def _assemble_cohort(cohort: Cohort, permuted: Sequence[Any] | None = None) -> Any:  # noqa: ANN401
    return AttributionAssembly.assemble(
        candidate_runs=cohort.runs,
        permuted=_permuted_reductions(cohort) if permuted is None else permuted,
        ablation_runs=cohort.ablation_runs,
        ablation_losses=_ablation_reductions(cohort),
        parameters=_params(),
        candidate="tft",
        candidate_seeds=_SEEDS,
        horizons=_HORIZONS,
    )


def test_synthetic_cohort_assembles_both_methods_on_the_same_decisions() -> None:
    permutation, ablation = _defined(_assemble_cohort(_cohort()))

    assert permutation.decision_timestamps == ablation.decision_timestamps
    assert len(permutation.decision_timestamps) > 0


def test_decisions_are_the_h1_h7_intersection() -> None:
    cohort = _cohort()
    permutation, _ = _defined(_assemble_cohort(cohort))

    by_horizon = {
        h: {r.decision_timestamp for r in cohort.permuted if r.horizon == h} for h in _HORIZONS
    }
    assert by_horizon[1] != by_horizon[7]  # h+1 tem decisões que h+7 não tem
    assert set(permutation.decision_timestamps) == by_horizon[1] & by_horizon[7]
    for reduction in _permuted_reductions(cohort):
        assert set(reduction.decision_timestamps) <= by_horizon[1] & by_horizon[7]


def test_losses_use_value_guardrail() -> None:
    """`value_raw` cruzado e `value_guardrail` monótono: a perda é a do guardrail."""
    cohort = _cohort()
    run_id = sorted({r.run_id for r in cohort.permuted})[0]
    rows = [r for r in cohort.permuted if r.run_id == run_id]
    point = min((r.horizon, r.decision_timestamp) for r in rows if r.permuted_family == "none")
    crossed = []
    for r in rows:
        if (r.horizon, r.decision_timestamp, r.permuted_family) == (*point, "none"):
            r = dataclasses.replace(r, value_raw=-r.value_raw, guardrail_applied=True)  # noqa: PLW2901
        crossed.append(r)

    reduction = _permuted_reductions(cohort, crossed)[0]

    target_rows = sorted(
        (
            r
            for r in crossed
            if (r.horizon, r.decision_timestamp, r.permuted_family) == (*point, "none")
        ),
        key=lambda r: r.quantile_level,
    )
    y = cohort.realized.realized_at(target_rows[0].target_timestamp)
    guardrail = sum(
        pinball_loss(realized=y, quantile=r.value_guardrail, level=r.quantile_level)
        for r in target_rows
    ) / len(target_rows)
    raw = sum(
        pinball_loss(realized=y, quantile=r.value_raw, level=r.quantile_level) for r in target_rows
    ) / len(target_rows)
    index = reduction.decision_timestamps.index(point[1])
    assert reduction.identity[point[0]][index] == pytest.approx(guardrail)
    assert reduction.identity[point[0]][index] != pytest.approx(raw)


def test_permutation_uses_its_own_identity_not_fact_oos() -> None:
    """I7: d_t sai da identidade da tabela permutada, não da linha de teste da 7.1."""
    cohort = _cohort()
    run_id = sorted({r.run_id for r in cohort.permuted})[0]
    oos = {
        (r.horizon, r.decision_timestamp, r.quantile_level): r.value_guardrail
        for r in cohort.records
        if r.run_id == run_id
    }
    identity = [r for r in cohort.permuted if r.run_id == run_id and r.permuted_family == "none"]
    assert any(
        oos[(r.horizon, r.decision_timestamp, r.quantile_level)] != r.value_guardrail
        for r in identity
    )  # o fixture difere de fato

    reduction = _permuted_reductions(cohort)[0]
    row = min(identity, key=lambda r: (r.horizon, r.decision_timestamp))
    points = sorted(
        (
            r
            for r in identity
            if (r.horizon, r.decision_timestamp) == (row.horizon, row.decision_timestamp)
        ),
        key=lambda r: r.quantile_level,
    )
    y = cohort.realized.realized_at(row.target_timestamp)
    expected = sum(
        pinball_loss(realized=y, quantile=r.value_guardrail, level=r.quantile_level) for r in points
    ) / len(points)
    if row.decision_timestamp in reduction.decision_timestamps:
        index = reduction.decision_timestamps.index(row.decision_timestamp)
        assert reduction.identity[row.horizon][index] == pytest.approx(expected)
    else:  # pragma: no cover — a primeira decisão do fixture tem os dois horizontes
        pytest.fail("first decision outside the h1/h7 intersection")


def _first_identity_point(cohort: Cohort) -> list[PermutedForecastRecord]:
    run_id = sorted({r.run_id for r in cohort.permuted})[0]
    rows = [r for r in cohort.permuted if r.run_id == run_id and r.permuted_family == "none"]
    first = min((r.horizon, r.target_timestamp) for r in rows)
    return [r for r in rows if (r.horizon, r.target_timestamp) == first]


@pytest.mark.parametrize(
    ("change", "kind"),
    [
        ("duplicate", "duplicate_point"),
        ("missing_level", "grid_incomplete"),
        ("realized", "realized_missing"),
    ],
)
def test_alignment_rules_from_series_assembly(change: str, kind: str) -> None:
    cohort = _cohort()
    point = _first_identity_point(cohort)
    records = list(cohort.permuted)
    if change == "duplicate":
        records.append(point[0])
    elif change == "missing_level":
        records.remove(point[0])
    else:
        realized = dataclasses.replace(
            cohort.realized,
            timestamps=cohort.realized.timestamps[:-1],
            returns=cohort.realized.returns[:-1],
        )
        cohort = dataclasses.replace(cohort, realized=realized)

    reductions = _permuted_reductions(cohort, records)
    undefined = [r for r in reductions if isinstance(r, UndefinedRunReduction)]

    assert undefined, reductions
    assert kind in undefined[0].reason
    result = _assemble_cohort(cohort, permuted=reductions)
    assert result.permutation is None
    assert kind in str(result.permutation_reason)


def test_violation_is_never_an_alignment_finding() -> None:
    cohort = _cohort()
    records = [*cohort.permuted, _first_identity_point(cohort)[0]]

    reductions = _permuted_reductions(cohort, records)
    result = _assemble_cohort(cohort, permuted=reductions)

    assert not any(isinstance(r, AlignmentFinding) for r in reductions)
    assert isinstance(result.permutation_reason, str)
    assert isinstance(result, AttributionAssemblyResult)
    assert not isinstance(result.permutation, FamilyLossDifferentials)


def test_reduce_ablation_run_reads_only_test_rows_of_its_run() -> None:
    cohort = _cohort()
    run = cohort.ablation_runs[0]
    rows = [r for r in cohort.ablation_records if r.run_id == run.run_id]
    calib = [dataclasses.replace(r, split="calib") for r in rows[:7]]

    reduced = reduce_ablation_run(
        [*rows, *calib], run=run, realized=cohort.realized, levels=GOLD_LEVELS
    )
    plain = reduce_ablation_run(rows, run=run, realized=cohort.realized, levels=GOLD_LEVELS)

    assert reduced == plain
    assert isinstance(reduced, AblationRunPart)
    assert reduced.model_version == run.model
    with pytest.raises(ValueError, match="takes the records of"):
        reduce_ablation_run(
            rows, run=cohort.ablation_runs[1], realized=cohort.realized, levels=GOLD_LEVELS
        )
    odd = dataclasses.replace(run, fold="f0")
    undefined = reduce_ablation_run(rows, run=odd, realized=cohort.realized, levels=GOLD_LEVELS)
    assert isinstance(undefined, UndefinedRunReduction)
    assert "is not an int" in undefined.reason


# --- regras públicas compartilhadas com a 6.4 (C6-4) ------------------------------------


def test_extra_levels_and_guardrail_flag_are_the_series_assembly_rules() -> None:
    from financial_forecasting.features.evaluation.domain.services import (  # noqa: PLC0415
        attribution_assembly,
        series_assembly,
    )

    assert attribution_assembly.extra_levels is series_assembly.extra_levels
    assert attribution_assembly.guardrail_flag_mismatch is series_assembly.guardrail_flag_mismatch
    extra = series_assembly.extra_levels(present=(0.1, 0.5, 0.7), expected=(0.1, 0.5), where="t")
    assert extra is not None
    assert (extra.kind.value, extra.detail) == (
        "grid_divergent",
        "t: levels [0.7] outside the grid",
    )
    assert series_assembly.extra_levels(present=(0.1,), expected=(0.1, 0.5), where="t") is None
    flag = series_assembly.guardrail_flag_mismatch((True, False), target_timestamp="x")
    assert flag is not None and flag.kind.value == "guardrail_flag_mismatch"
    assert series_assembly.guardrail_flag_mismatch((True, True), target_timestamp="x") is None


# --- blocos anuais da ablação (C6-1) -----------------------------------------------------


def _split_years(cohort: Cohort, run_id: str, boundary: int) -> tuple[list[Any], list[Any]]:
    """Simula o corte por `year` da decisão: o 2º bloco perde as linhas de h+7."""
    rows = [r for r in cohort.ablation_records if r.run_id == run_id]
    first = [r for r in rows if r.decision_idx < boundary]
    second = [r for r in rows if r.decision_idx >= boundary and r.horizon == 1]
    return first, second


def test_a_yearly_part_with_only_h1_merges_to_the_intersection() -> None:
    cohort = _cohort()
    run = cohort.ablation_runs[-1]  # o último fold: a cauda sem h+7 cai no "ano novo"
    rows = [r for r in cohort.ablation_records if r.run_id == run.run_id]
    with_h7 = sorted({r.decision_idx for r in rows if r.horizon == 7})  # noqa: PLR2004
    boundary = with_h7[-1] + 1  # o 2º bloco só tem decisões sem h+7
    first, second = _split_years(cohort, run.run_id, boundary)
    assert second and {r.horizon for r in second} == {1}

    parts = [
        reduce_ablation_run(block, run=run, realized=cohort.realized, levels=GOLD_LEVELS)
        for block in (first, second)
    ]
    merged = merge_ablation_run(parts)
    whole = merge_ablation_run(
        [reduce_ablation_run(rows, run=run, realized=cohort.realized, levels=GOLD_LEVELS)]
    )

    assert isinstance(merged, AblationRunLosses)
    assert merged == whole
    assert set(merged.decision_timestamps) == {
        r.decision_timestamp for r in rows if r.decision_idx in with_h7
    }


def test_a_missing_yearly_part_is_undefined_with_an_explicit_reason() -> None:
    cohort = _cohort()
    run = next(r for r in cohort.ablation_runs if r.model.endswith("minus_price") and r.seed == 1)
    rows = [r for r in cohort.ablation_records if r.run_id == run.run_id]
    boundary = sorted({r.decision_idx for r in rows})[len(rows) // 14 // 2]
    first = [r for r in rows if r.decision_idx < boundary]  # o bloco seguinte faltou

    losses = [
        merge_ablation_run(
            [
                reduce_ablation_run(
                    first
                    if r.run_id == run.run_id
                    else [x for x in cohort.ablation_records if x.run_id == r.run_id],
                    run=r,
                    realized=cohort.realized,
                    levels=GOLD_LEVELS,
                )
            ]
        )
        for r in cohort.ablation_runs
    ]
    result = AttributionAssembly.assemble(
        candidate_runs=cohort.runs,
        permuted=_permuted_reductions(cohort),
        ablation_runs=cohort.ablation_runs,
        ablation_losses=losses,
        parameters=_params(),
        candidate="tft",
        candidate_seeds=_SEEDS,
        horizons=_HORIZONS,
    )

    assert result.ablation is None
    reason = str(result.ablation_reason)
    assert "decision sets differ" in reason
    assert "missing or extra yearly part" in reason


def test_overlapping_yearly_parts_are_undefined_not_value_error() -> None:
    cohort = _cohort()
    run = cohort.ablation_runs[0]
    rows = [r for r in cohort.ablation_records if r.run_id == run.run_id]
    part = reduce_ablation_run(rows, run=run, realized=cohort.realized, levels=GOLD_LEVELS)

    merged = merge_ablation_run([part, part])

    assert isinstance(merged, UndefinedRunReduction)
    assert "is in two parts" in merged.reason


# --- dado inválido vira undefined, nunca ValueError (C6-3) -------------------------------


def _first_run_rows(cohort: Cohort) -> list[PermutedForecastRecord]:
    run_id = sorted({r.run_id for r in cohort.permuted})[0]
    return [r for r in cohort.permuted if r.run_id == run_id]


def test_identity_only_rows_are_undefined() -> None:
    cohort = _cohort()
    rows = [r for r in _first_run_rows(cohort) if r.permuted_family == "none"]
    reduced = reduce_permuted_run(rows, realized=cohort.realized, levels=GOLD_LEVELS)
    assert isinstance(reduced, UndefinedRunReduction)
    assert "no permuted rows (I11)" in reduced.reason


@pytest.mark.parametrize("damage", ["nan", "non-monotone"])
def test_vo_invariants_become_undefined(damage: str) -> None:
    cohort = _cohort()
    rows = _first_run_rows(cohort)
    point = min((r.horizon, r.target_timestamp) for r in rows if r.permuted_family == "price")
    changed = []
    for r in rows:
        if (r.horizon, r.target_timestamp, r.permuted_family, r.permutation_index) == (
            *point,
            "price",
            1,
        ):
            if damage == "nan":
                r = dataclasses.replace(r, value_guardrail=float("nan"))  # noqa: PLW2901
            elif r.quantile_level == GOLD_LEVELS[0]:
                r = dataclasses.replace(r, value_guardrail=10.0)  # noqa: PLW2901
        changed.append(r)

    reduced = reduce_permuted_run(changed, realized=cohort.realized, levels=GOLD_LEVELS)

    assert isinstance(reduced, UndefinedRunReduction)
    assert "price k=1" in reduced.reason


# --- entradas extras ou misturadas viram undefined com o seu motivo (C6-2) ----------------


def _reduce_reason(records: list[PermutedForecastRecord]) -> str:
    cohort = _cohort()
    reduced = reduce_permuted_run(records, realized=cohort.realized, levels=GOLD_LEVELS)
    assert isinstance(reduced, UndefinedRunReduction), reduced
    return reduced.reason


def _e11() -> str:
    rows = _first_run_rows(_cohort())
    target = rows[0]
    return _reduce_reason(
        [
            dataclasses.replace(r, guardrail_applied=True)
            if (r.horizon, r.target_timestamp, r.permuted_family, r.permutation_index)
            == (target.horizon, target.target_timestamp, "none", 0)
            and r.quantile_level == GOLD_LEVELS[3]
            else r
            for r in rows
        ]
    )


def _e12() -> str:
    rows = _first_run_rows(_cohort())
    return _reduce_reason([*rows, dataclasses.replace(rows[0], quantile_level=0.33)])


def _e16() -> str:
    rows = _first_run_rows(_cohort())
    return _reduce_reason([dataclasses.replace(rows[-1], permutation_seed=131), *rows[:-1]])


def _e17() -> str:
    rows = _first_run_rows(_cohort())
    point = max(r.target_timestamp for r in rows if r.horizon == 1)
    return _reduce_reason(
        [
            r
            for r in rows
            if not (
                (r.permuted_family, r.permutation_index, r.horizon) == ("price", 2, 1)
                and r.target_timestamp == point
            )
        ]
    )


def _e18() -> str:
    cohort = _cohort()
    run = cohort.ablation_runs[0]
    rows = [r for r in cohort.ablation_records if r.run_id == run.run_id]
    reduced = reduce_ablation_run(
        [*rows[1:], dataclasses.replace(rows[0], model="tft_quantile")],
        run=run,
        realized=cohort.realized,
        levels=GOLD_LEVELS,
    )
    assert isinstance(reduced, UndefinedRunReduction)
    return reduced.reason


def _assembled(permuted: Any = None, candidate_runs: Any = None, ablation: Any = None) -> Any:  # noqa: ANN401
    return _assemble(permuted=permuted, candidate_runs=candidate_runs, ablation=ablation)


def _e13() -> str:
    permuted = _hand_permuted()
    runs = [_candidate_run(1), _candidate_run(2)]
    extra_run = dataclasses.replace(_candidate_run(1), run_id="tft-s1-1", fold="1")
    extra = dataclasses.replace(permuted[0], run_id="tft-s1-1", fold_index=1)
    return str(_assembled([*permuted, extra], [*runs, extra_run]).permutation_reason)


def _e13b() -> str:
    permuted = _hand_permuted()
    runs = [_candidate_run(1), _candidate_run(2)]
    extra_run = dataclasses.replace(_candidate_run(1), run_id="tft-s1-1")
    later = tuple(session(20 + i) for i in range(3))
    extra = dataclasses.replace(permuted[0], run_id="tft-s1-1", decision_timestamps=later)
    return str(_assembled([*permuted, extra], [*runs, extra_run]).permutation_reason)


def _e14() -> str:
    permuted = _hand_permuted()
    permuted[0] = dataclasses.replace(permuted[0], seed=3)
    return str(_assembled(permuted).permutation_reason)


def _e15() -> str:
    permuted = _hand_permuted()
    permuted[0] = dataclasses.replace(
        permuted[0], permuted={**permuted[0].permuted, ("price", 3, 1): (0.0, 0.0, 0.0)}
    )
    return str(_assembled(permuted).permutation_reason)


def _e20() -> str:
    runs, losses = _hand_ablation()
    extra_run = _ablation_run(_REFERENCE, 3)
    extra = dataclasses.replace(losses[0], run_id=extra_run.run_id, seed=3)
    return str(_assembled(ablation=([*runs, extra_run], [*losses, extra])).ablation_reason)


def _e21() -> str:
    runs, losses = _hand_ablation()
    losses[0] = dataclasses.replace(losses[0], model_version=loco_model_of("price"))
    return str(_assembled(ablation=(runs, losses)).ablation_reason)


def _e24() -> str:
    permuted = _hand_permuted()
    permuted[0] = dataclasses.replace(
        permuted[0],
        identity={1: permuted[0].identity[1]},
        permuted={k: v for k, v in permuted[0].permuted.items() if k[2] == 1},
    )
    return str(_assembled(permuted).permutation_reason)


def _e25() -> str:
    permuted = _hand_permuted()
    shifted = (session(10), session(11), session(14))
    permuted[1] = dataclasses.replace(permuted[1], decision_timestamps=shifted)
    return str(_assembled(permuted).permutation_reason)


@pytest.mark.parametrize(
    ("case", "build", "reason"),
    [
        pytest.param("E11", _e11, "guardrail_flag_mismatch", id="E11"),
        pytest.param("E12", _e12, "grid_divergent", id="E12"),
        pytest.param("E13", _e13, "decisions of the folds overlap or are out of order", id="E13"),
        pytest.param("E13b", _e13b, "fold repeated", id="E13b"),
        pytest.param("E14", _e14, "seed 3 != dim_run 1", id="E14"),
        pytest.param("E15", _e15, "['price', 3, 1] outside [h3]", id="E15"),
        pytest.param("E16", _e16, "mixed seed, fold or permutation provenance", id="E16"),
        pytest.param("E17", _e17, "price k=2 h=1: decisions differ from the identity", id="E17"),
        pytest.param("E18", _e18, "model_version_mismatch", id="E18"),
        pytest.param("E20", _e20, "seed 3 is not a declared seed", id="E20"),
        pytest.param("E21", _e21, "reduction identity differs from the dim_run", id="E21"),
        pytest.param("E24", _e24, "identity horizons [1] != [1, 7]", id="E24"),
        pytest.param("E25", _e25, "decision sets differ between seeds or configurations", id="E25"),
    ],
)
def test_extra_or_mixed_inputs_are_undefined(case: str, build: Any, reason: str) -> None:  # noqa: ANN401
    """Os 13 mutantes sobreviventes do C6-2: cada entrada inválida vira undefined e o motivo."""
    assert reason in build(), case
