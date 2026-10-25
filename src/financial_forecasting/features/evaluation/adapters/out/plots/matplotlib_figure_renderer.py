"""`MatplotlibFigureRenderer` — satisfaz o port `FigureRenderer` com PDF determinístico (Stage 8.3).

ADR `8_3_0003`: `matplotlib.figure.Figure` + `FigureCanvasPdf`, **sem `pyplot`** e sem
estado global; `rc_context` com `pdf.fonttype = 42` (TrueType embutida) e `DejaVu Sans`
(embarcada no matplotlib — nenhuma fonte do sistema); `savefig(format="pdf",
metadata={"CreationDate": None})`; o layout restrito roda uma vez e fica fixado numa grade
(`freeze_layout`: o solver tem ruído de último bit entre chamadas). A mesma `FigureSpec`, no
mesmo ambiente, dá os mesmos bytes em qualquer chamada e processo.

O adapter **só desenha o que a spec traz** — um eixo por painel, uma marca por
`SeriesKind` —, nunca recalcula (as caixas usam `Axes.bxp` com as estatísticas da spec).
Identidade nunca só por cor: mapa **fixo** modelo → (cor, marcador, estilo de linha), cores
da ordem categórica da skill `dataviz` (`references/palette.md`, validadas pelo
`validate_palette.js --mode light`, technical §7); modelo fora do mapa → `ValueError`
(nenhuma cor gerada). Séries distintas nunca coincidem no atributo efetivamente desenhado
do seu tipo (`figure_looks`): faixas aninhadas por alpha/hachura, linhas por estilo, marcas
por marcador; a linha sem modelo (o observado) é fina e fica abaixo das linhas de modelo.
Escalas sequenciais e o heatmap do DM em `cividis`. Rótulos em PT; o
estatuto de cada painel no título e de cada série na legenda; notas e omissões no rodapé.

Estilo (issue #250): o renderizador recebe um `RenderStyle`. O padrão, `DOSSIER_STYLE`, é o
do dossiê (o desenho acima, byte a byte o da Stage 8.3); o de apresentação
(`presentation_style.PRESENTATION_STYLE`) troca só o texto exibido (nomes em português, sem
estatuto, sem título nem rodapé) e as medidas de fonte — o dado desenhado é o mesmo.

O processo precisa de `MPLCONFIGDIR` gravável (o container usa `/tmp`); o adapter não lê
variável de ambiente.
"""

from __future__ import annotations

import io
import math
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import matplotlib
from matplotlib import ft2font, rc_context
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.backends.backend_pdf import FigureCanvasPdf
from matplotlib.figure import Figure, SubFigure
from matplotlib.text import Text
from matplotlib.transforms import Bbox

from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FigureSpec,
    PanelSpec,
    SeriesKind,
    SeriesSpec,
)

Style = tuple[str, str, str]

MODEL_STYLES: Final[Mapping[str, Style]] = {
    "tft_quantile": ("#2a78d6", "o", "-"),
    "baseline_zero_return": ("#eb6834", "s", "--"),
    "baseline_historical_mean": ("#1baf7a", "^", "-."),
    "baseline_ar1": ("#eda100", "D", ":"),
    "baseline_ewma_vol": ("#e87ba4", "v", "--"),
    "baseline_historical_quantiles": ("#008300", "P", "-."),
    "gbm_quantile": ("#6250d6", "X", ":"),
}
"""Modelo → (cor, marcador, estilo): as sete primeiras cores da ordem categórica fixa."""

