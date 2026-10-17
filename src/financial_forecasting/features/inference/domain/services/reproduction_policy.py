"""Política de reprodução da 7.1 no domain do `inference` (ADR 7.2.0005, F3).

Funções puras sobre primitivos: o modo (`strict`/`tolerance`) pelas chaves de
ambiente não ignoradas, o critério de valor e a comparação dos conjuntos de chaves
da reprodução do teste. As chaves ignoradas vêm do chamador (o `RunInference`
passa `CODE_KEYS` e `DIRTY_KEY` do port do `modeling`), porque o domain não
importa nada fora de si e do `shared` (I13). As mensagens de erro C7/C8 ficam no
use case.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

STRICT: Final = "strict"
TOLERANCE: Final = "tolerance"
# Regra do `torch.testing.assert_close` para float32 aplicada a z = (y - c) / s
# (ADR 7.1.0003): |Δz| <= ATOL + RTOL * |z_ref|.
TOLERANCE_ATOL: Final = 1e-5
TOLERANCE_RTOL: Final = 1.3e-6

_Key = tuple[int, int, float]


@dataclass(frozen=True)
class ReproductionMode:
    """Modo de reprodução, o motivo e se foi forçado por justificativa."""

    name: str
    reason: str
    forced: bool


@dataclass(frozen=True)
class ReproductionComparison:
    """Resultado da comparação chave a chave entre referência e re-predição."""

    compared: int
    failures: int
    missing: int
    extra: int
    max_abs_diff: float
    max_normalized_diff: float


def reproduction_mode(
    reference: Mapping[str, str],
    current: Mapping[str, str],
    justification: str | None,
    *,
    ignored_keys: frozenset[str],
) -> ReproductionMode:
    """Modo pelas chaves não ignoradas (ADR 7.1.0003 item 3).

    Iguais e sem justificativa → `strict`; iguais com justificativa → `tolerance`
    forçado; alguma diferente → `tolerance` (a diferença vence a justificativa).
    """
    keys = (set(reference) | set(current)) - ignored_keys
    differing = sorted(key for key in keys if reference.get(key) != current.get(key))
    if differing:
        return ReproductionMode(TOLERANCE, f"non-code keys differ: {differing}", forced=False)
    if justification is not None:
        return ReproductionMode(TOLERANCE, "forced: cross-environment", forced=True)
    return ReproductionMode(STRICT, "non-code keys equal", forced=False)


def within_mode(*, new: float, ref: float, center: float, scale: float, mode: str) -> bool:
    """`strict` = igualdade exata; `tolerance` = regra do `assert_close` em z."""
    if mode == STRICT:
        return new == ref
    return abs(new - ref) / scale <= TOLERANCE_ATOL + TOLERANCE_RTOL * abs((ref - center) / scale)


def compare_reproduction(
    reference: Mapping[_Key, float],
    predicted: Mapping[_Key, float],
    *,
    mode: str,
    center: float,
    scale: float,
) -> ReproductionComparison:
    """Compara as chaves comuns pelo `within_mode`; conta faltantes e sobrantes.

    `compared` é o número de chaves comuns; `max_abs_diff` e `max_normalized_diff`
    (= max |Δ| / s) são tomados sobre elas. O chamador decide a recusa: nada
    comparado, conjuntos de chaves diferentes ou alguma falha.
    """
    common = set(reference) & set(predicted)
    max_abs = 0.0
    failures = 0
    for key in common:
        new, ref = predicted[key], reference[key]
        max_abs = max(max_abs, abs(new - ref))
        if not within_mode(new=new, ref=ref, center=center, scale=scale, mode=mode):
            failures += 1
    return ReproductionComparison(
        compared=len(common),
        failures=failures,
        missing=len(set(reference) - set(predicted)),
        extra=len(set(predicted) - set(reference)),
        max_abs_diff=max_abs,
        max_normalized_diff=max_abs / scale,
    )
