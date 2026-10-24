"""`MatplotlibFigureRenderer` — satisfaz o port `FigureRenderer` com PDF determinístico (Stage 8.3).

ADR `8_3_0003`: `matplotlib.figure.Figure` + `FigureCanvasPdf`, **sem `pyplot`** e sem
estado global; `rc_context` com `pdf.fonttype = 42` (TrueType embutida) e `DejaVu Sans`
(embarcada no matplotlib — nenhuma fonte do sistema); `savefig(format="pdf",
metadata={"CreationDate": None})`. A mesma `FigureSpec`, no mesmo ambiente, dá os mesmos
bytes em qualquer chamada e processo.

O adapter **só desenha o que a spec traz** — um eixo por painel, uma marca por
`SeriesKind` —, nunca recalcula (as caixas usam `Axes.bxp` com as estatísticas da spec).
Identidade nunca só por cor: mapa **fixo** modelo → (cor, marcador, estilo de linha), cores
da ordem categórica da skill `dataviz` (`references/palette.md`, validadas pelo
`validate_palette.js --mode light`, technical §7); modelo fora do mapa → `ValueError`
(nenhuma cor gerada). Escalas sequenciais e o heatmap do DM em `cividis`. Rótulos em PT; o
estatuto de cada painel no título e de cada série na legenda; notas e omissões no rodapé.

O processo precisa de `MPLCONFIGDIR` gravável (o container usa `/tmp`); o adapter não lê
variável de ambiente.
"""

from __future__ import annotations

import io
import math
import textwrap
from collections.abc import Mapping, Sequence
from typing import Final

import matplotlib
from matplotlib import ft2font, rc_context
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.backends.backend_pdf import FigureCanvasPdf
from matplotlib.figure import Figure

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
_NEUTRAL_MARKERS: Final = ("o", "s", "^", "D", "v", "P", "X")
_SEQUENTIAL: Final = "cividis"
_WIDTH_IN: Final = 6.3
_PANEL_HEIGHT_IN: Final = 2.6
_FOOTER_LINE_IN: Final = 0.11
_MAX_COLUMNS: Final = 2
_MAX_TICKS: Final = 6
_WRAP: Final = 120
_LEGEND_LINE_IN: Final = 0.1
_LEGEND_COLUMNS: Final = 2
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


def _label(series: SeriesSpec) -> str:
    return f"{series.name} [{series.label.status.value}]"


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


