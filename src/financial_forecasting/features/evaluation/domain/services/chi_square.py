"""Kernel `chi_square_sf` — sobrevivência da χ² em forma fechada (df 1 e 2) + piso I13.

stdlib-only (concept 6.3 §4, I7; ADR `6_3_0001` itens 6 e 8). Os testes de razão de
verossimilhança da Stage (Kupiec POF, trio de Christoffersen, LR_uc de 3 estados) só
precisam de df ∈ {1, 2}, onde a sobrevivência tem forma fechada — sem scipy no
domínio:

- df = 1: P(χ²₁ > x) = erfc(√(x/2));
- df = 2: P(χ²₂ > x) = exp(-x/2).

**Piso numérico (I13) com dono único aqui.** As estatísticas LR são diferenças de
log-somas e podem sair levemente negativas por arredondamento (Checkpoint A mediu até
-2.84e-14), o que quebraria `erfc(√(x/2))`. `floor_lr_statistic` leva todo valor em
`[LR_NEGATIVE_FLOOR, 0)` a `0.0` e ergue abaixo disso (é bug, não ruído). Mora neste
módulo-folha porque é a razão de existir do piso e porque todos os consumidores
(`chi_square_sf`, `kupiec_pof`, LR_ind, LR_uc de 3 estados) já dependem dele — uma
escrita da regra, nenhuma cópia (technical 6.3 §1, decisão de detalhe).

Módulo próprio (não um pacote "distributions" compartilhado): a 6.2 cria o seu
`student_t.py` sem dividir arquivo com este (concept 6.3 D9).
"""

from __future__ import annotations

import math
from typing import Final

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)

# I13 / ADR 6.3.0001 item 8: limite inferior do ruído de arredondamento tolerado.
LR_NEGATIVE_FLOOR: Final = -1e-9

_SUPPORTED_DF: Final = (1, 2)


def floor_lr_statistic(value: float) -> float:
    """Aplica o piso numérico I13 a uma estatística LR.

    `[LR_NEGATIVE_FLOOR, 0]` → `+0.0` (fronteira inclusa; `-0.0` também é
    normalizado, para nenhum relatório carregar um zero com sinal — o caso de
    contagens exatamente iguais a n·p dá `-2·(a - a) = -0.0`); > 0 volta inalterado.

    Alcance do piso absoluto: o LR é diferença de duas log-verossimilhanças de
    magnitude ~n, então o erro de cancelamento cresce como n·eps (eps ≈ 2.2e-16) —
    `-1e-9` cobre o ruído com folga para n ≲ 1e7 (muito acima de T ≤ 500 do oráculo e
    das séries do piloto). Acima disso um LR bruto negativo além do piso pode ser
    ruído, não bug (ADR 6.3.0001 item 8, nota do Checkpoint C).

    Raises:
        ValueError: valor não-finito ou `bool` (predicado único do slice), ou abaixo de
            `LR_NEGATIVE_FLOOR` (negativo além do ruído de arredondamento).
    """
    if not is_finite_number(value):
        raise ValueError(f"LR statistic must be a finite number, got {value!r}")
    if value < LR_NEGATIVE_FLOOR:
        raise ValueError(
            f"LR statistic {value!r} is below the numerical floor {LR_NEGATIVE_FLOOR} "
            "(negative beyond rounding noise)"
        )
    if value <= 0.0:
        return 0.0
    return value


def chi_square_sf(statistic: float, *, df: int) -> float:
    """P(χ²_df > statistic) para df ∈ {1, 2}, em forma fechada, após o piso I13.

    Raises:
        ValueError: `df` fora de {1, 2} ou não-`int` (inclusive `bool`); estatística
            não-finita, `bool` ou negativa além do piso (C3).
    """
    if isinstance(df, bool) or not isinstance(df, int) or df not in _SUPPORTED_DF:
        raise ValueError(f"df must be an int in {_SUPPORTED_DF}, got {df!r}")
    x = floor_lr_statistic(statistic)
    if df == 1:
        return math.erfc(math.sqrt(x / 2.0))
    return math.exp(-x / 2.0)
