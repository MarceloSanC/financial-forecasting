"""VOs `AblationRunPart`/`AblationRunLosses` e `merge_ablation_parts` — UM run da ablação (7.3).

Value objects de domínio frozen, stdlib-only (concept 7.3 §4; I19). A partição
`fs_all_ablation` de `fact_oos_predictions` não tem `run_id` na partição, então o
`RefreshGold` a lê uma vez por `year` (o ano da DECISÃO): dentro de cada bloco as linhas
são reduzidas por run (`reduce_ablation_run`, no serviço `attribution_assembly`) e
descartadas. A redução de um bloco é uma `AblationRunPart`: perdas por (horizonte,
decisão), SEM a interseção dos horizontes — a cauda de um fold que cai num ano novo pode
ter só h+1 (as decisões finais sem alvo de h+7). `merge_ablation_parts` une as partes de
um run por horizonte e só então aplica a interseção H3-PAIR (C6-1).

A união exige a mesma identidade (`run_id`, `model_version`, `seed`, `fold_index`) e
decisões disjuntas por horizonte. Violação de dado ergue `AblationMergeError` (ou a
subclasse `OverlappingAblationPartsError`), que a montagem traduz em `undefined` — nunca
escolhe uma parte.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    check_non_empty_str,
)
from financial_forecasting.features.evaluation.domain.value_objects.permuted_run_losses import (
    check_decision_timestamps,
    check_horizon_losses,
)


class AblationMergeError(ValueError):
    """Partes de um run que não se unem (identidade, sobreposição ou sem decisão comum)."""


class OverlappingAblationPartsError(AblationMergeError):
    """Duas reduções parciais do mesmo run com uma decisão em comum no mesmo horizonte."""


def _check_identity(run_id: object, model_version: object, seed: object, fold: object) -> None:
    check_non_empty_str(run_id, field="run_id")
    check_non_empty_str(model_version, field="model_version")
    validate_int_at_least(seed, minimum=0, field="seed")
    validate_int_at_least(fold, minimum=0, field="fold_index")


@dataclass(frozen=True, kw_only=True)
class AblationRunPart:
    """A redução de um run num bloco anual: horizonte → decisão → perda (sem interseção)."""

    run_id: str
    model_version: str
    seed: int
    fold_index: int
    losses: Mapping[int, Mapping[str, float]]

    def __post_init__(self) -> None:
        """Identidade, horizontes válidos e ao menos uma perda finita por horizonte."""
        _check_identity(self.run_id, self.model_version, self.seed, self.fold_index)
        if not isinstance(self.losses, Mapping) or not self.losses:
            raise ValueError(f"losses must be a non-empty mapping, got {self.losses!r}")
        canonical: dict[int, MappingProxyType[str, float]] = {}
        for horizon, by_decision in self.losses.items():
            validate_horizon(horizon, field="losses horizon")
            if not isinstance(by_decision, Mapping) or not by_decision:
                raise ValueError(f"losses[{horizon}] must be a non-empty mapping")
            for decision, loss in by_decision.items():
                check_non_empty_str(decision, field=f"losses[{horizon}] decision")
                if not is_finite_number(loss):
                    raise ValueError(f"losses[{horizon}][{decision}] must be a finite number")
            canonical[horizon] = MappingProxyType(
                {d: float(by_decision[d]) for d in sorted(by_decision)}
            )
        object.__setattr__(
            self, "losses", MappingProxyType({h: canonical[h] for h in sorted(canonical)})
        )

    def __hash__(self) -> int:
        """Hash pela identidade do run (os mapeamentos não são hasháveis)."""
        return hash((self.run_id, self.fold_index, tuple(self.losses)))


@dataclass(frozen=True, kw_only=True)
class AblationRunLosses:
    """As perdas por decisão de um run da ablação (uma configuração LOCO, uma seed, um fold)."""

    run_id: str
    model_version: str
    seed: int
    fold_index: int
    decision_timestamps: tuple[str, ...]
    losses: Mapping[int, tuple[float, ...]]

    def __post_init__(self) -> None:
        """Forma, decisões crescentes e uma perda por decisão em cada horizonte."""
        _check_identity(self.run_id, self.model_version, self.seed, self.fold_index)
        timestamps = check_decision_timestamps(self.decision_timestamps)
        losses = check_horizon_losses(self.losses, length=len(timestamps), field="losses")
        object.__setattr__(self, "decision_timestamps", timestamps)
        object.__setattr__(self, "losses", losses)

    def __hash__(self) -> int:
        """Hash pela identidade do run (os mapeamentos não são hasháveis)."""
        return hash((self.run_id, self.decision_timestamps))


def merge_ablation_parts(parts: Sequence[AblationRunPart]) -> AblationRunLosses:
    """Une as partes de UM run por horizonte e aplica a interseção H3-PAIR.

    Raises:
        ValueError: nenhuma parte (erro de chamada).
        AblationMergeError: identidade diferente entre as partes, ou nenhuma decisão com
            todos os horizontes presentes.
        OverlappingAblationPartsError: uma decisão em duas partes no mesmo horizonte.
    """
    if not parts:
        raise ValueError("merge_ablation_parts needs at least one part")
    first = parts[0]
    identity = (first.run_id, first.model_version, first.seed, first.fold_index)
    by_horizon: dict[int, dict[str, float]] = {}
    for part in parts:
        other = (part.run_id, part.model_version, part.seed, part.fold_index)
        if other != identity:
            raise AblationMergeError(
                f"cannot merge parts of different runs: {identity} and {other}"
            )
        for horizon, by_decision in part.losses.items():
            merged = by_horizon.setdefault(horizon, {})
            overlap = sorted(set(merged) & set(by_decision))
            if overlap:
                raise OverlappingAblationPartsError(
                    f"run {first.run_id} h={horizon}: decision {overlap[0]} is in two parts"
                )
            merged.update(by_decision)
    common = sorted(set.intersection(*(set(losses) for losses in by_horizon.values())))
    if not common:
        raise AblationMergeError(
            f"run {first.run_id}: no decision has every horizon {sorted(by_horizon)}"
        )
    return AblationRunLosses(
        run_id=first.run_id,
        model_version=first.model_version,
        seed=first.seed,
        fold_index=first.fold_index,
        decision_timestamps=tuple(common),
        losses={h: tuple(by_horizon[h][t] for t in common) for h in sorted(by_horizon)},
    )