_NEUTRAL: Final = "#4d4d4d"
_NEUTRALS: Final = (_NEUTRAL, "#8c8c8c")
"""Tons das séries sem modelo, alternados por tipo de série (escuro, médio; ambos ≥ 3:1)."""
_MARKERS: Final = ("o", "s", "^", "D", "v", "P", "X", "<", ">", "p", "h", "*", "d", "H", "8")
"""Marcadores na ordem de troca quando duas séries distintas cairiam no mesmo estilo."""
_REFERENCE_LINESTYLES: Final[tuple[object, ...]] = (
    "--",
    ":",
    "-.",
    (0, (5, 1)),
    (0, (1, 3)),
    (0, (3, 1, 1, 1)),
)
_LINESTYLES: Final[tuple[object, ...]] = ("-", *_REFERENCE_LINESTYLES)
"""Estilos de linha na ordem de troca quando duas linhas cairiam na mesma (cor, estilo)."""
_BAND_FILLS: Final[tuple[tuple[float, str | None], ...]] = (
    (0.12, None),
    (0.24, None),
    (0.36, None),
    (0.12, "////"),
    (0.12, "xxxx"),
    (0.12, "...."),
)
"""(alpha, hachura) das faixas na ordem da spec: faixas aninhadas ficam distinguíveis."""
_OBSERVED_WIDTH: Final = 0.4
"""Linha sem modelo (o observado, ex. y_t): fina e abaixo das linhas de modelo."""
_Z_BAND: Final = 1.0
_Z_OBSERVED: Final = 2.0
_Z_MODEL_LINE: Final = 3.0
_DODGE: Final = 0.3
"""Largura total do deslocamento lateral dos intervalos de um painel categórico."""
_LAYOUT_GRID: Final = 1e-6
"""Grade (fração da figura, ~0,0005 pt) das posições fixadas depois do layout restrito."""
_SEQUENTIAL: Final = "cividis"
_WIDTH_IN: Final = 6.3
_PANEL_HEIGHT_IN: Final = 2.6
_TITLE_IN: Final = 0.45
_FOOTER_LINE_IN: Final = 0.085
_MAX_COLUMNS: Final = 2
_MAX_TICKS: Final = 6
_WRAP: Final = 160
_LEGEND_WRAP: Final = 62
"""Caracteres por linha de um rótulo de legenda (cabe numa das duas colunas da página)."""
_LEGEND_LINE_IN: Final = 0.085
_LEGEND_ENTRY_IN: Final = 0.035
_LEGEND_COLUMNS: Final = 2
_PAD_IN: Final = 0.12
_ISO_MIN: Final = 19
_DARK_CELL: Final = 0.5
_RC: Final[Mapping[str, object]] = {
    "pdf.fonttype": 42,
    "font.family": "DejaVu Sans",
    "font.size": 6,
    "axes.titlesize": 6.5,
    "axes.labelsize": 6,
    "xtick.labelsize": 5,
    "ytick.labelsize": 5,
    "legend.fontsize": 4.5,
    "axes.grid": True,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.4,
    "axes.edgecolor": "#888888",
    "axes.linewidth": 0.5,
    "lines.linewidth": 1.0,
    "lines.markersize": 3.0,
    "figure.dpi": 72,
}


def _verbatim(text: str) -> str:
    return text


@dataclass(frozen=True, kw_only=True)
class RenderStyle:
    """O que muda entre o dossiê e a apresentação: texto exibido e medidas — nunca o dado.

    `annotations` liga o estatuto (título do painel e legenda), o título da figura e o
    rodapé; `text` traduz todo texto exibido vindo da spec (título de painel, eixos,
    categorias, nomes de série, células); `name` entra na identidade do renderizador
    (`None` no dossiê: o registro da 8.3 não muda).
    """

    name: str | None
    rc: Mapping[str, object]
    annotations: bool
    text: Callable[[str], str]
    panel_height_in: float
    title_in: float
    legend_wrap: int
    legend_line_in: float
    legend_entry_in: float


DOSSIER_STYLE: Final = RenderStyle(
    name=None,
    rc=_RC,
    annotations=True,
    text=_verbatim,
    panel_height_in=_PANEL_HEIGHT_IN,
    title_in=_TITLE_IN,
    legend_wrap=_LEGEND_WRAP,
    legend_line_in=_LEGEND_LINE_IN,
    legend_entry_in=_LEGEND_ENTRY_IN,
)
"""O estilo do dossiê (Stage 8.3): estatuto, título e rodapé, texto como na spec."""


