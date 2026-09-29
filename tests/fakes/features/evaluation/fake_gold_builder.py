"""Fake do port `GoldBuilder` — uma linha por nome de check, sem fórmula (ADR 6.4.0001).

Tabela mínima e **diferente** da do `QualityChecksGoldBuilder` (nenhum bloco de lógica
em comum para o `check_fake_parity`): uma linha por nome de check distinto nos
resultados, `key = ("check",)`, colunas `check`, `n_results`, `asset`,
`parent_sweep_id` e — quando o builder não roda bloqueado — `preregistration_ref`.
Registra cada `GoldInputs` recebido em `calls` (para os testes de ordem do use case).
"""

from __future__ import annotations

from collections import Counter

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)


class FakeGoldBuilder:
    """Satisfaz `GoldBuilder` com uma contagem de resultados por check."""

    def __init__(
        self,
        name: str,
        depends_on: frozenset[str] = frozenset(),
        runs_when_blocked: bool = False,
    ) -> None:
        self._name = name
        self._depends_on = depends_on
        self._runs_when_blocked = runs_when_blocked
        self.calls: list[GoldInputs] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def depends_on(self) -> frozenset[str]:
        return self._depends_on

    @property
    def runs_when_blocked(self) -> bool:
        return self._runs_when_blocked

    def build(self, inputs: GoldInputs) -> GoldTable:
        self.calls.append(inputs)
        counts = Counter(result.check for result in inputs.check_results)
        extra = (
            {} if self._runs_when_blocked else {"preregistration_ref": inputs.preregistration_ref}
        )
        rows = [
            {
                "check": check,
                "n_results": n_results,
                "asset": inputs.partition.asset,
                "parent_sweep_id": inputs.partition.parent_sweep_id,
                **extra,
            }
            for check, n_results in counts.items()
        ]
        return GoldTable.sorted_by_key(f"gold_{self._name}", ("check",), rows)
