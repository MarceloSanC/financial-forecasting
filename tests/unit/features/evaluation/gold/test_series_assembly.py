"""Testes do `SeriesAssembly` (Stage 6.4 Task 04; A2, A3; I1-I10; D1, D2).

Um teste por regra: cada um parte do cohort coerente de `make_cohort` (sem achado),
aplica UMA violação e confere o `kind` e o escopo (horizonte/modelo/seed) do achado —
e que, com achado, nenhuma amostra é montada.
"""

from __future__ import annotations

import dataclasses
import math
import random
from collections.abc import Callable, Mapping

import pytest

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AlignmentFinding,
    AlignmentKind,
    AssembledCohort,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from tests.unit.features.evaluation.gold._cohort_factory import (
    DEFAULT_HORIZONS,
    GOLD_LEVELS,
    Cohort,
    add_records,
    at_point,
    drop_records,
    make_cohort,
    of_series,
    replace_records,
    replace_runs,
    run_id,
    session,
    targets_of,
)

_REQUIRED = frozenset({"tft"})


def _assemble(
    cohort: Cohort,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    window_deficits: Mapping[str, int] | None = None,
    required_models: frozenset[str] = _REQUIRED,
) -> AssembledCohort:
    return SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=horizons,
        window_deficits={} if window_deficits is None else window_deficits,
        required_models=required_models,
    )


def _only(result: AssembledCohort, kind: AlignmentKind) -> list[AlignmentFinding]:
    """Todos os achados são do `kind` pedido (uma violação só); nenhuma amostra montada."""
    assert result.horizons == ()
    assert result.alignment.findings, "expected at least one finding"
    assert {f.kind for f in result.alignment.findings} == {kind}
    return list(result.alignment.findings)


def _scope(finding: AlignmentFinding) -> tuple[int | None, str | None, int | None]:
    return (finding.horizon, finding.model, finding.seed)


@pytest.mark.unit
def test_baseline_cohort_has_no_finding() -> None:
    result = _assemble(make_cohort())
    assert result.alignment.findings == ()
    assert [s.horizon for s in result.horizons] == list(DEFAULT_HORIZONS)


# --- split (I3) ------------------------------------------------------------------------


@pytest.mark.unit
def test_split_non_test_ignored() -> None:
    """Linhas `val` (mesmo com valores e duplicatas estranhos) não mudam a montagem."""
    cohort = make_cohort()
    noise = tuple(
        dataclasses.replace(r, split="val", value_raw=9.0, value_guardrail=9.0, decision_idx=0)
        for r in cohort.records[:30]
    )
    assert _assemble(add_records(cohort, *noise, *noise)) == _assemble(cohort)


# --- identidade (I3) -------------------------------------------------------------------


@pytest.mark.unit
def test_feature_sets_multiple() -> None:
    cohort = replace_runs(
        make_cohort(),
        lambda r: r.run_id == run_id("gbm", None, "f1"),
        lambda r: dataclasses.replace(r, feature_set_name="fs-other"),
    )
    [finding] = _only(_assemble(cohort), AlignmentKind.MULTIPLE_FEATURE_SETS)
    assert _scope(finding) == (None, None, None)
    assert "fs-other" in finding.detail


@pytest.mark.unit
def test_config_signatures_multiple() -> None:
    cohort = replace_runs(
        make_cohort(),
        lambda r: r.run_id == run_id("tft", 2, "f0"),
        lambda r: dataclasses.replace(r, config_signature="sig-drift"),
    )
    [finding] = _only(_assemble(cohort), AlignmentKind.MULTIPLE_CONFIG_SIGNATURES)
    assert _scope(finding) == (None, "tft", None)


@pytest.mark.unit
def test_orphan_run() -> None:
    cohort = make_cohort()
    extra = CohortRun(
        run_id="gbm-extra",
        model="gbm",
        seed=None,
        fold="f0",
        feature_set_name="fs-core",
        config_signature="sig-gbm",
    )
    cohort = dataclasses.replace(cohort, runs=(*cohort.runs, extra))
    [finding] = _only(_assemble(cohort), AlignmentKind.ORPHAN_RUN)
    assert _scope(finding) == (None, "gbm", None)
    assert "gbm-extra" in finding.detail


