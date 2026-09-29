"""Carregador da unidade de oráculo R `var_test_cases` (Stage 6.3; ADRs 6.3.0002/0003).

Módulo privado dos testes de integração (sem `test_` no nome; não é `conftest.py`):
lê `tests/fixtures/r_oracle/var_test_cases.json` uma vez e devolve casos tipados —
violações como `tuple[bool, ...]`, a taxa por `float.fromhex(hex)` (a forma exata da
entrada, ADR 6.2.0006) e cada *feed* com `uc`/`cc` ou o erro do R. Importado
absolutamente pelos dois testes de oráculo
(`from tests.integration.features.evaluation._var_test_cases import ...`).

Errata do ADR 6.3.0003: quando o *feed* t ≥ 2 falha, o *feed* traz `lr_uc_internal`
(`rugarch:::.LR.uc(p, T - 1, sum(v[-1]))`), o LR_uc puro calculado pelo próprio R.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

FIXTURE_PATH = (
    Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "r_oracle" / "var_test_cases.json"
)


@dataclass(frozen=True)
class OracleFeed:
    """Um *feed* do `VaRTest`: estatísticas do R ou a mensagem de erro."""

    uc_lrstat: float | None
    cc_lrstat: float | None
    error: str | None
    lr_uc_internal: float | None

    @property
    def ok(self) -> bool:
        """`True` quando o R devolveu as estatísticas (nenhum erro)."""
        return self.error is None


@dataclass(frozen=True)
class VarTestCase:
    """Um caso da fixture: sequência de violações, taxa nominal e os dois *feeds*."""

    id: str
    description: str
    category: str
    violation_rate: float
    violations: tuple[bool, ...]
    whole: OracleFeed
    from_t2: OracleFeed


@dataclass(frozen=True)
class VarTestFixture:
    """A unidade inteira: `provenance` (como gravado) e os casos na ordem do gerador."""

    provenance: dict[str, Any]
    cases: tuple[VarTestCase, ...]


def _feed(raw: dict[str, Any]) -> OracleFeed:
    return OracleFeed(
        uc_lrstat=raw.get("uc_lrstat"),
        cc_lrstat=raw.get("cc_lrstat"),
        error=raw.get("error"),
        lr_uc_internal=raw.get("lr_uc_internal"),
    )


def parse_violations(raw: list[Any]) -> tuple[bool, ...]:
    """Violações 0/1 **inteiras** do JSON como `bool`; booleano JSON ou outro valor ergue.

    `true`/`false` do JSON viram `bool` do Python, que é subclasse de `int` e passaria
    num `value == 1`: o formato do Step exige inteiros (ADR 6.2.0006 item 1).
    """
    for index, value in enumerate(raw):
        if type(value) is not int or value not in (0, 1):
            raise ValueError(f"violations[{index}] must be a JSON integer 0 or 1, got {value!r}")
    return tuple(value == 1 for value in raw)


@cache
def load_var_test_cases() -> VarTestFixture:
    """Lê e tipa a fixture (uma leitura por processo)."""
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = tuple(
        VarTestCase(
            id=raw["id"],
            description=raw["description"],
            category=raw["category"],
            violation_rate=float.fromhex(raw["violation_rate"]["hex"]),
            violations=parse_violations(raw["violations"]),
            whole=_feed(raw["whole"]),
            from_t2=_feed(raw["from_t2"]),
        )
        for raw in data["cases"]
    )
    return VarTestFixture(provenance=data["provenance"], cases=cases)
