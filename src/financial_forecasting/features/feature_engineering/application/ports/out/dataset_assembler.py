"""Port-out `DatasetAssemblerPort` (`Protocol`) — montagem física do dataset TFT.

`DatasetAssemblerPort` é o port secundário (driven) do bounded context
`feature_engineering` que abstrai a **engine física** de montagem do dataset TFT
(pandas/duckdb) e os **validadores anti-leakage in-process** que ela hospeda. O use
case `BuildDataset` (3.5 Task 05) depende SÓ deste `Protocol` — não monta nada, só
orquestra: passa os insumos primitivos das 4 famílias + a grade de pregão e recebe
o número de linhas montadas; a persistência física é delegada a `persist`.

I6/I7 — a fronteira do port é **só** `collections.abc`/primitivos: NUNCA cruza um
`DataFrame`. Os insumos chegam como `Sequence[Mapping[str, object]]` (1 linha por
barra/dia), agnósticos de pandas. `pandas`/`pyarrow`/`duckdb` vivem APENAS no adapter
`adapters/out/pandas/`; o gate `import-linter` `store-no-storage-leak` reprova se
vazarem para `application`/`domain`.

A separação engine (adapter) ↔ orquestração (use case puro) decompõe o monólito
não-hexagonal do old (`build_tft_dataset_use_case.py`, 418-624), onde montagem
física, alvo inline, validação e gate estavam misturados (concept 3.5 D5 / ADR
0.0.0022).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

# Uma linha na fronteira do port: registro chave→valor (sem DataFrame, I7).
Row = Mapping[str, object]


@dataclass(frozen=True)
class DatasetAssemblyInputs:
    """Insumos primitivos das 4 famílias + grade, alinhados por barra/dia (I7).

    DTO frozen agnóstico de pandas. O use case popula a partir dos ports
    consumidos (3.1/3.2/3.3/2.1/2.4); o adapter consome e monta o `DataFrame`
    internamente.

    - `asset`: símbolo do ativo (vai para `asset_id`).
    - `candles`: 1 `Row` por barra com `timestamp` (tz-aware) + OHLCV; ordenadas
      por timestamp pelo adapter (I9 herdado de 3.1).
    - `indicators`: 1 `Row` por barra (alinhada a `candles`) com as colunas de
      `INDICATOR_SPECS` (3.1).
    - `daily_sentiment`: 1 `Row` por dia de pregão com `day`/`sentiment_score`/
      `news_volume`/`sentiment_std` (3.2 `DailySentimentDTO`); pode ser vazia.
    - `asof_rows`: 1 `Row` por dia da grade (3.3 `AsofJoinAdapter`), já com
      `fundamentals_effective_date` + campos fundamentais + 3 ratios.
    - `grid_days`: a grade densa de dias de pregão (3.2/2.4), alinhada a `asof_rows`.
    """

    asset: str
    candles: Sequence[Row]
    indicators: Sequence[Row]
    daily_sentiment: Sequence[Row]
    asof_rows: Sequence[Row]
    grid_days: Sequence[date]


@dataclass(frozen=True)
class DatasetAssemblyResult:
    """Resultado da montagem (sem vazar `DataFrame`): contagens + ordem de colunas.

    - `n_rows`: linhas do dataset montado (após dropar a 1ª linha do alvo).
    - `columns`: ordem final das colunas (base + features do registry + alvo/idx).
    - `feature_columns`: subset de colunas de feature (set/ordem do `FeatureRegistry`).
    - `start`/`end`: 1ª e última `date` do dataset (do `timestamp` normalizado).
    """

    n_rows: int
    columns: tuple[str, ...]
    feature_columns: tuple[str, ...]
    start: date
    end: date


class DatasetAssemblerPort(Protocol):
    """Contrato de montagem física + validação anti-leakage + persistência.

    Semântica garantida por qualquer implementação (concept 3.5 §4 / I2-I4, I7):

    - **Montagem** na ordem candles→grade→indicadores→sentimento→derivadas→as-of→
      derivadas-de-fundamento→time-features; reordena as colunas de feature pela
      ordem do `FeatureRegistry` antes de devolver (I7).
    - **Alvo** backward log-return aplicado via `TargetDefinition` (dono único); a
      1ª linha (alvo `None`) é dropada.
    - **Anti-leakage (I2/C2):** re-deriva CADA feature via `DerivedFeatures` (3.4) +
      indicadores canônicos (3.1) como oráculo puro e confere contra o valor montado
      (`atol ~1e-12`); divergência ⇒ `AntiLeakageError` nomeando a feature.
    - **Guarda as-of (I3/C3):** re-checa `fundamentals_effective_date <= day`;
      violação ⇒ `AntiLeakageError`.
    - **Schema** pandera validado antes de devolver/persistir (C7).
    """

    def assemble(self, inputs: DatasetAssemblyInputs) -> DatasetAssemblyResult:
        """Monta o dataset, aplica alvo + validadores anti-leakage + schema.

        Devolve contagens/ordem de colunas — NUNCA um `DataFrame` (I7). O frame
        montado fica retido internamente para um `persist` subsequente da MESMA
        montagem (idempotente por `asset`).
        """
        ...

    def persist(self, asset: str) -> None:
        """Persiste o último dataset montado de `asset` (Parquet processed).

        Separado de `assemble` para manter a orquestração testável sem I/O e a
        engine física (pandas/pyarrow) confinada ao adapter (I6).
        """
        ...
