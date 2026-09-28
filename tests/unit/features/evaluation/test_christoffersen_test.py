"""Unit test do `ChristoffersenTest` (trio puro + leitura Kupiec), do primitivo e do
LR_uc de 3 estados (Task 08; o Monte Carlo está em `test_christoffersen_monte_carlo.py`).

Prova (concept 6.3 A6, I2, I5, I6, I8, I13, C4, C6, C9; ADRs 6.3.0001 itens 4, 7, 8
e Implementation notes, 6.3.0004 item 2) com fixtures analíticas: as log-somas dos
valores esperados são escritas **no teste** com `math.log` (ADR 0.0.0021) — o oráculo
R entra só nos testes de integração (Task 11).
"""

from __future__ import annotations

import dataclasses
import inspect
import math
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services import (
    christoffersen_test as christoffersen_test_module,
)
from financial_forecasting.features.evaluation.domain.services.chi_square import (
    LR_NEGATIVE_FLOOR,
    chi_square_sf,
)
from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenReport,
    ChristoffersenStatistics,
    ChristoffersenTest,
    IndependenceStatus,
    christoffersen_statistics,
    lr_uc_three_state,
)
from financial_forecasting.features.evaluation.domain.services.hit_sequences import (
    HitSequences,
)
from financial_forecasting.features.evaluation.domain.services.kupiec_pof import (
    kupiec_pof,
    xlogy,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitKind,
    HitSequence,
)

HitSequenceFactory = Callable[..., HitSequence]

T, F = True, False
# Tolerância declarada (ADR 0.0.0021): identidade de float64 entre formas algébricas.
_ABS_TOL = 1e-12
_P = 0.2
_P_LEVELS = (_P,)
# Fixture do A6: 12 posições, sem lacunas, I_1 = 0. Transições (n00, n01, n10, n11) =
# (4, 3, 3, 1); 4 violações (posições 2, 6, 7, 10), todas dentro do n_1 puro.
_HAND = (F, F, T, F, F, F, T, T, F, F, T, F)
_HAND_TRANSITIONS = (4, 3, 3, 1)
_HAND_VIOLATIONS = 4
# Piso I13 do LR_ind (technical §1): transições (1, 2, 3, 6), bruto ≈ -1.78e-15.
_FLOOR_SEQUENCE = (T, T, T, T, T, T, T, F, F, T, F, T, F)
_H7 = 7


