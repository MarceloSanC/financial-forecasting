"""DTO `CohortSpec` — especificação congelável do cohort confirmatório (Stage 5.5).

Espelho, em memória, do arquivo `config/cohorts/<nome>.toml`: declara tudo o que
define a corrida confirmatória — ativo, feature set (nome e hash), versão do
pipeline, horizontes, grade de quantis, geometria walk-forward, device, seeds do
candidato, plano dos sweeps exploratórios, hiperparâmetros congelados do TFT e do
GBM, specs das baselines, proveniência dos sweeps e a impressão digital do dado.

Vive em `application/dtos` porque carrega `TftTrainingParams`/`GbmTrainingParams`
e `SearchDimension`, que são tipos dos ports de saída do slice (LAYOUT §3: o
domínio não os vê).

**Identidade (ADR 5.5.0001):** `hash_payload()` é o payload canônico do spec
INTEIRO — mudar qualquer campo muda o hash —, exceto a `seed` dentro de
`tft_params`, que é por unidade (cada seed do TFT roda com a sua) e não pode
fazer duas declarações iguais parecerem diferentes. O hash em si é calculado por
`CohortHash.compute` (regra 6 do `check_layout`: `hash_mapping` só em VOs de
shared); este DTO recebe o hash pronto para derivar `cohort_id` e o scope id
dos sweeps.

**Rascunho e congelado:** o rascunho (antes dos sweeps e das decisões [P]) tem
`n_trials` e `seeds` possivelmente vazios e nenhum campo de congelamento;
`is_frozen()` exige todos. `draft_payload()` é o payload SEM os campos de
congelamento — é o que identifica os sweeps (`exploratory_scope_id`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    validate_dimension_names,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import ScopeSpec
from financial_forecasting.shared.domain.value_objects.asset_id import AssetId

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (  # noqa: E501
        SearchDimension,
    )
    from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
        BaselineSpec,
    )
    from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
        CohortGeometry,
    )
    from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash

_HASH_PREFIX = 12
_FREEZE_FIELDS = ("tft_params", "gbm_params", "provenance", "dataset_fingerprint", "seeds")


def _numbers_by_value(value: Any) -> Any:  # noqa: ANN401 — percorre o payload do asdict
    """Troca float inteiro por int, recursivamente (bool e não finitos intactos)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _numbers_by_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_numbers_by_value(item) for item in value]
    return value


@dataclass(frozen=True)
class SweepPlan:
    """Plano dos dois sweeps exploratórios (mesmo orçamento — D13)."""

    tft_space: tuple[SearchDimension, ...]
    tft_base_params: TftTrainingParams
    gbm_space: tuple[SearchDimension, ...]
    gbm_base_params: GbmTrainingParams
    n_trials: int | None  # [P] — nulo no rascunho, decidido após a medição de custo
    sampler_seed: int

    def __post_init__(self) -> None:
        if not self.tft_space or not self.gbm_space:
            raise ValueError("SweepPlan needs a non-empty space for both sweeps")
        if self.n_trials is not None and self.n_trials < 1:
            raise ValueError(f"SweepPlan.n_trials must be >= 1 when set; got {self.n_trials}")
        # Erro na borda (carga do arquivo do cohort), não só quando o sweep roda.
        validate_dimension_names(self.tft_space, TftTrainingParams)
        validate_dimension_names(self.gbm_space, GbmTrainingParams)


@dataclass(frozen=True)
class SweepProvenance:
    """O que os sweeps produziram e congelaram — o único insumo vindo de treino (I10)."""

    tft_study_id: str
    tft_best_trial: int
    tft_best_objective: float
    gbm_study_id: str
    gbm_best_trial: int
    gbm_best_objective: float
    dataset_fingerprint: str  # dado sobre o qual os DOIS sweeps rodaram


