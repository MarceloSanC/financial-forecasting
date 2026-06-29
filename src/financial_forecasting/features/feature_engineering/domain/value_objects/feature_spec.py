"""`FeatureSpec` — value-object frozen do registry rico de features (domínio puro).

Superset rico do `IndicatorSpec` mínimo da Stage 3.1
(`domain/services/indicator_spec.py`) e do `FeatureSpec` do old
(`financial-time-series-forecasting/src/infrastructure/schemas/feature_registry.py:7-17`):
adiciona os campos ricos do old (`formula_desc`/`null_policy`/`enabled_by_default`)
e os campos **novos** desta Stage — `anti_leakage_tag` obrigatória em vocabulário
fixo (espinha do DoD: feature sem contrato de causalidade é rejeitada) e
`tft_typing ∈ {known, unknown}` (promovido do use case de treino hardcoded do old,
`train_tft_model_use_case.py:1216`; concept 3.4 D4 / ADR 3.4.0002).

Diferenças de taxonomia vs o old (concept 3.4 §5):

- **`family`** substitui o `group` de 5 valores do old por **4 famílias** fixas
  `{price, technical, sentiment, fundamental}` (ADR 0.0.0016). `baseline`/`derived`
  do old NÃO são família: OHLCV cru e derivadas de preço → `price`, derivadas de
  indicador → `technical`, sentimento dinâmico → `sentiment`, fundamento
  derivado/YoY → `fundamental` (I4).
- **`anti_leakage_tag`** em vocabulário fixo — superset das 2 tags da 3.1
  (`trailing_window_causal`/`same_timestamp_ohlc_derived`) com as 4 tags adicionais
  usadas pelas famílias base/derivadas do old.

Pureza (I1): importa SÓ stdlib (`dataclasses`). `import pandas`/`numpy`/`pydantic`
aqui REPROVA `domain-purity` no import-linter (concept 3.4 I1/A8).
"""

from __future__ import annotations

from dataclasses import dataclass

# Conjuntos permitidos (C3/C4/C5): blindam o spec contra valores fora de contrato.
# `family` de 4 valores (I4, ADR 0.0.0016): `baseline`/`derived` do old NÃO são
# família — a derivada herda a família da natureza da sua fonte.
_ALLOWED_FAMILIES: frozenset[str] = frozenset({"price", "technical", "sentiment", "fundamental"})
# Vocabulário fixo de `anti_leakage_tag` (concept 3.4 §4) — superset das 2 tags da
# 3.1 com as 4 tags das famílias base/derivadas do old:
# - point_in_time_ohlcv      : OHLCV cru observado em t (preço base).
# - same_timestamp_ohlc_derived: derivação determinística no MESMO timestamp (candle_*).
# - trailing_window_causal   : janela trailing causal (indicadores, retornos, vol).
# - lagged_causal            : puro `shift(n>0)` (sentiment_lag_*).
# - publication_cutoff_asof  : agregado de sentimento com cutoff de publicação.
# - reported_date_asof       : fundamento as-of pela reported_date (+ YoY).
_ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "point_in_time_ohlcv",
        "same_timestamp_ohlc_derived",
        "trailing_window_causal",
        "lagged_causal",
        "publication_cutoff_asof",
        "reported_date_asof",
    }
)
# Tipagem TFT known/unknown (I3, D4): calendário = known; preço/indicador/
# sentimento/fundamento/derivada = unknown.
_ALLOWED_TFT_TYPING: frozenset[str] = frozenset({"known", "unknown"})


@dataclass(frozen=True)
class FeatureSpec:
    """Especificação imutável de uma feature (value-object de domínio).

    Campos (concept 3.4 §4):

    - `name`: identificador da coluna produzida (ex. `"log_return_1d"`); não-vazio.
    - `family`: uma das 4 famílias `{price, technical, sentiment, fundamental}` (I4).
    - `source_cols`: colunas de origem (ex. `("close",)`).
    - `formula_desc`: descrição textual da fórmula (verbatim do old quando derivada).
    - `anti_leakage_tag`: **tag de causalidade obrigatória**, em vocabulário fixo
      (C4 — espinha do DoD: feature sem contrato de causalidade é rejeitada).
    - `warmup_count`: nº de barras de aquecimento (`>= 0`); é o tamanho de janela
      nominal — o warmup EFETIVO (ex. `vol_of_vol`=40) é documentado no registry.
    - `tft_typing`: tipagem TFT em `{known, unknown}` (I3); obrigatória.
    - `null_policy`: política de nulos (default `"allow"`).
    - `dtype`: tipo de saída (default `"float64"`; flags/regimes usam `"int64"`).
    - `enabled_by_default`: se a feature entra no set default (default `True`).

    `__post_init__` valida os invariantes (C1-C5) - violação levanta `ValueError`
    de domínio (mensagens incluem `name`, espelhando o estilo do `IndicatorSpec`).
    """

    name: str
    family: str
    source_cols: tuple[str, ...]
    formula_desc: str
    anti_leakage_tag: str
    warmup_count: int
    tft_typing: str
    null_policy: str = "allow"
    dtype: str = "float64"
    enabled_by_default: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("FeatureSpec.name must be a non-empty string")
        if self.warmup_count < 0:
            raise ValueError(
                f"FeatureSpec.warmup_count must be >= 0, got {self.warmup_count!r} "
                f"for {self.name!r}"
            )
        if self.family not in _ALLOWED_FAMILIES:
            raise ValueError(
                f"FeatureSpec.family must be one of {sorted(_ALLOWED_FAMILIES)}, "
                f"got {self.family!r} for {self.name!r}"
            )
        if self.anti_leakage_tag not in _ALLOWED_TAGS:
            raise ValueError(
                f"FeatureSpec.anti_leakage_tag must be one of {sorted(_ALLOWED_TAGS)}, "
                f"got {self.anti_leakage_tag!r} for {self.name!r}"
            )
        if self.tft_typing not in _ALLOWED_TFT_TYPING:
            raise ValueError(
                f"FeatureSpec.tft_typing must be one of {sorted(_ALLOWED_TFT_TYPING)}, "
                f"got {self.tft_typing!r} for {self.name!r}"
            )
