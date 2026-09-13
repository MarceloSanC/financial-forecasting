"""Contract test #72 — geometria warmup nominal vs efetivo no frame REAL montado.

Fixa o que o `DatasetQualityGate` ARMADO acusa quando recebe `feature_rows` do
`DatasetAssembler` real (pandas + oráculo `DerivedFeatures`) sobre candles sintéticos
determinísticos + `FakeIndicatorCalculator` (NaN durante o warmup nominal dos
indicadores, como o adapter 3.1). O gate desconta SÓ o `warmup_count` NOMINAL do
registry; toda feature cujo warmup EFETIVO excede o nominal aparece como missing
pós-warmup — é isso que um gate armado tem de revelar.

Medido (300 candles → 299 linhas pós-drop):

- `volatility_regime`: nominal 63, 1º finito na linha 82 → excesso **+19**
  (`volatility_20d` warmup 20 + shift(1) + rolling(63), menos o drop da 1ª linha).
- `trend_regime`: nominal 63, 1º finito na linha 112 → excesso **+49**
  (`ema_50` warmup 50 + shift(1) + rolling(63), idem).
- TODAS as outras 53 features: 1º finito `<=` nominal (a maioria a `-1`, pelo drop da
  1ª linha; `vol_of_vol` — o exemplo da issue — já declara 40 e mede 38).

Estes dois excessos são **débito de declaração do registry** (`warmup_count` nominal
< efetivo), registrados como `[finding]` na #72 e fora do escopo dela (reconciliar
churna `feature_set_hash`). Este teste é o sentinela: quando o registry for
reconciliado, a lista de excessos aqui esvazia e o teste deve ser atualizado.

O ratio é dependente de N (excesso absoluto / linhas pós-nominal): a 299 linhas os
dois excessos dão 0.0805 e 0.2076; no piloto AAPL (4023 linhas, ADR 3.5.0002) dão
0.0048 e 0.0124 — abaixo do limiar wireado 0.02, que por desenho tolera este débito
conhecido e reprova bloco estrutural de missing.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime, timedelta

import pytest

from financial_forecasting.composition_root import _DATASET_MAX_NAN_RATIO_PER_FEATURE
from financial_forecasting.features.feature_engineering.adapters.out.pandas.dataset_assembler import (  # noqa: E501
    DatasetAssembler,
)
from financial_forecasting.features.feature_engineering.application.ports.out.dataset_assembler import (  # noqa: E501
    DatasetAssemblyInputs,
    DatasetAssemblyResult,
)
from financial_forecasting.features.feature_engineering.domain.services.dataset_quality_gate import (  # noqa: E501
    DatasetQualityError,
    DatasetQualityGate,
    DatasetQualityGateConfig,
)
from financial_forecasting.features.feature_engineering.domain.services.feature_registry import (
    get_feature_spec,
)
from financial_forecasting.features.market_data.domain.entities.candle import Candle
from tests.fakes.features.feature_engineering.in_memory_indicator_calculator import (
    FakeIndicatorCalculator,
)

pytestmark = pytest.mark.contract

_N = 300  # > maior warmup (252 YoY): toda feature tem linhas pós-warmup avaliáveis
# Excesso MEDIDO de warmup efetivo sobre o nominal, por feature (linhas). Sentinela do
# finding #72 — esvazia quando o registry reconciliar `warmup_count`.
_KNOWN_EXCESS_WARMUP: dict[str, int] = {"volatility_regime": 19, "trend_regime": 49}
# Tamanho do piloto AAPL (oráculo 4023 x 62, ADR 3.5.0002) para a conta do limiar.
_PILOT_N_ROWS = 4023
_FAILING_ITEM = re.compile(r"(\w+): first finite at row (\d+) > warmup_count (\d+)")


def _synthetic_inputs(n: int = _N) -> DatasetAssemblyInputs:
    """Insumos sintéticos determinísticos (mesma forma dos contract tests do assembler)."""
    base = datetime(2020, 1, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for i in range(n):
        close = 100.0 + math.sin(i / 9.0) * 4.0 + i * 0.04
        candles.append(
            Candle(
                asset="AAPL",
                timestamp=base + timedelta(days=i),
                open=close - 0.3,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000 + i * 100,
            )
        )
    indicators = FakeIndicatorCalculator().calculate("AAPL", candles)
    days: list[date] = [c.timestamp.date() for c in candles]
    candle_rows = [
        {
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": float(c.volume),
        }
        for c in candles
    ]
    asof_rows = [
        {
            "day": day,
            "fundamentals_effective_date": day - timedelta(days=30),
            "revenue": 1000.0,
            "net_income": 100.0,
            "operating_cash_flow": 120.0,
            "total_shareholder_equity": 500.0,
            "total_liabilities": 250.0,
            "net_margin": 0.1,
            "leverage_ratio": 0.5,
            "cashflow_efficiency": 0.12,
        }
        for day in days
    ]
    return DatasetAssemblyInputs(
        asset="AAPL",
        candles=candle_rows,
        indicators=list(indicators),
        daily_sentiment=[],  # sem sentimento → fillna(0.0) (paridade old)
        asof_rows=asof_rows,
        grid_days=days,
    )


@pytest.fixture(scope="module")
def assembled() -> DatasetAssemblyResult:
    """Frame real montado UMA vez por módulo (pandas + oráculo puro das derivadas)."""
    return DatasetAssembler().assemble(_synthetic_inputs())


def _first_finite_index(result: DatasetAssemblyResult, col: str) -> int:
    """Índice (pós-drop) da 1ª linha com valor não-faltante de `col`; -1 se nunca."""
    for index, row in enumerate(result.feature_rows):
        if row.get(col) is not None:
            return index
    return -1


def _failing_from_message(message: str) -> dict[str, tuple[int, int]]:
    """Extrai `{feature: (1º finito, nominal)}` do detalhe da checagem absoluta (d)."""
    _, _, detail = message.partition("(desc): ")
    return {
        name: (int(first), int(nominal)) for name, first, nominal in _FAILING_ITEM.findall(detail)
    }


def test_only_known_features_have_effective_warmup_beyond_nominal(
    assembled: DatasetAssemblyResult,
) -> None:
    """Geometria — SÓ `volatility_regime`/`trend_regime` têm 1º finito além do nominal.

    Para cada feature do registry mede o 1º índice finito no frame real e compara com
    `warmup_count`. Excessos positivos devem ser EXATAMENTE os medidos (+19/+49);
    qualquer outra feature com excesso — ou uma feature nunca finita em 299 linhas —
    reprova (o registry passou a subdeclarar mais um warmup).
    """
    excess: dict[str, int] = {}
    for col in assembled.feature_columns:
        first = _first_finite_index(assembled, col)
        assert first >= 0, f"{col}: nunca finita em {assembled.n_rows} linhas"
        nominal = get_feature_spec(col).warmup_count
        if first > nominal:
            excess[col] = first - nominal

    assert excess == _KNOWN_EXCESS_WARMUP


def test_armed_gate_names_exactly_the_known_excess_features_on_real_frame(
    assembled: DatasetAssemblyResult,
) -> None:
    """A checagem absoluta (d) do gate acusa EXATAMENTE as duas no frame real, em desc.

    Com o ratio DESARMADO (`1.0`) — o instrumento que a auditoria do #80 apontou como
    errado para "warmup efetivo > nominal" — a checagem (d) nomeia nominal e efetivo de
    cada uma: `trend_regime` (+49) antes de `volatility_regime` (+19). Nenhuma outra
    feature aparece — as 53 restantes têm 1º finito `<=` nominal (o gate não está
    "preso em falha").
    """
    with pytest.raises(DatasetQualityError, match=r"^Effective warmup exceeds") as exc:
        DatasetQualityGate().validate(
            timestamps=list(assembled.timestamps),
            rows=list(assembled.feature_rows),
            feature_cols=list(assembled.feature_columns),
            config=DatasetQualityGateConfig(max_nan_ratio_per_feature=1.0),
        )

    failing = _failing_from_message(str(exc.value))
    expected = {
        name: (get_feature_spec(name).warmup_count + excess, get_feature_spec(name).warmup_count)
        for name, excess in _KNOWN_EXCESS_WARMUP.items()
    }
    assert failing == expected
    assert list(failing) == ["trend_regime", "volatility_regime"]  # ordem desc. por excesso


def test_gate_passes_real_frame_once_known_excess_is_declared(
    assembled: DatasetAssemblyResult,
) -> None:
    """Controle — descontado o excesso conhecido, nada mais no frame real dispara o gate.

    Isola a causa das reprovações no débito de declaração: só as `feature_columns` sem
    excesso, a 0.0 (o limiar mais estrito), passam nas duas checagens (d) e (a).
    """
    DatasetQualityGate().validate(
        timestamps=list(assembled.timestamps),
        rows=list(assembled.feature_rows),
        feature_cols=[col for col in assembled.feature_columns if col not in _KNOWN_EXCESS_WARMUP],
        config=DatasetQualityGateConfig(max_nan_ratio_per_feature=0.0),
    )


def test_wired_threshold_tolerates_known_excess_at_pilot_size() -> None:
    """Razão do 0.02 wireado, falsificável: no piloto (4023 linhas) o débito conhecido cabe.

    Excesso absoluto / linhas pós-nominal do piloto: `trend_regime` 49/3960 = 0.0124 e
    `volatility_regime` 19/3960 = 0.0048 — ambos `<` 0.02. Baixar o limiar (ex. 0.01)
    SEM reconciliar o registry faria o `BuildDataset` de AAPL reprovar por débito de
    declaração, não por missing real; este teste avisa antes.
    """
    nominal = get_feature_spec("trend_regime").warmup_count
    worst = max(excess / (_PILOT_N_ROWS - nominal) for excess in _KNOWN_EXCESS_WARMUP.values())

    assert worst < _DATASET_MAX_NAN_RATIO_PER_FEATURE
