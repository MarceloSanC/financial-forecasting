"""Unit do `ReadServingGold` (Stage 7.4, Task 03) — concept I7, I8; CA3, CA5, CA9 (parte unitária).

Gerações publicadas num `InMemoryGoldStore` e lidas pelo `InMemoryGoldGenerationReader`
(montagem única `GoldGeneration.from_stored`, a mesma do real). Linhas com as colunas
que os builders da 7.2/7.3 gravam.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import pytest

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    CONFIRMATORY_TABLES,
    GOLD_CONFORMAL_CORRECTIONS,
    GOLD_H3_READING,
    GOLD_H3_SHARES,
    GOLD_H3_VSN,
    GOLD_SCHEMAS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldManifest,
    GoldPartition,
    GoldTable,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_generation_reader import (
    GoldGenerationCorruptError,
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
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.vsn_summary import VSN_LABEL
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
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
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from tests.fakes.features.evaluation.in_memory_gold_generation_reader import (
    InMemoryGoldGenerationReader,
)
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore
from tests.unit.features.evaluation._conformal_parameters import conformal_parameters
from tests.unit.features.evaluation._h3_parameters import h3_parameters

pytestmark = pytest.mark.unit

_ASSET = "AAPL"
_COHORT = "aapl_confirmatory-r0-abc"
_PARTITION = GoldPartition(_ASSET, _COHORT)
_REF = "aapl_confirmatory-r3-0123456789ab"
_NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
_SPLIT = "split_cqr_asymmetric_unweighted_v1"
_Rows = Mapping[str, Sequence[Mapping[str, object]]]


def _parameters(*, conformal: bool = True, h3: bool = True) -> RefreshParameters:
    return RefreshParameters(
        preregistration_ref=_REF,
        degeneracy_tolerance=1e-12,
        band_levels=(0.95, 0.975),
        min_violations=2,
        candidate="tft_quantile",
        dm_alpha=0.05,
        dm_variance_estimators=(DmVarianceEstimator.RECTANGULAR,),
        mcs_alpha=0.10,
        mcs_reps=1000,
        mcs_seed=127,
        mcs_schemes=(BootstrapScheme.STATIONARY,),
        monte_carlo_draws=999,
        monte_carlo_seed=128,
        mcs_block_sensitivities=("h",),
        profile_parameters=None,
        conformal_parameters=conformal_parameters() if conformal else None,
        h3_parameters=h3_parameters() if h3 else None,
    )


def _base(**extra: object) -> dict[str, object]:
    return {"asset": _ASSET, "parent_sweep_id": _COHORT, "preregistration_ref": _REF, **extra}


def correction_row(  # noqa: PLR0913
    fold_raw: str,
    seed: int | None,
    tail: str,
    *,
    status: str = "ok",
    reason: str | None = None,
    n: int | None = 200,
    rank: int | None = 190,
    correction: float | None = 0.004,
    infinite: bool | None = False,
) -> dict[str, object]:
    """Uma linha de `gold_conformal_corrections` com as colunas do builder da 7.2."""
    return _base(
        fold_raw=fold_raw,
        fold=int(fold_raw),
        seed=seed,
        horizon=1,
        lower_level=0.1,
        upper_level=0.9,
        variant=_SPLIT,
        tail=tail,
        tail_level=0.1 if tail == "lower" else 0.9,
        rho=None,
        status=status,
        reason=reason,
        n=n,
        rank=rank,
        correction=correction,
        infinite=infinite,
        beta_a=None,
        beta_b=None,
        beta_mean=None,
        beta_sd=None,
    )


def share_row(method: str, family: str, **fields: object) -> dict[str, object]:
    """Uma linha de `gold_h3_shares` com as colunas do builder da 7.3."""
    values: dict[str, object] = {
        "share_h1": 0.5,
        "share_h7": 0.25,
        "delta": -0.25,
        "lower": -0.5,
        "upper": 0.125,
        "lower_infinite": False,
        "upper_infinite": False,
        "level": 0.9875,
        "side": "two_sided",
        "excludes_zero": False,
        "status": "ok",
        "reason": None,
        "nonpositive_replicas_h1": 0,
        "nonpositive_replicas_h7": 0,
        "method_status": "ok",
        "method_reason": None,
    }
    values.update(fields)
    return _base(method=method, family=family, **values)


def reading_row(**fields: object) -> dict[str, object]:
    """A linha de `gold_h3_reading` com as colunas do builder da 7.3."""
    values: dict[str, object] = {
        "reading_rule": "interval_side_agreement_same_family_v1",
        "heterogeneous_permutation": True,
        "heterogeneous_ablation": False,
        "sustained": False,
        "agreeing_families": "price,technical",
        "block_length": 7,
        "max_block_estimate": 6.5,
        "reps": 1000,
        "bootstrap_seed": 129,
        "n_points": 1505,
        "nonpositive_permutation_h1": 0,
        "nonpositive_permutation_h7": 0,
        "nonpositive_ablation_h1": 0,
        "nonpositive_ablation_h7": 0,
        "ablation_cohort_id": "synthetic_ablation_r0_b2b2b2b2b2b2",
        "label": H3_LABEL,
        "status": "ok",
        "reason": None,
    }
    values.update(fields)
    return _base(**values)


def vsn_row(kind: str, name: str, **fields: object) -> dict[str, object]:
    """Uma linha de `gold_h3_vsn` com as colunas do builder da 7.3."""
    values: dict[str, object] = {
        "family": name,
        "p10": 0.125,
        "p50": 0.25,
        "p90": 0.5,
        "n_decisions": 1505,
        "label": VSN_LABEL,
        "status": "ok",
        "reason": None,
    }
    values.update(fields)
    return _base(kind=kind, name=name, **values)


def complete_rows() -> dict[str, list[dict[str, object]]]:
    """As quatro tabelas servidas de uma geração COMPLETED com os dois blocos."""
    return {
        GOLD_CONFORMAL_CORRECTIONS.name: [
            correction_row("0", 1, "lower", correction=0.00390625),
            correction_row("0", 1, "upper", correction=None, infinite=True, n=10, rank=11),
            correction_row("0", None, "lower"),  # unidade de run sem seed: descartada
            correction_row("0", None, "upper"),
            correction_row(
                "1",
                2,
                "lower",
                status="undefined",
                reason="n < 1/alpha",
                n=None,
                rank=None,
                correction=None,
                infinite=None,
            ),
            correction_row(
                "1",
                2,
                "upper",
                status="undefined",
                reason="n < 1/alpha",
                n=None,
                rank=None,
                correction=None,
                infinite=None,
            ),
        ],
        GOLD_H3_SHARES.name: [
            share_row("ablation", "price", lower=None, lower_infinite=True),
            share_row(
                "ablation",
                "technical",
                status="undefined",
                reason="Σ* <= 0",
                upper=None,
                upper_infinite=None,
            ),
            share_row("permutation", "price", upper=None, upper_infinite=True),
            share_row(
                "permutation",
                "technical",
                share_h1=None,
                share_h7=None,
                delta=None,
                lower=None,
                upper=None,
                lower_infinite=None,
                upper_infinite=None,
                level=None,
                side=None,
                excludes_zero=None,
                status="undefined",
                reason="método indefinido",
            ),
        ],
        GOLD_H3_READING.name: [reading_row()],
        GOLD_H3_VSN.name: [vsn_row("family", "price"), vsn_row("variable", "log_return")],
    }


def generation(
    status: RefreshStatus = RefreshStatus.COMPLETED,
    *,
    rows: _Rows | None = None,
    parameters: RefreshParameters | None = None,
) -> tuple[list[GoldTable], GoldManifest]:
    """Tabelas e manifesto de uma geração da partição (COMPLETED lista toda tabela)."""
    given = dict(rows or {})
    names = [
        name
        for name in GOLD_SCHEMAS
        if status is RefreshStatus.COMPLETED or name not in CONFIRMATORY_TABLES
    ]
    tables = [
        GoldTable.sorted_by_key(name, GOLD_SCHEMAS[name].key, given.get(name, ())) for name in names
    ]
    manifest = GoldManifest(
        status=status,
        partition=_PARTITION,
        rows_by_table={table.name: len(table.rows) for table in tables},
        parameters=parameters or _parameters(),
        horizons=(1, 7),
        window_deficits={"tft_quantile": 0},
        dataset_fingerprint=DatasetContentFingerprint("ab" * 32),
        grid_trimmed_prefix=0,
        realized_sessions=250,
        realized_returns_fsum=0.125,
        realized_first_timestamp="2024-01-02T00:00:00+00:00",
        realized_last_timestamp="2024-12-31T00:00:00+00:00",
        n_runs=12,
        build_order=tuple(table.name.removeprefix("gold_") for table in tables),
        started_at=_NOW,
        finished_at=_NOW,
    )
    return tables, manifest


def _reader(
    status: RefreshStatus = RefreshStatus.COMPLETED,
    *,
    rows: _Rows | None = None,
    parameters: RefreshParameters | None = None,
) -> ReadServingGold:
    store = InMemoryGoldStore()
    tables, manifest = generation(status, rows=rows, parameters=parameters)
    store.publish(partition=_PARTITION, tables=tables, manifest=manifest)
    return ReadServingGold(gold_reader=InMemoryGoldGenerationReader(store))


def _read(reader: ReadServingGold) -> ServingGold:
    return reader.read(asset=_ASSET, cohort_id=_COHORT)


_IDENTITY = {
    "published": True,
    "preregistration_ref": _REF,
    "candidate": "tft_quantile",
    "finished_at": "2026-10-02T12:00:00+00:00",
    "conformal_label": EMPIRICAL_COVERAGE_LABEL,
    "h3_label": H3_LABEL,
    "vsn_label": VSN_LABEL,
}


def test_unpublished_partition_is_a_state_not_an_error() -> None:
    reader = ReadServingGold(gold_reader=InMemoryGoldGenerationReader(InMemoryGoldStore()))
    assert _read(reader) == ServingGold.unpublished(
        reason=f"gold não publicado para o cohort {_COHORT}",
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
    gold = _read(_reader(parameters=_parameters(conformal=False, h3=False)))
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
            "0", 1, 1, 0.1, 0.9, _SPLIT, "lower", 0.1, "ok", None, 200, 190, 0.00390625
        ),
        ConformalCorrectionRecord(
            "0", 1, 1, 0.1, 0.9, _SPLIT, "upper", 0.9, "ok", None, 10, 11, math.inf
        ),
        ConformalCorrectionRecord(
            "1", 2, 1, 0.1, 0.9, _SPLIT, "lower", 0.1, "undefined", "n < 1/alpha", None, None, None
        ),
        ConformalCorrectionRecord(
            "1", 2, 1, 0.1, 0.9, _SPLIT, "upper", 0.9, "undefined", "n < 1/alpha", None, None, None
        ),
    )
    assert gold.shares == (
        H3ShareRecord(
            "ablation",
            "price",
            0.5,
            0.25,
            -0.25,
            -math.inf,
            0.125,
            0.9875,
            "two_sided",
            False,
            "ok",
            None,
        ),
        H3ShareRecord(
            "ablation",
            "technical",
            0.5,
            0.25,
            -0.25,
            -0.5,
            None,
            0.9875,
            "two_sided",
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
            "two_sided",
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
        False,
        ("price", "technical"),
        1505,
        "ok",
        None,
    )
    assert gold.vsn == (
        VsnRecord("family", "price", "price", 0.125, 0.25, 0.5, 1505, "ok", None),
        VsnRecord("variable", "log_return", "log_return", 0.125, 0.25, 0.5, 1505, "ok", None),
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
