"""Recorte do PICP x MPIW para o slide (reserva R5), com o GBM em vermelho.

Na figura do texto (../figuras/picp_mpiw_plot.pdf, que não muda) o GBM (#6250d6,
roxo) fica parecido demais com o TFT (#2a78d6, azul) no projetor. Aqui só a cor do
GBM troca para vermelho (#d62728); dados, marcadores e demais cores ficam iguais. A
chave de cores do slide usa a mesma cor.

Rodar a partir de text/apresentacao/, depois de recortes.sh (que regrava o PNG):
    uv run --no-project --with pymupdf python recolore_picp_mpiw.py
"""

import re

import pymupdf

SOURCE = "../figuras/picp_mpiw_plot.pdf"
TARGET = "../figuras/slides/picp_mpiw_plot.png"
CLIP = pymupdf.Rect(0, 0, 227.6, 166.96)  # o mesmo recorte de recortes.sh (painel h+1)
GBM = re.compile(rb"0\.3843137255\s+0\.3137254902\s+0\.8392156863\s+(rg|RG)")  # #6250d6
RED = "d62728"
EXPECTED = 9  # preenchimentos e contornos do GBM nos dois painéis e na legenda


def main() -> None:
    rgb = " ".join(f"{int(RED[i : i + 2], 16) / 255:.4f}" for i in (0, 2, 4)).encode()
    doc = pymupdf.open(SOURCE)
    page = doc[0]
    total = 0
    for xref in page.get_contents():
        stream, count = GBM.subn(lambda m: rgb + b" " + m.group(1), doc.xref_stream(xref))
        total += count
        doc.update_stream(xref, stream)
    if total != EXPECTED:
        raise SystemExit(f"esperava {EXPECTED} cores do GBM, achei {total}: a figura mudou?")
    page.get_pixmap(dpi=300, clip=CLIP).save(TARGET)


if __name__ == "__main__":
    main()