def _label(series: SeriesSpec, style: RenderStyle = DOSSIER_STYLE) -> str:
    """O rótulo da série na legenda (nome e, no dossiê, estatuto), quebrado para a coluna."""
    name = style.text(series.name)
    text = f"{name} [{series.label.status.value}]" if style.annotations else name
    return "\n".join(textwrap.wrap(text, style.legend_wrap))


class Look:
    """O estilo resolvido de uma série: cor, marcador, linha, vazado e preenchimento."""

    def __init__(  # noqa: PLR0913 — os atributos desenhados de uma série
        self,
        color: str,
        marker: str,
        linestyle: object,
        *,
        hollow: bool,
        alpha: float = 0.2,
        hatch: str | None = None,
    ) -> None:
        self.color = color
        self.marker = marker
        self.linestyle = linestyle
        self.hollow = hollow
        self.alpha = alpha
        self.hatch = hatch

    @property
    def face(self) -> str:
        return "none" if self.hollow else self.color


def _base_style(series: SeriesSpec, neutrals: dict[SeriesKind, int]) -> Style:
    """(cor, marcador, linha) de partida: o mapa fixo do modelo, ou um tom neutro.

    Séries sem modelo alternam os tons de `_NEUTRALS` na ordem em que aparecem dentro do
    mesmo tipo (Δ_f da permutação e do LOCO do H3 deixam de ser o mesmo cinza).
    """
    if series.model is not None:
        if series.model not in MODEL_STYLES:
            raise ValueError(f"models without a fixed style: {[series.model]}")
        return MODEL_STYLES[series.model]
    index = neutrals.get(series.kind, 0)
    neutrals[series.kind] = index + 1
    linestyle = "-" if series.kind is SeriesKind.LINE else "--"
    return _NEUTRALS[index % len(_NEUTRALS)], _MARKERS[0], linestyle


def figure_looks(spec: FigureSpec, style: RenderStyle = DOSSIER_STYLE) -> dict[str, Look]:
    """Rótulo da legenda → estilo, para a figura inteira (o mesmo rótulo, o mesmo estilo).

    A cor de um modelo é a do mapa fixo (identidade do modelo); série sem modelo usa um tom
    neutro. Duas séries **distintas** nunca ficam com o mesmo atributo **desenhado** do seu
    tipo: faixa → (cor, alpha, hachura), trocando na ordem de `_BAND_FILLS` (faixas
    aninhadas do mesmo modelo); linha → (cor, estilo), trocando o estilo; referência →
    estilo de linha; marca com marcador → (cor, marcador, vazado), trocando de marcador
    (ordem de `_MARKERS`) e, esgotados, passando a vazado — os tons neutros contam como uma
    cor só, então duas séries sem modelo nunca se distinguem só pelo tom.

    Raises:
        ValueError: série de um modelo fora de `MODEL_STYLES`.
    """
    looks: dict[str, Look] = {}
    used: set[tuple[object, ...]] = set()
    used_lines: list[object] = []
    neutrals: dict[SeriesKind, int] = {}
    for panel in spec.panels:
        for series in panel.series:
            label = _label(series, style)
            if series.kind is SeriesKind.CELLS or label in looks:
                continue
            color, marker, linestyle = _base_style(series, neutrals)
            if series.kind is SeriesKind.BAND:
                alpha, hatch = next(
                    (f for f in _BAND_FILLS if ("band", color, *f) not in used), _BAND_FILLS[-1]
                )
                used.add(("band", color, alpha, hatch))
                looks[label] = Look(color, marker, "-", hollow=False, alpha=alpha, hatch=hatch)
                continue
            if series.kind is SeriesKind.LINE:
                order = [linestyle, *(ls for ls in _LINESTYLES if ls != linestyle)]
                line = next((ls for ls in order if ("line", color, ls) not in used), linestyle)
                used.add(("line", color, line))
                looks[label] = Look(color, marker, line, hollow=False)
                continue
            line = linestyle
            if series.kind is SeriesKind.REFERENCE:
                line = next((ls for ls in _REFERENCE_LINESTYLES if ls not in used_lines), "--")
                used_lines.append(line)
            # os tons neutros contam como uma cor só: o marcador distingue sem depender do tom
            hue = color if series.model is not None else _NEUTRAL
            markers = [marker, *(m for m in _MARKERS if m != marker)]
            choice = next(
                (
                    (m, hollow)
                    for hollow in (False, True)
                    for m in markers
                    if ("mark", hue, m, hollow) not in used
                ),
                (marker, True),
            )
            used.add(("mark", hue, *choice))
            looks[label] = Look(color, choice[0], line, hollow=choice[1])
    return looks