@pytest.mark.unit
def test_model_version_mismatch() -> None:
    """Dois pontos (7 níveis cada) do mesmo run: UM achado por (horizonte, run)."""
    cohort = make_cohort()
    targets = targets_of(cohort, "tft", 2, 1)[3:5]
    cohort = replace_records(
        cohort,
        lambda r: any(at_point("tft", 2, 1, target)(r) for target in targets),
        lambda r: dataclasses.replace(r, model="tft-v2"),
    )
    findings = _only(_assemble(cohort), AlignmentKind.MODEL_VERSION_MISMATCH)
    assert len(findings) == 1
    assert _scope(findings[0]) == (1, "tft", 2)
    assert run_id("tft", 2, "f0") in findings[0].detail


# --- uma observação por ponto (I4) -----------------------------------------------------


@pytest.mark.unit
def test_duplicate_point() -> None:
    cohort = make_cohort()
    target = targets_of(cohort, "gbm", None, 2)[5]
    row = next(r for r in cohort.records if at_point("gbm", None, 2, target)(r))
    [finding] = _only(
        _assemble(add_records(cohort, dataclasses.replace(row, value_raw=row.value_raw + 1.0))),
        AlignmentKind.DUPLICATE_POINT,
    )
    assert _scope(finding) == (2, "gbm", None)
    assert target in finding.detail


# --- índices de sessão e realizado (I5, I7) --------------------------------------------


@pytest.mark.unit
def test_decision_index_mismatch() -> None:
    cohort = make_cohort()
    target = targets_of(cohort, "tft", 1, 2)[4]
    cohort = replace_records(
        cohort,
        at_point("tft", 1, 2, target),
        lambda r: dataclasses.replace(r, decision_idx=r.decision_idx + 1),
    )
    [finding] = _only(_assemble(cohort), AlignmentKind.DECISION_INDEX_MISMATCH)
    assert _scope(finding) == (2, "tft", 1)


@pytest.mark.unit
def test_horizon_label_mismatch() -> None:
    """Decisão uma sessão antes (índice coerente com o dataset): alvo a h + 1 sessões."""
    cohort = make_cohort()
    target = targets_of(cohort, "gbm", None, 1)[6]
    cohort = replace_records(
        cohort,
        at_point("gbm", None, 1, target),
        lambda r: dataclasses.replace(
            r, decision_idx=r.decision_idx - 1, decision_timestamp=session(r.decision_idx - 1)
        ),
    )
    [finding] = _only(_assemble(cohort), AlignmentKind.HORIZON_LABEL_MISMATCH)
    assert _scope(finding) == (1, "gbm", None)


@pytest.mark.unit
def test_realized_missing() -> None:
    """Sem a última sessão no dataset, o último alvo de toda série fica sem realizado."""
    cohort = make_cohort()
    realized = cohort.realized
    cut = RealizedReturns(timestamps=realized.timestamps[:-1], returns=realized.returns[:-1])
    findings = _only(
        _assemble(dataclasses.replace(cohort, realized=cut)), AlignmentKind.REALIZED_MISSING
    )
    assert {_scope(f) for f in findings} == {
        (h, m, s) for h in DEFAULT_HORIZONS for m, s in (("gbm", None), ("tft", 1), ("tft", 2))
    }


# --- grade e guardrail (I6) ------------------------------------------------------------


@pytest.mark.unit
def test_grid_incomplete() -> None:
    cohort = make_cohort()
    target = targets_of(cohort, "tft", 2, 1)[7]
    cohort = drop_records(
        cohort, lambda r: at_point("tft", 2, 1, target)(r) and r.quantile_level == GOLD_LEVELS[2]
    )
    [finding] = _only(_assemble(cohort), AlignmentKind.GRID_INCOMPLETE)
    assert _scope(finding) == (1, "tft", 2)
    assert str(GOLD_LEVELS[2]) in finding.detail


@pytest.mark.unit
def test_grid_divergent() -> None:
    """O `gbm` no h = 2 sem o par extremo: grade (coerente em si) diferente da do `tft`."""
    cohort = drop_records(
        make_cohort(),
        lambda r: of_series("gbm", None, 2)(r) and r.quantile_level in (0.05, 0.95),
    )
    [finding] = _only(_assemble(cohort), AlignmentKind.GRID_DIVERGENT)
    assert _scope(finding) == (2, None, None)


