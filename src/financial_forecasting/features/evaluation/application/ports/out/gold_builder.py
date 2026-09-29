"""Port-out `GoldBuilder` — mapeia os resultados de um refresh numa tabela gold (ADR 6.4.0001).

Protocol estrutural (concept 6.4 §4 "Application", D7, I14, I17). Cada builder declara
o próprio `name`, as dependências (`depends_on`, nomes de outros builders) e se roda
com o refresh bloqueado (`runs_when_blocked`); a ordem de execução sai do
`gold_build_order` (domínio) sobre essas declarações, validada no construtor do use
case. Os reais moram em `adapters/out/duckdb/gold_builders/`; o fake é o
`FakeGoldBuilder` (`tests/fakes/features/evaluation/fake_gold_builder.py`).

Contrato de `build(inputs)`:

- **mapeamento puro:** só lê os `GoldInputs` (relatórios já calculados pelo domínio) e
  devolve um `GoldTable` — nenhuma fórmula, nenhum estado compartilhado entre builders,
  nenhuma leitura de outro builder; mesmos `inputs` → mesma tabela;
- a tabela chama-se `gold_<name>` e as linhas vêm ordenadas pela chave (dono: o
  `GoldTable`);
- toda linha carrega `asset` e `parent_sweep_id` da partição; as tabelas confirmatórias
  (builders que **não** rodam bloqueados) carregam também `preregistration_ref`
  (ADR 6.4.0006 item 4);
- builder `runs_when_blocked` constrói também sobre os `GoldInputs` de um refresh
  `BLOCKED` (sem relatórios).
"""

from __future__ import annotations

from typing import Protocol

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)


class GoldBuilder(Protocol):
    """Um builder de tabela gold, com as dependências declaradas."""

    @property
    def name(self) -> str:
        """Nome do builder (a tabela é `gold_<name>`)."""
        ...

    @property
    def depends_on(self) -> frozenset[str]:
        """Nomes dos builders que precisam rodar antes deste."""
        ...

    @property
    def runs_when_blocked(self) -> bool:
        """`True` se a tabela também é publicada num refresh `BLOCKED`."""
        ...

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Mapeia os `inputs` na tabela `gold_<name>` (mapeamento puro)."""
        ...