def _tick(label: str) -> str:
    """Rótulo do eixo x: a data de um timestamp ISO; categorias inteiras."""
    is_timestamp = len(label) >= _ISO_MIN and label[4] == "-" and "T" in label
    return label[:10] if is_timestamp else label


def _number(value: float | None) -> float:
    return math.nan if value is None else float(value)


class _Positions:
    """Posições no eixo x de um painel: números como estão; categorias na ordem vista."""

    def __init__(self, panel: PanelSpec) -> None:
        self.categories: dict[str, int] = {}
        for series in panel.series:
            for value in series.x:
                if isinstance(value, str) and value not in self.categories:
                    self.categories[value] = len(self.categories)

    def of(self, values: Sequence[float | str]) -> list[float]:
        return [float(self.categories[v]) if isinstance(v, str) else float(v) for v in values]


def legend_labels(spec: FigureSpec, style: RenderStyle = DOSSIER_STYLE) -> list[str]:
    """Os rótulos da legenda da figura (um por série distinta, células fora)."""
    entries: dict[str, None] = {}
    for panel in spec.panels:
        for series in panel.series:
            if series.kind is not SeriesKind.CELLS:
                entries.setdefault(_label(series, style))
    return list(entries)


def footer_lines(spec: FigureSpec) -> list[str]:
    """O rodapé: notas da figura, omissões, notas de painel e de série, sem repetir.

    Nota de painel ou de série igual a uma nota já escrita não se repete (o texto
    "cobertura empírica (não garantida)" de todo painel do conformal sai uma vez; a nota do
    painel da VSN igual à da figura não vira "horizonte-invariante: horizonte-invariante").
    A mesma nota em vários painéis sai uma vez, prefixada por todos eles ("h+1, h+7: …");
    idem a nota da mesma série em vários painéis ("h+1, h+7 — série: …").
    """
    texts: dict[str, None] = dict.fromkeys(spec.notes)
    texts.update(dict.fromkeys(f"omissão declarada: {o}" for o in spec.omissions))
    seen = set(spec.notes)
    panel_notes: dict[str, list[str]] = {}
    for panel in spec.panels:
        note = panel.label.note
        if note and note not in seen:
            panel_notes.setdefault(note, []).append(panel.title)
    for note, titles in panel_notes.items():
        texts.setdefault(f"{', '.join(dict.fromkeys(titles))}: {note}")
    seen.update(panel_notes)
    series_notes: dict[tuple[str, str], list[str]] = {}
    for panel in spec.panels:
        for series in panel.series:
            note = series.label.note
            if note and note not in seen:
                series_notes.setdefault((series.name, note), []).append(panel.title)
    for (name, note), titles in series_notes.items():
        texts.setdefault(f"{', '.join(dict.fromkeys(titles))} — {name}: {note}")
    lines: list[str] = []
    for text in texts:
        lines += textwrap.wrap(text, _WRAP) or [""]
    return lines


