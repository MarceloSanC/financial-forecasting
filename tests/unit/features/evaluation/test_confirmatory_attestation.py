"""Testes do corpo de atestação (Stage 8.1 Task 12; concept D7; ADR 8.1.0003 item 7).

Texto fixo (golden) para uma cópia `COMPLETED` e uma `BLOCKED`; os rótulos de H3
("descritiva") e conformal ("cobertura empírica (não garantida)") com tabela e contagem
do manifesto; nenhum valor de tabela do gold lido (só manifesto, `run_record` e
scorecard); a mesma cópia dá o mesmo texto.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

import pytest

from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    GENERATION_MANIFEST,
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
    JudgedGeneration,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.use_cases.confirmatory_attestation import (  # noqa: E501
    CONFORMAL_TITLE,
    H3_TITLE,
    attestation_body,
)
from tests.unit.features.evaluation.gold.test_refresh_gold_dtos import _manifest

_A, _B, _C = "a" * 64, "b" * 64, "c" * 64
_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_PARTITION = GoldPartition("AAPL", "sweep-01")
_REF = _manifest().parameters.preregistration_ref
_ROWS = {
    "gold_quality_checks": 4,
    "gold_dm_results": 2,
    "gold_h3_importance": 12,
    "gold_h3_shares": 8,
    "gold_h3_reading": 3,
    "gold_h3_vsn": 59,
    "gold_conformal_corrections": 24,
    "gold_conformal_coverage": 96,
}
_SCORECARD: dict[str, object] = {
    "preregistration_ref": _REF,
    "academic_decision_ready": False,
    "readiness_reasons": ["gold_before_anchor"],
    "verdict": {
        "horizons": [
            {
                "horizon": 1,
                "h1": {"horizon": 1, "passed": True},
                "beats_naive": True,
                "beats_or_ties_strong": False,
                "in_mcs": True,
                "h2": "beats_naive_only",
                "primary_winner": "tft",
                "candidate_has_lowest_mean_pinball": True,
            },
            {
                "horizon": 7,
                "h1": {"horizon": 7, "passed": False},
                "beats_naive": False,
                "beats_or_ties_strong": False,
                "in_mcs": False,
                "h2": "not_applicable",
                "primary_winner": None,
                "candidate_has_lowest_mean_pinball": False,
            },
        ],
        "study_success_h1": True,
    },
}
_FAILED = [
    {
        "check": "alignment",
        "kind": "summary",
        "horizon": None,
        "model": None,
        "seed": None,
        "occurrences": 1,
        "detail": "",
    },
    {
        "check": "degeneracy",
        "kind": "by_seed",
        "horizon": 7,
        "model": "tft",
        "seed": 3,
        "occurrences": 2,
        "detail": "rate 0.31 > 0.25",
    },
]


def _record(failed: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"environment": {"commit": _COMMIT}, "failed_checks": failed or []}


def _judged(**changes: object) -> JudgedGeneration:
    fields: dict[str, Any] = {
        "preregistration_ref": _REF,
        "partition": _PARTITION,
        "generation_digest": _A,
        "refresh_status": RefreshStatus.COMPLETED,
        "files": {GENERATION_MANIFEST: _B, RUN_RECORD_DOCUMENT: _C, SCORECARD_DOCUMENT: _C},
        "manifest": _manifest(
            rows_by_table=_ROWS,
            finished_at=datetime(2026, 9, 29, 12, 40, tzinfo=UTC),
        ),
        "documents": {RUN_RECORD_DOCUMENT: _record(), SCORECARD_DOCUMENT: _SCORECARD},
    }
    fields.update(changes)
    return JudgedGeneration(**fields)


def _blocked() -> JudgedGeneration:
    manifest = _manifest(status=RefreshStatus.BLOCKED, rows_by_table={"gold_quality_checks": 4})
    return _judged(
        refresh_status=RefreshStatus.BLOCKED,
        manifest=manifest,
        files={GENERATION_MANIFEST: _B, RUN_RECORD_DOCUMENT: _C},
        documents={RUN_RECORD_DOCUMENT: _record(_FAILED)},
    )


_HEADER = f"""## Corrida confirmatória — `{_REF}`

- status: `{{status}}` (refresh `{{refresh}}`)
- generation_digest: `{_A}`
- commit: `{_COMMIT}`
- tag: `confirmatory-run/{_REF}`
- partição: `AAPL/sweep-01`
- started_at: `2026-09-29T12:00:00+00:00`
- finished_at: `{{finished}}`
"""

_JUDGED_BODY = (
    _HEADER.format(status="JUDGED", refresh="COMPLETED", finished="2026-09-29T12:40:00+00:00")
    + """
### Prontidão para decisão acadêmica

- academic_decision_ready: não
- razões: `gold_before_anchor`

### Veredito por horizonte

