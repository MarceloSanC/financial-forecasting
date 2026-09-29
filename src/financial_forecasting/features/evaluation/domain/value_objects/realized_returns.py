"""VO `RealizedReturns` — o `target_return` do dataset, por sessão, para o join do gold.

Value object de domínio **frozen, stdlib-only** (concept 6.4 §4 "Domínio", I5, I7;
ADR `6_4_0004`). Carrega as sessões do dataset em ordem (`timestamps`, ISO,
estritamente crescentes — regra única `_timestamps.check_strictly_increasing`) e o
`target_return` de cada uma (`returns`, finitos). É a **única** fonte do realizado da
avaliação: o `SeriesAssembly` consulta `index_of` para conferir `decision_idx` e o
rótulo de horizonte (I5) e `realized_at` para o join do `target` (I7).

O resumo (`n_sessions`, `returns_fsum`, `first_timestamp`, `last_timestamp`) é uma
computação só, consumida pelo check `realized_provenance` e pelo manifesto do gold
(technical 6.4 §1); a soma usa `math.fsum` (exata, independente da ordem de parcelas
parciais), não `sum`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._timestamps import (
    check_strictly_increasing,
)


@dataclass(frozen=True)
class RealizedReturns:
    """Sessões do dataset e o `target_return` de cada uma.

    Campos:
        timestamps: timestamps ISO UTC das sessões, estritamente crescentes (≥ 1).
        returns: `target_return` de cada sessão, finito, alinhado 1:1 a `timestamps`.

    Raises:
        ValueError: contêiner não-`tuple`, série vazia, tamanhos diferentes, timestamp
            não-`str`/fora de ordem ou retorno não-finito, na construção.
    """

    timestamps: tuple[str, ...]
    returns: tuple[float, ...]
    _index: dict[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Forma, ordem e finitude; constrói o índice por timestamp uma vez."""
        for name in ("timestamps", "returns"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(
                    f"{name} must be a tuple, got {type(getattr(self, name)).__name__}"
                )
        if not self.timestamps:
            raise ValueError("RealizedReturns needs at least one session")
        if len(self.returns) != len(self.timestamps):
            raise ValueError(
                f"returns must align with timestamps: {len(self.returns)} returns for "
                f"{len(self.timestamps)} timestamps"
            )
        for index, timestamp in enumerate(self.timestamps):
            if not isinstance(timestamp, str) or not timestamp:
                raise ValueError(f"timestamps[{index}] must be a non-empty str, got {timestamp!r}")
        check_strictly_increasing(self.timestamps)
        for index, value in enumerate(self.returns):
            if not is_finite_number(value):
                raise ValueError(f"returns[{index}] must be a finite number, got {value!r}")
        object.__setattr__(
            self, "_index", {timestamp: i for i, timestamp in enumerate(self.timestamps)}
        )

    def index_of(self, timestamp: str) -> int | None:
        """Índice de sessão de `timestamp`, ou `None` se não for uma sessão do dataset."""
        return self._index.get(timestamp)

    def realized_at(self, timestamp: str) -> float:
        """`target_return` da sessão `timestamp`.

        Raises:
            ValueError: `timestamp` fora das sessões do dataset.
        """
        index = self._index.get(timestamp)
        if index is None:
            raise ValueError(f"no realized return for session {timestamp!r}")
        return self.returns[index]

    @property
    def n_sessions(self) -> int:
        """Número de sessões do dataset."""
        return len(self.timestamps)

    @property
    def returns_fsum(self) -> float:
        """Soma exata (`math.fsum`) dos `target_return`."""
        return math.fsum(self.returns)

    @property
    def first_timestamp(self) -> str:
        """Primeira sessão."""
        return self.timestamps[0]

    @property
    def last_timestamp(self) -> str:
        """Última sessão."""
        return self.timestamps[-1]