def _close(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= _ABS_TOL


def _hand_report(make_hit_sequence: HitSequenceFactory) -> ChristoffersenReport:
    sequence = make_hit_sequence(_HAND, levels=_P_LEVELS)
    return ChristoffersenTest.evaluate(sequence, min_violations=0)


# --- A6 — trio à mão ------------------------------------------------------------------------


@pytest.mark.unit
def test_trio_hand_matches_log_sums_written_here(make_hit_sequence: HitSequenceFactory) -> None:
    """A6: n_ij e as três LR da fixture de 12 posições, pelas log-somas escritas aqui."""
    report = _hand_report(make_hit_sequence)
    stats = report.statistics

    # LR_uc puro: 4 violações em 11 pares; LR_ind: π01 = 3/7, π11 = 1/4, π = 4/11.
    lr_uc = -2 * (
        7 * math.log(1 - _P) + 4 * math.log(_P) - (7 * math.log(7 / 11) + 4 * math.log(4 / 11))
    )
    lr_ind = -2 * (
        7 * math.log(7 / 11)
        + 4 * math.log(4 / 11)
        - (4 * math.log(4 / 7) + 3 * math.log(3 / 7) + 3 * math.log(3 / 4) + math.log(1 / 4))
    )
    assert stats.transitions == _HAND_TRANSITIONS
    assert (stats.n_observed, stats.n_violations) == (len(_HAND), _HAND_VIOLATIONS)
    assert stats.independence_status is IndependenceStatus.APPLICABLE
    assert stats.lr_uc is not None and _close(stats.lr_uc, lr_uc)
    assert stats.lr_ind is not None and _close(stats.lr_ind, lr_ind)
    assert stats.lr_cc is not None and _close(stats.lr_cc, lr_uc + lr_ind)


@pytest.mark.unit
def test_pure_convention_uses_pairs_not_all_positions(
    make_hit_sequence: HitSequenceFactory,
) -> None:
    """A6/I5: o LR_uc puro usa n = Σn_ij (11 pares) e n_1 = n01 + n11; a leitura Kupiec
    usa as 12 posições — valores diferentes, cada um igual ao seu `kupiec_pof`."""
    stats = _hand_report(make_hit_sequence).statistics

    assert stats.lr_uc == kupiec_pof(violations=4, observations=11, violation_rate=_P)
    assert stats.kupiec_pof == kupiec_pof(violations=4, observations=12, violation_rate=_P)
    assert stats.lr_uc != stats.kupiec_pof


@pytest.mark.unit
def test_lr_cc_identity_is_exact_and_matches_the_direct_form(
    make_hit_sequence: HitSequenceFactory,
) -> None:
    """A6/I5: `lr_cc == lr_uc + lr_ind` (igualdade exata do campo) e ≈ -2·log[L(p)/L(Π̂_1)]
    escrita direta (1e-12)."""
    stats = _hand_report(make_hit_sequence).statistics
    direct = -2 * (
        7 * math.log(1 - _P)
        + 4 * math.log(_P)
        - (4 * math.log(4 / 7) + 3 * math.log(3 / 7) + 3 * math.log(3 / 4) + math.log(1 / 4))
    )

    assert stats.lr_uc is not None and stats.lr_ind is not None and stats.lr_cc is not None
    assert stats.lr_cc == stats.lr_uc + stats.lr_ind
    assert _close(stats.lr_cc, direct)


@pytest.mark.unit
def test_n11_zero_is_applicable_with_the_cp2004_likelihood() -> None:
    """A6/I6: `[F, T, F, F, T, F]` → (1, 2, 2, 0), aplicável; LR_ind = C&P §4.1 com
    π̂11 = 0 (0^0 = 1): π01 = 2/3, π = 2/5."""
    stats = christoffersen_statistics(
        violations=(F, T, F, F, T, F), violation_rate=_P, min_violations=0
    )
    expected = -2 * (
        3 * math.log(3 / 5) + 2 * math.log(2 / 5) - (math.log(1 / 3) + 2 * math.log(2 / 3))
    )

    assert stats.transitions == (1, 2, 2, 0)
    assert stats.independence_status is IndependenceStatus.APPLICABLE
    assert stats.lr_ind is not None and _close(stats.lr_ind, expected)


@pytest.mark.unit
def test_first_observation_violation_is_outside_the_pure_n1() -> None:
    """A6/I5: I_1 = 1 — o n_1 puro (n01 + n11 = 1 em 7 pares) exclui a 1ª violação; o
    `kupiec_pof` (2 em 8 posições) a inclui; ambos conferidos à mão."""
    stats = christoffersen_statistics(
        violations=(T, F, F, T, F, F, F, F), violation_rate=_P, min_violations=0
    )
    pure = -2 * (6 * math.log(1 - _P) + math.log(_P) - (6 * math.log(6 / 7) + math.log(1 / 7)))
    pof = -2 * (
        6 * math.log(1 - _P) + 2 * math.log(_P) - (6 * math.log(6 / 8) + 2 * math.log(2 / 8))
    )

    assert stats.transitions == (4, 1, 2, 0)
    assert stats.lr_uc is not None and _close(stats.lr_uc, pure)
    assert stats.kupiec_pof is not None and _close(stats.kupiec_pof, pof)
    assert not _close(stats.lr_uc, stats.kupiec_pof)


# --- I5 — lacunas no primitivo e contagem única ---------------------------------------------


@pytest.mark.unit
def test_primitive_gaps_count_only_observed_pairs(make_hit_sequence: HitSequenceFactory) -> None:
    """A6/I5 (Checkpoint B T4): lacunas no primitivo — transições (0, 2, 0, 1), iguais às
    do VO; n = 6 observadas, x = 4; POF sobre as observadas."""
    gapped = (F, T, None, T, T, None, F, T)

    stats = christoffersen_statistics(violations=gapped, violation_rate=_P, min_violations=0)

    assert stats.transitions == (0, 2, 0, 1)
    assert stats.transitions == make_hit_sequence(gapped).transition_counts
    assert (stats.n_observed, stats.n_violations) == (6, 4)
    assert stats.kupiec_pof == kupiec_pof(violations=4, observations=6, violation_rate=_P)


@pytest.mark.unit
def test_single_counting_through_the_vo_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """A6/I5: o primitivo conta pela `count_transitions` do VO (dono único) — trocar o
    nome no namespace do módulo muda as transições."""
    monkeypatch.setattr(christoffersen_test_module, "count_transitions", lambda _: (1, 1, 1, 1))

    stats = christoffersen_statistics(
        violations=(F, T, F, F, T, F), violation_rate=_P, min_violations=0
    )

    assert stats.transitions == (1, 1, 1, 1)


# --- I6 — status e precedência --------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("violations", "min_violations", "status"),
    [
        ((T,), 0, IndependenceStatus.NO_TRANSITIONS),
        ((T, None, F, None, T), 0, IndependenceStatus.NO_TRANSITIONS),
        ((F, T, F, F, T, F), 3, IndependenceStatus.BELOW_MIN_VIOLATIONS),
        ((F, F, F, T), 1, IndependenceStatus.DEGENERATE_TRANSITION_MATRIX),
        ((T, F, F, F), 1, IndependenceStatus.DEGENERATE_TRANSITION_MATRIX),
        (_HAND, 0, IndependenceStatus.APPLICABLE),
    ],
    ids=["single", "gaps-break-all-pairs", "below-min", "empty-row", "empty-column", "applicable"],
)
def test_status_each_with_statistics_presence(
    violations: tuple[bool | None, ...], min_violations: int, status: IndependenceStatus
) -> None:
    """A6/I6/C6: um caso por status; LR_ind/LR_cc presentes só com APPLICABLE."""
    stats = christoffersen_statistics(
        violations=violations, violation_rate=_P, min_violations=min_violations
    )

    assert stats.independence_status is status
    applicable = status is IndependenceStatus.APPLICABLE
    assert (stats.lr_ind is not None) is applicable
    assert (stats.lr_cc is not None) is applicable


