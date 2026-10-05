"""Dono único do fingerprint de uma grade de treino (issue #128; emenda ao ADR 6.4.0009).

A regra de hash mora no VO `DatasetContentFingerprint`; a ESCOLHA das entradas (ativo,
timestamps, colunas) mora só em `grid_fingerprint`, na `modeling`. Os testes de contrato
comparam valores — uma cópia idêntica da fórmula em outro módulo passaria por eles (achado
F2 da auditoria do PR #145). Este teste prova a ORIGEM: em `src/` há exatamente um ponto de
chamada de `DatasetContentFingerprint.compute`, dentro de `grid_fingerprint`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[2] / "src" / "financial_forecasting"
_OWNER = ("features/modeling/application/use_cases/train_gbm_quantile.py", "grid_fingerprint")


def _call_sites(source: str) -> list[str]:
    """Funções (nome da mais interna) que chamam `DatasetContentFingerprint.compute`."""
    sites: list[str] = []

    def visit(node: ast.AST, enclosing: str) -> None:
        for child in ast.iter_child_nodes(node):
            scope = enclosing
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                scope = child.name
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "compute"
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == "DatasetContentFingerprint"
            ):
                sites.append(enclosing)
            visit(child, scope)

    visit(ast.parse(source), "<module>")
    return sites


def test_detector_finds_a_call_and_its_function() -> None:
    """Sanidade do detector: sem ela, o teste do repo real poderia passar por vacuidade."""
    source = (
        "def outra():\n"
        "    return DatasetContentFingerprint.compute(hasher=h, asset_id=a)\n"
        "def nada():\n"
        "    return Outra.compute()\n"
    )
    assert _call_sites(source) == ["outra"]


def test_fingerprint_inputs_have_a_single_owner() -> None:
    found = [
        (path.relative_to(_SRC).as_posix(), site)
        for path in sorted(_SRC.rglob("*.py"))
        for site in _call_sites(path.read_text(encoding="utf-8"))
    ]
    assert found == [_OWNER], (
        "DatasetContentFingerprint.compute deve ter um único ponto de chamada em src/, dentro "
        f"de grid_fingerprint (issue #128); achados: {found}. Chame grid_fingerprint em vez de "
        "recompor a fórmula."
    )
