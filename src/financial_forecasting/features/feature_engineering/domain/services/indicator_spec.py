"""`IndicatorSpec` + `INDICATOR_SPECS` + `indicator_registry_hash()` (domínio puro).

Value-object de **domínio puro stdlib-only** do bounded context `feature_engineering`
(2º BC de feature). Molde reduzido do `FeatureSpec` rico do old
(`financial-time-series-forecasting/src/infrastructure/schemas/feature_registry.py:7-17`),
focado em indicador técnico — `name`, `family`, `source_cols`, `warmup`,
`anti_leakage_tag`, `dtype`. NÃO replica `null_policy`/`enabled_by_default`/`group`/
`formula_desc` ricos do old (isso é a Stage 3.4; concept 3.1 §1/§7 D2).

`INDICATOR_SPECS` é o registry estático dos indicadores (H-2, decisão humana fechada
no ledger: replicar o set EXATO do old, sem expansão). São **10 nomes de coluna** (= o
set `TECHNICAL_INDICATORS` do old); o concept fala em "11 indicadores" contando
`macd`/`macd_signal` como par (saem de uma chamada `ta.macd`, viram 2 colunas). Warmups
validados contra o `feature_registry.py` do old (concept 3.1 §4). `indicator_registry_hash()`
replica a postura de `feature_registry_hash` do old (:471-491): função pura do conteúdo
dos specs ordenados por nome (postura oráculo, ADR 0.0.0021).

Pureza (I1): importa SÓ stdlib (`dataclasses`/`hashlib`/`collections.abc`/`typing`).
`import pandas`/`pandas_ta_classic`/`numpy` aqui REPROVA `domain-purity` no import-linter
(concept 3.1 I1; provado por quebra intencional revertida na Task 08).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType

# Conjuntos permitidos (C1): blindam o registry contra valores fora de contrato.
_ALLOWED_DTYPES: frozenset[str] = frozenset({"float32"})
_ALLOWED_TAGS: frozenset[str] = frozenset({"trailing_window_causal", "same_timestamp_ohlc_derived"})


@dataclass(frozen=True)
class IndicatorSpec:
    """Especificação imutável de um indicador técnico (value-object de domínio).

    Campos (concept 3.1 §4):

    - `name`: identificador da coluna produzida (ex. `"rsi_14"`); não-vazio.
    - `family`: agrupamento conceitual (`momentum`/`trend`/`volatility`/`ohlc_derived`).
    - `source_cols`: colunas OHLCV de origem (ex. `("close",)`).
    - `warmup`: nº de barras de aquecimento (`>= 0`). É o TAMANHO da janela (paridade
      com o old); o warmup EFETIVO do `volatility_20d` é 21 (1 do `pct_change` + 20
      da janela `std`), documentado/validado na fixture-oráculo (I7/D6).
    - `anti_leakage_tag`: tag de causalidade obrigatória, em
      `{trailing_window_causal, same_timestamp_ohlc_derived}`.
    - `dtype`: tipo de saída, hoje só `"float32"` (I4; divergência intencional vs o
      `float64` do old).

    `__post_init__` valida os invariantes (C1) — violação levanta `ValueError`.
    """

    name: str
    family: str
    source_cols: tuple[str, ...]
    warmup: int
    anti_leakage_tag: str
    dtype: str = "float32"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("IndicatorSpec.name must be a non-empty string")
        if self.warmup < 0:
            raise ValueError(
                f"IndicatorSpec.warmup must be >= 0, got {self.warmup!r} for {self.name!r}"
            )
        if self.dtype not in _ALLOWED_DTYPES:
            raise ValueError(
                f"IndicatorSpec.dtype must be one of {sorted(_ALLOWED_DTYPES)}, "
                f"got {self.dtype!r} for {self.name!r}"
            )
        if self.anti_leakage_tag not in _ALLOWED_TAGS:
            raise ValueError(
                f"IndicatorSpec.anti_leakage_tag must be one of {sorted(_ALLOWED_TAGS)}, "
                f"got {self.anti_leakage_tag!r} for {self.name!r}"
            )


def _spec(
    name: str,
    family: str,
    source_cols: tuple[str, ...],
    warmup: int,
    anti_leakage_tag: str,
) -> IndicatorSpec:
    """Helper interno: monta um `IndicatorSpec` com `dtype='float32'` (default)."""
    return IndicatorSpec(
        name=name,
        family=family,
        source_cols=source_cols,
        warmup=warmup,
        anti_leakage_tag=anti_leakage_tag,
    )


# Registry estático dos indicadores (H-2). São 10 NOMES de coluna (= o set
# `TECHNICAL_INDICATORS` do old, autoridade da decisão humana fechada): o concept
# fala em "11 indicadores" porque conta `macd`/`macd_signal` como par; ambos saem de
# UMA chamada `ta.macd` mas viram 2 colunas distintas, totalizando 10 chaves. Warmups
# validados contra o `feature_registry.py` do old (concept 3.1 §4). É um
# `MappingProxyType` (read-only) para impedir mutação acidental do registry de domínio.
_TRAILING = "trailing_window_causal"
_OHLC = "same_timestamp_ohlc_derived"

INDICATOR_SPECS: Mapping[str, IndicatorSpec] = MappingProxyType(
    {
        "rsi_14": _spec("rsi_14", "momentum", ("close",), 14, _TRAILING),
        "macd": _spec("macd", "trend", ("close",), 26, _TRAILING),
        "macd_signal": _spec("macd_signal", "trend", ("close",), 35, _TRAILING),
        "ema_10": _spec("ema_10", "trend", ("close",), 10, _TRAILING),
        "ema_50": _spec("ema_50", "trend", ("close",), 50, _TRAILING),
        "ema_100": _spec("ema_100", "trend", ("close",), 100, _TRAILING),
        "ema_200": _spec("ema_200", "trend", ("close",), 200, _TRAILING),
        "volatility_20d": _spec("volatility_20d", "volatility", ("close",), 20, _TRAILING),
        "candle_range": _spec("candle_range", "ohlc_derived", ("high", "low"), 0, _OHLC),
        "candle_body": _spec("candle_body", "ohlc_derived", ("open", "close"), 0, _OHLC),
    }
)


def indicator_registry_hash(specs: Mapping[str, IndicatorSpec] | None = None) -> str:
    """`sha256` determinístico do conteúdo dos specs ordenados por `name` (I10).

    Função PURA do conteúdo: mesmo registry → mesmo hash; mudar `warmup`/`tag`/`dtype`/
    `family`/`source_cols` de qualquer spec MUDA o hash. Replica a postura de
    `feature_registry_hash` do old (:471-491) — serializa cada spec numa string
    canônica delimitada por `|`, junta por `\\n` e aplica `sha256` (postura oráculo,
    ADR 0.0.0021, reprodutibilidade).

    `specs` default = `INDICATOR_SPECS`; aceita um registry alternativo (usado nos
    testes para provar que uma perturbação muda o hash).
    """
    registry = INDICATOR_SPECS if specs is None else specs
    entries = []
    for name in sorted(registry.keys()):
        s = registry[name]
        entries.append(
            "|".join(
                [
                    s.name,
                    s.family,
                    ",".join(s.source_cols),
                    str(s.warmup),
                    s.anti_leakage_tag,
                    s.dtype,
                ]
            )
        )
    payload = "\n".join(entries).encode("utf-8")
    return sha256(payload).hexdigest()
