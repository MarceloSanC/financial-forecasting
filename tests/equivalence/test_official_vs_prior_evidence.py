"""Teste opt-in da equivalência: partição oficial contra a evidência anterior (Stage 8.2, A13).

Fora do CI por construção (ADR 8.2.0003 itens 3-6): lê as raízes de
`EQUIVALENCE_ORACLE_ROOT` (o `data/analytics/` do anterior) e `EQUIVALENCE_OFFICIAL_ROOT` (a
partição viva `data/cohorts/aapl`, montada `:ro`); sem elas, ou com caminho inexistente,
**pula** com o motivo e o caminho do registro (ver com `-rs`). Com elas, confere o registro
(arquivo diferente ou ausente **falha**, nunca pula), recalcula a tabela e afirma:

1. a classificação recomputada = `DECLARED` (declarada aqui, vazia até a E5 — com o oráculo e
   `DECLARED` vazio o teste falha);
2. `DECLARED` = a tabela parseada de `docs/reports/equivalence_audit.md` (editar um sem o
   outro falha, com o diff visível).

Nunca escreve o registro nem o relatório.

    EQUIVALENCE_ORACLE_ROOT=/oracle EQUIVALENCE_OFFICIAL_ROOT=/official \\
        uv run --no-sync pytest tests/equivalence/test_official_vs_prior_evidence.py -rs -q
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import pytest

from tests.equivalence.audit_table import Declared, classification, compute, declared_diff, parse
from tests.equivalence.prior_evidence import REGISTRY_PATH

pytestmark = pytest.mark.integration

ORACLE_ENV: Final = "EQUIVALENCE_ORACLE_ROOT"
OFFICIAL_ENV: Final = "EQUIVALENCE_OFFICIAL_ROOT"
REPORT_PATH: Final = REGISTRY_PATH.parent / "equivalence_audit.md"

DECLARED: Final[tuple[Declared, ...]] = ()
"""A classificação declarada (id, status) — preenchida só na E5, depois da E4."""


def _root(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value or not Path(value).is_dir():
        return None
    return Path(value)


def test_official_vs_prior_evidence() -> None:
    oracle, official = _root(ORACLE_ENV), _root(OFFICIAL_ENV)
    if oracle is None or official is None:
        pytest.skip(
            f"opt-in: set {ORACLE_ENV} and {OFFICIAL_ENV} to existing directories; the prior "
            f"evidence is checked against {REGISTRY_PATH.relative_to(REGISTRY_PATH.parents[2])}"
        )

    recomputed = classification(compute(oracle, official))

    assert recomputed == DECLARED, declared_diff(DECLARED, recomputed)
    parsed = parse(REPORT_PATH.read_text(encoding="utf-8"))
    assert parsed == DECLARED, declared_diff(DECLARED, parsed)
