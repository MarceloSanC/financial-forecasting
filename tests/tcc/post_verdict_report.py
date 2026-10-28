"""Análises pós-veredito (D1, D3 e D4) sobre a geração julgada: leitura, sanidade, cálculo e tabela.

Plano de fechamento (#237) §7; issue #243. **Calculado depois do veredito; não altera o
veredito.** D3 segue a especificação fixada no commit `cdf434bf`, antes de qualquer cálculo.

Leitura (só adaptadores de leitura, nada é escrito; a raiz é montada `:ro`):

- a cópia julgada única sob `<raiz>/gold/` (`judged_partition`, `read_judged_generation` e `find`,
  que conferem o `CONTENTS.sha256`), o seu `generation_digest` e o manifesto;
- o realizado pelo `ReadTrainingGrid` real, com o `dataset_fingerprint` conferido contra o
  do manifesto;
- o `dim_run` do cohort e o `fact_oos_predictions` dos seus runs pelo leitor silver real,
  com as unidades conferidas contra o `silver_content` da cópia (`check_silver_units`);
- a montagem pelo próprio `SeriesAssembly.assemble` do gold, com os horizontes, os déficits
  de janela e o candidato do manifesto: a amostra comum de H2 é a dele, não uma reconstrução.

**Sanidade (antes de qualquer número):** a pinball média da grade recomputada por (modelo,
semente, horizonte) na amostra comum tem de bater com `gold_metrics_by_run`; o MAE da
mediana, com 2·(pinball em τ = 0,5) gravada; o DM retangular do TFT contra cada
comparador, com `gold_dm_results`; o n comum, com o gravado. Qualquer divergência ergue
`PostVerdictSanityError` e nada é calculado.

    python -m tests.tcc.post_verdict_report <raiz>   # imprime o bloco de tabelas do relatório
"""

from __future__ import annotations

