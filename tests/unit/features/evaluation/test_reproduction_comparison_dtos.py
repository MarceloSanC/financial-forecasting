"""DTO da comparação da reprodução e mapa de classes (Stage 8.2, Task 01; concept A6)."""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    CONFIRMATORY_TABLES,
    GOLD_SCHEMAS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.dtos.reproduction_comparison import (
    IDENTITY_FIELDS,
    REPRODUCTION_CLASSES,
    ClassComparison,
    IdentityComparison,
    ReproductionClass,
    ReproductionComparison,
    ScorecardComparison,
    TableComparison,
)

R1, R2, R3 = ReproductionClass.R1, ReproductionClass.R2, ReproductionClass.R3
_DIGEST = "ab" * 32


@pytest.mark.unit
def test_every_schema_column_has_a_declared_class() -> None:
    """Completude: `key` + `read_columns` + colunas de partição de toda tabela gold."""
    assert set(REPRODUCTION_CLASSES) == set(GOLD_SCHEMAS)
    for name, schema in GOLD_SCHEMAS.items():
        declared = REPRODUCTION_CLASSES[name]
        partition = {"asset", "parent_sweep_id"}
        if name in CONFIRMATORY_TABLES:
            partition.add("preregistration_ref")
        else:
            assert "preregistration_ref" not in declared
        missing = (set(schema.key) | set(schema.read_columns) | partition) - set(declared)
        assert not missing, f"{name}: columns without class {sorted(missing)}"
        assert all(isinstance(cls, ReproductionClass) for cls in declared.values())


@pytest.mark.unit
def test_random_dependent_floats_are_r3() -> None:
    """R3 = exatamente MCS, sensibilidade de bloco, Monte Carlo e limites bootstrap de H3."""
    r3 = {
        (table, column)
        for table, columns in REPRODUCTION_CLASSES.items()
        for column, cls in columns.items()
        if cls is R3
    }
    assert r3 == {
        ("gold_mcs_results", "step_p_value"),
        ("gold_mcs_results", "mcs_p_value"),
        ("gold_mcs_block_sensitivity", "step_p_value"),
        ("gold_mcs_block_sensitivity", "mcs_p_value"),
        ("gold_christoffersen_monte_carlo", "mc_p_uc"),
        ("gold_christoffersen_monte_carlo", "mc_p_ind"),
        ("gold_christoffersen_monte_carlo", "mc_p_cc"),
        ("gold_h3_shares", "lower"),
        ("gold_h3_shares", "upper"),
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("gold_quality_checks", "occurrences"),  # contagem
        ("gold_calibration_table", "n_violations"),
        ("gold_dm_results", "rejected"),  # decisão
        ("gold_mcs_results", "included"),
        ("gold_h3_shares", "excludes_zero"),
        ("gold_metrics_by_run", "metric"),  # rótulo
        ("gold_dm_results", "variance_estimator"),
        ("gold_loss_differentials", "target_timestamp"),  # timestamp da chave
        ("gold_dm_results", "common_first_target_timestamp"),
        ("gold_mcs_results", "seed"),  # semente
        ("gold_christoffersen_monte_carlo", "mc_seed"),
        ("gold_dm_results", "degrees_of_freedom"),
        ("gold_mcs_results", "statistic"),  # nome da estatística (str)
        ("gold_metrics_by_run", "asset"),
        ("gold_metrics_by_run", "preregistration_ref"),
    ],
)
def test_non_float_columns_are_r1(table: str, column: str) -> None:
    assert REPRODUCTION_CLASSES[table][column] is R1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("gold_dm_results", "p_value"),
        ("gold_dm_results", "mean_differential"),
        ("gold_metrics_by_run", "value"),
        ("gold_calibration_table", "p_cc"),
        ("gold_conformal_coverage", "wilson_lower"),
        ("gold_h3_shares", "delta"),
    ],
)
def test_deterministic_floats_are_r2(table: str, column: str) -> None:
    assert REPRODUCTION_CLASSES[table][column] is R2


