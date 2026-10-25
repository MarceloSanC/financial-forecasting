"""Estilo de apresentação das figuras da 8.3 para o texto do TCC (issue #250).

As mesmas `FigureSpec` do dossiê, desenhadas para uma banca: nomes de modelos, famílias e
métodos em português, eixos por extenso, sem estatuto na legenda nem no título do painel,
sem título da figura (a legenda do LaTeX faz esse papel) e sem rodapé; fontes de 7 a 8,5 pt
na largura do texto (6,3 pol.), legíveis com a figura em meia página A4; vírgula decimal
nos eixos numéricos. Só o texto exibido e as medidas mudam — o dado desenhado, as cores e
os marcadores são os do dossiê.

`PRESENTATION_OMISSIONS` lista as figuras do catálogo que o texto não usa, com o motivo; o
sink de apresentação grava o motivo ao lado das figuras.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.adapters.out.plots.matplotlib_figure_renderer import (  # noqa: E501
    RenderStyle,
)

MODEL_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "tft_quantile": "TFT",
        "baseline_zero_return": "Retorno nulo",
        "baseline_historical_mean": "Média histórica",
        "baseline_ar1": "AR(1)",
        "baseline_ewma_vol": "EWMA-vol",
        "baseline_historical_quantiles": "Quantis empíricos",
        "gbm_quantile": "GBM quantílico",
    }
)
"""Identificador do modelo → nome de exibição."""

FAMILY_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "price": "Preço",
        "technical": "Técnico",
        "sentiment": "Sentimento",
        "fundamental": "Fundamento",
    }
)
"""Família de covariáveis → nome de exibição."""

METHOD_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "permutation": "permutação",
        "loco": "ablação",
        "nexcp_fixed_geometric_weights_v1": "NexCP",
        "split_cqr_asymmetric_unweighted_v1": "CQR",
    }
)
"""Método de importância (H3) e variante conformal → nome de exibição."""

AXIS_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "τ": "nível τ",
        "ĉ(τ)": "cobertura observada ĉ(τ)",
        "P̄_τ (pinball)": "perda pinball média",
        "MPIW": "largura média (MPIW)",
        "PICP": "cobertura observada (PICP)",
        "par (τ_l-τ_u)": r"par de níveis ($\tau_l$-$\tau_u$)",
        "largura u - l": "largura do intervalo",
        "target_timestamp": "data-alvo",
        "d_t": r"diferencial de perda $d_t$",
        "lag": "defasagem",
        "ACF": "autocorrelação",
        "I_f(h)": r"importância $I_f(h)$",
        "Δ_f / s_f(h)": r"$\Delta_f\,/\,s_f(h)$",
        "peso": "peso na VSN",
        "cauda / par": "nível ou par",
        "ĉ(τ) / PICP": "cobertura observada",
    }
)
"""Texto exibido inteiro (eixos) → texto por extenso; casa só o texto inteiro."""

_NOTATION: Final[tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], str]], ...]] = (
    (re.compile(r"(?<!\w)d_t(?!\w)"), lambda _: "$d_t$"),
    (re.compile(r"I_f\(h\)"), lambda _: "$I_f(h)$"),
    (re.compile(r"s_f\(h(\+\d+)?\)"), lambda m: f"$s_f(h{m.group(1) or ''})$"),
    (re.compile(r"Δ_f"), lambda _: r"$\Delta_f$"),
)
"""Notação com índice (`d_t`, `I_f(h)`, `s_f(h+7)`, `Δ_f`) em mathtext, sem `_` literal."""

_PHRASES: Final[tuple[tuple[str, str], ...]] = (
    (r" \(sem seed\)", ""),
    (r" \(c\S*/n\S*\)", ""),
    (r"\(larguras de (\d+) seeds empilhadas: [^)]*\)", r"(larguras das \1 sementes empilhadas)"),
    (r"nativo \(mesma máscara\)", "nativo"),
    (r"nominal 1 - 2τ_l", "cobertura nominal"),
    (r"realizado y_t", "retorno realizado"),
    (r"perfil por permutação", "dispersão entre repetições"),
    (r"perfil por seed", "dispersão entre sementes"),
    (r"\(p50; p10 a p90\)", "(mediana; p10 a p90)"),
    (r"\bcandidato\b", "TFT"),
    (r"— d t$", "— diferencial de perda"),
    (r"— acf$", "— autocorrelação"),
    (r"\bseeds\b", "sementes"),
    (r"\bseed\b", "semente"),
)
"""Trechos reescritos, na ordem (antes dos identificadores)."""

_IDENTIFIERS: Final[Mapping[str, str]] = MappingProxyType(
    {**MODEL_NAMES, **FAMILY_NAMES, **METHOD_NAMES}
)
_IDENTIFIER: Final = re.compile(
    r"(?<!\w)("
    + "|".join(re.escape(k) for k in sorted(_IDENTIFIERS, key=len, reverse=True))
    + r")(?!\w)"
)
_COMPILED: Final = tuple((re.compile(pattern), repl) for pattern, repl in _PHRASES)


def presentation_text(text: str) -> str:
    """O texto exibido no estilo de apresentação.

    Texto inteiro de eixo → `AXIS_LABELS`; senão, os trechos de `_PHRASES` na ordem, a
    notação com índice em mathtext (`_NOTATION`) e cada identificador (modelo, família,
    método) pelo nome de exibição, só como palavra inteira.
    """
    if text in AXIS_LABELS:
        return AXIS_LABELS[text]
    for pattern, repl in _COMPILED:
        text = pattern.sub(repl, text)
    for notation, write in _NOTATION:
        text = notation.sub(write, text)
    return _IDENTIFIER.sub(lambda match: _IDENTIFIERS[match.group(1)], text)


_PRESENTATION_RC: Final[Mapping[str, object]] = MappingProxyType(
    {
        "pdf.fonttype": 42,
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.titlesize": 8.5,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "axes.grid": True,
        "grid.color": "#dddddd",
        "grid.linewidth": 0.4,
        "axes.edgecolor": "#888888",
        "axes.linewidth": 0.5,
        "lines.linewidth": 1.0,
        "lines.markersize": 3.5,
        "figure.dpi": 72,
    }
)

PRESENTATION_STYLE: Final = RenderStyle(
    name="presentation",
    rc=_PRESENTATION_RC,
    annotations=False,
    text=presentation_text,
    panel_height_in=2.15,
    title_in=0.1,
    legend_wrap=50,
    legend_line_in=0.1,
    legend_entry_in=0.045,
    decimal_comma=True,
)
"""O estilo de apresentação (ver o docstring do módulo)."""

PRESENTATION_OMISSIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "dm_candidate_vs_comparators": (
            "a 'matriz' do DM tem uma linha só (o TFT contra cada comparador) e as células "
            "repetem o p bruto e a decisão de Holm, que o capítulo de resultados dá em tabela"
        ),
    }
)
"""Figura do catálogo → por que o texto do TCC não a usa."""
