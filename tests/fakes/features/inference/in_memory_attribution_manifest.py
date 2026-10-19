"""Fake in-memory do port `AttributionManifest` (Stage 7.3).

Um `dict` cohort → documento, mesclado pela MESMA `apply_run_entry` do manifesto da
inferência que o adapter JSON usa (paridade por construção). `history` guarda
`(run_id, status)` de cada `record_run`, na ordem — os testes provam o write-ahead
(entrada `started` antes da primeira escrita no silver).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

from financial_forecasting.features.inference.application.ports.out.inference_manifest import (
    apply_run_entry,
)


class InMemoryAttributionManifest:
    """Manifesto da atribuição por cohort em memória."""

    def __init__(self, documents: Mapping[str, Mapping[str, object]] | None = None) -> None:
        self._documents: dict[str, dict[str, object]] = {
            cohort: copy.deepcopy(dict(document)) for cohort, document in (documents or {}).items()
        }
        self.history: list[tuple[str, object]] = []

    def recorded(self, cohort_id: str) -> Mapping[str, object] | None:
        document = self._documents.get(cohort_id)
        return copy.deepcopy(document) if document is not None else None

    def record_run(self, cohort_id: str, run_id: str, entry: Mapping[str, object]) -> None:
        self._documents[cohort_id] = apply_run_entry(
            self._documents.get(cohort_id), cohort_id=cohort_id, run_id=run_id, entry=entry
        )
        self.history.append((run_id, entry.get("status")))
