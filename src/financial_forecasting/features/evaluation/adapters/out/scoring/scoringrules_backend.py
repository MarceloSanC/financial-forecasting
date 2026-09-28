"""Adapter `ScoringrulesBackend` — satisfaz o port `ScoringBackend` via `scoringrules`.

Segundo oráculo de biblioteca (ADR `6_1_0001` item 3; doc de domínio §11.3), com as
três funções **nativas** da lib, cada uma devolvendo o escore por ponto, que o
adapter média:

- `quantile_score(obs, fct, alpha=level)` — `alpha` é o **nível** τ;
- `crps_quantile(obs, fct, alpha=levels)` — `fct` com forma T x K (ensemble no último
  eixo), `alpha` os K níveis; já inclui o fator 2/K;
- `interval_score(obs, lower, upper, alpha=miscoverage)` — aqui `alpha` é a
  **miscobertura**. As desigualdades da lib são estritas (y < l, y > u), compatíveis
  com o domínio: y = l e y = u não pagam penalidade nas duas definições.

**Backend fixado** em toda chamada (`_BACKEND`): o default da scoringrules muda para
`numba` quando o numba está instalado (doc §11.3), e o resultado do oráculo não pode
depender do ambiente. A **entrada** passa primeiro pelo validador único do domínio
(C7) — a lib não impõe o contrato do port (`interval_score` aceita `lower > upper` e
devolve um número; `crps_quantile` com T = 0 devolve um vetor vazio). O retorno é
convertido para `float` nativo.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import scoringrules as sr

from financial_forecasting.features.evaluation.domain.services.scoring_input_validation import (
    validate_crps_inputs,
    validate_interval_inputs,
    validate_pinball_inputs,
)

# Backend explícito em toda chamada: sem ele, a presença do numba no ambiente mudaria o
# caminho de cálculo (e o default) da scoringrules — doc de domínio §11.3.
_BACKEND = "numpy"


class ScoringrulesBackend:
    """Satisfaz `ScoringBackend` com `quantile_score`/`crps_quantile`/`interval_score`."""

    def mean_pinball(
        self, *, realized: Sequence[float], quantiles: Sequence[float], level: float
    ) -> float:
        validate_pinball_inputs(realized, quantiles, level)
        scores = sr.quantile_score(
            np.asarray(realized, dtype=float),
            np.asarray(quantiles, dtype=float),
            level,
            backend=_BACKEND,
        )
        return float(np.mean(scores))

    def mean_crps_quantile(
        self,
        *,
        realized: Sequence[float],
        quantile_grid: Sequence[Sequence[float]],
        levels: Sequence[float],
    ) -> float:
        validate_crps_inputs(realized, quantile_grid, levels)
        scores = sr.crps_quantile(
            np.asarray(realized, dtype=float),
            np.asarray(quantile_grid, dtype=float),
            np.asarray(levels, dtype=float),
            backend=_BACKEND,
        )
        return float(np.mean(scores))

    def mean_interval_score(
        self,
        *,
        realized: Sequence[float],
        lower: Sequence[float],
        upper: Sequence[float],
        miscoverage: float,
    ) -> float:
        validate_interval_inputs(realized, lower, upper, miscoverage)
        scores = sr.interval_score(
            np.asarray(realized, dtype=float),
            np.asarray(lower, dtype=float),
            np.asarray(upper, dtype=float),
            miscoverage,
            backend=_BACKEND,
        )
        return float(np.mean(scores))
