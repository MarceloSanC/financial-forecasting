"""DTOs do scorecard confirmatório (Stage 6.5) — derivação do comando, comando e erros.

DTOs de aplicação **frozen** (concept 6.5 §4 "Application", D4, I6, C3-C8; ADRs
`6_5_0004` itens 3, 5, `6_5_0007`):

- `refresh_command_from(prereg, reference)` — a **única** derivação do
  `RefreshGoldCommand` a partir do plano (ADR 6.5.0004 item 3): a 8.1 refresca o gold
  com ele e o scorecard confere o gold contra ele;
- `BuildConfirmatoryScorecardCommand` — o pedido do scorecard, **sem** partição (a
  partição é a do plano);
- `MismatchField` — os nomes fixos do campo de um `PreregistrationMismatchError`;
- os cinco erros do scorecard. Moram aqui (e não no módulo do use case, como o concept
  §4 escreve) porque o mapeador `use_cases/scorecard_evidence.py` ergue o de C8 e é
  importado pelo use case — defini-los no use case criaria ciclo (technical 6.5 §1;
  `[deviation]` no §7). O use case os importa daqui, sem reexportação.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import StrEnum

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    FailedCheck,
    GoldManifest,
    RefreshGoldCommand,
    RefreshParameters,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationAnchor,
)
from financial_forecasting.features.evaluation.domain.services.confirmatory_scorecard import (
    ScorecardVerdict,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.application.exceptions import ApplicationError


def refresh_command_from(prereg: Preregistration, reference: str) -> RefreshGoldCommand:
    """O `RefreshGoldCommand` inteiro do plano — derivação única (ADR 6.5.0004 item 3).

    `asset` e `horizons` do plano; `parent_sweep_id` = o `cohort_id` referenciado;
    `window_deficits` e `dataset_fingerprint` (do realizado) do plano; os
    `RefreshParameters` com `preregistration_ref = reference`, as bandas do gate e do
    perfil ordenadas, e o primário seguido das sensibilidades no DM e no MCS; e, da
    Stage 6.6 (F8a), o `draws`/`seed` do Monte Carlo, as sensibilidades de bloco do MCS e
    o bloco de regras de perfil da revisão (`None` no r0).
    """
    gate = prereg.h1_gate
    parameters = RefreshParameters(
        preregistration_ref=reference,
        degeneracy_tolerance=gate.degeneracy_tolerance,
        band_levels=tuple(sorted({gate.gate_band_level, gate.profile_band_level})),
        min_violations=prereg.min_violations,
        candidate=prereg.candidate,
        dm_alpha=prereg.dm.alpha,
        dm_variance_estimators=(prereg.dm.primary_estimator, *prereg.dm.sensitivity_estimators),
        mcs_alpha=prereg.mcs.alpha,
        mcs_reps=prereg.mcs.reps,
        mcs_seed=prereg.mcs.seed,
        mcs_schemes=(prereg.mcs.primary_scheme, *prereg.mcs.sensitivity_schemes),
        monte_carlo_draws=prereg.monte_carlo.draws,
        monte_carlo_seed=prereg.monte_carlo.seed,
        mcs_block_sensitivities=prereg.mcs.block_sensitivities,
        profile_parameters=prereg.profile_parameters,
    )
    return RefreshGoldCommand(
        asset=prereg.asset,
        parent_sweep_id=prereg.cohort.cohort_id,
        horizons=prereg.horizons,
        window_deficits=dict(prereg.window_deficits),
        parameters=parameters,
        dataset_fingerprint=prereg.realized.dataset_fingerprint,
    )


@dataclass(frozen=True, kw_only=True)
class BuildConfirmatoryScorecardCommand:
    """O pedido do scorecard: a revisão julgada e a referência esperada (sem partição).

    Raises:
        ValueError: `name` ou `preregistration_ref` vazios; `revision` não-`int`,
            `bool` ou negativa.
    """

    name: str
    revision: int
    preregistration_ref: str

    def __post_init__(self) -> None:
        """Forma dos três campos."""
        for field in ("name", "preregistration_ref"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field} must be a non-empty str, got {value!r}")
        revision = self.revision
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError(f"revision must be an int >= 0, got {revision!r}")


class MismatchField(StrEnum):
    """Campo nomeado por um `PreregistrationMismatchError` (technical 6.5 Task 08)."""

    PARTITION = "partition"
    PREREGISTRATION_REF = "preregistration_ref"
    PARAMETERS = "parameters"
    HORIZONS = "horizons"
    WINDOW_DEFICITS = "window_deficits"
    DATASET_FINGERPRINT = "dataset_fingerprint"
    MODELS = "models"
    SEEDS = "seeds"
    QUANTILE_LEVELS = "quantile_levels"
    MCS_STATISTIC = "mcs.statistic"
    MCS_BLOCK_RULE = "mcs.block_rule"


class PreregistrationHashMismatchError(ApplicationError):
    """A referência calculada da revisão ≠ a do comando (C3), antes de ler o gold."""


class PreregistrationChainError(ApplicationError):
    """A cadeia de revisões está quebrada (C4; ADR 6.5.0002)."""


class PreregistrationNotAnchoredError(ApplicationError):
    """Uma revisão da cadeia não tem âncora (C5; ADR 6.5.0003)."""


class PreregistrationMismatchError(ApplicationError):
    """O gold é de outro plano ou de outro cohort (C8), nomeando o campo."""

    def __init__(self, field: MismatchField, detail: str) -> None:
        """`field`: o campo divergente; `detail`: o que divergiu."""
        super().__init__(f"the gold does not match the preregistration at {field.value}: {detail}")
        self.field = field


class GoldNotReadyError(ApplicationError):
    """O gold lido é `BLOCKED` (C7): leva os checks que bloquearam."""

    def __init__(self, failed_checks: tuple[FailedCheck, ...]) -> None:
        """`failed_checks`: as linhas `ERROR` + `FAIL` de `gold_quality_checks`."""
        names = sorted({check.check for check in failed_checks})
        super().__init__(f"the gold generation is BLOCKED by the checks {names}")
        self.failed_checks = failed_checks


# --- perfil do scorecard (Task 09; ADR 6.5.0008 item 2) --------------------------------


def to_jsonable(value: object) -> object:
    """Forma JSON-safe única dos DTOs do scorecard (dataclass → dict, enum → valor,
    tupla → lista, datetime → ISO)."""
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class GateSensitivitiesProfile:
    """Sensibilidades do gate H1 copiadas do `H1Result` (nunca veredito)."""

    lr_uc_statistic: float | None
    lr_uc_p_value: float | None
    lr_uc_rejected: bool | None
    dgt_band_level: float | None
    dgt_passed: bool | None
    common_sample_passed: bool | None
    mean_of_seed_rates: tuple[float | None, float | None]
    divergences: tuple[str, ...]


@dataclass(frozen=True)
class PowerProfile:
    """Probabilidade de reprovar o gate sob um cenário pré-registrado."""

    label: str
    role: str
    n: int
    failure_probability: float
    assumes_independence: bool


@dataclass(frozen=True)
class TierProfile:
    """Desfecho de um nível de comparadores (ADR 6.5.0007 item 5)."""

    tier: str
    members: tuple[str, ...]
    holm_rejects_all: bool
    candidate_in_mcs: bool
    beats_or_ties: bool
    ties_in_mcs: bool


@dataclass(frozen=True)
class DmProfileRow:
    """Uma linha do DM copiada do gold, com o IC do efeito a 95 % (`None` se S = 0)."""

    comparator: str
    estimator: str
    n_points: int
    mean_differential: float
    statistic: float
    adjusted_p_value: float
    rejected: bool
    fallback_applied: bool
    effect_interval: tuple[float, float] | None


@dataclass(frozen=True)
class ComparatorCalibrationProfile:
    """Calibração de um comparador no par do gate (S = 1) — informação, nunca filtro."""

    model: str
    lower_contains_nominal: bool | None
    upper_contains_nominal: bool | None
    mean_degeneracy_rate: float
    degeneracy_above_threshold: bool


@dataclass(frozen=True)
class CalibrationSeriesProfile:
    """Uma série da calibração no nível de banda do perfil (médias e frações entre seeds)."""

    model: str
    sample: str
    kind: str
    level_low: float
    level_high: float | None
    includes_degenerate: bool
    dgt_offset: int | None
    dgt_step: int | None
    n_seeds: int
    mean_violations: float
    mean_observed: float
    fraction_contains_nominal: float | None
    fraction_ind_rejected: float | None
    fraction_cc_rejected: float | None
    n_independence_not_applicable: int


@dataclass(frozen=True)
class TailSummaryProfile:
    """Uma cauda do gate na variante com as degeneradas ("sem lacunas" não aplicado)."""

    kind: str
    level: float
    mean_violations: float
    mean_observed: float


@dataclass(frozen=True)
class DescriptorProfile:
    """Um descritor de `gold_metrics_by_run`: média, mínimo e máximo entre seeds."""

    model: str
    sample: str
    metric: str
    level_low: float | None
    level_high: float | None
    mean: float
    minimum: float
    maximum: float
    n_seeds: int


# --- perfis de séries novas (Stage 6.6; ADR 6.6.0002 — nunca lidos pelo veredito) -------


class ProfileState(StrEnum):
    """Estado de um perfil declarado no scorecard (concept 6.6 §4, I9)."""

    BUILT = "built"
    NOT_FROZEN_IN_REVISION = "not_frozen_in_revision"  # a revisão não congela a regra
    NOT_BUILT_HERE = "not_built_here"  # construído fora do scorecard (8.3)


@dataclass(frozen=True)
class DmSubsetProfileRow:
    """Um recorte do DM (fold, seed ou τ) de `gold_dm_profiles` — descritivo, p bruto."""

    dimension: str
    fold: str | None
    seed: int | None
    level: float | None
    comparator: str
    status: str
    undefined_reason: str | None
    detail: str
    n_points: int | None
    first_target_timestamp: str | None
    last_target_timestamp: str | None
    variance_estimator: str
    mean_differential: float | None
    statistic: float | None
    p_value: float | None
    rejected: bool | None
    fallback_applied: bool | None
    horizon_used: int | None
    alpha: float


@dataclass(frozen=True)
class SeedFractionProfileRow:
    """Fração de seeds do candidato que rejeitam contra um comparador (`gold_dm_seed_fraction`)."""

    comparator: str
    n_seeds: int
    n_rejecting: int
    n_undefined: int
    fraction_rejecting: float | None
    alpha: float


@dataclass(frozen=True)
class McsBlockProfileRow:
    """Uma linha do MCS com bloco l = h ou l = ceil(sqrt(T)) (`gold_mcs_block_sensitivity`).

    Rodada com erro: uma linha com `model` nulo e as colunas do MCS nulas.
    """

    block_rule: str
    model: str | None
    status: str
    undefined_reason: str | None
    detail: str
    scheme: str
    block_size: int
    elimination_rank: int | None
    step_p_value: float | None
    mcs_p_value: float | None
    included: bool | None
    alpha: float | None
    reps: int | None
    seed: int | None
    n_points: int | None


@dataclass(frozen=True)
class MonteCarloProfileRow:
    """p-valores Monte Carlo de Christoffersen de uma sequência de hits (h = 1)."""

    model: str
    seed: int | None
    sample: str
    kind: str
    level_low: float
    level_high: float | None
    includes_degenerate: bool
    status: str
    detail: str
    uc_status: str | None
    ind_status: str | None
    mc_p_uc: float | None
    mc_p_ind: float | None
    mc_p_cc: float | None
    draws: int
    mc_seed: int
    attempts: int | None


@dataclass(frozen=True)
class PartialDegeneracyProfileRow:
    """Colapso parcial de um par de níveis (simétrico ou adjacente) de uma série."""

    model: str
    seed: int | None
    sample: str
    pair_kind: str
    level_low: float | None
    level_high: float | None
    status: str
    detail: str
    collapse_rate: float | None
    tolerance: float


@dataclass(frozen=True)
class StationarityProfileRow:
    """Diagnóstico de d_t de um par: CUSUM (`gold_differential_breaks`) e ACF por lag."""

    model_a: str
    model_b: str
    status: str
    undefined_reason: str | None
    detail: str
    statistic: float | None
    p_value: float | None
    rejected: bool | None
    alpha: float
    horizon_used: int | None
    break_target_timestamp: str | None
    n_points: int | None
    max_lag: int | None
    acf: tuple[float, ...]


@dataclass(frozen=True, kw_only=True)
class HorizonProfile:
    """O perfil de um horizonte (ADR 6.5.0008 item 2) — nunca lido pelo veredito (I12)."""

    horizon: int
    gate_sensitivities: GateSensitivitiesProfile
    power: tuple[PowerProfile, ...]
    tiers: tuple[TierProfile, ...]
    dm: tuple[DmProfileRow, ...]
    bartlett_divergences: tuple[str, ...]
    mcs_moving_block_divergence: bool
    comparators_calibration: tuple[ComparatorCalibrationProfile, ...]
    calibration_95: tuple[CalibrationSeriesProfile, ...]
    without_gaps: tuple[TailSummaryProfile, ...]
    descriptors: tuple[DescriptorProfile, ...]
    lowest_mean_pinball: bool
    dm_subsets: tuple[DmSubsetProfileRow, ...]
    dm_seed_fractions: tuple[SeedFractionProfileRow, ...]
    mcs_block_sensitivity: tuple[McsBlockProfileRow, ...]
    monte_carlo: tuple[MonteCarloProfileRow, ...]
    partial_degeneracy: tuple[PartialDegeneracyProfileRow, ...]
    stationarity: tuple[StationarityProfileRow, ...]


@dataclass(frozen=True)
class ScorecardProfile:
    """O perfil do scorecard: por horizonte, o estado de cada perfil declarado e os não
    construídos aqui (`declared_not_built` = os `not_built_here`)."""

    horizons: tuple[HorizonProfile, ...]
    declared_not_built: tuple[str, ...]
    profile_states: tuple[tuple[str, ProfileState], ...]

    def __post_init__(self) -> None:
        """`declared_not_built` é derivado de `profile_states` (os `not_built_here`)."""
        derived = tuple(p for p, s in self.profile_states if s is ProfileState.NOT_BUILT_HERE)
        if self.declared_not_built != derived:
            raise ValueError(
                f"declared_not_built {self.declared_not_built} != the not_built_here "
                f"profiles {derived}"
            )

    def as_mapping(self) -> dict[str, object]:
        """Serialização JSON-safe única."""
        return {f.name: to_jsonable(getattr(self, f.name)) for f in fields(self)}


# --- resultado do scorecard (Task 10; ADR 6.5.0007 item 8) ----------------------------


class ReadinessReason(StrEnum):
    """Por que o scorecard não está pronto para decisão acadêmica (C10)."""

    REQUIRED_CHECK_SKIPPED = "required_check_skipped"
    GOLD_BEFORE_ANCHOR = "gold_before_anchor"
    AMENDED_AFTER_UNBLINDING = "amended_after_unblinding"


@dataclass(frozen=True, kw_only=True)
class ScorecardResult:
    """O scorecard confirmatório de uma revisão julgada (concept 6.5 §4).

    `academic_decision_ready` conjuga só os gates de validade (nunca o desfecho de H1/H2
    nem a declaração de cegamento); cada conjunto falso é uma razão nomeada (I13).
    """

    preregistration_ref: str
    revision_chain: tuple[str, ...]
    anchor: PreregistrationAnchor
    blinding_statement: str | None
    manifest_read: GoldManifest
    verdict: ScorecardVerdict
    profile: ScorecardProfile
    academic_decision_ready: bool
    readiness_reasons: tuple[ReadinessReason, ...]

    def as_mapping(self) -> dict[str, object]:
        """Serialização única, JSON-safe (datetimes ISO, enums pelo valor)."""
        mapping = {f.name: to_jsonable(getattr(self, f.name)) for f in fields(self)}
        mapping["manifest_read"] = self.manifest_read.as_mapping()
        mapping["profile"] = self.profile.as_mapping()
        return mapping