@pytest.mark.unit
@pytest.mark.parametrize(
    ("violations", "status"),
    [
        ((F,), IndependenceStatus.NO_TRANSITIONS),
        ((F, F, F), IndependenceStatus.BELOW_MIN_VIOLATIONS),
    ],
    ids=["no-transitions-before-below-min", "below-min-before-degenerate"],
)
def test_status_precedence(violations: tuple[bool, ...], status: IndependenceStatus) -> None:
    """A6/I6: vale o primeiro status da ordem (`[F, F, F]` tem coluna vazia, mas o
    mínimo de violações vem antes)."""
    stats = christoffersen_statistics(violations=violations, violation_rate=_P, min_violations=1)

    assert stats.independence_status is status


@pytest.mark.unit
def test_min_violations_base_counts_all_observed_violations() -> None:
    """A6/I6 (Checkpoint B T10): `[T, F, F, T, F]`, mínimo 2 → APPLICABLE — conta as
    2 violações observadas, embora n01 + n11 = 1."""
    stats = christoffersen_statistics(
        violations=(T, F, F, T, F), violation_rate=_P, min_violations=2
    )

    assert stats.transitions == (1, 1, 2, 0)
    assert stats.n_violations == 2  # noqa: PLR2004
    assert stats.independence_status is IndependenceStatus.APPLICABLE


@pytest.mark.unit
def test_all_masked_not_applicable(make_hit_sequence: HitSequenceFactory) -> None:
    """A6/C6/C7: sequência toda `None` → tudo `None`, NO_TRANSITIONS, p-valores `None`."""
    sequence = make_hit_sequence((None, None, None, None), includes_degenerate=True)

    report = ChristoffersenTest.evaluate(sequence, min_violations=0)

    stats = report.statistics
    assert (stats.n_observed, stats.n_violations, stats.transitions) == (0, 0, (0, 0, 0, 0))
    assert (stats.kupiec_pof, stats.lr_uc, stats.lr_ind, stats.lr_cc) == (None,) * 4
    assert stats.independence_status is IndependenceStatus.NO_TRANSITIONS
    assert (report.kupiec_pof_p_value, report.p_uc, report.p_ind, report.p_cc) == (None,) * 4


# --- I8 — multi-passo -----------------------------------------------------------------------


