"""Testes de `DatasetQualityGate` (Task 02) — gate warmup-aware, stdlib-only.

Cobre concept 3.5 I5 / C4-C6:

- warmup-drop + NaN-ratio medido APÓS descontar o warmup do registry.
- C4: timestamp duplicado e não-monótono → `DatasetQualityError`.
- C5: NaN-ratio acima do limite, `failing_features` ordenado desc.
- C6: cobertura temporal insuficiente.
- happy path: dataset limpo passa.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from financial_forecasting.features.feature_engineering.domain.services.dataset_quality_gate import (  # noqa: E501
    DatasetQualityError,
    DatasetQualityGate,
    DatasetQualityGateConfig,
)


def _ts(day: int) -> datetime:
    """Timestamp UTC a `day` dias de 2024-01-01."""
    return datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=day)


def test_happy_path_clean_dataset_passes() -> None:
    """Dataset com features finitas pós-warmup e timestamps monótonos passa."""
    timestamps = [_ts(d) for d in range(300)]
    # `rsi_14` (warmup 14): NaN nas 14 primeiras, finito depois.
    rows = [
        {"rsi_14": (math.nan if d < 14 else 50.0 + d)}  # noqa: PLR2004
        for d in range(300)
    ]
    gate = DatasetQualityGate()

    gate.validate(
        timestamps=timestamps,
        rows=rows,
        feature_cols=["rsi_14"],
        config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.0),
    )


def test_warmup_is_discounted_before_measuring_nan_ratio() -> None:
    """NaN durante o warmup não conta; só o pós-warmup é medido (I5a)."""
    # `ema_50` (warmup 50): 50 NaN no warmup, depois finito → ratio pós-warmup = 0.
    timestamps = [_ts(d) for d in range(120)]
    rows = [{"ema_50": (math.nan if d < 50 else 1.0)} for d in range(120)]  # noqa: PLR2004
    gate = DatasetQualityGate()

    # max=0.0: passaria SÓ se o warmup for descontado (senão 50/120 > 0).
    gate.validate(
        timestamps=timestamps,
        rows=rows,
        feature_cols=["ema_50"],
        config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.0),
    )


def test_nan_after_warmup_above_limit_raises_c5_with_desc_order() -> None:
    """C5 — NaN pós-warmup acima do limite levanta erro com features desc."""
    timestamps = [_ts(d) for d in range(20)]
    # rsi_14 (warmup 14): 6 pós-warmup, 3 NaN → ratio 0.5.
    # macd (warmup 26 > n): série vazia pós-warmup → não avaliada.
    # volume_zscore (warmup 20 == n): vazia → não avaliada.
    # sentiment_score (warmup 0): 20 valores, 20 NaN → ratio 1.0 (pior).
    rows = []
    for d in range(20):
        rows.append(
            {
                "rsi_14": (math.nan if d >= 14 and d < 17 else 1.0),  # noqa: PLR2004
                "sentiment_score": math.nan,
            }
        )
    gate = DatasetQualityGate()

    with pytest.raises(DatasetQualityError) as exc:
        gate.validate(
            timestamps=timestamps,
            rows=rows,
            feature_cols=["rsi_14", "sentiment_score"],
            config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.1),
        )
    message = str(exc.value)
    # sentiment_score (1.0) deve vir ANTES de rsi_14 (0.5) — ordem desc.
    assert message.index("sentiment_score") < message.index("rsi_14")


def test_duplicate_timestamps_raises_c4() -> None:
    """C4 — timestamp duplicado levanta `DatasetQualityError`."""
    timestamps = [_ts(0), _ts(1), _ts(1)]
    rows = [{"rsi_14": 1.0} for _ in range(3)]
    gate = DatasetQualityGate()

    with pytest.raises(DatasetQualityError, match="Duplicate timestamps"):
        gate.validate(
            timestamps=timestamps,
            rows=rows,
            feature_cols=["rsi_14"],
            config=DatasetQualityGateConfig(),
        )


def test_non_monotonic_timestamps_raises_c4() -> None:
    """C4 — timestamp fora de ordem levanta `DatasetQualityError`."""
    timestamps = [_ts(0), _ts(2), _ts(1)]
    rows = [{"rsi_14": 1.0} for _ in range(3)]
    gate = DatasetQualityGate()

    with pytest.raises(DatasetQualityError, match="not monotonic"):
        gate.validate(
            timestamps=timestamps,
            rows=rows,
            feature_cols=["rsi_14"],
            config=DatasetQualityGateConfig(require_unique_timestamps=False),
        )


def test_insufficient_temporal_coverage_raises_c6() -> None:
    """C6 — span de dias abaixo do mínimo levanta `DatasetQualityError`."""
    timestamps = [_ts(0), _ts(1), _ts(2)]  # span = 3 dias
    rows = [{"rsi_14": 1.0} for _ in range(3)]
    gate = DatasetQualityGate()

    with pytest.raises(DatasetQualityError, match="Temporal coverage insufficient"):
        gate.validate(
            timestamps=timestamps,
            rows=rows,
            feature_cols=["rsi_14"],
            config=DatasetQualityGateConfig(min_temporal_coverage_days=10),
        )


def test_length_mismatch_raises() -> None:
    """timestamps e rows de tamanhos diferentes levanta erro de domínio."""
    gate = DatasetQualityGate()
    with pytest.raises(DatasetQualityError, match="length mismatch"):
        gate.validate(
            timestamps=[_ts(0)],
            rows=[{"rsi_14": 1.0}, {"rsi_14": 2.0}],
            feature_cols=["rsi_14"],
            config=DatasetQualityGateConfig(),
        )
