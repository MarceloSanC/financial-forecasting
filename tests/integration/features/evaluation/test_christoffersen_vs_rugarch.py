"""Integração: o trio puro de Christoffersen contra o `rugarch::VaRTest` por dois *feeds*.

Prova (concept 6.3 A10, I12, C8; ADR 6.3.0002 item 4; ADR 6.3.0003 e a sua errata):

- LR_uc puro == `uc.LRstat` do *feed* t ≥ 2 (ou, se esse *feed* falha, o
  `lr_uc_internal` = `rugarch:::.LR.uc(p, T - 1, sum(v[-1]))` gravado pelo gerador);
- LR_ind == `cc.LRstat - uc.LRstat` do *feed* inteiro; LR_cc == a soma;
- erro do R no *feed* inteiro ⇔ `independence_status` ≠ APPLICABLE (a matriz de
  transição perde um símbolo exatamente onde o `table(head, tail)` do R perde); valor
  de *feed* com erro nunca é esperado (C8);
- ao menos um caso I_1 = 1 em que a convenção importa (|uc(t ≥ 2) - uc(inteira)| > 0.1).

Tolerância de **arredondamento** (o R usa log do produto; o domínio, log-somas), nunca
O(1/T). `min_violations = 0`: a aplicabilidade é só a da matriz de transição.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenStatistics,
    IndependenceStatus,
    christoffersen_statistics,
)
from tests.integration.features.evaluation._var_test_cases import (
    OracleFeed,
    VarTestCase,
    load_var_test_cases,
)

pytestmark = pytest.mark.integration

# Tolerância declarada (ADR 0.0.0021; ADR 6.3.0003): arredondamento, nunca O(1/T).
_ORACLE_ABS_TOL = 1e-10
_GAP = 0.1
_T_MAX = 500
_T_MIN = 2  # o feed t >= 2 precisa de ao menos uma posição
_CATEGORIES = {"iid", "clustered", "first_violation", "n11_zero", "r_error", "t2_feed_error"}

_FIXTURE = load_var_test_cases()
_ALL = list(_FIXTURE.cases)
_WHOLE_OK = [case for case in _ALL if case.whole.ok]


def _stats(case: VarTestCase) -> ChristoffersenStatistics:
    return christoffersen_statistics(
        violations=case.violations, violation_rate=case.violation_rate, min_violations=0
    )


def _pure_uc_expected(feed: OracleFeed) -> float:
    """LR_uc puro do oráculo: `uc.LRstat` do *feed* t ≥ 2 ou, se ele falhou, o
    `lr_uc_internal` da errata do ADR 6.3.0003 (nunca um valor de *feed* com erro)."""
    value = feed.uc_lrstat if feed.ok else feed.lr_uc_internal
    assert value is not None
    return value


def _close(actual: float | None, expected: float) -> bool:
    return actual is not None and abs(actual - expected) <= _ORACLE_ABS_TOL


@pytest.mark.parametrize("case", _WHOLE_OK, ids=lambda case: case.id)
def test_trio_two_feeds_matches_rugarch(case: VarTestCase) -> None:
    """A10/I12: LR_uc puro ↔ t ≥ 2; LR_ind ↔ cc - uc da inteira; LR_cc ↔ a soma."""
    assert case.whole.uc_lrstat is not None and case.whole.cc_lrstat is not None
    stats = _stats(case)
    expected_uc = _pure_uc_expected(case.from_t2)
    expected_ind = case.whole.cc_lrstat - case.whole.uc_lrstat

    assert stats.independence_status is IndependenceStatus.APPLICABLE
    assert _close(stats.lr_uc, expected_uc)
    assert _close(stats.lr_ind, expected_ind)
    assert _close(stats.lr_cc, expected_uc + expected_ind)


@pytest.mark.parametrize("case", _WHOLE_OK, ids=lambda case: case.id)
def test_lr_ind_whole_feed_even_when_t2_fails(case: VarTestCase) -> None:
    """A10 (Checkpoint B T14): LR_ind == `cc - uc` do *feed* inteiro em todo caso com
    ele válido — inclusive quando o *feed* t ≥ 2 falha (n11_zero em t = 1/T, pontas)."""
    assert case.whole.uc_lrstat is not None and case.whole.cc_lrstat is not None

    assert _close(_stats(case).lr_ind, case.whole.cc_lrstat - case.whole.uc_lrstat)


def test_lr_ind_whole_feed_covers_failing_t2_feed() -> None:
    """A cobertura inclui casos com o *feed* inteiro válido e o t ≥ 2 com erro."""
    assert any(not case.from_t2.ok for case in _WHOLE_OK)


@pytest.mark.parametrize("case", _ALL, ids=lambda case: case.id)
def test_r_error_policy_whole_feed(case: VarTestCase) -> None:
    """A10/C8: erro do R no *feed* inteiro ⇔ status ≠ APPLICABLE; aí `lr_ind` é None, o
    POF segue definido (x = 0 → -2·T·log(1 - p)) e o LR_uc puro bate com o
    `lr_uc_internal` do R. Nenhum valor de *feed* com erro é usado como esperado."""
    stats = _stats(case)

    assert (not case.whole.ok) == (stats.independence_status is not IndependenceStatus.APPLICABLE)
    if case.whole.ok:
        return
    assert case.whole.uc_lrstat is None and case.whole.cc_lrstat is None
    assert stats.lr_ind is None and stats.lr_cc is None
    assert stats.kupiec_pof is not None and math.isfinite(stats.kupiec_pof)
    if not any(case.violations):
        n = len(case.violations)
        assert _close(stats.kupiec_pof, -2 * n * math.log(1 - case.violation_rate))
    assert _close(stats.lr_uc, _pure_uc_expected(case.from_t2))


def test_r_error_policy_has_each_side() -> None:
    """A política não é vácua: há casos com e sem erro do R no *feed* inteiro."""
    assert any(case.whole.ok for case in _ALL)
    assert any(not case.whole.ok for case in _ALL)


def test_first_violation_gap_the_convention_matters() -> None:
    """A10: ≥ 1 caso `first_violation` com |uc(t ≥ 2) - uc(inteira)| > 0.1, e o domínio
    reproduz os dois lados — o LR_uc puro bate com t ≥ 2 e o POF com a inteira."""
    gaps = [
        case
        for case in _ALL
        if case.category == "first_violation"
        and case.whole.ok
        and case.from_t2.ok
        and case.whole.uc_lrstat is not None
        and case.from_t2.uc_lrstat is not None
        and abs(case.from_t2.uc_lrstat - case.whole.uc_lrstat) > _GAP
    ]

    assert gaps
    for case in gaps:
        assert case.violations[0] is True
        assert case.whole.uc_lrstat is not None and case.from_t2.uc_lrstat is not None
        stats = _stats(case)
        assert _close(stats.lr_uc, case.from_t2.uc_lrstat)
        assert _close(stats.kupiec_pof, case.whole.uc_lrstat)


def test_fixture_guard_limits_and_categories() -> None:
    """A10: T ≤ `t_max` = 500 em todo caso e cada categoria do gerador presente."""
    assert _FIXTURE.provenance["t_max"] == _T_MAX
    assert all(_T_MIN <= len(case.violations) <= _T_MAX for case in _ALL)
    assert {case.category for case in _ALL} == _CATEGORIES
    assert len({case.id for case in _ALL}) == len(_ALL)
