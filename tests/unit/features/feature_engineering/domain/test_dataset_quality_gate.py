"""Testes de `DatasetQualityGate` (Task 02) — gate warmup-aware, stdlib-only.

Cobre concept 3.5 I5 / C4-C6:

- warmup-drop + NaN-ratio medido APÓS descontar o warmup do registry.
- C4: timestamp duplicado e não-monótono → `DatasetQualityError`.
- C5: NaN-ratio acima do limite, `failing_features` ordenado desc.
- C6: cobertura temporal insuficiente.
- happy path: dataset limpo passa.
- #72 (gate armado): `max_nan_ratio_per_feature` é OBRIGATÓRIO (sem default);
  controle — `1.0` nunca dispara (o defeito herdado, reproduzido); violação — acima do
  limiar ergue; abaixo e NO limiar (comparação estrita) não erguem; fora de `[0, 1]`
  é rejeitado na construção.
- #83 (checagem absoluta (d)): 1º valor finito em índice `> warmup_count` nominal ergue
  nomeando nominal e efetivo, ANTES do ratio e sem knob; feature nunca finita numa
  série mais longa que o nominal viola; série inteira dentro do nominal não é
  avaliada; excesso ordenado desc.; controle — 1º finito EXATAMENTE no nominal passa.
  Os testes de ratio modelam missing INTERIOR (pós-1º-finito): faltante à esquerda
  numa feature de warmup 0 é, por definição de (d), warmup subdeclarado.
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
    # sentiment_score (warmup 0): finita na linha 0 (dentro do nominal — a checagem
    # absoluta (d) passa), 19 NaN INTERIORES em 20 → ratio 0.95 (pior).
    rows = []
    for d in range(20):
        rows.append(
            {
                "rsi_14": (math.nan if d >= 14 and d < 17 else 1.0),  # noqa: PLR2004
                "sentiment_score": (0.1 if d == 0 else math.nan),
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
    # sentiment_score (0.95) deve vir ANTES de rsi_14 (0.5) — ordem desc.
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
            config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.0),
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
            config=DatasetQualityGateConfig(
                max_nan_ratio_per_feature=0.0, require_unique_timestamps=False
            ),
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
            config=DatasetQualityGateConfig(
                max_nan_ratio_per_feature=0.0, min_temporal_coverage_days=10
            ),
        )


def test_empty_dataset_fails_coverage() -> None:
    """Cobertura — dataset vazio tem span 0 dia < mínimo → `DatasetQualityError` (I5d).

    Exercita o branch de `timestamps` vazio (`coverage_days = 0`); uma mutação que
    retornasse cobertura default não-zero deixaria passar um dataset vazio.
    """
    gate = DatasetQualityGate()
    with pytest.raises(DatasetQualityError, match="Temporal coverage insufficient"):
        gate.validate(
            timestamps=[],
            rows=[],
            feature_cols=["rsi_14"],
            config=DatasetQualityGateConfig(
                max_nan_ratio_per_feature=0.0, min_temporal_coverage_days=1
            ),
        )


def test_length_mismatch_raises() -> None:
    """timestamps e rows de tamanhos diferentes levanta erro de domínio."""
    gate = DatasetQualityGate()
    with pytest.raises(DatasetQualityError, match="length mismatch"):
        gate.validate(
            timestamps=[_ts(0)],
            rows=[{"rsi_14": 1.0}, {"rsi_14": 2.0}],
            feature_cols=["rsi_14"],
            config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.0),
        )


# -- #72: gate armado — limiar obrigatório, controle e violação ---------------


def _rows_all_missing_after_warmup(n: int, col: str, warmup: int) -> list[dict[str, object]]:
    """`n` linhas: `col` finita no warmup e 100% faltante DEPOIS dele (pior caso)."""
    return [{col: (1.0 if d < warmup else math.nan)} for d in range(n)]


def test_ratio_threshold_is_required_no_inherited_default() -> None:
    """#72 — construir a config SEM limiar é rejeitado: o chamador declara o número.

    Antes do conserto `DatasetQualityGateConfig()` construía com `1.0` herdado do old —
    o gate nascia desarmado por omissão. Agora a omissão é um `TypeError`.
    """
    with pytest.raises(TypeError):
        DatasetQualityGateConfig()  # type: ignore[call-arg]


def test_threshold_one_never_fires_even_with_all_missing_control() -> None:
    """Controle #72 — com `1.0` a checagem NUNCA dispara (defeito reproduzido).

    Feature 100% faltante pós-warmup (`ratio == 1.0`) passa porque `1.0 > 1.0` é
    falso — `ratio ∈ [0, 1]` torna o limiar `1.0` inalcançável. É por isso que o
    default foi removido; `1.0` continua construível SÓ como desarme explícito.
    """
    n, warmup = 60, 14  # rsi_14
    gate = DatasetQualityGate()

    gate.validate(
        timestamps=[_ts(d) for d in range(n)],
        rows=_rows_all_missing_after_warmup(n, "rsi_14", warmup),
        feature_cols=["rsi_14"],
        config=DatasetQualityGateConfig(max_nan_ratio_per_feature=1.0),
    )


def test_ratio_above_threshold_raises_naming_feature_and_ratio() -> None:
    """#72 — feature com ratio acima do limiar ERGUE `DatasetQualityError` (C5).

    `sentiment_score` (warmup 0): 5 faltantes INTERIORES (linhas 50-54) em 100 → ratio
    0.05 > 0.02. Interior, não à esquerda: faltante à esquerda numa feature de warmup 0
    é warmup subdeclarado, e cai na checagem absoluta (d) antes do ratio (#83).
    """
    n = 100
    rows = [
        {"sentiment_score": (math.nan if 50 <= d < 55 else 0.1)}  # noqa: PLR2004
        for d in range(n)
    ]
    gate = DatasetQualityGate()

    with pytest.raises(
        DatasetQualityError, match=r"NaN-ratio above 0\.02.*sentiment_score=0\.0500"
    ):
        gate.validate(
            timestamps=[_ts(d) for d in range(n)],
            rows=rows,
            feature_cols=["sentiment_score"],
            config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.02),
        )


def test_ratio_below_threshold_passes_control() -> None:
    """Controle #72 — abaixo do limiar NÃO ergue: 1 faltante interior em 100 (0.01) com 0.02."""
    n = 100
    rows = [{"sentiment_score": (math.nan if d == 50 else 0.1)} for d in range(n)]  # noqa: PLR2004
    gate = DatasetQualityGate()

    gate.validate(
        timestamps=[_ts(d) for d in range(n)],
        rows=rows,
        feature_cols=["sentiment_score"],
        config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.02),
    )


