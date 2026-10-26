"""Teste opt-in: os números do relatório pós-veredito (D1 e D3) conferem com a geração julgada.

Fora do CI por construção, como a conferência C1 (`test_results_numbers.py`): lê a raiz de
dados do cohort confirmatório de `TCC_DATA_ROOT` (a pasta com `silver/`, `processed/` e
`gold/`, montada `:ro`); sem a variável, ou com caminho inexistente, **pula**.

Recalcula D1 e D3 por `tests.tcc.post_verdict_report.compute` — que para na sanidade se a
recomputação não bater com o gold julgado — e exige que o bloco entre os marcadores de
`docs/reports/post_verdict_analyses.md` seja exatamente o renderizado.

    TCC_DATA_ROOT=/data uv run --no-sync pytest tests/tcc/test_post_verdict_numbers.py -rs -q
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import pytest

from tests.tcc.post_verdict_report import (
    block_of,
    check_sanity,
    d1_rows,
    d3_rows,
    read_judged_inputs,
    render,
    sanity_checks,
)

_ROOT_VAR: Final = "TCC_DATA_ROOT"
_REPORT: Final = Path(__file__).parents[2] / "docs" / "reports" / "post_verdict_analyses.md"
_COMMON_POINTS: Final = {1: 1511, 7: 1505}
_SEED_MEAN_PINBALL_E3: Final = {1: "4.050", 7: "4.063"}


def test_report_block_matches_the_judged_generation() -> None:
    raw = os.environ.get(_ROOT_VAR)
    if not raw or not Path(raw).is_dir():
        pytest.skip(f"{_ROOT_VAR} ausente ou inexistente ({raw!r}): conferência opt-in")
    inputs = read_judged_inputs(Path(raw))
    checks = sanity_checks(inputs)
    check_sanity(checks)
    assert {h: s.n_common for h, s in inputs.samples.items()} == _COMMON_POINTS
    d3 = d3_rows(inputs)
    for row in d3:
        shown = f"{row.seed_mean_pinball * 1e3:.3f}"
        assert shown == _SEED_MEAN_PINBALL_E3[row.horizon], f"h+{row.horizon}: {shown}"
    rendered = render(inputs, d1_rows(inputs), d3, n_checks=len(checks))
    assert block_of(_REPORT.read_text(encoding="utf-8")) == rendered