@pytest.mark.unit
def test_guardrail_flag_mismatch() -> None:
    cohort = make_cohort()
    target = targets_of(cohort, "gbm", None, 2)[9]
    cohort = replace_records(
        cohort,
        lambda r: at_point("gbm", None, 2, target)(r) and r.quantile_level == GOLD_LEVELS[3],
        lambda r: dataclasses.replace(r, guardrail_applied=True),
    )
    [finding] = _only(_assemble(cohort), AlignmentKind.GUARDRAIL_FLAG_MISMATCH)
    assert _scope(finding) == (2, "gbm", None)


# --- contiguidade (I8) -----------------------------------------------------------------


@pytest.mark.unit
def test_interior_gap() -> None:
    cohort = make_cohort()
    target = targets_of(cohort, "tft", 1, 1)[10]
    [finding] = _only(
        _assemble(drop_records(cohort, at_point("tft", 1, 1, target))), AlignmentKind.INTERIOR_GAP
    )
    assert _scope(finding) == (1, "tft", 1)


@pytest.mark.unit
def test_truncated_suffix() -> None:
    cohort = make_cohort()
    last = targets_of(cohort, "tft", 2, 2)[-1]
    [finding] = _only(
        _assemble(drop_records(cohort, at_point("tft", 2, 2, last))),
        AlignmentKind.TRUNCATED_SUFFIX,
    )
    assert _scope(finding) == (2, "tft", 2)


@pytest.mark.unit
def test_prefix_over_deficit() -> None:
    """Primeiro ponto a menos com déficit 0: início atrasado sem declaração."""
    cohort = make_cohort()
    first = targets_of(cohort, "gbm", None, 1)[0]
    [finding] = _only(
        _assemble(drop_records(cohort, at_point("gbm", None, 1, first))),
        AlignmentKind.PREFIX_OVER_DEFICIT,
    )
    assert _scope(finding) == (1, "gbm", None)


@pytest.mark.unit
def test_prefix_over_deficit_when_prefix_exceeds_declared() -> None:
    cohort = make_cohort(prefixes={"tft": 3})
    findings = _only(
        _assemble(cohort, window_deficits={"tft": 2}), AlignmentKind.PREFIX_OVER_DEFICIT
    )
    assert {_scope(f) for f in findings} == {
        (h, "tft", s) for h in DEFAULT_HORIZONS for s in (1, 2)
    }


@pytest.mark.unit
def test_prefix_within_deficit() -> None:
    """Candidato 2 sessões atrás com déficit 3: sem achado; amostra comum = interseção."""
    cohort = make_cohort(prefixes={"tft": 2})
    result = _assemble(cohort, window_deficits={"tft": 3})
    assert result.alignment.findings == ()
    for samples in result.horizons:
        gbm_targets = targets_of(cohort, "gbm", None, samples.horizon)
        tft_targets = targets_of(cohort, "tft", 1, samples.horizon)
        assert tft_targets[0] == gbm_targets[2]
        assert samples.full["tft"][0].n_points == samples.full["gbm"][0].n_points - 2
        assert samples.n_common == len(tft_targets)
        assert samples.common_first_target_timestamp == tft_targets[0]
        assert samples.common_last_target_timestamp == tft_targets[-1]
        assert samples.common["gbm"][0].target_timestamps == tuple(tft_targets)
    assert result.alignment.common_points == tuple(
        (s.horizon, len(targets_of(cohort, "tft", 1, s.horizon))) for s in result.horizons
    )


@pytest.mark.unit
def test_common_intersection() -> None:
    """(h, T) de `common_points` = interseção dos intervalos, igual ao `n_common`."""
    cohort = make_cohort(prefixes={"gbm": 1, "tft": 4})
    result = _assemble(cohort, window_deficits={"tft": 4, "gbm": 1})
    assert result.alignment.findings == ()
    for samples in result.horizons:
        expected = targets_of(cohort, "tft", 2, samples.horizon)
        assert (samples.horizon, samples.n_common) in result.alignment.common_points
        assert samples.n_common == len(expected)
        for model in samples.models:
            for series in samples.common[model]:
                assert series.target_timestamps == tuple(expected)


# --- cobertura (I9) --------------------------------------------------------------------