def test_ratio_exactly_at_threshold_passes_strict_comparison() -> None:
    """#72 — NO limiar (ratio == max) passa: a comparação é estrita (`>`), como o old.

    2 faltantes interiores em 100 (0.02) com limiar 0.02 → passa; uma mutação `>=`
    reprovaria.
    """
    n = 100
    rows = [
        {"sentiment_score": (math.nan if 50 <= d < 52 else 0.1)}  # noqa: PLR2004
        for d in range(n)
    ]
    gate = DatasetQualityGate()

    gate.validate(
        timestamps=[_ts(d) for d in range(n)],
        rows=rows,
        feature_cols=["sentiment_score"],
        config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.02),
    )


@pytest.mark.parametrize("bad", [-0.01, 1.01, math.nan])
def test_threshold_outside_unit_interval_is_rejected(bad: float) -> None:
    """#72 — limiar fora de `[0, 1]` (ou NaN) é rejeitado: seria tão inalcançável quanto 1.0+."""
    with pytest.raises(ValueError, match="max_nan_ratio_per_feature"):
        DatasetQualityGateConfig(max_nan_ratio_per_feature=bad)


# -- #83: checagem absoluta (d) — warmup efetivo <= nominal ------------------


def _rows_first_finite_at(n: int, col: str, first_finite: int | None) -> list[dict[str, object]]:
    """`n` linhas: `col` faltante ANTES de `first_finite`, finita a partir dele (`None` = nunca)."""
    return [
        {col: (math.nan if first_finite is None or d < first_finite else 1.0)} for d in range(n)
    ]


