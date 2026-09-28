"""Unit test do VO `HitSequence` e de `count_transitions` (primitivo único da 6.3).

Prova (concept 6.3 A1, I1, I2, I4, I5, I8, C1; ADRs 6.3.0001 item 1, 6.3.0004):

- um `ValueError` por caso de C1, inclusive os ramos DGT e o `bool`-vs-`int`;
- taxa nominal exata pela regra do `kind`, divergente ergue;
- contagens com lacunas e transições só entre posições consecutivas observadas;
- partição DGT (h = 3, T = 8 e T = 2; h = 1 → `(self,)`; sub-série não re-particiona);
- o horizonte passado é preservado; o VO é frozen.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    pair_miscoverage,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    HitSequence,
    count_transitions,
    violation_rate_for,
)

HitSequenceFactory = Callable[..., HitSequence]

T, F = True, False
# Fixture com lacunas do A1: pares (0,1) F→T, (3,4) T→T, (6,7) F→T; os que tocam None
# não contam.
_GAPPED = (F, T, None, T, T, None, F, T)
_GAPPED_OBSERVED = 6
_GAPPED_VIOLATIONS = 4
_GAPPED_TRANSITIONS = (0, 2, 0, 1)
_H3 = 3
_H7 = 7


# --- C1 — um caso por ramo ---------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("violations", "kwargs", "match"),
    [
        ((T, F), {"target_timestamps": ("2024-01-02",)}, "must align 1:1"),
        ((), {}, r"at least one position \(T >= 1\)"),
        (
            (T, F),
            {"target_timestamps": ("2024-01-02", "2024-01-02")},
            "position 1 has '2024-01-02' after '2024-01-02'",
        ),
        ((T, F), {"kind": "lower_tail", "violation_rate": 0.05}, "kind must be a HitKind"),
        (
            (T,),
            {"kind": HitKind.INTERVAL, "levels": (0.05,), "violation_rate": 0.1},
            r"levels must have 2 element\(s\) for kind=interval",
        ),
        (
            (T,),
            {"levels": (0.05, 0.95), "violation_rate": 0.05},
            r"levels must have 1 element\(s\) for kind=lower_tail",
        ),
        (
            (T,),
            {"kind": HitKind.INTERVAL, "levels": (0.6, 0.4)},
            r"violation_rate must be in \(0, 1\)",
        ),
        ((T, 1), {}, r"violations\[1\] must be a bool or None, got 1"),
        ((0, F), {}, r"violations\[0\] must be a bool or None, got 0"),
        ((T, "x"), {}, r"violations\[1\] must be a bool or None, got 'x'"),
        ((T,), {"tolerance": -1.0}, r"HitSequence\.tolerance must be a finite number >= 0"),
        ((T,), {"tolerance": math.nan}, r"HitSequence\.tolerance must be a finite number >= 0"),
        ((T,), {"tolerance": True}, r"HitSequence\.tolerance must be a finite number >= 0"),
        ((T,), {"degeneracy_rate": -0.1}, r"degeneracy_rate must be in \[0, 1\]"),
        ((T,), {"degeneracy_rate": 1.5}, r"degeneracy_rate must be in \[0, 1\]"),
        ((T, None), {"includes_degenerate": True}, "includes_degenerate=True allows gaps only"),
        ((T, None), {"degeneracy_rate": 0.25}, r"degeneracy_rate must be n_None / T = 0\.5"),
        ((T, F), {"horizon": 2, "dgt_offset": 0}, "dgt_offset and dgt_step must be both set"),
        ((T, F), {"horizon": 2, "dgt_step": 2}, "dgt_offset and dgt_step must be both set"),
        ((T, F), {"horizon": 2, "dgt_offset": 2, "dgt_step": 2}, r"dgt_offset must be in \[0"),
        ((T, F), {"horizon": 2, "dgt_offset": -1, "dgt_step": 2}, r"dgt_offset must be in \[0"),
        ((T, F), {"horizon": 3, "dgt_offset": 0, "dgt_step": 2}, "dgt_step must equal horizon=3"),
        ((T, F), {"horizon": 1, "dgt_offset": 0, "dgt_step": 1}, "dgt_step must be >= 2"),
    ],
    ids=[
        "lengths-differ",
        "empty",
        "timestamps-not-increasing",
        "kind-not-hitkind",
        "interval-levels-size",
        "tail-levels-size",
        "rate-outside-unit-interval",
        "int-one-not-bool",
        "int-zero-not-bool",
        "str-element",
        "tolerance-negative",
        "tolerance-nan",
        "tolerance-bool",
        "degeneracy-rate-negative",
        "degeneracy-rate-above-one",
        "includes-degenerate-with-partial-gaps",
        "masked-degeneracy-rate-not-gap-fraction",
        "dgt-only-offset",
        "dgt-only-step",
        "dgt-offset-equals-step",
        "dgt-offset-negative",
        "dgt-step-not-horizon",
        "dgt-step-one",
    ],
)
def test_hitseq_invalid_construction_raises(
    make_hit_sequence: HitSequenceFactory,
    violations: tuple[object, ...],
    kwargs: dict[str, object],
    match: str,
) -> None:
    """A1/C1: cada ramo da validação ergue `ValueError` nomeando campo ou posição."""
    with pytest.raises(ValueError, match=match):
        make_hit_sequence(violations, **kwargs)


@pytest.mark.unit
def test_hitseq_is_frozen(make_hit_sequence: HitSequenceFactory) -> None:
    """A1: o VO é frozen."""
    sequence = make_hit_sequence((T, F))

    with pytest.raises(dataclasses.FrozenInstanceError):
        sequence.horizon = 2  # type: ignore[misc]


# --- I2 — taxa nominal pela regra do kind ---------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "levels", "expected"),
    [
        (HitKind.INTERVAL, (0.05, 0.95), pair_miscoverage(0.05)),
        (HitKind.LOWER_TAIL, (0.02,), 0.02),
        (HitKind.UPPER_TAIL, (0.98,), 1 - 0.98),
    ],
    ids=["interval", "lower-tail", "upper-tail"],
)
def test_kind_rate_is_the_grid_rule_exactly(
    make_hit_sequence: HitSequenceFactory,
    kind: HitKind,
    levels: tuple[float, ...],
    expected: float,
) -> None:
    """A1/I2: `violation_rate` = `pair_miscoverage(τ_l)` / τ / 1 - τ, por igualdade exata."""
    sequence = make_hit_sequence((T, F), kind=kind, levels=levels)

    assert violation_rate_for(kind, levels) == expected
    assert sequence.violation_rate == expected
    assert sequence.kind is kind


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "levels", "rate"),
    [
        (HitKind.INTERVAL, (0.05, 0.95), 1 - (0.95 - 0.05)),  # a forma larga diverge em float
        (HitKind.LOWER_TAIL, (0.02,), 0.98),  # orientação "hit dentro" trocada
        (HitKind.UPPER_TAIL, (0.98,), 0.02),  # 0.02 != 1 - 0.98 em float64
    ],
    ids=["interval-width-form", "lower-tail-complement", "upper-tail-rounded"],
)
def test_kind_rate_divergent_raises(
    make_hit_sequence: HitSequenceFactory,
    kind: HitKind,
    levels: tuple[float, ...],
    rate: float,
) -> None:
    """A1/C1: taxa diferente (exato) da regra do `kind` ergue."""
    with pytest.raises(ValueError, match="violation_rate must equal the"):
        make_hit_sequence((T, F), kind=kind, levels=levels, violation_rate=rate)


# --- I4/I5 — lacunas e transições -----------------------------------------------------------------


@pytest.mark.unit
def test_mask_gaps_counts_only_observed_positions(make_hit_sequence: HitSequenceFactory) -> None:
    """A1/I4: `None` é lacuna — n = posições observadas (6 de 8), x = violações (4)."""
    sequence = make_hit_sequence(_GAPPED)

    assert len(sequence.violations) == len(_GAPPED)
    assert sequence.n_observed == _GAPPED_OBSERVED
    assert sequence.n_violations == _GAPPED_VIOLATIONS
    assert sequence.degeneracy_rate == 2 / len(_GAPPED)


@pytest.mark.unit
def test_gap_transitions_skip_pairs_touching_a_gap(make_hit_sequence: HitSequenceFactory) -> None:
    """A1/I5: (n00, n01, n10, n11) = (0, 2, 0, 1) — só pares consecutivos observados;
    o VO delega a `count_transitions` (dono único)."""
    sequence = make_hit_sequence(_GAPPED)

    assert count_transitions(_GAPPED) == _GAPPED_TRANSITIONS
    assert sequence.transition_counts == _GAPPED_TRANSITIONS


@pytest.mark.unit
def test_gap_transitions_without_gaps_is_the_pure_convention() -> None:
    """ADR 6.3.0004 item 2: sem lacunas, t = 2..T — T - 1 pares, um por tipo aqui."""
    violations = (F, F, T, T, F)

    counts = count_transitions(violations)

    assert counts == (1, 1, 1, 1)
    assert sum(counts) == len(violations) - 1


# --- I8 — partição DGT --------------------------------------------------------------------------


@pytest.mark.unit
def test_dgt_partition_h3_t8_positions_gaps_and_identity(
    make_hit_sequence: HitSequenceFactory,
) -> None:
    """A1/I8: h = 3, T = 8 → {0,3,6}, {1,4,7}, {2,5}, lacunas preservadas, offset/step,
    horizonte e timestamps certos; união disjunta (por posição) = a sequência."""
    sequence = make_hit_sequence(_GAPPED, horizon=_H3)

    parts = sequence.dgt_partition()

    positions = ((0, 3, 6), (1, 4, 7), (2, 5))
    assert len(parts) == _H3
    covered: list[int] = []
    for offset, (part, indices) in enumerate(zip(parts, positions, strict=True)):
        assert part.dgt_offset == offset
        assert part.dgt_step == _H3
        assert part.horizon == _H3
        assert part.violations == tuple(_GAPPED[i] for i in indices)
        assert part.target_timestamps == tuple(sequence.target_timestamps[i] for i in indices)
        assert (part.kind, part.levels, part.violation_rate) == (
            sequence.kind,
            sequence.levels,
            sequence.violation_rate,
        )
        assert (part.tolerance, part.degeneracy_rate, part.includes_degenerate) == (
            sequence.tolerance,
            sequence.degeneracy_rate,
            sequence.includes_degenerate,
        )
        covered.extend(indices)
    assert sorted(covered) == list(range(len(_GAPPED)))
    assert parts[2].violations == (None, None)  # posições 2 e 5: lacunas preservadas


@pytest.mark.unit
@pytest.mark.parametrize(
    ("violations", "horizon", "expected"),
    [
        ((T, F, F, F, None, T, F, T), _H3, ((T, F, F), (F, None, T), (F, T))),
        ((T, T, F, None, F), 2, ((T, F, F), (T, None))),
    ],
    ids=["h3-asymmetric", "h2-asymmetric"],
)
def test_dgt_partition_keeps_position_order_on_asymmetric_subseries(
    make_hit_sequence: HitSequenceFactory,
    violations: tuple[bool | None, ...],
    horizon: int,
    expected: tuple[tuple[bool | None, ...], ...],
) -> None:
    """A1/I8: sub-séries não-palíndromas (h = 3 e h = 2) — cada uma na ordem das
    posições j, j + h, …; uma partição que invertesse ou reordenasse as posições falha."""
    sequence = make_hit_sequence(violations, horizon=horizon)

    parts = sequence.dgt_partition()

    assert tuple(part.violations for part in parts) == expected
    assert all(part.violations != part.violations[::-1] for part in parts)
    for offset, part in enumerate(parts):
        assert part.target_timestamps == sequence.target_timestamps[offset::horizon]


@pytest.mark.unit
def test_dgt_partition_h3_t2_gives_two_subseries(make_hit_sequence: HitSequenceFactory) -> None:
    """A1/I8: min(h, T) sub-séries não-vazias — h = 3, T = 2 → 2."""
    sequence = make_hit_sequence((T, F), horizon=_H3)

    parts = sequence.dgt_partition()

    assert [part.violations for part in parts] == [(T,), (F,)]
    assert [part.dgt_offset for part in parts] == [0, 1]


@pytest.mark.unit
def test_dgt_partition_h1_returns_self(make_hit_sequence: HitSequenceFactory) -> None:
    """A1/I8: h = 1 → `(self,)` (não há sub-série de passo 1)."""
    sequence = make_hit_sequence(_GAPPED)

    assert sequence.dgt_partition() == (sequence,)


@pytest.mark.unit
def test_dgt_partition_of_subseries_raises(make_hit_sequence: HitSequenceFactory) -> None:
    """A1/I8: chamar `dgt_partition` numa sub-série ergue (sem re-partição)."""
    sub = make_hit_sequence(_GAPPED, horizon=_H3).dgt_partition()[0]

    with pytest.raises(ValueError, match="cannot be applied to a DGT sub-series"):
        sub.dgt_partition()


# --- I1 — horizonte ------------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("horizon", [1, _H7])
def test_hitseq_horizon_is_preserved(make_hit_sequence: HitSequenceFactory, horizon: int) -> None:
    """A1/I1: o horizonte passado é o do VO."""
    assert make_hit_sequence((T, F), horizon=horizon).horizon == horizon


@pytest.mark.unit
@pytest.mark.parametrize(
    ("horizon", "match"),
    [
        (0, "horizon must be an int >= 1"),
        (True, "horizon must be an int >= 1"),
        (1.0, "horizon must be an int >= 1"),
    ],
    ids=["zero", "bool", "float"],
)
def test_hitseq_horizon_invalid_raises(
    make_hit_sequence: HitSequenceFactory, horizon: int, match: str
) -> None:
    """A1/C1: `horizon = 0` (e não-`int`) ergue."""
    with pytest.raises(ValueError, match=match):
        make_hit_sequence((T, F), horizon=horizon)


@pytest.mark.unit
def test_hitseq_all_none_variant_is_allowed(
    make_hit_sequence: HitSequenceFactory,
) -> None:
    """I4/C7: a variante sem lacunas de uma série 100 % degenerada é toda `None`."""
    sequence = make_hit_sequence((None, None, None), includes_degenerate=True)

    assert sequence.n_observed == 0
    assert sequence.transition_counts == (0, 0, 0, 0)
