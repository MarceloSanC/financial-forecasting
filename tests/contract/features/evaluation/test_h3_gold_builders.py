"""Builders das quatro tabelas gold de H3, célula a célula (Stage 7.3, Task 29).

Insumos: `completed_inputs()` (com `[h3]` e `h3_reports_sample()`: permutação `ok` com uma
família `undefined` e limites infinitos, LOCO `undefined`, leitura `undefined`, VSN) e
`completed_inputs_without_h3()` (sem o bloco). CA13 "limite infinito null + flag", CA14
"4 tabelas, zero linhas sem `[h3]`", I16.
"""

from __future__ import annotations

from typing import Any

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_importance import (  # noqa: E501
    H3ImportanceGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_reading import (
    H3ReadingGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_shares import (
    H3SharesGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_vsn import (
    H3VsnGoldBuilder,
)
from tests.contract.features.evaluation._gold_inputs import (
    PARTITION,
    completed_inputs,
    completed_inputs_without_h3,
)

pytestmark = pytest.mark.contract

_BUILDERS = (H3ImportanceGoldBuilder, H3SharesGoldBuilder, H3ReadingGoldBuilder, H3VsnGoldBuilder)


def _rows(builder: Any, **where: object) -> list[dict[str, object]]:  # noqa: ANN401
    table = builder().build(completed_inputs())
    return [
        dict(row) for row in table.rows if all(row[key] == value for key, value in where.items())
    ]


def _one(builder: Any, **where: object) -> dict[str, object]:  # noqa: ANN401
    [row] = _rows(builder, **where)
    return row


def test_importance_rows_cell_by_cell() -> None:
    aggregated = _one(
        H3ImportanceGoldBuilder,
        method="permutation",
        family="price",
        horizon=7,
        seed=None,
        permutation_index=None,
    )
    assert (aggregated["importance"], aggregated["n_points"]) == (0.01, 3)
    assert (aggregated["status"], aggregated["reason"]) == ("ok", None)
    by_seed = _one(H3ImportanceGoldBuilder, method="permutation", family="price", horizon=1, seed=2)
    assert by_seed["importance"] == 0.02  # noqa: PLR2004
    assert by_seed["permutation_index"] is None
    by_k = _one(
        H3ImportanceGoldBuilder,
        method="permutation",
        family="sentiment",
        horizon=1,
        seed=None,
        permutation_index=2,
    )
    assert by_k["importance"] == 0.002  # noqa: PLR2004
    permutation = _rows(H3ImportanceGoldBuilder, method="permutation")
    assert len(permutation) == 4 * 2 * (1 + 2 + 2)  # f x h x (agregada + 2 seeds + 2 k)
    assert all(
        (row["asset"], row["parent_sweep_id"]) == (PARTITION.asset, PARTITION.parent_sweep_id)
        and row["preregistration_ref"]
        for row in permutation
    )


def test_shares_rows_cell_by_cell() -> None:
    price = _one(H3SharesGoldBuilder, method="permutation", family="price")
    assert (price["share_h1"], price["share_h7"], price["delta"]) == (0.4, 0.2, -0.2)
    assert (price["lower"], price["upper"]) == (-0.3, -0.1)
    assert (price["lower_infinite"], price["upper_infinite"]) == (False, False)
    assert (price["side"], price["excludes_zero"], price["level"]) == (-1, True, 0.9875)
    assert (price["status"], price["reason"]) == ("ok", None)
    assert (price["nonpositive_replicas_h1"], price["nonpositive_replicas_h7"]) == (3, 0)
    assert (price["method_status"], price["method_reason"]) == ("ok", None)
    technical = _one(H3SharesGoldBuilder, method="permutation", family="technical")
    assert technical["status"] == "undefined"
    assert "exactly 0" in str(technical["reason"])


def test_infinite_bound_maps_to_null_with_flag() -> None:
    sentiment = _one(H3SharesGoldBuilder, method="permutation", family="sentiment")
    assert (sentiment["lower"], sentiment["lower_infinite"]) == (None, True)
    assert (sentiment["upper"], sentiment["upper_infinite"]) == (0.5, False)
    fundamental = _one(H3SharesGoldBuilder, method="permutation", family="fundamental")
    assert (fundamental["upper"], fundamental["upper_infinite"]) == (None, True)


def test_undefined_method_rows_carry_reason_and_null_measures() -> None:
    rows = _rows(H3SharesGoldBuilder, method="loco")
    assert len(rows) == 4  # noqa: PLR2004
    for row in rows:
        assert row["method_status"] == "undefined"
        assert "H3-NEG" in str(row["method_reason"])
        assert row["status"] == "undefined"
        for column in ("share_h1", "share_h7", "delta", "lower", "upper", "side"):
            assert row[column] is None, column
    importance = _rows(H3ImportanceGoldBuilder, method="loco")
    assert len(importance) == 4 * 2  # só a agregada: a montagem do LOCO não tem perfis
    assert {row["status"] for row in importance} == {"undefined"}
    assert {row["importance"] for row in importance} == {-0.01}


def test_reading_single_row_with_label_and_counts() -> None:
    [row] = _rows(H3ReadingGoldBuilder)
    assert row["reading_rule"] == "interval_side_agreement_same_family_v1"
    assert (row["sustained"], row["agreeing_families"]) == (False, "")
    assert (row["heterogeneous_permutation"], row["heterogeneous_ablation"]) == (True, None)
    assert (row["block_length"], row["max_block_estimate"], row["n_points"]) == (7, 5.25, 3)
    assert (row["reps"], row["bootstrap_seed"]) == (1000, 129)
    assert (row["nonpositive_permutation_h1"], row["nonpositive_permutation_h7"]) == (3, 0)
    assert (row["nonpositive_ablation_h1"], row["nonpositive_ablation_h7"]) == (0, 0)
    assert row["ablation_cohort_id"] == "synthetic_ablation_r0_b2b2b2b2b2b2"
    assert row["label"] == "descritiva (sem claim causal)"
    assert row["status"] == "undefined"
    assert "loco:" in str(row["reason"])


def test_vsn_rows_by_variable_and_family() -> None:
    rows = _rows(H3VsnGoldBuilder)
    assert {(r["kind"], r["name"]) for r in rows} == {
        ("variable", "log_return"),
        ("variable", "relative_time_idx"),
        ("family", "price"),
    }
    family = _one(H3VsnGoldBuilder, kind="family", name="price")
    assert (family["p10"], family["p50"], family["p90"], family["n_decisions"]) == (
        0.2,
        0.3,
        0.4,
        40,
    )
    assert family["label"] == "horizonte-invariante; descreve quanto o modelo usa cada família"
    assert _one(H3VsnGoldBuilder, kind="variable", name="relative_time_idx")["family"] == "none"


@pytest.mark.parametrize("builder", _BUILDERS, ids=lambda b: b.name)
def test_without_h3_inputs_all_four_tables_are_empty(builder: Any) -> None:  # noqa: ANN401
    table = builder().build(completed_inputs_without_h3())
    assert table.rows == ()
    assert table.name == f"gold_{builder.name}"
