"""Port-out `CheckpointResolver` do slice `inference` — resolver os checkpoints de uma seed.

Port do CONSUMIDOR (ADR 0.0.0053; ADR 7.1.0001 item 1): o `RunInference` pede, por
seed do cohort congelado, o checkpoint de cada fold — `run_id`, `model_version`,
caminho e sha256 lido por streaming. **Não carrega nenhum checkpoint**: resolver é
listar e hashear, sem unpickle e sem pilha de deep learning (ADR 7.1.0004 item 1).

Real: o use case `ResolveTftCheckpoints` do `modeling`, satisfeito por
duck-typing. Os DTOs são do fornecedor e cruzam como dados, importados só sob
`TYPE_CHECKING` (o `inference` não ganha aresta de runtime para tipar o port). As
anotações são textualmente as do use case — o `check_port_coverage.py` as compara
(#93).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (  # noqa: E501
        ResolveTftCheckpointsCommand,
        ResolveTftCheckpointsResult,
    )


class CheckpointResolver(Protocol):
    """Resolve o checkpoint de cada fold de uma seed — sem carregar nenhum."""

    def __call__(self, command: ResolveTftCheckpointsCommand) -> ResolveTftCheckpointsResult:
        """Um item por fold, em ordem.

        As guardas (C1/C2/C3/C14) erguem `ApplicationError`; C13 ergue `ValueError`.
        """
        ...