def test_first_finite_beyond_nominal_warmup_raises_naming_nominal_and_effective() -> None:
    """#83 — 1º finito em índice > `warmup_count` ergue nomeando nominal e efetivo (d).

    `rsi_14` (nominal 14) finita só a partir da linha 20 em 100 → excesso de 6 linhas.
    A mensagem carrega o índice medido e o nominal (é o que se corrige no registry),
    e a violação ergue mesmo com o ratio DESARMADO (`1.0`): (d) é absoluta e sem knob —
    o ratio de 6/86 = 0.07 passaria a 0.1, e é exatamente por isso que (d) existe.
    """
    n = 100
    gate = DatasetQualityGate()

    with pytest.raises(
        DatasetQualityError,
        match=r"Effective warmup exceeds declared warmup_count.*rsi_14: first finite at row 20"
        r" > warmup_count 14",
    ):
        gate.validate(
            timestamps=[_ts(d) for d in range(n)],
            rows=_rows_first_finite_at(n, "rsi_14", 20),
            feature_cols=["rsi_14"],
            config=DatasetQualityGateConfig(max_nan_ratio_per_feature=1.0),
        )


def test_first_finite_exactly_at_nominal_warmup_passes_control() -> None:
    """Controle #83 — 1º finito EXATAMENTE no nominal (`<=`, não `<`) passa a 0.0.

    `rsi_14` finita a partir da linha 14 (nominal 14): (d) passa e o ratio pós-warmup é
    0. Uma mutação `>=` na comparação reprovaria aqui; uma que ignorasse (d) passaria
    no teste anterior.
    """
    n = 100
    gate = DatasetQualityGate()

    gate.validate(
        timestamps=[_ts(d) for d in range(n)],
        rows=_rows_first_finite_at(n, "rsi_14", 14),
        feature_cols=["rsi_14"],
        config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.0),
    )


def test_never_finite_feature_longer_than_nominal_violates_effective_warmup() -> None:
    """#83 — feature NUNCA finita numa série mais longa que o nominal viola (d).

    `rsi_14` 100% faltante em 100 linhas (nominal 14): o warmup efetivo é `>= 100 > 14`.
    Ergue mesmo com o ratio desarmado (`1.0`) — antes da #83 este caso passava com
    `1.0`, porque o ratio `1.0 > 1.0` é falso.
    """
    n = 100
    gate = DatasetQualityGate()

    with pytest.raises(
        DatasetQualityError, match=r"rsi_14: never finite in 100 rows > warmup_count 14"
    ):
        gate.validate(
            timestamps=[_ts(d) for d in range(n)],
            rows=_rows_first_finite_at(n, "rsi_14", None),
            feature_cols=["rsi_14"],
            config=DatasetQualityGateConfig(max_nan_ratio_per_feature=1.0),
        )


def test_series_entirely_within_nominal_warmup_is_not_evaluated() -> None:
    """#83 — série inteira dentro do warmup declarado não é avaliável por (d).

    `macd` (nominal 26) nunca finita em 20 linhas: não há como saber se o efetivo
    excede 26 — paridade com "série vazia pós-warmup → não avaliada" do ratio (a).
    Uma mutação que avaliasse `len(rows) <= nominal` reprovaria todo dataset curto.
    """
    n = 20
    gate = DatasetQualityGate()

    gate.validate(
        timestamps=[_ts(d) for d in range(n)],
        rows=_rows_first_finite_at(n, "macd", None),
        feature_cols=["macd"],
        config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.0),
    )


def test_effective_warmup_violations_ordered_by_excess_desc_and_before_ratio() -> None:
    """#83 — (d) lista TODAS as violações em ordem desc. de excesso e roda ANTES de (a).

    `ema_50` (nominal 50) finita na 60 (+10) e `rsi_14` (nominal 14) na 40 (+26):
    `rsi_14` vem antes. `sentiment_score` (nominal 0) com missing interior acima do
    limiar NÃO aparece: (d) ergue antes de o ratio ser medido — a mensagem é a de (d).
    """
    n = 100
    rows = [
        {
            "ema_50": (math.nan if d < 60 else 1.0),  # noqa: PLR2004
            "rsi_14": (math.nan if d < 40 else 1.0),  # noqa: PLR2004
            "sentiment_score": (math.nan if 50 <= d < 60 else 0.1),  # noqa: PLR2004
        }
        for d in range(n)
    ]
    gate = DatasetQualityGate()

    with pytest.raises(DatasetQualityError, match=r"^Effective warmup exceeds") as exc:
        gate.validate(
            timestamps=[_ts(d) for d in range(n)],
            rows=rows,
            feature_cols=["ema_50", "rsi_14", "sentiment_score"],
            config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.02),
        )
    message = str(exc.value)
    assert message.index("rsi_14: first finite at row 40 > warmup_count 14") < message.index(
        "ema_50: first finite at row 60 > warmup_count 50"
    )
    assert "sentiment_score" not in message
