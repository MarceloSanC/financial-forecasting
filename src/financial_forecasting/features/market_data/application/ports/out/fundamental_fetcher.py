"""Port-out `FundamentalFetcher` (`Protocol`) — origem de fundamentos (concept 2.3 §4 D1).

`FundamentalFetcher` é o port secundário (driven) do bounded context `market_data`
para fundamentos: abstrai a ORIGEM dos relatórios de um ativo (parquet existente —
origem default; Alpha Vantage 4 endpoints ao vivo — não-default). A `application`
(`IngestFundamentals`) depende SÓ deste `Protocol` estrutural; os adapters concretos
(`ParquetFundamentalFetcher`/`AlphaVantageFundamentalFetcher`) o satisfazem por
duck-typing (NÃO herdam da `application`, ao contrário da ABC do old).

`Protocol` (não ABC) é a postura hexagonal do projeto (`hex-arch-python`, LAYOUT
§3), idêntica a `CandleFetcher` (2.2)/`NewsFetcher`. Importa a entity
`FundamentalReport` em runtime — a `application` pode importar o `domain`. NUNCA
importa `adapters`/`httpx`/`pandas`/`pyarrow` (inward-only; concept 2.3 I3/I4).

O filtro de `report_type` e de intervalo de `fiscal_date_end` é responsabilidade do
use case `IngestFundamentals` (concept 2.3 I10), NÃO do adapter: o port devolve
TODOS os reports do ativo na origem.
"""

from __future__ import annotations

from typing import Protocol

from financial_forecasting.features.market_data.domain.entities.fundamental_report import (
    FundamentalReport,
)


class FundamentalFetcher(Protocol):
    """Contrato de leitura de relatórios fundamentais de um ativo, agnóstico de origem.

    Semântica garantida por qualquer implementação:

    - Devolve TODOS os `FundamentalReport` do ativo na origem (sem filtrar
      `report_type`/intervalo — isso é do use case, concept 2.3 I10).
    - Origem sem dados para o ativo devolve uma lista vazia; origem
      indisponível/ilegível levanta erro (não silencia em vazio; concept 2.3 C6).
    """

    def fetch_fundamentals(self, asset_id: str) -> list[FundamentalReport]:
        """Devolve os relatórios fundamentais de `asset_id` (annual + quarterly)."""
        ...