@pytest.mark.unit
def test_h7_descriptive_except_on_dgt_subseries(make_hit_sequence: HitSequenceFactory) -> None:
    """A6/I8: h = 7 → `independence_descriptive`; sub-série DGT de h = 7 → não."""
    sequence = make_hit_sequence(_HAND + _HAND, horizon=_H7)

    assert ChristoffersenTest.evaluate(sequence, min_violations=0).independence_descriptive
    sub = sequence.dgt_partition()[0]
    assert not ChristoffersenTest.evaluate(sub, min_violations=0).independence_descriptive


@pytest.mark.unit
def test_copies_identity_of_the_sequence(make_hit_sequence: HitSequenceFactory) -> None:
    """A6/D8: o relatório copia a identidade inteira (inclusive `dgt_offset`/`dgt_step` da
    sub-série) e grava `min_violations`; p-valores χ² das estatísticas."""
    sequence = make_hit_sequence(
        _HAND, kind=HitKind.UPPER_TAIL, levels=(0.95,), horizon=3, tolerance=0.001
    )
    sub = sequence.dgt_partition()[1]

    report = ChristoffersenTest.evaluate(sub, min_violations=1)

    assert (report.horizon, report.kind, report.levels, report.violation_rate) == (
        sub.horizon,
        sub.kind,
        sub.levels,
        sub.violation_rate,
    )
    assert (report.tolerance, report.degeneracy_rate, report.includes_degenerate) == (
        sub.tolerance,
        sub.degeneracy_rate,
        sub.includes_degenerate,
    )
    assert (report.dgt_offset, report.dgt_step) == (1, 3)
    assert report.min_violations == 1
    assert report.statistics == christoffersen_statistics(
        violations=sub.violations, violation_rate=sub.violation_rate, min_violations=1
    )


# --- I2 — invariância hits ↔ violações ------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("violations", "rate"),
    [
        (_HAND, _P),
        ((F, T, F, F, T, F, T, T, F, F), 0.05),
        ((T, F, T, F, F, T, F, F, F, T, T, F, F, F), 0.3),
    ],
    ids=["hand", "short", "long"],
)
def test_hits_invariance_with_complemented_rate(violations: tuple[bool, ...], rate: float) -> None:
    """A6/I2 (doc §7.1): hits "dentro" com taxa 1 - p dão os mesmos LR que as violações."""
    direct = christoffersen_statistics(violations=violations, violation_rate=rate, min_violations=0)
    hits = christoffersen_statistics(
        violations=tuple(not v for v in violations), violation_rate=1 - rate, min_violations=0
    )

    assert direct.independence_status is IndependenceStatus.APPLICABLE
    for name in ("kupiec_pof", "lr_uc", "lr_ind", "lr_cc"):
        a, b = getattr(direct, name), getattr(hits, name)
        assert a is not None and b is not None and _close(a, b), name


# --- I13 — piso do LR_ind -------------------------------------------------------------------


@pytest.mark.unit
def test_lr_ind_floor_clamps_negative_raw_value(make_hit_sequence: HitSequenceFactory) -> None:
    """A6/I13: transições (1, 2, 3, 6) — LR_ind bruto (mesma ordem de operações do
    serviço) na faixa do piso; o relatório traz `lr_ind == 0.0` e `p_ind == 1.0`."""
    n00, n01, n10, n11 = 1, 2, 3, 6
    pi, pi01, pi11 = (n01 + n11) / 12, n01 / (n00 + n01), n11 / (n10 + n11)
    raw = -2.0 * (
        (xlogy(n00 + n10, 1.0 - pi) + xlogy(n01 + n11, pi))
        - (xlogy(n00, 1.0 - pi01) + xlogy(n01, pi01) + xlogy(n10, 1.0 - pi11) + xlogy(n11, pi11))
    )
    assert LR_NEGATIVE_FLOOR <= raw < 0.0  # premissa: o piso de fato atua

    report = ChristoffersenTest.evaluate(make_hit_sequence(_FLOOR_SEQUENCE), min_violations=0)

    assert report.statistics.transitions == (n00, n01, n10, n11)
    assert report.statistics.lr_ind == 0.0
    assert report.p_ind == 1.0


