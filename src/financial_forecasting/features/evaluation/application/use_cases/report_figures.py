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

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_CONFORMAL_COVERAGE,
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
    col_float_or_none,
    col_int_or_none,
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
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_real_number,
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


FigureBuilder = Callable[[ReportInputs], FigureAssembly]
