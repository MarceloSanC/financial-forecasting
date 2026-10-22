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

Stage 8.1 (`judged_records`): `<root>/<name>-r<revision>.judged.toml`, os registros de
atestação commitados, com exatamente as chaves de `_JUDGED_KEYS` (como o `.anchor.toml`);
a revisão vem do nome do arquivo e `commented_at` é um *offset date-time* TOML nativo.
"""

from __future__ import annotations

import re
import tomllib
from datetime import datetime
from pathlib import Path

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JudgedRecord,
    PreregistrationAnchor,
    PreregistrationNotFoundError,
    PreregistrationRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.shared.domain.services.path_identifier import (
    validate_path_identifier,
)

_ANCHOR_KEYS = frozenset({"tag", "commit", "comment_url", "anchored_at"})
_JUDGED_KEYS = frozenset(
    {
        "preregistration_ref",
        "generation_digest",
        "refresh_status",
        "commit",
        "tag",
        "comment_url",
        "commented_at",
        "input_backup",
        "input_backup_sha256",
        "judged_backup",
        "judged_backup_sha256",
    }
)
_JUDGED_SUFFIX = ".judged.toml"


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
        validate_int_at_least(revision, minimum=0, field="revision")
        plan_path = self._root / f"{name}-r{revision}.toml"
        if not plan_path.is_file():
            raise PreregistrationNotFoundError(
                f"preregistration {name!r} revision {revision} not found ({plan_path.name})"
            )
        payload = _load(plan_path)
        anchor_path = self._root / f"{name}-r{revision}.anchor.toml"
        anchor = _anchor(anchor_path) if anchor_path.is_file() else None
        return PreregistrationRecord(payload=payload, anchor=anchor)

    def judged_records(self, *, name: str) -> tuple[JudgedRecord, ...]:
        """Os `<name>-r<revision>.judged.toml` sob a raiz, ordenados pela revisão."""
        validate_path_identifier(name, field="name")
        pattern = re.compile(rf"{re.escape(name)}-r(\d+){re.escape(_JUDGED_SUFFIX)}")
        records: list[JudgedRecord] = []
        for path in sorted(self._root.glob(f"{name}-r*{_JUDGED_SUFFIX}")):
            match = pattern.fullmatch(path.name)
            if match is None:
                raise ValueError(f"{path.name}: judged record file name has no integer revision")
            records.append(_judged(path, revision=int(match.group(1))))
        return tuple(sorted(records, key=lambda record: record.revision))


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


def _judged(path: Path, *, revision: int) -> JudgedRecord:
    fields = _load(path)
    if set(fields) != _JUDGED_KEYS:
        raise ValueError(
            f"{path.name} must have exactly the keys {sorted(_JUDGED_KEYS)}, got {sorted(fields)}"
        )
    commented_at = fields["commented_at"]
    if not isinstance(commented_at, datetime):
        raise ValueError(
            f"{path.name}: commented_at must be a TOML date-time, got {commented_at!r}"
        )
    try:
        status = RefreshStatus(str(fields["refresh_status"]))
    except ValueError as error:
        raise ValueError(f"{path.name}: {error}") from error
    return JudgedRecord(
        revision=revision,
        preregistration_ref=fields["preregistration_ref"],  # type: ignore[arg-type]
        generation_digest=fields["generation_digest"],  # type: ignore[arg-type]
        refresh_status=status,
        commit=fields["commit"],  # type: ignore[arg-type]
        tag=fields["tag"],  # type: ignore[arg-type]
        comment_url=fields["comment_url"],  # type: ignore[arg-type]
        commented_at=commented_at,
        input_backup=fields["input_backup"],  # type: ignore[arg-type]
        input_backup_sha256=fields["input_backup_sha256"],  # type: ignore[arg-type]
        judged_backup=fields["judged_backup"],  # type: ignore[arg-type]
        judged_backup_sha256=fields["judged_backup_sha256"],  # type: ignore[arg-type]
    )