class MatplotlibFigureRenderer:
    """Satisfaz `FigureRenderer`: uma página PDF por `FigureSpec`."""

    def identity(self) -> Mapping[str, str]:
        return {
            "format": "pdf",
            "matplotlib": matplotlib.__version__,
            "freetype": ft2font.__freetype_version__,
        }

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
        with rc_context(_RC):  # type: ignore[arg-type]
            canvas_figure = self._draw(figure)
            buffer = io.BytesIO()
            canvas_figure.savefig(buffer, format="pdf", metadata={"CreationDate": None})
        return buffer.getvalue()

    # -- desenho ----------------------------------------------------------------------

    def _draw(self, spec: FigureSpec) -> Figure:
        n = len(spec.panels)
        columns = min(n, _MAX_COLUMNS)
        rows = math.ceil(n / columns)
        footer = self._footer(spec)
        footer_in = _FOOTER_LINE_IN * (len(footer) + 1)
        entries = self._legend_entries(spec)
        legend_in = _LEGEND_LINE_IN * math.ceil(len(entries) / _LEGEND_COLUMNS) + 0.3
        height = rows * _PANEL_HEIGHT_IN + footer_in + legend_in + 0.4
        figure = Figure(figsize=(_WIDTH_IN, height))
        FigureCanvasPdf(figure)
        axes = figure.subplots(rows, columns, squeeze=False)
        for index, panel in enumerate(spec.panels):
            self._panel(axes[index // columns][index % columns], panel)
        for index in range(n, rows * columns):
            axes[index // columns][index % columns].set_visible(False)
        figure.suptitle(spec.title, fontsize=8)
        figure.subplots_adjust(
            left=0.08,
            right=0.98,
            top=1 - 0.55 / height,
            bottom=(footer_in + legend_in + 0.35) / height,
            hspace=0.6,
            wspace=0.25,
        )
        handles: dict[str, Artist] = {}
        for row in axes:
            for ax in row:
                for handle, text in zip(*ax.get_legend_handles_labels(), strict=True):
                    handles.setdefault(text, handle)
        if handles:
            figure.legend(
                list(handles.values()),
                list(handles),
                loc="lower center",
                bbox_to_anchor=(0.5, footer_in / height),
                ncol=_LEGEND_COLUMNS,
                frameon=False,
            )
        figure.text(0.01, 0.01, "\n".join(footer), fontsize=4.5, va="bottom", ha="left")
        return figure

    @staticmethod
    def _legend_entries(spec: FigureSpec) -> list[str]:
        """Os rótulos da legenda da figura (um por série distinta, células fora)."""
        entries: dict[str, None] = {}
        for panel in spec.panels:
            for series in panel.series:
                if series.kind is not SeriesKind.CELLS:
                    entries.setdefault(_label(series))
        return list(entries)

    @staticmethod
    def _footer(spec: FigureSpec) -> list[str]:
        lines: list[str] = []
        texts = [*spec.notes, *(f"omissão declarada: {o}" for o in spec.omissions)]
        texts += [f"{panel.title}: {panel.label.note}" for panel in spec.panels if panel.label.note]
        for text in texts:
            lines += textwrap.wrap(text, _WRAP) or [""]
        return lines

    def _panel(self, axes: Axes, panel: PanelSpec) -> None:
        positions = _Positions(panel)
        axes.set_title(f"{panel.title} — {panel.label.status.value}")
        axes.set_xlabel(panel.x_label)
        axes.set_ylabel(panel.y_label)
        groups = {
            kind: [s for s in panel.series if s.kind is kind]
            for kind in (SeriesKind.BOXES, SeriesKind.BARS)
        }
        for index, series in enumerate(panel.series):
            self._series(axes, series, positions, index, groups)
        if positions.categories:
            labels = list(positions.categories)
            step = max(1, math.ceil(len(labels) / _MAX_TICKS))
            ticks = list(range(0, len(labels), step))
            axes.set_xticks([float(t) for t in ticks])
            axes.set_xticklabels([_tick(labels[t]) for t in ticks], rotation=30, ha="right")

    @staticmethod
    def _style(series: SeriesSpec, index: int) -> Style:
        if series.model is not None:
            return MODEL_STYLES[series.model]
        return _NEUTRAL, _NEUTRAL_MARKERS[index % len(_NEUTRAL_MARKERS)], "--"

    def _series(
        self,
        axes: Axes,
        series: SeriesSpec,
        positions: _Positions,
        index: int,
        groups: Mapping[SeriesKind, list[SeriesSpec]],
    ) -> None:
        color, marker, linestyle = self._style(series, index)
        label = _label(series)
        xs = positions.of(series.x)
        ys = [_number(v) for v in series.y]
        low = None if series.low is None else [_number(v) for v in series.low]
        high = None if series.high is None else [_number(v) for v in series.high]
        kind = series.kind
        if kind is SeriesKind.LINE:
            axes.plot(xs, ys, color=color, linestyle=linestyle, label=label)
            if low is not None and high is not None:
                axes.fill_between(xs, low, high, color=color, alpha=0.15, linewidth=0)
        elif kind is SeriesKind.POINTS:
            self._points(axes, xs, ys, low, high, color, marker, label)
        elif kind is SeriesKind.BAND:
            axes.fill_between(
                xs, low or ys, high or ys, color=color, alpha=0.2, linewidth=0, label=label
            )
        elif kind is SeriesKind.INTERVAL:
            self._points(axes, xs, ys, low, high, color, marker, label)
        elif kind is SeriesKind.BOXES:
            self._boxes(axes, series, xs, color, label, groups[SeriesKind.BOXES])
        elif kind is SeriesKind.CELLS:
            self._cells(axes, series, ys)
        elif kind is SeriesKind.STEMS:
            axes.vlines(xs, 0.0, ys, color=color, linewidth=0.8)
            axes.plot(xs, ys, linestyle="none", marker=marker, color=color, label=label)
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
            self._reference(axes, series, xs, ys, label)

    @staticmethod
    def _points(  # noqa: PLR0913 — a marca e a sua banda
        axes: Axes,
        xs: list[float],
        ys: list[float],
        low: list[float] | None,
        high: list[float] | None,
        color: str,
        marker: str,
        label: str,
    ) -> None:
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
                linestyle="none",
                elinewidth=0.6,
                capsize=1.5,
                label=label,
            )
        else:
            axes.plot(xs, ys, color=color, marker=marker, linestyle="none", label=label)

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
    def _cells(axes: Axes, series: SeriesSpec, ys: list[float]) -> None:
        axes.imshow([ys], cmap=_SEQUENTIAL, vmin=0.0, vmax=1.0, aspect="auto")
        for i, text in enumerate(series.text or ()):
            axes.text(
                i,
                0,
                "\n".join(textwrap.wrap(text, 12)),
                ha="center",
                va="center",
                fontsize=3.5,
                color="white" if ys[i] < _DARK_CELL else "black",
            )
        axes.set_yticks([])
        axes.grid(visible=False)

    @staticmethod
    def _reference(
        axes: Axes, series: SeriesSpec, xs: list[float], ys: list[float], label: str
    ) -> None:
        if len(xs) == 1:
            axes.axhline(ys[0], color=_NEUTRAL, linestyle="--", linewidth=0.6, label=label)
        elif all(isinstance(v, str) for v in series.x):
            axes.plot(
                xs, ys, color=_NEUTRAL, marker="_", markersize=8, linestyle="none", label=label
            )
        else:
            axes.plot(xs, ys, color=_NEUTRAL, linestyle="--", linewidth=0.6, label=label)
