"""`TomlPreregistrationSource` — satisfaz o port `PreregistrationSource` com `tomllib`.

Adapter de saída (concept 6.5 §4 "Adapters", §8 "Externas", C2; ADRs `6_5_0001` item
1, `6_5_0003` itens 2-3). Lê, sob a raiz injetada (`settings.repo_root /
"config/preregistration"` no composition root):

- `<root>/<name>-r<revision>.toml` — o plano, devolvido como mapeamento **cru** (o
  VO `Preregistration.from_mapping` valida; este adapter só faz I/O). Ausente →
  `PreregistrationNotFoundError`; TOML inválido → `ValueError` com o caminho;
- `<root>/<name>-r<revision>.anchor.toml` — a âncora, se existir, com exatamente as
  chaves `tag`, `commit`, `comment_url` e `anchored_at` (este um *offset date-time*
  TOML nativo; data local sem fuso → `ValueError`).

`name` passa pela regra única de identificador de caminho antes de montar o caminho;
`revision` é `int` não-`bool` ≥ 0.
"""

from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path

from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationAnchor,
    PreregistrationNotFoundError,
    PreregistrationRecord,
)
from financial_forecasting.shared.domain.services.path_identifier import (
    validate_path_identifier,
)

_ANCHOR_KEYS = frozenset({"tag", "commit", "comment_url", "anchored_at"})


def _load(path: Path) -> dict[str, object]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path.name} is not valid TOML: {error}") from error


class TomlPreregistrationSource:
    """Lê as revisões do pré-registro de arquivos TOML sob uma raiz."""

    def __init__(self, root: Path) -> None:
        """`root`: o diretório `config/preregistration` do repositório."""
        self._root = root

    def read(self, *, name: str, revision: int) -> PreregistrationRecord:
        """O plano cru e a âncora (ou `None`) da revisão (ver docstring do módulo)."""
        validate_path_identifier(name, field="name")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError(f"revision must be an int >= 0, got {revision!r}")
        plan_path = self._root / f"{name}-r{revision}.toml"
        if not plan_path.is_file():
            raise PreregistrationNotFoundError(
                f"preregistration {name!r} revision {revision} not found ({plan_path.name})"
            )
        payload = _load(plan_path)
        anchor_path = self._root / f"{name}-r{revision}.anchor.toml"
        anchor = _anchor(anchor_path) if anchor_path.is_file() else None
        return PreregistrationRecord(payload=payload, anchor=anchor)


def _anchor(path: Path) -> PreregistrationAnchor:
    fields = _load(path)
    if set(fields) != _ANCHOR_KEYS:
        raise ValueError(
            f"{path.name} must have exactly the keys {sorted(_ANCHOR_KEYS)}, got {sorted(fields)}"
        )
    anchored_at = fields["anchored_at"]
    if not isinstance(anchored_at, datetime):
        raise ValueError(f"{path.name}: anchored_at must be a TOML date-time, got {anchored_at!r}")
    return PreregistrationAnchor(
        tag=fields["tag"],  # type: ignore[arg-type]
        commit=fields["commit"],  # type: ignore[arg-type]
        comment_url=fields["comment_url"],  # type: ignore[arg-type]
        anchored_at=anchored_at,
    )
