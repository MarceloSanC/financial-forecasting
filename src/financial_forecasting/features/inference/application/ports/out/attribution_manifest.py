"""Port-out `AttributionManifest` do `inference` — proveniência write-ahead da atribuição (7.3).

O manifesto da atribuição de um cohort (`<data_root>/inference/<cohort_id>/
attribution_manifest.json` no adapter real; ADR 7.3.0002 item 2, padrão do ADR
7.1.0004) registra, por run, o plano e a partição com que as predições permutadas e os
pesos da VSN foram gravados. A entrada de um run é gravada com status `started` ANTES
da primeira linha (write-ahead) e passa a `completed` depois das duas escritas.

Campos de uma entrada (`ATTRIBUTION_ENTRY_FIELDS`): `status`, `checkpoint_sha256`,
`first_write_environment`, `settings`, `mode`, `max_abs_diff`, `permutation_seed`, `k_p`,
`permutation_algorithm`, `fold_index`, `n_decisions`, `family_partition`,
`partition_hash`, `permuted_rows`, `vsn_rows`.

Regra de mescla — a mesma do manifesto da inferência (`merge_run_entry`/
`apply_run_entry` e `FIRST_WRITE_FIELDS` de `inference_manifest`), usada pelo adapter E
pelo fake: os campos de primeira escrita (`checkpoint_sha256`,
`first_write_environment`) nunca são sobrescritos; os demais são substituídos; `runs`
com forma inválida é manifesto ilegível (`ValueError`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

ATTRIBUTION_ENTRY_FIELDS = (
    "status",
    "checkpoint_sha256",
    "first_write_environment",
    "settings",
    "mode",
    "max_abs_diff",
    "permutation_seed",
    "k_p",
    "permutation_algorithm",
    "fold_index",
    "n_decisions",
    "family_partition",
    "partition_hash",
    "permuted_rows",
    "vsn_rows",
)
"""Campos que o `RunPermutationInference` grava na entrada de cada run."""

STARTED = "started"
COMPLETED = "completed"


class AttributionManifest(Protocol):
    """Proveniência da atribuição de um cohort, por run, com escrita atômica."""

    def recorded(self, cohort_id: str) -> Mapping[str, object] | None:
        """O documento inteiro do cohort, ou `None` sem manifesto."""
        ...

    def record_run(self, cohort_id: str, run_id: str, entry: Mapping[str, object]) -> None:
        """Mescla `entry` na entrada do run (`apply_run_entry`) e grava."""
        ...
