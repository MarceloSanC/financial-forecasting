"""Adapter `MapieCqrBackend` — MAPIE 1.5 como oráculo do split-CQR sem pesos (ADR 7.2.0002 item 4).

Satisfaz o port-out `ConformalBackend` (`inference/application/ports/out/`). É
oráculo, não implementação de registro: o split-CQR de registro é o
`ConformalCalibrator` do domain, e nenhum use case chama este adapter (I1; ADR
6.4.0008). Só a suíte de contrato o usa.

Como o MAPIE é chamado: as predições dadas (q_lo, q_hi e a mediana (q_lo + q_hi)/2)
entram por três estimadores `prefit` privados (`_PrefitPredictions`), que devolvem a
predição pelo índice da linha de `X` (uma coluna com 0..n-1). Então
`ConformalizedQuantileRegressor(estimator=[lo, hi, med], confidence_level=1 - 2 *
tail_alpha, prefit=True).conformalize(X, y)`. O MAPIE 1.5 não expõe o quantil
conformal como atributo (ele é calculado dentro do `predict`), então cada Q sai
por subtração sobre `predict_interval(X, symmetric_correction=False)`:
Q_lo = q_lo - L e Q_hi = U - q_hi, lidos na linha 0.

Erros do MAPIE propagam (C5): com tail_alpha = 0,02 o `conformalize` recusa n < 25
e o `predict_interval` recusa n <= 49 ("Number of samples of the score is too low").
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from mapie.regression import ConformalizedQuantileRegressor


class _PrefitPredictions:
    """Estimador já "ajustado" que devolve predições fixas pelo índice da linha."""

    n_features_in_ = 1

    def __init__(self, values: np.ndarray) -> None:
        self._values = np.asarray(values, dtype=float)

    def fit(self, X: object, y: object) -> _PrefitPredictions:
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        rows = np.asarray(X)[:, 0].astype(np.intp)
        return self._values[rows]

    def __sklearn_is_fitted__(self) -> bool:
        return True


class MapieCqrBackend:
    """Correções (Q_lo, Q_hi) do split-CQR sem pesos pelo MAPIE 1.5 (oráculo)."""

    def split_cqr_corrections(
        self,
        *,
        calib_lower: Sequence[float],
        calib_upper: Sequence[float],
        calib_realized: Sequence[float],
        tail_alpha: float,
    ) -> tuple[float, float]:
        if not len(calib_lower) == len(calib_upper) == len(calib_realized):
            raise ValueError("calib_lower, calib_upper and calib_realized must align")
        n = len(calib_realized)
        rows = np.arange(n, dtype=float).reshape(-1, 1)
        lower = np.asarray(calib_lower, dtype=float)
        upper = np.asarray(calib_upper, dtype=float)
        median = (lower + upper) / 2
        regressor = ConformalizedQuantileRegressor(
            estimator=[
                _PrefitPredictions(lower),
                _PrefitPredictions(upper),
                _PrefitPredictions(median),
            ],
            confidence_level=1 - 2 * tail_alpha,
            prefit=True,
        )
        regressor.conformalize(rows, np.asarray(calib_realized, dtype=float))
        _, intervals = regressor.predict_interval(rows[:1], symmetric_correction=False)
        return (
            float(lower[0] - intervals[0, 0, 0]),
            float(intervals[0, 1, 0] - upper[0]),
        )