import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldManifest,
)
from financial_forecasting.features.evaluation.application.use_cases.silver_content_accumulator import (  # noqa: E501
    SilverContentAccumulator,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DieboldMariano,
    DieboldMarianoResult,
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    PinballScore,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    wilson_interval,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.features.feature_engineering.domain.services.dataset_tft_contract import (  # noqa: E501
    TARGET_COLUMN,
)
from financial_forecasting.features.modeling.application.use_cases.read_training_grid import (
    ReadTrainingGrid,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from tests.equivalence.readers import check_silver_units, judged_partition
from tests.tcc.post_verdict import (
    PointProfile,
    TailRates,
    median_is_identically_zero,
    pair_widths,
    point_profile,
    quantile_type7,
    seed_ensemble,
    seed_mean,
    spearman,
    tail_rates,
    values_at_decision,
)

BEGIN_MARKER: Final = "<!-- BEGIN: post-verdict-numbers -->"
END_MARKER: Final = "<!-- END: post-verdict-numbers -->"
ENSEMBLE: Final = "tft_seed_ensemble"
"""Nome da coluna do ensemble D3 na `PairedLossSeries` (não é um `model_version`)."""
D3_COMPARATORS: Final = ("baseline_ewma_vol", "gbm_quantile")
PAIR_80: Final = (0.1, 0.9)
WILSON_LEVEL: Final = 0.95
VOLATILITY_COLUMN: Final = "volatility_20d"
"""D4: a volatilidade de 20 sessões do registro, na sessão de decisão (causal)."""
DISPERSION_PROBABILITIES: Final = (0.05, 0.95)
RELATIVE_TOLERANCE: Final = 1e-9
"""Tolerância relativa da sanidade (o mesmo código sobre os mesmos dados; folga de fsum)."""
_SILVER: Final = "silver"
_DIM_RUN: Final = "dim_run"
_FACT: Final = "fact_oos_predictions"
_TEST_SPLIT: Final = "test"
_GUARDRAIL_FLAGS: Final = {0: False, 1: True}
MODEL_LABELS: Final[Mapping[str, str]] = {
    "baseline_zero_return": "Retorno nulo",
    "baseline_historical_mean": "Média histórica",
    "baseline_ar1": "AR(1)",
    "baseline_ewma_vol": "EWMA-vol",
    "baseline_historical_quantiles": "Quantis empíricos",
    "gbm_quantile": "GBM quantílico",
    "tft_quantile": "TFT",
}

Row = Mapping[str, object]


class PostVerdictSanityError(AssertionError):
    """A recomputação não bate com o gold julgado: parar antes de reportar qualquer número."""


# --- leitura ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class JudgedInputs:
    """O que as análises leem: proveniência, amostras montadas e tabelas gold de conferência."""

    preregistration_ref: str
    generation_digest: str
    candidate: str
    samples: Mapping[int, HorizonSamples]
    metrics_by_run: Sequence[Row]
    dm_results: Sequence[Row]
    grid_timestamps: tuple[str, ...]
    volatility: tuple[float, ...]
    """D4: `VOLATILITY_COLUMN` da grade de treino, alinhada a `grid_timestamps`."""


def _record(row: Row, run: CohortRun) -> ForecastRecord:
    """O mesmo mapeamento linha → `ForecastRecord` do `RefreshGold._read_records`."""
    flag = row["guardrail_applied"]
    if isinstance(flag, bool) or flag not in _GUARDRAIL_FLAGS:
        raise ValueError(f"guardrail_applied must be the int 0 or 1, got {flag!r}")
    return ForecastRecord(
        run_id=run.run_id,
        model=str(row["model_version"]),
        seed=run.seed,
        fold=run.fold,
        horizon=row["horizon"],  # type: ignore[arg-type]
        decision_idx=row["decision_idx"],  # type: ignore[arg-type]
        decision_timestamp=str(row["timestamp_utc"]),
        target_timestamp=str(row["target_timestamp_utc"]),
        split=str(row["split"]),
        quantile_level=row["quantile_level"],  # type: ignore[arg-type]
        value_raw=row["value_raw"],  # type: ignore[arg-type]
        value_guardrail=row["value_guardrail"],  # type: ignore[arg-type]
        guardrail_applied=_GUARDRAIL_FLAGS[flag],
    )


def _read_cohort(
    root: Path, manifest: GoldManifest
) -> tuple[tuple[CohortRun, ...], tuple[ForecastRecord, ...]]:
    """`dim_run` do cohort e as linhas de teste dos seus runs, com o silver conferido."""
    partition = manifest.partition
    repository = ParquetAnalyticsRepository(data_root=root, clock=SystemClock())
    accumulator = SilverContentAccumulator(hasher=CanonicalJsonHasher())
    dim_rows = [
        row
        for row in repository.read(
            layer=_SILVER,
            table=_DIM_RUN,
            filters={"asset": partition.asset, "parent_sweep_id": partition.parent_sweep_id},
        )
        if (row.get("asset"), row.get("parent_sweep_id"))
        == (partition.asset, partition.parent_sweep_id)
    ]
    accumulator.add_dim_run(
        columns=repository.columns(layer=_SILVER, table=_DIM_RUN),
        parent_sweep_id=partition.parent_sweep_id,
        rows=dim_rows,
    )
    runs = tuple(
        sorted(
            (
                CohortRun(
                    run_id=str(row["run_id"]),
                    model=str(row["model_version"]),
                    seed=row["seed"],  # type: ignore[arg-type]
                    fold=row["fold"],  # type: ignore[arg-type]
                    feature_set_name=str(row["feature_set_name"]),
                    config_signature=str(row["config_signature"]),
                )
                for row in dim_rows
            ),
            key=lambda run: run.run_id,
        )
    )
    by_id = {run.run_id: run for run in runs}
    fact_columns = repository.columns(layer=_SILVER, table=_FACT)
    records: list[ForecastRecord] = []
    for feature_set in sorted({run.feature_set_name for run in runs}):
        kept = [
            row
            for row in repository.read(
                layer=_SILVER,
                table=_FACT,
                filters={"asset": partition.asset, "feature_set_name": feature_set},
            )
            if row.get("asset") == partition.asset and str(row["run_id"]) in by_id
        ]
        accumulator.add_facts(table=_FACT, columns=fact_columns, rows=kept)
        records += [
            _record(row, by_id[str(row["run_id"])]) for row in kept if row["split"] == _TEST_SPLIT
        ]
    check_silver_units(accumulator.result(), manifest.silver_content, partition, frozenset(by_id))
    return runs, tuple(records)


def read_judged_inputs(root: Path) -> JudgedInputs:
    """Lê a cópia julgada, o realizado e o silver do cohort e monta as amostras do gold.

    Raises:
        PostVerdictSanityError: fingerprint da grade ≠ manifesto, ou a montagem com achados.
        OfficialSilverMismatchError: silver lido ≠ o consumido pela cópia julgada.
    """
    root = Path(root)
    partition, ref = judged_partition(root)
    store = ParquetGoldStore(root)
    generation = store.read_judged_generation(partition=partition, preregistration_ref=ref)
    sealed = store.find(partition=partition, preregistration_ref=ref)
    if sealed is None:  # o `read_judged_generation` acabou de achar a cópia
        raise PostVerdictSanityError(f"judged copy {ref} vanished")
    manifest = generation.manifest
    grid, fingerprint = ReadTrainingGrid(
        store=ParquetMedallionStore(data_root=root),
        columns=modeling_columns(),
        hasher=CanonicalJsonHasher(),
    )(asset_id=partition.asset)
    if fingerprint.value != manifest.dataset_fingerprint.value:
        raise PostVerdictSanityError(
            f"training grid fingerprint {fingerprint.value} != judged copy "
            f"{manifest.dataset_fingerprint.value}"
        )
    realized = RealizedReturns(timestamps=grid.timestamps_iso(), returns=grid.column(TARGET_COLUMN))
    runs, records = _read_cohort(root, manifest)
    candidate = manifest.parameters.candidate
    assembled = SeriesAssembly.assemble(
        records,
        runs,
        realized,
        horizons=manifest.horizons,
        window_deficits=manifest.window_deficits,
        required_models=frozenset({candidate}),
    )
    if assembled.alignment.findings:
        raise PostVerdictSanityError(f"assembly findings: {assembled.alignment.findings[:5]}")
    return JudgedInputs(
        preregistration_ref=ref,
        generation_digest=sealed.generation_digest,
        candidate=candidate,
        samples={sample.horizon: sample for sample in assembled.horizons},
        metrics_by_run=generation.tables["gold_metrics_by_run"].rows,
        dm_results=generation.tables["gold_dm_results"].rows,
        grid_timestamps=grid.timestamps_iso(),
        volatility=grid.column(VOLATILITY_COLUMN),
    )


# --- sanidade --------------------------------------------------------------------------------


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=RELATIVE_TOLERANCE, abs_tol=0.0)


def _gold_row(rows: Iterable[Row], where: str, **match: object) -> Row:
    found = [row for row in rows if all(row.get(k) == v for k, v in match.items())]
    if len(found) != 1:
        raise PostVerdictSanityError(f"{where}: {len(found)} gold rows for {match}")
    return found[0]


def _number(row: Row, field: str) -> float:
    value = row[field]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PostVerdictSanityError(f"gold field {field} is not a number: {value!r}")
    return float(value)


@dataclass(frozen=True)
class SanityCheck:
    """Uma conferência recomputado contra gravado (todas têm de bater)."""

    what: str
    recomputed: float
    recorded: float


def sanity_checks(inputs: JudgedInputs) -> tuple[SanityCheck, ...]:
    """As conferências da sanidade, sem julgar (o `check_sanity` julga)."""
    checks: list[SanityCheck] = []
    for horizon, sample in sorted(inputs.samples.items()):
        for model in sample.models:
            for seed, series in zip(sample.seeds[model], sample.common[model], strict=True):
                key = {"model": model, "seed": seed, "horizon": horizon, "sample": "common"}
                where = f"{model} seed {seed} h+{horizon}"
                grid = _gold_row(inputs.metrics_by_run, where, metric="pinball_grid_mean", **key)
                median = _gold_row(
                    inputs.metrics_by_run, where, metric="pinball", level_low=0.5, **key
                )
                checks += [
                    SanityCheck(
                        f"pinball_grid_mean {where}",
                        PinballScore.score(series).grid_mean,
                        _number(grid, "value"),
                    ),
                    SanityCheck(
                        f"MAE = 2 x pinball(0.5) {where}",
                        point_profile(series).mae,
                        2.0 * _number(median, "value"),
                    ),
                    SanityCheck(
                        f"n_points {where}", float(series.n_points), _number(grid, "n_points")
                    ),
                ]
        candidate = inputs.candidate
        for comparator in sample.models:
            if comparator == candidate:
                continue
            result = _dm(sample, {candidate: sample.common[candidate]}, comparator)
            gold = [
                row
                for row in inputs.dm_results
                if row["horizon"] == horizon
                and row["candidate"] == candidate
                and row["comparator"] == comparator
                and row["variance_estimator"] == DmVarianceEstimator.RECTANGULAR.value
            ]
            if len(gold) != 1:
                raise PostVerdictSanityError(f"DM {comparator} h+{horizon}: {len(gold)} rows")
            checks += [
                SanityCheck(
                    f"DM {field} {candidate} x {comparator} h+{horizon}",
                    float(getattr(result, field)),
                    _number(gold[0], field),
                )
                for field in ("mean_differential", "statistic", "p_value")
            ]
    return tuple(checks)


def check_sanity(checks: Sequence[SanityCheck]) -> None:
    """Para se alguma conferência não bate (tolerância relativa `RELATIVE_TOLERANCE`).

    Raises:
        PostVerdictSanityError: lista as divergências.
    """
    bad = [c for c in checks if not _close(c.recomputed, c.recorded)]
    if bad:
        shown = "; ".join(f"{c.what}: {c.recomputed!r} != {c.recorded!r}" for c in bad[:10])
        raise PostVerdictSanityError(f"{len(bad)} of {len(checks)} checks differ: {shown}")


# --- D1 e D3 -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Direction:
    """Acurácia direcional (média entre sementes) com o IC de Wilson de 95 %."""

    hits: float
    ties: float
    n_points: int
    rate: float
    lower: float
    upper: float


@dataclass(frozen=True)
class D1Row:
    """Perfil pontual de um modelo num horizonte (média entre sementes; mín. e máx. se S > 1)."""

    model: str
    horizon: int
    n_seeds: int
    rmse: tuple[float, float, float]
    mae: tuple[float, float, float]
    direction: Direction | None
    """`None` quando a mediana é identicamente nula (acurácia direcional não se aplica)."""


def _summary(values: Sequence[float]) -> tuple[float, float, float]:
    return seed_mean(values), min(values), max(values)


def d1_rows(inputs: JudgedInputs) -> tuple[D1Row, ...]:
    """D1 por modelo e horizonte na amostra comum, na ordem de `MODEL_LABELS`."""
    rows: list[D1Row] = []
    for horizon, sample in sorted(inputs.samples.items()):
        for model in (m for m in MODEL_LABELS if m in sample.models):
            seeds = sample.common[model]
            profiles: list[PointProfile] = [point_profile(series) for series in seeds]
            direction = None
            if not median_is_identically_zero(seeds):
                n_points = profiles[0].n_points
                hits = seed_mean([float(p.hits) for p in profiles])
                lower, upper = wilson_interval(count=hits, n=n_points, band_level=WILSON_LEVEL)
                direction = Direction(
                    hits=hits,
                    ties=seed_mean([float(p.ties) for p in profiles]),
                    n_points=n_points,
                    rate=hits / n_points,
                    lower=lower,
                    upper=upper,
                )
            rows.append(
                D1Row(
                    model=model,
                    horizon=horizon,
                    n_seeds=len(seeds),
                    rmse=_summary([p.rmse for p in profiles]),
                    mae=_summary([p.mae for p in profiles]),
                    direction=direction,
                )
            )
    return tuple(rows)


def _dm(
    sample: HorizonSamples,
    candidate: Mapping[str, Sequence[CoverageSeries]],
    comparator: str,
) -> DieboldMarianoResult:
    """DM unilateral retangular + HLN (a especificação confirmatória) do candidato x comparador.

    As perdas são as L_t da grade, com média ponto a ponto entre sementes do comparador
    (`paired_pinball_losses`), exatamente como no gold.
    """
    (name,) = candidate
    series = paired_pinball_losses({**candidate, comparator: sample.common[comparator]})
    return DieboldMariano.compare(
        series,
        candidate=name,
        comparator=comparator,
        variance_estimator=DmVarianceEstimator.RECTANGULAR,
    )


@dataclass(frozen=True)
class D3Row:
    """A média das sementes do TFT num horizonte (especificação `cdf434bf`)."""

    horizon: int
    n_points: int
    ensemble_pinball: float
    seed_mean_pinball: float
    comparator_pinball: Mapping[str, float]
    ensemble_rates: TailRates
    seed_mean_rates: TailRates
    dm: Mapping[str, DieboldMarianoResult]


def d3_rows(inputs: JudgedInputs) -> tuple[D3Row, ...]:
    """D3 por horizonte: pinball, razões, caudas do par de 80 %, PICP e DM bruto."""
    rows: list[D3Row] = []
    for horizon, sample in sorted(inputs.samples.items()):
        seeds = sample.common[inputs.candidate]
        ensemble = seed_ensemble(seeds)
        per_seed_rates = [tail_rates(series, pair=PAIR_80) for series in seeds]
        rows.append(
            D3Row(
                horizon=horizon,
                n_points=ensemble.n_points,
                ensemble_pinball=PinballScore.score(ensemble).grid_mean,
                seed_mean_pinball=seed_mean(
                    [PinballScore.score(series).grid_mean for series in seeds]
                ),
                comparator_pinball={
                    c: seed_mean([PinballScore.score(s).grid_mean for s in sample.common[c]])
                    for c in D3_COMPARATORS
                },
                ensemble_rates=tail_rates(ensemble, pair=PAIR_80),
                seed_mean_rates=TailRates(
                    lower=seed_mean([r.lower for r in per_seed_rates]),
                    upper=seed_mean([r.upper for r in per_seed_rates]),
                    picp=seed_mean([r.picp for r in per_seed_rates]),
                ),
                dm={c: _dm(sample, {ENSEMBLE: (ensemble,)}, c) for c in D3_COMPARATORS},
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class D4Row:
    """Resposta da largura do par de 80 % à volatilidade, num modelo e horizonte (issue #272).

    No TFT, a largura de cada ponto é a média das larguras das sementes (a largura do
    *ensemble* da D3, pois a média é linear).
    """

    model: str
    horizon: int
    n_points: int
    spearman: float
    median_width: float
    dispersion: float
    """Razão entre os quantis de 95 % e de 5 % da largura ao longo da série."""


def d4_rows(inputs: JudgedInputs) -> tuple[D4Row, ...]:
    """D4 por modelo e horizonte na amostra comum, sem os modelos de largura identicamente nula."""
    rows: list[D4Row] = []
    for horizon, sample in sorted(inputs.samples.items()):
        for model in (m for m in MODEL_LABELS if m in sample.models):
            seeds = sample.common[model]
            per_seed = [pair_widths(series, pair=PAIR_80) for series in seeds]
            widths = [seed_mean(list(point)) for point in zip(*per_seed, strict=True)]
            if all(w == 0.0 for w in widths):
                continue
            volatility = values_at_decision(
                seeds[0], timestamps=inputs.grid_timestamps, column=inputs.volatility
            )
            low, high = (quantile_type7(widths, p) for p in DISPERSION_PROBABILITIES)
            rows.append(
                D4Row(
                    model=model,
                    horizon=horizon,
                    n_points=len(widths),
                    spearman=spearman(widths, volatility),
                    median_width=quantile_type7(widths, 0.5),
                    dispersion=high / low,
                )
            )
    return tuple(rows)


# --- tabela ----------------------------------------------------------------------------------


def _positive_share(realized: Sequence[float]) -> float:
    return sum(1 for y in realized if y > 0.0) / len(realized)


def _f(value: float, decimals: int, scale: float = 1.0) -> str:
    return f"{value * scale:.{decimals}f}"


def _range(values: tuple[float, float, float], n_seeds: int, scale: float) -> str:
    mean, low, high = values
    if n_seeds == 1:
        return _f(mean, 3, scale)
    return f"{_f(mean, 3, scale)} [{_f(low, 3, scale)}; {_f(high, 3, scale)}]"


def render(
    inputs: JudgedInputs,
    d1: Sequence[D1Row],
    d3: Sequence[D3Row],
    d4: Sequence[D4Row],
    *,
    n_checks: int,
) -> str:
    """O bloco de números do relatório (determinístico; o teste opt-in o compara)."""
    lines = [
        BEGIN_MARKER,
        "",
        f"`preregistration_ref` `{inputs.preregistration_ref}`; "
        f"`generation_digest` `{inputs.generation_digest}`; "
        "n comum: "
        + ", ".join(f"h+{h} = {s.n_common}" for h, s in sorted(inputs.samples.items()))
        + ".",
        "",
        f"Sanidade: as {n_checks} conferências contra o gold julgado bateram (tolerância "
        f"relativa {RELATIVE_TOLERANCE:g}): pinball média da grade, MAE = 2·pinball(0,5) e n "
        "por (modelo, semente, horizonte) na amostra comum; d̄, estatística e p do DM "
        "retangular do TFT contra cada comparador.",
        "",
        "### D1 — perfil pontual da mediana (τ = 0,5)",
        "",
        "RMSE e MAE em 10⁻²; TFT: média das 10 sementes [mín.; máx.]. Acurácia direcional: "
        "fração de pontos com mediana·realizado > 0 (média das sementes no TFT), IC de "
        "Wilson de 95 %.",
        "",
        "Referência de taxa-base: fração de realizados > 0 na amostra comum, "
        + ", ".join(
            f"h+{h} = {_f(_positive_share(s.common[inputs.candidate][0].realized), 4)}"
            for h, s in sorted(inputs.samples.items())
        )
        + " (uma mediana sempre positiva acerta exatamente essa fração).",
        "",
        "| modelo | h | RMSE | MAE | acurácia direcional | IC 95 % | empates |",
        "|---|---|---|---|---|---|---|",
    ]
    for d1_row in d1:
        direction = d1_row.direction
        tail = (
            "não se aplica (mediana identicamente nula) | — | —"
            if direction is None
            else f"{_f(direction.rate, 4)} | [{_f(direction.lower, 4)}; "
            f"{_f(direction.upper, 4)}] | {_f(direction.ties, 1)}"
        )
        lines.append(
            f"| {MODEL_LABELS[d1_row.model]} | {d1_row.horizon} | "
            f"{_range(d1_row.rmse, d1_row.n_seeds, 1e2)} | "
            f"{_range(d1_row.mae, d1_row.n_seeds, 1e2)} | {tail} |"
        )
    lines += [
        "",
        "### D3 — média das sementes do TFT (especificação `cdf434bf`)",
        "",
        "Pinball média da grade em 10⁻³. Razão < 1: o *ensemble* perde menos que a referência.",
        "",
        "| h | n | *ensemble* | média das perdas por semente | razão | EWMA-vol | razão "
        "| GBM | razão |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in d3:
        ewma = row.comparator_pinball["baseline_ewma_vol"]
        gbm = row.comparator_pinball["gbm_quantile"]
        lines.append(
            f"| {row.horizon} | {row.n_points} | {_f(row.ensemble_pinball, 4, 1e3)} | "
            f"{_f(row.seed_mean_pinball, 4, 1e3)} | "
            f"{_f(row.ensemble_pinball / row.seed_mean_pinball, 4)} | "
            f"{_f(ewma, 4, 1e3)} | {_f(row.ensemble_pinball / ewma, 4)} | "
            f"{_f(gbm, 4, 1e3)} | {_f(row.ensemble_pinball / gbm, 4)} |"
        )
    lines += [
        "",
        "Par de 80 % (τ = 0,1 e 0,9): violação inferior (y ≤ q₀,₁), superior (y > q₀,₉) e PICP "
        '(nominais 0,10, 0,10 e 0,80). A linha "por semente" é a média das taxas das 10 '
        "sementes, só como referência.",
        "",
        "| h | série | violação inferior | violação superior | PICP |",
        "|---|---|---|---|---|",
    ]
    for row in d3:
        for label, rates in (
            ("*ensemble*", row.ensemble_rates),
            ("por semente", row.seed_mean_rates),
        ):
            lines.append(
                f"| {row.horizon} | {label} | {_f(rates.lower, 4)} | {_f(rates.upper, 4)} | "
                f"{_f(rates.picp, 4)} |"
            )
    lines += [
        "",
        "DM unilateral (H1: o *ensemble* tem perda esperada menor), variância retangular até a "
        "defasagem h-1, correção HLN; d̄ em 10⁻⁵; **p-valor bruto** (sem Holm).",
        "",
        "| h | comparador | d̄ | estatística | p bruto | fallback |",
        "|---|---|---|---|---|---|",
    ]
    for row in d3:
        for comparator, result in row.dm.items():
            lines.append(
                f"| {row.horizon} | {MODEL_LABELS[comparator]} | "
                f"{_f(result.mean_differential, 3, 1e5)} | {_f(result.statistic, 3)} | "
                f"{_f(result.p_value, 4)} | {'sim' if result.fallback_applied else 'não'} |"
            )
    lines += [
        "",
        "### D4 — resposta da largura do par de 80 % à volatilidade (issue #272)",
        "",
        "Largura q₀,₉ - q₀,₁ por ponto (TFT: média das larguras das 10 sementes). Spearman: "
        f"correlação de postos entre a largura e `{VOLATILITY_COLUMN}` na sessão de decisão. "
        "Dispersão: quantil de 95 % ÷ quantil de 5 % da largura (tipo 7). Mediana em 10⁻².",
        "",
        "| modelo | h | n | Spearman | mediana | dispersão |",
        "|---|---|---|---|---|---|",
    ]
    for d4_row in d4:
        lines.append(
            f"| {MODEL_LABELS[d4_row.model]} | {d4_row.horizon} | {d4_row.n_points} | "
            f"{_f(d4_row.spearman, 3)} | {_f(d4_row.median_width, 3, 1e2)} | "
            f"{_f(d4_row.dispersion, 2)} |"
        )
    lines += ["", END_MARKER]
    return "\n".join(lines) + "\n"


def compute(root: Path) -> str:
    """Lê, confere a sanidade (para se divergir) e devolve o bloco renderizado."""
    inputs = read_judged_inputs(root)
    checks = sanity_checks(inputs)
    check_sanity(checks)
    return render(inputs, d1_rows(inputs), d3_rows(inputs), d4_rows(inputs), n_checks=len(checks))


def block_of(text: str) -> str:
    """O bloco entre os marcadores (inclusive) de um documento.

    Raises:
        ValueError: marcador ausente ou fora de ordem.
    """
    start, end = text.find(BEGIN_MARKER), text.find(END_MARKER)
    if start < 0 or end < start:
        raise ValueError("post-verdict markers missing or out of order")
    return text[start : end + len(END_MARKER)] + "\n"


def main(argv: Sequence[str]) -> int:
    """`python -m tests.tcc.post_verdict_report <raiz>`: imprime o bloco."""
    if len(argv) != 1:
        print("usage: python -m tests.tcc.post_verdict_report <data_root>", file=sys.stderr)
        return 2
    sys.stdout.write(compute(Path(argv[0])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
