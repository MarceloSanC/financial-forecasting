"""Port-out `ConformalCalibration` — a calibração conformal que o `RefreshGold` pede (ADR 7.2.0003).

Port do **consumidor** (concept 7.2 §4; ADR 7.2.0003 item 3; ADR 0.0.0053; LAYOUT §7,
#93): o `evaluation` precisa das correções e dos limites conformais de cada unidade
(fold, seed, horizonte), e quem os calcula é o domain do `inference`. O real é o use case
`CalibrateConformal` (`inference/application/use_cases/calibrate_conformal.py`), por
duck typing; o fake é o `FakeConformalCalibration`
(`tests/fakes/features/evaluation/fake_conformal_calibration.py`). As anotações são
textualmente as do use case, para o gate de cobertura de ports reconhecer o real (#93).

Os DTOs de comando e de resultado são do fornecedor e entram **só sob
`if TYPE_CHECKING:`** aqui; a aresta de runtime (o `refresh_gold` monta o comando) é
declarada no `bc-independence` pela Task 19.

Contrato de `__call__(command)`:

- uma linha por (unidade, par, variante), em ordem (fold, seed, horizonte) e, dentro da
  unidade, pares e variantes na ordem do comando;
- status por unidade: `ok`, `undefined` (entrada incompleta) ou `error` (recusa do VO ou
  do calibrador naquela unidade), sem derrubar as vizinhas;
- erro de comando (unidade duplicada, variante desconhecida, rho ausente para NEXCP, par
  inválido) ergue `ValueError` antes de qualquer unidade.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
        CalibrateConformalCommand,
        CalibrateConformalResult,
    )


class ConformalCalibration(Protocol):
    """Calibra as unidades conformais do comando; status por unidade (ver o módulo)."""

    def __call__(self, command: CalibrateConformalCommand) -> CalibrateConformalResult:
        """Uma linha por (unidade, par, variante), com status, correções e limites."""
        ...