def _dodged(xs: list[float], series: SeriesSpec, group: Sequence[SeriesSpec]) -> list[float]:
    """Intervalos de várias séries na mesma categoria: lado a lado, como as barras."""
    if len(group) < 2 or not all(isinstance(v, str) for v in series.x):  # noqa: PLR2004
        return xs
    step = _DODGE / (len(group) - 1)
    offset = (group.index(series) - (len(group) - 1) / 2) * step
    return [x + offset for x in xs]


def _legend_height(labels: Sequence[str], style: RenderStyle = DOSSIER_STYLE) -> float:
    """Altura da legenda: o matplotlib preenche as colunas de cima para baixo."""
    per_column = math.ceil(len(labels) / _LEGEND_COLUMNS)
    columns = [labels[i : i + per_column] for i in range(0, len(labels), per_column)]
    rows = [max(c[i].count("\n") + 1 for c in columns if i < len(c)) for i in range(per_column)]
    return style.legend_line_in * sum(rows) + style.legend_entry_in * per_column


def _legend(band: SubFigure, axes: Sequence[Sequence[Axes]]) -> None:
    handles: dict[str, Artist] = {}
    for row in axes:
        for ax in row:
            for handle, text in zip(*ax.get_legend_handles_labels(), strict=True):
                handles.setdefault(text, handle)
    if handles:
        band.legend(
            list(handles.values()),
            list(handles),
            loc="upper center",
            bbox_to_anchor=(0.5, 1.0),
            ncol=_LEGEND_COLUMNS,
            frameon=False,
            borderaxespad=0.0,
        )


def _snap(value: float) -> float:
    """`value` na grade `_LAYOUT_GRID` da fração da figura, sem zero negativo."""
    return round(float(value) / _LAYOUT_GRID) * _LAYOUT_GRID + 0.0


def _snapped(box: Bbox) -> Bbox:
    return Bbox([[_snap(box.x0), _snap(box.y0)], [_snap(box.x1), _snap(box.y1)]])


def freeze_layout(figure: Figure) -> None:
    """Roda o layout restrito uma vez, fixa o resultado na grade e desliga o motor.

    O solver do layout restrito (kiwisolver) devolve posições com ruído de arredondamento
    no último bit que muda de uma chamada para outra no MESMO processo (a ordem interna das
    variáveis do solver segue endereços de memória): o fundo da faixa do rodapé sai
    `-2.4e-16` numa chamada e `0.0` noutra, e o PDF escreve `-0` vs `0` — bytes diferentes
    para a mesma spec. Cada posição decidida pelo layout (caixas das subfiguras, posição dos
    eixos, título da faixa dos painéis) vai para a grade `_LAYOUT_GRID` (sem zero negativo) e
    o `savefig` desenha sem rodar o solver de novo; tudo a jusante é aritmética determinística
    sobre essas posições.
    """
    figure.draw_without_rendering()
    subfigures = list(figure.subfigs)
    for sub in subfigures:
        subfigures += sub.subfigs
        sub.bbox_relative.set_points(_snapped(sub.bbox_relative).get_points())
    for ax in figure.get_axes():
        ax.set_position(_snapped(ax.get_position(original=False)), which="both")
    for owner in [figure, *subfigures]:
        # o título que o layout posiciona (o matplotlib não tem acessor público do artista)
        title = getattr(owner, "_suptitle", None)
        if isinstance(title, Text):
            x, y = title.get_position()
            title.set_position((_snap(x), _snap(y)))
    figure.set_layout_engine("none")


