"""`ServeInference` — serve as predições de teste gravadas do candidato (Stage 7.4).

Use case = port-in da API de inferência (concept 7.4 §4, D8; ADR 7.4.0001). Não roda o
modelo, não carrega checkpoint e não lê o realizado (I1, I2). Fluxo (technical 7.4 §1):

1. ativo, horizontes e seeds do pedido contra o escopo servido → `NoServedDataError`;
2. `dim_run` do cohort, só os runs do `model_version` servido (o mesmo
   `parent_sweep_id` também tem baselines); zero runs, seed do escopo sem run ou run
   sem `fold` → `ApplicationError` (I3);
3. `fact_oos_predictions` da partição do ano da decisão, só `split = "test"` de um run
   do cohort, nos horizontes pedidos e com a data de `timestamp_utc` igual à decisão;
4. um run por (seed, horizonte): nenhum → 404 com o que faltou; mais de um → 500;
5. grade = os `quantile_levels` do escopo, valor `value_guardrail` (I4); `target_date`
   igual entre as seeds do horizonte;
6. gold pelo `ServingGoldReader`; o use case aplica só a regra "outro candidato" (I8);
7. intervalo conformal da variante de registro por membro e par, por
   `PairCorrection.limits`, sem rearranjo (I6);
8. `ValueError` ao montar DTO a partir do lido → `ApplicationError` com contexto (I13).

Uma entrada por seed, sem agregação (I5, D2). Ordem fixa de horizontes, seeds, níveis
e pares (I11). Os rótulos vêm do `ServingGold` (I7): nenhum literal deles aqui.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from fractions import Fraction
from itertools import pairwise
from typing import Final, Literal

from financial_forecasting.features.inference.application.dtos.serving_gold import (
    AVAILABLE,
    COMPLETED,
    LOWER,
    OK,
    UNAVAILABLE,
    UPPER,
    ConformalCorrectionRecord,
    H3ReadingRecord,
    H3ShareRecord,
    ServingGold,
    VsnRecord,
)
from financial_forecasting.features.inference.application.ports.out.serving_gold_reader import (
    ServingGoldReader,
)
from financial_forecasting.features.inference.application.ports.out.silver_table_reader import (
    SilverTableReader,
)
from financial_forecasting.features.inference.domain.exceptions.serving import (
    NoServedDataError,
)
from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalVariant,
    PairCorrection,
    TailCorrection,
    exact_level,
)
from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    is_finite,
)
from financial_forecasting.shared.application.exceptions import ApplicationError

_SILVER: Final = "silver"
_DIM_RUN: Final = "dim_run"
_FACT: Final = "fact_oos_predictions"
_TEST: Final = "test"
_VARIANT: Final = ConformalVariant.SPLIT_CQR
_UNIT_MISSING: Final = "unidade ausente na geração gold"
_OTHER_CANDIDATE: Final = "geração gold de outro candidato"
_HALF: Final = Fraction(1, 2)
_BLOCK_STATUSES: Final = frozenset({AVAILABLE, UNAVAILABLE})
_INTERVAL_STATUSES: Final = frozenset({OK, UNAVAILABLE})
_GOLD_STATUSES: Final = frozenset({OK, "undefined", "error"})


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_ids(name: str, values: tuple[int, ...], *, positive: bool) -> None:
    if not values:
        raise ValueError(f"{name} must not be empty")
    if not all(_is_int(value) for value in values):
        raise ValueError(f"{name} must be integers, got {values!r}")
    if any(a >= b for a, b in pairwise(values)):
        raise ValueError(f"{name} must be unique and increasing, got {values!r}")
    if positive and values[0] < 1:
        raise ValueError(f"{name} must be >= 1, got {values!r}")


def _check_no_nan(field: str, *values: float | None) -> None:
    for value in values:
        if value is not None and math.isnan(value):
            raise ValueError(f"{field} must not be NaN")


@dataclass(frozen=True)
class ServingScope:
    """O cohort que o processo serve (P2): identidade, grade e seeds do candidato."""

    cohort_id: str
    asset: str
    feature_set_name: str
    model_version: str
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    seeds: tuple[int, ...]

    def __post_init__(self) -> None:
        """Campos não vazios; horizontes e seeds crescentes; grade simétrica com mediana."""
        for name in ("cohort_id", "asset", "feature_set_name", "model_version"):
            if not getattr(self, name):
                raise ValueError(f"{name} must not be empty")
        _check_ids("horizons", self.horizons, positive=True)
        _check_ids("seeds", self.seeds, positive=False)
        levels = self.quantile_levels
        if not levels:
            raise ValueError("quantile_levels must not be empty")
        exact = [exact_level(level) for level in levels]
        if any(a >= b for a, b in pairwise(exact)):
            raise ValueError(f"quantile_levels must be strictly increasing, got {levels!r}")
        if not (exact[0] > 0 and exact[-1] < 1):
            raise ValueError(f"quantile_levels must lie in (0, 1), got {levels!r}")
        if len(levels) % 2 == 0 or exact[len(levels) // 2] != _HALF:
            raise ValueError(f"quantile_levels must have the median 0.5 at the centre: {levels!r}")
        for lower, upper in self.pairs:
            if exact_level(lower) + exact_level(upper) != 1:
                raise ValueError(f"quantile_levels must be symmetric: ({lower!r}, {upper!r})")

    @property
    def pairs(self) -> tuple[tuple[float, float], ...]:
        """Pares simétricos (τ_lo, τ_hi), do externo ao interno."""
        levels = self.quantile_levels
        last = len(levels) - 1
        return tuple((levels[i], levels[last - i]) for i in range(len(levels) // 2))


@dataclass(frozen=True)
class ServeInferenceQuery:
    """Pedido: ativo, data de decisão e, opcionais, horizontes e seeds (`None` = todos)."""

    asset: str
    decision_date: date
    horizons: tuple[int, ...] | None = None
    seeds: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        """Listas pedidas não vazias e sem repetição."""
        for name, values in (("horizons", self.horizons), ("seeds", self.seeds)):
            if values is None:
                continue
            if not values:
                raise ValueError(f"{name} must not be empty")
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must not repeat, got {values!r}")


@dataclass(frozen=True)
class ConformalInterval:
    """Intervalo de um par: `ok` com os dois limites (±inf permitido) ou `unavailable`."""

    lower_level: float
    upper_level: float
    status: str
    gold_status: str | None
    reason: str | None
    lower: float | None
    upper: float | None

    def __post_init__(self) -> None:
        """Status do catálogo; `ok` ⇒ limites; `unavailable` ⇒ sem limites; sem NaN."""
        if self.status not in _INTERVAL_STATUSES:
            raise ValueError(f"interval status must be ok or unavailable, got {self.status!r}")
        if self.gold_status is not None and self.gold_status not in _GOLD_STATUSES:
            raise ValueError(f"gold_status outside the catalogue: {self.gold_status!r}")
        _check_no_nan("interval limit", self.lower, self.upper)
        if self.status == OK and (self.lower is None or self.upper is None):
            raise ValueError("an ok interval needs both limits")
        if self.status == UNAVAILABLE and (self.lower is not None or self.upper is not None):
            raise ValueError("an unavailable interval carries no limits")


def _check_block(status: str, reason: str | None, label: str, *records: object) -> None:
    if status not in _BLOCK_STATUSES:
        raise ValueError(f"block status must be available or unavailable, got {status!r}")
    if not label:
        raise ValueError("block label must not be empty")
    if status == UNAVAILABLE:
        if not reason:
            raise ValueError("an unavailable block needs a reason")
        if any(record not in ((), None) for record in records):
            raise ValueError("an unavailable block carries no records")
    elif reason is not None:
        raise ValueError("an available block carries no reason")


@dataclass(frozen=True)
class ConformalBlock:
    """Intervalos conformais de um membro, com o rótulo de cobertura empírica."""

    status: str
    reason: str | None
    label: str
    variant: str
    intervals: tuple[ConformalInterval, ...]

    def __post_init__(self) -> None:
        """Bloco coerente com o status; variante de registro."""
        _check_block(self.status, self.reason, self.label, self.intervals)
        if self.variant != _VARIANT.value:
            raise ValueError(f"variant must be {_VARIANT.value!r}, got {self.variant!r}")


@dataclass(frozen=True)
class SeedForecast:
    """A grade de uma seed num horizonte, com o run que a gravou e o seu intervalo."""

    seed: int
    fold: str
    run_id: str
    quantiles: tuple[float, ...]
    conformal: ConformalBlock


@dataclass(frozen=True)
class HorizonForecast:
    """Os membros (um por seed) de um horizonte e a data-alvo comum."""

    horizon: int
    target_date: date
    members: tuple[SeedForecast, ...]


@dataclass(frozen=True)
class ExplainabilityBlock:
    """Leitura de H3 do estudo (descritiva), igual em toda resposta (D7)."""

    status: str
    reason: str | None
    label: str
    shares: tuple[H3ShareRecord, ...]
    reading: H3ReadingRecord | None
    vsn: tuple[VsnRecord, ...]
    vsn_label: str

    def __post_init__(self) -> None:
        """Bloco coerente com o status; rótulo da VSN não vazio."""
        _check_block(self.status, self.reason, self.label, self.shares, self.reading, self.vsn)
        if not self.vsn_label:
            raise ValueError("vsn_label must not be empty")


@dataclass(frozen=True)
class GoldProvenance:
    """A geração gold lida (campos `None` quando não publicada)."""

    published: bool
    generation_status: str | None
    preregistration_ref: str | None
    candidate: str | None
    finished_at: str | None


@dataclass(frozen=True)
class InferencePayload:
    """A resposta do `ServeInference` (o adapter HTTP acrescenta `schema_version`)."""

    asset: str
    decision_date: date
    cohort_id: str
    model_version: str
    quantile_levels: tuple[float, ...]
    forecasts: tuple[HorizonForecast, ...]
    explainability: ExplainabilityBlock
    gold: GoldProvenance


@dataclass(frozen=True)
class _Run:
    run_id: str
    seed: int
    fold: str


@dataclass(frozen=True)
class _Member:
    run: _Run
    quantiles: tuple[float, ...]
    target_date: date


_UnitKey = tuple[str, int, int, Fraction, Fraction]


def _date_of(value: object, field: str) -> date:
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        raise ValueError(f"{field}: {value!r} is not an ISO 8601 timestamp") from None


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field}: {value!r} is not a number")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"{field}: {value!r} is not a number") from None
    if not is_finite(number):
        raise ValueError(f"{field}: {value!r} is not finite")
    return number


def _integer(value: object, field: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    number = _number(value, field)
    if not number.is_integer():
        raise ValueError(f"{field}: {value!r} is not an integer")
    return int(number)


class ServeInference:
    """Serve, sem rodar o modelo, a grade gravada, o intervalo conformal e a leitura de H3."""

    def __init__(
        self, *, scope: ServingScope, silver: SilverTableReader, gold: ServingGoldReader
    ) -> None:
        self._scope = scope
        self._silver = silver
        self._gold = gold

    def __call__(self, query: ServeInferenceQuery) -> InferencePayload:
        """O payload do pedido; `NoServedDataError` quando falta dado gravado."""
        horizons, seeds = self._requested(query)
        try:
            runs = self._cohort_runs()
            points = self._points(query.decision_date, runs, horizons, seeds)
            members = {key: self._member(query.decision_date, key, rows) for key, rows in points}
            gold = self._gold.read(asset=self._scope.asset, cohort_id=self._scope.cohort_id)
            return self._payload(query, horizons, seeds, members, gold)
        except ValueError as exc:
            raise ApplicationError(
                f"dado gravado inconsistente ao servir {query.decision_date.isoformat()} "
                f"do cohort {self._scope.cohort_id}: {exc}"
            ) from exc

    # --- 1. pedido contra o escopo -----------------------------------------------------

    def _requested(self, query: ServeInferenceQuery) -> tuple[tuple[int, ...], tuple[int, ...]]:
        scope = self._scope
        if query.asset != scope.asset:
            raise NoServedDataError(
                f"ativo {query.asset!r} (o cohort servido é do ativo {scope.asset!r})"
            )
        chosen: list[tuple[int, ...]] = []
        for name, wanted, available in (
            ("horizonte", query.horizons, scope.horizons),
            ("seed", query.seeds, scope.seeds),
        ):
            asked = available if wanted is None else wanted
            outside = sorted(set(asked) - set(available))
            if outside:
                raise NoServedDataError(
                    f"{name}(s) {outside} fora do cohort (o cohort tem {list(available)})"
                )
            chosen.append(tuple(value for value in available if value in set(asked)))
        return chosen[0], chosen[1]

    # --- 2. runs do candidato no cohort -------------------------------------------------

    def _cohort_runs(self) -> dict[str, _Run]:
        scope = self._scope
        rows = self._silver.read(
            layer=_SILVER,
            table=_DIM_RUN,
            filters={"asset": scope.asset, "parent_sweep_id": scope.cohort_id},
        )
        candidate = [
            row
            for row in rows
            if row.get("asset") == scope.asset
            and row.get("parent_sweep_id") == scope.cohort_id
            and row.get("model_version") == scope.model_version
        ]
        if not candidate:
            raise ApplicationError(
                f"o silver não tem runs do cohort {scope.cohort_id} ({scope.model_version}); "
                "confira o DATA_ROOT"
            )
        runs: dict[str, _Run] = {}
        for row in candidate:
            run_id = str(row["run_id"])
            fold = row.get("fold")
            if fold is None or fold == "":
                raise ApplicationError(
                    f"run {run_id} do candidato sem fold no dim_run do cohort {scope.cohort_id}"
                )
            seed = row.get("seed")
            if seed is None:
                continue  # run sem seed nunca é servido (o escopo lista as seeds)
            runs[run_id] = _Run(run_id=run_id, seed=_integer(seed, "dim_run.seed"), fold=str(fold))
        with_run = {run.seed for run in runs.values()}
        missing = [seed for seed in scope.seeds if seed not in with_run]
        if missing:
            raise ApplicationError(
                f"seed(s) {missing} do cohort {scope.cohort_id} sem run do candidato no dim_run"
            )
        return runs

    # --- 3-4. linhas de teste da decisão ------------------------------------------------

    def _points(
        self,
        decision: date,
        runs: Mapping[str, _Run],
        horizons: tuple[int, ...],
        seeds: tuple[int, ...],
    ) -> list[tuple[tuple[int, int], tuple[_Run, list[Mapping[str, object]]]]]:
        scope = self._scope
        rows = self._silver.read(
            layer=_SILVER,
            table=_FACT,
            filters={
                "asset": scope.asset,
                "feature_set_name": scope.feature_set_name,
                "year": decision.year,
            },
        )
        wanted_seeds, wanted_horizons = set(seeds), set(horizons)
        found: dict[tuple[int, int], dict[str, list[Mapping[str, object]]]] = {}
        for row in rows:
            run = runs.get(str(row.get("run_id")))
            if run is None or run.seed not in wanted_seeds or row.get("split") != _TEST:
                continue
            horizon = _integer(row.get("horizon"), "fact_oos_predictions.horizon")
            if horizon not in wanted_horizons:
                continue
            if _date_of(row.get("timestamp_utc"), "timestamp_utc") != decision:
                continue
            found.setdefault((run.seed, horizon), {}).setdefault(run.run_id, []).append(row)
        points: list[tuple[tuple[int, int], tuple[_Run, list[Mapping[str, object]]]]] = []
        missing: list[tuple[int, int]] = []
        for horizon in horizons:
            for seed in seeds:
                by_run = found.get((seed, horizon))
                if not by_run:
                    missing.append((seed, horizon))
                    continue
                if len(by_run) > 1:
                    raise ApplicationError(
                        f"{len(by_run)} runs de teste ({sorted(by_run)}) para a seed {seed}, "
                        f"h+{horizon}, decisão {decision.isoformat()}"
                    )
                ((run_id, point_rows),) = by_run.items()
                points.append(((seed, horizon), (runs[run_id], point_rows)))
        if missing:
            listed = ", ".join(f"(seed {seed}, h+{horizon})" for seed, horizon in missing)
            raise NoServedDataError(
                f"decisão {decision.isoformat()} sem linha de teste para {listed}"
            )
        return points

    # --- 5. grade de um membro ----------------------------------------------------------

    def _member(
        self,
        decision: date,
        key: tuple[int, int],
        point: tuple[_Run, Sequence[Mapping[str, object]]],
    ) -> _Member:
        run, rows = point
        where = f"run {run.run_id} (seed {key[0]}, h+{key[1]}, decisão {decision.isoformat()})"
        levels = self._scope.quantile_levels
        index = {level: position for position, level in enumerate(levels)}
        values: list[float | None] = [None] * len(levels)
        targets: set[date] = set()
        for row in rows:
            level = _number(row.get("quantile_level"), "quantile_level")
            position = index.get(level)
            if position is None:
                raise ApplicationError(f"{where}: nível {level!r} fora da grade do cohort")
            if values[position] is not None:
                raise ApplicationError(f"{where}: nível {level!r} repetido")
            values[position] = _number(row.get("value_guardrail"), "value_guardrail")
            targets.add(_date_of(row.get("target_timestamp_utc"), "target_timestamp_utc"))
        absent = [level for level, value in zip(levels, values, strict=True) if value is None]
        if absent:
            raise ApplicationError(f"{where}: grade incompleta, faltam os níveis {absent}")
        if len(targets) != 1:
            raise ApplicationError(f"{where}: datas-alvo divergentes {sorted(targets)}")
        quantiles = tuple(value for value in values if value is not None)
        return _Member(run=run, quantiles=quantiles, target_date=targets.pop())

    # --- 6-7. gold e montagem ------------------------------------------------------------

    def _payload(
        self,
        query: ServeInferenceQuery,
        horizons: tuple[int, ...],
        seeds: tuple[int, ...],
        members: Mapping[tuple[int, int], _Member],
        gold: ServingGold,
    ) -> InferencePayload:
        scope = self._scope
        conformal = (gold.conformal_status, gold.conformal_reason)
        explainability = (gold.explainability_status, gold.explainability_reason)
        if (
            gold.published
            and gold.generation_status == COMPLETED
            and gold.candidate != scope.model_version
        ):
            reason = f"{_OTHER_CANDIDATE}: {gold.candidate} (servido: {scope.model_version})"
            conformal = explainability = (UNAVAILABLE, reason)
        units = self._units(gold.corrections) if conformal[0] == AVAILABLE else {}
        forecasts: list[HorizonForecast] = []
        for horizon in horizons:
            row = [members[(seed, horizon)] for seed in seeds]
            targets = {member.target_date for member in row}
            if len(targets) != 1:
                raise ApplicationError(
                    f"h+{horizon}, decisão {query.decision_date.isoformat()}: datas-alvo "
                    f"divergentes entre seeds {sorted(targets)}"
                )
            forecasts.append(
                HorizonForecast(
                    horizon=horizon,
                    target_date=targets.pop(),
                    members=tuple(
                        SeedForecast(
                            seed=seed,
                            fold=member.run.fold,
                            run_id=member.run.run_id,
                            quantiles=member.quantiles,
                            conformal=self._conformal(
                                conformal, gold.conformal_label, units, horizon, member
                            ),
                        )
                        for seed, member in zip(seeds, row, strict=True)
                    ),
                )
            )
        available = explainability[0] == AVAILABLE
        return InferencePayload(
            asset=scope.asset,
            decision_date=query.decision_date,
            cohort_id=scope.cohort_id,
            model_version=scope.model_version,
            quantile_levels=scope.quantile_levels,
            forecasts=tuple(forecasts),
            explainability=ExplainabilityBlock(
                status=explainability[0],
                reason=explainability[1],
                label=gold.h3_label,
                shares=gold.shares if available else (),
                reading=gold.reading if available else None,
                vsn=gold.vsn if available else (),
                vsn_label=gold.vsn_label,
            ),
            gold=GoldProvenance(
                published=gold.published,
                generation_status=gold.generation_status,
                preregistration_ref=gold.preregistration_ref,
                candidate=gold.candidate,
                finished_at=gold.finished_at,
            ),
        )

    @staticmethod
    def _units(
        corrections: Sequence[ConformalCorrectionRecord],
    ) -> dict[_UnitKey, dict[str, ConformalCorrectionRecord]]:
        units: dict[_UnitKey, dict[str, ConformalCorrectionRecord]] = {}
        for record in corrections:
            if record.variant != _VARIANT.value:
                continue
            key: _UnitKey = (
                record.fold_raw,
                record.seed,
                record.horizon,
                exact_level(record.lower_level),
                exact_level(record.upper_level),
            )
            tails = units.setdefault(key, {})
            if record.tail in tails:
                raise ApplicationError(f"cauda {record.tail} repetida na unidade conformal {key}")
            tails[record.tail] = record
        return units

    def _conformal(
        self,
        state: tuple[str, str | None],
        label: str,
        units: Mapping[_UnitKey, Mapping[str, ConformalCorrectionRecord]],
        horizon: int,
        member: _Member,
    ) -> ConformalBlock:
        if state[0] != AVAILABLE:
            return ConformalBlock(
                status=state[0], reason=state[1], label=label, variant=_VARIANT.value, intervals=()
            )
        levels = self._scope.quantile_levels
        last = len(levels) - 1
        seed = member.run.seed
        intervals = tuple(
            self._interval(
                units.get((member.run.fold, seed, horizon, exact_level(lo), exact_level(hi))),
                (lo, hi),
                (member.quantiles[i], member.quantiles[last - i]),
                f"fold {member.run.fold}, seed {seed}, h+{horizon}, par ({lo}, {hi})",
            )
            for i, (lo, hi) in enumerate(self._scope.pairs)
        )
        return ConformalBlock(
            status=AVAILABLE, reason=None, label=label, variant=_VARIANT.value, intervals=intervals
        )

    @staticmethod
    def _interval(
        tails: Mapping[str, ConformalCorrectionRecord] | None,
        pair: tuple[float, float],
        grid: tuple[float, float],
        where: str,
    ) -> ConformalInterval:
        lo, hi = pair
        if tails is None:
            return ConformalInterval(lo, hi, UNAVAILABLE, None, _UNIT_MISSING, None, None)
        if set(tails) != {LOWER, UPPER}:
            raise ApplicationError(
                f"unidade conformal {where} com uma cauda só ({sorted(tails)}) na geração gold"
            )
        lower, upper = tails[LOWER], tails[UPPER]
        if lower.status == OK and upper.status == OK:
            correction = PairCorrection(
                variant=_VARIANT,
                rho=None,
                lower=_tail(lower, LOWER, exact_level(lo), where),
                upper=_tail(upper, UPPER, 1 - exact_level(hi), where),
            )
            low, high = correction.limits(lower=grid[0], upper=grid[1])
            return ConformalInterval(lo, hi, OK, OK, None, low, high)
        failed = lower if lower.status != OK else upper
        return ConformalInterval(lo, hi, UNAVAILABLE, failed.status, failed.reason, None, None)


def _tail(
    record: ConformalCorrectionRecord,
    tail: Literal["lower", "upper"],
    alpha: Fraction,
    where: str,
) -> TailCorrection:
    if record.n is None or record.correction is None:  # o DTO já recusa; estreita o tipo
        raise ApplicationError(f"unidade conformal {where}: cauda ok sem correção ou n")
    return TailCorrection(
        tail=tail,
        level=record.tail_level,
        alpha=alpha,
        n=record.n,
        rank=record.rank,
        correction=record.correction,
        infinite=math.isinf(record.correction),
    )