@dataclass(frozen=True)
class CohortSpec:
    """Especificação do cohort confirmatório (concept §4; ADR 5.5.0001)."""

    name: str
    revision: int
    asset_id: str
    feature_set_name: str
    feature_set_hash: str
    pipeline_version: str
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    geometry: CohortGeometry
    device: str
    seeds: tuple[int, ...]
    sweep: SweepPlan
    tft_params: TftTrainingParams | None
    gbm_params: GbmTrainingParams | None
    baseline_specs: tuple[BaselineSpec, ...]
    provenance: SweepProvenance | None
    dataset_fingerprint: str | None

    def __post_init__(self) -> None:
        """Validações de forma; a coerência declarado/observado é do `run` (I4)."""
        for field_name in (
            "name",
            "asset_id",
            "feature_set_name",
            "feature_set_hash",
            "pipeline_version",
            "device",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"CohortSpec.{field_name} must be non-empty")
        # identidade canônica ESTRITA (#69 c): a ingestão grava `asset=<canônico>` e o
        # `BuildDataset` lê com o texto da spec; recusar (e não normalizar) mantém o
        # `cohort_hash` do que foi declarado — o "AAPL" congelado segue válido
        try:
            AssetId(self.asset_id)
        except ValueError as exc:
            raise ValueError(f"CohortSpec.asset_id: {exc}") from exc
        if self.revision < 0:
            raise ValueError(f"CohortSpec.revision must be >= 0; got {self.revision}")
        if (
            not self.horizons
            or any(h < 1 for h in self.horizons)
            or any(b <= a for a, b in pairwise(self.horizons))
        ):
            raise ValueError(
                f"CohortSpec.horizons must be positive and strictly increasing; got {self.horizons}"
            )
        levels = self.quantile_levels
        if (
            not levels
            or any(not 0.0 < tau < 1.0 for tau in levels)
            or any(b <= a for a, b in pairwise(levels))
        ):
            raise ValueError(
                "CohortSpec.quantile_levels must be in (0, 1) and strictly increasing; "
                f"got {levels}"
            )
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError(f"CohortSpec.seeds must be unique; got {self.seeds}")
        if not self.baseline_specs:
            raise ValueError("CohortSpec.baseline_specs must be non-empty")
        families = [spec.family for spec in self.baseline_specs]
        if len(set(families)) != len(families):
            # Mesma família duas vezes grava sob o mesmo `model_version`: a
            # contagem por modelo (corrida e `verify`) deixaria de fechar.
            raise ValueError(f"CohortSpec.baseline_specs repeats a family: {families}")

    @property
    def max_horizon(self) -> int:
        return max(self.horizons)

    def is_frozen(self) -> bool:
        """Congelado = sweeps decididos e rodados, seeds decididas, dado fixado (I1)."""
        return (
            self.sweep.n_trials is not None
            and bool(self.seeds)
            and self.tft_params is not None
            and self.gbm_params is not None
            and self.provenance is not None
            and self.dataset_fingerprint is not None
        )

    def hash_payload(self) -> dict[str, object]:
        """Payload canônico do spec inteiro (sem a seed por unidade do TFT).

        Números entram pelo VALOR: float inteiro (`8.0`) vira `8`. Sem isso, dois
        specs iguais pela igualdade do dataclass (`8 == 8.0`) — um montado em
        memória, outro lido do arquivo, que coere para o tipo declarado — teriam
        hashes diferentes.
        """
        payload = asdict(self)
        tft = payload.get("tft_params")
        if isinstance(tft, dict):
            tft.pop("seed", None)
        canonical: dict[str, object] = _numbers_by_value(payload)
        return canonical

    def draft_payload(self) -> dict[str, object]:
        """Payload sem os campos de congelamento — identifica os sweeps."""
        payload = self.hash_payload()
        for field_name in _FREEZE_FIELDS:
            payload.pop(field_name, None)
        return payload

    def cohort_id(self, cohort_hash: CohortHash) -> str:
        """`<nome>-r<revisão>-<12 hex do hash>` — vai no `parent_sweep_id` (I3)."""
        return f"{self.name}-r{self.revision}-{cohort_hash.value[:_HASH_PREFIX]}"

    def exploratory_scope_id(self, draft_hash: CohortHash) -> str:
        """Scope id dos sweeps, calculado sobre o rascunho (antes do congelamento)."""
        return f"{self.name}-r{self.revision}-sweep-{draft_hash.value[:_HASH_PREFIX]}"

    def scope(self, cohort_id: str) -> ScopeSpec:
        """`ScopeSpec` das unidades: `max_horizon = max(horizons)` (I3)."""
        return ScopeSpec(
            asset_id=self.asset_id,
            feature_set_name=self.feature_set_name,
            max_horizon=self.max_horizon,
            cohort_id=cohort_id,
        )
