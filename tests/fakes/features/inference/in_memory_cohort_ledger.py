"""Fake in-memory do port `CohortLedger` do `inference` (Stage 7.1).

Subclasse fina do `InMemoryCohortProgressLedger` do `modeling`: o port do
`inference` é um subconjunto exato daquele, então lock, `break_stale` e ambiente
vêm do fake existente (os testes gravam o ambiente pelo `record_environment`
herdado). O nome existe para o `check_port_coverage.py` e para tipar pelo port
do `inference` — duplicar o corpo seria uma segunda definição do mesmo dublê.
"""

from __future__ import annotations

from tests.fakes.features.modeling.in_memory_cohort_progress_ledger import (
    InMemoryCohortProgressLedger,
)


class InMemoryCohortLedger(InMemoryCohortProgressLedger):
    """`InMemoryCohortProgressLedger` visto pelo port `CohortLedger` do `inference`."""
