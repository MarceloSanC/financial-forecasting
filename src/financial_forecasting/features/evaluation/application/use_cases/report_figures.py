"""Montagem do dado plotado das figuras canônicas (Stage 8.3) — o módulo de montagem (A6).

Funções **puras** `*_figure(...) -> FigureAssembly`: cada uma lê a cópia julgada (gold e
scorecard) pelo mapa figura → fonte do D13 (concept 8.3 §7), por `col_*` + o
`GoldTableSchema`, e devolve a `FigureSpec` e as `SourceRef` que leu (o registro vem
delas, não de uma lista paralela). Nada de I/O, nada de biblioteca de desenho.

Regras comuns:

- **Nenhum teste novo** (I3): só seleção, reordenação e as transformações de exibição
  declaradas — complemento `1 - taxa` (e a banda com os limites trocados) para orientar o
  eixo de uma cauda superior, e a razão de contagens médias já persistidas. Este módulo
  não importa serviço inferencial do domínio (guarda AST em
  `tests/architecture/test_stage_8_3_regression_guards.py`);
- **por horizonte** (I5): um painel por horizonte, nada mistura horizontes;
- **rótulo de estatuto por elemento** (P8-ROT): `confirmatório` só nas caudas do gate do
  candidato nos horizontes em que H1 passa (I4);
- **o filtro do gate** é o do dono (`scorecard_evidence._tail`): `sample = GATE_SAMPLE`,
  `includes_degenerate = False`, `dgt_offset = dgt_step = None`. Os dois literais não têm
  constante nomeada no dono; são declarados aqui e **amarrados em tempo de execução**: a
  entrada do `calibration_95` do candidato com esse filtro, nas caudas do gate, tem de ter
  o `mean_observed` do `verdict.horizons[h].h1` — senão `ReportSourceMismatchError`;
- linha esperada ausente, repetida ou documento fora da forma → `ReportSourceMismatchError`
  com as chaves, nunca valores.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_CONFORMAL_COVERAGE,
    GOLD_DIFFERENTIAL_ACF,
    GOLD_DM_RESULTS,
    GOLD_H3_IMPORTANCE,
    GOLD_H3_READING,
    GOLD_H3_SHARES,
    GOLD_H3_VSN,
    GOLD_LOSS_DIFFERENTIALS,
    GOLD_METRICS_BY_RUN,
    GoldTableSchema,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    SCORECARD_DOCUMENT,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldPartition,
    col,
    col_bool_or_none,
    col_float,
    col_float_or_none,
    col_int,
    col_int_or_none,
    col_str,
    col_str_or_none,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    EMPIRICAL_COVERAGE_NOTE,
    FIGURE_CATALOG,
    ElementLabel,
    FigureSpec,
    FilterValue,
    PanelScope,
    PanelSpec,
    ReportSourceMismatchError,
    SeriesKind,
    SeriesSpec,
    SourceKind,
    SourceRef,
    StatusLabel,
    fan_chart_seed_note,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    REALIZED_TABLE,
    UNIT_KEY_SEPARATOR,
)
from financial_forecasting.features.evaluation.application.use_cases.report_silver import (
    FACT_TABLE,
    VerifiedSilver,
)
from financial_forecasting.features.evaluation.application.use_cases.silver_content_accumulator import (  # noqa: E501
    DIM_RUN_TABLE,
)
from financial_forecasting.features.evaluation.domain.services.coverage_metrics import (
    CoverageMetrics,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_real_number,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.family_loss_differentials import (  # noqa: E501
    H3_HORIZONS,
    H3_METHODS,
    PERMUTATION,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.evaluation.domain.value_objects.scorecard_evidence import (
    GATE_SAMPLE,
)

Row = Mapping[str, object]
Seed = int | None

COMMON_SAMPLE: Final = "common"
GATE_INCLUDES_DEGENERATE: Final = False
GATE_DGT_OFFSET: Final = None
GATE_DGT_STEP: Final = None
LOWER_TAIL: Final = "lower_tail"
UPPER_TAIL: Final = "upper_tail"
PAIR_KIND: Final = "pair"
MEDIAN_LEVEL: Final = 0.5

_CONFIRMATORY = ElementLabel(status=StatusLabel.CONFIRMATORY)
_PROFILE = ElementLabel(status=StatusLabel.DESCRIPTIVE_PROFILE)
_DESCRIPTIVE = ElementLabel(status=StatusLabel.DESCRIPTIVE)


# --------------------------------------------------------------------------------------
# Entradas e saída
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ReportInputs:
    """O que as figuras leem: o plano julgado, a ref, a partição, a cópia e o scorecard.

    Raises:
        ValueError: campo de tipo errado.
    """

    plan: Preregistration
    preregistration_ref: str
    partition: GoldPartition
    generation: GoldGeneration
    scorecard: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, Preregistration):
            raise ValueError("plan must be a Preregistration")
        if not isinstance(self.generation, GoldGeneration):
            raise ValueError("generation must be a GoldGeneration")
        if not isinstance(self.scorecard, Mapping):
            raise ValueError("scorecard must be a Mapping")

    def seeds(self, model: str) -> tuple[Seed, ...]:
        """As seeds do modelo na revisão julgada (`(None,)` num modelo sem seed)."""
        spec = self.plan.seeds[model]
        return (None,) if spec.seeds is None else tuple(spec.seeds)


@dataclass(frozen=True, kw_only=True)
class FigureAssembly:
    """Uma figura montada: a spec, as fontes lidas e o que vai só ao registro.

    `silver_units` (fan chart e sharpness) e `excluded_degenerate` (sharpness) ficam vazios
    nas figuras do gold.
    """

    spec: FigureSpec
    sources: tuple[SourceRef, ...]
    silver_units: Mapping[str, str] = field(default_factory=dict)
    excluded_degenerate: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "silver_units", MappingProxyType(dict(self.silver_units)))
        object.__setattr__(
            self, "excluded_degenerate", MappingProxyType(dict(self.excluded_degenerate))
        )


# --------------------------------------------------------------------------------------
# Leitura (gold e scorecard)
# --------------------------------------------------------------------------------------


def _rows(inputs: ReportInputs, schema: GoldTableSchema, **where: object) -> list[Row]:
    """As linhas da tabela cujas colunas (do schema) igualam `where` (tipo incluído)."""

    def matches(row: Row) -> bool:
        for column, wanted in where.items():
            value = col(row, schema, column)
            if value != wanted or (type(value) is bool and type(wanted) is not bool):
                return False
        return True

    return [row for row in inputs.generation.table(schema).rows if matches(row)]


def _one(inputs: ReportInputs, schema: GoldTableSchema, **where: object) -> Row:
    """A única linha com a chave `where`; zero ou mais de uma → `ReportSourceMismatchError`."""
    found = _rows(inputs, schema, **where)
    if len(found) != 1:
        raise ReportSourceMismatchError(
            f"{schema.name}: expected one row for {sorted(where)} at "
            f"{_key_text(where)}, found {len(found)}"
        )
    return found[0]


def _key_text(where: Mapping[str, object]) -> str:
    keys = ("model", "seed", "horizon", "sample", "kind", "variant", "comparator", "metric")
    return ", ".join(f"{k}={where[k]}" for k in keys if k in where)


def _get(mapping: object, *path: str | int) -> object:
    """Acesso por chave ao documento; fora da forma → `ReportSourceMismatchError`."""
    current = mapping
    try:
        for step in path:
            current = current[step]  # type: ignore[index]
    except (KeyError, IndexError, TypeError) as error:
        raise ReportSourceMismatchError(
            f"{SCORECARD_DOCUMENT} lacks {'.'.join(map(str, path))}"
        ) from error
    return current


def _number(value: object, *, where: str) -> float:
    if not is_real_number(value):
        raise ReportSourceMismatchError(f"{SCORECARD_DOCUMENT}: {where} is not a number")
    return float(value)


def _number_or_none(value: object, *, where: str) -> float | None:
    return None if value is None else _number(value, where=where)


def _entries(value: object, *, where: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ReportSourceMismatchError(f"{SCORECARD_DOCUMENT}: {where} is not a list of objects")
    return list(value)


def horizon_entry(scorecard: Mapping[str, object], part: str, horizon: int) -> Mapping[str, object]:
    """A entrada `part.horizons` com `horizon == h` (o "[h]" do concept)."""
    entries = _entries(_get(scorecard, part, "horizons"), where=f"{part}.horizons")
    found = [entry for entry in entries if entry.get("horizon") == horizon]
    if len(found) != 1:
        raise ReportSourceMismatchError(
            f"{SCORECARD_DOCUMENT}: {part}.horizons has {len(found)} entries for horizon {horizon}"
        )
    return found[0]


def _profile_entry(
    profile: Mapping[str, object], section: str, **where: object
) -> Mapping[str, object]:
    entries = _entries(_get(profile, section), where=f"profile.horizons[].{section}")
    found = [e for e in entries if all(e.get(k) == v for k, v in where.items())]
    if len(found) != 1:
        raise ReportSourceMismatchError(
            f"{SCORECARD_DOCUMENT}: profile {section} has {len(found)} entries for "
            f"{_key_text(where) or sorted(where)}"
        )
    return found[0]


# --------------------------------------------------------------------------------------
# Transformações de exibição (I3) e rótulos
# --------------------------------------------------------------------------------------


def tail_kind(level: float) -> str:
    """A cauda de um nível: inferior abaixo da mediana, superior acima."""
    return LOWER_TAIL if level < MEDIAN_LEVEL else UPPER_TAIL


def _orient(kind: str, rate: float | None) -> float | None:
    """ĉ(τ) de uma taxa de violação: a própria (inferior) ou `1 - taxa` (superior)."""
    if rate is None:
        return None
    return rate if kind == LOWER_TAIL else 1.0 - rate


def _orient_band(
    kind: str, low: float | None, high: float | None
) -> tuple[float | None, float | None]:
    """A banda da taxa orientada como ĉ: superior → `(1 - high, 1 - low)`."""
    if kind == LOWER_TAIL:
        return low, high
    return (None if high is None else 1.0 - high), (None if low is None else 1.0 - low)


def _ratio(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def level_text(level: float) -> str:
    """Nível em PT (vírgula decimal)."""
    return f"{level:g}".replace(".", ",")


def pair_text(pair: tuple[float, float]) -> str:
    return f"{level_text(pair[0])}-{level_text(pair[1])}"


def _seed_text(seed: Seed) -> str:
    return "sem seed" if seed is None else f"seed {seed}"


def symmetric_pairs(levels: Sequence[float]) -> tuple[tuple[float, float], ...]:
    """Pares `(levels[k], levels[K-1-k])` com τ_l < 0,5 — a regra da `CoverageSeries`."""
    size = len(levels)
    return tuple((levels[k], levels[size - 1 - k]) for k in range(size) if levels[k] < MEDIAN_LEVEL)


def _panel(  # noqa: PLR0913 — o painel e os seus rótulos
    inputs: ReportInputs,
    horizon: int,
    series: list[SeriesSpec],
    *,
    x_label: str,
    y_label: str,
    suffix: str = "",
    label: ElementLabel = _PROFILE,
) -> PanelSpec:
    return PanelSpec(
        panel_id=f"h{horizon}{suffix}",
        scope=PanelScope.HORIZON,
        horizon=horizon,
        title=f"h+{horizon}{(' — ' + suffix.strip('_').replace('_', ' ')) if suffix else ''}",
        x_label=x_label,
        y_label=y_label,
        series=tuple(series),
        label=label,
    )


def _spec(figure_id: str, panels: list[PanelSpec], notes: tuple[str, ...] = ()) -> FigureSpec:
    entry = FIGURE_CATALOG[figure_id]
    return FigureSpec(
        figure_id=figure_id,
        title=entry.title,
        panels=tuple(panels),
        notes=notes,
        omissions=entry.omissions,
    )


def _gold(name: str, fields: tuple[str, ...], **where: FilterValue) -> SourceRef:
    return SourceRef(kind=SourceKind.GOLD_TABLE, name=name, filter=where, fields=fields)


def _document(path: str, fields: tuple[str, ...], **where: FilterValue) -> SourceRef:
    return SourceRef(
        kind=SourceKind.DOCUMENT,
        name=SCORECARD_DOCUMENT,
        filter={"path": path, **where},
        fields=fields,
    )


def _levels_without_median(inputs: ReportInputs) -> tuple[float, ...]:
    return tuple(level for level in inputs.plan.quantile_levels if level != MEDIAN_LEVEL)


# --------------------------------------------------------------------------------------
# Reliability diagram por τ
# --------------------------------------------------------------------------------------

RELIABILITY_NOTE: Final = FIGURE_CATALOG["reliability_diagram"].required_notes[0]


def _gate_key(inputs: ReportInputs, model: str, kind: str, level: float) -> dict[str, object]:
    return {
        "model": model,
        "sample": GATE_SAMPLE,
        "kind": kind,
        "level_low": level,
        "level_high": None,
        "includes_degenerate": GATE_INCLUDES_DEGENERATE,
        "dgt_offset": GATE_DGT_OFFSET,
        "dgt_step": GATE_DGT_STEP,
    }


def _power_note(profile: Mapping[str, object], band_level: float) -> str:
    scenarios = _entries(_get(profile, "power"), where="profile.horizons[].power")
    parts = [
        f"{_get(s, 'label')} ({_get(s, 'role')}): P(reprovar) = "
        f"{_number(_get(s, 'failure_probability'), where='power.failure_probability'):.3f}"
        for s in scenarios
    ]
    return f"banda {level_text(band_level)} do gate; poder declarado — " + "; ".join(parts)


def _bind_gate_filter(inputs: ReportInputs, horizon: int, h1: object, profile: object) -> None:
    """O filtro do gate declarado aqui é o do dono: `mean_observed` igual ao do H1."""
    observed = _number(_get(h1, "mean_observed"), where="h1.mean_observed")
    gate = inputs.plan.h1_gate
    for kind, level in ((LOWER_TAIL, gate.lower_level), (UPPER_TAIL, gate.upper_level)):
        entry = _profile_entry(
            profile,  # type: ignore[arg-type]
            "calibration_95",
            **_gate_key(inputs, inputs.plan.candidate, kind, level),
        )
        if _number(entry.get("mean_observed"), where="calibration_95.mean_observed") != observed:
            raise ReportSourceMismatchError(
                f"the gate filter of horizon {horizon} {kind} does not reproduce "
                "verdict.h1.mean_observed (calibration_95 of the candidate)"
            )


def _confirmatory_tails(
    inputs: ReportInputs, horizon: int, h1: object, profile: object
) -> list[SeriesSpec]:
    passed = _get(h1, "passed") is True
    gate = inputs.plan.h1_gate
    series: list[SeriesSpec] = []
    for kind, level, band_name in (
        (LOWER_TAIL, gate.lower_level, "lower_band"),
        (UPPER_TAIL, gate.upper_level, "upper_band"),
    ):
        band = _get(h1, band_name)
        where = f"h1.{band_name}"
        estimate = _number_or_none(_get(band, "estimate"), where=where)
        low, high = _orient_band(
            kind,
            _number_or_none(_get(band, "lower"), where=where),
            _number_or_none(_get(band, "upper"), where=where),
        )
        band_level = _number(_get(band, "band_level"), where=where)
        status = StatusLabel.CONFIRMATORY if passed else StatusLabel.DESCRIPTIVE_PROFILE
        series.append(
            SeriesSpec(
                series_id=f"gate_{kind}",
                kind=SeriesKind.INTERVAL,
                name=f"candidato, cauda do gate τ = {level_text(level)}",
                model=inputs.plan.candidate,
                label=ElementLabel(status=status, note=_power_note(profile, band_level)),  # type: ignore[arg-type]
                x=(level,),
                y=(_orient(kind, estimate),),
                low=(low,),
                high=(high,),
            )
        )
    return series


def _candidate_profile_points(inputs: ReportInputs, profile: object) -> SeriesSpec:
    levels = _levels_without_median(inputs)
    values: list[float | None] = []
    for level in levels:
        kind = tail_kind(level)
        entry = _profile_entry(
            profile,  # type: ignore[arg-type]
            "calibration_95",
            **_gate_key(inputs, inputs.plan.candidate, kind, level),
        )
        ratio = _ratio(
            _number(entry.get("mean_violations"), where="calibration_95.mean_violations"),
            _number(entry.get("mean_observed"), where="calibration_95.mean_observed"),
        )
        values.append(_orient(kind, ratio))
    return SeriesSpec(
        series_id="candidate_seed_mean",
        kind=SeriesKind.POINTS,
        name="candidato, média entre seeds (contagens médias)",
        model=inputs.plan.candidate,
        label=_PROFILE,
        x=levels,
        y=tuple(values),
    )


def _candidate_seed_points(inputs: ReportInputs, horizon: int) -> SeriesSpec:
    band = inputs.plan.h1_gate.profile_band_level
    xs: list[float] = []
    ys: list[float | None] = []
    texts: list[str] = []
    for seed in inputs.seeds(inputs.plan.candidate):
        for level in _levels_without_median(inputs):
            kind = tail_kind(level)
            row = _one(
                inputs,
                GOLD_CALIBRATION_TABLE,
                seed=seed,
                horizon=horizon,
                band_level=band,
                **_gate_key(inputs, inputs.plan.candidate, kind, level),
            )
            xs.append(level)
            ys.append(
                _orient(kind, col_float_or_none(row, GOLD_CALIBRATION_TABLE, "violation_rate"))
            )
            texts.append(_seed_text(seed))
    return SeriesSpec(
        series_id="candidate_per_seed",
        kind=SeriesKind.POINTS,
        name="candidato, por seed",
        model=inputs.plan.candidate,
        label=_PROFILE,
        x=tuple(xs),
        y=tuple(ys),
        text=tuple(texts),
    )


def _comparator_bands(inputs: ReportInputs, horizon: int) -> list[SeriesSpec]:
    schema = GOLD_CALIBRATION_TABLE
    band = inputs.plan.h1_gate.profile_band_level
    levels = _levels_without_median(inputs)
    series: list[SeriesSpec] = []
    for model in inputs.plan.comparators:
        for seed in inputs.seeds(model):
            ys: list[float | None] = []
            lows: list[float | None] = []
            highs: list[float | None] = []
            for level in levels:
                kind = tail_kind(level)
                row = _one(
                    inputs,
                    schema,
                    seed=seed,
                    horizon=horizon,
                    band_level=band,
                    **_gate_key(inputs, model, kind, level),
                )
                low, high = _orient_band(
                    kind,
                    col_float_or_none(row, schema, "wilson_lower"),
                    col_float_or_none(row, schema, "wilson_upper"),
                )
                ys.append(_orient(kind, col_float_or_none(row, schema, "wilson_estimate")))
                lows.append(low)
                highs.append(high)
            series.append(
                SeriesSpec(
                    series_id=f"{model}|{seed}",
                    kind=SeriesKind.INTERVAL,
                    name=f"{model} ({_seed_text(seed)}), Wilson {level_text(band)}",
                    model=model,
                    label=_PROFILE,
                    x=levels,
                    y=tuple(ys),
                    low=tuple(lows),
                    high=tuple(highs),
                )
            )
    return series


def _diagonal() -> SeriesSpec:
    return SeriesSpec(
        series_id="diagonal",
        kind=SeriesKind.REFERENCE,
        name="calibração perfeita (ĉ = τ)",
        label=_DESCRIPTIVE,
        x=(0.0, 1.0),
        y=(0.0, 1.0),
    )


def reliability_figure(inputs: ReportInputs) -> FigureAssembly:
    """{(τ, ĉ(τ))} por modelo e horizonte (doc §6.2; D13 linha 1)."""
    panels: list[PanelSpec] = []
    for horizon in inputs.plan.horizons:
        h1 = _get(horizon_entry(inputs.scorecard, "verdict", horizon), "h1")
        profile = horizon_entry(inputs.scorecard, "profile", horizon)
        _bind_gate_filter(inputs, horizon, h1, profile)
        series = [
            *_confirmatory_tails(inputs, horizon, h1, profile),
            _candidate_profile_points(inputs, profile),
            _candidate_seed_points(inputs, horizon),
            *_comparator_bands(inputs, horizon),
            _diagonal(),
        ]
        panels.append(_panel(inputs, horizon, series, x_label="τ", y_label="ĉ(τ)"))
    band = inputs.plan.h1_gate.profile_band_level
    gate_filter: dict[str, FilterValue] = {
        "sample": GATE_SAMPLE,
        "includes_degenerate": GATE_INCLUDES_DEGENERATE,
        "dgt_offset": GATE_DGT_OFFSET,
        "dgt_step": GATE_DGT_STEP,
        "level_high": None,
    }
    sources = (
        _document(
            "verdict.horizons[].h1",
            ("lower_band", "upper_band", "passed", "mean_observed"),
        ),
        _document("profile.horizons[].power", ("label", "role", "failure_probability")),
        _document(
            "profile.horizons[].calibration_95",
            ("mean_violations", "mean_observed"),
            model=inputs.plan.candidate,
            **gate_filter,
        ),
        _gold(
            GOLD_CALIBRATION_TABLE.name,
            ("violation_rate",),
            model=inputs.plan.candidate,
            band_level=band,
            **gate_filter,
        ),
        _gold(
            GOLD_CALIBRATION_TABLE.name,
            ("wilson_estimate", "wilson_lower", "wilson_upper"),
            models="comparators",
            band_level=band,
            **gate_filter,
        ),
    )
    return FigureAssembly(
        spec=_spec("reliability_diagram", panels, (RELIABILITY_NOTE,)), sources=sources
    )


# --------------------------------------------------------------------------------------
# Quantile score plot
# --------------------------------------------------------------------------------------


def _descriptor(profile: Mapping[str, object], **where: object) -> tuple[float, float, float]:
    entry = _profile_entry(profile, "descriptors", **where)
    return (
        _number(entry.get("mean"), where="descriptors.mean"),
        _number(entry.get("minimum"), where="descriptors.minimum"),
        _number(entry.get("maximum"), where="descriptors.maximum"),
    )


def _metric(  # noqa: PLR0913 — a chave de uma linha de gold_metrics_by_run
    inputs: ReportInputs,
    *,
    model: str,
    seed: Seed,
    horizon: int,
    sample: str,
    metric: str,
    level_low: float,
    level_high: float | None,
) -> float | None:
    row = _one(
        inputs,
        GOLD_METRICS_BY_RUN,
        model=model,
        seed=seed,
        horizon=horizon,
        sample=sample,
        metric=metric,
        level_low=level_low,
        level_high=level_high,
    )
    return col_float_or_none(row, GOLD_METRICS_BY_RUN, "value")


def quantile_score_figure(inputs: ReportInputs) -> FigureAssembly:
    """P̄_τ x τ por modelo e horizonte (doc §6.2; D13 linha 2)."""
    levels = tuple(inputs.plan.quantile_levels)
    candidate = inputs.plan.candidate
    panels: list[PanelSpec] = []
    for horizon in inputs.plan.horizons:
        profile = horizon_entry(inputs.scorecard, "profile", horizon)
        series: list[SeriesSpec] = []
        for model in inputs.plan.models:
            for seed in inputs.seeds(model):
                values = tuple(
                    _metric(
                        inputs,
                        model=model,
                        seed=seed,
                        horizon=horizon,
                        sample=COMMON_SAMPLE,
                        metric="pinball",
                        level_low=level,
                        level_high=None,
                    )
                    for level in levels
                )
                series.append(
                    SeriesSpec(
                        series_id=f"{model}|{seed}",
                        kind=SeriesKind.POINTS if model == candidate else SeriesKind.LINE,
                        name=f"{model} ({_seed_text(seed)})",
                        model=model,
                        label=_PROFILE,
                        x=levels,
                        y=values,
                    )
                )
        stats = [
            _descriptor(
                profile,
                model=candidate,
                sample=COMMON_SAMPLE,
                metric="pinball",
                level_low=level,
                level_high=None,
            )
            for level in levels
        ]
        series.append(
            SeriesSpec(
                series_id="candidate_seed_mean",
                kind=SeriesKind.LINE,
                name="candidato, média entre seeds (mín-máx)",
                model=candidate,
                label=_PROFILE,
                x=levels,
                y=tuple(s[0] for s in stats),
                low=tuple(s[1] for s in stats),
                high=tuple(s[2] for s in stats),
            )
        )
        panels.append(_panel(inputs, horizon, series, x_label="τ", y_label="P̄_τ (pinball)"))
    sources = (
        _gold(
            GOLD_METRICS_BY_RUN.name,
            ("value",),
            sample=COMMON_SAMPLE,
            metric="pinball",
            level_high=None,
        ),
        _document(
            "profile.horizons[].descriptors",
            ("mean", "minimum", "maximum"),
            model=candidate,
            sample=COMMON_SAMPLE,
            metric="pinball",
        ),
    )
    return FigureAssembly(spec=_spec("quantile_score_plot", panels), sources=sources)


# --------------------------------------------------------------------------------------
# PICP x MPIW
# --------------------------------------------------------------------------------------

PICP_MPIW_NOTE: Final = FIGURE_CATALOG["picp_mpiw_plot"].required_notes[0]


def picp_mpiw_figure(inputs: ReportInputs) -> FigureAssembly:
    """Um ponto por (modelo, par, seed) e horizonte; nominal 1 - 2τ_l (D13 linha 4)."""
    pairs = symmetric_pairs(inputs.plan.quantile_levels)
    candidate = inputs.plan.candidate
    panels: list[PanelSpec] = []
    for horizon in inputs.plan.horizons:
        profile = horizon_entry(inputs.scorecard, "profile", horizon)
        series: list[SeriesSpec] = []
        for model in inputs.plan.models:
            xs: list[float | None] = []
            ys: list[float | None] = []
            texts: list[str] = []
            for seed in inputs.seeds(model):
                for low, high in pairs:
                    key = {
                        "model": model,
                        "seed": seed,
                        "horizon": horizon,
                        "sample": COMMON_SAMPLE,
                        "level_low": low,
                        "level_high": high,
                    }
                    xs.append(_metric(inputs, metric="mpiw", **key))  # type: ignore[arg-type]
                    ys.append(_metric(inputs, metric="picp", **key))  # type: ignore[arg-type]
                    texts.append(f"{pair_text((low, high))}, {_seed_text(seed)}")
            series.append(_xy_series(model, xs, ys, texts))
        for low, high in pairs:
            picp = _descriptor(
                profile,
                model=candidate,
                sample=COMMON_SAMPLE,
                metric="picp",
                level_low=low,
                level_high=high,
            )
            mpiw = _descriptor(
                profile,
                model=candidate,
                sample=COMMON_SAMPLE,
                metric="mpiw",
                level_low=low,
                level_high=high,
            )
            series.append(
                SeriesSpec(
                    series_id=f"candidate_seed_mean|{pair_text((low, high))}",
                    kind=SeriesKind.POINTS,
                    name=f"candidato, média entre seeds, par {pair_text((low, high))}",
                    model=candidate,
                    label=_PROFILE,
                    x=(mpiw[0],),
                    y=(picp[0],),
                    low=(picp[1],),
                    high=(picp[2],),
                )
            )
            series.append(
                SeriesSpec(
                    series_id=f"nominal|{pair_text((low, high))}",
                    kind=SeriesKind.REFERENCE,
                    name=f"nominal 1 - 2τ_l, par {pair_text((low, high))}",
                    label=_DESCRIPTIVE,
                    x=(0.0,),
                    y=(1.0 - 2.0 * low,),
                )
            )
        panels.append(_panel(inputs, horizon, series, x_label="MPIW", y_label="PICP"))
    sources = (
        _gold(
            GOLD_METRICS_BY_RUN.name,
            ("value",),
            sample=COMMON_SAMPLE,
            metric="picp|mpiw",
        ),
        _document(
            "profile.horizons[].descriptors",
            ("mean", "minimum", "maximum"),
            model=candidate,
            sample=COMMON_SAMPLE,
            metric="picp|mpiw",
        ),
    )
    return FigureAssembly(spec=_spec("picp_mpiw_plot", panels, (PICP_MPIW_NOTE,)), sources=sources)


def _xy_series(
    model: str, xs: list[float | None], ys: list[float | None], texts: list[str]
) -> SeriesSpec:
    """Pontos (MPIW, PICP); um ponto sem MPIW finito fica sem x — a série recusa `None` em x."""
    kept = [(x, y, t) for x, y, t in zip(xs, ys, texts, strict=True) if x is not None]
    return SeriesSpec(
        series_id=model,
        kind=SeriesKind.POINTS,
        name=f"{model} (por par e seed)",
        model=model,
        label=_PROFILE,
        x=tuple(x for x, _, _ in kept),
        y=tuple(y for _, y, _ in kept),
        text=tuple(t for _, _, t in kept),
    )


# --------------------------------------------------------------------------------------
# Nativo x conformal
# --------------------------------------------------------------------------------------

_EMPIRICAL = ElementLabel(status=StatusLabel.DESCRIPTIVE, note=EMPIRICAL_COVERAGE_NOTE)


def _conformal_row(  # noqa: PLR0913 — a chave de uma linha de gold_conformal_coverage
    inputs: ReportInputs,
    *,
    horizon: int,
    variant: str,
    kind: str,
    pair: tuple[float, float],
    seed: Seed,
    band_level: float | None,
) -> Row:
    return _one(
        inputs,
        GOLD_CONFORMAL_COVERAGE,
        horizon=horizon,
        variant=variant,
        kind=kind,
        lower_level=pair[0],
        upper_level=pair[1],
        seed=seed,
        band_level=band_level,
    )


def _native_calibration(
    inputs: ReportInputs, *, horizon: int, seed: Seed, kind: str, level: float
) -> Row:
    return _one(
        inputs,
        GOLD_CALIBRATION_TABLE,
        model=inputs.plan.candidate,
        seed=seed,
        horizon=horizon,
        sample=GATE_SAMPLE,
        kind=kind,
        level_low=level,
        level_high=None,
        includes_degenerate=False,
        dgt_offset=None,
        dgt_step=None,
        band_level=inputs.plan.h1_gate.profile_band_level,
    )


@dataclass
class _Points:
    """Acumulador de uma série categórica (x, y, low, high, text)."""

    x: list[str] = field(default_factory=list)
    y: list[float | None] = field(default_factory=list)
    low: list[float | None] = field(default_factory=list)
    high: list[float | None] = field(default_factory=list)
    text: list[str] = field(default_factory=list)

    def add(
        self,
        x: str,
        y: float | None,
        band: tuple[float | None, float | None] = (None, None),
        text: str = "",
    ) -> None:
        self.x.append(x)
        self.y.append(y)
        self.low.append(band[0])
        self.high.append(band[1])
        self.text.append(text or x)

    def series(  # noqa: PLR0913 — os campos da série
        self,
        series_id: str,
        name: str,
        *,
        model: str | None,
        label: ElementLabel,
        kind: SeriesKind = SeriesKind.POINTS,
        with_band: bool = False,
    ) -> SeriesSpec:
        return SeriesSpec(
            series_id=series_id,
            kind=kind,
            name=name,
            model=model,
            label=label,
            x=tuple(self.x),
            y=tuple(self.y),
            low=tuple(self.low) if with_band else None,
            high=tuple(self.high) if with_band else None,
            text=tuple(self.text),
        )


def _conformal_variants(inputs: ReportInputs, horizon: int) -> list[str]:
    band = inputs.plan.h1_gate.profile_band_level
    rows = _rows(inputs, GOLD_CONFORMAL_COVERAGE, horizon=horizon, seed=None, band_level=band)
    variants = sorted(
        {v for r in rows if (v := col_str_or_none(r, GOLD_CONFORMAL_COVERAGE, "variant"))}
    )
    if not variants:
        raise ReportSourceMismatchError(
            f"gold_conformal_coverage has no rows for horizon {horizon}"
        )
    return variants


def _check_same_mask(conformal: Row, native: Row, *, where: str) -> None:
    evaluated = col_int_or_none(conformal, GOLD_CONFORMAL_COVERAGE, "n_evaluated")
    observed = col_int_or_none(native, GOLD_CALIBRATION_TABLE, "n_observed")
    if evaluated != observed:
        raise ReportSourceMismatchError(
            f"conformal n_evaluated differs from the native n_observed at {where} "
            "(not the same mask)"
        )


def _conformal_series(
    inputs: ReportInputs,
    horizon: int,
    variant: str,
    pairs: Sequence[tuple[float, float]],
    *,
    quantity: str,
) -> list[SeriesSpec]:
    schema = GOLD_CONFORMAL_COVERAGE
    band = inputs.plan.h1_gate.profile_band_level
    mean, per_seed = _Points(), _Points()
    note = EMPIRICAL_COVERAGE_NOTE
    for pair in pairs:
        if quantity == "coverage":
            for kind, level in ((LOWER_TAIL, pair[0]), (UPPER_TAIL, pair[1])):
                x = f"cauda {level_text(level)}"
                row = _conformal_row(
                    inputs,
                    horizon=horizon,
                    variant=variant,
                    kind=kind,
                    pair=pair,
                    seed=None,
                    band_level=band,
                )
                note = col_str_or_none(row, schema, "label") or note
                seed_mean = col_float_or_none(row, schema, "mean_of_seed_coverages")
                mean.add(
                    x,
                    col_float_or_none(row, schema, "coverage"),
                    (
                        col_float_or_none(row, schema, "wilson_lower"),
                        col_float_or_none(row, schema, "wilson_upper"),
                    ),
                    f"{x}; média das coberturas das seeds = {seed_mean}",
                )
                for seed in inputs.seeds(inputs.plan.candidate):
                    seed_row = _conformal_row(
                        inputs,
                        horizon=horizon,
                        variant=variant,
                        kind=kind,
                        pair=pair,
                        seed=seed,
                        band_level=band,
                    )
                    native = _native_calibration(
                        inputs, horizon=horizon, seed=seed, kind=kind, level=level
                    )
                    _check_same_mask(
                        seed_row,
                        native,
                        where=f"horizon={horizon}, variant={variant}, seed={seed}, kind={kind}",
                    )
                    per_seed.add(
                        x,
                        col_float_or_none(seed_row, schema, "coverage"),
                        text=f"{x}, {_seed_text(seed)}",
                    )
        column = "coverage" if quantity == "coverage" else "mpiw"
        x = f"PICP {pair_text(pair)}" if quantity == "coverage" else f"MPIW {pair_text(pair)}"
        row = _conformal_row(
            inputs,
            horizon=horizon,
            variant=variant,
            kind=PAIR_KIND,
            pair=pair,
            seed=None,
            band_level=None,
        )
        mean.add(x, col_float_or_none(row, schema, column))
        for seed in inputs.seeds(inputs.plan.candidate):
            seed_row = _conformal_row(
                inputs,
                horizon=horizon,
                variant=variant,
                kind=PAIR_KIND,
                pair=pair,
                seed=seed,
                band_level=None,
            )
            per_seed.add(
                x, col_float_or_none(seed_row, schema, column), text=f"{x}, {_seed_text(seed)}"
            )
    label = ElementLabel(status=StatusLabel.DESCRIPTIVE, note=note)
    return [
        mean.series(
            f"conformal|{variant}|seed_mean",
            f"conformal {variant}, média entre seeds (c̄/n̄)",
            model=None,
            label=label,
            kind=SeriesKind.INTERVAL,
            with_band=True,
        ),
        per_seed.series(
            f"conformal|{variant}|per_seed",
            f"conformal {variant}, por seed",
            model=None,
            label=label,
        ),
    ]


def _native_series(
    inputs: ReportInputs,
    horizon: int,
    profile: Mapping[str, object],
    pairs: Sequence[tuple[float, float]],
    *,
    quantity: str,
) -> list[SeriesSpec]:
    candidate = inputs.plan.candidate
    mean, per_seed = _Points(), _Points()
    for pair in pairs:
        if quantity == "coverage":
            for kind, level in ((LOWER_TAIL, pair[0]), (UPPER_TAIL, pair[1])):
                x = f"cauda {level_text(level)}"
                entry = _profile_entry(
                    profile,
                    "calibration_95",
                    **_gate_key(inputs, candidate, kind, level),
                )
                ratio = _ratio(
                    _number(entry.get("mean_violations"), where="calibration_95.mean_violations"),
                    _number(entry.get("mean_observed"), where="calibration_95.mean_observed"),
                )
                mean.add(x, _orient(kind, ratio))
                for seed in inputs.seeds(candidate):
                    row = _native_calibration(
                        inputs, horizon=horizon, seed=seed, kind=kind, level=level
                    )
                    schema = GOLD_CALIBRATION_TABLE
                    violations = col_int_or_none(row, schema, "n_violations")
                    observed = col_int_or_none(row, schema, "n_observed")
                    rate = (
                        None
                        if violations is None or not observed
                        else _ratio(float(violations), float(observed))
                    )
                    per_seed.add(
                        x,
                        _orient(kind, rate),
                        _orient_band(
                            kind,
                            col_float_or_none(row, schema, "wilson_lower"),
                            col_float_or_none(row, schema, "wilson_upper"),
                        ),
                        f"{x}, {_seed_text(seed)}",
                    )
        metric = "picp" if quantity == "coverage" else "mpiw"
        x = f"PICP {pair_text(pair)}" if quantity == "coverage" else f"MPIW {pair_text(pair)}"
        mean.add(
            x,
            _descriptor(
                profile,
                model=candidate,
                sample=GATE_SAMPLE,
                metric=metric,
                level_low=pair[0],
                level_high=pair[1],
            )[0],
        )
        for seed in inputs.seeds(candidate):
            per_seed.add(
                x,
                _metric(
                    inputs,
                    model=candidate,
                    seed=seed,
                    horizon=horizon,
                    sample=GATE_SAMPLE,
                    metric=metric,
                    level_low=pair[0],
                    level_high=pair[1],
                ),
                text=f"{x}, {_seed_text(seed)}",
            )
    return [
        mean.series(
            "native|seed_mean",
            "nativo (mesma máscara), média entre seeds",
            model=candidate,
            label=_EMPIRICAL,
        ),
        per_seed.series(
            "native|per_seed",
            "nativo (mesma máscara), por seed",
            model=candidate,
            label=_EMPIRICAL,
            kind=SeriesKind.INTERVAL if quantity == "coverage" else SeriesKind.POINTS,
            with_band=quantity == "coverage",
        ),
    ]


def _nominal(pairs: Sequence[tuple[float, float]]) -> SeriesSpec:
    nominal = _Points()
    for low, high in pairs:
        nominal.add(f"cauda {level_text(low)}", low)
        nominal.add(f"cauda {level_text(high)}", high)
        nominal.add(f"PICP {pair_text((low, high))}", high - low)
    return nominal.series(
        "nominal", "nominal", model=None, label=_EMPIRICAL, kind=SeriesKind.REFERENCE
    )


def native_vs_conformal_figure(inputs: ReportInputs) -> FigureAssembly:
    """ĉ por cauda, PICP e MPIW do nativo (mesma máscara) e do CQR (D13 última linha)."""
    conformal = inputs.plan.conformal
    if conformal is None:
        raise ReportSourceMismatchError("the judged revision has no [conformal] block")
    pairs = conformal.pairs
    panels: list[PanelSpec] = []
    for horizon in inputs.plan.horizons:
        profile = horizon_entry(inputs.scorecard, "profile", horizon)
        variants = _conformal_variants(inputs, horizon)
        for quantity, suffix, y_label in (
            ("coverage", "_cobertura", "ĉ(τ) / PICP"),
            ("width", "_largura", "MPIW"),
        ):
            series = [
                s
                for variant in variants
                for s in _conformal_series(inputs, horizon, variant, pairs, quantity=quantity)
            ]
            series += _native_series(inputs, horizon, profile, pairs, quantity=quantity)
            if quantity == "coverage":
                series.append(_nominal(pairs))
            panels.append(
                _panel(
                    inputs,
                    horizon,
                    series,
                    x_label="cauda / par",
                    y_label=y_label,
                    suffix=suffix,
                    label=_EMPIRICAL,
                )
            )
    band = inputs.plan.h1_gate.profile_band_level
    candidate = inputs.plan.candidate
    sources = (
        _gold(
            GOLD_CONFORMAL_COVERAGE.name,
            (
                "coverage",
                "mean_of_seed_coverages",
                "n_evaluated",
                "mpiw",
                "wilson_lower",
                "wilson_upper",
                "label",
            ),
            band_level=band,
        ),
        _gold(
            GOLD_CALIBRATION_TABLE.name,
            ("n_observed", "n_violations", "wilson_lower", "wilson_upper"),
            model=candidate,
            sample=GATE_SAMPLE,
            includes_degenerate=False,
            dgt_offset=None,
            band_level=band,
        ),
        _document(
            "profile.horizons[].calibration_95",
            ("mean_violations", "mean_observed"),
            model=candidate,
            sample=GATE_SAMPLE,
            includes_degenerate=False,
            dgt_offset=None,
        ),
        _gold(
            GOLD_METRICS_BY_RUN.name,
            ("value",),
            model=candidate,
            sample=GATE_SAMPLE,
            metric="picp|mpiw",
        ),
        _document(
            "profile.horizons[].descriptors",
            ("mean",),
            model=candidate,
            sample=GATE_SAMPLE,
            metric="picp|mpiw",
        ),
    )
    return FigureAssembly(
        spec=_spec("native_vs_conformal", panels, (EMPIRICAL_COVERAGE_NOTE,)), sources=sources
    )


# --------------------------------------------------------------------------------------
# DM: candidato x comparadores (I4; D2)
# --------------------------------------------------------------------------------------

_H2_NOT_APPLICABLE = ElementLabel(status=StatusLabel.DESCRIPTIVE_PROFILE_H2_NOT_APPLICABLE)


def _holm_text(raw: float, adjusted: float, *, rejected: bool) -> str:
    decision = "rejeita" if rejected else "não rejeita"
    return f"p bruto = {raw:.3g}; Holm {decision} (p ajustado = {adjusted:.3g})"


def dm_figure(inputs: ReportInputs) -> FigureAssembly:
    """Por horizonte, uma célula por comparador da família: p bruto e decisão de Holm.

    Linha `variance_estimator = primário (retangular)`; `adjusted_p_value`/`rejected`
    conferidos contra `profile.horizons[h].dm` (estimador primário). Confirmatório só onde
    `verdict.horizons[h].h1.passed`; senão "descritivo (perfil) — H2 não aplicável".

    Raises:
        ReportSourceMismatchError: linha ausente, entrada do scorecard ausente ou divergente.
    """
    schema = GOLD_DM_RESULTS
    estimator = inputs.plan.dm.primary_estimator.value
    candidate = inputs.plan.candidate
    panels: list[PanelSpec] = []
    for horizon in inputs.plan.horizons:
        passed = _get(horizon_entry(inputs.scorecard, "verdict", horizon), "h1", "passed") is True
        profile = horizon_entry(inputs.scorecard, "profile", horizon)
        label = _CONFIRMATORY if passed else _H2_NOT_APPLICABLE
        raws: list[float | None] = []
        texts: list[str] = []
        for comparator in inputs.plan.comparators:
            row = _one(
                inputs,
                schema,
                horizon=horizon,
                variance_estimator=estimator,
                candidate=candidate,
                comparator=comparator,
            )
            raw = col_float(row, schema, "p_value")
            adjusted = col_float(row, schema, "adjusted_p_value")
            rejected = col_bool_or_none(row, schema, "rejected") is True
            entry = _profile_entry(profile, "dm", comparator=comparator, estimator=estimator)
            if (
                _number(entry.get("adjusted_p_value"), where="dm.adjusted_p_value") != adjusted
                or entry.get("rejected") is not rejected
            ):
                raise ReportSourceMismatchError(
                    f"gold_dm_results differs from the scorecard profile dm at horizon "
                    f"{horizon}, comparator {comparator}, estimator {estimator}"
                )
            raws.append(raw)
            texts.append(_holm_text(raw, adjusted, rejected=rejected))
        cells = SeriesSpec(
            series_id="dm_cells",
            kind=SeriesKind.CELLS,
            name=f"DM unilateral (candidato com perda menor), estimador {estimator}",
            model=candidate,
            label=label,
            x=inputs.plan.comparators,
            y=tuple(raws),
            text=tuple(texts),
        )
        panels.append(
            _panel(
                inputs,
                horizon,
                [cells],
                x_label="comparador",
                y_label="p bruto",
                label=label,
            )
        )
    sources = (
        _gold(
            schema.name,
            ("p_value", "adjusted_p_value", "rejected"),
            variance_estimator=estimator,
            candidate=candidate,
        ),
        _document("profile.horizons[].dm", ("adjusted_p_value", "rejected"), estimator=estimator),
        _document("verdict.horizons[].h1", ("passed",)),
    )
    return FigureAssembly(spec=_spec("dm_candidate_vs_comparators", panels), sources=sources)


# --------------------------------------------------------------------------------------
# Diferencial de perda d_t e ACF (D14)
# --------------------------------------------------------------------------------------


def _pair_rows(
    inputs: ReportInputs, schema: GoldTableSchema, horizon: int, comparator: str
) -> tuple[list[Row], bool]:
    """As linhas do par (candidato, comparador) e se o candidato é `model_b` (sinal)."""
    candidate = inputs.plan.candidate
    forward = _rows(inputs, schema, horizon=horizon, model_a=candidate, model_b=comparator)
    backward = _rows(inputs, schema, horizon=horizon, model_a=comparator, model_b=candidate)
    if bool(forward) == bool(backward):
        raise ReportSourceMismatchError(
            f"{schema.name}: expected the pair (candidate, {comparator}) once at horizon "
            f"{horizon}, found {len(forward)} forward and {len(backward)} backward rows"
        )
    return (forward, False) if forward else (backward, True)


def _fold_cuts(timestamps: Sequence[str], folds: Sequence[str | None]) -> list[str]:
    return [timestamps[i] for i in range(1, len(timestamps)) if folds[i] != folds[i - 1]]


def loss_differential_figure(inputs: ReportInputs) -> FigureAssembly:
    """d_t = L_candidato - L_comparador ao longo do tempo e a ACF persistida (D14).

    O gold guarda d_t = L_a - L_b do par em ordem; com o candidato em `model_b` o sinal é
    trocado (orientação do eixo, I3). A faixa de confiança da ACF não é persistida e fica
    fora (omissão declarada).
    """
    loss, acf = GOLD_LOSS_DIFFERENTIALS, GOLD_DIFFERENTIAL_ACF
    panels: list[PanelSpec] = []
    for horizon in inputs.plan.horizons:
        lines: list[SeriesSpec] = []
        stems: list[SeriesSpec] = []
        cuts: set[str] = set()
        for comparator in inputs.plan.comparators:
            rows, flipped = _pair_rows(inputs, loss, horizon, comparator)
            ordered = sorted(rows, key=lambda r: col_str(r, loss, "target_timestamp"))
            timestamps = [col_str(r, loss, "target_timestamp") for r in ordered]
            sign = -1.0 if flipped else 1.0
            lines.append(
                SeriesSpec(
                    series_id=f"d_t|{comparator}",
                    kind=SeriesKind.LINE,
                    name=f"d_t vs. {comparator}",
                    model=comparator,
                    label=_DESCRIPTIVE,
                    x=tuple(timestamps),
                    y=tuple(sign * col_float(r, loss, "differential") for r in ordered),
                )
            )
            folds = [col_str_or_none(r, loss, "fold") for r in ordered]
            cuts.update(_fold_cuts(timestamps, folds))
            acf_rows, _ = _pair_rows(inputs, acf, horizon, comparator)
            by_lag = sorted(acf_rows, key=lambda r: col_int(r, acf, "lag"))
            stems.append(
                SeriesSpec(
                    series_id=f"acf|{comparator}",
                    kind=SeriesKind.STEMS,
                    name=f"ACF de d_t vs. {comparator}",
                    model=comparator,
                    label=_DESCRIPTIVE,
                    x=tuple(float(col_int(r, acf, "lag")) for r in by_lag),
                    y=tuple(col_float_or_none(r, acf, "acf") for r in by_lag),
                )
            )
        if cuts:
            ordered_cuts = tuple(sorted(cuts))
            lines.append(
                SeriesSpec(
                    series_id="fold_cuts",
                    kind=SeriesKind.VLINES,
                    name="corte de fold",
                    label=_DESCRIPTIVE,
                    x=ordered_cuts,
                    y=tuple(None for _ in ordered_cuts),
                )
            )
        panels.append(
            _panel(
                inputs,
                horizon,
                lines,
                x_label="target_timestamp",
                y_label="d_t",
                suffix="_d_t",
                label=_DESCRIPTIVE,
            )
        )
        panels.append(
            _panel(
                inputs,
                horizon,
                stems,
                x_label="lag",
                y_label="ACF",
                suffix="_acf",
                label=_DESCRIPTIVE,
            )
        )
    sources = (
        _gold(loss.name, ("differential", "fold"), pairs="candidate x family comparator"),
        _gold(acf.name, ("acf",), pairs="candidate x family comparator"),
    )
    return FigureAssembly(spec=_spec("loss_differential_acf", panels), sources=sources)


# --------------------------------------------------------------------------------------
# Importância por família / H3
# --------------------------------------------------------------------------------------

H3_NOTE: Final = FIGURE_CATALOG["h3_family_importance"].required_notes[0]


def _importance(row: Row) -> float | None:
    return col_float_or_none(row, GOLD_H3_IMPORTANCE, "importance")


def _status_text(row: Row, schema: GoldTableSchema) -> str:
    status = col_str_or_none(row, schema, "status")
    reason = col_str_or_none(row, schema, "reason")
    return f"{status}; {reason}" if reason else str(status)


def _h3_horizon_series(
    inputs: ReportInputs, horizon: int, families: Sequence[str]
) -> list[SeriesSpec]:
    schema = GOLD_H3_IMPORTANCE
    series: list[SeriesSpec] = []
    for method in H3_METHODS:
        aggregate = [
            _one(
                inputs,
                schema,
                method=method,
                family=family,
                horizon=horizon,
                seed=None,
                permutation_index=None,
            )
            for family in families
        ]
        series.append(
            SeriesSpec(
                series_id=f"{method}|aggregate",
                kind=SeriesKind.BARS,
                name=f"I_f(h), {method}",
                label=_DESCRIPTIVE,
                x=tuple(families),
                y=tuple(_importance(r) for r in aggregate),
                text=tuple(_status_text(r, schema) for r in aggregate),
            )
        )
        per_seed: list[tuple[str, Row]] = []
        per_permutation: list[tuple[str, Row]] = []
        for family in families:
            for row in _rows(inputs, schema, method=method, family=family, horizon=horizon):
                seed = col_int_or_none(row, schema, "seed")
                index = col_int_or_none(row, schema, "permutation_index")
                if seed is not None and index is None:
                    per_seed.append((f"seed {seed}", row))
                elif seed is None and index is not None and method == PERMUTATION:
                    per_permutation.append((f"permutação {index}", row))
        for dimension, chosen in (("seed", per_seed), ("permutation", per_permutation)):
            if not chosen:
                continue
            series.append(
                SeriesSpec(
                    series_id=f"{method}|per_{dimension}",
                    kind=SeriesKind.POINTS,
                    name=f"perfil por {'seed' if dimension == 'seed' else 'permutação'}, {method}",
                    label=_DESCRIPTIVE,
                    x=tuple(col_str(r, schema, "family") for _, r in chosen),
                    y=tuple(_importance(r) for _, r in chosen),
                    text=tuple(text for text, _ in chosen),
                )
            )
    return series


def _h3_comparison_series(inputs: ReportInputs, families: Sequence[str]) -> list[SeriesSpec]:
    schema = GOLD_H3_SHARES
    series: list[SeriesSpec] = []
    for method in H3_METHODS:
        rows = [_one(inputs, schema, method=method, family=family) for family in families]
        series.append(
            SeriesSpec(
                series_id=f"{method}|delta",
                kind=SeriesKind.INTERVAL,
                name=f"Δ_f = s_f(h+7) - s_f(h+1), {method}",
                label=_DESCRIPTIVE,
                x=tuple(families),
                y=tuple(col_float_or_none(r, schema, "delta") for r in rows),
                low=tuple(col_float_or_none(r, schema, "lower") for r in rows),
                high=tuple(col_float_or_none(r, schema, "upper") for r in rows),
                text=tuple(str(col_str_or_none(r, schema, "status")) for r in rows),
            )
        )
        for column, horizon in (("share_h1", 1), ("share_h7", 7)):
            series.append(
                SeriesSpec(
                    series_id=f"{method}|{column}",
                    kind=SeriesKind.POINTS,
                    name=f"s_f(h+{horizon}), {method}",
                    label=_DESCRIPTIVE,
                    x=tuple(families),
                    y=tuple(col_float_or_none(r, schema, column) for r in rows),
                )
            )
    return series


def _reading_note(inputs: ReportInputs) -> str:
    schema = GOLD_H3_READING
    rows = inputs.generation.table(schema).rows
    if len(rows) != 1:
        raise ReportSourceMismatchError(f"gold_h3_reading has {len(rows)} rows, expected one")
    row = rows[0]
    permutation = col_bool_or_none(row, schema, "heterogeneous_permutation")
    ablation = col_bool_or_none(row, schema, "heterogeneous_ablation")
    return (
        f"leitura ({col_str(row, schema, 'reading_rule')}): "
        f"{col_str_or_none(row, schema, 'label')} [{col_str_or_none(row, schema, 'status')}]; "
        f"heterogênea na permutação = {permutation}, na ablação = {ablation}; "
        f"sustentada = {col_bool_or_none(row, schema, 'sustained')}; "
        f"famílias concordantes = {col_str_or_none(row, schema, 'agreeing_families')}"
    )


def h3_figure(inputs: ReportInputs) -> FigureAssembly:
    """I_f(h) por família e método em h+1 e h+7 lado a lado; Δ_f e a leitura C4/C5.

    Linguagem estritamente descritiva (C7). Os intervalos bootstrap de I_f(h) e s_f(h) não
    são persistidos (omissão declarada); só o de Δ_f é desenhado.

    Raises:
        ReportSourceMismatchError: revisão sem `[h3]` ou linha ausente.
    """
    if inputs.plan.h3 is None:
        raise ReportSourceMismatchError("the judged revision has no [h3] block")
    families = inputs.plan.h3.families
    panels = [
        _panel(
            inputs,
            horizon,
            _h3_horizon_series(inputs, horizon, families),
            x_label="família",
            y_label="I_f(h)",
            label=_DESCRIPTIVE,
        )
        for horizon in H3_HORIZONS
    ]
    panels.append(
        PanelSpec(
            panel_id="h1_vs_h7",
            scope=PanelScope.HORIZON_COMPARISON,
            horizon=None,
            title="h+1 vs. h+7",
            x_label="família",
            y_label="Δ_f / s_f(h)",
            series=tuple(_h3_comparison_series(inputs, families)),
            label=ElementLabel(status=StatusLabel.DESCRIPTIVE, note=_reading_note(inputs)),
        )
    )
    sources = (
        _gold(GOLD_H3_IMPORTANCE.name, ("importance", "status", "reason")),
        _gold(GOLD_H3_SHARES.name, ("share_h1", "share_h7", "delta", "lower", "upper", "status")),
        _gold(
            GOLD_H3_READING.name,
            (
                "label",
                "status",
                "heterogeneous_permutation",
                "heterogeneous_ablation",
                "sustained",
                "agreeing_families",
            ),
        ),
    )
    return FigureAssembly(spec=_spec("h3_family_importance", panels, (H3_NOTE,)), sources=sources)


# --------------------------------------------------------------------------------------
# Pesos da VSN (horizonte-invariante)
# --------------------------------------------------------------------------------------

VSN_NOTE: Final = FIGURE_CATALOG["vsn_weights"].required_notes[0]
VSN_FAMILY_KIND: Final = "family"


def vsn_figure(inputs: ReportInputs) -> FigureAssembly:
    """Peso por família na seleção de variáveis: p10/p50/p90 das linhas `kind = family`."""
    schema = GOLD_H3_VSN
    rows = sorted(
        _rows(inputs, schema, kind=VSN_FAMILY_KIND), key=lambda r: col_str(r, schema, "name")
    )
    if not rows:
        raise ReportSourceMismatchError("gold_h3_vsn has no family rows")
    label = ElementLabel(status=StatusLabel.DESCRIPTIVE, note=VSN_NOTE)
    series = SeriesSpec(
        series_id="vsn_family",
        kind=SeriesKind.INTERVAL,
        name="peso da VSN por família (p50; p10 a p90)",
        label=label,
        x=tuple(col_str(r, schema, "name") for r in rows),
        y=tuple(col_float_or_none(r, schema, "p50") for r in rows),
        low=tuple(col_float_or_none(r, schema, "p10") for r in rows),
        high=tuple(col_float_or_none(r, schema, "p90") for r in rows),
        text=tuple(
            f"{col_str_or_none(r, schema, 'label')} [{col_str_or_none(r, schema, 'status')}]"
            for r in rows
        ),
    )
    panel = PanelSpec(
        panel_id="invariant",
        scope=PanelScope.HORIZON_INVARIANT,
        horizon=None,
        title="horizonte-invariante",
        x_label="família",
        y_label="peso",
        series=(series,),
        label=label,
    )
    sources = (
        _gold(schema.name, ("name", "p10", "p50", "p90", "label", "status"), kind=VSN_FAMILY_KIND),
    )
    return FigureAssembly(spec=_spec("vsn_weights", [panel], (VSN_NOTE,)), sources=sources)


# --------------------------------------------------------------------------------------
# Figuras do silver: sharpness diagram e fan chart (D4, I6)
# --------------------------------------------------------------------------------------

SHARPNESS_NOTE: Final = FIGURE_CATALOG["sharpness_diagram"].required_notes[0]
_TEST_SPLIT: Final = "test"


def _assembled(inputs: ReportInputs, silver: VerifiedSilver) -> Mapping[int, HorizonSamples]:
    """As amostras por horizonte pelo dono do refresh, com os mesmos argumentos."""
    command = refresh_command_from(inputs.plan, inputs.preregistration_ref)
    assembled = SeriesAssembly.assemble(
        silver.records,
        silver.runs,
        silver.realized,
        horizons=command.horizons,
        window_deficits=command.window_deficits,
        required_models=frozenset({inputs.plan.candidate}),
    )
    if assembled.alignment.findings:
        raise ReportSourceMismatchError(
            f"the verified silver does not assemble: {len(assembled.alignment.findings)} "
            "alignment findings"
        )
    return {samples.horizon: samples for samples in assembled.horizons}


def degenerate_key(model: str, seed: Seed, horizon: int, pair: tuple[float, float]) -> str:
    """Chave de `excluded_degenerate`: `<modelo>|<seed>|h<h>|<τ_l>-<τ_u>`."""
    return f"{model}|{seed}|h{horizon}|{pair[0]}-{pair[1]}"


def _box(widths: Sequence[float]) -> tuple[float, float, float, float, float] | None:
    """Mínimo, quartis e máximo das larguras (exibição declarada no I3, GBR 2007 §3.3)."""
    if not widths:
        return None
    if len(widths) == 1:
        only = widths[0]
        return only, only, only, only, only
    q1, median, q3 = statistics.quantiles(widths, n=4, method="inclusive")
    return min(widths), q1, median, q3, max(widths)


def sharpness_figure(inputs: ReportInputs, silver: VerifiedSilver) -> FigureAssembly:
    """Caixas das larguras u - l por par, modelo, seed e horizonte (D13 linha 3).

    As larguras saem de `CoverageMetrics.interval_widths` sobre as séries `full` (máscara
    não-degenerada do MPIW); a média desenhada `fsum(widths) / len(widths)` tem de ser
    **exatamente** o `mpiw` `model_full` do gold. Os degenerados excluídos vão à legenda e
    ao registro (`excluded_degenerate`).

    Raises:
        ReportSourceMismatchError: o silver não monta ou a média difere do `mpiw` do gold.
    """
    tolerance = inputs.plan.h1_gate.degeneracy_tolerance
    by_horizon = _assembled(inputs, silver)
    excluded: dict[str, int] = {}
    panels: list[PanelSpec] = []
    for horizon in inputs.plan.horizons:
        samples = by_horizon[horizon]
        series: list[SeriesSpec] = []
        for model in samples.models:
            for seed, full in zip(samples.seeds[model], samples.full[model], strict=True):
                boxes: list[tuple[float, float, float, float, float] | None] = []
                labels: list[str] = []
                counts: list[str] = []
                for pair in full.symmetric_pairs:
                    widths = CoverageMetrics.interval_widths(full, tolerance=tolerance, pair=pair)
                    gold = _metric(
                        inputs,
                        model=model,
                        seed=seed,
                        horizon=horizon,
                        sample=GATE_SAMPLE,
                        metric="mpiw",
                        level_low=pair[0],
                        level_high=pair[1],
                    )
                    drawn = math.fsum(widths) / len(widths) if widths else None
                    if drawn != gold:
                        raise ReportSourceMismatchError(
                            f"sharpness mean width differs from gold mpiw model_full at "
                            f"model={model}, seed={seed}, horizon={horizon}, pair {pair}"
                        )
                    degenerate = full.n_points - len(widths)
                    excluded[degenerate_key(model, seed, horizon, pair)] = degenerate
                    boxes.append(_box(widths))
                    labels.append(pair_text(pair))
                    counts.append(f"{pair_text(pair)}: {degenerate}")
                series.append(
                    SeriesSpec(
                        series_id=f"{model}|{seed}",
                        kind=SeriesKind.BOXES,
                        name=f"{model} ({_seed_text(seed)})",
                        model=model,
                        label=ElementLabel(
                            status=StatusLabel.DESCRIPTIVE,
                            note="degenerados excluídos pela máscara do MPIW — "
                            + "; ".join(counts),
                        ),
                        x=tuple(labels),
                        y=tuple(None if b is None else b[2] for b in boxes),
                        low=tuple(None if b is None else b[1] for b in boxes),
                        high=tuple(None if b is None else b[3] for b in boxes),
                        whisker_low=tuple(None if b is None else b[0] for b in boxes),
                        whisker_high=tuple(None if b is None else b[4] for b in boxes),
                    )
                )
        panels.append(
            _panel(
                inputs,
                horizon,
                series,
                x_label="par (τ_l-τ_u)",
                y_label="largura u - l",
                label=_DESCRIPTIVE,
            )
        )
    sources = (
        SourceRef(
            kind=SourceKind.SILVER_TABLE,
            name=FACT_TABLE,
            filter={"split": _TEST_SPLIT, "value": "value_guardrail"},
            fields=("quantile_level", "value_guardrail", "target_timestamp_utc"),
        ),
        SourceRef(
            kind=SourceKind.REALIZED, name=REALIZED_TABLE, filter={}, fields=("target_return",)
        ),
        _gold(GOLD_METRICS_BY_RUN.name, ("value",), sample=GATE_SAMPLE, metric="mpiw"),
    )
    return FigureAssembly(
        spec=_spec("sharpness_diagram", panels, (SHARPNESS_NOTE,)),
        sources=sources,
        silver_units=silver.units,
        excluded_degenerate=excluded,
    )


def _fan_seed(inputs: ReportInputs, silver: VerifiedSilver, cohort_seeds: Sequence[int]) -> int:
    """A primeira seed da revisão julgada, igual à lista do cohort (I6); sem fallback."""
    candidate = inputs.plan.candidate
    seeds = inputs.plan.seeds[candidate].seeds
    if seeds is None or tuple(seeds) != tuple(cohort_seeds):
        raise ReportSourceMismatchError(
            "the cohort file seeds differ from the judged revision [seeds] of the candidate"
        )
    seed = seeds[0]
    if not any(
        r.model == candidate and r.seed == seed and r.split == _TEST_SPLIT for r in silver.records
    ):
        raise ReportSourceMismatchError(f"seed {seed} of the candidate has no test predictions")
    return seed


def _fan_units(silver: VerifiedSilver, run_ids: frozenset[str]) -> dict[str, str]:
    def keep(key: str) -> bool:
        parts = key.split(UNIT_KEY_SEPARATOR)
        if parts[0] == FACT_TABLE:
            return len(parts) > 1 and parts[1] in run_ids
        return parts[0] in {DIM_RUN_TABLE, REALIZED_TABLE}

    return {key: digest for key, digest in silver.units.items() if keep(key)}


def fan_chart_figure(
    inputs: ReportInputs, silver: VerifiedSilver, cohort_seeds: Sequence[int]
) -> FigureAssembly:
    """Realizado sobre as faixas dos pares simétricos do candidato, uma seed (I6; D13).

    Seed = a primeira de `[seeds].tft_quantile` da revisão julgada; a lista tem de ser a
    do arquivo de cohort. Quantis = a grade pontuada (`scored_values`, `value_guardrail`)
    da série `full`; realizado = `series.realized`; cortes de fold pelo run de cada alvo.
    Nunca a média dos quantis entre seeds.

    Raises:
        ReportSourceMismatchError: seeds diferentes, seed sem predições ou silver que não
            monta.
    """
    candidate = inputs.plan.candidate
    seed = _fan_seed(inputs, silver, cohort_seeds)
    by_horizon = _assembled(inputs, silver)
    panels: list[PanelSpec] = []
    for horizon in inputs.plan.horizons:
        samples = by_horizon[horizon]
        seeds = samples.seeds[candidate]
        full = samples.full[candidate][seeds.index(seed)]
        targets = full.target_timestamps
        points = range(full.n_points)
        series: list[SeriesSpec] = []
        for (low_level, high_level), (k_low, k_high) in zip(
            full.symmetric_pairs, full.symmetric_pair_indices, strict=True
        ):
            series.append(
                SeriesSpec(
                    series_id=f"band|{pair_text((low_level, high_level))}",
                    kind=SeriesKind.BAND,
                    name=f"faixa {pair_text((low_level, high_level))}",
                    model=candidate,
                    label=_DESCRIPTIVE,
                    x=targets,
                    y=tuple(None for _ in points),
                    low=tuple(full.scored_values(i)[k_low] for i in points),
                    high=tuple(full.scored_values(i)[k_high] for i in points),
                )
            )
        if MEDIAN_LEVEL in full.levels:
            k_median = full.levels.index(MEDIAN_LEVEL)
            series.append(
                SeriesSpec(
                    series_id="median",
                    kind=SeriesKind.LINE,
                    name="mediana (τ = 0,5)",
                    model=candidate,
                    label=_DESCRIPTIVE,
                    x=targets,
                    y=tuple(full.scored_values(i)[k_median] for i in points),
                )
            )
        series.append(
            SeriesSpec(
                series_id="realized",
                kind=SeriesKind.LINE,
                name="realizado y_t",
                label=_DESCRIPTIVE,
                x=targets,
                y=full.realized,
            )
        )
        fold_of = {
            r.target_timestamp: r.fold
            for r in silver.records
            if r.model == candidate
            and r.seed == seed
            and r.horizon == horizon
            and r.split == _TEST_SPLIT
        }
        cuts = tuple(_fold_cuts(targets, [fold_of.get(t) for t in targets]))
        if cuts:
            series.append(
                SeriesSpec(
                    series_id="fold_cuts",
                    kind=SeriesKind.VLINES,
                    name="corte de fold",
                    label=_DESCRIPTIVE,
                    x=cuts,
                    y=tuple(None for _ in cuts),
                )
            )
        panels.append(
            _panel(
                inputs,
                horizon,
                series,
                x_label="target_timestamp",
                y_label="retorno",
                label=ElementLabel(status=StatusLabel.DESCRIPTIVE, note=fan_chart_seed_note(seed)),
            )
        )
    run_ids = frozenset(
        run.run_id for run in silver.runs if run.model == candidate and run.seed == seed
    )
    sources = (
        SourceRef(
            kind=SourceKind.SILVER_TABLE,
            name=FACT_TABLE,
            filter={"model": candidate, "seed": seed, "split": _TEST_SPLIT},
            fields=("quantile_level", "value_guardrail", "target_timestamp_utc"),
        ),
        SourceRef(
            kind=SourceKind.REALIZED, name=REALIZED_TABLE, filter={}, fields=("target_return",)
        ),
        SourceRef(kind=SourceKind.SILVER_TABLE, name=DIM_RUN_TABLE, filter={}, fields=("fold",)),
    )
    return FigureAssembly(
        spec=_spec("oos_fan_chart", panels, (fan_chart_seed_note(seed),)),
        sources=sources,
        silver_units=_fan_units(silver, run_ids),
    )


FigureBuilder = Callable[[ReportInputs], FigureAssembly]
