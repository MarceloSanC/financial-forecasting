"""Contract test do port `ServingGoldReader` do `inference` — suíte ÚNICA para o fake e o real.

Prova (concept 7.4 CA9; ADR 7.4.0001 item 7) que toda implementação devolve, por
cenário, exatamente o mesmo `ServingGold`:

- não publicado; `BLOCKED`; COMPLETED sem `[conformal]` e sem `[h3]`;
- COMPLETED com os dois blocos: unidade `ok`, `undefined` e infinita; participação com
  limite infinito e participação não-`ok` com limite finito; VSN `ok`;
- COMPLETED com VSN `undefined` (linhas sem rótulo e medidas nulas).

Pernas: `fake` (`InMemoryServingGoldReader` carregado com o `ServingGold` esperado) e
`real` (`ReadServingGold` sobre um `ParquetGoldStore` em `tmp_path`, com a geração
publicada pelo `publish` real). Só na perna real: geração corrompida (tabela apagada)
→ `ApplicationError`. O leitor é anotado pelo Protocol do `inference`, conferido pelo
mypy strict explícito da Task 04.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_H3_VSN,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
    RefreshParameters,
    RefreshStatus,
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
from tests.fakes.features.inference.in_memory_serving_gold_reader import (
    InMemoryServingGoldReader,
)
from tests.unit.features.evaluation.test_read_serving_gold import (
    complete_rows,
    generation,
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
        "1", 2, 1, 0.1, 0.9, _SPLIT, "lower", 0.1, "undefined", "n < 1/alpha", None, None, None
    ),
    ConformalCorrectionRecord(
        "1", 2, 1, 0.1, 0.9, _SPLIT, "upper", 0.9, "undefined", "n < 1/alpha", None, None, None
    ),
)
_SHARES = (
    H3ShareRecord(
        "ablation",
        "price",
        0.5,
        0.25,
        -0.25,
        -math.inf,
        0.125,
        0.9875,
        -1,
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
    False,
    ("price", "technical"),
    1505,
    "ok",
    None,
)
_VSN_OK = (
    VsnRecord("family", "price", "price", 0.125, 0.25, 0.5, 1505, "ok", None),
    VsnRecord("variable", "log_return", "log_return", 0.125, 0.25, 0.5, 1505, "ok", None),
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


def _without_blocks() -> RefreshParameters:
    default = generation()[1].parameters
    return replace(default, conformal_parameters=None, h3_parameters=None)


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
    "completed-without-blocks": Scenario(
        status=RefreshStatus.COMPLETED,
        rows={},
        parameters=_without_blocks(),
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


def test_real_corrupt_generation_raises_application_error(tmp_path: Path) -> None:
    store = ParquetGoldStore(tmp_path)
    tables, manifest = generation(RefreshStatus.COMPLETED, rows=complete_rows())
    store.publish(partition=_PARTITION, tables=tables, manifest=manifest)
    (store.current_dir(_PARTITION) / f"{GOLD_H3_VSN.name}.parquet").unlink()
    reader: ServingGoldReader = ReadServingGold(gold_reader=store)
    with pytest.raises(ApplicationError):
        reader.read(asset=_ASSET, cohort_id=_COHORT)
