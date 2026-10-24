"""Layout do `MatplotlibFigureRenderer` (Stage 8.3, fix do `FAIL_LAYOUT` da Etapa R).

Sobre as dez specs sintéticas e specs mínimas: séries distintas com estilos distintos (cor,
marcador, vazado), rótulos de legenda que cabem numa coluna da página, rodapé sem nota
repetida, e todo texto e eixo dentro da página (nada cortado nas bordas), medido nas caixas
renderizadas.
"""

from __future__ import annotations

import pytest
from matplotlib import rc_context
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.legend import Legend

from financial_forecasting.features.evaluation.adapters.out.plots.matplotlib_figure_renderer import (  # noqa: E501
    _LEGEND_WRAP,
    _RC,
    MatplotlibFigureRenderer,
    figure_looks,
    footer_lines,
    legend_labels,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FIGURE_CATALOG,
    ElementLabel,
    FigureSpec,
    PanelScope,
    PanelSpec,
    SeriesKind,
    SeriesSpec,
    StatusLabel,
)
from financial_forecasting.features.evaluation.application.use_cases.report_figures import (
    FigureAssembly,
    dm_figure,
    fan_chart_figure,
    h3_figure,
    loss_differential_figure,
    native_vs_conformal_figure,
    picp_mpiw_figure,
    quantile_score_figure,
    reliability_figure,
    sharpness_figure,
    vsn_figure,
)
from tests.unit.features.evaluation._report_inputs import (
    CANDIDATE_SEEDS,
    make_silver,
    make_world,
)

pytestmark = pytest.mark.integration

_DESCRIPTIVE = ElementLabel(status=StatusLabel.DESCRIPTIVE)


def _assemblies() -> list[FigureAssembly]:
    world = make_world()
    silver = make_silver(world)
    inputs = world.inputs()
    return [
        reliability_figure(inputs),
        quantile_score_figure(inputs),
        sharpness_figure(inputs, silver),
        picp_mpiw_figure(inputs),
        dm_figure(inputs),
        fan_chart_figure(inputs, silver, CANDIDATE_SEEDS),
        loss_differential_figure(inputs),
        h3_figure(inputs),
        vsn_figure(inputs),
        native_vs_conformal_figure(inputs),
    ]


@pytest.fixture(scope="module")
def specs() -> list[FigureSpec]:
    return [assembly.spec for assembly in _assemblies()]


def _series(series_id: str, name: str, model: str | None, kind: SeriesKind) -> SeriesSpec:
    return SeriesSpec(
        series_id=series_id,
        kind=kind,
        name=name,
        model=model,
        label=_DESCRIPTIVE,
        x=(0.1, 0.5),
        y=(0.2, 0.3),
    )


def _spec(series: tuple[SeriesSpec, ...], panel_note: str | None = None) -> FigureSpec:
    entry = FIGURE_CATALOG["vsn_weights"]
    panel = PanelSpec(
        panel_id="invariant",
        scope=PanelScope.HORIZON_INVARIANT,
        horizon=None,
        title="horizonte-invariante",
        x_label="x",
        y_label="y",
        series=series,
        label=ElementLabel(status=StatusLabel.DESCRIPTIVE, note=panel_note),
    )
    return FigureSpec(
        figure_id="vsn_weights",
        title=entry.title,
        panels=(panel,),
        notes=entry.required_notes,
        omissions=entry.omissions,
    )


def test_distinct_series_get_distinct_looks_in_every_figure(specs: list[FigureSpec]) -> None:
    for spec in specs:
        looks = figure_looks(spec)
        keys = [look.key() for look in looks.values()]
        assert len(keys) == len(set(keys)), spec.figure_id


def test_same_model_series_keep_the_model_color_and_change_marker() -> None:
    spec = _spec(
        (
            _series("a", "tft_quantile (seed 1)", "tft_quantile", SeriesKind.POINTS),
            _series("b", "tft_quantile (seed 2)", "tft_quantile", SeriesKind.POINTS),
            _series("c", "sem modelo 1", None, SeriesKind.POINTS),
            _series("d", "sem modelo 2", None, SeriesKind.POINTS),
        )
    )
    looks = list(figure_looks(spec).values())
    assert looks[0].color == looks[1].color
    assert looks[0].marker != looks[1].marker
    assert looks[2].marker != looks[3].marker


def test_legend_labels_fit_one_column(specs: list[FigureSpec]) -> None:
    for spec in specs:
        for label in legend_labels(spec):
            assert all(len(line) <= _LEGEND_WRAP for line in label.split("\n")), label


def test_footer_does_not_repeat_a_panel_note_equal_to_a_figure_note() -> None:
    spec = _spec(
        (_series("a", "peso", None, SeriesKind.POINTS),), panel_note="horizonte-invariante"
    )
    lines = footer_lines(spec)
    assert lines.count("horizonte-invariante") == 1
    assert not any("horizonte-invariante: horizonte-invariante" in line for line in lines)


def test_conformal_note_of_every_panel_appears_once(specs: list[FigureSpec]) -> None:
    conformal = next(s for s in specs if s.figure_id == "native_vs_conformal")
    text = "\n".join(footer_lines(conformal))
    assert text.count("cobertura empírica (não garantida)") == 1


def test_series_notes_reach_the_footer(specs: list[FigureSpec]) -> None:
    sharpness = next(s for s in specs if s.figure_id == "sharpness_diagram")
    text = " ".join(footer_lines(sharpness))
    assert "degenerados excluídos pela máscara do MPIW" in text


def _outside(figure: Figure) -> list[str]:
    """O que sai da página: eixos (com ticks e rótulos), legendas e textos das faixas."""
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    renderer = canvas.get_renderer()
    page = figure.bbox
    boxes = [
        (f"eixo {ax.get_title()!r}", ax.get_tightbbox(renderer))
        for ax in figure.get_axes()
        if ax.get_visible()
    ]
    boxes += [
        (f"legenda {i}", lg.get_window_extent(renderer))
        for i, lg in enumerate(figure.findobj(Legend))
    ]
    for sub in [figure, *figure.subfigs]:
        boxes += [
            (f"texto {t.get_text()[:30]!r}", t.get_window_extent(renderer))
            for t in sub.texts
            if t.get_text()
        ]
    return [
        name
        for name, box in boxes
        if box is not None
        and (
            box.x0 < page.x0 - 1
            or box.x1 > page.x1 + 1
            or box.y0 < page.y0 - 1
            or box.y1 > page.y1 + 1
        )
    ]


def test_every_text_inside_the_page(specs: list[FigureSpec]) -> None:
    renderer = MatplotlibFigureRenderer()
    for spec in specs:
        with rc_context(_RC):  # type: ignore[arg-type]
            figure = renderer._draw(spec)
            assert _outside(figure) == [], spec.figure_id
