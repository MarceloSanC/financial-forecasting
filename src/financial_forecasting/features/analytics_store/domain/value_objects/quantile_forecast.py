"""VO `QuantileForecast` — grade densa de quantis + guardrail de monotonicidade.

Value object de domínio **frozen, stdlib-only** (concept 4.3 §4, I5/C3/C4; ADR
`4_3_0002`). Carrega a **grade densa** de níveis de quantil (`levels` estritamente
crescentes e únicos) com `raw_values` alinhados 1:1, e materializa o **guardrail de
monotonicidade generalizado** — a extensão de `enforce_monotonic_triplet` do old
(p10/p50/p90) para uma grade arbitrária de ~7-9 níveis (decisão humana H-1 / ADR de
fundação `0_0_0012`).

Regra do guardrail (ADR `4_3_0002`):

- **Todos finitos:** ``guardrail_values = tuple(sorted(raw_values))`` (não-decrescente
  ao longo dos níveis); ``guardrail_applied = (guardrail_values != raw_values)`` —
  exatamente a semântica "a ordem mudou" do old, generalizada de 3 para N níveis.
- **Algum não-finito (`inf`/`nan`) ou `None`:** **preserva** os `raw_values` em
  `guardrail_values` e marca ``guardrail_applied = False`` (postura defensiva do old);
  a decisão sobre qualidade/degeneração é deferida ao Step 6.

O guardrail é **SEPARADO** do gate de degeneração (`q_low == q_high`, distribuição
colapsada) — este NÃO é implementado aqui; é concern de avaliação do Step 6 (ADR de
fundação `0_0_0011`). O guardrail nunca iguala nem rejeita quantis colapsados:
`q_low == q_high` passa intacto.

PUREZA (concept 4.3 I8 / D3): importa só `dataclasses` + `math`; valores `float`, sem
`pandas`/`numpy`. Gates domain-purity (import-linter) + `scripts/check_layout.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class QuantileForecast:
    """Grade densa de quantis (raw + post-guardrail) para um `(decision, horizon)`.

    Campos:
        levels: níveis de quantil estritamente crescentes e únicos (ex.:
            ``(0.1, 0.25, 0.5, 0.75, 0.9)``).
        raw_values: valores brutos do modelo, alinhados 1:1 a `levels`.
        guardrail_values: valores após o guardrail de monotonicidade (não-decrescentes
            ao longo dos níveis), ou os `raw_values` preservados se houver não-finito.
        guardrail_applied: ``True`` se o guardrail reordenou (a ordem mudou);
            ``False`` caso já-monotônico ou preservado por não-finito/`None`.
    """

    levels: tuple[float, ...]
    raw_values: tuple[float, ...]
    guardrail_values: tuple[float, ...]
    guardrail_applied: bool

    @classmethod
    def from_raw(
        cls,
        *,
        levels: tuple[float, ...],
        raw_values: tuple[float, ...],
    ) -> QuantileForecast:
        """Constrói o VO validando a grade e aplicando o guardrail monotônico.

        Args:
            levels: níveis de quantil — estritamente crescentes e únicos.
            raw_values: valores brutos do modelo, alinhados 1:1 a `levels`.

        Returns:
            `QuantileForecast` com `guardrail_values`/`guardrail_applied` resolvidos.

        Raises:
            ValueError: `len(levels) != len(raw_values)`, ou `levels` não estritamente
                crescente / com duplicatas (C3).
        """
        if len(levels) != len(raw_values):
            raise ValueError(
                f"levels and raw_values must align: len(levels)={len(levels)} "
                f"!= len(raw_values)={len(raw_values)}"
            )
        if not levels:
            raise ValueError("levels must be non-empty")
        if any(b <= a for a, b in pairwise(levels)):
            raise ValueError(f"levels must be strictly increasing and unique, got {levels}")

        guardrail_values, guardrail_applied = cls._enforce_monotonic(raw_values)
        return cls(
            levels=levels,
            raw_values=raw_values,
            guardrail_values=guardrail_values,
            guardrail_applied=guardrail_applied,
        )

    @staticmethod
    def _enforce_monotonic(
        raw_values: tuple[float, ...],
    ) -> tuple[tuple[float, ...], bool]:
        """Garante quantis não-decrescentes via `sorted`; preserva se houver não-finito.

        Generaliza `enforce_monotonic_triplet` do old (`quantile_guardrail_service.py`)
        de 3 para N níveis (C4). Não-finito/`None` → preserva, `applied = False`.
        """
        if any(not _is_finite_number(v) for v in raw_values):
            return raw_values, False
        ordered = tuple(sorted(raw_values))
        return ordered, ordered != raw_values


def _is_finite_number(value: object) -> bool:
    """`True` só para `int`/`float` finitos (exclui `None`, `nan`, `inf`, `bool`).

    Postura defensiva do old: qualquer valor não-finito/`None` faz o guardrail
    preservar a grade sem reordenar (C4). `bool` é excluído por defesa (não é um
    valor de quantil legítimo, ainda que subclasse de `int`).
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return math.isfinite(value)
