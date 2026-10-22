"""Port-out `PreregistrationSource` — leitura de uma revisão do pré-registro (Stage 6.5).

Port do **consumidor** (concept 6.5 §4 "Application", C2; ADRs `6_5_0001` item 1,
`6_5_0003` itens 2-3). Devolve o **mapeamento cru** de `<name>-r<revision>.toml` (o
VO `Preregistration.from_mapping` valida o plano, não o source) e a âncora da
revisão, se houver (`<name>-r<revision>.anchor.toml`, fora do hash por construção).

O real é o `TomlPreregistrationSource` (`adapters/out/toml/`); o fake é o
`InMemoryPreregistrationSource` (`tests/fakes/features/evaluation/`). A forma do
retorno (`PreregistrationRecord`, `PreregistrationAnchor`) e o erro de revisão
inexistente (`PreregistrationNotFoundError`) moram aqui, junto do port.

Stage 8.1 (concept 8.1 §4, D7, D12; ADR `8_1_0004` item 2a): `judged_records(name=...)`
lê os registros de atestação commitados `<name>-r<revision>.judged.toml` — a verdade
cruzada que o G4 confere antes de qualquer efeito. A forma (`JudgedRecord`) e o prefixo
da tag (`JUDGED_TAG_PREFIX`) moram aqui também.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    RefreshStatus,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.services.git_commit import validate_git_commit_sha
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

ANCHOR_TAG_PREFIX: Final = "preregistration/"
"""Prefixo da tag git da âncora (ADR 6.5.0003 item 1: `preregistration/<ref>`)."""

JUDGED_TAG_PREFIX: Final = "confirmatory-run/"
"""Prefixo da tag git da corrida julgada (concept 8.1 D7: `confirmatory-run/<ref>`)."""


class PreregistrationNotFoundError(ApplicationError):
    """A revisão pedida não existe no source (C2)."""


def _check_text(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"anchor {field} must be a non-empty str, got {value!r}")


@dataclass(frozen=True)
class PreregistrationAnchor:
    """Onde e quando a revisão foi ancorada (ADR 6.5.0003 item 2).

    Raises:
        ValueError: texto vazio, tag sem o prefixo `preregistration/` ou `anchored_at`
            sem fuso.
    """

    tag: str
    commit: str
    comment_url: str
    anchored_at: datetime

    def __post_init__(self) -> None:
        """Textos não vazios, tag com o prefixo e instante com fuso."""
        for name in ("tag", "commit", "comment_url"):
            _check_text(getattr(self, name), field=name)
        if not self.tag.startswith(ANCHOR_TAG_PREFIX):
            raise ValueError(f"anchor tag must start with {ANCHOR_TAG_PREFIX!r}, got {self.tag!r}")
        if not isinstance(self.anchored_at, datetime) or self.anchored_at.tzinfo is None:
            raise ValueError(
                f"anchor anchored_at must be a timezone-aware datetime, got {self.anchored_at!r}"
            )


@dataclass(frozen=True)
class PreregistrationRecord:
    """Uma revisão lida: o mapeamento cru do plano e a âncora (ou `None`)."""

    payload: Mapping[str, object]
    anchor: PreregistrationAnchor | None


class PreregistrationSource(Protocol):
    """Lê uma revisão do pré-registro pelo nome e número."""

    def read(self, *, name: str, revision: int) -> PreregistrationRecord:
        """A revisão `revision` do plano `name`.

        Raises:
            PreregistrationNotFoundError: a revisão não existe.
            ValueError: artefato malformado (TOML inválido, âncora com chave a mais ou
                a menos, instante sem fuso).
        """
        ...

    def judged_records(self, *, name: str) -> tuple[JudgedRecord, ...]:
        """Os registros `.judged.toml` do plano `name`, ordenados pela revisão.

        Sem arquivo → tupla vazia.

        Raises:
            ValueError: registro malformado (chave a mais ou a menos, campo inválido,
                nome de arquivo sem revisão inteira).
        """
        ...


@dataclass(frozen=True, kw_only=True)
class JudgedRecord:
    """O registro de atestação commitado de uma revisão julgada (concept 8.1 §4, D7).

    Campos: `revision` (do nome do arquivo), `preregistration_ref`, `generation_digest`
    (sha256 hex do `CONTENTS.sha256`), `refresh_status`, `commit` (40 hex), `tag`
    (`confirmatory-run/<preregistration_ref>`), `comment_url`, `commented_at` (com fuso),
    `input_backup` e `input_backup_sha256`, `judged_backup` e `judged_backup_sha256`
    (sha256 hex da listagem `sha256sum` de cada backup, ADR 8.1.0003 itens 6b-6c).

    Raises:
        ValueError: campo de tipo ou forma errada, na construção.
    """

    revision: int
    preregistration_ref: str
    generation_digest: str
    refresh_status: RefreshStatus
    commit: str
    tag: str
    comment_url: str
    commented_at: datetime
    input_backup: str
    input_backup_sha256: str
    judged_backup: str
    judged_backup_sha256: str

    def __post_init__(self) -> None:
        """Forma de cada campo; a tag é a da própria referência."""
        validate_int_at_least(self.revision, minimum=0, field="judged revision")
        for name in ("preregistration_ref", "comment_url", "input_backup", "judged_backup"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"judged {name} must be a non-empty str, got {value!r}")
        for name in ("generation_digest", "input_backup_sha256", "judged_backup_sha256"):
            validate_sha256_hex(getattr(self, name), field=f"judged {name}")
        if not isinstance(self.refresh_status, RefreshStatus):
            raise ValueError(
                f"judged refresh_status must be a RefreshStatus, got {self.refresh_status!r}"
            )
        validate_git_commit_sha(self.commit, field="judged commit")
        expected_tag = f"{JUDGED_TAG_PREFIX}{self.preregistration_ref}"
        if self.tag != expected_tag:
            raise ValueError(f"judged tag must be {expected_tag!r}, got {self.tag!r}")
        if not isinstance(self.commented_at, datetime) or self.commented_at.tzinfo is None:
            raise ValueError(
                f"judged commented_at must be a timezone-aware datetime, got {self.commented_at!r}"
            )
