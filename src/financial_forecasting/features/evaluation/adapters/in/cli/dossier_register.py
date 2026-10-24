"""Parser do registro curado `docs/reports/dossier_register.toml` (Stage 8.3, D8, D11).

Fronteira (adapter de entrada): o registro é lido aqui, com a stdlib `tomllib`, e entra
no comando do use case já como `tuple[DossierEntry, ...]` — sem port novo de leitura. Forma
do arquivo (concept 8.3 §4):

    [[entry]]
    kind = "deviation"   # ou finding, pre_anchor, environment, reproduction, internal
    title = "…"
    summary = "…"
    pointer = "docs/stages/…/technical.md#…"
    status = "open"           # só (e obrigatório) em finding

Chave fora da forma, campo faltando, `kind` desconhecido ou TOML inválido → `ValueError`
(o `main` traduz em exit 2) antes de qualquer chamada ao use case. A 1ª barreira do A17
(ponteiro proibido numa entrada citável) é do `DossierEntry` — dono único, vale aqui.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    DossierEntry,
    DossierEntryKind,
)

ENTRY_KEY: Final = "entry"
_REQUIRED: Final = frozenset({"kind", "title", "summary", "pointer"})
_OPTIONAL: Final = frozenset({"status"})


def parse_register(text: str) -> tuple[DossierEntry, ...]:
    """As entradas do registro, na ordem do arquivo.

    Raises:
        ValueError: TOML inválido, chave de topo além de `entry`, entrada com campo a mais
            ou a menos, `kind` desconhecido, valor que não é texto, ou entrada recusada pelo
            `DossierEntry` (finding sem `status = "open"`, ponteiro proibido no citável).
    """
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"dossier register is not valid TOML: {error}") from error
    extra = sorted(set(document) - {ENTRY_KEY})
    if extra:
        raise ValueError(f"dossier register has unknown top-level keys {extra}")
    entries = document.get(ENTRY_KEY, [])
    if not isinstance(entries, list):
        raise ValueError("dossier register 'entry' must be an array of tables ([[entry]])")
    return tuple(_entry(index, raw) for index, raw in enumerate(entries))


def _entry(index: int, raw: object) -> DossierEntry:
    if not isinstance(raw, Mapping):
        raise ValueError(f"dossier register entry {index} must be a table")
    keys = set(raw)
    missing = sorted(_REQUIRED - keys)
    unknown = sorted(keys - _REQUIRED - _OPTIONAL)
    if missing or unknown:
        raise ValueError(f"dossier register entry {index}: missing {missing}, unknown {unknown}")
    for key, value in raw.items():
        if not isinstance(value, str):
            raise ValueError(f"dossier register entry {index}: {key} must be a string")
    try:
        kind = DossierEntryKind(raw["kind"])
    except ValueError as error:
        raise ValueError(
            f"dossier register entry {index}: kind {raw['kind']!r} is not one of "
            f"{[k.value for k in DossierEntryKind]}"
        ) from error
    return DossierEntry(
        kind=kind,
        title=raw["title"],
        summary=raw["summary"],
        pointer=raw["pointer"],
        status=raw.get("status"),
    )


def load_register(path: Path) -> tuple[DossierEntry, ...]:
    """Lê e parseia o arquivo do registro (UTF-8).

    Raises:
        OSError: arquivo ausente ou ilegível.
        ValueError: ver `parse_register`.
    """
    return parse_register(path.read_text(encoding="utf-8"))
