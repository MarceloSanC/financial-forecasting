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
   erros do dono propagam, C4) com o `DatasetContentFingerprint` que o PRÓPRIO dono
   calcula e devolve (issue #128) conferido contra o `command.dataset_fingerprint` —
   divergente → `GridFingerprintMismatchError` (C10),
   antes da montagem e de qualquer efeito;
4. `SeriesAssembly.assemble` (achados, nunca exceção — D1);
5. passo de pré-condições (I11): por horizonte, `models_suffice` antes da fábrica
   `paired_pinball_losses`; por par, `block_request_defect` antes do backend; do
   backend, **só** `ArithmeticError` vira `BlockEstimate` indefinido — o resto propaga
   (C7);
6. `QualityCheckRegistry` com os quatro checks (ADR `6_4_0002`) → bloqueado?;
7. se não bloqueado: `HorizonReports` por horizonte e o MCS por (horizonte, esquema)
   com o bloco da regra (`ModelConfidenceSet.block_length`) e `reps`/`seed` dos
   parâmetros (ADR `6_4_0006`); depois os perfis de séries novas (`ProfileReports`, Stage
   6.6) e, com as regras de perfil da revisão, o MCS por bloco de sensibilidade
   (`mcs_block_runs`) — falha de perfil vira unidade `error`, nunca aborta o refresh
   (ADR `6_6_0002` item 3); e, com o bloco `[conformal]` da revisão (Stage 7.2, ADR
   `7_2_0003` itens 4-5), a etapa `conformal`: `ConformalAssembly` → uma chamada ao
   port `ConformalCalibration` com as unidades `ok` → registros, coberturas por seed e
   médias entre seeds (`conformal_reports_from`) — unidade não-`ok` vira linha com o
   motivo e cada `error` soma em `conformal_error_units`; exceção do port propaga;
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
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    EMPTY_CONFORMAL_REPORTS,
    ConformalReports,
    ConformalTailRecord,
    ConformalUndefinedCoverage,
    ConformalUnitRecord,
    GoldInputs,
    GoldManifest,
    GoldPartition,
    GoldTable,
    McsBlockRun,
    RefreshGoldCommand,
    RefreshGoldResult,
    RefreshParameters,
    RefreshStatus,
    failed_checks_of,
    profile_settings_from,
)
from financial_forecasting.features.evaluation.application.ports.out.conformal_calibration import (
    ConformalCalibration,
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
from financial_forecasting.features.evaluation.domain.services.conformal_assembly import (
    ConformalAssembly,
    ConformalAssemblyResult,
    ConformalUnitAssembly,
)
from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    ConformalCoverage,
    ConformalCoverageReport,
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
    block_sensitivity_length,
)
from financial_forecasting.features.evaluation.domain.services.paired_pinball_losses import (
    paired_pinball_losses,
)
from financial_forecasting.features.evaluation.domain.services.profile_reports import (
    HorizonProfileReport,
    ProfileReports,
    UnitStatus,
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
from financial_forecasting.features.evaluation.domain.value_objects.conformal_coverage_series import (  # noqa: E501
    ConformalCoverageSeries,
    ConformalPairLimits,
)
from financial_forecasting.features.evaluation.domain.value_objects.conformal_parameters import (
    ConformalParameters,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
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
from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
    CalibrateConformalCommand,
    ConformalPointInput,
    ConformalUnitInput,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.application.ports.out.clock import Clock
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)

if TYPE_CHECKING:
    from financial_forecasting.features.inference.application.use_cases.calibrate_conformal import (
        ConformalUnitResult,
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

    def __init__(  # noqa: PLR0913 — 7 colaboradores (concept 6.4 §4 sem o Hasher, #128; 7.2)
        self,
        *,
        silver_reader: SilverTableReader,
        grid_reader: TrainingGridReader,
        clock: Clock,
        mcs_backend: McsBackend,
        gold_store: GoldStore,
        builders: Sequence[GoldBuilder],
        conformal_calibration: ConformalCalibration,
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
        self._clock = clock
        self._mcs_backend = mcs_backend
        self._gold_store = gold_store
        self._conformal_calibration = conformal_calibration
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
        profiles: tuple[HorizonProfileReport, ...] = ()
        blocks: tuple[McsBlockRun, ...] = ()
        conformal: ConformalReports = EMPTY_CONFORMAL_REPORTS
        conformal_errors = 0
        if not blocked:
            reports = _timed(
                "reports",
                len(assembled.horizons),
                lambda: self._reports(assembled, paired, parameters),
                len,
            )
            mcs = _timed("mcs", len(paired), lambda: self._mcs(paired, estimates, parameters), len)
            profiles = _timed(
                "profiles",
                len(reports),
                lambda: self._profiles(assembled, reports, paired, parameters),
                len,
            )
            blocks = _timed(
                "mcs_blocks",
                len(paired),
                lambda: mcs_block_runs(paired, parameters, self._mcs_backend),
                len,
            )
            if parameters.conformal_parameters is not None:
                conformal, conformal_errors = _timed(
                    "conformal",
                    len(records),
                    lambda: conformal_reports_from(
                        assembled=assembled,
                        records=records,
                        runs=runs,
                        realized=realized,
                        parameters=parameters,
                        port=self._conformal_calibration,
                    ),
                    lambda result: len(result[0].units),
                )
        inputs = GoldInputs(
            partition=partition,
            parameters=parameters,
            status=status,
            check_results=results,
            horizon_reports=reports,
            mcs_reports=mcs,
            block_estimates=estimates,
            profile_reports=profiles,
            mcs_block_reports=blocks,
            conformal_reports=conformal,
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
        error_units = sum(p.error_units for p in profiles) + sum(
            1 for b in blocks if b.status is UnitStatus.ERROR
        )
        logger.info(
            "refresh_gold status=%s partition=%s conformal_error_units=%d profile_error_units=%d",
            status.value,
            partition,
            conformal_errors,
            error_units,
        )
        return RefreshGoldResult(
            status=status,
            rows_by_table=rows_by_table,
            failed_checks=failed_checks_of(results),
            profile_error_units=error_units,
            conformal_error_units=conformal_errors,
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
        # o fingerprint vem do dono da grade (issue #128): aqui só se compara
        grid, fingerprint = self._grid_reader(asset_id=asset)
        timestamps = grid.timestamps_iso()
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

    @staticmethod
    def _profiles(
        assembled: AssembledCohort,
        reports: Sequence[HorizonReport],
        paired: Mapping[int, PairedLossSeries],
        parameters: RefreshParameters,
    ) -> tuple[HorizonProfileReport, ...]:
        settings = profile_settings_from(parameters)
        by_horizon = {report.horizon: report for report in reports}
        return tuple(
            ProfileReports.evaluate(
                samples,
                horizon_report=by_horizon[samples.horizon],
                paired=paired[samples.horizon],
                settings=settings,
            )
            for samples in assembled.horizons
        )

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


_SCHEME_INDEX: Final[Mapping[str, int]] = MappingProxyType({"primary_scheme": 0})
"""Regra do esquema do MCS por bloco (catálogo do `ProfileParameters`) → posição em
`mcs_schemes` (o primário vem primeiro: `refresh_command_from`)."""


def mcs_block_runs(
    paired: Mapping[int, PairedLossSeries],
    parameters: RefreshParameters,
    backend: McsBackend,
) -> tuple[McsBlockRun, ...]:
    """MCS com bloco l = h e l = ⌈√T⌉ no esquema primário (Stage 6.6; ADR 6.6.0002, D10).

    Só com as regras de perfil da revisão (`profile_parameters`; sem elas, nenhuma rodada
    — I9). O bloco sai do dono (`block_sensitivity_length`) e é passado ao backend; o
    esquema sai da regra `mcs_block_sensitivity_scheme` da revisão (`primary_scheme` →
    `mcs_schemes[0]`; regra fora do mapa → `KeyError`, bug de contrato). Só a
    chamada ao backend e ao `ModelConfidenceSet.evaluate` fica na captura: `ValueError`/
    `ArithmeticError` vira rodada `error` (I4) — a outra regra e o MCS primário seguem.
    """
    rules = parameters.profile_parameters
    if rules is None:
        return ()
    scheme = parameters.mcs_schemes[_SCHEME_INDEX[rules.mcs_block_sensitivity_scheme]]
    runs: list[McsBlockRun] = []
    for horizon in sorted(paired):
        series = paired[horizon]
        for rule in parameters.mcs_block_sensitivities:
            block = block_sensitivity_length(rule, horizon=horizon, n_points=series.n_points)
            try:
                indices = backend.bootstrap_indices(
                    n_obs=series.n_points,
                    block_size=block,
                    reps=parameters.mcs_reps,
                    seed=parameters.mcs_seed,
                    scheme=scheme,
                )
                report: McsReport | None = ModelConfidenceSet.evaluate(
                    series, bootstrap=indices, alpha=parameters.mcs_alpha
                )
                status, detail = UnitStatus.COMPUTED, ""
            except (ValueError, ArithmeticError) as error:
                report, status, detail = None, UnitStatus.ERROR, f"{type(error).__name__}: {error}"
            runs.append(
                McsBlockRun(
                    horizon=horizon,
                    block_rule=rule,
                    block_size=block,
                    scheme=scheme,
                    status=status,
                    detail=detail,
                    report=report,
                )
            )
    return tuple(runs)


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


# --- Stage 7.2: benchmark conformal (ADR 7.2.0003 itens 3-5) ----------------------------

_OK = "ok"
_UNDEFINED = "undefined"
_ERROR = "error"
_UnitKey = tuple[str, int, int]  # (fold_raw, seed, horizonte) de uma unidade ok (C4-8)
_PortKey = tuple[int, int, int]  # (fold, seed, horizonte) como o port os devolve


def _null_tail(tail: str, level: float) -> ConformalTailRecord:
    return ConformalTailRecord(
        tail=tail,
        level=level,
        n=None,
        rank=None,
        correction=None,
        infinite=None,
        beta_a=None,
        beta_b=None,
        beta_mean=None,
        beta_sd=None,
    )


def _tail_record(row: ConformalUnitResult, side: str) -> ConformalTailRecord:
    """A cauda `side` de uma linha `ok` do port (só o módulo do use case é importado)."""
    tail = row.lower if side == "lower" else row.upper
    beta = row.lower_beta if side == "lower" else row.upper_beta
    if tail is None:
        raise ValueError(f"an ok port row has no {side} tail: {row!r}")
    return ConformalTailRecord(
        tail=tail.tail,
        level=tail.level,
        n=tail.n,
        rank=tail.rank,
        correction=tail.correction,
        infinite=tail.infinite,
        beta_a=None if beta is None else beta.a,
        beta_b=None if beta is None else beta.b,
        beta_mean=None if beta is None else beta.mean,
        beta_sd=None if beta is None else beta.sd,
    )


def _port_record(row: ConformalUnitResult, fold_raw: str) -> ConformalUnitRecord:
    """O resultado do port em tipos do `evaluation` (o único mapeamento, ADR 7.2.0003)."""
    status = str(row.status)
    if status == _OK:
        tails = (_tail_record(row, "lower"), _tail_record(row, "upper"))
    else:
        tails = (_null_tail("lower", row.lower_level), _null_tail("upper", row.upper_level))
    return ConformalUnitRecord(
        fold_index=row.fold_index,
        fold_raw=fold_raw,
        seed=row.seed,
        horizon=row.horizon,
        lower_level=row.lower_level,
        upper_level=row.upper_level,
        variant=row.variant,
        rho=row.rho,
        status=status,
        reason=row.reason,
        tails=tails,
    )


def _assembly_records(
    unit: ConformalUnitAssembly, parameters: ConformalParameters, variants: tuple[str, ...]
) -> list[ConformalUnitRecord]:
    """Unidade `undefined` da montagem: um registro por par e variante do plano."""
    return [
        ConformalUnitRecord(
            fold_index=unit.fold_index,
            fold_raw=unit.fold_raw,
            seed=unit.seed,
            horizon=unit.horizon,
            lower_level=low,
            upper_level=high,
            variant=variant,
            rho=parameters.nexcp_rho if variant == parameters.sensitivity else None,
            status=_UNDEFINED,
            reason=unit.reason or "undefined in the assembly",
            tails=(_null_tail("lower", low), _null_tail("upper", high)),
        )
        for low, high in parameters.pairs
        for variant in variants
    ]


def _unit_input(key: _PortKey, unit: ConformalUnitAssembly) -> ConformalUnitInput:
    return ConformalUnitInput(
        fold_index=key[0],
        seed=key[1],
        horizon=key[2],
        calib=tuple(ConformalPointInput(d, t, grid, y) for d, t, grid, y in unit.calib),
        test=tuple(ConformalPointInput(d, t, grid, None) for d, t, grid in unit.test),
    )


def _limits_by_target(
    unit: ConformalUnitAssembly, row: ConformalUnitResult
) -> dict[str, tuple[float, float]]:
    """(L, U) por alvo de teste da unidade: o join é por `target_timestamp` (C3-8 b)."""
    if row.test_lower is None or row.test_upper is None:
        raise ValueError(f"an ok port row has no test limits: {row!r}")
    return {
        point[1]: (low, high)
        for point, low, high in zip(unit.test, row.test_lower, row.test_upper, strict=True)
    }


def conformal_reports_from(  # noqa: PLR0913 — as entradas da etapa conformal
    *,
    assembled: AssembledCohort,
    records: Sequence[ForecastRecord],
    runs: Sequence[CohortRun],
    realized: RealizedReturns,
    parameters: RefreshParameters,
    port: ConformalCalibration,
) -> tuple[ConformalReports, int]:
    """Montagem → uma chamada ao port com as unidades ok → registros, coberturas e médias.

    Devolve os relatórios e o número de unidades (fold, seed, h) distintas com alguma
    linha `error` do port (CA15; C4-6), não o de linhas. Uma (seed, h,
    variante) com qualquer unidade não-`ok` (da montagem ou do port), ou com alvo
    nativo sem unidade, vira cobertura `undefined` com o motivo; as completas são
    medidas pela `ConformalCoverage` sobre a série nativa, com os limites unidos por
    `target_timestamp`. Exceção do port propaga (erro de comando ou de programação).
    """
    block = parameters.conformal_parameters
    if block is None:
        raise ValueError("conformal_reports_from needs the [conformal] block")
    candidate = parameters.candidate
    variants = (block.variant_of_record, block.sensitivity)
    natives: dict[tuple[int, int], CoverageSeries] = {}
    for samples in assembled.horizons:
        for seed, series in zip(samples.seeds[candidate], samples.full[candidate], strict=True):
            if seed is not None:
                natives[(seed, samples.horizon)] = series
    levels = assembled.horizons[0].levels
    assembly = ConformalAssembly.assemble(
        records,
        runs,
        realized,
        natives,
        candidate=candidate,
        horizons=tuple(samples.horizon for samples in assembled.horizons),
        levels=levels,
    )
    ok_units: dict[_UnitKey, ConformalUnitAssembly] = {}
    inputs: list[ConformalUnitInput] = []
    raw_of: dict[_PortKey, str] = {}  # único: a montagem já recusou o inteiro repetido
    for unit in assembly.units:
        if unit.status == _OK and unit.fold_index is not None and unit.seed is not None:
            ok_units[(unit.fold_raw, unit.seed, unit.horizon)] = unit
            port_key = (unit.fold_index, unit.seed, unit.horizon)
            raw_of[port_key] = unit.fold_raw
            inputs.append(_unit_input(port_key, unit))
    rows: tuple[ConformalUnitResult, ...] = ()
    if inputs:
        command = CalibrateConformalCommand(
            units=tuple(inputs),
            pairs=block.pairs,
            variants=variants,
            nexcp_rho=block.nexcp_rho,
        )
        rows = port(command).units
    records_out: list[ConformalUnitRecord] = []
    for unit in assembly.units:
        if unit.status != _OK:
            records_out += _assembly_records(unit, block, variants)
    by_key: dict[tuple[_UnitKey, tuple[float, float], str], ConformalUnitResult] = {}
    for row in rows:
        raw = raw_of[(row.fold_index, row.seed, row.horizon)]
        key: _UnitKey = (raw, row.seed, row.horizon)
        records_out.append(_port_record(row, raw))
        by_key[(key, (row.lower_level, row.upper_level), row.variant)] = row
    errors = len(
        {(row.fold_index, row.seed, row.horizon) for row in rows if str(row.status) == _ERROR}
    )
    coverage, undefined = _coverages(
        assembly, ok_units, by_key, natives, block, variants, parameters
    )
    expected_seeds = tuple(sorted({seed for seed, _ in natives}))
    seed_means = tuple(
        ConformalCoverage.seed_mean(
            [r for r in coverage if (r.horizon, r.variant) == (samples.horizon, variant)],
            horizon=samples.horizon,
            variant=variant,
            expected_seeds=expected_seeds,
            band_levels=parameters.band_levels,
        )
        for samples in assembled.horizons
        for variant in variants
    )
    reports = ConformalReports(
        units=tuple(records_out),
        coverage=tuple(coverage),
        undefined_coverage=tuple(undefined),
        seed_means=seed_means,
    )
    return reports, errors


def _coverages(  # noqa: PLR0913 — o que a cobertura de cada (seed, h, variante) junta
    assembly: ConformalAssemblyResult,
    ok_units: Mapping[_UnitKey, ConformalUnitAssembly],
    by_key: Mapping[tuple[_UnitKey, tuple[float, float], str], ConformalUnitResult],
    natives: Mapping[tuple[int, int], CoverageSeries],
    block: ConformalParameters,
    variants: tuple[str, ...],
    parameters: RefreshParameters,
) -> tuple[list[ConformalCoverageReport], list[ConformalUndefinedCoverage]]:
    coverage: list[ConformalCoverageReport] = []
    undefined: list[ConformalUndefinedCoverage] = []
    for (seed, horizon), native in sorted(natives.items()):
        units = [u for u in assembly.units if (u.seed, u.horizon) == (seed, horizon)]
        not_ok = [u for u in units if u.status != _OK]
        ok_here = {k: u for k, u in ok_units.items() if (k[1], k[2]) == (seed, horizon)}
        uncovered = assembly.uncovered_targets.get((seed, horizon), ())
        for variant in variants:
            reason = _undefined_reason(not_ok, uncovered, ok_here, by_key, block, variant)
            if reason is not None:
                undefined.append(
                    ConformalUndefinedCoverage(
                        seed=seed,
                        horizon=horizon,
                        variant=variant,
                        reason=reason,
                        n_points=native.n_points,
                    )
                )
                continue
            limits = []
            for pair in block.pairs:
                joined: dict[str, tuple[float, float]] = {}
                for key, unit in ok_here.items():
                    joined.update(_limits_by_target(unit, by_key[(key, pair, variant)]))
                limits.append(
                    ConformalPairLimits(
                        pair[0],
                        pair[1],
                        tuple(joined[t][0] for t in native.target_timestamps),
                        tuple(joined[t][1] for t in native.target_timestamps),
                    )
                )
            coverage.append(
                ConformalCoverage.evaluate(
                    ConformalCoverageSeries(
                        seed=seed, native=native, variant=variant, pairs=tuple(limits)
                    ),
                    tolerance=parameters.degeneracy_tolerance,
                    band_levels=parameters.band_levels,
                )
            )
    return coverage, undefined


def _undefined_reason(  # noqa: PLR0913 — os motivos possíveis, na ordem
    not_ok: Sequence[ConformalUnitAssembly],
    uncovered: tuple[str, ...],
    ok_here: Mapping[_UnitKey, ConformalUnitAssembly],
    by_key: Mapping[tuple[_UnitKey, tuple[float, float], str], ConformalUnitResult],
    block: ConformalParameters,
    variant: str,
) -> str | None:
    """O motivo de a (seed, h, variante) não ter cobertura, ou `None` se está completa."""
    if not_ok:
        first = not_ok[0]
        return f"assembly unit fold {first.fold_raw!r}: {first.reason}"
    if uncovered:
        return f"native targets without a unit: {list(uncovered)}"
    for key, unit in ok_here.items():
        for pair in block.pairs:
            row = by_key.get((key, pair, variant))
            if row is None:
                return f"unit fold {unit.fold_raw!r} pair {list(pair)}: no port result"
            if str(row.status) != _OK:
                return f"unit fold {unit.fold_raw!r} pair {list(pair)}: {row.status}: {row.reason}"
    return None