| horizonte | H1 | vence o ingênuo | vence ou empata o forte | no MCS | H2 | vencedor primário |
|---|---|---|---|---|---|---|
| 1 | passa | sim | não | sim | `beats_naive_only` | `tft` |
| 7 | falha | não | não | não | `not_applicable` | — |

- sucesso do estudo (H1 em ≥ 1 horizonte): sim

### Leitura de H3 (descritiva)

| tabela | linhas |
|---|---|
| `gold_h3_importance` | 12 |
| `gold_h3_shares` | 8 |
| `gold_h3_reading` | 3 |
| `gold_h3_vsn` | 59 |

### Conformal — cobertura empírica (não garantida)

| tabela | linhas |
|---|---|
| `gold_conformal_corrections` | 24 |
| `gold_conformal_coverage` | 96 |
"""
)

_BLOCKED_BODY = (
    _HEADER.format(status="BLOCKED", refresh="BLOCKED", finished="2026-09-29T12:00:00+00:00")
    + """
### Checks que falharam (refresh BLOCKED, sem veredito)

- `alignment` (`summary`; horizonte —, modelo —, seed —): 1 ocorrência(s) — —
- `degeneracy` (`by_seed`; horizonte 7, modelo tft, seed 3): 2 ocorrência(s) — rate 0.31 > 0.25

### Leitura de H3 (descritiva)

| tabela | linhas |
|---|---|
| `gold_h3_importance` | não publicada |
| `gold_h3_shares` | não publicada |
| `gold_h3_reading` | não publicada |
| `gold_h3_vsn` | não publicada |

### Conformal — cobertura empírica (não garantida)

| tabela | linhas |
|---|---|
| `gold_conformal_corrections` | não publicada |
| `gold_conformal_coverage` | não publicada |
"""
)


@pytest.mark.unit
def test_body_golden_for_judged() -> None:
    assert attestation_body(_judged()) == _JUDGED_BODY


@pytest.mark.unit
def test_body_golden_for_blocked() -> None:
    assert attestation_body(_blocked()) == _BLOCKED_BODY


@pytest.mark.unit
def test_body_labels_h3_descriptive_and_conformal_empirical() -> None:
    lines = attestation_body(_judged()).splitlines()

    assert H3_TITLE == "### Leitura de H3 (descritiva)"
    assert CONFORMAL_TITLE == "### Conformal — cobertura empírica (não garantida)"
    h3, conformal = lines.index(H3_TITLE), lines.index(CONFORMAL_TITLE)
    assert lines[h3 + 2 : h3 + 4] == ["| tabela | linhas |", "|---|---|"]
    assert "| `gold_h3_vsn` | 59 |" in lines[h3:conformal]
    assert "| `gold_conformal_coverage` | 96 |" in lines[conformal:]
    # tabela fora das de H3 e conformal não entra no corpo, nem com contagem
    assert not any("gold_dm_results" in line for line in lines)


@pytest.mark.unit
def test_body_reads_no_gold_value() -> None:
    """Só manifesto, `run_record` e scorecard: arquivos e digests das tabelas não contam."""
    judged = _judged()
    other_tables = _judged(
        files={
            GENERATION_MANIFEST: _C,
            "generation/gold_dm_results.parquet": _B,
            RUN_RECORD_DOCUMENT: _A,
            SCORECARD_DOCUMENT: _B,
        }
    )
    assert attestation_body(other_tables) == attestation_body(judged)
    # o scorecard só entra pelo que a prontidão e o veredito citam
    extra = {**_SCORECARD, "profile": {"anything": [1, 2, 3]}, "manifest_read": {"x": 1}}
    with_extra = _judged(documents={RUN_RECORD_DOCUMENT: _record(), SCORECARD_DOCUMENT: extra})
    assert attestation_body(with_extra) == attestation_body(judged)
    # mudar o que o corpo cita muda o corpo
    moved = dataclasses.replace(judged, generation_digest=_B)
    assert attestation_body(moved) != attestation_body(judged)


@pytest.mark.unit
def test_same_judged_generation_same_body() -> None:
    first, second = _judged(), _judged()
    assert first == second
    assert attestation_body(first) == attestation_body(second)
    assert attestation_body(first).endswith("\n")
    assert "\r" not in attestation_body(first)


@pytest.mark.unit
def test_body_refuses_a_copy_without_what_it_cites() -> None:
    with pytest.raises(ValueError, match="needs gold_model_comparison_confirmatory_scorecard"):
        attestation_body(_judged(documents={RUN_RECORD_DOCUMENT: _record()}))
    with pytest.raises(ValueError, match="has no 'commit'"):
        attestation_body(_judged(documents={RUN_RECORD_DOCUMENT: {"environment": {}}}))
    broken = {**_SCORECARD, "academic_decision_ready": "yes"}
    with pytest.raises(ValueError, match="expected a bool"):
        attestation_body(
            _judged(documents={RUN_RECORD_DOCUMENT: _record(), SCORECARD_DOCUMENT: broken})
        )
