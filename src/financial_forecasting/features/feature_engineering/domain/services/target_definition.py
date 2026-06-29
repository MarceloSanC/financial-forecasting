"""`TargetDefinition` — dono único do alvo backward log-return (domain puro).

Serviço de domínio **puro stdlib-only** (`math`/`collections.abc`) que é o **dono
único** da convenção do alvo do dataset TFT (concept 3.5 I1, D1; ADR 3.5.0001):

    target_return[t] = log(close_t / close_{t-1})   (backward)
    target_return[0] = None                          (primeira linha cai)

O alvo é indexado pelo **decision_day**: a linha em `t` carrega as features
conhecidas *as of* `decision_day` e o retorno backward realizado *naquele* dia. A
jusante o persister da 4.3 mapeia o horizonte `h` para
`target_timestamp = dataset_timestamps[decision_idx + h]`, de modo que as duas
convenções são a MESMA convenção dita uma vez — eliminando o off-by-one que gerou
bug no old (ADR-0003 / R-20).

Verbatim com o old (`build_tft_dataset_use_case.py:563-572`,
`np.log(close / close.shift(1))` + `dropna(subset=["target_return"])`), porém
materializado como serviço de domínio puro testável em isolamento e reusável como
oráculo de re-derivação (decompõe o monólito onde o alvo era inline).

Pureza (I6): importa SÓ stdlib. `import pandas`/`numpy` aqui REPROVA `domain-purity`
no import-linter.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# Tipo de saída: o alvo alinhado 1:1 com os closes (None na 1ª posição — warmup).
TargetReturns = tuple[float | None, ...]

# Mínimo de closes para definir ao menos 1 retorno backward (close_t e close_{t-1}).
_MIN_CLOSES = 2


def compute_target_return(closes: Sequence[float]) -> TargetReturns:
    """Calcula o alvo backward `log(close_t / close_{t-1})` alinhado aos closes.

    Convenção única (concept 3.5 I1 / ADR 3.5.0001):

    - `len(saída) == len(closes)`; `saída[0] is None` (a 1ª linha cai na montagem
      porque `log(close_0 / close_{-1})` é indefinido).
    - `saída[t] = math.log(close_t / close_{t-1})` para `t >= 1`.

    Erros de domínio (C1):

    - menos de 2 closes → `ValueError("not enough rows to compute target_return")`.
    - qualquer close `<= 0` ou não-finito (NaN/inf) → `ValueError` claro
      (o logaritmo só é definido para preços estritamente positivos e finitos).
    """
    if len(closes) < _MIN_CLOSES:
        raise ValueError("not enough rows to compute target_return")

    values = [_require_positive_finite(close, index) for index, close in enumerate(closes)]

    out: list[float | None] = [None]
    for t in range(1, len(values)):
        out.append(math.log(values[t] / values[t - 1]))
    return tuple(out)


def _require_positive_finite(close: float, index: int) -> float:
    """Coage `close` a `float` exigindo positivo e finito (C1); senão `ValueError`."""
    value = float(close)
    if not math.isfinite(value):
        raise ValueError(
            f"close at index {index} must be a finite number to compute target_return, "
            f"got {close!r}"
        )
    if value <= 0.0:
        raise ValueError(
            f"close at index {index} must be strictly positive to compute target_return, "
            f"got {value!r}"
        )
    return value
