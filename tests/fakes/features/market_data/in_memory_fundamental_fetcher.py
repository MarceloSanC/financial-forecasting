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
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.asset_id import AssetId


class FakeFundamentalFetcher:
    """Implementação in-memory determinística do contrato `FundamentalFetcher`.

    `simulate_source_failure`: quando informado, o fake ergue o tipo do contrato para
    "origem indisponível" (`ApplicationError`) com essa mensagem no MESMO ponto em que
    o adapter real toca a origem — DEPOIS da validação da entrada (issue #69). É o
    que permite ao contract test provar que fake e real falham com o mesmo tipo.
    """

    def __init__(
        self,
        reports: list[FundamentalReport] | None = None,
        *,
        simulate_source_failure: str | None = None,
    ) -> None:
        # Cópia defensiva: o fake não compartilha estado mutável com o chamador.
        self._reports: list[FundamentalReport] = list(reports or [])
        self._simulate_source_failure = simulate_source_failure

    def fetch_fundamentals(self, asset_id: str) -> list[FundamentalReport]:
        """Devolve TODOS os reports pré-carregados de `asset_id` (sem filtrar, I10)."""
        asset = AssetId.parse(asset_id).value  # mesma identidade canônica do real (#69 c)
        if self._simulate_source_failure is not None:
            raise ApplicationError(self._simulate_source_failure) from ConnectionError(
                "simulated source failure"
            )
        return [r for r in self._reports if r.asset_id == asset]
