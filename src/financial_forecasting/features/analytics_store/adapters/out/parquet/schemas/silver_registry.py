"""`SILVER_REGISTRY` — registry `(layer, table) -> SilverTable` (Stage 4.1, task-08).

Agrega as 5 tabelas silver consumidas pelos Steps 1-4 num único `Mapping` chaveado por
`("silver", <table>)`, espelhando o `BRONZE_REGISTRY` da Stage 2.1. É a costura (seam)
sobre a qual o repositório da Stage 4.2 despacha escritas/leituras por tabela, sem
hard-coding tabela a tabela.

Um par `(layer, table)` fora do registry é `KeyError` (concept §6 C6): o registry não
engole o erro — quem despacha (4.2) trata. As 8 tabelas deferidas (inference_*/
feature_contrib_local/epoch_metrics/model_artifacts/bridge_run_features/
split_timestamps_ref/fact_run_snapshot) NÃO entram aqui (ADR 4.1.0001).

Vive no adapter (importa os 5 módulos de schema + `SilverTable`).
"""

from __future__ import annotations

from collections.abc import Mapping

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.dim_run_schema import (  # noqa: E501
    DIM_RUN,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_config_schema import (  # noqa: E501
    FACT_CONFIG,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_failures_schema import (  # noqa: E501
    FACT_FAILURES,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_oos_predictions_schema import (  # noqa: E501
    FACT_OOS_PREDICTIONS,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.fact_split_metrics_schema import (  # noqa: E501
    FACT_SPLIT_METRICS,
)
from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_table import (  # noqa: E501
    SilverTable,
)

SILVER_LAYER = "silver"

# Registry `(layer, table) -> SilverTable` sobre o qual o adapter da 4.2 despacha.
# Um par fora deste registry é erro de aplicação (concept §6 C6 — KeyError).
SILVER_REGISTRY: Mapping[tuple[str, str], SilverTable] = {
    (SILVER_LAYER, DIM_RUN.name): DIM_RUN,
    (SILVER_LAYER, FACT_CONFIG.name): FACT_CONFIG,
    (SILVER_LAYER, FACT_OOS_PREDICTIONS.name): FACT_OOS_PREDICTIONS,
    (SILVER_LAYER, FACT_SPLIT_METRICS.name): FACT_SPLIT_METRICS,
    (SILVER_LAYER, FACT_FAILURES.name): FACT_FAILURES,
}
