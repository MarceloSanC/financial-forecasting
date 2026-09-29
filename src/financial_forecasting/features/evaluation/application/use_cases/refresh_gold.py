"""Use case `RefreshGold` — regenera o gold de um cohort a partir do silver (Stage 6.4).

Orquestração (concept 6.4 §4, D1-D8, I1-I17, C1-C7; ADRs `6_4_0001`-`6_4_0006`), sem
regra de domínio própria — cada passo delega ao dono, na ordem de I15 (guardas antes
de efeitos):

1. a ordem dos builders é validada no **construtor** (`gold_build_order`, C1): grafo
   inválido falha no wiring, antes de qualquer leitura;
2. o `RefreshGoldCommand` já validou os identificadores (`GoldPartition`, C3);
3. leituras: `dim_run` do cohort (vazio → `ValueError`, C4) → `fact_oos_predictions`
   de cada `feature_set_name` do cohort, pós-filtrado ao cohort → o realizado **uma
   vez** pela grade de treino da 5.5 (`TrainingGridReader`, ADR 6.4.0009: índice 0 =
   primeira sessão da grade aparada, a mesma origem do `decision_idx` dos escritores;
   erros do dono propagam, C4) com o `DatasetContentFingerprint` conferido contra o
   `command.dataset_fingerprint` — divergente → `GridFingerprintMismatchError` (C10),
   antes da montagem e de qualquer efeito;
4. `SeriesAssembly.assemble` (achados, nunca exceção — D1);
5. passo de pré-condições (I11): por horizonte, `models_suffice` antes da fábrica
   `paired_pinball_losses`; por par, `block_request_defect` antes do backend; do
   backend, **só** `ArithmeticError` vira `BlockEstimate` indefinido — o resto propaga
   (C7);
6. `QualityCheckRegistry` com os quatro checks (ADR `6_4_0002`) → bloqueado?;
7. se não bloqueado: `HorizonReports` por horizonte e o MCS por (horizonte, esquema)
   com o bloco da regra (`ModelConfidenceSet.block_length`) e `reps`/`seed` dos
   parâmetros (ADR `6_4_0006`);
8. builders na ordem validada (bloqueado → só os `runs_when_blocked`);
9. `GoldManifest` (timestamps só do `Clock`, I16) e `GoldStore.publish` — o único
   efeito colateral, por último (nada é gravado antes; exceção antes dele não toca o
   store).

Uma linha `INFO` por etapa (`step=<nome> duration_s=<s> in=<n> out=<n>`) e uma final
com o `status`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from time import perf_counter

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldManifest,
    GoldPartition,
    GoldTable,
    RefreshGoldCommand,
    RefreshGoldResult,
    RefreshParameters,
    RefreshStatus,
    failed_checks_of,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_builder import (
    GoldBuilder,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_store import (
    GoldStore,
)
from financial_forecasting.features.evaluation.application.ports.out.mcs_backend import (
    McsBackend,
)
from financial_forecasting.features.evaluation.application.ports.out.silver_table_reader import (
    SilverTableReader,
)
from financial_forecasting.features.evaluation.application.ports.out.training_grid_reader import (
    TrainingGridReader,
)
from financial_forecasting.features.evaluation.domain.services.gold_build_order import (
    gold_build_order,
)
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    HorizonReport,
    HorizonReports,
)
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    McsReport,
    ModelConfidenceSet,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.alignment_check import (  # noqa: E501
    AlignmentCheck,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.degeneracy_check import (  # noqa: E501
    DegeneracyCheck,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.realized_provenance_check import (  # noqa: E501
    RealizedProvenanceCheck,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.registry import (
    QualityCheckContext,
    QualityCheckRegistry,
)
from financial_forecasting.features.evaluation.domain.services.quality_checks.statistical_preconditions_check import (  # noqa: E501
    StatisticalPreconditionsCheck,
    block_request_defect,
)
from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    SeriesAssembly,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AssembledCohort,
)
from financial_forecasting.features.evaluation.domain.value_objects.block_estimate import (
    BlockEstimate,
    UndefinedReason,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
    models_suffice,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.shared.application.ports.out.clock import Clock
from financial_forecasting.shared.application.ports.out.hasher import Hasher
from financial_forecasting.shared.domain.exceptions.base import ApplicationError
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)

logger = logging.getLogger(__name__)

SILVER_LAYER = "silver"
_TARGET = "target_return"
_FINGERPRINT_SHOWN = 12
_GUARDRAIL_FLAGS = {0: False, 1: True}
_DEFECT_DETAIL = {
    UndefinedReason.CONSTANT_DIFFERENTIAL: "the loss differential is constant",
    UndefinedReason.INVALID_SERIES: "the differential fails validate_block_length_request",
}


def _timed[T](step: str, n_in: int, action: Callable[[], T], count: Callable[[T], int]) -> T:
    start = perf_counter()
    result = action()
    logger.info(
        "refresh_gold step=%s duration_s=%.6f in=%d out=%d",
        step,
        perf_counter() - start,
        n_in,
        count(result),
    )
    return result


class GridFingerprintMismatchError(ApplicationError):
    """A grade lida não é a do cohort: o fingerprint diverge do congelado (C10).

    Espelha o `DatasetMismatchError` da corrida confirmatória (ADR 6.4.0009 item 5): o
    dado não é aquele sobre o qual o cohort treinou, então não há série a julgar.
    """


class RefreshGold:
    """Regenera por inteiro a geração gold de um cohort (ADR `6_4_0005`)."""

    def __init__(  # noqa: PLR0913 — os sete colaboradores do concept 6.4 §4 (keyword-only)
        self,
        *,
        silver_reader: SilverTableReader,
        grid_reader: TrainingGridReader,
        hasher: Hasher,
        clock: Clock,
        mcs_backend: McsBackend,
        gold_store: GoldStore,
        builders: Sequence[GoldBuilder],
    ) -> None:
        """Valida a ordem dos builders já no wiring (C1) e guarda os colaboradores.

        Raises:
            ValueError: grafo de builders inválido (`gold_build_order`).
        """
        order = gold_build_order([(builder.name, builder.depends_on) for builder in builders])
        by_name = {builder.name: builder for builder in builders}
        self._build_order = order
        self._builders = tuple(by_name[name] for name in order)
        self._silver_reader = silver_reader
        self._grid_reader = grid_reader
        self._hasher = hasher
        self._clock = clock
        self._mcs_backend = mcs_backend
        self._gold_store = gold_store
        self._registry = QualityCheckRegistry(
            [
                AlignmentCheck(),
                StatisticalPreconditionsCheck(),
                DegeneracyCheck(),
                RealizedProvenanceCheck(),
            ]
        )

    @property
    def build_order(self) -> tuple[str, ...]:
        """A ordem validada dos builders."""
        return self._build_order

    def __call__(self, command: RefreshGoldCommand) -> RefreshGoldResult:
        """Lê, monta, checa, relata, mapeia e publica uma geração (I15).

        Raises:
            GridFingerprintMismatchError: a grade não é a do cohort (C10).
            ValueError: cohort vazio (C4), linha de silver mal-formada, e qualquer erro
                de programação (C7); os erros do dono da grade (`NoUsableRowsError`,
                `InteriorMissingValuesError`) propagam — nada é publicado.
        """
        started_at = self._clock.now()
        partition, parameters = command.partition, command.parameters
        runs = _timed("read_runs", 0, lambda: self._read_runs(partition), len)
        records = _timed(
            "read_facts",
            len(runs),
            lambda: self._read_records(partition, runs),
            len,
        )
        realized, fingerprint, trimmed_prefix = _timed(
            "read_realized",
            0,
            lambda: self._read_realized(partition.asset, command.dataset_fingerprint),
            lambda r: len(r[0].timestamps),
        )
        assembled = _timed(
            "assemble",
            len(records),
            lambda: SeriesAssembly.assemble(
                records,
                runs,
                realized,
                horizons=command.horizons,
                window_deficits=command.window_deficits,
                required_models=frozenset({parameters.candidate}),
            ),
            lambda a: len(a.horizons),
        )
        paired, estimates = _timed(
            "preconditions",
            len(assembled.horizons),
            lambda: self._preconditions(assembled),
            lambda pe: sum(len(e) for e in pe[1].values()),
        )
        results = _timed(
            "checks",
            len(self._registry.names),
            lambda: self._registry.run(
                QualityCheckContext(
                    assembled=assembled,
                    paired=paired,
                    block_estimates=estimates,
                    tolerance=parameters.degeneracy_tolerance,
                    dataset_fingerprint=fingerprint,
                    grid_trimmed_prefix=trimmed_prefix,
                    realized=realized,
                )
            ),
            len,
        )
        blocked = QualityCheckRegistry.is_blocking(results)
        status = RefreshStatus.BLOCKED if blocked else RefreshStatus.COMPLETED
        reports: tuple[HorizonReport, ...] = ()
        mcs: tuple[McsReport, ...] = ()
        if not blocked:
            reports = _timed(
                "reports",
                len(assembled.horizons),
                lambda: self._reports(assembled, paired, parameters),
                len,
            )
            mcs = _timed("mcs", len(paired), lambda: self._mcs(paired, estimates, parameters), len)
        inputs = GoldInputs(
            partition=partition,
            parameters=parameters,
            status=status,
            check_results=results,
            horizon_reports=reports,
            mcs_reports=mcs,
            block_estimates=estimates,
        )
        builders = [b for b in self._builders if not blocked or b.runs_when_blocked]
        tables = _timed("build", len(builders), lambda: [b.build(inputs) for b in builders], len)
        rows_by_table = {table.name: len(table.rows) for table in tables}
        manifest = self._manifest(
            command=command,
            status=status,
            tables=tables,
            runs=runs,
            realized=realized,
            fingerprint=fingerprint,
            grid_trimmed_prefix=trimmed_prefix,
            started_at=started_at,
        )
        _timed(
            "publish",
            len(tables),
            lambda: self._gold_store.publish(partition=partition, tables=tables, manifest=manifest),
            lambda _: sum(rows_by_table.values()),
        )
        logger.info("refresh_gold status=%s partition=%s", status.value, partition)
        return RefreshGoldResult(
            status=status,
            rows_by_table=rows_by_table,
            failed_checks=failed_checks_of(results),
        )

    # -- leituras --------------------------------------------------------------------

    def _read_runs(self, partition: GoldPartition) -> tuple[CohortRun, ...]:
        rows = self._silver_reader.read(
            layer=SILVER_LAYER,
            table="dim_run",
            filters={"asset": partition.asset, "parent_sweep_id": partition.parent_sweep_id},
        )
        runs = tuple(
            CohortRun(
                run_id=str(row["run_id"]),
                model=str(row["model_version"]),
                seed=row["seed"],  # type: ignore[arg-type]
                fold=row["fold"],  # type: ignore[arg-type]
                feature_set_name=str(row["feature_set_name"]),
                config_signature=str(row["config_signature"]),
            )
            for row in rows
            if (row.get("asset"), row.get("parent_sweep_id"))
            == (partition.asset, partition.parent_sweep_id)
        )
        if not runs:
            raise ValueError(f"cohort {partition} has no dim_run rows (C4)")
        return tuple(sorted(runs, key=lambda run: run.run_id))

    def _read_records(
        self, partition: GoldPartition, runs: Sequence[CohortRun]
    ) -> tuple[ForecastRecord, ...]:
        by_id = {run.run_id: run for run in runs}
        records: list[ForecastRecord] = []
        for feature_set in sorted({run.feature_set_name for run in runs}):
            rows = self._silver_reader.read(
                layer=SILVER_LAYER,
                table="fact_oos_predictions",
                filters={"asset": partition.asset, "feature_set_name": feature_set},
            )
            for row in rows:
                run = by_id.get(str(row["run_id"]))
                if row.get("asset") != partition.asset or run is None:
                    continue  # fora do cohort: descartado na leitura (ADR 6.4.0004 item 2)
                records.append(_record(row, run))
        return tuple(records)

    def _read_realized(
        self, asset: str, expected: str
    ) -> tuple[RealizedReturns, DatasetContentFingerprint, int]:
        """Realizado = a grade de treino do ativo, conferida contra o cohort (ADR 6.4.0009).

        Raises:
            GridFingerprintMismatchError: fingerprint da grade != `expected` (C10).
        """
        grid = self._grid_reader(asset_id=asset)
        timestamps = grid.timestamps_iso()
        fingerprint = DatasetContentFingerprint.compute(
            hasher=self._hasher, asset_id=asset, timestamps=timestamps, columns=grid.columns
        )
        if fingerprint.value != expected:
            raise GridFingerprintMismatchError(
                f"training grid of {asset!r} has fingerprint "
                f"{fingerprint.value[:_FINGERPRINT_SHOWN]}…, the cohort was trained on "
                f"{expected[:_FINGERPRINT_SHOWN]}… (C10)"
            )
        realized = RealizedReturns(timestamps=timestamps, returns=grid.column(_TARGET))
        return realized, fingerprint, grid.trimmed_prefix

    # -- pré-condições, relatórios e MCS ------------------------------------------------

    def _preconditions(
        self, assembled: AssembledCohort
    ) -> tuple[dict[int, PairedLossSeries], dict[int, tuple[BlockEstimate, ...]]]:
        paired: dict[int, PairedLossSeries] = {}
        estimates: dict[int, tuple[BlockEstimate, ...]] = {}
        if assembled.alignment.findings:
            return paired, estimates
        for samples in assembled.horizons:
            if not models_suffice(samples.models):
                continue  # k < MIN_MODELS: a fábrica nunca é chamada (I11 i)
            series = paired_pinball_losses(
                {model: samples.common[model] for model in samples.models}
            )
            paired[samples.horizon] = series
            estimates[samples.horizon] = tuple(
                self._block_estimate(series, pair) for pair in series.model_pairs()
            )
        return paired, estimates

    def _block_estimate(self, series: PairedLossSeries, pair: tuple[str, str]) -> BlockEstimate:
        differential = series.differential(*pair)
        reason = block_request_defect(differential)
        if reason is not None:  # o backend nunca recebe entrada inválida (I11 ii)
            return BlockEstimate(
                pair=pair, value=None, reason=reason, detail=_DEFECT_DETAIL[reason]
            )
        try:
            value = self._mcs_backend.optimal_block_length(series=differential)
        except ArithmeticError as error:  # só este vira indefinido (I11 iii); o resto propaga
            return BlockEstimate(
                pair=pair,
                value=None,
                reason=UndefinedReason.BACKEND_ARITHMETIC,
                detail=f"{type(error).__name__}: {error}",
            )
        return BlockEstimate(pair=pair, value=value, reason=None, detail="")

    @staticmethod
    def _reports(
        assembled: AssembledCohort,
        paired: Mapping[int, PairedLossSeries],
        parameters: RefreshParameters,
    ) -> tuple[HorizonReport, ...]:
        return tuple(
            HorizonReports.evaluate(
                samples,
                paired=paired[samples.horizon],
                tolerance=parameters.degeneracy_tolerance,
                band_levels=parameters.band_levels,
                min_violations=parameters.min_violations,
                candidate=parameters.candidate,
                dm_alpha=parameters.dm_alpha,
                dm_variance_estimators=parameters.dm_variance_estimators,
            )
            for samples in assembled.horizons
        )

    def _mcs(
        self,
        paired: Mapping[int, PairedLossSeries],
        estimates: Mapping[int, tuple[BlockEstimate, ...]],
        parameters: RefreshParameters,
    ) -> tuple[McsReport, ...]:
        reports: list[McsReport] = []
        for horizon in sorted(paired):
            series = paired[horizon]
            block = ModelConfidenceSet.block_length(
                series,
                block_estimates={
                    e.pair: e.value for e in estimates[horizon] if e.value is not None
                },
            )
            for scheme in parameters.mcs_schemes:
                indices = self._mcs_backend.bootstrap_indices(
                    n_obs=series.n_points,
                    block_size=block,
                    reps=parameters.mcs_reps,
                    seed=parameters.mcs_seed,
                    scheme=scheme,
                )
                reports.append(
                    ModelConfidenceSet.evaluate(
                        series, bootstrap=indices, alpha=parameters.mcs_alpha
                    )
                )
        return tuple(reports)

    # -- manifesto -------------------------------------------------------------------

    def _manifest(  # noqa: PLR0913 — o que o manifesto registra (ADR 6.4.0005 item 8)
        self,
        *,
        command: RefreshGoldCommand,
        status: RefreshStatus,
        tables: Sequence[GoldTable],
        runs: Sequence[CohortRun],
        realized: RealizedReturns,
        fingerprint: DatasetContentFingerprint,
        grid_trimmed_prefix: int,
        started_at: datetime,
    ) -> GoldManifest:
        return GoldManifest(
            status=status,
            partition=command.partition,
            rows_by_table={table.name: len(table.rows) for table in tables},
            parameters=command.parameters,
            horizons=command.horizons,
            window_deficits=command.window_deficits,
            dataset_fingerprint=fingerprint,
            grid_trimmed_prefix=grid_trimmed_prefix,
            realized_sessions=realized.n_sessions,
            realized_returns_fsum=realized.returns_fsum,
            realized_first_timestamp=realized.first_timestamp,
            realized_last_timestamp=realized.last_timestamp,
            n_runs=len(runs),
            build_order=self._build_order,
            started_at=started_at,
            finished_at=self._clock.now(),
        )


def _record(row: Mapping[str, object], run: CohortRun) -> ForecastRecord:
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
