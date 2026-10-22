"""Unit do use case `ServeInference` (Stage 7.4, Task 02) — concept I2-I8, I11, I13; CA1-CA7, CA13.

Cohort sintético: folds "0" e "1" x seeds 1 e 2, h+1 e h+7. O teste do fold 0 vai de
2024-03-11 a 2024-03-15; o calib do fold 1 cobre 2024-03-14 e 2024-03-15 (a
sobreposição teste k / calib k+1); o teste do fold 1 vai de 2024-03-18 a 2024-03-22, e
2024-03-22 só tem h+1 (as últimas sessões). 2024-03-08 só existe no calib do fold 0. Um
`gbm_quantile` com seed 1 vive no mesmo `parent_sweep_id`. Valores diádicos: os
literais esperados são exatos.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, timedelta

import pytest

from financial_forecasting.features.inference.application.dtos.serving_gold import (
    AVAILABLE,
    LOWER,
    OK,
    UNAVAILABLE,
    UPPER,
    ConformalCorrectionRecord,
    H3ReadingRecord,
    H3ShareRecord,
    ServingGold,
    VsnRecord,
)
from financial_forecasting.features.inference.application.ports.out.serving_gold_reader import (
    ServingGoldReader,
)
from financial_forecasting.features.inference.application.ports.out.silver_table_reader import (
    SilverTableReader,
)
from financial_forecasting.features.inference.application.use_cases.serve_inference import (
    InferencePayload,
    SeedForecast,
    ServeInference,
    ServeInferenceQuery,
    ServingScope,
)
from financial_forecasting.features.inference.domain.exceptions.serving import (
    NO_SERVED_DATA,
    NoServedDataError,
)
from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalVariant,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.exceptions.base import NotFoundError
from tests.fakes.features.evaluation.fake_silver_table_reader import FakeSilverTableReader
from tests.fakes.features.inference.in_memory_serving_gold_reader import (
    InMemoryServingGoldReader,
)

pytestmark = pytest.mark.unit

_COHORT = "aapl_confirmatory-r0-abc"
_ASSET = "AAPL"
_FS = "fs_v1"
_MODEL = "tft_quantile"
_LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)
_SPLIT = ConformalVariant.SPLIT_CQR.value
_NEXCP = ConformalVariant.NEXCP.value
_LABELS = {"conformal_label": "rótulo c", "h3_label": "rótulo h3", "vsn_label": "rótulo vsn"}
_OFFSETS = (-0.03125, -0.015625, 0.0, 0.0078125, 0.03125)
_DEFAULT_Q = 0.001953125

_CALIB_0 = [date(2024, 3, d) for d in (4, 5, 6, 7, 8)]
_TEST_0 = [date(2024, 3, d) for d in (11, 12, 13, 14, 15)]
_CALIB_1 = [date(2024, 3, 14), date(2024, 3, 15)]
_TEST_1 = [date(2024, 3, d) for d in (18, 19, 20, 21, 22)]
_LAST = date(2024, 3, 22)  # só h+1
_H7 = 7
_SEED_2 = 2
_FRIDAY = date(2024, 3, 15)
_OVERLAP = date(2024, 3, 14)
_ONLY_CALIB = date(2024, 3, 8)

# Membro literal (fold 0, seed 1, h+1, 2024-03-15).
_LITERAL_GRID = (-0.03125, -0.015625, 0.001953125, 0.0078125, 0.03125)


def _scope(**overrides: object) -> ServingScope:
    fields: dict[str, object] = {
        "cohort_id": _COHORT,
        "asset": _ASSET,
        "feature_set_name": _FS,
        "model_version": _MODEL,
        "horizons": (1, 7),
        "quantile_levels": _LEVELS,
        "seeds": (1, 2),
    }
    fields.update(overrides)
    return ServingScope(**fields)  # type: ignore[arg-type]


def _ts(day: date) -> str:
    return f"{day.isoformat()}T00:00:00+00:00"


def _grid(run_id: str, seed: int, fold: int, horizon: int, day: date) -> tuple[float, ...]:
    if (run_id, horizon, day) == ("f0s1", 1, _FRIDAY):
        return _LITERAL_GRID
    base = seed / 512 + horizon / 4096 + fold / 8192
    return tuple(base + offset for offset in _OFFSETS)


def _fact_rows(
    run: tuple[str, int, int], split: str, day: date, horizon: int, model: str = _MODEL
) -> list[dict[str, object]]:
    run_id, seed, fold = run
    return [
        {
            "run_id": run_id,
            "model_version": model,
            "asset": _ASSET,
            "feature_set_name": _FS,
            "split": split,
            "horizon": horizon,
            "decision_idx": 0,
            "timestamp_utc": _ts(day),
            "target_timestamp_utc": _ts(day + timedelta(days=horizon)),
            "quantile_level": level,
            "value_raw": value + 1.0,  # nunca servido: só o `value_guardrail` é
            "value_guardrail": value,
            "guardrail_applied": 0,
            "year": day.year,
        }
        for level, value in zip(_LEVELS, _grid(run_id, seed, fold, horizon, day), strict=True)
    ]


def _dim_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "run_id": f"f{fold}s{seed}",
            "asset": _ASSET,
            "parent_sweep_id": _COHORT,
            "feature_set_name": _FS,
            "fold": str(fold),
            "seed": seed,
            "model_version": _MODEL,
        }
        for fold in (0, 1)
        for seed in (1, 2)
    ]
    rows.append(
        {
            "run_id": "gbm0",
            "asset": _ASSET,
            "parent_sweep_id": _COHORT,
            "feature_set_name": _FS,
            "fold": "0",
            "seed": 1,
            "model_version": "gbm_quantile",
        }
    )
    return rows


def _silver_rows() -> dict[str, list[dict[str, object]]]:
    facts: list[dict[str, object]] = []
    for seed in (1, 2):
        for horizon in (1, 7):
            for day in _CALIB_0:
                facts += _fact_rows((f"f0s{seed}", seed, 0), "calib", day, horizon)
            for day in _TEST_0:
                facts += _fact_rows((f"f0s{seed}", seed, 0), "test", day, horizon)
            for day in _CALIB_1:
                facts += _fact_rows((f"f1s{seed}", seed, 1), "calib", day, horizon)
            for day in _TEST_1:
                if horizon == _H7 and day == _LAST:
                    continue
                facts += _fact_rows((f"f1s{seed}", seed, 1), "test", day, horizon)
    for day in _TEST_0:
        facts += _fact_rows(("gbm0", 1, 0), "test", day, 1, model="gbm_quantile")
    return {"dim_run": _dim_rows(), "fact_oos_predictions": facts}


def _correction(
    fold: str, seed: int, horizon: int, pair: tuple[float, float], tail: str, **fields: object
) -> ConformalCorrectionRecord:
    values: dict[str, object] = {
        "fold_raw": fold,
        "seed": seed,
        "horizon": horizon,
        "lower_level": pair[0],
        "upper_level": pair[1],
        "variant": _SPLIT,
        "tail": tail,
        "tail_level": pair[0] if tail == LOWER else pair[1],
        "status": OK,
        "reason": None,
        "n": 200,
        "rank": 190,
        "correction": _DEFAULT_Q,
    }
    values.update(fields)
    return ConformalCorrectionRecord(**values)  # type: ignore[arg-type]


_Key = tuple[str, int, int, tuple[float, float], str]

# Overrides da variante de registro do membro literal e da seed 2 (fold 0, h+1).
_LITERAL_OVERRIDES: dict[_Key, dict[str, object]] = {
    ("0", 1, 1, (0.1, 0.9), LOWER): {"correction": 0.00390625},
    ("0", 1, 1, (0.25, 0.75), LOWER): {"correction": -0.0234375},
    ("0", 1, 1, (0.25, 0.75), UPPER): {"correction": -0.015625},
    ("0", 2, 1, (0.1, 0.9), UPPER): {"correction": math.inf, "n": 10, "rank": 11},
    # fold "1" com Q̂ próprio: a chave da unidade tem de incluir o fold (C1-3)
    ("1", 1, 1, (0.1, 0.9), LOWER): {"correction": 0.0625},
}


def _corrections(
    overrides: Mapping[_Key, Mapping[str, object]] | None = None,
    *,
    drop: Sequence[_Key] = (),
) -> tuple[ConformalCorrectionRecord, ...]:
    chosen = {**_LITERAL_OVERRIDES, **(overrides or {})}
    records: list[ConformalCorrectionRecord] = []
    for fold in ("0", "1"):
        for seed in (1, 2):
            for horizon in (1, 7):
                for pair in ((0.1, 0.9), (0.25, 0.75)):
                    for tail in (LOWER, UPPER):
                        key: _Key = (fold, seed, horizon, pair, tail)
                        # NEXCP com valor grande: misturar variantes muda os literais
                        records.append(_correction(*key, variant=_NEXCP, correction=0.5, rank=None))
                        if key in drop:
                            continue
                        records.append(_correction(*key, **chosen.get(key, {})))
    return tuple(records)


_SHARE = H3ShareRecord(
    method="permutation",
    family="price",
    share_h1=0.5,
    share_h7=0.25,
    delta=-0.25,
    lower=-0.5,
    upper=math.inf,
    level=0.9,
    side=-1,
    excludes_zero=False,
    status=OK,
    reason=None,
)
_READING = H3ReadingRecord(
    reading_rule="regra",
    heterogeneous_permutation=True,
    heterogeneous_ablation=False,
    sustained=False,
    agreeing_families=("price",),
    n_points=5,
    status=OK,
    reason=None,
)
_VSN = VsnRecord(
    kind="family",
    name="price",
    family="price",
    p10=0.125,
    p50=0.25,
    p90=0.5,
    n_decisions=5,
    status=OK,
    reason=None,
)


def _gold(**overrides: object) -> ServingGold:
    fields: dict[str, object] = {
        "published": True,
        "generation_status": "COMPLETED",
        "preregistration_ref": "config/preregistration/x-r3.toml",
        "candidate": _MODEL,
        "finished_at": "2026-10-21T12:00:00+00:00",
        "conformal_status": AVAILABLE,
        "conformal_reason": None,
        "explainability_status": AVAILABLE,
        "explainability_reason": None,
        "corrections": _corrections(),
        "shares": (_SHARE,),
        "reading": _READING,
        "vsn": (_VSN,),
        **_LABELS,
    }
    fields.update(overrides)
    return ServingGold(**fields)  # type: ignore[arg-type]


def _no_conformal(**overrides: object) -> ServingGold:
    return _gold(
        conformal_status=UNAVAILABLE,
        conformal_reason="geração sem bloco [conformal]",
        corrections=(),
        **overrides,
    )


def _blocked(**overrides: object) -> ServingGold:
    return _gold(
        generation_status="BLOCKED",
        conformal_status=UNAVAILABLE,
        conformal_reason="geração gold BLOCKED",
        corrections=(),
        explainability_status=UNAVAILABLE,
        explainability_reason="geração gold BLOCKED",
        shares=(),
        reading=None,
        vsn=(),
        **overrides,
    )


def _serve(
    *,
    rows: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    gold: ServingGold | None = None,
    scope: ServingScope | None = None,
) -> tuple[ServeInference, FakeSilverTableReader, InMemoryServingGoldReader]:
    silver = FakeSilverTableReader(_silver_rows() if rows is None else rows)
    reader = InMemoryServingGoldReader({(_ASSET, _COHORT): _gold() if gold is None else gold})
    use_case = ServeInference(scope=scope or _scope(), silver=silver, gold=reader)
    return use_case, silver, reader


def _query(
    day: date = _FRIDAY,
    *,
    asset: str = _ASSET,
    horizons: tuple[int, ...] | None = None,
    seeds: tuple[int, ...] | None = None,
) -> ServeInferenceQuery:
    return ServeInferenceQuery(asset=asset, decision_date=day, horizons=horizons, seeds=seeds)


def _member(payload: InferencePayload, horizon: int, seed: int) -> SeedForecast:
    (forecast,) = (f for f in payload.forecasts if f.horizon == horizon)
    (member,) = (m for m in forecast.members if m.seed == seed)
    return member


# --- CA1: caminho feliz com literais -------------------------------------------------


def test_happy_path_serves_the_recorded_grid_per_seed_and_horizon() -> None:
    use_case, _, reader = _serve()
    payload = use_case(_query())

    assert (payload.asset, payload.decision_date, payload.cohort_id, payload.model_version) == (
        _ASSET,
        _FRIDAY,
        _COHORT,
        _MODEL,
    )
    assert payload.quantile_levels == _LEVELS
    assert [f.horizon for f in payload.forecasts] == [1, 7]
    assert [f.target_date for f in payload.forecasts] == [date(2024, 3, 16), date(2024, 3, 22)]
    for forecast in payload.forecasts:
        assert [(m.seed, m.fold, m.run_id) for m in forecast.members] == [
            (1, "0", "f0s1"),
            (2, "0", "f0s2"),
        ]
    assert _member(payload, 1, 1).quantiles == _LITERAL_GRID
    # seed 2, h+1, fold 0: base = 2/512 + 1/4096
    assert _member(payload, 1, 2).quantiles == (
        -0.027099609375,
        -0.011474609375,
        0.004150390625,
        0.011962890625,
        0.035400390625,
    )
    assert reader.calls == [(_ASSET, _COHORT)]


def test_happy_path_intervals_are_literal_including_crossed_and_infinite() -> None:
    payload = _serve()[0](_query())
    literal = _member(payload, 1, 1).conformal
    assert (literal.status, literal.reason, literal.label, literal.variant) == (
        AVAILABLE,
        None,
        "rótulo c",
        _SPLIT,
    )
    outer, inner = literal.intervals
    # (q_lo - Q_lo, q_hi + Q_hi) com Q_lo = 2^-8 e Q_hi = 2^-9 (Q_lo != Q_hi)
    assert (outer.lower_level, outer.upper_level, outer.status, outer.gold_status) == (
        0.1,
        0.9,
        OK,
        OK,
    )
    assert (outer.lower, outer.upper) == (-0.03515625, 0.033203125)
    # par interno cruzado: servido sem correção nem rearranjo (I6)
    assert (inner.lower_level, inner.upper_level) == (0.25, 0.75)
    assert (inner.lower, inner.upper) == (0.0078125, -0.0078125)
    assert inner.lower > inner.upper

    infinite_outer = _member(payload, 1, 2).conformal.intervals[0]
    assert infinite_outer.status == OK
    assert (infinite_outer.lower, infinite_outer.upper) == (-0.029052734375, math.inf)


def test_happy_path_explainability_and_provenance_come_from_the_gold() -> None:
    payload = _serve()[0](_query())
    block = payload.explainability
    assert (block.status, block.reason, block.label, block.vsn_label) == (
        AVAILABLE,
        None,
        "rótulo h3",
        "rótulo vsn",
    )
    assert (block.shares, block.reading, block.vsn) == ((_SHARE,), _READING, (_VSN,))
    gold = payload.gold
    assert (gold.published, gold.generation_status, gold.candidate) == (True, "COMPLETED", _MODEL)
    assert gold.preregistration_ref == "config/preregistration/x-r3.toml"
    assert gold.finished_at == "2026-10-21T12:00:00+00:00"


def test_requested_subset_keeps_the_fixed_order() -> None:
    payload = _serve()[0](_query(horizons=(7, 1), seeds=(2,)))
    assert [f.horizon for f in payload.forecasts] == [1, 7]
    assert [[m.seed for m in f.members] for f in payload.forecasts] == [[2], [2]]


# --- CA1/CA2: ligação pedido -> run --------------------------------------------------


def test_overlap_of_test_k_and_calib_k_plus_1_is_served_by_the_test_run_of_fold_k() -> None:
    payload = _serve()[0](_query(_OVERLAP))
    assert {m.fold for f in payload.forecasts for m in f.members} == {"0"}


def test_date_only_in_calib_is_not_found() -> None:
    with pytest.raises(NoServedDataError, match="decisão 2024-03-08"):
        _serve()[0](_query(_ONLY_CALIB))


def test_last_sessions_have_no_h7_but_h1_alone_is_served() -> None:
    use_case = _serve()[0]
    with pytest.raises(NoServedDataError, match=r"\(seed 1, h\+7\), \(seed 2, h\+7\)"):
        use_case(_query(_LAST))
    payload = use_case(_query(_LAST, horizons=(1,)))
    assert [f.horizon for f in payload.forecasts] == [1]
    assert {m.fold for m in payload.forecasts[0].members} == {"1"}


def test_member_of_fold_1_uses_the_unit_of_fold_1() -> None:
    payload = _serve()[0](_query(_LAST, horizons=(1,)))
    member = _member(payload, 1, 1)
    assert (member.fold, member.run_id) == ("1", "f1s1")
    outer = member.conformal.intervals[0]
    # seed 1, h+1, fold 1: base = 1/512 + 1/4096 + 1/8192; Q_lo = 2^-4, Q_hi = 2^-9
    assert (outer.status, outer.lower, outer.upper) == (OK, -0.0914306640625, 0.0355224609375)


# --- CA2: 404 com o que faltou ---------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "missing"),
    [
        (_query(asset="MSFT"), "ativo 'MSFT'"),
        (_query(horizons=(1, 3)), r"horizonte\(s\) \[3\] fora do cohort"),
        (_query(seeds=(9,)), r"seed\(s\) \[9\] fora do cohort"),
        (_query(date(2023, 1, 2)), "decisão 2023-01-02 sem linha de teste"),
        (_query(date(2024, 3, 16)), "decisão 2024-03-16 sem linha de teste"),  # sábado
    ],
)
def test_not_found_says_what_is_missing(query: ServeInferenceQuery, missing: str) -> None:
    with pytest.raises(NoServedDataError, match=missing) as info:
        _serve()[0](query)
    assert isinstance(info.value, NotFoundError)
    assert str(info.value).startswith(f"{NO_SERVED_DATA}: ")


# --- CA7: silver inconsistente -> ApplicationError ------------------------------------


def _rows_with(
    *,
    dim: list[dict[str, object]] | None = None,
    extra_facts: Sequence[dict[str, object]] = (),
    keep: object = None,
) -> dict[str, list[dict[str, object]]]:
    rows = _silver_rows()
    if dim is not None:
        rows["dim_run"] = dim
    facts = rows["fact_oos_predictions"]
    if callable(keep):
        facts = [row for row in facts if keep(row)]
    rows["fact_oos_predictions"] = facts + list(extra_facts)
    return rows


def _is_literal_point(row: Mapping[str, object]) -> bool:
    return (
        row["run_id"] == "f0s1"
        and row["horizon"] == 1
        and row["split"] == "test"
        and row["timestamp_utc"] == _ts(_FRIDAY)
    )


def _second_run_dim() -> list[dict[str, object]]:
    return [*_dim_rows(), {**_dim_rows()[0], "run_id": "dup", "fold": "9"}]


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (_rows_with(dim=[]), "não tem runs do cohort .*confira o DATA_ROOT"),
        (
            _rows_with(dim=[r for r in _dim_rows() if r["model_version"] != _MODEL]),
            "não tem runs do cohort",
        ),
        (_rows_with(dim=[r for r in _dim_rows() if r["seed"] != _SEED_2]), r"seed\(s\) \[2\]"),
        (
            _rows_with(
                dim=[{**r, "fold": None} if r["run_id"] == "f1s2" else r for r in _dim_rows()]
            ),
            "run f1s2 do candidato sem fold",
        ),
        (
            _rows_with(
                dim=_second_run_dim(), extra_facts=_fact_rows(("dup", 1, 9), "test", _FRIDAY, 1)
            ),
            r"2 runs de teste \(\['dup', 'f0s1'\]\) para a seed 1, h\+1",
        ),
        (
            _rows_with(
                keep=lambda r: not (_is_literal_point(r) and r["quantile_level"] == _LEVELS[3])
            ),
            r"grade incompleta, faltam os níveis \[0.75\]",
        ),
        (
            _rows_with(extra_facts=_fact_rows(("f0s1", 1, 0), "test", _FRIDAY, 1)[:1]),
            r"nível 0.1 repetido",
        ),
        (
            _rows_with(
                extra_facts=[
                    {**_fact_rows(("f0s1", 1, 0), "test", _FRIDAY, 1)[0], "quantile_level": 0.3}
                ]
            ),
            r"nível 0.3 fora da grade",
        ),
        (
            _rows_with(
                keep=lambda r: not (r["run_id"] == "f0s2" and r["timestamp_utc"] == _ts(_FRIDAY)),
                extra_facts=[
                    {**row, "target_timestamp_utc": _ts(date(2024, 3, 18))}
                    for row in _fact_rows(("f0s2", 2, 0), "test", _FRIDAY, 1)
                ]
                + _fact_rows(("f0s2", 2, 0), "test", _FRIDAY, 7),
            ),
            r"h\+1, decisão 2024-03-15: datas-alvo divergentes entre seeds",
        ),
    ],
    ids=[
        "zero-runs",
        "only-baseline-runs",
        "seed-without-run",
        "run-without-fold",
        "two-runs-at-the-point",
        "incomplete-grid",
        "repeated-level",
        "level-outside-grid",
        "target-date-diverges-across-seeds",
    ],
)
def test_inconsistent_silver_is_an_application_error(
    rows: dict[str, list[dict[str, object]]], message: str
) -> None:
    with pytest.raises(ApplicationError, match=message):
        _serve(rows=rows)[0](_query())


def test_target_dates_diverging_inside_one_run_are_an_application_error() -> None:
    rows = _rows_with(
        keep=lambda r: not (_is_literal_point(r) and r["quantile_level"] == _LEVELS[4]),
        extra_facts=[
            {
                **_fact_rows(("f0s1", 1, 0), "test", _FRIDAY, 1)[-1],
                "target_timestamp_utc": _ts(date(2024, 3, 19)),
            }
        ],
    )
    with pytest.raises(ApplicationError, match="datas-alvo divergentes"):
        _serve(rows=rows)[0](_query())


def test_a_single_missing_tail_is_an_application_error() -> None:
    gold = _gold(corrections=_corrections(drop=[("0", 1, 1, (0.25, 0.75), UPPER)]))
    with pytest.raises(ApplicationError, match=r"uma cauda só \(\['lower'\]\)"):
        _serve(gold=gold)[0](_query())


def test_a_repeated_tail_is_an_application_error() -> None:
    gold = _gold(corrections=(*_corrections(), _correction("0", 1, 1, (0.1, 0.9), LOWER)))
    with pytest.raises(ApplicationError, match="cauda lower repetida"):
        _serve(gold=gold)[0](_query())


@pytest.mark.parametrize(
    ("field", "value"),
    [("timestamp_utc", "15/03/2024"), ("value_guardrail", None), ("value_guardrail", math.nan)],
)
def test_value_error_from_read_data_becomes_application_error(field: str, value: object) -> None:
    rows = _rows_with(
        keep=lambda r: not _is_literal_point(r),
        extra_facts=[
            {**row, field: value} if row["quantile_level"] == _LEVELS[2] else row
            for row in _fact_rows(("f0s1", 1, 0), "test", _FRIDAY, 1)
        ],
    )
    with pytest.raises(ApplicationError, match="dado gravado inconsistente") as info:
        _serve(rows=rows)[0](_query())
    assert isinstance(info.value.__cause__, ValueError)


def test_gold_reader_error_propagates() -> None:
    silver = FakeSilverTableReader(_silver_rows())
    reader = InMemoryServingGoldReader({}, error=ApplicationError("geração corrompida"))
    with pytest.raises(ApplicationError, match="geração corrompida"):
        ServeInference(scope=_scope(), silver=silver, gold=reader)(_query())


# --- CA6: estados do intervalo -------------------------------------------------------


@pytest.mark.parametrize("status", ["undefined", "error"])
def test_non_ok_tail_makes_the_interval_unavailable_with_the_gold_status(status: str) -> None:
    overrides: dict[_Key, dict[str, object]] = {
        ("0", 1, 1, (0.1, 0.9), UPPER): {
            "status": status,
            "reason": f"motivo {status}",
            "correction": None,
            "n": None,
            "rank": None,
        }
    }
    payload = _serve(gold=_gold(corrections=_corrections(overrides)))[0](_query())
    outer, inner = _member(payload, 1, 1).conformal.intervals
    assert (outer.status, outer.gold_status, outer.reason, outer.lower, outer.upper) == (
        UNAVAILABLE,
        status,
        f"motivo {status}",
        None,
        None,
    )
    assert (inner.status, inner.lower, inner.upper) == (OK, 0.0078125, -0.0078125)


def test_missing_unit_is_unavailable_and_other_pairs_stay_ok() -> None:
    drop = [("0", 1, 1, (0.25, 0.75), LOWER), ("0", 1, 1, (0.25, 0.75), UPPER)]
    payload = _serve(gold=_gold(corrections=_corrections(drop=drop)))[0](_query())
    outer, inner = _member(payload, 1, 1).conformal.intervals
    assert (inner.status, inner.gold_status, inner.reason) == (
        UNAVAILABLE,
        None,
        "unidade ausente na geração gold",
    )
    assert (outer.status, outer.lower, outer.upper) == (OK, -0.03515625, 0.033203125)


# --- CA3: blocos do gold ---------------------------------------------------------------


def _assert_grid_served(payload: InferencePayload) -> None:
    assert _member(payload, 1, 1).quantiles == _LITERAL_GRID
    assert [f.horizon for f in payload.forecasts] == [1, 7]


def _conformal_states(payload: InferencePayload) -> set[tuple[str, str | None, int]]:
    return {
        (m.conformal.status, m.conformal.reason, len(m.conformal.intervals))
        for f in payload.forecasts
        for m in f.members
    }


def test_unpublished_gold_serves_the_grid_with_both_blocks_unavailable() -> None:
    gold = ServingGold.unpublished(reason="gold não publicado para o cohort x", **_LABELS)
    payload = _serve(gold=gold)[0](_query())
    _assert_grid_served(payload)
    assert _conformal_states(payload) == {(UNAVAILABLE, "gold não publicado para o cohort x", 0)}
    block = payload.explainability
    assert (block.status, block.reason, block.shares, block.reading, block.vsn) == (
        UNAVAILABLE,
        "gold não publicado para o cohort x",
        (),
        None,
        (),
    )
    labels = {m.conformal.label for f in payload.forecasts for m in f.members}
    assert (labels, block.label, block.vsn_label) == ({"rótulo c"}, "rótulo h3", "rótulo vsn")
    assert payload.gold.published is False
    assert payload.gold.generation_status is payload.gold.candidate is None


def test_blocked_gold_is_repassed() -> None:
    payload = _serve(gold=_blocked())[0](_query())
    _assert_grid_served(payload)
    assert _conformal_states(payload) == {(UNAVAILABLE, "geração gold BLOCKED", 0)}
    assert payload.explainability.reason == "geração gold BLOCKED"
    assert payload.gold.generation_status == "BLOCKED"


def test_gold_without_conformal_block_keeps_explainability() -> None:
    payload = _serve(gold=_no_conformal())[0](_query())
    assert _conformal_states(payload) == {(UNAVAILABLE, "geração sem bloco [conformal]", 0)}
    assert payload.explainability.status == AVAILABLE


def test_gold_of_another_candidate_makes_both_blocks_unavailable() -> None:
    payload = _serve(gold=_gold(candidate="gbm_quantile"))[0](_query())
    _assert_grid_served(payload)
    reason = "geração gold de outro candidato: gbm_quantile (servido: tft_quantile)"
    assert _conformal_states(payload) == {(UNAVAILABLE, reason, 0)}
    block = payload.explainability
    assert (block.status, block.reason, block.shares, block.reading) == (
        UNAVAILABLE,
        reason,
        (),
        None,
    )
    assert payload.gold.candidate == "gbm_quantile"


def test_precedence_blocked_wins_over_another_candidate() -> None:
    payload = _serve(gold=_blocked(candidate="gbm_quantile"))[0](_query())
    assert _conformal_states(payload) == {(UNAVAILABLE, "geração gold BLOCKED", 0)}
    assert payload.explainability.reason == "geração gold BLOCKED"


def test_precedence_another_candidate_wins_over_a_missing_block() -> None:
    payload = _serve(gold=_no_conformal(candidate="gbm_quantile"))[0](_query())
    reason = "geração gold de outro candidato: gbm_quantile (servido: tft_quantile)"
    assert _conformal_states(payload) == {(UNAVAILABLE, reason, 0)}
    assert payload.explainability.reason == reason


# --- CA13: cegamento, só leitura e determinismo --------------------------------------


def test_only_dim_run_and_fact_oos_predictions_are_read_by_partition() -> None:
    use_case, silver, _ = _serve()
    use_case(_query())
    assert silver.reads == [
        ("silver", "dim_run", {"asset": _ASSET, "parent_sweep_id": _COHORT}),
        (
            "silver",
            "fact_oos_predictions",
            {"asset": _ASSET, "feature_set_name": _FS, "year": 2024},
        ),
    ]


@pytest.mark.parametrize("port", [SilverTableReader, ServingGoldReader])
def test_ports_used_have_only_read(port: type) -> None:
    assert [name for name in vars(port) if not name.startswith("_")] == ["read"]


def test_two_equal_requests_give_equal_payloads() -> None:
    use_case = _serve()[0]
    assert use_case(_query()) == use_case(_query())


def test_baseline_rows_in_the_same_cohort_are_not_served() -> None:
    payload = _serve()[0](_query())
    assert "gbm0" not in {m.run_id for f in payload.forecasts for m in f.members}


# --- validação do escopo e da consulta -------------------------------------------------


def test_scope_pairs_go_from_the_outermost_to_the_innermost() -> None:
    assert _scope().pairs == ((0.1, 0.9), (0.25, 0.75))
    assert _scope(quantile_levels=(0.5,)).pairs == ()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"cohort_id": ""}, "cohort_id"),
        ({"asset": ""}, "asset"),
        ({"feature_set_name": ""}, "feature_set_name"),
        ({"model_version": ""}, "model_version"),
        ({"horizons": ()}, "horizons must not be empty"),
        ({"horizons": (7, 1)}, "horizons must be unique and increasing"),
        ({"horizons": (1, 1)}, "horizons must be unique and increasing"),
        ({"horizons": (0, 1)}, "horizons must be >= 1"),
        ({"horizons": (True,)}, "horizons must be integers"),
        ({"seeds": (2, 1)}, "seeds must be unique and increasing"),
        ({"quantile_levels": ()}, "quantile_levels must not be empty"),
        ({"quantile_levels": (0.1, 0.5, 0.5, 0.9)}, "strictly increasing"),
        ({"quantile_levels": (0.0, 0.5, 1.0)}, r"lie in \(0, 1\)"),
        ({"quantile_levels": (0.1, 0.4, 0.9)}, "median 0.5"),
        ({"quantile_levels": (0.1, 0.5, 0.6, 0.9)}, "median 0.5"),
        ({"quantile_levels": (0.1, 0.5, 0.8)}, "symmetric"),
    ],
)
def test_scope_refuses_the_invalid(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _scope(**overrides)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"horizons": ()}, "horizons must not be empty"),
        ({"seeds": ()}, "seeds must not be empty"),
        ({"horizons": (1, 1)}, "horizons must not repeat"),
        ({"seeds": (2, 2)}, "seeds must not repeat"),
    ],
)
def test_query_refuses_empty_or_repeated(fields: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ServeInferenceQuery(asset=_ASSET, decision_date=_FRIDAY, **fields)  # type: ignore[arg-type]


def test_payload_blocks_refuse_incoherent_states() -> None:
    payload = _serve()[0](_query())
    member = _member(payload, 1, 1)
    interval = member.conformal.intervals[0]
    with pytest.raises(ValueError, match="ok interval needs both limits"):
        replace(interval, upper=None)
    with pytest.raises(ValueError, match="unavailable interval carries no limits"):
        replace(interval, status=UNAVAILABLE)
    with pytest.raises(ValueError, match="interval status"):
        replace(interval, status="partial")
    with pytest.raises(ValueError, match="gold_status"):
        replace(interval, gold_status="skipped")
    with pytest.raises(ValueError, match="NaN"):
        replace(interval, lower=math.nan)
    with pytest.raises(ValueError, match="unavailable conformal block carries no records"):
        replace(member.conformal, status=UNAVAILABLE, reason="x")
    with pytest.raises(ValueError, match="unavailable conformal block needs a reason"):
        replace(member.conformal, status=UNAVAILABLE, intervals=())
    with pytest.raises(ValueError, match="available conformal block carries no reason"):
        replace(member.conformal, reason="x")
    with pytest.raises(ValueError, match="conformal label must not be empty"):
        replace(member.conformal, label="")
    with pytest.raises(ValueError, match="variant must be"):
        replace(member.conformal, variant=_NEXCP)
    with pytest.raises(ValueError, match="explainability_status must be one of"):
        replace(payload.explainability, status="partial")
    with pytest.raises(ValueError, match="vsn_label"):
        replace(payload.explainability, vsn_label="")
