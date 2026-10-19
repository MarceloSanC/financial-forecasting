"""`FamilyPermutationPlan` — as K_p permutações das decisões de teste de um fold (Stage 7.3).

Domínio puro (stdlib). A permutação π_k é função só de (`permutation_seed`, fold, k) e é
a mesma para toda seed do candidato e toda família (concept 7.3 I6; ADR 7.3.0005
H3-PI). O algoritmo `fisher_yates_random_random_v1` é escrito aqui, sem
`random.shuffle` (cujo algoritmo não é contrato da stdlib):

- um gerador local `random.Random(permutation_seed * 1000 + fold_index)` por fold;
- as K_p permutações saem em sequência, j = 0..K_p - 1, e são gravadas com
  `permutation_index = j + 1` (o índice 0 é a identidade);
- cada uma é Fisher-Yates de `range(n_decisions)`: `i` de n - 1 a 1,
  `r = floor(random() · (i + 1))`, troca das posições i e r.

As constantes do plano (`PERMUTATION_ALGORITHM`, `PERMUTATION_SEED`, `K_P`) são as do
bloco `[h3]` da r3. A duplicação no catálogo do evaluation é travada por teste de
integração (I17).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Final

PERMUTATION_ALGORITHM: Final = "fisher_yates_random_random_v1"
PERMUTATION_SEED: Final = 130
K_P: Final = 10
_FOLD_STRIDE = 1000


def _check_int(value: object, *, field: str, minimum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(
            f"FamilyPermutationPlan.{field} must be an int >= {minimum}, got {value!r}"
        )


def _check_fold(fold_index: object) -> None:
    """`0 <= fold_index < 1000`: com fold ≥ 1000, (semente s, fold 1000) e (s + 1, fold 0)
    dariam o mesmo gerador (C4-2)."""
    _check_int(fold_index, field="fold_index", minimum=0)
    if isinstance(fold_index, int) and fold_index >= _FOLD_STRIDE:
        raise ValueError(
            f"FamilyPermutationPlan.fold_index must be < {_FOLD_STRIDE} (the generator seed is "
            f"permutation_seed * {_FOLD_STRIDE} + fold_index), got {fold_index!r}"
        )


def _fisher_yates(rng: random.Random, n: int) -> tuple[int, ...]:
    positions = list(range(n))
    for i in range(n - 1, 0, -1):
        r = math.floor(rng.random() * (i + 1))
        positions[i], positions[r] = positions[r], positions[i]
    return tuple(positions)


@dataclass(frozen=True)
class FamilyPermutationPlan:
    """As K_p permutações de `range(n_decisions)` de um fold (k = 1..K_p)."""

    permutation_seed: int
    k_p: int
    fold_index: int
    n_decisions: int
    permutations: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        _check_int(self.permutation_seed, field="permutation_seed", minimum=0)
        _check_int(self.k_p, field="k_p", minimum=1)
        _check_fold(self.fold_index)
        _check_int(self.n_decisions, field="n_decisions", minimum=1)
        object.__setattr__(self, "permutations", tuple(tuple(p) for p in self.permutations))
        if len(self.permutations) != self.k_p:
            raise ValueError(
                f"FamilyPermutationPlan.permutations must hold k_p={self.k_p} permutations, "
                f"got {len(self.permutations)}"
            )
        expected = list(range(self.n_decisions))
        for k, permutation in enumerate(self.permutations, start=1):
            if sorted(permutation) != expected:
                raise ValueError(
                    f"FamilyPermutationPlan.permutations[{k - 1}] is not a permutation of "
                    f"range({self.n_decisions})"
                )

    @classmethod
    def generate(
        cls, *, permutation_seed: int, k_p: int, fold_index: int, n_decisions: int
    ) -> FamilyPermutationPlan:
        """O plano do fold pelo `fisher_yates_random_random_v1` (ver docstring do módulo)."""
        _check_int(permutation_seed, field="permutation_seed", minimum=0)
        _check_int(k_p, field="k_p", minimum=1)
        _check_fold(fold_index)
        _check_int(n_decisions, field="n_decisions", minimum=1)
        rng = random.Random(
            permutation_seed * _FOLD_STRIDE + fold_index
        )  # gerador local com semente (não é cripto)
        return cls(
            permutation_seed=permutation_seed,
            k_p=k_p,
            fold_index=fold_index,
            n_decisions=n_decisions,
            permutations=tuple(_fisher_yates(rng, n_decisions) for _ in range(k_p)),
        )

    @property
    def permutation_indices(self) -> tuple[int, ...]:
        """Os índices gravados das permutações: 1..K_p (0 é a identidade)."""
        return tuple(range(1, self.k_p + 1))

    def permutation(self, index: int) -> tuple[int, ...]:
        """A permutação de índice gravado `index` (1..K_p)."""
        if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= self.k_p:
            raise ValueError(f"permutation index must be in 1..{self.k_p}, got {index!r}")
        return self.permutations[index - 1]
