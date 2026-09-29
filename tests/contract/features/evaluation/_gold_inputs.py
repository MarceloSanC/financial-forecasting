"""`GoldInputs` de teste para a suíte de contrato do `GoldBuilder` (Stage 6.4 Task 09).

Módulo privado (sem `test_`, importado absolutamente). Monta os insumos dos builders
**só com o domínio** + `FakeMcsBackend`, a partir de um cohort sintético pequeno
(`make_cohort` do `gold/conftest.py`): 2 horizontes, candidato `tft` com 2 seeds, `gbm`
e um baseline pontual `naive` (grade toda igual em todo ponto — 100 % degenerado).

- `completed_inputs()`: montagem sem achado → checks → `HorizonReports` por horizonte →
  b̂_sb por par (`FakeMcsBackend`) → MCS por (horizonte, esquema) → `COMPLETED`;
- `blocked_inputs()`: o mesmo cohort com um ponto interno removido (achado
  `interior_gap`) → checks → `BLOCKED`, sem relatórios.

É a mesma sequência que o use case `RefreshGold` (Task 11) orquestra; aqui só para
produzir entradas realistas e coerentes para o mapeamento dos builders.
"""

from __future__ import annotations

import dataclasses
from functools import cache

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldPartition,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
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
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)
from financial_forecasting.shared.domain.value_objects.dataset_fingerprint import (
    DatasetFingerprint,
)
from tests.fakes.features.evaluation.fake_mcs_backend import FakeMcsBackend
from tests.unit.features.evaluation.gold.conftest import (
    Cohort,
    at_point,
    drop_records,
    make_cohort,
    replace_records,
    targets_of,
)

PREREGISTRATION_REF = "prereg-test-0001"  # literal declarado até a 6.5 fornecer o hash
PARTITION = GoldPartition("AAPL", "sweep-01")
HORIZONS = (1, 2)
SEEDS = {"gbm": (None,), "naive": (None,), "tft": (1, 2)}
PARAMETERS = RefreshParameters(
    preregistration_ref=PREREGISTRATION_REF,
    degeneracy_tolerance=1e-9,
    band_levels=(0.95, 0.975),
    min_violations=5,
    candidate="tft",
    dm_alpha=0.05,
    dm_variance_estimators=(DmVarianceEstimator.RECTANGULAR, DmVarianceEstimator.BARTLETT),
    mcs_alpha=0.10,
    mcs_reps=1000,
    mcs_seed=20260929,
    mcs_schemes=(BootstrapScheme.STATIONARY, BootstrapScheme.MOVING_BLOCK),
)
FINGERPRINT = DatasetFingerprint(value="e3" * 32)
_BLOCK_LENGTH = 2.5
_POINT_FORECAST = 0.001


def _cohort() -> Cohort:
    cohort = make_cohort(seeds=SEEDS, horizons=HORIZONS)
    return replace_records(
        cohort,
        lambda r: r.model == "naive",
        lambda r: dataclasses.replace(
            r, value_raw=_POINT_FORECAST, value_guardrail=_POINT_FORECAST
        ),
    )


def _assemble(cohort: Cohort) -> AssembledCohort:
    return SeriesAssembly.assemble(
        cohort.records,
        cohort.runs,
        cohort.realized,
        horizons=HORIZONS,
        window_deficits={},
        required_models=frozenset({PARAMETERS.candidate}),
    )


def _registry() -> QualityCheckRegistry:
    return QualityCheckRegistry(
        [
            AlignmentCheck(),
            StatisticalPreconditionsCheck(),
            DegeneracyCheck(),
            RealizedProvenanceCheck(),
        ]
    )


def _estimates(series: PairedLossSeries, backend: FakeMcsBackend) -> tuple[BlockEstimate, ...]:
    estimates = []
    for first, second in series.model_pairs():
        differential = series.differential(first, second)
        reason = block_request_defect(differential)
        if reason is None:
            value = backend.optimal_block_length(series=differential)
            estimates.append(
                BlockEstimate(pair=(first, second), value=value, reason=None, detail="")
            )
        else:
            estimates.append(
                BlockEstimate(pair=(first, second), value=None, reason=reason, detail=reason.value)
            )
    return tuple(estimates)


@cache
def completed_inputs() -> GoldInputs:
    """`GoldInputs` de um refresh `COMPLETED` (sem achado, pré-condições ok)."""
    cohort = _cohort()
    assembled = _assemble(cohort)
    assert assembled.alignment.findings == (), assembled.alignment.findings
    backend = FakeMcsBackend(block_length=_BLOCK_LENGTH)
    paired = {
        samples.horizon: paired_pinball_losses(
            {model: samples.common[model] for model in samples.models}
        )
        for samples in assembled.horizons
    }
    estimates = {h: _estimates(series, backend) for h, series in paired.items()}
    context = QualityCheckContext(
        assembled=assembled,
        paired=paired,
        block_estimates=estimates,
        tolerance=PARAMETERS.degeneracy_tolerance,
        dataset_fingerprint=FINGERPRINT,
        realized=cohort.realized,
    )
    results = _registry().run(context)
    assert not QualityCheckRegistry.is_blocking(results), results
    reports = tuple(
        HorizonReports.evaluate(
            samples,
            paired=paired[samples.horizon],
            tolerance=PARAMETERS.degeneracy_tolerance,
            band_levels=PARAMETERS.band_levels,
            min_violations=PARAMETERS.min_violations,
            candidate=PARAMETERS.candidate,
            dm_alpha=PARAMETERS.dm_alpha,
            dm_variance_estimators=PARAMETERS.dm_variance_estimators,
        )
        for samples in assembled.horizons
    )
    mcs: list[McsReport] = []
    for horizon, series in paired.items():
        block = ModelConfidenceSet.block_length(
            series,
            block_estimates={e.pair: e.value for e in estimates[horizon] if e.value is not None},
        )
        for scheme in PARAMETERS.mcs_schemes:
            indices = backend.bootstrap_indices(
                n_obs=series.n_points,
                block_size=block,
                reps=PARAMETERS.mcs_reps,
                seed=PARAMETERS.mcs_seed,
                scheme=scheme,
            )
            mcs.append(
                ModelConfidenceSet.evaluate(series, bootstrap=indices, alpha=PARAMETERS.mcs_alpha)
            )
    return GoldInputs(
        partition=PARTITION,
        parameters=PARAMETERS,
        status=RefreshStatus.COMPLETED,
        check_results=results,
        horizon_reports=reports,
        mcs_reports=tuple(mcs),
        block_estimates=estimates,
    )


@cache
def blocked_inputs() -> GoldInputs:
    """`GoldInputs` de um refresh `BLOCKED` (achado de alinhamento, sem relatórios)."""
    cohort = _cohort()
    gap = targets_of(cohort, "tft", 1, 1)[10]
    cohort = drop_records(cohort, at_point("tft", 1, 1, gap))
    assembled = _assemble(cohort)
    context = QualityCheckContext(
        assembled=assembled,
        paired={},
        block_estimates={},
        tolerance=PARAMETERS.degeneracy_tolerance,
        dataset_fingerprint=FINGERPRINT,
        realized=cohort.realized,
    )
    results = _registry().run(context)
    assert QualityCheckRegistry.is_blocking(results), results
    return GoldInputs(
        partition=PARTITION,
        parameters=PARAMETERS,
        status=RefreshStatus.BLOCKED,
        check_results=results,
        horizon_reports=(),
        mcs_reports=(),
        block_estimates={},
    )