@pytest.mark.unit
def test_fold_coverage() -> None:
    """A série (tft, 2) inteira no run do `f0`: sem o fold `f1` do cohort."""
    cohort = make_cohort()
    merged = run_id("tft", 2, "f0")
    cohort = replace_records(
        cohort,
        lambda r: r.run_id == run_id("tft", 2, "f1"),
        lambda r: dataclasses.replace(r, run_id=merged, fold="f0"),
    )
    cohort = dataclasses.replace(
        cohort, runs=tuple(r for r in cohort.runs if r.run_id != run_id("tft", 2, "f1"))
    )
    [finding] = _only(_assemble(cohort), AlignmentKind.FOLD_COVERAGE)
    assert _scope(finding) == (None, "tft", 2)


@pytest.mark.unit
def test_seed_horizon_coverage() -> None:
    cohort = drop_records(make_cohort(), of_series("tft", 2, 2))
    [finding] = _only(_assemble(cohort), AlignmentKind.SEED_HORIZON_COVERAGE)
    assert _scope(finding) == (2, "tft", 2)


@pytest.mark.unit
def test_horizon_missing() -> None:
    cohort = drop_records(make_cohort(), lambda r: r.horizon == DEFAULT_HORIZONS[1])
    [finding] = _only(_assemble(cohort), AlignmentKind.HORIZON_MISSING)
    assert _scope(finding) == (2, None, None)


@pytest.mark.unit
def test_required_model_missing() -> None:
    [finding] = _only(
        _assemble(make_cohort(), required_models=frozenset({"tft", "naive"})),
        AlignmentKind.REQUIRED_MODEL_MISSING,
    )
    assert _scope(finding) == (None, "naive", None)


# --- T mínimo (I10) --------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("n_sessions", "horizon", "reason"),
    [
        pytest.param(16, 1, "MIN_BLOCK_LENGTH_OBS", id="below-block-length"),
        pytest.param(9, 2, "T > h", id="t-not-above-h"),
    ],
)
def test_common_too_short(n_sessions: int, horizon: int, reason: str) -> None:
    """T = 10 < 11 (b̂_sb) e T = 2 = h (`check_points`) — os mínimos dos donos."""
    cohort = make_cohort(n_sessions=n_sessions, horizons=(horizon,), folds=("f0",))
    result = _assemble(cohort, horizons=(horizon,))
    [finding] = _only(result, AlignmentKind.COMMON_SAMPLE_TOO_SHORT)
    assert _scope(finding) == (horizon, None, None)
    assert reason in finding.detail
    assert result.alignment.common_points == ((horizon, n_sessions - 5 - horizon),)


@pytest.mark.unit
def test_common_too_short_empty_intersection() -> None:
    """Interseção vazia (gbm termina antes do tft começar): achado, sem (h, T), sem exceção."""
    cohort = make_cohort(prefixes={"tft": 20}, folds=("f0",))
    late = {session(i) for i in range(20, 40)}
    cohort = drop_records(
        cohort, lambda r: of_series("gbm", None, 1)(r) and r.target_timestamp in late
    )
    result = _assemble(cohort, window_deficits={"tft": 20})
    kinds = {(f.kind, f.horizon, f.model) for f in result.alignment.findings}
    assert kinds == {
        (AlignmentKind.TRUNCATED_SUFFIX, 1, "gbm"),
        (AlignmentKind.COMMON_SAMPLE_TOO_SHORT, 1, None),
    }
    assert result.horizons == ()
    assert [h for h, _ in result.alignment.common_points] == [2]


@pytest.mark.unit
def test_common_too_short_not_at_block_floor() -> None:
    """T == MIN_BLOCK_LENGTH_OBS (11): o piso é inclusivo, sem achado."""
    cohort = make_cohort(n_sessions=17, horizons=(1,), folds=("f0",))
    result = _assemble(cohort, horizons=(1,))
    assert result.alignment.findings == ()
    assert result.alignment.common_points == ((1, 11),)


@pytest.mark.unit
def test_realized_missing_whole_series() -> None:
    """Série com TODO alvo fora do dataset: só `realized_missing`, sem intervalo."""
    cohort = replace_records(
        make_cohort(),
        of_series("tft", 2, 1),
        lambda r: dataclasses.replace(r, target_timestamp="2099-" + r.target_timestamp[5:]),
    )
    result = _assemble(cohort)
    assert {f.kind for f in result.alignment.findings} == {AlignmentKind.REALIZED_MISSING}
    findings = _only(result, AlignmentKind.REALIZED_MISSING)
    assert {_scope(f) for f in findings} == {(1, "tft", 2)}


# --- montagem sem achado (A3, I6, I7) --------------------------------------------------


