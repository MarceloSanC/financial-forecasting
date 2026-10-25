"""Regras de leitura do LaTeX usadas na conferência dos números do TCC."""

from __future__ import annotations

import pytest

from tests.tcc.latex_numbers import (
    consistent,
    normalize,
    parse_interval,
    parse_number,
    table_rows,
)

pytestmark = pytest.mark.unit

_TABLE = r"""
\caption{x}
\label{tab:x}
\begin{tabular}{l c c}
\toprule
Modelo & \(h+1\) & \(h+7\) \\
\midrule
EWMA-vol & \textbf{3,920} & \(-286{,}4\) \\
TFT & 4,050 [3,987; 4,117] & ilimitado\textsuperscript{a} \\
\bottomrule
\multicolumn{3}{l}{nota} \\
\end{tabular}
"""


def test_normalize_strips_math_bold_and_decimal_braces() -> None:
    assert normalize(r" \textbf{\(0{,}332\)} ") == "0,332"


def test_table_rows_reads_data_rows_and_stops_at_bottomrule() -> None:
    rows = table_rows(_TABLE, "tab:x")
    assert rows == [
        ["Modelo", "h+1", "h+7"],
        ["EWMA-vol", "3,920", "-286,4"],
        ["TFT", "4,050 [3,987; 4,117]", "ilimitado"],
    ]


def test_table_rows_unknown_label_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        table_rows(_TABLE, "tab:y")


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("1.511", (1511.0, 0)),
        ("-286,4", (-286.4, 1)),
        ("+13,1", (13.1, 1)),
        ("0,0887", (0.0887, 4)),
    ],
)
def test_parse_number_brazilian_notation(cell: str, expected: tuple[float, int]) -> None:
    assert parse_number(cell) == expected


def test_parse_number_rejects_text() -> None:
    with pytest.raises(ValueError, match="not a number"):
        parse_number("ilimitado")


def test_parse_interval() -> None:
    assert parse_interval(r"[\(-0{,}355\); \(0{,}758\)]") == ((-0.355, 3), (0.758, 3))


@pytest.mark.parametrize(
    ("shown", "decimals", "value", "ok"),
    [(0.022, 3, 0.0224, True), (0.022, 3, 0.0226, False), (4.050, 3, 4.0504, True)],
)
def test_consistent_is_half_unit_of_displayed_precision(
    shown: float, decimals: int, value: float, ok: bool
) -> None:
    assert consistent(shown, decimals, value) is ok