# --- C4 — min_violations --------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("value", [-1, 1.5, True], ids=["negative", "float", "bool"])
def test_min_violations_invalid_raises(make_hit_sequence: HitSequenceFactory, value: int) -> None:
    """A6/C4: `min_violations` negativo, não-inteiro ou `bool` ergue (serviço e primitivo)."""
    with pytest.raises(ValueError, match="min_violations must be an int >= 0"):
        ChristoffersenTest.evaluate(make_hit_sequence(_HAND), min_violations=value)
    with pytest.raises(ValueError, match="min_violations must be an int >= 0"):
        christoffersen_statistics(violations=_HAND, violation_rate=_P, min_violations=value)


@pytest.mark.unit
@pytest.mark.parametrize("target", ["evaluate", "primitive"])
def test_min_violations_signature_is_keyword_only_without_default(target: str) -> None:
    """A6/I6: `min_violations` obrigatório (keyword-only, sem default) nos dois."""
    function = ChristoffersenTest.evaluate if target == "evaluate" else christoffersen_statistics
    parameter = inspect.signature(function).parameters["min_violations"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


@pytest.mark.unit
@pytest.mark.parametrize("element", [1, 0, "x"], ids=["int-one", "int-zero", "str"])
def test_min_violations_invalid_element_in_primitive_raises(element: object) -> None:
    """Decisão de detalhe do §1: o primitivo valida os elementos (`bool` ou `None`)."""
    with pytest.raises(ValueError, match=r"violations\[1\] must be a bool or None"):
        christoffersen_statistics(violations=(T, element), violation_rate=_P, min_violations=0)  # type: ignore[arg-type]


# --- C9 — relatório e estatísticas incoerentes, um caso por ramo ----------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"n_observed": 5}, r"exceeds max\(n_observed - 1, 0\)"),
        ({"n_violations": 3}, "n01 \\+ n11 = 4 exceeds n_violations=3"),
        ({"n_observed": 13, "transitions": (3, 3, 4, 1)}, "n10 \\+ n11 = 5 exceeds n_violations=4"),
        ({"n_violations": 6}, r"n_violations - \(n01 \+ n11\) = 2 exceeds"),
        ({"transitions": (-1, 3, 3, 1)}, "must be ints >= 0"),
        ({"n_observed": True}, "must be ints >= 0"),
        ({"transitions": (4, 3, 3)}, "must be ints >= 0"),
        ({"kupiec_pof": None}, "kupiec_pof must be None exactly when n_observed == 0"),
        ({"lr_uc": None, "lr_cc": None}, "lr_uc must be None exactly when"),
        ({"independence_status": IndependenceStatus.NO_TRANSITIONS}, "lr_ind must be set exactly"),
        ({"lr_ind": None, "lr_cc": None}, "lr_ind must be set exactly"),
        ({"kupiec_pof": -1.0}, "kupiec_pof must be a finite number >= 0"),
        ({"lr_cc": 99.0}, "lr_cc must be lr_uc \\+ lr_ind"),
    ],
    ids=[
        "pairs-above-observed",
        "n1-pure-above-violations",
        "violation-row-above-violations",
        "first-observation-gap",
        "negative-count",
        "bool-count",
        "three-transitions",
        "pof-missing",
        "lr-uc-missing",
        "statistic-with-non-applicable-status",
        "applicable-without-statistic",
        "negative-statistic",
        "lr-cc-not-the-sum",
    ],
)
def test_report_incoherent_statistics_raise(
    make_hit_sequence: HitSequenceFactory, overrides: dict[str, object], match: str
) -> None:
    """C9: cada ramo do `ChristoffersenStatistics.__post_init__` (as quatro desigualdades
    do ADR 6.3.0001, presença das estatísticas, `lr_cc` ≠ soma)."""
    stats = _hand_report(make_hit_sequence).statistics

    with pytest.raises(ValueError, match=match):
        dataclasses.replace(stats, **overrides)  # type: ignore[arg-type]


