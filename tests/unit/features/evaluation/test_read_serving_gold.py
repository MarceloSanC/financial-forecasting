"""Unit do `ReadServingGold` (Stage 7.4, Task 03) — concept I7, I8; CA3, CA5, CA9 (parte unitária).

Gerações publicadas num `InMemoryGoldStore` e lidas pelo `InMemoryGoldGenerationReader`
(montagem única `GoldGeneration.from_stored`, a mesma do real). Linhas com as colunas
que os builders da 7.2/7.3 gravam.
"""

from __future__ import annotations

import math

import pytest

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CONFORMAL_CORRECTIONS,
    GOLD_H3_READING,
    GOLD_H3_SHARES,
    GOLD_H3_VSN,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldPartition,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_generation_reader import (
    GoldGenerationCorruptError,
)
from financial_forecasting.features.evaluation.application.use_cases import (
    read_serving_gold as read_serving_gold_module,
)
from financial_forecasting.features.evaluation.application.use_cases.read_serving_gold import (
    ReadServingGold,
)
from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    EMPIRICAL_COVERAGE_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.contribution_agreement import (
    H3_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.vsn_summary import VSN_LABEL
from financial_forecasting.features.inference.application.dtos.serving_gold import (
    AVAILABLE,
    UNAVAILABLE,
    ConformalCorrectionRecord,
    H3ReadingRecord,
    H3ShareRecord,
    ServingGold,
    VsnRecord,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from tests.fakes.features.evaluation.in_memory_gold_generation_reader import (
    InMemoryGoldGenerationReader,
)
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore
from tests.unit.features.evaluation._serving_gold_rows import (
    ASSET,
    COHORT,
    PARTITION,
    REF,
    SPLIT,
    Rows,
    complete_rows,
    correction_row,
    generation,
    reading_row,
    refresh_parameters,
    share_row,
    vsn_row,
)

pytestmark = pytest.mark.unit


def _reader(
    status: RefreshStatus = RefreshStatus.COMPLETED,
    *,
    rows: Rows | None = None,
    parameters: RefreshParameters | None = None,
) -> ReadServingGold:
    store = InMemoryGoldStore()
    tables, manifest = generation(status, rows=rows, parameters=parameters)
    store.publish(partition=PARTITION, tables=tables, manifest=manifest)
    return ReadServingGold(gold_reader=InMemoryGoldGenerationReader(store))


def _read(reader: ReadServingGold) -> ServingGold:
    return reader.read(asset=ASSET, cohort_id=COHORT)


_IDENTITY = {
    "published": True,
    "preregistration_ref": REF,
    "candidate": "tft_quantile",
    "finished_at": "2026-10-02T12:00:00+00:00",
    "conformal_label": EMPIRICAL_COVERAGE_LABEL,
    "h3_label": H3_LABEL,
    "vsn_label": VSN_LABEL,
}


def test_unpublished_partition_is_a_state_not_an_error() -> None:
    reader = ReadServingGold(gold_reader=InMemoryGoldGenerationReader(InMemoryGoldStore()))
    assert _read(reader) == ServingGold.unpublished(
        reason=f"gold não publicado para o cohort {COHORT}",
        conformal_label=EMPIRICAL_COVERAGE_LABEL,
        h3_label=H3_LABEL,
        vsn_label=VSN_LABEL,
    )


def test_blocked_generation_makes_both_blocks_unavailable_without_reading_tables() -> None:
    # a geração BLOCKED não lista as tabelas confirmatórias: ler uma delas ergueria
    gold = _read(_reader(RefreshStatus.BLOCKED))
    assert gold == ServingGold(
        **_IDENTITY,
        generation_status="BLOCKED",
        conformal_status=UNAVAILABLE,
        conformal_reason="geração gold BLOCKED",
        explainability_status=UNAVAILABLE,
        explainability_reason="geração gold BLOCKED",
        corrections=(),
        shares=(),
        reading=None,
        vsn=(),
    )


def test_generation_without_conformal_and_h3_blocks() -> None:
    gold = _read(_reader(parameters=refresh_parameters(conformal=False, h3=False)))
    assert (gold.generation_status, gold.published) == ("COMPLETED", True)
    assert (gold.conformal_status, gold.conformal_reason, gold.corrections) == (
        UNAVAILABLE,
        "geração sem bloco [conformal]",
        (),
    )
    assert (gold.explainability_status, gold.explainability_reason) == (
        UNAVAILABLE,
        "geração sem bloco [h3]",
    )
    assert (gold.shares, gold.reading, gold.vsn) == ((), None, ())


def test_generation_without_h3_reading_row() -> None:
    rows = {k: v for k, v in complete_rows().items() if k != GOLD_H3_READING.name}
    gold = _read(_reader(rows=rows))
    assert gold.conformal_status == AVAILABLE
    assert (gold.explainability_status, gold.explainability_reason, gold.shares) == (
        UNAVAILABLE,
        "leitura de H3 ausente na geração",
        (),
    )


def test_completed_generation_with_both_blocks() -> None:
    gold = _read(_reader(rows=complete_rows()))
    assert (gold.conformal_status, gold.conformal_reason) == (AVAILABLE, None)
    assert (gold.explainability_status, gold.explainability_reason) == (AVAILABLE, None)
    assert (gold.generation_status, gold.candidate, gold.finished_at) == (
        "COMPLETED",
        "tft_quantile",
        "2026-10-02T12:00:00+00:00",
    )
    assert gold.corrections == (
        ConformalCorrectionRecord(
            "0", 1, 1, 0.1, 0.9, SPLIT, "lower", 0.1, "ok", None, 200, 190, 0.00390625
        ),
        ConformalCorrectionRecord(
            "0", 1, 1, 0.1, 0.9, SPLIT, "upper", 0.9, "ok", None, 10, 11, math.inf
        ),
        ConformalCorrectionRecord(
            "0", 1, 7, 0.1, 0.9, SPLIT, "lower", 0.1, "ok", None, 200, 190, 0.0078125
        ),
        ConformalCorrectionRecord(
            "0", 1, 7, 0.1, 0.9, SPLIT, "upper", 0.9, "ok", None, 200, 190, 0.015625
        ),
        ConformalCorrectionRecord(
            "1", 2, 1, 0.1, 0.9, SPLIT, "lower", 0.1, "undefined", "n < 1/alpha", None, None, None
        ),
        ConformalCorrectionRecord(
            "1", 2, 1, 0.1, 0.9, SPLIT, "upper", 0.9, "undefined", "n < 1/alpha", None, None, None
        ),
    )
    assert gold.shares == (
        H3ShareRecord(
            "loco",
            "price",
            0.5,
            0.25,
            -0.25,
            -math.inf,
            0.125,
            0.9875,
            -1,
            True,
            "ok",
            None,
        ),
        H3ShareRecord(
            "loco",
            "technical",
            0.5,
            0.25,
            -0.25,
            -0.5,
            None,
            0.9875,
            -1,
            False,
            "undefined",
            "Σ* <= 0",
        ),
        H3ShareRecord(
            "permutation",
            "price",
            0.5,
            0.25,
            -0.25,
            -0.5,
            math.inf,
            0.9875,
            -1,
            False,
            "ok",
            None,
        ),
        H3ShareRecord(
            "permutation",
            "technical",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "undefined",
            "método indefinido",
        ),
    )
    assert gold.reading == H3ReadingRecord(
        "interval_side_agreement_same_family_v1",
        True,
        False,
        True,
        ("price", "technical"),
        1505,
        "ok",
        None,
    )
    assert gold.vsn == (
        VsnRecord("family", "price", "price", 0.125, 0.25, 0.5, 1505, "ok", None),
        VsnRecord("variable", "log_return", "price", 0.125, 0.25, 0.5, 1505, "ok", None),
    )


def test_reading_without_agreeing_families_is_an_empty_tuple() -> None:
    rows = {**complete_rows(), GOLD_H3_READING.name: [reading_row(agreeing_families="")]}
    reading = _read(_reader(rows=rows)).reading
    assert reading is not None
    assert reading.agreeing_families == ()


def test_undefined_vsn_is_an_available_block_with_non_ok_rows() -> None:
    undefined = {
        "p10": None,
        "p50": None,
        "p90": None,
        "n_decisions": None,
        "label": None,
        "status": "undefined",
        "reason": "sem pesos de VSN",
    }
    rows = {
        **complete_rows(),
        GOLD_H3_VSN.name: [vsn_row("family", "price", **undefined)],
    }
    gold = _read(_reader(rows=rows))
    assert gold.explainability_status == AVAILABLE
    assert gold.vsn == (
        VsnRecord(
            "family", "price", "price", None, None, None, None, "undefined", "sem pesos de VSN"
        ),
    )


@pytest.mark.parametrize(
    ("table", "rows", "message"),
    [
        (GOLD_H3_READING.name, [reading_row(label="outro rótulo")], "not the H3 label"),
        (
            GOLD_H3_READING.name,
            [reading_row(label=None, status="undefined", reason="x")],
            "not the H3 label",
        ),
        (GOLD_H3_VSN.name, [vsn_row("family", "price", label="outro")], "is ok with label"),
        (GOLD_H3_VSN.name, [vsn_row("family", "price", label=None)], "is ok with label"),
        (
            GOLD_H3_VSN.name,
            [vsn_row("family", "price", status="undefined", reason="x", label=VSN_LABEL)],
            "is undefined but carries the label",
        ),
    ],
    ids=[
        "reading-label-differs",
        "reading-label-null",
        "vsn-ok-label-differs",
        "vsn-ok-label-null",
        "vsn-not-ok-with-label",
    ],
)
def test_stored_label_must_match_its_owner(
    table: str, rows: list[dict[str, object]], message: str
) -> None:
    with pytest.raises(GoldGenerationCorruptError, match=message):
        _read(_reader(rows={**complete_rows(), table: rows}))


def test_dto_value_error_becomes_corruption() -> None:
    # cauda `ok` sem correção nem infinito: o DTO recusa
    bad = [correction_row("0", 1, "lower", correction=None, infinite=False)]
    rows = {**complete_rows(), GOLD_CONFORMAL_CORRECTIONS.name: bad}
    with pytest.raises(GoldGenerationCorruptError, match="does not hold") as info:
        _read(_reader(rows=rows))
    assert isinstance(info.value.__cause__, ValueError)


def test_wrongly_typed_cell_is_corruption() -> None:
    bad = [correction_row("0", 1, "lower"), {**correction_row("0", 1, "upper"), "n": "200"}]
    rows = {**complete_rows(), GOLD_CONFORMAL_CORRECTIONS.name: bad}
    with pytest.raises(GoldGenerationCorruptError, match="expected int"):
        _read(_reader(rows=rows))


def test_more_than_one_reading_row_is_corruption() -> None:
    rows = {
        **complete_rows(),
        GOLD_H3_READING.name: [reading_row(), reading_row(reading_rule="outra_regra_v1")],
    }
    with pytest.raises(GoldGenerationCorruptError, match="reads H3 once"):
        _read(_reader(rows=rows))


class _CorruptReader:
    def read_generation(self, *, partition: GoldPartition) -> GoldGeneration:
        raise GoldGenerationCorruptError(f"table missing in {partition}")


def test_corrupt_generation_propagates_as_application_error() -> None:
    reader = ReadServingGold(gold_reader=_CorruptReader())
    with pytest.raises(GoldGenerationCorruptError, match="table missing") as info:
        _read(reader)
    assert isinstance(info.value, ApplicationError)


@pytest.mark.parametrize("side", [-1, 0, 1])
def test_share_side_is_read_as_the_sign_of_delta(side: int) -> None:
    rows = {**complete_rows(), GOLD_H3_SHARES.name: [share_row("permutation", "price", side=side)]}
    (share,) = _read(_reader(rows=rows)).shares
    assert share.side == side


def test_share_side_stored_as_text_is_corruption() -> None:
    rows = {
        **complete_rows(),
        GOLD_H3_SHARES.name: [share_row("permutation", "price", side="two_sided")],
    }
    with pytest.raises(GoldGenerationCorruptError, match="side: expected int"):
        _read(_reader(rows=rows))


def test_infinite_vsn_measure_becomes_corruption(monkeypatch: pytest.MonkeyPatch) -> None:
    """C2-2: o `GoldTable` já recusa float não finito na gravação; se um chegasse ao leitor,
    o DTO o recusa e o leitor o traduz em `GoldGenerationCorruptError` (500)."""
    original = read_serving_gold_module.col_float_or_none

    def p10_infinite(row: object, schema: object, column: str) -> float | None:
        if column == "p10":
            return math.inf
        return original(row, schema, column)  # type: ignore[arg-type]

    monkeypatch.setattr(read_serving_gold_module, "col_float_or_none", p10_infinite)
    with pytest.raises(GoldGenerationCorruptError, match="vsn must be finite") as info:
        _read(_reader(rows=complete_rows()))
    assert isinstance(info.value, ApplicationError)
    assert isinstance(info.value.__cause__, ValueError)


def test_infinite_flag_with_a_stored_correction_is_corruption() -> None:
    """TA-6: o builder grava infinito como `null` + `infinite = true`; valor e flag juntos
    não se sustentam."""
    bad = [
        correction_row("0", 1, "lower"),
        correction_row("0", 1, "upper", correction=0.5, infinite=True),
    ]
    rows = {**complete_rows(), GOLD_CONFORMAL_CORRECTIONS.name: bad}
    with pytest.raises(GoldGenerationCorruptError, match=r"infinite = true with correction 0.5"):
        _read(_reader(rows=rows))


class _OnlyReadGeneration:
    """Expõe só `read_generation` e registra as chamadas: outro método seria AttributeError."""

    def __init__(self, inner: InMemoryGoldGenerationReader) -> None:
        self._inner = inner
        self.calls: list[GoldPartition] = []

    def read_generation(self, *, partition: GoldPartition) -> GoldGeneration:
        self.calls.append(partition)
        return self._inner.read_generation(partition=partition)


def test_reader_only_calls_read_generation_once_per_request() -> None:
    """Só leitura (I1; auditoria TA-8): uma `read_generation` da partição pedida."""
    store = InMemoryGoldStore()
    tables, manifest = generation(rows=complete_rows())
    store.publish(partition=PARTITION, tables=tables, manifest=manifest)
    spy = _OnlyReadGeneration(InMemoryGoldGenerationReader(store))
    gold = ReadServingGold(gold_reader=spy).read(asset=ASSET, cohort_id=COHORT)
    assert gold.published
    assert spy.calls == [PARTITION]
