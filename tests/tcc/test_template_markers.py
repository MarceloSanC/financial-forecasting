"""Nenhum texto de exemplo do template chega ao PDF do TCC (critério C2 do plano #237, #263).

Lê o `text/Main.tex` e os arquivos que ele inclui de fato (`\\input` não comentado) e procura os
marcadores do template da UFSC. Os campos que só o autor pode preencher (banca, data de
aprovação, tratamento do orientador) ficam em `_PENDING_AUTHOR_DATA`, com a issue que os
acompanha: quando o autor os preencher, a lista esvazia e o teste passa a cobri-los também.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

pytestmark = pytest.mark.unit

_TEXT: Final = Path(__file__).parents[2] / "text"
_INPUT: Final = re.compile(r"^[^%\n]*\\input\{([^}]+)\}", re.MULTILINE)
_MARKERS: Final = (
    "Nome do Membro",
    "Universidade do Membro",
    r"\newcommand{\diaAprovacao}{00}",
    r"\newcommand{\mesAprovacao}{mês}",
    "Dr(a).",
    "Xxxx",
    "Inserir os agradecimentos",
    "Texto da Epígrafe",
    "Dedico este trabalho a ....",
)
_PENDING_AUTHOR_DATA: Final[dict[str, str]] = {
    "Nome do Membro": "#263 — banca a definir pelo autor",
    "Universidade do Membro": "#263 — banca a definir pelo autor",
    r"\newcommand{\diaAprovacao}{00}": "#263 — data de aprovação",
    r"\newcommand{\mesAprovacao}{mês}": "#263 — data de aprovação",
    "Dr(a).": "#263 — tratamento do orientador e do coorientador",
}


def _active_sources() -> dict[str, str]:
    main = (_TEXT / "Main.tex").read_text(encoding="utf-8")
    sources = {"Main.tex": main}
    for name in _INPUT.findall(main):
        path = _TEXT / (name if name.endswith(".tex") else f"{name}.tex")
        if path.is_file():
            sources[name] = path.read_text(encoding="utf-8")
    return sources


def test_inputs_are_resolved() -> None:
    sources = _active_sources()
    assert len(sources) > 1, "nenhum \\input ativo encontrado no Main.tex"


@pytest.mark.parametrize("marker", _MARKERS)
def test_no_template_marker_reaches_the_pdf(marker: str) -> None:
    hits = [name for name, text in _active_sources().items() if marker in text]
    if marker in _PENDING_AUTHOR_DATA:
        if hits:
            pytest.xfail(f"{marker!r} em {hits}: {_PENDING_AUTHOR_DATA[marker]}")
        pytest.fail(f"{marker!r} já foi preenchido: tire-o de _PENDING_AUTHOR_DATA")
    assert not hits, f"texto do template {marker!r} ainda é incluído por {hits}"
