"""VO `PermutedRunLosses` — o que sobra de UM run de atribuição depois da leitura (7.3).

Value object de domínio frozen, stdlib-only (concept 7.3 §4; I19). O `RefreshGold` lê um
run por vez de `fact_permuted_predictions`, reduz as linhas a perdas por decisão e
descarta os registros antes do próximo run. A redução (`reduce_permuted_run`) mora no
serviço `attribution_assembly`, porque constrói `CoverageSeries`; aqui ficam só a forma e
as invariantes do resultado:

- `decision_timestamps` estritamente crescentes e não vazios (as decisões do run com os
  dois horizontes, na ordem do tempo);
- `identity`: horizonte → perda média na grade de cada decisão (`L^id_t`);
- `permuted`: `(família, k, horizonte)` → `L^{perm f,k}_t`;
- toda série com o comprimento de `decision_timestamps`, perdas finitas, famílias das
  quatro do ADR 0.0.0016, `k >= 1` e os mesmos horizontes da identidade.
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
from financial_forecasting.features.evaluation.domain.value_objects._timestamps import (
    check_strictly_increasing,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    check_non_empty_str,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
)
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex


def check_decision_timestamps(value: object) -> tuple[str, ...]:
    """Decisões não vazias, `str` não vazias, estritamente crescentes."""
    if isinstance(value, str) or not isinstance(value, Sequence) or not value:
        raise ValueError(f"decision_timestamps must be a non-empty sequence, got {value!r}")
    timestamps = tuple(value)
    for index, timestamp in enumerate(timestamps):
        check_non_empty_str(timestamp, field=f"decision_timestamps[{index}]")
    check_strictly_increasing(timestamps, field="decision_timestamps")
    return timestamps


def check_loss_series(value: object, *, length: int, field: str) -> tuple[float, ...]:
    """Uma série de perdas finitas com uma entrada por decisão."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of losses, got {value!r}")
    if len(value) != length:
        raise ValueError(f"{field} has {len(value)} losses for {length} decisions")
    for index, loss in enumerate(value):
        if not is_finite_number(loss):
            raise ValueError(f"{field}[{index}] must be a finite number, got {loss!r}")
    return tuple(float(loss) for loss in value)


def check_horizon_losses(
    value: object, *, length: int, field: str
) -> MappingProxyType[int, tuple[float, ...]]:
    """Horizonte → série de perdas, não vazio, em ordem crescente de horizonte."""
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{field} must be a non-empty mapping horizon -> losses, got {value!r}")
    for horizon in value:
        validate_horizon(horizon, field=f"{field} horizon")
    return MappingProxyType(
        {
            horizon: check_loss_series(value[horizon], length=length, field=f"{field}[{horizon}]")
            for horizon in sorted(value)
        }
    )


@dataclass(frozen=True, kw_only=True)
class PermutedRunLosses:
    """As perdas por decisão de um run do candidato: identidade e cada (família, k)."""

    run_id: str
    seed: int
    fold_index: int
    permutation_seed: int
    permutation_algorithm: str
    partition_hash: str
    decision_timestamps: tuple[str, ...]
    identity: Mapping[int, tuple[float, ...]]
    permuted: Mapping[tuple[str, int, int], tuple[float, ...]]

    def __post_init__(self) -> None:
        """Forma, decisões crescentes e séries com uma perda por decisão."""
        check_non_empty_str(self.run_id, field="run_id")
        check_non_empty_str(self.permutation_algorithm, field="permutation_algorithm")
        for field in ("seed", "fold_index", "permutation_seed"):
            validate_int_at_least(getattr(self, field), minimum=0, field=field)
        validate_sha256_hex(self.partition_hash, field="partition_hash")
        timestamps = check_decision_timestamps(self.decision_timestamps)
        length = len(timestamps)
        identity = check_horizon_losses(self.identity, length=length, field="identity")
        if not isinstance(self.permuted, Mapping) or not self.permuted:
            raise ValueError(f"permuted must be a non-empty mapping, got {self.permuted!r}")
        permuted: dict[tuple[str, int, int], tuple[float, ...]] = {}
        for key in list(self.permuted):
            if not isinstance(key, tuple) or len(key) != 3:  # noqa: PLR2004 — (f, k, h)
                raise ValueError(f"permuted key must be (family, k, horizon), got {key!r}")
            family, k, horizon = key
            if family not in H3_FAMILIES:
                raise ValueError(f"permuted family must be one of {list(H3_FAMILIES)}, got {key!r}")
            validate_int_at_least(k, minimum=1, field=f"permuted{list(key)} k")
            if horizon not in identity:
                raise ValueError(
                    f"permuted{list(key)} horizon {horizon!r} is not an identity horizon "
                    f"{list(identity)}"
                )
            permuted[key] = check_loss_series(
                self.permuted[key], length=length, field=f"permuted{list(key)}"
            )
        object.__setattr__(self, "decision_timestamps", timestamps)
        object.__setattr__(self, "identity", identity)
        object.__setattr__(
            self, "permuted", MappingProxyType({key: permuted[key] for key in sorted(permuted)})
        )

    def __hash__(self) -> int:
        """Hash pela identidade do run (os mapeamentos não são hasháveis)."""
        return hash((self.run_id, self.decision_timestamps))
