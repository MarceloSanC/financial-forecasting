"""Leitura de números e tabelas do LaTeX do TCC, para conferir contra a geração julgada.

Regras puras sobre texto:

- `table_rows(tex, label)`: as linhas da tabela cujo `\\label{label}` aparece antes do
  `tabular`, com as células normalizadas (sem `\\textbf`, delimitadores de math e o
  separador decimal `{,}`);
- `parse_number(cell)`: o número de uma célula em notação brasileira (`1.511`, `-286,4`),
  junto com as casas decimais exibidas;
- `consistent(shown, decimals, value)`: verdadeiro se `value` arredondado às casas exibidas
  dá o número exibido, ou seja, se o texto é um arredondamento honesto do valor gravado.
"""

from __future__ import annotations

import re
from typing import Final

_MINUS_SIGN: Final = chr(0x2212)
_MATH: Final = re.compile(r"\\\(|\\\)|\$")
_WRAPPERS: Final = re.compile(r"\\(?:textbf|textit|mathbf)\{([^{}]*)\}")
_SUPERSCRIPT: Final = re.compile(r"\\textsuperscript\{[^{}]*\}")
_NUMBER: Final = re.compile(r"^[+\-]?\d{1,3}(?:\.\d{3})*(?:,\d+)?$|^[+\-]?\d+(?:,\d+)?$")


def normalize(cell: str) -> str:
    """Tira math, negrito e sobrescrito; troca `{,}` por `,` e colapsa espaços."""
    text = _SUPERSCRIPT.sub("", cell)
    text = _MATH.sub("", text).replace("{,}", ",").replace("~", " ")
    previous = None
    while previous != text:
        previous = text
        text = _WRAPPERS.sub(r"\1", text)
    return " ".join(text.split())


def table_rows(tex: str, label: str) -> list[list[str]]:
    """Linhas de dados (entre `\\midrule`/`\\toprule` e `\\bottomrule`) da tabela `label`.

    Raises:
        ValueError: o rótulo não existe ou não há `tabular` depois dele.
    """
    start = tex.find(f"\\label{{{label}}}")
    if start < 0:
        raise ValueError(f"label {label!r} not found")
    begin = tex.find("\\begin{tabular}", start)
    end = tex.find("\\end{tabular}", begin)
    if begin < 0 or end < 0:
        raise ValueError(f"no tabular after label {label!r}")
    body = tex[begin:end]
    bottom = body.find("\\bottomrule")
    body = body[: bottom if bottom >= 0 else len(body)]
    rows: list[list[str]] = []
    for raw in body.split("\\\\"):
        line = re.sub(r"\\(?:toprule|midrule|cmidrule\S*)", "", raw)
        line = re.sub(r"\\begin\{tabular\}\{[^}]*\}", "", line)
        if "&" not in line:
            continue
        rows.append([normalize(cell) for cell in line.split("&")])
    return rows


def parse_number(cell: str) -> tuple[float, int]:
    """Número em notação brasileira e as casas decimais exibidas.

    Raises:
        ValueError: a célula não é um número.
    """
    text = normalize(cell).replace(_MINUS_SIGN, "-").replace(" ", "")
    if not _NUMBER.match(text):
        raise ValueError(f"not a number: {cell!r}")
    decimals = len(text.split(",")[1]) if "," in text else 0
    return float(text.replace(".", "").replace(",", ".")), decimals


def parse_interval(cell: str) -> tuple[tuple[float, int], tuple[float, int]]:
    """Intervalo `[a; b]` em notação brasileira.

    Raises:
        ValueError: a célula não tem a forma `[a; b]`.
    """
    text = normalize(cell)
    match = re.fullmatch(r"\[\s*([^;]+);\s*([^\]]+)\]", text)
    if not match:
        raise ValueError(f"not an interval: {cell!r}")
    return parse_number(match.group(1)), parse_number(match.group(2))


def consistent(shown: float, decimals: int, value: float) -> bool:
    """`value` arredondado a `decimals` casas reproduz `shown` (meia unidade de folga)."""
    return abs(shown - value) <= 0.5 * 10.0 ** (-decimals) + 1e-12
