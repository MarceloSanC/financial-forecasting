"""Value object `FoldSplit` — as quatro partições disjuntas de um fold walk-forward.

Frozen, domínio puro (stdlib-only). Um `FoldSplit` carrega, para um fold, as
listas ordenadas de timestamps ISO8601 de `train`, `early_stop`, `calib` e
`test`, o `fold_index` e a `SplitFingerprint` (4 vias) que atesta a identidade do
split. As invariantes de fronteira são verificadas na construção, não assumidas
(postura "boundary = value object", ADR 0.0.0020):

- **Cada lista é não-vazia e estritamente crescente** (ISO8601 ordena
  cronologicamente por comparação lexicográfica).
- **Ordenação de bloco** (concept §5 I2): `train < early_stop < calib < test` no
  tempo — `train[-1] < early_stop[0]`, `early_stop[-1] < calib[0]`,
  `calib[-1] < test[0]`. Isso implica a **disjunção pairwise** (I1): blocos
  contíguos e ordenados não compartilham timestamp.
- **`calib` é o bloco mais recente antes do `test`** (adjacente, após o gap de
  purga+embargo do splitter) e **nunca** o early-stop — invariante do conformal
  do Step 7.2 (ADR 5.1.0002).
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.shared.domain.value_objects.split_fingerprint import (
    SplitFingerprint,
)


def _validate_strictly_increasing(name: str, values: tuple[str, ...]) -> None:
    """Ergue `ValueError` se `values` for vazio ou não estritamente crescente."""
    if not values:
        raise ValueError(f"FoldSplit.{name} must be non-empty")
    previous: str | None = None
    for current in values:
        if previous is not None and current <= previous:
            raise ValueError(
                f"FoldSplit.{name} must be strictly increasing without duplicates; "
                f"got {previous!r} followed by {current!r}"
            )
        previous = current


@dataclass(frozen=True)
class FoldSplit:
    """Partições disjuntas e ordenadas de um fold: train/early_stop/calib/test.

    Attributes:
        fold_index: índice do fold (≥ 0), crescente com a janela expansiva.
        train: timestamps ISO8601 do treino (ancorado no início da história).
        early_stop: timestamps do bloco de early-stop (seleção do modelo).
        calib: timestamps do calibration set dedicado (adjacente ao test).
        test: timestamps do bloco de teste OOS.
        fingerprint: impressão determinística 4-vias do split.
    """

    fold_index: int
    train: tuple[str, ...]
    early_stop: tuple[str, ...]
    calib: tuple[str, ...]
    test: tuple[str, ...]
    fingerprint: SplitFingerprint

    def __post_init__(self) -> None:
        """Valida `fold_index`, ordenação interna e ordenação de bloco (I1/I2)."""
        if self.fold_index < 0:
            raise ValueError(f"FoldSplit.fold_index must be >= 0; got {self.fold_index}")

        _validate_strictly_increasing("train", self.train)
        _validate_strictly_increasing("early_stop", self.early_stop)
        _validate_strictly_increasing("calib", self.calib)
        _validate_strictly_increasing("test", self.test)

        # Ordenação de bloco no tempo (implica disjunção pairwise — I1/I2).
        for earlier_name, earlier, later_name, later in (
            ("train", self.train, "early_stop", self.early_stop),
            ("early_stop", self.early_stop, "calib", self.calib),
            ("calib", self.calib, "test", self.test),
        ):
            if earlier[-1] >= later[0]:
                raise ValueError(
                    f"FoldSplit blocks must be time-ordered and disjoint: "
                    f"{earlier_name}[-1]={earlier[-1]!r} must be < "
                    f"{later_name}[0]={later[0]!r}"
                )
