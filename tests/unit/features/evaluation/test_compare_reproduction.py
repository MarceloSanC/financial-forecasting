"""Comparador puro `compare_reproduction` (Stage 8.2, Task 02; concept A6).

Gerações sintéticas pelo dono único `GoldGeneration.from_stored` (fábrica
`_scorecard_factory.make_stored`); cada teste aplica uma mudança ao lado reproduzido.
"""

from __future__ import annotations

import dataclasses
import math
import struct
from collections.abc import Callable
from datetime import timedelta

import pytest

from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    result_layer_digest,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.dtos.reproduction_comparison import (
    ReproductionClass,
    ReproductionComparison,
    TableComparison,
)
from financial_forecasting.features.evaluation.application.use_cases.reproduction_comparison import (  # noqa: E501
    compare_reproduction,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from tests.unit.features.evaluation._preregistration_payload import valid_payload
from tests.unit.features.evaluation._scorecard_factory import StoredGold, make_stored

R1, R2, R3 = ReproductionClass.R1, ReproductionClass.R2, ReproductionClass.R3
_METRICS = "gold_metrics_by_run"
_MC = "gold_christoffersen_monte_carlo"
_CHECKS = "gold_quality_checks"
_VSN = "gold_h3_vsn"


def _vsn_row(stored: StoredGold, label: str) -> dict[str, object]:
    """Uma linha de `gold_h3_vsn` só com colunas de texto (R1 não numérica)."""
    return {
        "asset": stored.partition.asset,
        "parent_sweep_id": stored.partition.parent_sweep_id,
        "preregistration_ref": stored.manifest["preregistration_ref"],
        "kind": "family",
        "name": "price",
        "label": label,
    }


def _stored(change: Callable[[StoredGold], object] | None = None) -> StoredGold:
    stored = make_stored(Preregistration.from_mapping(valid_payload()))
    stored.rows[_VSN] = [_vsn_row(stored, "descriptive")]
    if change is not None:
        change(stored)
    return stored


def _scorecard(**verdict: object) -> dict[str, object]:
    return {
        "manifest_read": {
            "started_at": "2026-10-05T12:00:00+00:00",
            "finished_at": "2026-10-05T12:10:00+00:00",
            "n_runs": 6,
        },
        "verdict": {"p": 0.5, "labels": ["a", 1], **verdict},
    }


def _compare(
    reproduced: GoldGeneration,
    *,
    judged: GoldGeneration | None = None,
    reproduced_scorecard: dict[str, object] | None = None,
    judged_scorecard: dict[str, object] | None = None,
    expected: str | None = None,
) -> ReproductionComparison:
    judged = judged if judged is not None else _stored().generation()
    return compare_reproduction(
        judged=judged,
        judged_scorecard=judged_scorecard if judged_scorecard is not None else _scorecard(),
        reproduced=reproduced,
        reproduced_scorecard=(
            reproduced_scorecard if reproduced_scorecard is not None else _scorecard()
        ),
        expected_result_digest=expected if expected is not None else result_layer_digest(judged),
    )


def _table(comparison: ReproductionComparison, name: str) -> TableComparison:
    return next(table for table in comparison.tables if table.name == name)


def _first() -> Callable[[dict[str, object]], bool]:
    """Seleciona só a primeira linha visitada (pela identidade) no `set_cell`/`drop_rows`."""
    marker: list[int] = []

    def where(row: dict[str, object]) -> bool:
        if marker:
            return id(row) == marker[0]
        marker.append(id(row))
        return True

    return where


def _metric_value(stored: StoredGold) -> float:
    value = stored.rows[_METRICS][0]["value"]
    assert isinstance(value, float)
    return value


@pytest.mark.unit
def test_identical_generations_are_bit_identical_with_zero_max_per_class() -> None:
    comparison = _compare(_stored().generation())

    assert comparison.bit_identical is True
    for total in comparison.totals:
        assert total.compared > 0, total
        assert total.different == 0
        assert total.max_abs_diff == 0.0
    assert all(table.keys_equal for table in comparison.tables)
    assert comparison.scorecard.equal is True
    assert len(comparison.tables) == 19  # noqa: PLR2004 — toda tabela de GOLD_SCHEMAS


@pytest.mark.unit
def test_one_ulp_in_r2_float_is_reported_in_r2_with_its_delta() -> None:
    value = _metric_value(_stored())
    bumped = math.nextafter(value, math.inf)
    comparison = _compare(
        _stored(lambda s: s.set_cell(_METRICS, _first(), "value", bumped)).generation()
    )

    r1, r2, r3 = _table(comparison, _METRICS).classes
    assert (r2.different, r2.max_abs_diff) == (1, bumped - value)
    assert r2.max_abs_diff == math.ulp(value)
    assert (r1.different, r3.different) == (0, 0)
    assert comparison.totals[1].different == 1
    assert comparison.bit_identical is False


@pytest.mark.unit
def test_one_ulp_in_r3_float_is_reported_in_r3() -> None:
    value = 0.41  # o mc_p_uc da fábrica
    bumped = math.nextafter(value, 0.0)
    comparison = _compare(
        _stored(lambda s: s.set_cell(_MC, _first(), "mc_p_uc", bumped)).generation()
    )

    r1, r2, r3 = _table(comparison, _MC).classes
    assert (r3.different, r3.max_abs_diff) == (1, value - bumped)
    assert (r1.different, r2.different) == (0, 0)
    assert comparison.totals[2].different == 1
    assert comparison.bit_identical is False


@pytest.mark.unit
def test_integer_off_by_one_is_r1_with_max_1() -> None:
    comparison = _compare(
        _stored(lambda s: s.set_cell(_CHECKS, _first(), "occurrences", 2)).generation()
    )

    r1, r2, _ = _table(comparison, _CHECKS).classes
    assert (r1.different, r1.max_abs_diff) == (1, 1.0)
    assert r2.different == 0


@pytest.mark.unit
def test_label_change_is_r1_count_without_max() -> None:
    def relabel(stored: StoredGold) -> None:
        stored.rows[_VSN] = [_vsn_row(stored, "other")]

    comparison = _compare(_stored(relabel).generation())

    r1, r2, r3 = _table(comparison, _VSN).classes
    assert (r1.different, r1.numeric, r1.max_abs_diff) == (1, 0, None)
    assert (r2.compared, r3.compared) == (0, 0)
    assert comparison.bit_identical is False


@pytest.mark.unit
def test_negative_zero_differs_from_zero() -> None:
    def zero(sign: float) -> Callable[[StoredGold], object]:
        return lambda s: s.set_cell(_METRICS, _first(), "value", math.copysign(0.0, sign))

    comparison = _compare(_stored(zero(-1.0)).generation(), judged=_stored(zero(1.0)).generation())

    r2 = _table(comparison, _METRICS).classes[1]
    assert (r2.different, r2.max_abs_diff) == (1, 0.0)
    assert comparison.bit_identical is False


def _nan(payload: str) -> float:
    value: float = struct.unpack(">d", bytes.fromhex(payload))[0]
    assert math.isnan(value)
    return value


@pytest.mark.unit
def test_nan_payloads_compared_by_bits() -> None:
    quiet, other = _nan("7ff8000000000000"), _nan("7ff8000000000001")
    generation = _stored().generation()

    same = _compare(
        generation,
        judged_scorecard=_scorecard(x=quiet),
        reproduced_scorecard=_scorecard(x=_nan("7ff8000000000000")),
    )
    differs = _compare(
        generation, judged_scorecard=_scorecard(x=quiet), reproduced_scorecard=_scorecard(x=other)
    )
    infinite = _compare(
        generation,
        judged_scorecard=_scorecard(x=math.inf),
        reproduced_scorecard=_scorecard(x=1.0),
    )

    assert same.scorecard.equal is True
    assert same.bit_identical is True
    assert (differs.scorecard.different, differs.scorecard.max_abs_diff) == (1, math.inf)
    assert differs.scorecard.paths == ("verdict.x",)
    assert infinite.scorecard.max_abs_diff == math.inf


@pytest.mark.unit
def test_int_and_float_of_same_value_differ() -> None:
    def as_number(value: object) -> Callable[[StoredGold], object]:
        return lambda s: s.set_cell(_METRICS, _first(), "value", value)

    comparison = _compare(
        _stored(as_number(1)).generation(), judged=_stored(as_number(1.0)).generation()
    )
    r2 = _table(comparison, _METRICS).classes[1]
    assert (r2.different, r2.max_abs_diff) == (1, 0.0)

    flag = _compare(
        _stored(lambda s: s.set_cell(_CHECKS, _first(), "occurrences", True)).generation()
    )
    assert _table(flag, _CHECKS).classes[0].different == 1


@pytest.mark.unit
@pytest.mark.parametrize("side", ["missing", "extra"])
def test_missing_or_extra_key_row_sets_keys_equal_false(side: str) -> None:
    dropped = _stored(lambda s: s.drop_rows(_CHECKS, _first())).generation()
    full = _stored().generation()
    reproduced, judged = (dropped, full) if side == "missing" else (full, dropped)

    comparison = _compare(reproduced, judged=judged)

    table = _table(comparison, _CHECKS)
    assert table.keys_equal is False
    assert abs(table.judged_rows - table.reproduced_rows) == 1
    assert table.classes[0].different == 1
    assert comparison.bit_identical is False


@pytest.mark.unit
def test_started_and_finished_at_differences_do_not_count() -> None:
    def later(stored: StoredGold) -> None:
        for name in ("started_at", "finished_at"):
            value = stored.manifest[name]
            assert isinstance(value, str)
            stored.manifest[name] = value.replace("2026", "2027")

    judged = _stored().generation()
    reproduced = _stored(later).generation()
    assert reproduced.manifest.started_at - judged.manifest.started_at > timedelta(days=300)
    scorecard = _scorecard()
    scorecard["manifest_read"] = {
        "started_at": "2027-01-01T00:00:00+00:00",
        "finished_at": "2027-01-01T00:10:00+00:00",
        "n_runs": 6,
    }

    comparison = _compare(reproduced, judged=judged, reproduced_scorecard=scorecard)

    assert comparison.bit_identical is True
    assert comparison.scorecard.leaves == 4  # noqa: PLR2004 — n_runs, p, labels[0], labels[1]


@pytest.mark.unit
def test_other_scorecard_leaf_differs_with_path() -> None:
    nested = _scorecard()
    nested["manifest_read"] = {**nested["manifest_read"], "n_runs": 7}  # type: ignore[dict-item]
    comparison = _compare(_stored().generation(), reproduced_scorecard=nested)

    assert comparison.scorecard.equal is False
    assert comparison.scorecard.paths == ("manifest_read.n_runs",)
    assert comparison.scorecard.max_abs_diff == 1.0
    assert comparison.bit_identical is False

    listed = _compare(_stored().generation(), reproduced_scorecard=_scorecard(labels=["a", 2]))
    assert listed.scorecard.paths == ("verdict.labels[1]",)


@pytest.mark.unit
def test_scorecard_key_only_on_one_side_differs() -> None:
    extra = _compare(_stored().generation(), reproduced_scorecard=_scorecard(extra={"k": 1}))
    missing = _compare(_stored().generation(), judged_scorecard=_scorecard(extra=0.5))
    longer = _compare(_stored().generation(), reproduced_scorecard=_scorecard(labels=["a", 1, 2]))

    assert (extra.scorecard.equal, extra.scorecard.paths) == (False, ("verdict.extra",))
    assert (missing.scorecard.equal, missing.scorecard.paths) == (False, ("verdict.extra",))
    assert longer.scorecard.paths == ("verdict.labels[2]",)
    assert extra.bit_identical is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "field", ["silver_content.digest", "dataset_fingerprint", "preregistration_ref", "partition"]
)
def test_identity_mismatch_is_not_bit_identical(field: str) -> None:
    judged = _stored().generation()
    manifest = judged.manifest
    changed = {
        "silver_content.digest": lambda: dataclasses.replace(
            manifest,
            silver_content=dataclasses.replace(manifest.silver_content, digest="cd" * 32),
        ),
        "dataset_fingerprint": lambda: dataclasses.replace(
            manifest, dataset_fingerprint=DatasetContentFingerprint(value="cd" * 32)
        ),
        "preregistration_ref": lambda: dataclasses.replace(
            manifest,
            parameters=dataclasses.replace(manifest.parameters, preregistration_ref="other-r0"),
        ),
        "partition": lambda: dataclasses.replace(
            manifest, partition=GoldPartition("MSFT", manifest.partition.parent_sweep_id)
        ),
    }[field]()
    reproduced = GoldGeneration(manifest=changed, tables=judged.tables)

    comparison = _compare(reproduced, judged=judged)

    unequal = [item.field for item in comparison.identity if not item.equal]
    assert unequal == [field]
    assert comparison.identity_equal is False
    assert comparison.bit_identical is False
    assert comparison.preregistration_ref == manifest.parameters.preregistration_ref
    assert comparison.partition == manifest.partition


@pytest.mark.unit
def test_result_digest_other_than_expected_is_not_bit_identical() -> None:
    generation = _stored().generation()
    comparison = _compare(generation, judged=generation, expected="00" * 32)

    assert comparison.judged_result_digest == comparison.reproduced_result_digest
    assert comparison.digests_equal is False
    assert comparison.identity_equal and comparison.tables_equal and comparison.scorecard.equal
    assert comparison.bit_identical is False
    with pytest.raises(ValueError, match="expected_result_digest"):
        _compare(generation, expected="not-hex")


@pytest.mark.unit
def test_undeclared_column_raises() -> None:
    def surprise(stored: StoredGold) -> None:
        for row in stored.rows[_CHECKS]:
            row["surprise"] = 1

    with pytest.raises(
        ValueError, match=r"columns without a declared reproduction class \['surprise'\]"
    ):
        _compare(_stored(surprise).generation())
