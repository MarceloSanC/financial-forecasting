"""VO `AblationRunLosses` e `merge_ablation_parts` — UM run da ablação reduzido (7.3).

Value object de domínio frozen, stdlib-only (concept 7.3 §4; I19). A partição
`fs_all_ablation` de `fact_oos_predictions` não tem `run_id` na partição, então o
`RefreshGold` a lê uma vez por `year`: dentro de cada bloco as linhas são reduzidas por
run (`reduce_ablation_run`, no serviço `attribution_assembly`) e descartadas. Um run cujo
teste cruza a virada do ano sai em duas reduções parciais, que `merge_ablation_parts` une
(technical 7.3 §1 "Leitura da ablação por `year`").

A união exige a mesma identidade (`run_id`, `model_version`, `seed`, `fold_index`), os
mesmos horizontes e decisões disjuntas; partes que se sobrepõem erguem
`OverlappingAblationPartsError` (a montagem a traduz em `undefined`, nunca escolhe uma).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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


class OverlappingAblationPartsError(ValueError):
    """Duas reduções parciais do mesmo run com uma decisão em comum."""


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
        check_non_empty_str(self.run_id, field="run_id")
        check_non_empty_str(self.model_version, field="model_version")
        for field in ("seed", "fold_index"):
            validate_int_at_least(getattr(self, field), minimum=0, field=field)
        timestamps = check_decision_timestamps(self.decision_timestamps)
        losses = check_horizon_losses(self.losses, length=len(timestamps), field="losses")
        object.__setattr__(self, "decision_timestamps", timestamps)
        object.__setattr__(self, "losses", losses)

    def __hash__(self) -> int:
        """Hash pela identidade do run (os mapeamentos não são hasháveis)."""
        return hash((self.run_id, self.decision_timestamps))


def merge_ablation_parts(parts: Sequence[AblationRunLosses]) -> AblationRunLosses:
    """Une as reduções parciais de UM run (decisões disjuntas) numa redução só.

    Raises:
        ValueError: nenhuma parte, identidade ou horizontes diferentes entre as partes.
        OverlappingAblationPartsError: uma decisão aparece em duas partes.
    """
    if not parts:
        raise ValueError("merge_ablation_parts needs at least one part")
    first = parts[0]
    identity = (first.run_id, first.model_version, first.seed, first.fold_index)
    horizons = tuple(first.losses)
    for part in parts[1:]:
        other = (part.run_id, part.model_version, part.seed, part.fold_index)
        if other != identity:
            raise ValueError(f"cannot merge parts of different runs: {identity} and {other}")
        if tuple(part.losses) != horizons:
            raise ValueError(
                f"run {first.run_id}: parts with different horizons "
                f"{list(horizons)} and {list(part.losses)}"
            )
    by_decision: dict[str, tuple[float, ...]] = {}
    for part in parts:
        for index, timestamp in enumerate(part.decision_timestamps):
            if timestamp in by_decision:
                raise OverlappingAblationPartsError(
                    f"run {first.run_id}: decision {timestamp} is in two parts"
                )
            by_decision[timestamp] = tuple(part.losses[h][index] for h in horizons)
    timestamps = tuple(sorted(by_decision))
    return AblationRunLosses(
        run_id=first.run_id,
        model_version=first.model_version,
        seed=first.seed,
        fold_index=first.fold_index,
        decision_timestamps=timestamps,
        losses={
            horizon: tuple(by_decision[t][position] for t in timestamps)
            for position, horizon in enumerate(horizons)
        },
    )
