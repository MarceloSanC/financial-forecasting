"""Schemas de pedido e resposta de `POST /inference/run` (Stage 7.4; ADR 7.4.0002).

ATENÇÃO — módulo sob `adapters/in/` (keyword `in`): carregue com
`importlib.import_module` (LAYOUT §8).

Pydantic só aqui, na fronteira (skill `fastapi-thin-adapter`). O pedido valida a forma
(data ISO, horizontes > 0, listas não vazias e sem repetição → 422 padrão do FastAPI)
e vira `ServeInferenceQuery`; a resposta é o `InferencePayload` com `schema_version`
(I9) e com a regra de infinito do ADR 7.4.0002 item 3 em todo limite que pode ser
infinito (intervalos conformais e participações de H3):

- `±inf` no DTO → `null` + `*_infinite = true`;
- `None` no DTO (sem valor, status não-`ok`) → `null` + `false`;
- finito → o número + `false`, em qualquer status.

Os floats da resposta recusam não finitos (`allow_inf_nan=False`): o JSON não tem
infinito (RFC 8259 §6) e o Pydantic o serializaria como `null` sem flag.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from financial_forecasting.features.inference.application.dtos.serving_gold import (
    H3ReadingRecord,
    H3ShareRecord,
    VsnRecord,
)
from financial_forecasting.features.inference.application.use_cases.serve_inference import (
    ConformalBlock,
    ConformalInterval,
    ExplainabilityBlock,
    GoldProvenance,
    HorizonForecast,
    InferencePayload,
    SeedForecast,
    ServeInferenceQuery,
)

SCHEMA_VERSION: Literal[1] = 1
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Horizon = Annotated[int, Field(strict=True, gt=0)]
Seed = Annotated[int, Field(strict=True)]


def _limit(value: float | None) -> tuple[float | None, bool]:
    """(valor, flag) de um limite: infinito → (None, True); sem valor → (None, False)."""
    if value is None:
        return None, False
    if math.isinf(value):
        return None, True
    return value, False


class InferenceRunRequest(BaseModel):
    """Pedido: ativo, data de decisão (ISO) e, opcionais, horizontes e seeds."""

    asset: str = Field(min_length=1)
    decision_date: date
    horizons: list[Horizon] | None = Field(default=None, min_length=1)
    seeds: list[Seed] | None = Field(default=None, min_length=1)

    @field_validator("decision_date", mode="before")
    @classmethod
    def _iso_text(cls, value: object) -> object:
        # só texto `YYYY-MM-DD`: o modo lax do Pydantic aceitaria um timestamp numérico, e
        # o `date.fromisoformat` do 3.12 aceitaria `20240315` e `2024-W11-5` (C2-1)
        if not isinstance(value, str) or _ISO_DATE.fullmatch(value) is None:
            raise ValueError("decision_date must be an ISO date string (YYYY-MM-DD)")
        return value

    @field_validator("horizons", "seeds")
    @classmethod
    def _no_repeats(cls, values: list[int] | None) -> list[int] | None:
        if values is not None and len(set(values)) != len(values):
            raise ValueError("values must not repeat")
        return values

    def to_query(self) -> ServeInferenceQuery:
        """O DTO de consulta do use case."""
        return ServeInferenceQuery(
            asset=self.asset,
            decision_date=self.decision_date,
            horizons=None if self.horizons is None else tuple(self.horizons),
            seeds=None if self.seeds is None else tuple(self.seeds),
        )


class ConformalIntervalResponse(BaseModel):
    """Intervalo conformal de um par, com os limites e as flags de infinito."""

    lower_level: FiniteFloat
    upper_level: FiniteFloat
    status: str
    gold_status: str | None
    reason: str | None
    lower: FiniteFloat | None
    upper: FiniteFloat | None
    lower_infinite: bool
    upper_infinite: bool

    @classmethod
    def from_dto(cls, interval: ConformalInterval) -> ConformalIntervalResponse:
        """Aplica a regra de (valor, flag) aos dois limites."""
        lower, lower_infinite = _limit(interval.lower)
        upper, upper_infinite = _limit(interval.upper)
        return cls(
            lower_level=interval.lower_level,
            upper_level=interval.upper_level,
            status=interval.status,
            gold_status=interval.gold_status,
            reason=interval.reason,
            lower=lower,
            upper=upper,
            lower_infinite=lower_infinite,
            upper_infinite=upper_infinite,
        )


class ConformalBlockResponse(BaseModel):
    """Bloco conformal de um membro."""

    status: str
    reason: str | None
    label: str
    variant: str
    intervals: list[ConformalIntervalResponse]

    @classmethod
    def from_dto(cls, block: ConformalBlock) -> ConformalBlockResponse:
        """Bloco e intervalos na ordem do DTO."""
        return cls(
            status=block.status,
            reason=block.reason,
            label=block.label,
            variant=block.variant,
            intervals=[ConformalIntervalResponse.from_dto(i) for i in block.intervals],
        )


class SeedForecastResponse(BaseModel):
    """A grade de uma seed num horizonte."""

    seed: int
    fold: str
    run_id: str
    quantiles: list[FiniteFloat]
    conformal: ConformalBlockResponse

    @classmethod
    def from_dto(cls, member: SeedForecast) -> SeedForecastResponse:
        """Membro com o seu bloco conformal."""
        return cls(
            seed=member.seed,
            fold=member.fold,
            run_id=member.run_id,
            quantiles=list(member.quantiles),
            conformal=ConformalBlockResponse.from_dto(member.conformal),
        )


class HorizonForecastResponse(BaseModel):
    """Os membros de um horizonte e a data-alvo."""

    horizon: int
    target_date: date
    members: list[SeedForecastResponse]

    @classmethod
    def from_dto(cls, forecast: HorizonForecast) -> HorizonForecastResponse:
        """Horizonte com os membros na ordem do DTO."""
        return cls(
            horizon=forecast.horizon,
            target_date=forecast.target_date,
            members=[SeedForecastResponse.from_dto(m) for m in forecast.members],
        )


class H3ShareResponse(BaseModel):
    """Participação de uma família por método, com o intervalo de Δ e as flags."""

    method: str
    family: str
    share_h1: FiniteFloat | None
    share_h7: FiniteFloat | None
    delta: FiniteFloat | None
    lower: FiniteFloat | None
    upper: FiniteFloat | None
    lower_infinite: bool
    upper_infinite: bool
    level: FiniteFloat | None
    side: int | None  # sinal de Δ̂_f em {-1, 0, +1}
    excludes_zero: bool | None
    status: str
    reason: str | None

    @classmethod
    def from_dto(cls, share: H3ShareRecord) -> H3ShareResponse:
        """Aplica a regra de (valor, flag) aos dois limites do intervalo."""
        lower, lower_infinite = _limit(share.lower)
        upper, upper_infinite = _limit(share.upper)
        return cls(
            method=share.method,
            family=share.family,
            share_h1=share.share_h1,
            share_h7=share.share_h7,
            delta=share.delta,
            lower=lower,
            upper=upper,
            lower_infinite=lower_infinite,
            upper_infinite=upper_infinite,
            level=share.level,
            side=share.side,
            excludes_zero=share.excludes_zero,
            status=share.status,
            reason=share.reason,
        )


class H3ReadingResponse(BaseModel):
    """A leitura de H3 pela regra pré-registrada."""

    reading_rule: str
    heterogeneous_permutation: bool | None
    heterogeneous_ablation: bool | None
    sustained: bool | None
    agreeing_families: list[str]
    n_points: int | None
    status: str
    reason: str | None

    @classmethod
    def from_dto(cls, reading: H3ReadingRecord) -> H3ReadingResponse:
        """Campos da leitura."""
        return cls(
            reading_rule=reading.reading_rule,
            heterogeneous_permutation=reading.heterogeneous_permutation,
            heterogeneous_ablation=reading.heterogeneous_ablation,
            sustained=reading.sustained,
            agreeing_families=list(reading.agreeing_families),
            n_points=reading.n_points,
            status=reading.status,
            reason=reading.reason,
        )


class VsnResponse(BaseModel):
    """Peso da VSN por variável ou por família."""

    kind: str
    name: str
    family: str
    p10: FiniteFloat | None
    p50: FiniteFloat | None
    p90: FiniteFloat | None
    n_decisions: int | None
    status: str
    reason: str | None

    @classmethod
    def from_dto(cls, record: VsnRecord) -> VsnResponse:
        """Campos do resumo."""
        return cls(
            kind=record.kind,
            name=record.name,
            family=record.family,
            p10=record.p10,
            p50=record.p50,
            p90=record.p90,
            n_decisions=record.n_decisions,
            status=record.status,
            reason=record.reason,
        )


class ExplainabilityResponse(BaseModel):
    """Leitura de H3 do estudo (descritiva)."""

    status: str
    reason: str | None
    label: str
    shares: list[H3ShareResponse]
    reading: H3ReadingResponse | None
    vsn: list[VsnResponse]
    vsn_label: str

    @classmethod
    def from_dto(cls, block: ExplainabilityBlock) -> ExplainabilityResponse:
        """Bloco com os registros na ordem do DTO."""
        return cls(
            status=block.status,
            reason=block.reason,
            label=block.label,
            shares=[H3ShareResponse.from_dto(s) for s in block.shares],
            reading=None if block.reading is None else H3ReadingResponse.from_dto(block.reading),
            vsn=[VsnResponse.from_dto(v) for v in block.vsn],
            vsn_label=block.vsn_label,
        )


class GoldProvenanceResponse(BaseModel):
    """A geração gold lida."""

    published: bool
    generation_status: str | None
    preregistration_ref: str | None
    candidate: str | None
    finished_at: str | None

    @classmethod
    def from_dto(cls, gold: GoldProvenance) -> GoldProvenanceResponse:
        """Campos da geração."""
        return cls(
            published=gold.published,
            generation_status=gold.generation_status,
            preregistration_ref=gold.preregistration_ref,
            candidate=gold.candidate,
            finished_at=gold.finished_at,
        )


class InferenceRunResponse(BaseModel):
    """Resposta 200 de `POST /inference/run`, com `schema_version` (I9; ADR 7.4.0002)."""

    schema_version: Literal[1]
    asset: str
    decision_date: date
    cohort_id: str
    model_version: str
    quantile_levels: list[FiniteFloat]
    forecasts: list[HorizonForecastResponse]
    explainability: ExplainabilityResponse
    gold: GoldProvenanceResponse

    @classmethod
    def from_payload(cls, payload: InferencePayload) -> InferenceRunResponse:
        """O payload do use case na forma servida."""
        return cls(
            schema_version=SCHEMA_VERSION,
            asset=payload.asset,
            decision_date=payload.decision_date,
            cohort_id=payload.cohort_id,
            model_version=payload.model_version,
            quantile_levels=list(payload.quantile_levels),
            forecasts=[HorizonForecastResponse.from_dto(f) for f in payload.forecasts],
            explainability=ExplainabilityResponse.from_dto(payload.explainability),
            gold=GoldProvenanceResponse.from_dto(payload.gold),
        )