def _records_by_point(
    cohort: Cohort,
) -> dict[tuple[str, int | None, int, str], dict[float, ForecastRecord]]:
    table: dict[tuple[str, int | None, int, str], dict[float, ForecastRecord]] = {}
    for r in cohort.records:
        table.setdefault((r.model, r.seed, r.horizon, r.target_timestamp), {})[r.quantile_level] = r
    return table


@pytest.mark.unit
def test_reproduces_persisted_values() -> None:
    """Cada ponto de cada série guarda `value_raw`/`value_guardrail`/`guardrail_applied`."""
    cohort = make_cohort()
    table = _records_by_point(cohort)
    result = _assemble(cohort)
    special = cohort.special
    assert special is not None
    assert special.guardrail != tuple(sorted(special.raw))
    seen_special = False
    for samples in result.horizons:
        for model in samples.models:
            for seed, series in zip(samples.seeds[model], samples.full[model], strict=True):
                for ts, forecast in zip(series.target_timestamps, series.forecasts, strict=True):
                    rows = table[model, seed, samples.horizon, ts]
                    assert forecast.levels == samples.levels == GOLD_LEVELS
                    assert forecast.raw_values == tuple(rows[q].value_raw for q in GOLD_LEVELS)
                    assert forecast.guardrail_values == tuple(
                        rows[q].value_guardrail for q in GOLD_LEVELS
                    )
                    assert forecast.guardrail_applied is rows[GOLD_LEVELS[0]].guardrail_applied
                    if (model, seed, samples.horizon, ts) == (
                        special.model,
                        special.seed,
                        special.horizon,
                        special.target_timestamp,
                    ):
                        seen_special = True
                        assert forecast.raw_values == special.raw
                        assert forecast.guardrail_values == special.guardrail
                        assert forecast.guardrail_applied is False
                        rebuilt = QuantileForecast.from_raw(
                            levels=GOLD_LEVELS, raw_values=special.raw
                        )
                        assert rebuilt.guardrail_applied is True
    assert seen_special


@pytest.mark.unit
def test_quantile_forecast_not_from_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> QuantileForecast:
        raise AssertionError("from_raw must not be called by the assembly")

    monkeypatch.setattr(QuantileForecast, "from_raw", _forbidden)
    result = _assemble(make_cohort())
    assert result.alignment.findings == ()
    assert result.horizons


@pytest.mark.unit
def test_realized_joined() -> None:
    """`realized` de cada ponto = `realized_at(target)` — o realizado lido (I7)."""
    cohort = make_cohort()
    for samples in _assemble(cohort).horizons:
        for model in samples.models:
            for series in (*samples.full[model], *samples.common[model]):
                assert series.realized == tuple(
                    cohort.realized.realized_at(ts) for ts in series.target_timestamps
                )


@pytest.mark.unit
def test_horizons_from_command() -> None:
    """Horizonte no silver e fora do comando é ignorado; só os pedidos são montados."""
    cohort = make_cohort(horizons=(1, 2, 3))
    result = _assemble(cohort, horizons=(2,))
    assert result.alignment.findings == ()
    assert [s.horizon for s in result.horizons] == [2]
    assert [h for h, _ in result.alignment.common_points] == [2]


@pytest.mark.unit
def test_all_findings_reported() -> None:
    """Duas violações de tipos diferentes: os dois achados, em ordem do enum."""
    cohort = make_cohort()
    target = targets_of(cohort, "tft", 1, 1)[10]
    cohort = drop_records(cohort, at_point("tft", 1, 1, target))
    result = _assemble(cohort, required_models=frozenset({"naive", "tft"}))
    kinds = [f.kind for f in result.alignment.findings]
    assert kinds == [AlignmentKind.INTERIOR_GAP, AlignmentKind.REQUIRED_MODEL_MISSING]
    assert result.horizons == ()


@pytest.mark.unit
def test_shuffled_input_same_result() -> None:
    cohort = make_cohort(prefixes={"tft": 1})
    rng = random.Random(20260929)
    records = list(cohort.records)
    runs = list(cohort.runs)
    rng.shuffle(records)
    rng.shuffle(runs)
    shuffled = dataclasses.replace(cohort, records=tuple(records), runs=tuple(runs))
    deficits = {"tft": 1}
    assert _assemble(shuffled, window_deficits=deficits) == _assemble(
        cohort, window_deficits=deficits
    )
    broken = drop_records(cohort, at_point("tft", 1, 1, targets_of(cohort, "tft", 1, 1)[5]))
    broken_shuffled = dataclasses.replace(
        broken, records=tuple(rng.sample(broken.records, len(broken.records)))
    )
    assert _assemble(broken_shuffled) == _assemble(broken)


