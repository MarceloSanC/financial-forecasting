"""Contract test do port `GoldBuilder` — suíte ÚNICA para o fake e os builders reais.

Prova (concept 6.4 A8, I14, I17; ADR 6.4.0001) que todo builder é um **mapeamento
puro**: `build` duas vezes com os mesmos `GoldInputs` dá tabelas iguais e não toca os
inputs; a tabela chama-se `gold_<name>`; toda linha carrega `asset`/`parent_sweep_id`
da partição; as confirmatórias (builders que não rodam bloqueados) carregam
`preregistration_ref` em toda linha; um builder `runs_when_blocked` constrói sobre os
`GoldInputs` de um refresh `BLOCKED`; `depends_on` não contém o próprio nome.

Os `GoldInputs` vêm de `_gold_inputs.py` (só domínio + `FakeMcsBackend`). Perna `fake`
nesta Task; a Task 10 acrescenta um id por builder real, sem `skipif`.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.application.ports.out.gold_builder import (
    GoldBuilder,
)
from tests.contract.features.evaluation._gold_inputs import (
    PARTITION,
    PREREGISTRATION_REF,
    blocked_inputs,
    completed_inputs,
)
from tests.fakes.features.evaluation.fake_gold_builder import FakeGoldBuilder

BUILDERS: dict[str, Callable[[], GoldBuilder]] = {
    "fake": lambda: FakeGoldBuilder(
        "probe", depends_on=frozenset({"quality_checks"}), runs_when_blocked=False
    ),
}


@pytest.fixture(params=list(BUILDERS), ids=list(BUILDERS))
def builder(request: pytest.FixtureRequest) -> GoldBuilder:
    return BUILDERS[request.param]()


@pytest.mark.contract
def test_builder_pure_mapping(builder: GoldBuilder) -> None:
    inputs = completed_inputs()
    snapshot = repr(inputs)
    first = builder.build(inputs)
    second = builder.build(inputs)
    assert first == second
    assert repr(inputs) == snapshot
    assert first.rows, "a completed refresh maps to at least one row"


@pytest.mark.contract
def test_table_named_after_builder(builder: GoldBuilder) -> None:
    assert builder.build(completed_inputs()).name == f"gold_{builder.name}"


@pytest.mark.contract
def test_rows_carry_partition(builder: GoldBuilder) -> None:
    for row in builder.build(completed_inputs()).rows:
        assert (row["asset"], row["parent_sweep_id"]) == (
            PARTITION.asset,
            PARTITION.parent_sweep_id,
        )


@pytest.mark.contract
def test_confirmatory_rows_carry_prereg(builder: GoldBuilder) -> None:
    """Confirmatória (não roda bloqueada) → `preregistration_ref` em toda linha."""
    table = builder.build(completed_inputs())
    if builder.runs_when_blocked:
        assert all("preregistration_ref" not in row for row in table.rows)
    else:
        assert all(row["preregistration_ref"] == PREREGISTRATION_REF for row in table.rows)


@pytest.mark.contract
def test_blocked_inputs_tolerated(builder: GoldBuilder) -> None:
    """Quem roda bloqueado constrói sobre um refresh `BLOCKED` (sem relatórios)."""
    if builder.runs_when_blocked:
        table = builder.build(blocked_inputs())
        assert table.name == f"gold_{builder.name}"
        assert table.rows
    else:
        assert blocked_inputs().horizon_reports == ()


@pytest.mark.contract
def test_no_self_dependency(builder: GoldBuilder) -> None:
    assert isinstance(builder.depends_on, frozenset)
    assert builder.name not in builder.depends_on
    assert isinstance(builder.runs_when_blocked, bool)


@pytest.mark.contract
def test_fake_counts_results_per_check() -> None:
    """Só do fake: uma linha por check com a contagem, e a chamada registrada."""
    fake = FakeGoldBuilder("probe", runs_when_blocked=True)
    inputs = blocked_inputs()
    table = fake.build(inputs)
    assert [row["check"] for row in table.rows] == sorted({r.check for r in inputs.check_results})
    assert sum(row["n_results"] for row in table.rows) == len(inputs.check_results)  # type: ignore[misc]
    assert fake.calls == [inputs]
