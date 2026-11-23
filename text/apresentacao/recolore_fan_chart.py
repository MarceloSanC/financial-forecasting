"""Recorte do fan chart para o slide, com as faixas em matizes distintos.

Na figura do texto (../figuras/oos_fan_chart.pdf, que não muda) as três faixas são o
mesmo azul com transparências diferentes; no projetor ficavam difíceis de separar.
Aqui cada faixa vira uma cor opaca. Como as faixas são desenhadas de fora para dentro
(96%, 80%, 50%), cada uma cobre exatamente a de fora: nenhum dado ou traço muda, só a
cor de preenchimento. A chave de cores do slide usa as mesmas cores.

Rodar a partir de text/apresentacao/, depois de recortes.sh (que regrava o PNG):
    uv run --no-project --with pymupdf python recolore_fan_chart.py
"""

import re

import pymupdf

SOURCE = "../figuras/oos_fan_chart.pdf"
TARGET = "../figuras/slides/oos_fan_chart.png"
CLIP = pymupdf.Rect(0, 0, 453.6, 162.4)  # o mesmo recorte de recortes.sh (sem a legenda)
BLUE = rb"0\.1647058824\s+0\.4705882353\s+0\.8392156863\s+rg"  # #2a78d6, cor do TFT
# Estado gráfico da faixa (/A2: 96%, /A3: 80%, /A4: 50%) -> cor opaca.
BANDS = {b"2": "f6e49a", b"3": "8ccaee", b"4": "ef9a48"}
EXPECTED = 6  # três faixas em cada um dos dois painéis


def _rg(hex_color: str) -> bytes:
    return " ".join(f"{int(hex_color[i : i + 2], 16) / 255:.4f}" for i in (0, 2, 4)).encode() + b" rg"


def main() -> None:
    doc = pymupdf.open(SOURCE)
    page = doc[0]
    pattern = re.compile(rb"/A([234]) gs\s+" + BLUE + rb"\s+1 j 0 G\s+" + BLUE)
    total = 0
    for xref in page.get_contents():
        stream = doc.xref_stream(xref)
        stream, count = pattern.subn(
            lambda m: b"/A5 gs\n" + _rg(BANDS[m.group(1)]) + b" 1 j 0 G " + _rg(BANDS[m.group(1)]),
            stream,
        )
        total += count
        doc.update_stream(xref, stream)
    if total != EXPECTED:
        raise SystemExit(f"esperava {EXPECTED} faixas, achei {total}: a figura mudou?")
    page.get_pixmap(dpi=300, clip=CLIP).save(TARGET)


if __name__ == "__main__":
    main()
