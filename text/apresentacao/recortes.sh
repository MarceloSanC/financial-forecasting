#!/bin/sh
# Recortes das figuras usadas nos slides, rasterizados (issue #272).
#
# Os slides recortavam as figuras do texto com trim + clip, o que deixa o conteúdo
# cortado dentro do PDF: visualizadores que ignoram o recorte mostravam pedaços da
# legenda escondida. Aqui cada recorte vira um PNG de 300 dpi, sem conteúdo oculto.
#
# Rodar a partir de text/apresentacao/, numa imagem com Ghostscript, por exemplo:
#   docker run --rm -v "$PWD/..:/w" -w /w/apresentacao texlive/texlive:latest sh recortes.sh
#
# Cada linha: figura, largura e altura do recorte (pt) e o canto inferior esquerdo
# (x, y) do recorte na página original, em pt. No PageOffset do Ghostscript, y
# positivo desce o conteúdo, e x negativo o leva para a esquerda.
set -eu
mkdir -p ../figuras/slides
while read -r name width height x y; do
  gs -q -dNOPAUSE -dBATCH -dSAFER -sDEVICE=png16m -r300 \
    -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dFIXEDMEDIA \
    -dDEVICEWIDTHPOINTS="$width" -dDEVICEHEIGHTPOINTS="$height" \
    -sOutputFile="../figuras/slides/$name.png" \
    -c "<</PageOffset [-$x $y]>> setpagedevice" -f "../figuras/$name.pdf"
done <<'EOF'
oos_fan_chart 453.6 162.4 0 50
reliability_diagram 227.6 165.44 0 70
picp_mpiw_plot 227.6 166.96 0 80
quantile_score_plot 227.6 167.52 0 114
EOF
