"""Port-out `PreregistrationSource` — leitura de uma revisão do pré-registro (Stage 6.5).

Port do **consumidor** (concept 6.5 §4 "Application", C2; ADRs `6_5_0001` item 1,
`6_5_0003` itens 2-3). Devolve o **mapeamento cru** de `<name>-r<revision>.toml` (o
VO `Preregistration.from_mapping` valida o plano, não o source) e a âncora da
revisão, se houver (`<name>-r<revision>.anchor.toml`, fora do hash por construção).

O real é o `TomlPreregistrationSource` (`adapters/out/toml/`); o fake é o
`InMemoryPreregistrationSource` (`tests/fakes/features/evaluation/`). A forma do
retorno (`PreregistrationRecord`, `PreregistrationAnchor`) e o erro de revisão
inexistente (`PreregistrationNotFoundError`) moram aqui, junto do port.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from financial_forecasting.shared.domain.exceptions.base import ApplicationError

ANCHOR_TAG_PREFIX: Final = "preregistration/"
"""Prefixo da tag git da âncora (ADR 6.5.0003 item 1: `preregistration/<ref>`)."""


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
