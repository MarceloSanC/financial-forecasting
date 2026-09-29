"""VO `PairedLossSeries` — a amostra pareada, por horizonte, de DM, Holm e MCS.

Value object de domínio **frozen, stdlib-only** (concept 6.2 §4, I1/I2, C1/C2; ADR
`6_2_0001`). Carrega, para **um** horizonte, a matriz T x k de perdas por ponto — uma
coluna por modelo, na ordem fixa de `models`, alinhada 1:1 aos `target_timestamps` —,
com as invariantes verificadas **uma vez**, na construção (ADR `0_0_0020`):

- um único rótulo `horizon` (int ≥ 1): nenhuma família de Holm nem MCS mistura
  horizontes (I1);
- k ≥ 2 modelos com nomes `str` não-vazios e únicos;
- T ≥ 2 (df da t_{T-1} ≥ 1) e **T > horizon** — divergência deliberada do R, que
  aceita h = T (a variância retangular e o fator HLN seriam identicamente 0 e o
  fallback ficaria decidido por ruído de arredondamento);
- `target_timestamps` estritamente crescentes (uma observação por ponto; comparação de
  string ISO — regra única em `_timestamps.check_strictly_increasing`);
- toda coluna com T perdas finitas e ≥ 0.

Todos os contêineres são `tuple` (inclusive cada coluna): uma lista validada ainda
poderia ser mutada depois da construção. O VO **valida, nunca monta** (ADR `6_2_0001`
item 4): nenhuma interseção, reindexação ou dedup — entrada desalinhada é erro. Também
**não** checa var(L_i - L_j) > 0: um par de comparadores com diferencial constante não
bloqueia o DM/Holm do horizonte; é pré-condição do MCS (I8; doc §6.5, convenção #16).
Que as colunas sejam L_t (pinball médio na grade, média entre seeds) é garantia da
fábrica `paired_pinball_losses` (I3); o construtor aceita quaisquer perdas ≥ 0 (testes,
perfis descritivos).
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    check_horizon,
    check_loss,
    check_points,
    differential,
)
from financial_forecasting.features.evaluation.domain.value_objects._timestamps import (
    check_strictly_increasing,
)

_MIN_MODELS = 2


@dataclass(frozen=True)
class PairedLossSeries:
    """Matriz T x k de perdas por ponto de um horizonte, uma coluna por modelo.

    Campos:
        horizon: rótulo do horizonte (int ≥ 1) — um só por série.
        models: nomes dos k ≥ 2 modelos, únicos e não-vazios, em ordem fixa.
        target_timestamps: timestamps ISO do alvo, estritamente crescentes (T ≥ 2,
            T > horizon).
        losses: uma coluna por modelo, na ordem de `models`, cada uma com T perdas
            finitas e ≥ 0.

    Raises:
        ValueError: em qualquer violação de C1 (concept 6.2 §6), na construção.
    """

    horizon: int
    models: tuple[str, ...]
    target_timestamps: tuple[str, ...]
    losses: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        """Valida as invariantes na ordem do technical 6.2 Task 03."""
        self._check_containers()
        self._check_horizon()
        self._check_models()
        self._check_points()
        self._check_timestamps()
        self._check_losses()

    @property
    def n_points(self) -> int:
        """T — número de pontos pareados da série."""
        return len(self.target_timestamps)

    def losses_of(self, model: str) -> tuple[float, ...]:
        """Coluna de perdas de `model`; nome fora de `models` ergue `ValueError` (C2)."""
        return self.losses[self._index_of(model)]

    def differential(self, first: str, second: str) -> tuple[float, ...]:
        """d_t = L_first - L_second, ponto a ponto.

        Raises:
            ValueError: nome fora de `models` ou `first == second` (C2).
        """
        if first == second:
            raise ValueError(f"differential needs two distinct models, got {first!r} twice")
        return differential(self.losses_of(first), self.losses_of(second))

    def model_pairs(self) -> tuple[tuple[str, str], ...]:
        """Pares não-ordenados `(models[i], models[j])`, i < j, na ordem de `models`."""
        return tuple(
            (self.models[i], self.models[j])
            for i in range(len(self.models))
            for j in range(i + 1, len(self.models))
        )

    def _index_of(self, model: str) -> int:
        try:
            return self.models.index(model)
        except ValueError:
            raise ValueError(f"unknown model {model!r}; known models: {self.models}") from None

    def _check_containers(self) -> None:
        # tuple (imutável) em todo contêiner: lista validada ainda poderia ser mutada depois
        for name in ("models", "target_timestamps", "losses"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(
                    f"{name} must be a tuple, got {type(getattr(self, name)).__name__}"
                )
        for index, column in enumerate(self.losses):
            if not isinstance(column, tuple):
                raise ValueError(f"losses[{index}] must be a tuple, got {type(column).__name__}")

    def _check_horizon(self) -> None:
        check_horizon(self.horizon)

    def _check_models(self) -> None:
        if len(self.models) < _MIN_MODELS:
            raise ValueError(
                f"a PairedLossSeries needs k >= {_MIN_MODELS} models, got {self.models}"
            )
        for index, name in enumerate(self.models):
            if not isinstance(name, str) or not name:
                raise ValueError(f"model {index}: name must be a non-empty str, got {name!r}")
        if len(set(self.models)) != len(self.models):
            raise ValueError(f"model names must be unique, got {self.models}")

    def _check_points(self) -> None:
        check_points(self.n_points, self.horizon)

    def _check_timestamps(self) -> None:
        check_strictly_increasing(self.target_timestamps)

    def _check_losses(self) -> None:
        if len(self.losses) != len(self.models):
            raise ValueError(
                f"losses must hold one column per model: {len(self.losses)} columns for "
                f"{len(self.models)} models"
            )
        for name, column in zip(self.models, self.losses, strict=True):
            if len(column) != self.n_points:
                raise ValueError(
                    f"model {name!r}: {len(column)} losses for T={self.n_points} points"
                )
            for index, loss in enumerate(column):
                check_loss(loss, where=f"model {name!r}, point {index}")
