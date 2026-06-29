"""Fake in-memory do port `FundamentalFetcher` — NÃO um mock (concept 2.3 A4).

`FakeFundamentalFetcher` é um fake COMPORTAMENTAL determinístico (stdlib-only):
devolve uma `list[FundamentalReport]` pré-carregada para o ativo pedido, SEM filtrar
`report_type`/intervalo (esse filtro é do use case, concept 2.3 I10). Não asserta
chamadas — produz comportamento real e estável, para passar o MESMO contract test
parametrizado do port que o `ParquetFundamentalFetcher` (paridade fake↔real,
concept 2.3 I14).

Vive em `tests/` (fora do gate `import-linter`), mas mantém o contrato agnóstico de
`pandas`/`pyarrow`: só a entity `FundamentalReport`.
"""

from __future__ import annotations

from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)


class FakeFundamentalFetcher:
    """Implementação in-memory determinística do contrato `FundamentalFetcher`."""

    def __init__(self, reports: list[FundamentalReport] | None = None) -> None:
        # Cópia defensiva: o fake não compartilha estado mutável com o chamador.
        self._reports: list[FundamentalReport] = list(reports or [])

    def fetch_fundamentals(self, asset_id: str) -> list[FundamentalReport]:
        """Devolve TODOS os reports pré-carregados de `asset_id` (sem filtrar, I10)."""
        return [r for r in self._reports if r.asset_id == asset_id]
