"""Unit test do validador único dos kernels de contagem real (C3; ADR 6.3.0005 item 1).

`validate_real_count`/`validate_rate` são a única escrita do contrato de entrada de
`kupiec_pof`, `wilson_interval` e `lr_uc_three_state`; as mensagens nomeiam o campo
que o kernel passou (aqui, os nomes do Wilson: `count`, `n`, `band_level`). O
consumo pelo `kupiec_pof` é provado por `test_kupiec_pof.py::kupiec_invalid` (mesmas
mensagens) e por monkeypatch abaixo.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.domain.services import (
    kupiec_pof as kupiec_pof_module,
)
from financial_forecasting.features.evaluation.domain.services.count_input_validation import (
    validate_rate,
    validate_real_count,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("count", "n"),
    [(0, 1), (10.5, 500), (500.5, 500.5), (0.0, 1e-3)],
    ids=["zero-count", "real-count", "count-equals-n", "real-n"],
)
def test_real_count_accepts_valid_counts(count: float, n: float) -> None:
    """ADR 6.3.0005: contagem real 0 ≤ count ≤ n, n > 0, passa sem erguer."""
    validate_real_count(count, n, count_field="count", n_field="n")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("count", "n", "match"),
    [
        (math.nan, 10, "count must be a finite number"),
        (True, 10, "count must be a finite number"),
        (1, math.inf, "n must be a finite number"),
        (1, False, "n must be a finite number"),
        (0, 0, "n must be > 0"),
        (-1, 10, r"count must be in \[0, n=10\]"),
        (11, 10, r"count must be in \[0, n=10\]"),
        (1e-320, 1e10, r"count/n underflows to 0\.0 with count > 0"),
        (1, 10**400, "n must be a finite number"),
    ],
    ids=[
        "count-nan",
        "count-bool",
        "n-inf",
        "n-bool",
        "n-zero",
        "count-negative",
        "count-above",
        "ratio-underflow",
        "n-int-beyond-float",
    ],
)
def test_real_count_rejects_with_named_field(count: float, n: float, match: str) -> None:
    """C3: cada ramo ergue `ValueError` com o nome de campo passado pelo kernel."""
    with pytest.raises(ValueError, match=match):
        validate_real_count(count, n, count_field="count", n_field="n")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rate", "match"),
    [
        (0.0, r"band_level must be in \(0, 1\)"),
        (1.0, r"band_level must be in \(0, 1\)"),
        (math.nan, "band_level must be a finite number"),
        (True, "band_level must be a finite number"),
    ],
    ids=["zero", "one", "nan", "bool"],
)
def test_rate_rejects_with_named_field(rate: float, match: str) -> None:
    """C3: taxa/nível fora de (0, 1), não-finito ou `bool` ergue nomeando o campo."""
    with pytest.raises(ValueError, match=match):
        validate_rate(rate, field="band_level")


@pytest.mark.unit
def test_kupiec_pof_consumes_the_single_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 6.3.0005 item 1: o `kupiec_pof` valida pelo validador único — trocar o nome
    no namespace do módulo muda o erro, logo não há cópia inline da regra."""

    def _reject(*_: object, **__: object) -> None:
        raise ValueError("single validator called")

    monkeypatch.setattr(kupiec_pof_module, "validate_real_count", _reject)

    with pytest.raises(ValueError, match="single validator called"):
        kupiec_pof_module.kupiec_pof(violations=4, observations=500, violation_rate=0.02)
