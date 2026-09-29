"""Port-out `TrainingGridReader` — a grade de treino do ativo, fonte do realizado (ADR 6.4.0009).

Port do **consumidor** (concept 6.4 §4 "Application", D3, C4; ADR `6_4_0009` itens 1-2;
ADR `0_0_0053`): o `evaluation` precisa do `target_return` na MESMA grade em que os
escritores da 5.5 indexam o `decision_idx` — a grade de treino aparada
(`build_training_grid`, ADR 5.5.0004). O real é o use case `ReadTrainingGrid` da
`modeling` (`modeling/application/use_cases/read_training_grid.py`), por duck
typing; o fake é o `FakeTrainingGridReader`
(`tests/fakes/features/evaluation/fake_training_grid_reader.py`).

`TrainingGrid` é o valor do fornecedor (`modeling/domain/services/training_grid.py`)
e entra **só sob `if TYPE_CHECKING:`** — aresta type-only, declarada pelo nome no
perímetro do LAYOUT §7 e no comentário do contrato `bc-independence`. O
`RefreshGold` só lê atributos do valor devolvido (`timestamps_iso()`,
`column("target_return")`, `columns`, `trimmed_prefix`).

Contrato de `__call__(asset_id=...)`:

- as linhas do ativo (partição `asset` do dataset), em ordem cronológica;
- o prefixo sem valor (aquecimento dos indicadores) aparado — `trimmed_prefix` diz
  quantas linhas saíram; o índice 0 é a primeira sessão da grade;
- erros do dono propagam: `NoUsableRowsError` (sem linha utilizável ou ativo
  ausente), `InteriorMissingValuesError` (valor ausente depois do prefixo),
  `ValueError` (coluna pedida ausente, timestamp repetido ou sem fuso).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.domain.services.training_grid import (
        TrainingGrid,
    )


class TrainingGridReader(Protocol):
    """Lê a grade de treino (aparada) de um ativo."""

    def __call__(self, *, asset_id: str) -> TrainingGrid:
        """A grade de treino do ativo (ver o contrato no docstring do módulo)."""
        ...