@pytest.mark.unit
def test_class_map_is_read_only() -> None:
    with pytest.raises(TypeError):
        REPRODUCTION_CLASSES["gold_dm_results"]["p_value"] = R3  # type: ignore[index]


@pytest.mark.unit
def test_identity_field_equal_is_derived_from_sides() -> None:
    assert IdentityComparison("dataset_fingerprint", "a", "a").equal is True
    assert IdentityComparison("dataset_fingerprint", "a", "b").equal is False
    with pytest.raises(TypeError):
        IdentityComparison("dataset_fingerprint", "a", "b", True)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="identity field"):
        IdentityComparison("commit", "a", "a")
    with pytest.raises(ValueError, match="must be a str"):
        IdentityComparison("partition", "a", 1)  # type: ignore[arg-type]


def _cls(
    reproduction_class: ReproductionClass,
    *,
    compared: int = 4,
    different: int = 0,
    numeric: int = 4,
    max_abs_diff: float | None = 0.0,
) -> ClassComparison:
    return ClassComparison(
        reproduction_class=reproduction_class,
        compared=compared,
        different=different,
        numeric=numeric,
        max_abs_diff=max_abs_diff,
    )


def _classes() -> tuple[ClassComparison, ...]:
    return (_cls(R1), _cls(R2), _cls(R3))


def _table(name: str = "gold_dm_results") -> TableComparison:
    return TableComparison(
        name=name, judged_rows=2, reproduced_rows=2, keys_equal=True, classes=_classes()
    )


def _scorecard(different: int = 0) -> ScorecardComparison:
    return ScorecardComparison(
        leaves=max(10, different),
        different=different,
        numeric=3,
        max_abs_diff=0.5 if different else 0.0,
        paths=tuple(f"verdict.leaf{index}" for index in range(min(different, 20))),
    )


