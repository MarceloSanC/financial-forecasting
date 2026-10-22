"""DTOs do port `ServingGoldReader` — o que a API de inferência lê do gold (Stage 7.4).

Tipos do CONSUMIDOR (concept 7.4 §4; ADR 7.4.0001 item 7). O leitor real é o use case
`ReadServingGold` do `evaluation`, que lê a geração viva pelo `GoldGenerationReader` e
monta estes DTOs: a aresta de dados vai evaluation → inference, exceção declarada aos
itens 2-3 do ADR 0.0.0053 (a direção oposta fecharia ciclo com a aresta
`refresh_gold → calibrate_conformal`). O `inference` nunca importa o `evaluation`.

Convenções:

- limite infinito é `math.inf` aqui (`None` = sem valor); o adapter HTTP o serializa
  como `null` + flag (ADR 7.4.0002 item 3);
- bloco `unavailable` carrega motivo e nenhum registro; bloco `available` não carrega
  motivo (concept I8);
- os três rótulos são as constantes de dono único do `evaluation`, sempre preenchidos,
  também em bloco indisponível (concept I7).
"""

from __future__ import annotations

import math
from collections.abc import Sized
from dataclasses import dataclass
from typing import Final

AVAILABLE: Final = "available"
UNAVAILABLE: Final = "unavailable"
OK: Final = "ok"
LOWER: Final = "lower"
UPPER: Final = "upper"
# Status de uma geração gold publicada: os valores do `RefreshStatus` do `evaluation`,
# repetidos aqui porque o `inference` não o importa; a paridade é presa por
# `tests/architecture/test_serving_gold_status_parity.py` (Checkpoint C1-4).
COMPLETED: Final = "COMPLETED"
BLOCKED: Final = "BLOCKED"
GENERATION_STATUSES: Final = frozenset({COMPLETED, BLOCKED})

_BLOCK_STATUSES: Final = frozenset({AVAILABLE, UNAVAILABLE})
_UNIT_STATUSES: Final = frozenset({OK, "undefined", "error"})
_TAILS: Final = frozenset({LOWER, UPPER})
_SIDES: Final = frozenset({-1, 0, 1})


def _check_not_nan(field: str, *values: float | None) -> None:
    for value in values:
        if value is not None and math.isnan(value):
            raise ValueError(f"{field} must not be NaN")


def _check_status(status: str) -> None:
    if not isinstance(status, str) or not status:
        raise ValueError(f"status must be a non-empty string, got {status!r}")


@dataclass(frozen=True)
class ConformalCorrectionRecord:
    """Uma cauda de uma unidade conformal (`fold_raw`, seed, horizonte, par, variante)."""

    fold_raw: str
    seed: int
    horizon: int
    lower_level: float
    upper_level: float
    variant: str
    tail: str
    tail_level: float
    status: str
    reason: str | None
    n: int | None
    rank: int | None
    correction: float | None  # Q̂ da cauda; `math.inf` quando infinito; `None` fora de `ok`

    def __post_init__(self) -> None:
        """Cauda e status do catálogo da 7.2; cauda `ok` tem correção e `n` (I3 da 7.2)."""
        if self.tail not in _TAILS:
            raise ValueError(f"tail must be one of {sorted(_TAILS)}, got {self.tail!r}")
        if self.status not in _UNIT_STATUSES:
            raise ValueError(f"status must be one of {sorted(_UNIT_STATUSES)}, got {self.status!r}")
        _check_not_nan("correction", self.correction)
        if self.status == OK and (self.correction is None or self.n is None):
            raise ValueError("an ok tail needs a correction and n")


@dataclass(frozen=True)
class H3ShareRecord:
    """Participação de uma família por método em h+1 e h+7, com o intervalo de Δ."""

    method: str
    family: str
    share_h1: float | None
    share_h7: float | None
    delta: float | None
    lower: float | None  # ±inf permitido; `None` = sem valor
    upper: float | None
    level: float | None
    side: int | None  # sinal de Δ̂_f em {-1, 0, +1} (`FamilyShare.side`); `None` sem valor
    excludes_zero: bool | None
    status: str
    reason: str | None

    def __post_init__(self) -> None:
        """Sem NaN; participação `ok` tem os dois limites."""
        _check_status(self.status)
        _check_not_nan(
            "share", self.share_h1, self.share_h7, self.delta, self.lower, self.upper, self.level
        )
        if self.side is not None and (isinstance(self.side, bool) or self.side not in _SIDES):
            raise ValueError(f"side must be -1, 0 or +1, got {self.side!r}")
        if self.status == OK and (self.lower is None or self.upper is None):
            raise ValueError("an ok share needs both interval bounds")


