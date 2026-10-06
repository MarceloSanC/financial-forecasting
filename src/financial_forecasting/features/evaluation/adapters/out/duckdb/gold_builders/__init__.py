"""Os gold builders: os cinco da Stage 6.4 e os oito de perfil da 6.6.

Satisfazem o port `GoldBuilder` (ADR 6.4.0001).

Mapeamento puro em Python (sem `pyarrow`/`duckdb`/`pandas`): cada `build` só copia
campos dos relatórios dos `GoldInputs` para as colunas da sua tabela (technical 6.4 §1
"Tabelas gold") e devolve um `GoldTable` ordenado pela chave. `partition_columns` é a
escrita única das colunas de autodescrição (I17): `asset`/`parent_sweep_id` em toda
linha e `preregistration_ref` só nas confirmatórias.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
)

QUALITY_CHECKS = "quality_checks"


def partition_columns(inputs: GoldInputs, *, confirmatory: bool) -> dict[str, object]:
    """Colunas de autodescrição de toda linha (I17; ADR 6.4.0006 item 4)."""
    columns: dict[str, object] = {
        "asset": inputs.partition.asset,
        "parent_sweep_id": inputs.partition.parent_sweep_id,
    }
    if confirmatory:
        columns["preregistration_ref"] = inputs.preregistration_ref
    return columns
