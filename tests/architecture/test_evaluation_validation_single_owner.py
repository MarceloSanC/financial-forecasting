"""Dono único das regras de inteiro, número e timestamps do slice `evaluation` (#118, #167).

Os testes de mensagem comparam o erro, não a origem: uma cópia da regra com a mesma
mensagem passaria por eles. Este teste prova a ORIGEM, pela AST (um nome em docstring
ou comentário não conta):

- "int não-`bool`" — as duas escritas antigas (`isinstance(x, bool)` ao lado de
  `isinstance(x, int)` na mesma expressão, e `type(x) is [not] int`) só aparecem em
  `domain/value_objects/_integer.py`;
- "número não-`bool`" (#167) — `isinstance(x, bool)` ao lado de
  `isinstance(x, int | float)` (ou `(int, float)`) na mesma expressão só aparece em
  `domain/value_objects/_finite_number.py`;
- "timestamps estritamente crescentes" — a mensagem da regra só é montada em
  `domain/value_objects/_timestamps.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[2] / "src" / "financial_forecasting"
_SLICE = _SRC / "features" / "evaluation"
_INT_OWNER = "domain/value_objects/_integer.py"
_NUMBER_OWNER = "domain/value_objects/_finite_number.py"
_TIMESTAMPS_OWNER = "domain/value_objects/_timestamps.py"
_TIMESTAMPS_MESSAGE = "must be strictly increasing (unique and ordered)"


def _isinstance_of(node: ast.AST, type_name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isinstance"
        and len(node.args) == 2  # noqa: PLR2004
        and isinstance(node.args[1], ast.Name)
        and node.args[1].id == type_name
    )


def _is_int_float_union(node: ast.AST) -> bool:
    """`int | float`, `float | int`, `(int, float)` ou `(float, int)`."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        parts: list[ast.expr] = [node.left, node.right]
    elif isinstance(node, ast.Tuple):
        parts = list(node.elts)
    else:
        return False
    return sorted(p.id for p in parts if isinstance(p, ast.Name)) == ["float", "int"]


def _isinstance_of_number(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isinstance"
        and len(node.args) == 2  # noqa: PLR2004
        and _is_int_float_union(node.args[1])
    )


def _number_rule_lines(source: str) -> list[int]:
    """Linhas com uma escrita da regra "número não-`bool`"."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BoolOp):
            calls = [
                part.operand if isinstance(part, ast.UnaryOp) else part for part in node.values
            ]
            if any(_isinstance_of(c, "bool") for c in calls) and any(
                _isinstance_of_number(c) for c in calls
            ):
                lines.append(node.lineno)
    return lines


def _int_rule_lines(source: str) -> list[int]:
    """Linhas com uma escrita da regra "int não-`bool`"."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BoolOp):
            calls = [
                part.operand if isinstance(part, ast.UnaryOp) else part for part in node.values
            ]
            if any(_isinstance_of(c, "bool") for c in calls) and any(
                _isinstance_of(c, "int") for c in calls
            ):
                lines.append(node.lineno)
        elif (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Call)
            and isinstance(node.left.func, ast.Name)
            and node.left.func.id == "type"
            and any(isinstance(op, ast.Is | ast.IsNot) for op in node.ops)
            and any(isinstance(c, ast.Name) and c.id == "int" for c in node.comparators)
        ):
            lines.append(node.lineno)
    return lines


def _timestamps_rule_lines(source: str) -> list[int]:
    """Linhas que montam a mensagem da regra de timestamps."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _TIMESTAMPS_MESSAGE in node.value
    ]


def _files_with(detector: object) -> list[str]:
    assert callable(detector)
    return [
        path.relative_to(_SLICE).as_posix()
        for path in sorted(_SLICE.rglob("*.py"))
        if detector(path.read_text(encoding="utf-8"))
    ]


def test_int_detector_flags_both_old_forms() -> None:
    """Sanidade: sem ela, o teste do repo real poderia passar por vacuidade."""
    source = (
        "a = isinstance(x, bool) or not isinstance(x, int) or x < 0\n"
        "b = type(y) is not int\n"
        "c = isinstance(z, int) and not isinstance(z, bool)\n"
        "d = isinstance(w, bool) or not isinstance(w, int | float)\n"
        "e = not isinstance(v, bool)\n"
    )
    assert _int_rule_lines(source) == [1, 2, 3]


def test_number_detector_flags_every_spelling() -> None:
    """Sanidade: as grafias da regra de número contam; a de inteiro e `bool` sozinho não."""
    source = (
        "a = isinstance(x, bool) or not isinstance(x, int | float)\n"
        "b = isinstance(y, float | int) and not isinstance(y, bool)\n"
        "c = not isinstance(z, bool) and isinstance(z, (int, float))\n"
        "d = isinstance(w, bool) or not isinstance(w, int)\n"
        "e = isinstance(v, int | float)\n"
        "f = isinstance(u, bool) or not isinstance(u, int | str)\n"
    )
    assert _number_rule_lines(source) == [1, 2, 3]


def test_timestamps_detector_flags_the_message() -> None:
    source = 'raise ValueError("t must be strictly increasing (unique and ordered): p")\n'
    assert _timestamps_rule_lines(source) == [1]


def test_int_rule_has_a_single_owner() -> None:
    found = _files_with(_int_rule_lines)
    assert found == [_INT_OWNER], (
        f"'int não-bool' deve ser escrito só em {_INT_OWNER} (issue #118); achados: {found}. "
        "Use is_int / validate_int_at_least."
    )


def test_number_rule_has_a_single_owner() -> None:
    found = _files_with(_number_rule_lines)
    assert found == [_NUMBER_OWNER], (
        f"'número não-bool' deve ser escrito só em {_NUMBER_OWNER} (issue #167); "
        f"achados: {found}. Use is_real_number / is_finite_number."
    )


def test_timestamps_rule_has_a_single_owner() -> None:
    found = _files_with(_timestamps_rule_lines)
    assert found == [_TIMESTAMPS_OWNER], (
        f"'timestamps estritamente crescentes' deve ser escrito só em {_TIMESTAMPS_OWNER} "
        f"(issue #118); achados: {found}. Use check_strictly_increasing."
    )
