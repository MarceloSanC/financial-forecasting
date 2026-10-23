"""`SilverContent` de amostra para manifestos de teste (Stage 8.1, ripple do campo obrigatório).

O `GoldManifest.silver_content` é obrigatório desde a 8.1 (ADR 8.1.0002 item 4); os
manifestos montados à mão nos testes da 6.4 à 7.4 carregam este valor fixo, que não
descreve silver nenhum — só satisfaz a forma (sha256 hex por unidade e por tabela).
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
)

SAMPLE_SILVER_CONTENT = SilverContent(
    digest="5c" * 32,
    tables={"dim_run": "d1" * 32, "fact_oos_predictions": "f0" * 32, "realized": "7e" * 32},
    units={
        "dim_run|sweep-01": "d1" * 32,
        "fact_oos_predictions|run-a|2024": "f0" * 32,
        "realized|AAPL": "7e" * 32,
    },
)