class MatplotlibFigureRenderer:
    """Satisfaz `FigureRenderer`: uma página PDF por `FigureSpec`, no estilo dado."""

    def __init__(self, style: RenderStyle = DOSSIER_STYLE) -> None:
        self._style = style

    def identity(self) -> Mapping[str, str]:
        identity = {
            "format": "pdf",
            "matplotlib": matplotlib.__version__,
            "freetype": ft2font.__freetype_version__,
        }
        if self._style.name is not None:
            identity["style"] = self._style.name
        return identity

    def render(self, figure: FigureSpec) -> bytes:
        """Os bytes do PDF da figura (ver o docstring do módulo).

        Raises:
            ValueError: série de um modelo fora de `MODEL_STYLES`.
        """
        unknown = sorted(
            {
                series.model
                for panel in figure.panels
                for series in panel.series
                if series.model is not None and series.model not in MODEL_STYLES
            }
        )
        if unknown:
            raise ValueError(f"models without a fixed style: {unknown}")
        with rc_context(self._style.rc):  # type: ignore[arg-type]
            canvas_figure = self._draw(figure)
            freeze_layout(canvas_figure)
            buffer = io.BytesIO()
            canvas_figure.savefig(buffer, format="pdf", metadata={"CreationDate": None})
        return buffer.getvalue()

    # -- desenho ----------------------------------------------------------------------

    def _draw(self, spec: FigureSpec) -> Figure:
        """A página: painéis (layout restrito), legenda e rodapé em faixas próprias.

        Três subfiguras empilhadas: os painéis, com o layout restrito do matplotlib (rótulo
        de eixo e tick nunca cortados nem sobrepostos); a legenda da figura em duas colunas,
        cada rótulo quebrado para caber na coluna; e o rodapé (notas, omissões, notas de
        painel e de série, sem repetir). As alturas das faixas de baixo saem da contagem de
        linhas.
        """
        style = self._style
        looks = figure_looks(spec, style)
        n = len(spec.panels)
        columns = min(n, _MAX_COLUMNS)
        rows = math.ceil(n / columns)
        footer = footer_lines(spec) if style.annotations else []
        labels = legend_labels(spec, style)
        panels_in = rows * style.panel_height_in + style.title_in
        legend_in = _legend_height(labels, style) + _PAD_IN if labels else 0.05
        footer_in = _FOOTER_LINE_IN * len(footer) + _PAD_IN if footer else 0.05
        figure = Figure(
            figsize=(_WIDTH_IN, panels_in + legend_in + footer_in), layout="constrained"
        )
        FigureCanvasPdf(figure)
        bands = figure.subfigures(3, 1, height_ratios=[panels_in, legend_in, footer_in])
        top, legend_band, footer_band = (bands[i] for i in range(3))  # type: ignore[index]
        axes = top.subplots(rows, columns, squeeze=False)
        for index, panel in enumerate(spec.panels):
            self._panel(axes[index // columns][index % columns], panel, looks)
        for index in range(n, rows * columns):
            axes[index // columns][index % columns].set_visible(False)
        if style.annotations:
            top.suptitle(spec.title, fontsize=8)
        _legend(legend_band, axes)
        footer_band.text(
            0.01, 0.98, "\n".join(footer), fontsize=4.5, va="top", ha="left", linespacing=1.25
        )
        return figure

    def _panel(self, axes: Axes, panel: PanelSpec, looks: Mapping[str, Look]) -> None:
        text = self._style.text
        positions = _Positions(panel)
        title = text(panel.title)
        if self._style.annotations:
            title = f"{title} — {panel.label.status.value}"
        axes.set_title(title)
        axes.set_xlabel(text(panel.x_label))
        axes.set_ylabel(text(panel.y_label))
        groups = {
            kind: [s for s in panel.series if s.kind is kind]
            for kind in (SeriesKind.BOXES, SeriesKind.BARS, SeriesKind.INTERVAL)
        }
        for series in panel.series:
            self._series(axes, series, positions, looks, groups)
        if positions.categories:
            labels = list(positions.categories)
            # datas: um rótulo a cada `step`; categoria: todas rotuladas (posição sem rótulo
            # seria ambígua), mais inclinadas quando passam de `_MAX_TICKS`
            dates = all(_tick(label) != label for label in labels)
            step = max(1, math.ceil(len(labels) / _MAX_TICKS)) if dates else 1
            ticks = list(range(0, len(labels), step))
            rotation = 60 if not dates and len(labels) > _MAX_TICKS else 30
            axes.set_xticks([float(t) for t in ticks])
            axes.set_xticklabels(
                [text(_tick(labels[t])) for t in ticks],
                rotation=rotation,
                ha="right",
                rotation_mode="anchor",
            )

    def _series(
        self,
        axes: Axes,
        series: SeriesSpec,
        positions: _Positions,
        looks: Mapping[str, Look],
        groups: Mapping[SeriesKind, list[SeriesSpec]],
    ) -> None:
        label = _label(series, self._style)
        look = looks.get(label, Look(_NEUTRAL, _MARKERS[0], "--", hollow=False))
        color, marker, linestyle, face = look.color, look.marker, look.linestyle, look.face
        xs = positions.of(series.x)
        ys = [_number(v) for v in series.y]
        low = None if series.low is None else [_number(v) for v in series.low]
        high = None if series.high is None else [_number(v) for v in series.high]
        kind = series.kind
        if kind is SeriesKind.LINE:
            # sem modelo = o observado (y_t): fino e abaixo, nunca cobre a linha de um modelo
            observed = series.model is None
            axes.plot(
                xs,
                ys,
                color=color,
                linestyle=linestyle,
                linewidth=_OBSERVED_WIDTH if observed else None,
                zorder=_Z_OBSERVED if observed else _Z_MODEL_LINE,
                label=label,
            )
            if low is not None and high is not None:
                axes.fill_between(
                    xs, low, high, color=color, alpha=0.15, linewidth=0, zorder=_Z_BAND
                )
        elif kind is SeriesKind.POINTS:
            self._points(axes, xs, ys, low, high, (color, marker, face), label)
        elif kind is SeriesKind.BAND:
            axes.fill_between(
                xs,
                low or ys,
                high or ys,
                facecolor=color,
                edgecolor=color if look.hatch else "none",
                alpha=look.alpha,
                hatch=look.hatch,
                linewidth=0,
                zorder=_Z_BAND,
                label=label,
            )
        elif kind is SeriesKind.INTERVAL:
            xs = _dodged(xs, series, groups[SeriesKind.INTERVAL])
            self._points(axes, xs, ys, low, high, (color, marker, face), label)
        elif kind is SeriesKind.BOXES:
            self._boxes(axes, series, xs, color, label, groups[SeriesKind.BOXES])
        elif kind is SeriesKind.CELLS:
            self._cells(axes, series, ys, self._style.text)
        elif kind is SeriesKind.STEMS:
            axes.vlines(xs, 0.0, ys, color=color, linewidth=0.8)
            axes.plot(
                xs,
                ys,
                linestyle="none",
                marker=marker,
                color=color,
                markerfacecolor=face,
                label=label,
            )
            axes.axhline(0.0, color="#888888", linewidth=0.5)
        elif kind is SeriesKind.BARS:
            group = groups[SeriesKind.BARS]
            width = 0.8 / len(group)
            offset = (group.index(series) - (len(group) - 1) / 2) * width
            axes.bar(
                [x + offset for x in xs],
                ys,
                width=width,
                color=color,
                label=label,
                hatch="//" if group.index(series) % 2 else None,
            )
        elif kind is SeriesKind.VLINES:
            for x in xs:
                axes.axvline(x, color="#999999", linestyle=":", linewidth=0.6)
            axes.plot([], [], color="#999999", linestyle=":", label=label)
        else:
            self._reference(axes, series, xs, ys, label, linestyle)

    @staticmethod
    def _points(  # noqa: PLR0913 — a marca e a sua banda
        axes: Axes,
        xs: list[float],
        ys: list[float],
        low: list[float] | None,
        high: list[float] | None,
        look: tuple[str, str, str],
        label: str,
    ) -> None:
        color, marker, face = look
        if low is not None and high is not None:
            centers = [
                y if not math.isnan(y) else (lo + hi) / 2
                for y, lo, hi in zip(ys, low, high, strict=True)
            ]
            errors = [
                [max(c - lo, 0.0) for c, lo in zip(centers, low, strict=True)],
                [max(hi - c, 0.0) for c, hi in zip(centers, high, strict=True)],
            ]
            axes.errorbar(
                xs,
                ys,
                yerr=errors,
                color=color,
                marker=marker,
                markerfacecolor=face,
                linestyle="none",
                elinewidth=0.6,
                capsize=1.5,
                label=label,
            )
        else:
            axes.plot(
                xs,
                ys,
                color=color,
                marker=marker,
                markerfacecolor=face,
                linestyle="none",
                label=label,
            )

    @staticmethod
    def _boxes(  # noqa: PLR0913 — a série de caixas e o seu grupo
        axes: Axes,
        series: SeriesSpec,
        xs: list[float],
        color: str,
        label: str,
        group: list[SeriesSpec],
    ) -> None:
        width = 0.8 / len(group)
        offset = (group.index(series) - (len(group) - 1) / 2) * width
        stats = []
        kept: list[float] = []
        assert series.low is not None and series.high is not None
        assert series.whisker_low is not None and series.whisker_high is not None
        for i, x in enumerate(xs):
            values = (
                series.whisker_low[i],
                series.low[i],
                series.y[i],
                series.high[i],
                series.whisker_high[i],
            )
            if any(v is None for v in values):
                continue
            wl, q1, med, q3, wh = (float(v) for v in values)  # type: ignore[arg-type]
            stats.append({"whislo": wl, "q1": q1, "med": med, "q3": q3, "whishi": wh, "fliers": []})
            kept.append(x + offset)
        if stats:
            axes.bxp(
                stats,
                positions=kept,
                widths=width * 0.9,
                showfliers=False,
                patch_artist=True,
                boxprops={"facecolor": color, "alpha": 0.5, "linewidth": 0.5},
                medianprops={"color": "#222222", "linewidth": 0.8},
                whiskerprops={"linewidth": 0.5},
                capprops={"linewidth": 0.5},
            )
        axes.plot([], [], color=color, marker="s", linestyle="none", label=label)

    @staticmethod
    def _cells(
        axes: Axes, series: SeriesSpec, ys: list[float], display: Callable[[str], str]
    ) -> None:
        axes.imshow([ys], cmap=_SEQUENTIAL, vmin=0.0, vmax=1.0, aspect="auto")
        for i, text in enumerate(series.text or ()):
            axes.text(
                i,
                0,
                "\n".join(textwrap.wrap(display(text), 12)),
                ha="center",
                va="center",
                fontsize=3.5,
                color="white" if ys[i] < _DARK_CELL else "black",
            )
        axes.set_yticks([])
        axes.grid(visible=False)

    @staticmethod
    def _reference(  # noqa: PLR0913 — a referência e o seu estilo de linha
        axes: Axes,
        series: SeriesSpec,
        xs: list[float],
        ys: list[float],
        label: str,
        linestyle: object,
    ) -> None:
        if len(xs) == 1:
            axes.axhline(
                ys[0],
                color=_NEUTRAL,
                linestyle=linestyle,
                linewidth=0.6,
                label=label,
            )
        elif all(isinstance(v, str) for v in series.x):
            axes.plot(
                xs, ys, color=_NEUTRAL, marker="_", markersize=8, linestyle="none", label=label
            )
        else:
            axes.plot(
                xs,
                ys,
                color=_NEUTRAL,
                linestyle=linestyle,
                linewidth=0.6,
                label=label,
            )