@dataclass(frozen=True)
class H3ReadingRecord:
    """A leitura de H3 pela regra pré-registrada (sustentada ou não)."""

    reading_rule: str
    heterogeneous_permutation: bool | None
    heterogeneous_ablation: bool | None
    sustained: bool | None
    agreeing_families: tuple[str, ...]
    n_points: int | None
    status: str
    reason: str | None

    def __post_init__(self) -> None:
        """Regra e status não vazios."""
        if not self.reading_rule:
            raise ValueError("reading_rule must not be empty")
        _check_status(self.status)


@dataclass(frozen=True)
class VsnRecord:
    """Peso da VSN por variável ou por família (p10/p50/p90; nulos em resumo indefinido)."""

    kind: str
    name: str
    family: str
    p10: float | None
    p50: float | None
    p90: float | None
    n_decisions: int | None
    status: str
    reason: str | None

    def __post_init__(self) -> None:
        """Status não vazio; sem NaN."""
        _check_status(self.status)
        _check_not_nan("vsn", self.p10, self.p50, self.p90)


def _check_block(name: str, status: str, reason: str | None, *records: Sized | None) -> None:
    if status not in _BLOCK_STATUSES:
        raise ValueError(f"{name}_status must be one of {sorted(_BLOCK_STATUSES)}, got {status!r}")
    if status == UNAVAILABLE:
        if not reason:
            raise ValueError(f"an unavailable {name} block needs a reason")
        if any(record is not None and len(record) > 0 for record in records):
            raise ValueError(f"an unavailable {name} block carries no records")
    elif reason is not None:
        raise ValueError(f"an available {name} block carries no reason")


@dataclass(frozen=True)
class ServingGold:
    """O que a API serve da geração gold viva de um cohort (ou a sua ausência)."""

    published: bool
    generation_status: str | None
    preregistration_ref: str | None
    candidate: str | None
    finished_at: str | None  # `datetime.isoformat()` do manifesto
    conformal_status: str
    conformal_reason: str | None
    explainability_status: str
    explainability_reason: str | None
    conformal_label: str
    h3_label: str
    vsn_label: str
    corrections: tuple[ConformalCorrectionRecord, ...]
    shares: tuple[H3ShareRecord, ...]
    reading: H3ReadingRecord | None
    vsn: tuple[VsnRecord, ...]

    def __post_init__(self) -> None:
        """Blocos coerentes com o status; não publicado sem campos de geração; rótulos."""
        _check_block("conformal", self.conformal_status, self.conformal_reason, self.corrections)
        reading = None if self.reading is None else (self.reading,)
        _check_block(
            "explainability",
            self.explainability_status,
            self.explainability_reason,
            self.shares,
            reading,
            self.vsn,
        )
        generation = (
            self.generation_status,
            self.preregistration_ref,
            self.candidate,
            self.finished_at,
        )
        if not self.published:
            if AVAILABLE in (self.conformal_status, self.explainability_status):
                raise ValueError("an unpublished gold has no available block")
            if any(value is not None for value in generation):
                raise ValueError("an unpublished gold carries no generation fields")
        elif any(value is None for value in generation):
            raise ValueError("a published gold carries every generation field")
        elif self.generation_status not in GENERATION_STATUSES:
            raise ValueError(
                f"generation_status must be one of {sorted(GENERATION_STATUSES)}, "
                f"got {self.generation_status!r}"
            )
        elif self.generation_status == BLOCKED and AVAILABLE in (
            self.conformal_status,
            self.explainability_status,
        ):
            raise ValueError("a BLOCKED generation has no available block")
        for label in (self.conformal_label, self.h3_label, self.vsn_label):
            if not label:
                raise ValueError("labels must not be empty")

    @classmethod
    def unpublished(
        cls, *, reason: str, conformal_label: str, h3_label: str, vsn_label: str
    ) -> ServingGold:
        """A partição sem geração publicada: os dois blocos indisponíveis pelo `reason`."""
        return cls(
            published=False,
            generation_status=None,
            preregistration_ref=None,
            candidate=None,
            finished_at=None,
            conformal_status=UNAVAILABLE,
            conformal_reason=reason,
            explainability_status=UNAVAILABLE,
            explainability_reason=reason,
            conformal_label=conformal_label,
            h3_label=h3_label,
            vsn_label=vsn_label,
            corrections=(),
            shares=(),
            reading=None,
            vsn=(),
        )
