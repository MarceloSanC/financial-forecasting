"""Port-out `AsofJoinAdapter` (`Protocol`) — junção as-of backward de fundamentos.

`AsofJoinAdapter` é o port secundário (driven) do bounded context
`feature_engineering` para a junção as-of: abstrai o **as-of backward** dos
fundamentos sobre a grade diária de pregão, traduzido do
`pandas.merge_asof(direction="backward")` do old
(`build_tft_dataset_use_case.py:513-535`). A `application`/`domain` depende SÓ deste
`Protocol` estrutural; o adapter concreto (`AsofJoinDuckdbAdapter`, Task 04) o
satisfaz por duck-typing (NÃO herda da `application`), assim como o fake
(`InMemoryAsofJoinAdapter`, Task 03) — base do contract test de paridade fake↔real
(ADR 0.0.0021).

`Protocol` (não ABC) é a postura hexagonal do projeto (`hex-arch-python`, LAYOUT
§3), idêntica a `IndicatorCalculator`/`SentimentModel` (3.1/3.2), `MedallionStore`
(2.1) e `ExperimentTracker` (1.5).

I7 — a fronteira do port é só `collections.abc`/primitivos: troca
`Sequence[date]` (grade de pregão) + `Sequence[Mapping]` (reports já com
`effective_date` calculado pela `FundamentalsAsofPolicy`) → `Sequence[Mapping]` (1
linha por dia). `duckdb`/`pandas` NUNCA cruzam a fronteira — vivem APENAS no adapter
`adapters/out/duckdb/`; o gate `import-linter` `store-no-storage-leak` reprova se
vazarem para `application`/`domain` (concept 3.3 I5/I7/D5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Protocol

# Linha (na fronteira do port): primitivos apenas — sem entity/duckdb/pandas (I7).
Row = Mapping[str, object]


class AsofJoinAdapter(Protocol):
    """Contrato de as-of backward de fundamentos, agnóstico de biblioteca de dados.

    Semântica garantida por qualquer implementação (concept 3.3 §4/§5):

    - **I3 — visibilidade as-of backward:** devolve **1 linha por dia** de
      `grid_days` (ordem preservada); cada dia recebe o **último** `report` cujo
      `effective_date <= day` (semântica `direction="backward"` /
      `ASOF JOIN ON d.date >= f.effective_date`). Um fundamento só é visível a
      partir do seu `effective_date`, **nunca antes**.
    - **Entrada:** cada `report` de `reports` traz a chave `effective_date` (uma
      `date`, já calculada pela `FundamentalsAsofPolicy` a montante — I2) + os campos
      fundamentais (`revenue`/`net_income`/...).
    - **I8 — coluna de auditoria:** a saída expõe `fundamentals_effective_date`
      (rastreabilidade da origem do fundamento, `<= day`); o nome interno
      `effective_date` **nunca** é exposto.
    - **I1 — anti-leakage (defense-in-depth):** re-checa `effective_date <= day` e
      levanta `AntiLeakageError` se violado, mesmo a condição do join já garantindo-o.
    - **C4 — dia sem fundamento elegível:** linha do dia com os campos fundamentais
      e `fundamentals_effective_date` em `None` (não inventa valor, não levanta erro).
    - **I7 — fronteira sem libs de dados:** `duckdb`/`pandas` não cruzam a fronteira.
    """

    def asof_join_backward(
        self,
        *,
        grid_days: Sequence[date],
        reports: Sequence[Row],
    ) -> Sequence[Row]:
        """As-of backward: 1 linha por dia de `grid_days` com o último fundamento
        cujo `effective_date <= day`; saída com `fundamentals_effective_date` (I3/I8)."""
        ...
