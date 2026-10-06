"""Port-out `InferenceManifest` do slice `inference` — proveniência write-ahead (Stage 7.1).

O manifesto de um cohort (`<data_root>/inference/<cohort_id>/manifest.json` no
adapter real, ADR 7.1.0004 item 4) registra, por run, de onde vieram as linhas de
calib: o sha256 do checkpoint, o ambiente e os parâmetros da PRIMEIRA escrita e o
resultado da última verificação (modo de reprodução, |Δ|, contagens). A entrada de
um run é gravada com status `started` ANTES da primeira linha de calib e passa a
`completed` só depois da releitura (I8).

Documento:

    {"cohort_id": ..., "cohort_environment": {...}, "runs": {run_id: {...}}}

Regra de mescla — dona única: `merge_run_entry`/`apply_run_entry` e
`FIRST_WRITE_FIELDS` aqui, usadas pelo adapter E pelo fake (paridade por
construção): os campos de primeira escrita de um run nunca são sobrescritos; os
demais são substituídos; `cohort_environment` vem na `entry` e é cabeçalho de
primeira escrita do arquivo (gravado no primeiro `record_run`, nunca sobrescrito).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Protocol

FIRST_WRITE_FIELDS = (
    "checkpoint_sha256",
    "first_write_environment",
    "first_write_settings",
    "first_written_at",
)
"""Campos de um run gravados uma única vez (ADR 7.1.0004 item 4)."""

COHORT_ENVIRONMENT = "cohort_environment"
"""Chave do cabeçalho de primeira escrita; chega na `entry` e sai dela no documento."""

RUNS = "runs"


def merge_run_entry(
    previous: Mapping[str, object] | None, entry: Mapping[str, object]
) -> dict[str, object]:
    """Entrada mesclada de um run: primeira escrita preservada, o resto substituído."""
    merged: dict[str, object] = dict(previous or {})
    for key, value in entry.items():
        if key == COHORT_ENVIRONMENT:
            continue
        if previous is not None and key in FIRST_WRITE_FIELDS and key in previous:
            continue
        merged[key] = copy.deepcopy(value)
    return merged


def apply_run_entry(
    document: Mapping[str, object] | None,
    *,
    cohort_id: str,
    run_id: str,
    entry: Mapping[str, object],
) -> dict[str, object]:
    """O documento depois de `record_run(cohort_id, run_id, entry)` (função pura)."""
    updated: dict[str, object] = copy.deepcopy(dict(document)) if document else {}
    updated.setdefault("cohort_id", cohort_id)
    if COHORT_ENVIRONMENT not in updated and COHORT_ENVIRONMENT in entry:
        updated[COHORT_ENVIRONMENT] = copy.deepcopy(entry[COHORT_ENVIRONMENT])
    runs = updated.setdefault(RUNS, {})
    assert isinstance(runs, dict)  # documento montado só por esta função
    previous = runs.get(run_id)
    runs[run_id] = merge_run_entry(previous if isinstance(previous, Mapping) else None, entry)
    return updated


class InferenceManifest(Protocol):
    """Proveniência da inferência de um cohort, por run, com escrita atômica."""

    def recorded(self, cohort_id: str) -> Mapping[str, object] | None:
        """O documento inteiro do cohort, ou `None` sem manifesto."""
        ...

    def record_run(self, cohort_id: str, run_id: str, entry: Mapping[str, object]) -> None:
        """Mescla `entry` na entrada do run (`apply_run_entry`) e grava."""
        ...
