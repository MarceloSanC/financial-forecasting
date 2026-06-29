"""Adapter `DatasetAssembler` — engine física de montagem do dataset TFT (pandas).

ÚNICA casa de `pandas`/`pyarrow` na montagem do dataset (I6). Satisfaz o port
`DatasetAssemblerPort` por duck-typing. Decompõe o monólito do old
(`build_tft_dataset_use_case.py`, 418-624) na peça hexagonal correta: o use case
`BuildDataset` (application) só orquestra; AQUI mora a engine física (pandas), o
cálculo das derivadas (via o oráculo puro `DerivedFeatures` 3.4 — NÃO fórmula inline
em pandas, D3), os validadores anti-leakage in-process e a persistência Parquet.

Pipeline de montagem (concept 3.5 §4, ordem candles→grade→indicadores→sentimento→
derivadas→as-of→derivadas-de-fundamento→time-features):

1. candles ordenados por `timestamp` → base OHLCV + `asset_id`.
2. indicadores (3.1) alinhados por barra (`candle_*`/`rsi_14`/`macd*`/`ema_*`/
   `volatility_20d`).
3. sentimento diário (3.2) merge por dia de pregão; `news_volume`/`has_news` int,
   `sentiment_score`/`sentiment_std` float com `fillna(0.0)` (paridade old).
4. derivadas de preço/vol/regime/sentimento (3.4) computadas pelo oráculo puro
   `DerivedFeatures` sobre as sequências da base.
5. as-of (3.3) já vem pronto em `asof_rows` (1 linha por dia): fundamentos +
   `fundamentals_effective_date` + 3 ratios; derivadas YoY (3.4) computadas DEPOIS
   do as-of sobre a série diária alinhada.
6. time-features (`day_of_week`/`month`), alvo backward (`TargetDefinition`, dono
   único) com drop da 1ª linha, `time_idx`.

Validadores anti-leakage in-process (I2/I3/D3):

- **guarda as-of (I3/C3):** re-checa `fundamentals_effective_date <= day`;
  violação ⇒ `AntiLeakageError`.
- **invariante causal (I2/I4):** re-deriva cada feature derivada com o oráculo puro
  `DerivedFeatures` e confere contra a coluna montada (`atol ~1e-12`); divergência
  ⇒ `AntiLeakageError` nomeando a feature. O oráculo é a segunda implementação
  independente (ADR 0.0.0021), e como as janelas são trailing/shiftadas (`n>0`),
  anexar barras futuras não muda o prefixo (causalidade).

Ordem de colunas (I7): `timestamp`, `asset_id`, as 55 features na ORDEM do
`FeatureRegistry`, `fundamentals_effective_date`, `day_of_week`, `month`,
`target_return`, `time_idx` — 62 colunas (paridade de set/contagem com o oráculo;
ordem governada pelo registry, não pelo old).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblyInputs,
    DatasetAssemblyResult,
)
from financial_forecasting.features.feature_engineering.domain.services import (
    derived_features as df_,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    list_feature_specs,
)
from financial_forecasting.features.feature_engineering.domain.services.fundamentals_asof_policy import (  # noqa: E501
    AntiLeakageError,
)
from financial_forecasting.features.feature_engineering.domain.services.target_definition import (
    compute_target_return,
)

# Raiz default do dataset processado (espelha os demais writers processed, 2.2/2.3).
DEFAULT_DATASET_ROOT = Path("data/processed/dataset_tft")

# Tolerância de paridade montado↔oráculo (concept 3.5 I2).
_ATOL = 1e-9

# Colunas-base/identificador/alvo fora do set de feature (concept 3.5 §9).
_BASE_LEADING = ("timestamp", "asset_id")
_TAIL_COLUMNS = (
    "fundamentals_effective_date",
    "day_of_week",
    "month",
    "target_return",
    "time_idx",
)
_FUNDAMENTAL_BASE = (
    "revenue",
    "net_income",
    "operating_cash_flow",
    "total_shareholder_equity",
    "total_liabilities",
)


def _seq(frame: pd.DataFrame, col: str) -> list[float | None]:
    """Extrai uma coluna como `list[float | None]` (NaN → None) para o oráculo puro."""
    out: list[float | None] = []
    for value in frame[col].tolist():
        if value is None or (isinstance(value, float) and math.isnan(value)):
            out.append(None)
        else:
            out.append(float(value))
    return out


class DatasetAssembler:
    """Implementação real do `DatasetAssemblerPort` sobre pandas (concept 3.5 §4)."""

    def __init__(self, dataset_root: Path | str = DEFAULT_DATASET_ROOT) -> None:
        self._dataset_root = Path(dataset_root)
        # Retém o último frame montado por asset (entre assemble→persist).
        self._assembled: dict[str, pd.DataFrame] = {}

    # -- contrato ------------------------------------------------------------

    def assemble(self, inputs: DatasetAssemblyInputs) -> DatasetAssemblyResult:
        """Monta o dataset, aplica alvo + validadores anti-leakage; devolve contagens."""
        frame = self._build_frame(inputs)
        # Valida ANTES do drop da 1ª linha: o oráculo puro re-deriva sobre a MESMA
        # série de entrada que a montagem usou (full frame), conferindo posição a
        # posição (I2). Após validar, dropa a 1ª linha e numera o `time_idx`.
        self._validate_asof_guard(frame)
        self._validate_anti_leakage(frame)
        self._apply_target_and_drop(frame)
        ordered = self._order_columns(frame)
        self._assembled[inputs.asset] = ordered

        feature_columns = tuple(spec.name for spec in list_feature_specs())
        timestamps = ordered["timestamp"].tolist()
        feature_rows = tuple(
            {col: _none_if_nan(row[col]) for col in feature_columns}
            for _, row in ordered[list(feature_columns)].iterrows()
        )
        return DatasetAssemblyResult(
            n_rows=len(ordered),
            columns=tuple(ordered.columns),
            feature_columns=feature_columns,
            start=_to_date(timestamps[0]),
            end=_to_date(timestamps[-1]),
            timestamps=tuple(timestamps),
            feature_rows=feature_rows,
        )

    def persist(self, asset: str) -> None:
        """Persiste o último dataset montado de `asset` em Parquet (processed)."""
        frame = self._assembled.get(asset)
        if frame is None:
            raise ValueError(
                f"no assembled dataset retained for asset {asset!r}; call assemble first"
            )
        target_dir = self._dataset_root / asset
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"dataset_tft_{asset}.parquet"
        frame.to_parquet(path, index=False)

    # -- montagem ------------------------------------------------------------

    def _build_frame(self, inputs: DatasetAssemblyInputs) -> pd.DataFrame:
        """Monta o `DataFrame` completo na ordem candles→...→time-features→alvo."""
        frame = self._base_frame(inputs)
        self._attach_indicators(frame, inputs.indicators)
        self._attach_sentiment(frame, inputs.daily_sentiment)
        self._attach_price_derived(frame)
        self._attach_asof(frame, inputs.asof_rows)
        self._attach_fundamental_derived(frame)
        self._attach_time_features(frame)
        return frame

    @staticmethod
    def _base_frame(inputs: DatasetAssemblyInputs) -> pd.DataFrame:
        """Base OHLCV ordenada por `timestamp` + `asset_id` + `day` (chave de merge)."""
        frame = pd.DataFrame(list(inputs.candles))
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        frame["asset_id"] = inputs.asset
        for col in ("open", "high", "low", "close", "volume"):
            frame[col] = pd.to_numeric(frame[col], errors="raise").astype("float64")
        frame["day"] = frame["timestamp"].dt.normalize()
        return frame

    @staticmethod
    def _attach_indicators(frame: pd.DataFrame, indicators: Sequence[Mapping[str, object]]) -> None:
        """Anexa os indicadores (3.1) alinhados 1:1 por barra (ordem preservada)."""
        ind = pd.DataFrame(list(indicators))
        if len(ind) != len(frame):
            raise ValueError(
                f"indicators rows ({len(ind)}) must align 1:1 with candles ({len(frame)})"
            )
        for col in ind.columns:
            frame[col] = pd.to_numeric(ind[col].to_numpy(), errors="coerce").astype("float64")

    @staticmethod
    def _attach_sentiment(
        frame: pd.DataFrame, daily_sentiment: Sequence[Mapping[str, object]]
    ) -> None:
        """Merge do sentimento diário por dia de pregão (`fillna(0)` paridade old)."""
        if daily_sentiment:
            sent = pd.DataFrame(list(daily_sentiment))
            sent["day"] = pd.to_datetime(sent["day"], utc=True).dt.normalize()
            sent = sent[["day", "sentiment_score", "news_volume", "sentiment_std"]]
            merged = frame.merge(sent, on="day", how="left")
        else:
            merged = frame
            merged["sentiment_score"] = pd.NA
            merged["news_volume"] = pd.NA
            merged["sentiment_std"] = pd.NA
        frame["news_volume"] = (
            pd.to_numeric(merged["news_volume"], errors="coerce").fillna(0).astype("int64")
        )
        frame["has_news"] = (frame["news_volume"] > 0).astype("int64")
        frame["sentiment_score"] = (
            pd.to_numeric(merged["sentiment_score"], errors="coerce").fillna(0.0).astype("float64")
        )
        frame["sentiment_std"] = (
            pd.to_numeric(merged["sentiment_std"], errors="coerce").fillna(0.0).astype("float64")
        )

    def _attach_price_derived(self, frame: pd.DataFrame) -> None:
        """Derivadas de preço/vol/regime/sentimento via o oráculo puro `DerivedFeatures` (D3)."""
        for name, values in self._compute_derived(frame).items():
            frame[name] = _to_float_column(values)

    @staticmethod
    def _attach_asof(frame: pd.DataFrame, asof_rows: Sequence[Mapping[str, object]]) -> None:
        """Anexa o resultado as-of (3.3): 1 linha por dia, alinhado por `day`."""
        asof = pd.DataFrame(list(asof_rows))
        asof["day"] = pd.to_datetime(asof["day"], utc=True).dt.normalize()
        keep = [
            "day",
            "fundamentals_effective_date",
            *_FUNDAMENTAL_BASE,
            "net_margin",
            "leverage_ratio",
            "cashflow_efficiency",
        ]
        asof = asof[[c for c in keep if c in asof.columns]]
        merged = frame.merge(asof, on="day", how="left")
        for col in merged.columns:
            if col not in frame.columns:
                frame[col] = merged[col].to_numpy()
        frame["fundamentals_effective_date"] = pd.to_datetime(
            merged["fundamentals_effective_date"], utc=True
        ).to_numpy()
        for col in (*_FUNDAMENTAL_BASE, "net_margin", "leverage_ratio", "cashflow_efficiency"):
            frame[col] = pd.to_numeric(merged[col], errors="coerce").astype("float64").to_numpy()

    @staticmethod
    def _attach_fundamental_derived(frame: pd.DataFrame) -> None:
        """YoY de fundamento (3.4) DEPOIS do as-of (precisa da série diária alinhada)."""
        frame["revenue_yoy_growth"] = _to_float_column(
            df_.revenue_yoy_growth(_seq(frame, "revenue"))
        )
        frame["net_income_yoy_growth"] = _to_float_column(
            df_.net_income_yoy_growth(_seq(frame, "net_income"))
        )

    @staticmethod
    def _attach_time_features(frame: pd.DataFrame) -> None:
        """`day_of_week`/`month` + alvo backward (sem drop ainda — drop após validar)."""
        frame["day_of_week"] = frame["timestamp"].dt.dayofweek.astype("int64")
        frame["month"] = frame["timestamp"].dt.month.astype("int64")

        closes = [float(c) for c in frame["close"].tolist()]
        target = compute_target_return(closes)
        frame["target_return"] = [(math.nan if value is None else value) for value in target]

    @staticmethod
    def _apply_target_and_drop(frame: pd.DataFrame) -> None:
        """Dropa a 1ª linha (alvo `None`, ADR 3.5.0001) e numera `time_idx`."""
        frame.drop(index=frame.index[0], inplace=True)
        frame.reset_index(drop=True, inplace=True)
        if frame.empty:
            raise ValueError("not enough rows to compute target_return")
        frame["time_idx"] = range(len(frame))

    # -- derivadas (oráculo puro) -------------------------------------------

    @staticmethod
    def _compute_derived(frame: pd.DataFrame) -> dict[str, df_.OutSeq]:
        """Computa as ~33 derivadas de preço/vol/regime/sentimento via `DerivedFeatures`."""
        close = _seq(frame, "close")
        high = _seq(frame, "high")
        low = _seq(frame, "low")
        open_ = _seq(frame, "open")
        volume = _seq(frame, "volume")
        vol20 = _seq(frame, "volatility_20d")
        ema10 = _seq(frame, "ema_10")
        ema50 = _seq(frame, "ema_50")
        sentiment = _seq(frame, "sentiment_score")
        return {
            "log_return_1d": df_.log_return_1d(close),
            "log_return_5d": df_.log_return_5d(close),
            "log_return_21d": df_.log_return_21d(close),
            "momentum_5d": df_.momentum_5d(close),
            "momentum_21d": df_.momentum_21d(close),
            "momentum_63d": df_.momentum_63d(close),
            "reversal_1d": df_.reversal_1d(close),
            "reversal_5d": df_.reversal_5d(close),
            "drawdown_lookback": df_.drawdown_lookback(close),
            "amihud_illiquidity_proxy": df_.amihud_illiquidity_proxy(close, volume),
            "volume_zscore": df_.volume_zscore(volume),
            "volume_spike_flag": _int_seq(df_.volume_spike_flag(volume)),
            "volatility_parkinson": df_.volatility_parkinson(high, low),
            "volatility_garman_klass": df_.volatility_garman_klass(open_, high, low, close),
            "downside_semivolatility": df_.downside_semivolatility(close),
            "vol_of_vol": df_.vol_of_vol(vol20),
            "volatility_regime": _int_seq(df_.volatility_regime(vol20)),
            "trend_regime": _int_seq(df_.trend_regime(ema10, ema50)),
            "stress_tail_return_flag": _int_seq(df_.stress_tail_return_flag(close)),
            "sentiment_lag_1": df_.sentiment_lag_1(sentiment),
            "sentiment_lag_3": df_.sentiment_lag_3(sentiment),
            "sentiment_lag_5": df_.sentiment_lag_5(sentiment),
            "sentiment_ema": df_.sentiment_ema(sentiment),
            "sentiment_surprise": df_.sentiment_surprise(sentiment),
            "sentiment_x_volatility": df_.sentiment_x_volatility(sentiment, vol20),
            "sentiment_x_volume": df_.sentiment_x_volume(sentiment, volume),
        }

    # -- validadores anti-leakage --------------------------------------------

    @staticmethod
    def _validate_asof_guard(frame: pd.DataFrame) -> None:
        """I3/C3 — re-checa `fundamentals_effective_date <= day` no frame montado."""
        if "fundamentals_effective_date" not in frame.columns:
            return
        eff = frame["fundamentals_effective_date"]
        mask = eff.notna()
        if mask.any() and (eff[mask] > frame.loc[mask, "day"]).any():
            raise AntiLeakageError(
                "Anti-leakage violation: fundamentals_effective_date posterior to sample "
                "date (overview ADR 0.0.0018 regra 2)."
            )

    def _validate_anti_leakage(self, frame: pd.DataFrame) -> None:
        """I2/D3 — re-deriva cada derivada via o oráculo puro e confere (atol ~1e-9)."""
        oracle = self._compute_derived(frame)
        for name, expected in oracle.items():
            built = frame[name].tolist()
            if len(built) != len(expected):
                raise AntiLeakageError(
                    f"Anti-leakage validator: column {name!r} length {len(built)} "
                    f"!= oracle {len(expected)}"
                )
            for index, (b, e) in enumerate(zip(built, expected, strict=True)):
                if not _close(b, e):
                    raise AntiLeakageError(
                        f"Anti-leakage validator: column {name!r} diverges from pure oracle "
                        f"at row {index}: assembled={b!r} oracle={e!r} (atol={_ATOL})"
                    )

    # -- ordenação de colunas (I7) -------------------------------------------

    @staticmethod
    def _order_columns(frame: pd.DataFrame) -> pd.DataFrame:
        """Reordena pelas regras de I7: base + features do registry + cauda fixa."""
        feature_order = [spec.name for spec in list_feature_specs()]
        ordered_cols = [
            *_BASE_LEADING,
            *feature_order,
            *_TAIL_COLUMNS,
        ]
        missing = [c for c in ordered_cols if c not in frame.columns]
        if missing:
            raise ValueError(f"assembled frame is missing declared columns: {missing}")
        extra = [c for c in frame.columns if c not in ordered_cols and c != "day"]
        if extra:
            raise ValueError(f"assembled frame has unexpected extra columns: {extra}")
        return frame[ordered_cols].copy()


def _to_float_column(values: Sequence[float | int | None]) -> list[float]:
    """Converte uma `OutSeq` (com `None`) para `list[float]` com `NaN` no lugar de `None`."""
    return [math.nan if value is None else float(value) for value in values]


def _int_seq(values: Sequence[int | None]) -> tuple[float | None, ...]:
    """Normaliza saída discreta (int/None) à `OutSeq` float (D2: float64 com NaN)."""
    return tuple(None if value is None else float(value) for value in values)


def _close(built: object, expected: float | None) -> bool:
    """`True` se `built` casa `expected` dentro de `_ATOL` (NaN↔None contam como iguais)."""
    built_missing = built is None or (isinstance(built, float) and math.isnan(built))
    if expected is None:
        return built_missing
    if built_missing:
        return False
    return abs(float(built) - float(expected)) <= _ATOL  # type: ignore[arg-type]


def _to_date(value: object) -> date:
    """Coage um timestamp para `date` (`pd.Timestamp` é subclasse de `datetime`)."""
    if isinstance(value, datetime):
        return value.date()
    raise TypeError(f"cannot coerce {type(value).__name__} to date")


def _none_if_nan(value: object) -> object:
    """Normaliza `NaN`→`None` para o gate de domínio (primitivos, sem `DataFrame`)."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