@pytest.mark.unit
def test_report_incoherent_round_trips_when_valid(make_hit_sequence: HitSequenceFactory) -> None:
    report = _hand_report(make_hit_sequence)

    assert dataclasses.replace(report) == report
    assert isinstance(report.statistics, ChristoffersenStatistics)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"p_uc": 1.5}, r"p_uc must be in \[0, 1\]"),
        ({"p_uc": 0.3}, r"p_uc must be chi_square_sf\(statistic, df=1\)"),
        ({"p_cc": None}, "p_cc must be None exactly when its statistic is None"),
        ({"independence_descriptive": True}, "independence_descriptive must be"),
        ({"min_violations": 10}, "independence_status must be below_min_violations"),
        ({"horizon": 0}, "horizon must be an int >= 1"),
        ({"min_violations": True}, "min_violations must be an int >= 0"),
    ],
    ids=[
        "p-value-above-one",
        "p-value-not-chi2",
        "p-value-missing",
        "descriptive-incoherent",
        "status-incoherent-with-min",
        "horizon-zero",
        "min-violations-bool",
    ],
)
def test_report_incoherent_applicable_raises(
    make_hit_sequence: HitSequenceFactory, overrides: dict[str, object], match: str
) -> None:
    """C9: ramos do `ChristoffersenReport.__post_init__` sobre o relatório aplicável."""
    report = _hand_report(make_hit_sequence)

    with pytest.raises(ValueError, match=match):
        dataclasses.replace(report, **overrides)  # type: ignore[arg-type]


@pytest.mark.unit
def test_report_incoherent_p_value_without_statistic_raises(
    make_hit_sequence: HitSequenceFactory,
) -> None:
    """C9: p-valor preenchido com a estatística `None` (sequência toda mascarada) ergue."""
    sequence = make_hit_sequence((None, None), includes_degenerate=True)
    report = ChristoffersenTest.evaluate(sequence, min_violations=0)

    with pytest.raises(ValueError, match="p_uc must be None exactly when its statistic is None"):
        dataclasses.replace(report, p_uc=0.5)


# --- Task 08 — LR_uc de 3 estados (A7, I10, I13, C3) ----------------------------------------

_THREE_RATE = 0.02


def _three_state_by_hand(
    lower: float, upper: float, n: float, lower_rate: float, upper_rate: float
) -> float:
    """-2·[l(taxas) - l(p̂)] multinomial, escrito aqui com `math.log` (contagens > 0)."""
    middle = n - lower - upper
    null = (
        lower * math.log(lower_rate)
        + upper * math.log(upper_rate)
        + middle * math.log(1 - lower_rate - upper_rate)
    )
    fitted = (
        lower * math.log(lower / n) + upper * math.log(upper / n) + middle * math.log(middle / n)
    )
    return -2 * (null - fitted)


def _three_state(lower: float, upper: float, n: float) -> float:
    return lr_uc_three_state(
        lower_count=lower,
        upper_count=upper,
        n=n,
        lower_rate=_THREE_RATE,
        upper_rate=_THREE_RATE,
    )


@pytest.mark.unit
def test_three_state_hand_value() -> None:
    """A7: (7, 3, 200), taxas 0.02/0.02 — igual às log-somas escritas aqui (≈ 2.1294)."""
    expected = _three_state_by_hand(7, 3, 200, _THREE_RATE, _THREE_RATE)

    assert _close(_three_state(7, 3, 200), expected)
    assert round(expected, 4) == 2.1294  # noqa: PLR2004 — technical §1


@pytest.mark.unit
def test_three_state_zero_when_counts_match_rates() -> None:
    """A7: contagens = n·taxas (4, 4, 200) → exatamente 0.0 (aceita o -0.0 medido)."""
    assert _three_state(4, 4, 200) == 0.0


@pytest.mark.unit
def test_three_state_chi2_two_degrees_of_freedom() -> None:
    """A7/I7: o p-valor do 3 estados é χ²(2) pelo `chi_square_sf` = exp(-x/2)."""
    statistic = _three_state(7, 3, 200)

    assert chi_square_sf(statistic, df=2) == math.exp(-statistic / 2)


@pytest.mark.unit
def test_three_state_real_count_between_integer_neighbours() -> None:
    """A7/I10: `lower_count` = 7.5 (média entre seeds) fica estritamente entre os
    valores em 7 e 8, com `upper_count` e `n` fixos (2.1294 < 2.7357 < 3.4114)."""
    at_7, at_7_5, at_8 = _three_state(7, 3, 200), _three_state(7.5, 3, 200), _three_state(8, 3, 200)

    assert at_7 < at_7_5 < at_8
    assert _close(at_7_5, _three_state_by_hand(7.5, 3, 200, _THREE_RATE, _THREE_RATE))


