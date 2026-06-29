"""Testes de `TargetDefinition` (Task 01) — alvo backward log-return, dono único.

Cobre concept 3.5 I1 / ADR 3.5.0001:

- happy path: valores conferidos contra `math.log` manual; alinhamento 1:1.
- `target[0] is None` (primeira linha cai na montagem).
- C1: menos de 2 closes → `ValueError`.
- close inválido (`<= 0` / não-finito) → `ValueError` nomeando o índice.
- pureza: o módulo não carrega pandas/numpy em `sys.modules` ao importar (I6;
  a garantia dura vem de `import-linter`/`check_layout.py`).
"""

from __future__ import annotations

import math
import sys

import pytest

from financial_forecasting.features.feature_engineering.domain.services import (
    target_definition,
)
from financial_forecasting.features.feature_engineering.domain.services.target_definition import (
    compute_target_return,
)


def test_target_is_backward_log_return_aligned_with_first_none() -> None:
    """`target[t] = log(c_t / c_{t-1})`, `target[0] is None`, alinhado 1:1."""
    closes = [100.0, 110.0, 99.0, 99.0]

    target = compute_target_return(closes)

    assert len(target) == len(closes)
    assert target[0] is None
    assert target[1] == pytest.approx(math.log(110.0 / 100.0))
    assert target[2] == pytest.approx(math.log(99.0 / 110.0))
    assert target[3] == pytest.approx(math.log(99.0 / 99.0))  # = 0.0 (close estável)


def test_minimum_two_closes_produces_one_return() -> None:
    """Com exatamente 2 closes: `(None, log(c1/c0))`."""
    target = compute_target_return([50.0, 55.0])

    assert target == (None, pytest.approx(math.log(55.0 / 50.0)))


def test_fewer_than_two_closes_raises_c1() -> None:
    """C1 — menos de 2 closes (0 ou 1) levanta `ValueError` com mensagem clara."""
    with pytest.raises(ValueError, match="not enough rows to compute target_return"):
        compute_target_return([100.0])
    with pytest.raises(ValueError, match="not enough rows to compute target_return"):
        compute_target_return([])


def test_non_positive_close_raises() -> None:
    """Close `<= 0` levanta `ValueError` nomeando o índice (log indefinido)."""
    with pytest.raises(ValueError, match="index 1 must be strictly positive"):
        compute_target_return([100.0, 0.0, 105.0])
    with pytest.raises(ValueError, match="index 0 must be strictly positive"):
        compute_target_return([-1.0, 100.0])


def test_non_finite_close_raises() -> None:
    """Close não-finito (NaN/inf) levanta `ValueError` nomeando o índice."""
    with pytest.raises(ValueError, match="index 2 must be a finite number"):
        compute_target_return([100.0, 101.0, math.nan])
    with pytest.raises(ValueError, match="index 1 must be a finite number"):
        compute_target_return([100.0, math.inf])


def test_module_does_not_depend_on_pandas_numpy() -> None:
    """Pureza (I6): o módulo só usa stdlib (`math`/`collections.abc`).

    Confere que o namespace do módulo não expõe `pandas`/`numpy` como atributo
    (eles não foram importados). A garantia DURA é do `import-linter`
    (`domain-purity`) + `check_layout.py`; este teste é um canário leve.
    """
    assert not hasattr(target_definition, "pd")
    assert not hasattr(target_definition, "np")
    assert "pandas" not in sys.modules or not _module_imports(target_definition, "pandas")


def _module_imports(module: object, name: str) -> bool:
    """`True` se `module` referencia diretamente o pacote `name` no seu namespace."""
    return any(getattr(module, attr, None) is sys.modules.get(name) for attr in dir(module))
