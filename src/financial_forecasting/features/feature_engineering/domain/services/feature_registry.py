"""`FeatureRegistry` — fonte única da verdade das features (domain service puro).

`FEATURE_SPECS` é o registry estático imutável (`MappingProxyType`, read-only) de
TODAS as features das 4 famílias + derivadas (concept 3.4 §1/§4). Cada entrada é um
`FeatureSpec` (value-object), de modo que o registry **não consegue** conter uma
feature sem contrato de causalidade: a validação mora no `__post_init__` do spec
(I2/A3). Replica o `FEATURE_REGISTRY` do old
(`financial-time-series-forecasting/src/infrastructure/schemas/feature_registry.py`)
com a taxonomia desta Stage (concept 3.4 §5):

Mapeamento `group` (old, 5 valores) → `family` (4 valores, I4 / ADR 0.0.0016):

| group (old)  | family (3.4)                                  |
|--------------|-----------------------------------------------|
| baseline     | price        (OHLCV cru)                      |
| technical    | technical    (indicadores + candle_*)         |
| sentiment    | sentiment                                     |
| fundamental  | fundamental                                   |
| derived      | herda da natureza da fonte:                   |
|              |   preço/retorno/vol/regime → price/technical  |
|              |   sentimento dinâmico       → sentiment       |
|              |   fundamento derivado/YoY   → fundamental     |

Regra única de `tft_typing` (I3/D4): calendário (`day_of_week`/`month`/`time_idx`,
se vierem a ser registrados como features) = `known`; preço/indicador/sentimento/
fundamento/derivada = `unknown`. Hoje o registry só tem features `unknown` (não há
features de calendário aqui; elas entram na 3.5 ao montar o dataset TFT).

`feature_set_hash` replica a postura de `indicator_registry_hash` (3.1) e
`feature_registry_hash` do old (:471-491): função PURA do conteúdo dos specs
ordenados por `name` (D3, sem injetar o port `Hasher` — `hashlib` é stdlib).

Pureza (I1): importa SÓ stdlib (`collections.abc`/`hashlib`/`types`) + o VO
`FeatureSpec` do mesmo domínio. `import pandas`/`numpy` aqui REPROVA `domain-purity`.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from types import MappingProxyType

from financial_forecasting.features.feature_engineering.domain.value_objects.feature_spec import (
    FeatureSpec,
)

# Atalhos de tag para legibilidade do registry (vocabulário fixo do `FeatureSpec`).
_OHLCV = "point_in_time_ohlcv"
_OHLC_DERIVED = "same_timestamp_ohlc_derived"
_TRAILING = "trailing_window_causal"
_LAGGED = "lagged_causal"
_PUB_ASOF = "publication_cutoff_asof"
_REP_ASOF = "reported_date_asof"
_UNKNOWN = "unknown"


def _base_specs() -> dict[str, FeatureSpec]:
    """Specs das features BASE das 4 famílias (sem derivadas — Task 02).

    Famílias base (concept 3.4 §5):

    - preço/baseline: OHLCV cru → `family="price"`, tag `point_in_time_ohlcv`.
    - técnico: os 10 indicadores da 3.1 (`INDICATOR_SPECS`) + `candle_*` →
      `family="technical"`, tags `trailing_window_causal`/`same_timestamp_ohlc_derived`.
    - sentimento: agregados diários → `family="sentiment"`, tag `publication_cutoff_asof`.
    - fundamento base: reports as-of → `family="fundamental"`, tag `reported_date_asof`.
    """
    return {
        # -- price (baseline OHLCV cru) ---------------------------------------
        "open": FeatureSpec(
            name="open",
            family="price",
            source_cols=("open",),
            formula_desc="Observed open price at timestamp t",
            anti_leakage_tag=_OHLCV,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "high": FeatureSpec(
            name="high",
            family="price",
            source_cols=("high",),
            formula_desc="Observed high price at timestamp t",
            anti_leakage_tag=_OHLCV,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "low": FeatureSpec(
            name="low",
            family="price",
            source_cols=("low",),
            formula_desc="Observed low price at timestamp t",
            anti_leakage_tag=_OHLCV,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "close": FeatureSpec(
            name="close",
            family="price",
            source_cols=("close",),
            formula_desc="Observed close price at timestamp t",
            anti_leakage_tag=_OHLCV,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "volume": FeatureSpec(
            name="volume",
            family="price",
            source_cols=("volume",),
            formula_desc="Observed traded volume at timestamp t",
            anti_leakage_tag=_OHLCV,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        # -- technical (10 indicadores da 3.1 + candle_*) ---------------------
        "rsi_14": FeatureSpec(
            name="rsi_14",
            family="technical",
            source_cols=("close",),
            formula_desc="Relative Strength Index over 14 periods",
            anti_leakage_tag=_TRAILING,
            warmup_count=14,
            tft_typing=_UNKNOWN,
        ),
        "macd": FeatureSpec(
            name="macd",
            family="technical",
            source_cols=("close",),
            formula_desc="MACD line from EMA(12)-EMA(26)",
            anti_leakage_tag=_TRAILING,
            warmup_count=26,
            tft_typing=_UNKNOWN,
        ),
        "macd_signal": FeatureSpec(
            name="macd_signal",
            family="technical",
            source_cols=("close",),
            formula_desc="Signal line from MACD(12,26,9)",
            anti_leakage_tag=_TRAILING,
            warmup_count=35,
            tft_typing=_UNKNOWN,
        ),
        "ema_10": FeatureSpec(
            name="ema_10",
            family="technical",
            source_cols=("close",),
            formula_desc="Exponential Moving Average over 10 periods",
            anti_leakage_tag=_TRAILING,
            warmup_count=10,
            tft_typing=_UNKNOWN,
        ),
        "ema_50": FeatureSpec(
            name="ema_50",
            family="technical",
            source_cols=("close",),
            formula_desc="Exponential Moving Average over 50 periods",
            anti_leakage_tag=_TRAILING,
            warmup_count=50,
            tft_typing=_UNKNOWN,
        ),
        "ema_100": FeatureSpec(
            name="ema_100",
            family="technical",
            source_cols=("close",),
            formula_desc="Exponential Moving Average over 100 periods",
            anti_leakage_tag=_TRAILING,
            warmup_count=100,
            tft_typing=_UNKNOWN,
        ),
        "ema_200": FeatureSpec(
            name="ema_200",
            family="technical",
            source_cols=("close",),
            formula_desc="Exponential Moving Average over 200 periods",
            anti_leakage_tag=_TRAILING,
            warmup_count=200,
            tft_typing=_UNKNOWN,
        ),
        "volatility_20d": FeatureSpec(
            name="volatility_20d",
            family="technical",
            source_cols=("close",),
            formula_desc="Rolling std of close returns over 20 periods",
            anti_leakage_tag=_TRAILING,
            warmup_count=20,
            tft_typing=_UNKNOWN,
        ),
        "candle_range": FeatureSpec(
            name="candle_range",
            family="technical",
            source_cols=("high", "low"),
            formula_desc="Candle range high-low at t",
            anti_leakage_tag=_OHLC_DERIVED,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "candle_body": FeatureSpec(
            name="candle_body",
            family="technical",
            source_cols=("open", "close"),
            formula_desc="Absolute candle body abs(close-open) at t",
            anti_leakage_tag=_OHLC_DERIVED,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        # -- sentiment (agregados diários as-of) ------------------------------
        "sentiment_score": FeatureSpec(
            name="sentiment_score",
            family="sentiment",
            source_cols=("scored_news",),
            formula_desc="Daily aggregate sentiment score for effective day",
            anti_leakage_tag=_PUB_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "news_volume": FeatureSpec(
            name="news_volume",
            family="sentiment",
            source_cols=("scored_news",),
            formula_desc="Daily count of news articles for effective day",
            anti_leakage_tag=_PUB_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "sentiment_std": FeatureSpec(
            name="sentiment_std",
            family="sentiment",
            source_cols=("scored_news",),
            formula_desc="Daily std of article sentiment scores",
            anti_leakage_tag=_PUB_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "has_news": FeatureSpec(
            name="has_news",
            family="sentiment",
            source_cols=("news_volume",),
            formula_desc="Binary flag 1(news_volume>0) else 0",
            anti_leakage_tag=_PUB_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
            dtype="int64",
        ),
        # -- fundamental base (reports as-of) ---------------------------------
        "revenue": FeatureSpec(
            name="revenue",
            family="fundamental",
            source_cols=("fundamental_reports",),
            formula_desc=("Reported revenue merged with as-of join by fundamentals_effective_date"),
            anti_leakage_tag=_REP_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "net_income": FeatureSpec(
            name="net_income",
            family="fundamental",
            source_cols=("fundamental_reports",),
            formula_desc=(
                "Reported net income merged with as-of join by fundamentals_effective_date"
            ),
            anti_leakage_tag=_REP_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "operating_cash_flow": FeatureSpec(
            name="operating_cash_flow",
            family="fundamental",
            source_cols=("fundamental_reports",),
            formula_desc=(
                "Reported operating cash flow merged with as-of join by fundamentals_effective_date"
            ),
            anti_leakage_tag=_REP_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "total_shareholder_equity": FeatureSpec(
            name="total_shareholder_equity",
            family="fundamental",
            source_cols=("fundamental_reports",),
            formula_desc=(
                "Reported shareholder equity merged with as-of join by fundamentals_effective_date"
            ),
            anti_leakage_tag=_REP_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "total_liabilities": FeatureSpec(
            name="total_liabilities",
            family="fundamental",
            source_cols=("fundamental_reports",),
            formula_desc=(
                "Reported liabilities merged with as-of join by fundamentals_effective_date"
            ),
            anti_leakage_tag=_REP_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
    }


def _derived_specs() -> dict[str, FeatureSpec]:
    """Specs das ~38 derivadas (metadados, NÃO computação — Task 03).

    Replica `formula_desc`/`warmup_count`/`anti_leakage_tag`/`dtype` verbatim do
    `FEATURE_REGISTRY` do old, com a taxonomia desta Stage (concept 3.4 §5):

    Família da derivada (I4): preço/retorno/liquidez/volatilidade/regime →
    `price`/`technical` (derivada de indicador como `vol_of_vol`/`volatility_regime`
    de `volatility_20d`, `trend_regime` de `ema_*` → `technical`); sentimento
    dinâmico → `sentiment`; fundamento derivado/YoY → `fundamental`.

    Tags: derivadas de OHLCV/preço → `trailing_window_causal`; `sentiment_lag_*`
    (puro `shift`) → `lagged_causal` (promovido vs o old, que usava
    `trailing_window_causal` — `lagged_causal` é a tag nova precisa para shift puro;
    [decision] technical §7); demais sentimento dinâmico → `trailing_window_causal`;
    fundamento derivado/YoY → `reported_date_asof` (verbatim old).

    Warmup efetivo (I7) documentado quando difere da janela nominal: `vol_of_vol`=40
    (20 da `volatility_20d` consumidos + 20 da janela `std`); `volume_zscore`=20
    (estatística trailing `t-20..t-1` + numerador corrente `volume_t`); YoY=252.
    """
    return {
        # -- price: log-returns, momentum, reversal, drawdown, liquidez -------
        "log_return_1d": FeatureSpec(
            name="log_return_1d",
            family="price",
            source_cols=("close",),
            formula_desc="log(close_t / close_t-1)",
            anti_leakage_tag=_TRAILING,
            warmup_count=1,
            tft_typing=_UNKNOWN,
        ),
        "log_return_5d": FeatureSpec(
            name="log_return_5d",
            family="price",
            source_cols=("close",),
            formula_desc="log(close_t / close_t-5)",
            anti_leakage_tag=_TRAILING,
            warmup_count=5,
            tft_typing=_UNKNOWN,
        ),
        "log_return_21d": FeatureSpec(
            name="log_return_21d",
            family="price",
            source_cols=("close",),
            formula_desc="log(close_t / close_t-21)",
            anti_leakage_tag=_TRAILING,
            warmup_count=21,
            tft_typing=_UNKNOWN,
        ),
        "momentum_5d": FeatureSpec(
            name="momentum_5d",
            family="price",
            source_cols=("close",),
            formula_desc="close_t / close_t-5 - 1",
            anti_leakage_tag=_TRAILING,
            warmup_count=5,
            tft_typing=_UNKNOWN,
        ),
        "momentum_21d": FeatureSpec(
            name="momentum_21d",
            family="price",
            source_cols=("close",),
            formula_desc="close_t / close_t-21 - 1",
            anti_leakage_tag=_TRAILING,
            warmup_count=21,
            tft_typing=_UNKNOWN,
        ),
        "momentum_63d": FeatureSpec(
            name="momentum_63d",
            family="price",
            source_cols=("close",),
            formula_desc="close_t / close_t-63 - 1",
            anti_leakage_tag=_TRAILING,
            warmup_count=63,
            tft_typing=_UNKNOWN,
        ),
        "reversal_1d": FeatureSpec(
            name="reversal_1d",
            family="price",
            source_cols=("close",),
            formula_desc="-1 * return_1d",
            anti_leakage_tag=_TRAILING,
            warmup_count=1,
            tft_typing=_UNKNOWN,
        ),
        "reversal_5d": FeatureSpec(
            name="reversal_5d",
            family="price",
            source_cols=("close",),
            formula_desc="-1 * momentum_5d",
            anti_leakage_tag=_TRAILING,
            warmup_count=5,
            tft_typing=_UNKNOWN,
        ),
        "drawdown_lookback": FeatureSpec(
            name="drawdown_lookback",
            family="price",
            source_cols=("close",),
            formula_desc="close_t / rolling_max(close,63)_t - 1",
            anti_leakage_tag=_TRAILING,
            warmup_count=63,
            tft_typing=_UNKNOWN,
        ),
        "amihud_illiquidity_proxy": FeatureSpec(
            name="amihud_illiquidity_proxy",
            family="price",
            source_cols=("close", "volume"),
            formula_desc="abs(return_1d) / volume_t",
            anti_leakage_tag=_TRAILING,
            warmup_count=1,
            tft_typing=_UNKNOWN,
        ),
        "volume_zscore": FeatureSpec(
            name="volume_zscore",
            family="price",
            source_cols=("volume",),
            # warmup efetivo 20: estatistica trailing t-20..t-1 + numerador corrente.
            formula_desc="(volume_t - mean(volume_t-20..t-1)) / std(volume_t-20..t-1)",
            anti_leakage_tag=_TRAILING,
            warmup_count=20,
            tft_typing=_UNKNOWN,
        ),
        "volume_spike_flag": FeatureSpec(
            name="volume_spike_flag",
            family="price",
            source_cols=("volume",),
            formula_desc="1 if volume_zscore > 3 else 0",
            anti_leakage_tag=_TRAILING,
            warmup_count=20,
            tft_typing=_UNKNOWN,
            dtype="int64",
        ),
        # -- technical: volatilidades + regimes -------------------------------
        "volatility_parkinson": FeatureSpec(
            name="volatility_parkinson",
            family="technical",
            source_cols=("high", "low"),
            formula_desc="sqrt(rolling_mean((ln(high/low)^2),20)/(4*ln(2)))",
            anti_leakage_tag=_TRAILING,
            warmup_count=20,
            tft_typing=_UNKNOWN,
        ),
        "volatility_garman_klass": FeatureSpec(
            name="volatility_garman_klass",
            family="technical",
            source_cols=("open", "high", "low", "close"),
            formula_desc="sqrt(rolling_mean(0.5*ln(h/l)^2-(2ln2-1)*ln(c/o)^2,20))",
            anti_leakage_tag=_TRAILING,
            warmup_count=20,
            tft_typing=_UNKNOWN,
        ),
        "downside_semivolatility": FeatureSpec(
            name="downside_semivolatility",
            family="technical",
            source_cols=("close",),
            formula_desc="sqrt(rolling_mean(min(return_1d,0)^2,20))",
            anti_leakage_tag=_TRAILING,
            warmup_count=20,
            tft_typing=_UNKNOWN,
        ),
        "vol_of_vol": FeatureSpec(
            name="vol_of_vol",
            family="technical",
            source_cols=("volatility_20d",),
            # warmup efetivo 40 = 20 (volatility_20d ja consumidos) + 20 (janela std).
            formula_desc="rolling_std(volatility_20d,20)",
            anti_leakage_tag=_TRAILING,
            warmup_count=40,
            tft_typing=_UNKNOWN,
        ),
        "volatility_regime": FeatureSpec(
            name="volatility_regime",
            family="technical",
            source_cols=("volatility_20d",),
            formula_desc=(
                "Regime 0/1/2 from trailing terciles of volatility_20d (window 63, shifted)"
            ),
            anti_leakage_tag=_TRAILING,
            warmup_count=63,
            tft_typing=_UNKNOWN,
            dtype="int64",
        ),
        "trend_regime": FeatureSpec(
            name="trend_regime",
            family="technical",
            source_cols=("ema_10", "ema_50"),
            formula_desc=(
                "Regime -1/0/1 from EMA spread with trailing deadband (window 63, shifted)"
            ),
            anti_leakage_tag=_TRAILING,
            warmup_count=63,
            tft_typing=_UNKNOWN,
            dtype="int64",
        ),
        "stress_tail_return_flag": FeatureSpec(
            name="stress_tail_return_flag",
            family="technical",
            source_cols=("close",),
            formula_desc="Flag 1 when return_1d <= trailing q10(return_1d) over 63, shifted",
            anti_leakage_tag=_TRAILING,
            warmup_count=63,
            tft_typing=_UNKNOWN,
            dtype="int64",
        ),
        # -- sentiment: lags, ema, surprise, interacoes -----------------------
        "sentiment_lag_1": FeatureSpec(
            name="sentiment_lag_1",
            family="sentiment",
            source_cols=("sentiment_score",),
            formula_desc="sentiment_score shifted by 1",
            anti_leakage_tag=_LAGGED,
            warmup_count=1,
            tft_typing=_UNKNOWN,
        ),
        "sentiment_lag_3": FeatureSpec(
            name="sentiment_lag_3",
            family="sentiment",
            source_cols=("sentiment_score",),
            formula_desc="sentiment_score shifted by 3",
            anti_leakage_tag=_LAGGED,
            warmup_count=3,
            tft_typing=_UNKNOWN,
        ),
        "sentiment_lag_5": FeatureSpec(
            name="sentiment_lag_5",
            family="sentiment",
            source_cols=("sentiment_score",),
            formula_desc="sentiment_score shifted by 5",
            anti_leakage_tag=_LAGGED,
            warmup_count=5,
            tft_typing=_UNKNOWN,
        ),
        "sentiment_ema": FeatureSpec(
            name="sentiment_ema",
            family="sentiment",
            source_cols=("sentiment_score",),
            formula_desc="EMA(span=10) over sentiment_score",
            anti_leakage_tag=_TRAILING,
            warmup_count=1,
            tft_typing=_UNKNOWN,
        ),
        "sentiment_surprise": FeatureSpec(
            name="sentiment_surprise",
            family="sentiment",
            source_cols=("sentiment_score",),
            formula_desc="sentiment_score - trailing_mean(sentiment_score,5, shifted)",
            anti_leakage_tag=_TRAILING,
            warmup_count=5,
            tft_typing=_UNKNOWN,
        ),
        "sentiment_x_volatility": FeatureSpec(
            name="sentiment_x_volatility",
            family="sentiment",
            source_cols=("sentiment_score", "volatility_20d"),
            formula_desc="sentiment_score * volatility_20d",
            anti_leakage_tag=_TRAILING,
            warmup_count=20,
            tft_typing=_UNKNOWN,
        ),
        "sentiment_x_volume": FeatureSpec(
            name="sentiment_x_volume",
            family="sentiment",
            source_cols=("sentiment_score", "volume"),
            formula_desc="sentiment_score * volume",
            anti_leakage_tag=_TRAILING,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        # -- fundamental derivado + YoY ---------------------------------------
        "net_margin": FeatureSpec(
            name="net_margin",
            family="fundamental",
            source_cols=("net_income", "revenue"),
            formula_desc="net_income / revenue",
            anti_leakage_tag=_REP_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "leverage_ratio": FeatureSpec(
            name="leverage_ratio",
            family="fundamental",
            source_cols=("total_liabilities", "total_shareholder_equity"),
            formula_desc="total_liabilities / total_shareholder_equity",
            anti_leakage_tag=_REP_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "cashflow_efficiency": FeatureSpec(
            name="cashflow_efficiency",
            family="fundamental",
            source_cols=("operating_cash_flow", "revenue"),
            formula_desc="operating_cash_flow / revenue",
            anti_leakage_tag=_REP_ASOF,
            warmup_count=0,
            tft_typing=_UNKNOWN,
        ),
        "revenue_yoy_growth": FeatureSpec(
            name="revenue_yoy_growth",
            family="fundamental",
            source_cols=("revenue",),
            formula_desc="pct_change(revenue, 252) on as-of merged daily series",
            anti_leakage_tag=_REP_ASOF,
            warmup_count=252,
            tft_typing=_UNKNOWN,
        ),
        "net_income_yoy_growth": FeatureSpec(
            name="net_income_yoy_growth",
            family="fundamental",
            source_cols=("net_income",),
            formula_desc="pct_change(net_income, 252) on as-of merged daily series",
            anti_leakage_tag=_REP_ASOF,
            warmup_count=252,
            tft_typing=_UNKNOWN,
        ),
    }


def _build_registry() -> dict[str, FeatureSpec]:
    """Monta o dicionário completo de specs (base + ~38 derivadas)."""
    specs = _base_specs()
    specs.update(_derived_specs())
    return specs


FEATURE_SPECS: Mapping[str, FeatureSpec] = MappingProxyType(_build_registry())


def get_feature_spec(name: str) -> FeatureSpec:
    """Devolve o `FeatureSpec` de `name` (KeyError se ausente — análogo ao old)."""
    return FEATURE_SPECS[name]


def list_feature_specs(
    *,
    family: str | None = None,
    enabled_only: bool = False,
) -> list[FeatureSpec]:
    """Lista os specs, opcionalmente filtrando por `family` e/ou habilitados.

    Análogo a `list_feature_specs` do old (que filtrava por `group`); aqui filtra
    por `family` (taxonomia de 4 valores).
    """
    specs = list(FEATURE_SPECS.values())
    if family is not None:
        specs = [s for s in specs if s.family == family]
    if enabled_only:
        specs = [s for s in specs if s.enabled_by_default]
    return specs


def feature_set_hash(specs: Mapping[str, FeatureSpec] | None = None) -> str:
    """`sha256` determinístico do conteúdo dos specs ordenados por `name` (I5).

    Função PURA do conteúdo: mesmo set → mesmo hash (ordem de inserção irrelevante);
    perturbar QUALQUER campo de QUALQUER spec MUDA o hash. Postura idêntica a
    `indicator_registry_hash` (3.1) e `feature_registry_hash` do old (:471-491) —
    serializa cada spec numa string canônica delimitada por `|` cobrindo TODOS os
    campos, junta por `\\n`, `.encode("utf-8")` e aplica `sha256` (D3, ADR 1.4.0001;
    sem injetar o port `Hasher`, que vive em adapters/out e não pode ser importado
    pelo domínio).

    `specs` default = `FEATURE_SPECS`; aceita um registry alternativo (usado nos
    testes para provar que uma perturbação muda o hash).
    """
    registry = FEATURE_SPECS if specs is None else specs
    entries: list[str] = []
    for name in sorted(registry.keys()):
        s = registry[name]
        entries.append(
            "|".join(
                [
                    s.name,
                    s.family,
                    ",".join(s.source_cols),
                    s.formula_desc,
                    s.anti_leakage_tag,
                    str(s.warmup_count),
                    s.tft_typing,
                    s.null_policy,
                    s.dtype,
                    str(s.enabled_by_default),
                ]
            )
        )
    payload = "\n".join(entries).encode("utf-8")
    return sha256(payload).hexdigest()
