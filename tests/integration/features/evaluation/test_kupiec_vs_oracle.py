"""Integração: Kupiec POF do domínio contra o `uc.LRstat` do `rugarch::VaRTest` congelado.

Prova (concept 6.3 A10, I12; ADRs 6.3.0002, 6.3.0003): o POF de Kupiec sobre todas as
posições observadas é o `uc.LRstat` do *feed* inteiro — o kernel `kupiec_pof` e a
leitura Kupiec do primitivo `christoffersen_statistics` — sob tolerância de
**arredondamento** (o R calcula pelo log do produto de verossimilhanças; o domínio,
por log-somas), nunca O(1/T).
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    christoffersen_statistics,
)
from financial_forecasting.features.evaluation.domain.services.kupiec_pof import kupiec_pof
from tests.integration.features.evaluation._var_test_cases import (
    VarTestCase,
    load_var_test_cases,
)

pytestmark = pytest.mark.integration

# Tolerância declarada (ADR 0.0.0021; ADR 6.3.0003): arredondamento, nunca O(1/T).
_ORACLE_ABS_TOL = 1e-10

_WHOLE_OK = [case for case in load_var_test_cases().cases if case.whole.ok]


@pytest.mark.parametrize("case", _WHOLE_OK, ids=lambda case: case.id)
def test_kupiec_whole_feed_matches_uc_lrstat(case: VarTestCase) -> None:
    """A10/I12: POF(x, T, p) == `uc.LRstat` do *feed* inteiro, pelo kernel e pelo trio."""
    assert case.whole.uc_lrstat is not None
    x, n = sum(case.violations), len(case.violations)

    kernel = kupiec_pof(violations=x, observations=n, violation_rate=case.violation_rate)
    reading = christoffersen_statistics(
        violations=case.violations, violation_rate=case.violation_rate, min_violations=0
    ).kupiec_pof

    assert abs(kernel - case.whole.uc_lrstat) <= _ORACLE_ABS_TOL
    assert reading is not None
    assert abs(reading - case.whole.uc_lrstat) <= _ORACLE_ABS_TOL


def test_kupiec_whole_feed_cases_exist() -> None:
    """A comparação não é vácua: há casos com o *feed* inteiro válido."""
    assert len(_WHOLE_OK) >= 20  # noqa: PLR2004
