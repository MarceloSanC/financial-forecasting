"""Contract test do port `ServingGoldReader` do `inference` — suíte ÚNICA para o fake e o real.

Prova (concept 7.4 CA9; ADR 7.4.0001 item 7) que toda implementação devolve, por
cenário, exatamente o mesmo `ServingGold`:

- não publicado; `BLOCKED`; COMPLETED sem `[conformal]` e sem `[h3]`;
- COMPLETED com os dois blocos: unidade `ok`, `undefined` e infinita; participação com
  limite infinito e participação não-`ok` com limite finito; VSN `ok`;
- COMPLETED com VSN `undefined` (linhas sem rótulo e medidas nulas).

Pernas: `fake` (`InMemoryServingGoldReader` carregado com o `ServingGold` esperado) e
`real` (`ReadServingGold` sobre um `ParquetGoldStore` em `tmp_path`, com a geração
publicada pelo `publish` real). A perna fake é uma **busca simples** por partição: não
monta nada a partir do gold, então devolver o esperado não prova regra de leitura. O
que ela prova é a forma do contrato que os testes do `ServeInference` usam (o mesmo
`ServingGold` por cenário e o erro como `ApplicationError`); a montagem é provada só
na perna real, aqui e em `test_real_reads_what_the_real_builders_write`.

Erro: a perna fake com `error=` e a perna real com a geração corrompida (tabela
apagada) erguem `ApplicationError`. O leitor é anotado pelo Protocol do `inference`,
conferido pelo mypy do `make typecheck`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.conformal_corrections import (  # noqa: E501
    ConformalCorrectionsGoldBuilder,
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
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_H3_VSN,
    GOLD_SCHEMAS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
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
from financial_forecasting.features.inference.application.ports.out.serving_gold_reader import (
    ServingGoldReader,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from tests.contract.features.evaluation._gold_inputs import completed_inputs
from tests.fakes.features.inference.in_memory_serving_gold_reader import (
    InMemoryServingGoldReader,
)
from tests.unit.features.evaluation._serving_gold_rows import (
    complete_rows,
    generation,
    refresh_parameters,
    vsn_row,
)

pytestmark = pytest.mark.contract

_ASSET = "AAPL"
_COHORT = "aapl_confirmatory-r0-abc"
_PARTITION = GoldPartition(_ASSET, _COHORT)
_SPLIT = "split_cqr_asymmetric_unweighted_v1"
_FINISHED = "2026-10-02T12:00:00+00:00"
_REF = "aapl_confirmatory-r3-0123456789ab"
_Rows = dict[str, list[dict[str, object]]]


@dataclass(frozen=True)
class Scenario:
    """O que publicar (nada, se `status` é `None`) e o `ServingGold` esperado."""

    status: RefreshStatus | None
    rows: _Rows
    parameters: RefreshParameters | None
    expected: ServingGold


def _published(
    status: str,
    *,
    conformal: tuple[str, str | None],
    explainability: tuple[str, str | None],
    corrections: tuple[ConformalCorrectionRecord, ...] = (),
    h3: tuple[tuple[H3ShareRecord, ...], H3ReadingRecord | None, tuple[VsnRecord, ...]] = (
        (),
        None,
        (),
    ),
) -> ServingGold:
    return ServingGold(
        published=True,
        generation_status=status,
        preregistration_ref=_REF,
        candidate="tft_quantile",
        finished_at=_FINISHED,
        conformal_status=conformal[0],
        conformal_reason=conformal[1],
        explainability_status=explainability[0],
        explainability_reason=explainability[1],
        conformal_label=EMPIRICAL_COVERAGE_LABEL,
        h3_label=H3_LABEL,
        vsn_label=VSN_LABEL,
        corrections=corrections,
        shares=h3[0],
        reading=h3[1],
        vsn=h3[2],
    )


_CORRECTIONS = (
    ConformalCorrectionRecord(
        "0", 1, 1, 0.1, 0.9, _SPLIT, "lower", 0.1, "ok", None, 200, 190, 0.00390625
    ),
    ConformalCorrectionRecord(
        "0", 1, 1, 0.1, 0.9, _SPLIT, "upper", 0.9, "ok", None, 10, 11, math.inf
    ),
    ConformalCorrectionRecord(
        "0", 1, 7, 0.1, 0.9, _SPLIT, "lower", 0.1, "ok", None, 200, 190, 0.0078125
    ),
    ConformalCorrectionRecord(
        "0", 1, 7, 0.1, 0.9, _SPLIT, "upper", 0.9, "ok", None, 200, 190, 0.015625
    ),
    ConformalCorrectionRecord(
        "1", 2, 1, 0.1, 0.9, _SPLIT, "lower", 0.1, "undefined", "n < 1/alpha", None, None, None
    ),
    ConformalCorrectionRecord(
        "1", 2, 1, 0.1, 0.9, _SPLIT, "upper", 0.9, "undefined", "n < 1/alpha", None, None, None
    ),
)
_SHARES = (
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
_READING = H3ReadingRecord(
    "interval_side_agreement_same_family_v1",
    True,
    False,
    True,
    ("price", "technical"),
    1505,
    "ok",
    None,
)
_VSN_OK = (
    VsnRecord("family", "price", "price", 0.125, 0.25, 0.5, 1505, "ok", None),
    VsnRecord("variable", "log_return", "price", 0.125, 0.25, 0.5, 1505, "ok", None),
)
_VSN_UNDEFINED = (
    VsnRecord("family", "price", "price", None, None, None, None, "undefined", "sem pesos"),
)


def _undefined_vsn_rows() -> _Rows:
    undefined: dict[str, object] = {
        "p10": None,
        "p50": None,
        "p90": None,
        "n_decisions": None,
        "label": None,
        "status": "undefined",
        "reason": "sem pesos",
    }
    return {**complete_rows(), GOLD_H3_VSN.name: [vsn_row("family", "price", **undefined)]}


_BLOCKED = (UNAVAILABLE, "geração gold BLOCKED")
_BOTH = (AVAILABLE, None)

SCENARIOS: dict[str, Scenario] = {
    "unpublished": Scenario(
        status=None,
        rows={},
        parameters=None,
        expected=ServingGold.unpublished(
            reason=f"gold não publicado para o cohort {_COHORT}",
            conformal_label=EMPIRICAL_COVERAGE_LABEL,
            h3_label=H3_LABEL,
            vsn_label=VSN_LABEL,
        ),
    ),
    "blocked": Scenario(
        status=RefreshStatus.BLOCKED,
        rows={},
        parameters=None,
        expected=_published("BLOCKED", conformal=_BLOCKED, explainability=_BLOCKED),
    ),
    # BLOCKED vence a falta de bloco no pré-registro: o status é conferido antes (TA-4)
    "blocked-without-blocks": Scenario(
        status=RefreshStatus.BLOCKED,
        rows={},
        parameters=refresh_parameters(conformal=False, h3=False),
        expected=_published("BLOCKED", conformal=_BLOCKED, explainability=_BLOCKED),
    ),
    "completed-without-blocks": Scenario(
        status=RefreshStatus.COMPLETED,
        rows={},
        parameters=refresh_parameters(conformal=False, h3=False),
        expected=_published(
            "COMPLETED",
            conformal=(UNAVAILABLE, "geração sem bloco [conformal]"),
            explainability=(UNAVAILABLE, "geração sem bloco [h3]"),
        ),
    ),
    "completed-with-both-blocks": Scenario(
        status=RefreshStatus.COMPLETED,
        rows=complete_rows(),
        parameters=None,
        expected=_published(
            "COMPLETED",
            conformal=_BOTH,
            explainability=_BOTH,
            corrections=_CORRECTIONS,
            h3=(_SHARES, _READING, _VSN_OK),
        ),
    ),
    "completed-with-undefined-vsn": Scenario(
        status=RefreshStatus.COMPLETED,
        rows=_undefined_vsn_rows(),
        parameters=None,
        expected=_published(
            "COMPLETED",
            conformal=_BOTH,
            explainability=_BOTH,
            corrections=_CORRECTIONS,
            h3=(_SHARES, _READING, _VSN_UNDEFINED),
        ),
    ),
}


def _fake(_: Path, scenario: Scenario) -> ServingGoldReader:
    return InMemoryServingGoldReader({(_ASSET, _COHORT): scenario.expected})


def _real(root: Path, scenario: Scenario) -> ServingGoldReader:
    store = ParquetGoldStore(root)
    if scenario.status is not None:
        tables, manifest = generation(
            scenario.status, rows=scenario.rows, parameters=scenario.parameters
        )
        store.publish(partition=_PARTITION, tables=tables, manifest=manifest)
    return ReadServingGold(gold_reader=store)


LEGS: dict[str, Callable[[Path, Scenario], ServingGoldReader]] = {"fake": _fake, "real": _real}


@pytest.mark.parametrize("scenario_name", list(SCENARIOS))
@pytest.mark.parametrize("leg", list(LEGS))
def test_reader_returns_the_expected_serving_gold(
    leg: str, scenario_name: str, tmp_path: Path
) -> None:
    scenario = SCENARIOS[scenario_name]
    reader: ServingGoldReader = LEGS[leg](tmp_path, scenario)
    assert reader.read(asset=_ASSET, cohort_id=_COHORT) == scenario.expected


_OTHER_COHORT = "aapl_confirmatory-r0-other"


def _fake_other_cohort(_: Path) -> InMemoryServingGoldReader:
    return InMemoryServingGoldReader(
        {(_ASSET, _COHORT): SCENARIOS["completed-with-both-blocks"].expected}
    )


def _real_other_cohort(root: Path) -> ServingGoldReader:
    store = ParquetGoldStore(root)
    tables, manifest = generation(RefreshStatus.COMPLETED, rows=complete_rows())
    store.publish(partition=_PARTITION, tables=tables, manifest=manifest)
    return ReadServingGold(gold_reader=store)


@pytest.mark.parametrize("leg", ["fake", "real"])
def test_another_cohort_of_a_published_asset_is_unpublished(leg: str, tmp_path: Path) -> None:
    """Partição sem geração (outro cohort do mesmo ativo) → `unpublished`, nas duas pernas."""
    reader = _fake_other_cohort(tmp_path) if leg == "fake" else _real_other_cohort(tmp_path)
    gold = reader.read(asset=_ASSET, cohort_id=_OTHER_COHORT)
    assert gold == ServingGold.unpublished(
        reason=f"gold não publicado para o cohort {_OTHER_COHORT}",
        conformal_label=EMPIRICAL_COVERAGE_LABEL,
        h3_label=H3_LABEL,
        vsn_label=VSN_LABEL,
    )
    if isinstance(reader, InMemoryServingGoldReader):
        assert reader.calls == [(_ASSET, _OTHER_COHORT)]


def _fake_with_error(_: Path) -> ServingGoldReader:
    corrupt = GoldGenerationCorruptError("the generation has no table 'gold_h3_vsn'")
    return InMemoryServingGoldReader({}, error=corrupt)


def _real_corrupt(root: Path) -> ServingGoldReader:
    store = ParquetGoldStore(root)
    tables, manifest = generation(RefreshStatus.COMPLETED, rows=complete_rows())
    store.publish(partition=_PARTITION, tables=tables, manifest=manifest)
    (store.current_dir(_PARTITION) / f"{GOLD_H3_VSN.name}.parquet").unlink()
    return ReadServingGold(gold_reader=store)


CORRUPT_LEGS: dict[str, Callable[[Path], ServingGoldReader]] = {
    "fake": _fake_with_error,
    "real": _real_corrupt,
}


@pytest.mark.parametrize("leg", list(CORRUPT_LEGS))
def test_corrupt_generation_raises_application_error(leg: str, tmp_path: Path) -> None:
    reader = CORRUPT_LEGS[leg](tmp_path)
    with pytest.raises(ApplicationError):
        reader.read(asset=_ASSET, cohort_id=_COHORT)


# --- builders reais (Checkpoint C1-2) ---------------------------------------------------


def _undefined_vsn(inputs: GoldInputs) -> GoldInputs:
    assert inputs.h3_reports.vsn is not None
    vsn = replace(inputs.h3_reports.vsn, status="undefined", reason="sem pesos", entries=())
    return replace(inputs, h3_reports=replace(inputs.h3_reports, vsn=vsn))


def _publish_real_builders(root: Path, inputs: GoldInputs) -> None:
    """As quatro tabelas servidas escritas pelos builders reais; as demais vazias."""
    built = {
        table.name: table
        for table in (
            builder.build(inputs)
            for builder in (
                ConformalCorrectionsGoldBuilder(),
                H3SharesGoldBuilder(),
                H3ReadingGoldBuilder(),
                H3VsnGoldBuilder(),
            )
        )
    }
    tables = [
        built.get(name) or GoldTable(name, schema.key, ()) for name, schema in GOLD_SCHEMAS.items()
    ]
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    manifest = GoldManifest(
        status=RefreshStatus.COMPLETED,
        partition=inputs.partition,
        rows_by_table={table.name: len(table.rows) for table in tables},
        parameters=inputs.parameters,
        horizons=(1, 7),
        window_deficits={inputs.parameters.candidate: 0},
        dataset_fingerprint=DatasetContentFingerprint("ab" * 32),
        grid_trimmed_prefix=0,
        realized_sessions=250,
        realized_returns_fsum=0.125,
        realized_first_timestamp="2024-01-02T00:00:00+00:00",
        realized_last_timestamp="2024-12-31T00:00:00+00:00",
        n_runs=12,
        build_order=tuple(table.name.removeprefix("gold_") for table in tables),
        started_at=now,
        finished_at=now,
    )
    ParquetGoldStore(root).publish(partition=inputs.partition, tables=tables, manifest=manifest)


@pytest.mark.parametrize("vsn", ["ok", "undefined"])
def test_real_reads_what_the_real_builders_write(vsn: str, tmp_path: Path) -> None:
    """Os builders reais da 7.2/7.3 sobre `completed_inputs()`, pelo `ParquetGoldStore`.

    Prende os tipos que só o builder real grava (o blocker C1-1: `side` inteiro), os
    infinitos reconstruídos das flags e o `n` das unidades `ok`.
    """
    inputs = completed_inputs() if vsn == "ok" else _undefined_vsn(completed_inputs())
    _publish_real_builders(tmp_path, inputs)
    reader: ServingGoldReader = ReadServingGold(gold_reader=ParquetGoldStore(tmp_path))
    gold = reader.read(asset=inputs.partition.asset, cohort_id=inputs.partition.parent_sweep_id)

    assert (gold.conformal_status, gold.explainability_status) == (AVAILABLE, AVAILABLE)
    ok_units = [r for r in gold.corrections if r.status == "ok"]
    assert ok_units
    assert {r.n for r in ok_units} == {10}
    assert all(isinstance(r.seed, int) and isinstance(r.horizon, int) for r in gold.corrections)
    assert all(isinstance(r.correction, float) for r in ok_units)
    assert math.inf in {r.correction for r in ok_units}
    assert {r.status for r in gold.corrections} >= {"ok", "error"}

    assert {s.method for s in gold.shares} == {"loco", "permutation"}
    sides = {s.side for s in gold.shares}
    assert sides <= {-1, 0, 1, None}
    assert {-1, 0, 1} <= sides
    assert all(type(s.side) is int for s in gold.shares if s.side is not None)
    assert -math.inf in {s.lower for s in gold.shares}
    assert math.inf in {s.upper for s in gold.shares}
    # participação não-ok com limite finito gravado: o valor passa (0.0, não None)
    (zero,) = (s for s in gold.shares if s.status != "ok" and s.lower is not None)
    assert (zero.lower, zero.upper, zero.side) == (0.0, 0.0, 0)

    # uma linha de cada tabela, valor a valor, como os builders reais a gravam (TA-2)
    assert (
        ConformalCorrectionRecord(
            "1",
            2,
            2,
            0.1,
            0.9,
            _SPLIT,
            "lower",
            0.1,
            "error",
            "points[3].target_timestamp: not before test_start",
            None,
            None,
            None,
        )
        in gold.corrections
    )
    assert (
        H3ShareRecord(
            "permutation", "price", 0.4, 0.2, -0.2, -0.3, -0.1, 0.975, -1, True, "ok", None
        )
        in gold.shares
    )
    assert gold.reading == H3ReadingRecord(
        "interval_side_agreement_same_family_v1",
        True,
        None,
        False,
        (),
        3,
        "undefined",
        "loco: the point total of importances is <= 0 at h=1 or h=7 (H3-NEG)",
    )
    if vsn == "ok":
        assert (
            VsnRecord("variable", "log_return", "price", 0.1, 0.2, 0.3, 40, "ok", None) in gold.vsn
        )
    assert gold.reading is not None
    if vsn == "ok":
        assert {v.status for v in gold.vsn} == {"ok"}
        assert all(isinstance(v.n_decisions, int) for v in gold.vsn)
    else:
        assert {v.status for v in gold.vsn} == {"undefined"}
        assert all(v.p10 is v.p50 is v.p90 is v.n_decisions is None for v in gold.vsn)