@pytest.mark.unit
def test_three_state_floor_clamps_negative_raw_value() -> None:
    """A7/I13: (1, 3, 6), taxas 1/6 e 0.5 — LR bruto (mesma ordem de operações do
    kernel) na faixa do piso; o kernel devolve exatamente 0.0."""
    lower, upper, n, lower_rate, upper_rate = 1, 3, 6, 1 / 6, 0.5
    middle = n - lower - upper
    raw = -2.0 * (
        (
            xlogy(lower, lower_rate)
            + xlogy(upper, upper_rate)
            + xlogy(middle, 1.0 - lower_rate - upper_rate)
        )
        - (xlogy(lower, lower / n) + xlogy(upper, upper / n) + xlogy(middle, middle / n))
    )
    assert LR_NEGATIVE_FLOOR <= raw < 0.0  # premissa: o piso de fato atua

    result = lr_uc_three_state(
        lower_count=lower, upper_count=upper, n=n, lower_rate=lower_rate, upper_rate=upper_rate
    )

    assert result == 0.0
    assert math.copysign(1.0, result) == 1.0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"lower_count": -1}, r"lower_count must be in \[0, n="),
        ({"upper_count": 201}, r"upper_count must be in \[0, n="),
        ({"n": 0, "lower_count": 0, "upper_count": 0}, "n must be > 0"),
        ({"lower_count": 150, "upper_count": 60}, "lower_count \\+ upper_count must be <= n"),
        ({"lower_rate": 0.0}, r"lower_rate must be in \(0, 1\)"),
        ({"upper_rate": 1.0}, r"upper_rate must be in \(0, 1\)"),
        ({"lower_rate": 0.5, "upper_rate": 0.5}, "lower_rate \\+ upper_rate must be < 1"),
        ({"lower_count": math.nan}, "lower_count must be a finite number"),
        ({"n": True}, "n must be a finite number"),
        ({"upper_rate": math.inf}, "upper_rate must be a finite number"),
    ],
    ids=[
        "lower-negative",
        "upper-above-n",
        "n-zero",
        "sum-above-n",
        "lower-rate-zero",
        "upper-rate-one",
        "rates-sum-one",
        "lower-nan",
        "n-bool",
        "upper-rate-inf",
    ],
)
def test_three_state_invalid_argument_raises(overrides: dict[str, float], match: str) -> None:
    """A7/C3: um caso por ramo (inclusive soma das contagens > n e taxas somando 1)."""
    arguments = {
        "lower_count": 7,
        "upper_count": 3,
        "n": 200,
        "lower_rate": _THREE_RATE,
        "upper_rate": _THREE_RATE,
        **overrides,
    }
    with pytest.raises(ValueError, match=match):
        lr_uc_three_state(**arguments)


@pytest.mark.unit
def test_three_state_composition_with_tail_hit_sequences(
    make_series: Callable[..., CoverageSeries],
) -> None:
    """A7/I10 (Checkpoint B T22): composição que a 6.5 consome — as duas caudas
    unilaterais da mesma série e tolerância têm o mesmo `n_observed`, e o 3 estados
    das suas contagens é finito e igual ao valor à mão."""
    spread = (-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03)
    dirac = (0.004,) * 7
    grids = [spread, dirac, spread, spread, spread, dirac, spread, spread]
    realized = [-0.04, 0.0, 0.05, -0.035, 0.0, 0.0, 0.031, 0.01]
    series = make_series(grids, realized)
    lower = HitSequences.lower_tail(series, level=0.05, tolerance=1e-9)
    upper = HitSequences.upper_tail(series, level=0.95, tolerance=1e-9)

    statistic = lr_uc_three_state(
        lower_count=lower.n_violations,
        upper_count=upper.n_violations,
        n=lower.n_observed,
        lower_rate=lower.violation_rate,
        upper_rate=upper.violation_rate,
    )

    assert lower.n_observed == upper.n_observed == 6  # noqa: PLR2004
    assert (lower.n_violations, upper.n_violations) == (2, 2)
    assert math.isfinite(statistic)
    expected = _three_state_by_hand(2, 2, 6, lower.violation_rate, upper.violation_rate)
    assert _close(statistic, expected)