@pytest.mark.unit
def test_non_finite_guardrail_raises_not_finding() -> None:
    """Não-finito com o resto alinhado: invariante do fornecedor, a `CoverageSeries` ergue.

    Decisão do technical 6.4 §7 (ADR 6.1.0002 item 5): não é regra de alinhamento
    I3-I10, então não vira achado; propaga (C7).
    """
    cohort = make_cohort()
    target = targets_of(cohort, "gbm", None, 1)[3]
    cohort = replace_records(
        cohort,
        lambda r: at_point("gbm", None, 1, target)(r) and r.quantile_level == GOLD_LEVELS[-1],
        lambda r: dataclasses.replace(r, value_guardrail=math.nan),
    )
    with pytest.raises(ValueError, match="guardrail values must all be finite"):
        _assemble(cohort)


# --- erro de chamada -------------------------------------------------------------------


def _duplicate_run(cohort: Cohort) -> Cohort:
    return dataclasses.replace(cohort, runs=(*cohort.runs, cohort.runs[0]))


def _record_outside(cohort: Cohort) -> Cohort:
    return dataclasses.replace(
        cohort, runs=tuple(r for r in cohort.runs if r.run_id != run_id("gbm", None, "f0"))
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"horizons": ()}, "horizons must be a non-empty tuple", id="no-horizons"),
        pytest.param({"horizons": [1, 2]}, "non-empty tuple", id="horizons-list"),
        pytest.param({"horizons": (2, 1)}, "strictly increasing", id="horizons-order"),
        pytest.param({"horizons": (1, 1)}, "strictly increasing", id="horizons-repeat"),
        pytest.param({"horizons": (0,)}, "horizons must be an int >= 1", id="horizon-zero"),
        pytest.param({"horizons": (True,)}, "horizons must be an int >= 1", id="horizon-bool"),
        pytest.param({"window_deficits": [("tft", 1)]}, "must be a Mapping", id="deficits-list"),
        pytest.param({"window_deficits": {"tft": -1}}, r"window_deficits\['tft'\]", id="neg"),
        pytest.param({"window_deficits": {"tft": True}}, r"window_deficits\['tft'\]", id="bool"),
        pytest.param({"window_deficits": {"tft": 1.0}}, r"window_deficits\['tft'\]", id="float"),
        pytest.param({"required_models": {"tft"}}, "must be a frozenset", id="required-set"),
    ],
)
def test_invalid_call_raises(changes: dict[str, object], message: str) -> None:
    cohort = make_cohort()
    kwargs: dict[str, object] = {
        "horizons": DEFAULT_HORIZONS,
        "window_deficits": {},
        "required_models": _REQUIRED,
    }
    kwargs.update(changes)
    with pytest.raises(ValueError, match=message):
        SeriesAssembly.assemble(cohort.records, cohort.runs, cohort.realized, **kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(_duplicate_run, "unique run_id", id="duplicate-run"),
        pytest.param(_record_outside, "outside the cohort runs", id="record-outside"),
    ],
)
def test_invalid_call_raises_structural_runs(
    mutate: Callable[[Cohort], Cohort], message: str
) -> None:
    cohort = mutate(make_cohort())
    with pytest.raises(ValueError, match=message):
        _assemble(cohort)


@pytest.mark.unit
def test_horizon_label_short_mismatch() -> None:
    """Decisão uma sessão DEPOIS (índice coerente): alvo a h - 1 sessões também é achado."""
    cohort = make_cohort()
    target = targets_of(cohort, "gbm", None, 2)[6]
    cohort = replace_records(
        cohort,
        at_point("gbm", None, 2, target),
        lambda r: dataclasses.replace(
            r, decision_idx=r.decision_idx + 1, decision_timestamp=session(r.decision_idx + 1)
        ),
    )
    [finding] = _only(_assemble(cohort), AlignmentKind.HORIZON_LABEL_MISMATCH)
    assert _scope(finding) == (2, "gbm", None)


