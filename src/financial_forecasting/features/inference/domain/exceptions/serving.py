"""Pedido da API de inferência sem dado gravado (Stage 7.4; concept I8, D3; ADR 7.4.0001 item 4).

`NoServedDataError` é um `NotFoundError`: o handler global da app o responde com 404
`{detail, type: "not_found"}`. A mensagem começa sempre por `NO_SERVED_DATA` (a frase
que o humano fixou no Passo 1b, B1) e diz o que faltou: o ativo, o horizonte, a seed
ou os (seed, horizonte) sem linha de teste na data de decisão.
"""

from __future__ import annotations

from typing import Final

from financial_forecasting.shared.domain.exceptions.base import NotFoundError

NO_SERVED_DATA: Final = "não há dados para o pedido solicitado"


class NoServedDataError(NotFoundError):
    """O pedido não tem dado gravado no cohort servido; `missing` diz o que faltou."""

    def __init__(self, missing: str) -> None:
        self.missing = missing
        super().__init__(f"{NO_SERVED_DATA}: {missing}")
