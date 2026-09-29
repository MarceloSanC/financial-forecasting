"""Regras únicas da amostra pareada de perdas — horizonte, T e perda (privado do slice).

Um só dono para as regras que o VO `PairedLossSeries`, o validador `validate_dm_request`
e o `DieboldMarianoResult` checam (concept 6.2 I2/I5, C1/C3; ADR `6_2_0001` item 2):

- `check_horizon`: `horizon` int **não-bool** ≥ 1;
- `check_points`: T ≥ 2 (df da t_{T-1} ≥ 1) e **T > h** (divergência deliberada do R,
  que aceita h = T — ADR `6_2_0001`);
- `check_loss`: perda finita (sem `bool`/`None`) e ≥ 0 (o R pontuaria |L|);
- `differential`: d_t = L_first,t - L_second,t, a única escrita do diferencial;
- `is_constant`: série com todos os valores iguais — a pré-condição var > 0 do MCS e do
  `validate_block_length_request`, a regra "d constante ⇒ var̂ = 0" do DM do domínio
  (`diebold_mariano`, média inexata em float não vira var̂ > 0) e a guarda equivalente do
  adapter `StatsmodelsHac`.

Fica em `value_objects/` porque o primeiro dono das regras é o VO e a direção interna
do domínio é serviço → VO. Não se chama `_horizon.py`: a Stage 6.3, em paralelo, cria um
`value_objects/_horizon.py` próprio — unificar os dois (e a `CoverageSeries`) depois do
merge é `[finding]` no technical 6.2 §7 (candidata: 6.4).
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)

MIN_POINTS = 2


def check_horizon(horizon: object) -> None:
    """`horizon` int não-bool ≥ 1; senão `ValueError`."""
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError(f"horizon must be an int >= 1, got {horizon!r}")


def check_points(n_points: int, horizon: int) -> None:
    """T ≥ 2 e T > h; senão `ValueError` (chamar depois de `check_horizon`)."""
    if n_points < MIN_POINTS:
        raise ValueError(f"paired losses need T >= {MIN_POINTS} points, got T={n_points}")
    if n_points <= horizon:
        raise ValueError(
            f"T must be greater than the horizon (T > h), got T={n_points} and h={horizon}"
        )


def check_loss(loss: float, *, where: str) -> None:
    """Perda finita (não-bool) e ≥ 0; senão `ValueError` com `where` na mensagem."""
    if not is_finite_number(loss) or loss < 0.0:
        raise ValueError(f"{where}: loss must be a finite number >= 0, got {loss!r}")


def differential(first: Sequence[float], second: Sequence[float]) -> tuple[float, ...]:
    """d_t = first_t - second_t, ponto a ponto (tamanhos iguais)."""
    return tuple(a - b for a, b in zip(first, second, strict=True))


def is_constant(values: Sequence[float]) -> bool:
    """`True` se todos os valores são iguais (sequência não-vazia)."""
    return all(value == values[0] for value in values)
