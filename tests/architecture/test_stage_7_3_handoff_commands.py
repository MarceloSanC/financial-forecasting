"""Handoff da Stage 7.3 para a fase Linux (Task 33; concept CA16; ADR 7.3.0006 itens 2, 5, 6).

A entrada `[handoff]` da §7 do technical 7.3 é o roteiro da fase Linux (L0 a L8 e L6b).
Um subcomando renomeado ou removido da CLI quebraria o roteiro só na máquina Linux; aqui
ele reprova o CI antes:

- todo subcomando que o roteiro usa tem `--help` (o parser o conhece);
- todo `financial_forecasting.cli <sub>` (ou `$CLI <sub>`, a variável do roteiro)
  citado na entrada `[handoff]` está nessa lista, e a lista inteira é citada.

Fica em `tests/architecture/` porque lê um arquivo do repo (`docs/stages/`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from financial_forecasting import cli

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]
_TECHNICAL = _REPO / "docs" / "stages" / "7.3-explainability" / "technical.md"
_SUBCOMMANDS = (
    "attribute",
    "ablation-pilot",
    "ablation-run",
    "ablation-verify",
    "ablation-freeze",
    "verify",
)
_SECTION = "## 7. Execução"
_END = "<!-- END: post-execution -->"
_CITED = re.compile(r"(?:financial_forecasting\.cli|\$CLI)\s+([a-z][a-z-]*)")


def _handoff_entry() -> str:
    """A entrada `[decision] handoff` da §7 (do título até a próxima entrada)."""
    text = _TECHNICAL.read_text(encoding="utf-8")
    section = text[text.index(_SECTION) : text.index(_END)]
    entries = re.split(r"\n(?=### )", section)
    # o vocabulário da §7 não tem `[handoff]` (G9): a entrada é `— [decision] handoff —`
    handoff = [entry for entry in entries if "— [decision] handoff —" in entry.splitlines()[0]]
    assert len(handoff) == 1, f"expected one [handoff] entry in §7, found {len(handoff)}"
    return handoff[0]


@pytest.mark.parametrize("subcommand", _SUBCOMMANDS)
def test_every_cited_subcommand_has_help(
    subcommand: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([subcommand, "--help"])
    assert exit_info.value.code == 0
    assert "--data-root" in capsys.readouterr().out


def test_handoff_cites_only_known_subcommands() -> None:
    cited = set(_CITED.findall(_handoff_entry()))
    assert cited <= set(_SUBCOMMANDS), sorted(cited - set(_SUBCOMMANDS))
    assert cited == set(_SUBCOMMANDS), sorted(set(_SUBCOMMANDS) - cited)