def _comparison(**changes: object) -> ReproductionComparison:
    kwargs: dict[str, object] = {
        "preregistration_ref": "plan-r0-0123456789ab",
        "partition": GoldPartition("AAPL", "sweep-01"),
        "identity": tuple(IdentityComparison(name, "x", "x") for name in IDENTITY_FIELDS),
        "judged_result_digest": _DIGEST,
        "reproduced_result_digest": _DIGEST,
        "expected_result_digest": _DIGEST,
        "tables": (_table("gold_dm_results"), _table("gold_mcs_results")),
        "scorecard": _scorecard(),
    }
    kwargs.update(changes)
    return ReproductionComparison(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_bit_identical_requires_identity_digests_tables_and_scorecard() -> None:
    assert _comparison().bit_identical is True
    identity = tuple(
        IdentityComparison(name, "x", "y" if name == "silver_content.digest" else "x")
        for name in IDENTITY_FIELDS
    )
    differing_table = TableComparison(
        name="gold_mcs_results",
        judged_rows=2,
        reproduced_rows=2,
        keys_equal=True,
        classes=(_cls(R1), _cls(R2), _cls(R3, different=1, max_abs_diff=1e-17)),
    )
    for changes in (
        {"identity": identity},
        {"reproduced_result_digest": "cd" * 32},
        {"expected_result_digest": "cd" * 32},
        {"tables": (_table("gold_dm_results"), differing_table)},
        {"scorecard": _scorecard(different=1)},
    ):
        assert _comparison(**changes).bit_identical is False, changes


@pytest.mark.unit
def test_unequal_keys_are_not_bit_identical() -> None:
    table = TableComparison(
        name="gold_dm_results",
        judged_rows=2,
        reproduced_rows=1,
        keys_equal=False,
        classes=(_cls(R1, compared=5, different=1), _cls(R2), _cls(R3)),
    )
    assert _comparison(tables=(table,)).bit_identical is False


@pytest.mark.unit
def test_totals_sum_counts_and_take_the_max() -> None:
    other = TableComparison(
        name="gold_mcs_results",
        judged_rows=2,
        reproduced_rows=2,
        keys_equal=True,
        classes=(
            _cls(R1, numeric=0, max_abs_diff=None),
            _cls(R2, different=2, max_abs_diff=0.25),
            _cls(R3, compared=0, numeric=0, max_abs_diff=None),
        ),
    )
    totals = _comparison(tables=(_table(), other)).totals
    assert [item.reproduction_class for item in totals] == [R1, R2, R3]
    assert (totals[0].compared, totals[0].numeric, totals[0].max_abs_diff) == (8, 4, 0.0)
    assert (totals[1].different, totals[1].max_abs_diff) == (2, 0.25)
    assert (totals[2].compared, totals[2].max_abs_diff) == (4, 0.0)


@pytest.mark.unit
def test_class_comparison_rejects_negative_counts_and_max_for_non_numeric() -> None:
    for changes, message in (
        ({"compared": -1}, "compared must be an int >= 0"),
        ({"different": -1}, "different must be an int >= 0"),
        ({"numeric": True}, "numeric must be an int >= 0"),
        ({"different": 5}, "cannot exceed compared"),
        ({"numeric": 5}, "cannot exceed compared"),
        ({"numeric": 0, "max_abs_diff": 0.0}, "only defined over numeric pairs"),
        ({"max_abs_diff": None}, "must be a float >= 0"),
        ({"max_abs_diff": -1.0}, "must be a float >= 0"),
        ({"max_abs_diff": float("nan")}, "must be a float >= 0"),
        ({"max_abs_diff": 1}, "must be a float >= 0"),
        ({"max_abs_diff": 0.5}, r"must be 0\.0 without differences"),
    ):
        with pytest.raises(ValueError, match=message):
            _cls(R1, **changes)
    assert _cls(R1, different=1, max_abs_diff=float("inf")).max_abs_diff == float("inf")
    assert _cls(R1, different=1, max_abs_diff=0.0).different == 1  # -0.0 contra 0.0
    assert _cls(R1, numeric=0, max_abs_diff=None).max_abs_diff is None
    with pytest.raises(ValueError, match="ReproductionClass"):
        _cls("R1")  # type: ignore[arg-type]


@pytest.mark.unit
def test_table_comparison_validates_classes_and_keys() -> None:
    for changes, message in (
        ({"classes": (_cls(R1), _cls(R2))}, "R1, R2, R3 in order"),
        ({"classes": (_cls(R2), _cls(R1), _cls(R3))}, "R1, R2, R3 in order"),
        ({"classes": list(_classes())}, "R1, R2, R3 in order"),
        ({"reproduced_rows": 3}, "same number of rows"),
        ({"keys_equal": False}, "unequal keys are R1 differences"),
        ({"judged_rows": -1}, "judged_rows must be an int >= 0"),
        ({"name": ""}, "non-empty str"),
    ):
        with pytest.raises(ValueError, match=message):
            dataclasses.replace(_table(), **changes)


@pytest.mark.unit
def test_scorecard_comparison_paths_follow_the_differences() -> None:
    assert _scorecard().equal is True
    assert _scorecard(different=1).equal is False
    assert len(_scorecard(different=25).paths) == 20  # noqa: PLR2004
    with pytest.raises(ValueError, match="paths must list"):
        dataclasses.replace(_scorecard(different=2), paths=("a",))
    with pytest.raises(ValueError, match=r"must be 0\.0 without differences"):
        dataclasses.replace(_scorecard(), max_abs_diff=0.5)


@pytest.mark.unit
def test_reproduction_comparison_validates_shape() -> None:
    for changes, message in (
        ({"identity": ()}, "identity must be"),
        (
            {"identity": tuple(IdentityComparison(n, "x", "x") for n in reversed(IDENTITY_FIELDS))},
            "identity must be",
        ),
        ({"judged_result_digest": "xyz"}, "judged_result_digest"),
        ({"tables": (_table("gold_mcs_results"), _table("gold_dm_results"))}, "sorted by name"),
        ({"tables": (_table(), _table())}, "sorted by name"),
        ({"partition": ("AAPL", "sweep-01")}, "GoldPartition"),
        ({"preregistration_ref": ""}, "non-empty str"),
        ({"scorecard": None}, "ScorecardComparison"),
    ):
        with pytest.raises(ValueError, match=message):
            _comparison(**changes)
