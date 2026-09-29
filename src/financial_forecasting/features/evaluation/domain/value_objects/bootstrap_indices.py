"""VO `BootstrapIndices` e os validadores únicos do port `McsBackend` (ADR `6_2_0004`).

Value object de domínio **frozen, stdlib-only** (concept 6.2 §4, C6/C9; ADR `6_2_0004`
itens 2 e 3). Carrega as reps x n_obs posições de reamostragem que o MCS 'R' do domínio
consome, com a proveniência do gerador de registro (`generator`, ex. `"arch 8.0.0
StationaryBootstrap / numpy default_rng"`): reproduzir um MCS confirmatório depende das
versões pinadas de `arch`/`numpy`, e o relatório diz quais.

Dois validadores únicos, chamados pelo VO, pelo fake e pelo adapter — os mesmos erros em
todas as pernas (padrão `scoring_input_validation` da 6.1):

- `validate_bootstrap_request`: `n_obs`, `block_size`, `reps`, `seed` int **não-bool**;
  `n_obs ≥ 2`, `block_size ≥ 1`, `reps ≥ 1`, `seed ≥ 0`, esquema conhecido e, no
  moving-block, `block_size < n_obs`;
- `validate_block_length_request`: série de `optimal_block_length` com pelo menos
  `MIN_BLOCK_LENGTH_OBS` pontos, todos finitos, e **não constante**.

`MIN_BLOCK_LENGTH_OBS = 11` é medido (technical 6.2 §1 item 4 e §7, Task 06): o
`_single_optimal_block` do `arch` 8.0.0 calcula autocorrelações até o lag
m_max = ⌈√n⌉ + max(5, ⌊log10 n⌋) e divide por √(v1·v2) com v1 = eps[i+1:] @ eps[i+1:];
para n ≤ 10 o lag chega a n - 1 e v1 = 0 — divisão por zero em toda série, com um número
espúrio na saída. Numa série constante o `arch` devolve `nan` ou um valor espúrio,
enquanto o fake devolveria a sua constante: sem o validador não há paridade.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)

MIN_BLOCK_LENGTH_OBS: Final = 11

_MIN_OBS = 2


class BootstrapScheme(StrEnum):
    """Esquema de bootstrap em blocos do MCS (doc §6.5; B-MCS)."""

    STATIONARY = "stationary"  # primário (B-MCS)
    MOVING_BLOCK = "moving_block"  # sensibilidade (esquema de HLN 2011)


def _check_int(name: str, value: object, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an int >= {minimum}, got {value!r}")


def validate_bootstrap_request(
    *, n_obs: int, block_size: int, reps: int, seed: int, scheme: BootstrapScheme
) -> None:
    """Validador único de um pedido de índices de bootstrap (C6/C9).

    Raises:
        ValueError: `n_obs`/`block_size`/`reps`/`seed` não-int, `bool` ou abaixo do mínimo
            (2, 1, 1, 0); esquema fora de `BootstrapScheme` (string crua inclusive);
            moving-block com `block_size >= n_obs`.
    """
    _check_int("n_obs", n_obs, _MIN_OBS)
    _check_int("block_size", block_size, 1)
    _check_int("reps", reps, 1)
    _check_int("seed", seed, 0)
    if not isinstance(scheme, BootstrapScheme):
        raise ValueError(f"scheme must be a BootstrapScheme, got {scheme!r}")
    if scheme is BootstrapScheme.MOVING_BLOCK and block_size >= n_obs:
        raise ValueError(
            f"moving_block needs block_size < n_obs, got block_size={block_size} and n_obs={n_obs}"
        )


def validate_block_length_request(series: Sequence[float]) -> None:
    """Validador único da série de `optimal_block_length` (C9).

    Raises:
        ValueError: menos de `MIN_BLOCK_LENGTH_OBS` pontos; valor não-finito, não-número
            ou `bool`; série constante.
    """
    if len(series) < MIN_BLOCK_LENGTH_OBS:
        raise ValueError(
            f"optimal_block_length needs at least {MIN_BLOCK_LENGTH_OBS} points, got {len(series)}"
        )
    for index, value in enumerate(series):
        if not is_finite_number(value):
            raise ValueError(f"series[{index}] must be a finite number, got {value!r}")
    if all(value == series[0] for value in series):
        raise ValueError("optimal_block_length needs a non-constant series")


@dataclass(frozen=True)
class BootstrapIndices:
    """reps x n_obs posições de reamostragem em [0, n_obs), com a sua proveniência.

    Campos:
        scheme: esquema de bootstrap.
        block_size: tamanho (médio, no estacionário) do bloco.
        seed: semente do gerador.
        n_obs: T da série reamostrada.
        generator: gerador de registro (proveniência), string não-vazia.
        indices: uma linha de `n_obs` posições int por réplica.

    Raises:
        ValueError: pedido inválido (`validate_bootstrap_request`, com `reps` =
            `len(indices)`), `generator` vazio ou linha mal-formada (C6), na construção.
    """

    scheme: BootstrapScheme
    block_size: int
    seed: int
    n_obs: int
    generator: str
    indices: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        """C6: pedido, proveniência e cada linha de índices (tuple, imutável)."""
        if not isinstance(self.indices, tuple):
            raise ValueError(f"indices must be a tuple, got {type(self.indices).__name__}")
        validate_bootstrap_request(
            n_obs=self.n_obs,
            block_size=self.block_size,
            reps=len(self.indices),
            seed=self.seed,
            scheme=self.scheme,
        )
        if not isinstance(self.generator, str) or not self.generator:
            raise ValueError(f"generator must be a non-empty str, got {self.generator!r}")
        n_obs = self.n_obs
        for rep, row in enumerate(self.indices):
            if not isinstance(row, tuple):
                raise ValueError(f"row {rep} must be a tuple, got {type(row).__name__}")
            if len(row) != n_obs:
                raise ValueError(f"row {rep}: {len(row)} indices for n_obs={n_obs}")
            for position in row:
                if isinstance(position, bool) or not isinstance(position, int):
                    raise ValueError(f"row {rep}: index {position!r} is not an int")
                if not 0 <= position < n_obs:
                    raise ValueError(f"row {rep}: index {position} outside [0, {n_obs})")

    @property
    def reps(self) -> int:
        """B — número de réplicas (linhas)."""
        return len(self.indices)