@pytest.mark.unit
def test_run_with_only_val_rows_orphaned() -> None:
    """Run cujas linhas são todas `val` continua órfão: só `split = "test"` conta (I3)."""
    cohort = make_cohort()
    extra = CohortRun(
        run_id="gbm-extra",
        model="gbm",
        seed=None,
        fold="f0",
        feature_set_name="fs-core",
        config_signature="sig-gbm",
    )
    val_rows = tuple(
        dataclasses.replace(r, run_id="gbm-extra", split="val")
        for r in cohort.records
        if of_series("gbm", None, 1)(r)
    )
    cohort = dataclasses.replace(add_records(cohort, *val_rows), runs=(*cohort.runs, extra))
    [finding] = _only(_assemble(cohort), AlignmentKind.ORPHAN_RUN)
    assert _scope(finding) == (None, "gbm", None)
    assert "gbm-extra" in finding.detail


# --- Stage 6.6 Task 05: fold da amostra comum (CA1; ADR 6.6.0003) ----------------------


def _folds_by_target(cohort: Cohort, horizon: int) -> dict[str, str | None]:
    return {
        r.target_timestamp: r.fold
        for r in cohort.records
        if r.horizon == horizon and r.model == "tft" and r.seed == 1
    }


@pytest.mark.unit
@pytest.mark.parametrize("folds", [("f0", "f1"), ("a", "b", "c")])
def test_common_folds_follow_the_run_of_each_point(folds: tuple[str, ...]) -> None:
    """Folds de tamanhos distintos: um rótulo por ponto comum, o do run que o previu."""
    cohort = make_cohort(folds=folds)
    result = _assemble(cohort)
    assert result.alignment.findings == ()
    for samples in result.horizons:
        expected = _folds_by_target(cohort, samples.horizon)
        targets = samples.common["tft"][0].target_timestamps
        assert samples.common_folds == tuple(expected[t] for t in targets)
        assert samples.fold_mismatch_detail is None
        assert set(samples.common_folds) == set(folds)


@pytest.mark.unit
def test_common_folds_none_label() -> None:
    """Cohort sem folds (`fold = None` em todo run): uma tupla de `None`, sem achado."""
    cohort = make_cohort(folds=("f0",))
    cohort = replace_runs(cohort, lambda _: True, lambda r: dataclasses.replace(r, fold=None))
    cohort = replace_records(cohort, lambda _: True, lambda r: dataclasses.replace(r, fold=None))
    result = _assemble(cohort)
    assert result.alignment.findings == ()
    for samples in result.horizons:
        assert samples.common_folds == (None,) * samples.n_common


@pytest.mark.unit
@pytest.mark.parametrize(("model", "seed"), [("gbm", None), ("tft", 1), ("tft", 2)])
def test_diverging_fold_labels_are_not_a_finding(model: str, seed: int | None) -> None:
    """Uma série com o fold trocado num alvo: `common_folds = None` + motivo, sem achado e
    com as amostras montadas (o fold não bloqueia o veredito — ADR 6.6.0003). Toda série
    conta, inclusive a última seed do mesmo modelo (Checkpoint C bloco 2, T2)."""
    cohort = make_cohort()
    target = targets_of(cohort, model, seed, 1)[3]
    cohort = replace_records(
        cohort,
        at_point(model, seed, 1, target),
        lambda r: dataclasses.replace(r, fold="f9"),
    )
    result = _assemble(cohort)
    assert result.alignment.findings == ()
    first = result.horizons[0]
    assert first.common_folds is None
    assert first.fold_mismatch_detail is not None
    assert target in first.fold_mismatch_detail
    assert "f9" in first.fold_mismatch_detail
    assert result.horizons[1].common_folds is not None


@pytest.mark.unit
@pytest.mark.parametrize("level_index", [0, 3, -1])
def test_diverging_fold_in_a_single_level_is_seen(level_index: int) -> None:
    """Checkpoint C bloco 2 (T3): o fold de **todos** os níveis do ponto conta — um nível só
    com outro fold já torna o rótulo do alvo ambíguo."""
    cohort = make_cohort()
    target = targets_of(cohort, "tft", 1, 1)[2]
    level = GOLD_LEVELS[level_index]
    cohort = replace_records(
        cohort,
        lambda r: at_point("tft", 1, 1, target)(r) and r.quantile_level == level,
        lambda r: dataclasses.replace(r, fold="f9"),
    )
    result = _assemble(cohort)
    assert result.alignment.findings == ()
    assert result.horizons[0].common_folds is None
