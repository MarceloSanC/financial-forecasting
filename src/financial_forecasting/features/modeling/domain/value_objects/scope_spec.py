"""Value object `ScopeSpec` — identidade do cohort que isola comparações justas.

Frozen, domínio puro (stdlib-only). Um `ScopeSpec` nomeia o **escopo** sob o qual
um conjunto de modelos (candidato TFT + baselines + GBM) é comparado de forma
justa: mesmo ativo, mesmo conjunto de features e mesmo horizonte máximo. Dois
forecasts só são comparáveis quando compartilham o mesmo `ScopeSpec` (overview
§OOS "1 obs/unidade, alinhamento estrito"; roadmap Stage 5.1
"ScopeSpec/cohort para isolar comparações").

O `max_horizon` é a maior distância de horizonte `h` que qualquer modelo do
cohort prevê; fixa a **largura da purga** do `WalkForwardSplitter` (concept §5 I3:
uma decisão em `t` depende de `t + h` até `t + max_horizon`).

`cohort_id` mapeia, a jusante, ao `parent_sweep_id` do `analytics_store` (o id do
sweep/cohort pai; `None` quando avulso).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeSpec:
    """Escopo de comparação de um cohort (ativo + feature set + horizonte máximo).

    Attributes:
        asset_id: identificador do ativo (ex.: `"AAPL"`).
        feature_set_name: nome do conjunto de features do dataset comparado.
        max_horizon: maior horizonte de previsão do cohort (≥ 1); fixa a purga.
        cohort_id: id do sweep/cohort pai (`None` quando avulso).
    """

    asset_id: str
    feature_set_name: str
    max_horizon: int
    cohort_id: str | None = None

    def __post_init__(self) -> None:
        """Valida não-vazios e `max_horizon >= 1` (invariantes de construção)."""
        if not self.asset_id:
            raise ValueError("ScopeSpec.asset_id must be a non-empty string")
        if not self.feature_set_name:
            raise ValueError("ScopeSpec.feature_set_name must be a non-empty string")
        if self.max_horizon < 1:
            raise ValueError(
                f"ScopeSpec.max_horizon must be >= 1; got {self.max_horizon}"
            )
