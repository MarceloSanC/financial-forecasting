"""Estilo de apresentação das figuras para o texto do TCC (issue #250).

Sobre as dez specs sintéticas da 8.3: nenhum identificador interno nem marcador de
estatuto em texto desenhado, sem título da figura nem rodapé, fonte de pelo menos 8 pt,
altura até meia página A4, rótulos de legenda distintos como no dossiê, bytes iguais em
renderizações repetidas e a identidade do renderizador com o estilo. O dossiê continua com
o estilo padrão e a identidade da 8.3. Issue #268: vírgula decimal e meia-risca nos pares,
GBM sem semente, legenda sem série que não desenha nada e rótulos do eixo x horizontais
quando cabem. Integração (não unit): o módulo importa matplotlib pelo adapter de plots
(gate de pureza dos unit do `evaluation`).
"""

from __future__ import annotations

import dataclasses
import re

import pytest
from matplotlib import rc_context
from matplotlib.legend import Legend
from matplotlib.text import Text

from financial_forecasting.features.evaluation.adapters.out.plots.matplotlib_figure_renderer import (  # noqa: E501
    _RC,
    DOSSIER_STYLE,
    MODEL_STYLES,
    MatplotlibFigureRenderer,
    RenderStyle,
    drawn,
    footer_lines,
    legend_labels,
    ticks_fit,
)
from financial_forecasting.features.evaluation.adapters.out.plots.presentation_style import (
    AXIS_LABELS,
    FAMILY_NAMES,
    METHOD_NAMES,
    MODEL_NAMES,
    PRESENTATION_OMISSIONS,
    PRESENTATION_STYLE,
    presentation_text,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FIGURE_CATALOG,
    FIGURE_IDS,
    FigureSpec,
    SeriesKind,
    SeriesSpec,
    StatusLabel,
)
from tests.integration.features.evaluation.test_matplotlib_figure_renderer_layout import (
    _DESCRIPTIVE,
    _assemblies,
    _interval,
    _spec,
)

pytestmark = pytest.mark.integration

_SNAKE_CASE = re.compile(r"[A-Za-z]{2,}_[A-Za-z0-9]{2,}")
"""Identificador interno (`baseline_ar1`, `target_timestamp`); `d_t` e `τ_l` não casam."""
_DASH = "\N{EN DASH}"
_DECIMAL_POINT = re.compile(r"\d\.\d")
_HALF_A4_IN = 297 / 2 / 25.4
_MIN_FONT_PT = 8.0


@pytest.fixture(scope="module")
def specs() -> list[FigureSpec]:
    return [assembly.spec for assembly in _assemblies()]


def _drawn_texts(spec: FigureSpec) -> list[Text]:
    figure = MatplotlibFigureRenderer(PRESENTATION_STYLE)._draw(spec)
    return [t for t in figure.findobj(Text) if t.get_visible() and t.get_text().strip()]


@pytest.mark.parametrize(
    ("internal", "shown"),
    [
        *MODEL_NAMES.items(),
        *FAMILY_NAMES.items(),
        *METHOD_NAMES.items(),
    ],
)
def test_identifier_shown_by_display_name(internal: str, shown: str) -> None:
    assert presentation_text(internal) == shown
    assert presentation_text(f"comparador {internal}") == f"comparador {shown}"


def test_display_names_of_the_issue() -> None:
    assert [MODEL_NAMES[m] for m in MODEL_STYLES] == [
        "TFT",
        "Retorno nulo",
        "Média histórica",
        "AR(1)",
        "EWMA-vol",
        "Quantis empíricos",
        "GBM quantílico",
    ]
    assert list(FAMILY_NAMES.values()) == ["Preço", "Técnico", "Sentimento", "Fundamento"]


def test_identifier_replaced_only_as_whole_word() -> None:
    assert presentation_text("pricey technicality") == "pricey technicality"
    assert presentation_text("baseline_ar1x") == "baseline_ar1x"


def test_axis_labels_exact_text_only() -> None:
    assert presentation_text("τ") == "nível τ"
    assert presentation_text("target_timestamp") == "data-alvo"
    assert presentation_text("retorno") == "retorno"
    assert presentation_text("ĉ(τ)") == AXIS_LABELS["ĉ(τ)"] == "cobertura observada ĉ(τ)"
    # o mesmo texto dentro de outro não é eixo
    assert presentation_text("MPIW 0,1-0,9") == f"MPIW 0,1{_DASH}0,9"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("cauda 0.02", "cauda 0,02"),
        ("PICP 0.02-0.98", f"PICP 0,02{_DASH}0,98"),
        ("faixa 0,1-0,9", f"faixa 0,1{_DASH}0,9"),
        ("cobertura nominal, par 0,25-0,75", f"cobertura nominal, par 0,25{_DASH}0,75"),
        ("2019-12-27", "2019-12-27"),
        ("Δ_f = s_f(h+7) - s_f(h+1), loco", r"$\Delta_f$ = $s_f(h+7)$ - $s_f(h+1)$, ablação"),
    ],
)
def test_numbers_with_decimal_comma_and_pairs_with_en_dash(text: str, shown: str) -> None:
    assert presentation_text(text) == shown


def test_gbm_shown_without_its_single_seed() -> None:
    assert presentation_text("gbm_quantile (seed 0)") == "GBM quantílico"
    assert presentation_text("gbm_quantile (seed 0), Wilson 0,95") == (
        "GBM quantílico, Wilson 0,95"
    )
    assert presentation_text("tft_quantile (seed 1)") == "TFT (semente 1)"


def test_seed_wording_in_portuguese() -> None:
    assert presentation_text("baseline_ar1 (sem seed), Wilson 0,95") == "AR(1), Wilson 0,95"
    assert presentation_text("tft_quantile (seed 3)") == "TFT (semente 3)"
    assert presentation_text("candidato, média entre seeds") == "TFT, média entre sementes"
    assert (
        presentation_text("tft_quantile (larguras de 10 seeds empilhadas: seed 1, seed 2)")
        == "TFT (larguras das 10 sementes empilhadas)"
    )


def test_indexed_notation_in_mathtext() -> None:
    assert presentation_text("d_t vs. baseline_ar1") == "$d_t$ vs. AR(1)"
    assert presentation_text("ACF de d_t vs. gbm_quantile") == "ACF de $d_t$ vs. GBM quantílico"
    assert presentation_text("Δ_f = s_f(h+7) - s_f(h+1), loco") == (
        r"$\Delta_f$ = $s_f(h+7)$ - $s_f(h+1)$, ablação"
    )
    assert presentation_text("I_f(h), permutation") == "$I_f(h)$, permutação"
    assert presentation_text("d_t") == "diferencial de perda $d_t$"


def test_numeric_ticks_with_decimal_comma(specs: list[FigureSpec]) -> None:
    spec = specs[FIGURE_IDS.index("vsn_weights")]
    for style, separator in ((PRESENTATION_STYLE, ","), (DOSSIER_STYLE, ".")):
        figure = MatplotlibFigureRenderer(style)._draw(spec)
        figure.draw_without_rendering()
        labels = [t.get_text() for ax in figure.get_axes() for t in ax.get_yticklabels()]
        assert any(separator in label for label in labels), labels
        other = "." if separator == "," else ","
        assert not any(other in label for label in labels), labels


def test_omissions_are_catalog_figures_with_reason() -> None:
    assert set(PRESENTATION_OMISSIONS) <= set(FIGURE_IDS)
    assert set(PRESENTATION_OMISSIONS) == {"dm_candidate_vs_comparators"}
    assert all(reason.strip() for reason in PRESENTATION_OMISSIONS.values())


def test_no_internal_identifier_or_status_marker_drawn(specs: list[FigureSpec]) -> None:
    statuses = [status.value for status in StatusLabel]
    for spec in specs:
        if spec.figure_id in PRESENTATION_OMISSIONS:
            continue
        for text in (t.get_text() for t in _drawn_texts(spec)):
            assert not _SNAKE_CASE.search(text), (spec.figure_id, text)
            assert not _DECIMAL_POINT.search(text), (spec.figure_id, text)
            assert not any(f"[{status}]" in text for status in statuses), (spec.figure_id, text)
            assert not text.endswith(tuple(f"— {status}" for status in statuses)), text


def test_no_figure_title_nor_footer_drawn(specs: list[FigureSpec]) -> None:
    for spec in specs:
        drawn = {t.get_text() for t in _drawn_texts(spec)}
        assert FIGURE_CATALOG[spec.figure_id].title not in drawn, spec.figure_id
        footer = footer_lines(spec)
        # uma linha só pode coincidir com o título de um painel (VSN: horizonte-invariante)
        assert len(footer) == 1 or "\n".join(footer) not in drawn, spec.figure_id
        assert not [t for t in drawn if "omissão declarada" in t], spec.figure_id


def test_drawn_text_at_least_seven_points(specs: list[FigureSpec]) -> None:
    for spec in specs:
        if spec.figure_id in PRESENTATION_OMISSIONS:
            continue
        for text in _drawn_texts(spec):
            assert float(text.get_fontsize()) >= _MIN_FONT_PT, (spec.figure_id, text.get_text())


def test_figure_fits_half_an_a4_page(specs: list[FigureSpec]) -> None:
    for spec in specs:
        if spec.figure_id in PRESENTATION_OMISSIONS:
            continue
        figure = MatplotlibFigureRenderer(PRESENTATION_STYLE)._draw(spec)
        width, height = figure.get_size_inches()
        assert width == pytest.approx(6.3)
        assert height <= _HALF_A4_IN, (spec.figure_id, height)


def test_legend_entries_stay_distinct(specs: list[FigureSpec]) -> None:
    dossier_drawn = dataclasses.replace(DOSSIER_STYLE, legend_drawn_only=True)
    for spec in specs:
        shown = legend_labels(spec, PRESENTATION_STYLE)
        assert len(set(shown)) == len(legend_labels(spec, dossier_drawn)), spec.figure_id


def _empty(series_id: str, model: str) -> SeriesSpec:
    return SeriesSpec(
        series_id=series_id,
        kind=SeriesKind.INTERVAL,
        name=series_id,
        model=model,
        label=_DESCRIPTIVE,
        x=("a", "b"),
        y=(None, None),
        low=(None, None),
        high=(None, None),
    )


def _rendered_legend(spec: FigureSpec, style: RenderStyle) -> list[str]:
    with rc_context(_RC):  # type: ignore[arg-type]
        figure = MatplotlibFigureRenderer(style)._draw(spec)
    return [t.get_text() for legend in figure.findobj(Legend) for t in legend.get_texts()]


def test_series_without_any_mark_left_out_of_the_presentation_legend() -> None:
    spec = _spec(
        (_interval("drawn", "tft_quantile"), _empty("baseline_zero_return", "baseline_zero_return"))
    )
    assert drawn(spec.panels[0].series[0])
    assert not drawn(spec.panels[0].series[1])
    assert _rendered_legend(spec, PRESENTATION_STYLE) == ["drawn"]
    assert legend_labels(spec, PRESENTATION_STYLE) == ["drawn"]
    # o dossiê da 8.3 não muda: a série vazia segue na legenda
    assert len(_rendered_legend(spec, DOSSIER_STYLE)) == 2  # noqa: PLR2004
    assert len(legend_labels(spec, DOSSIER_STYLE)) == 2  # noqa: PLR2004


def test_vertical_lines_count_as_drawn_by_their_x() -> None:
    cuts = SeriesSpec(
        series_id="cuts",
        kind=SeriesKind.VLINES,
        name="corte de fold",
        label=_DESCRIPTIVE,
        x=(1.0, 2.0),
        y=(None, None),
    )
    assert drawn(cuts)


def _rotations(spec: FigureSpec, style: RenderStyle) -> set[float]:
    with rc_context(style.rc):  # type: ignore[arg-type]
        figure = MatplotlibFigureRenderer(style)._draw(spec)
    return {t.get_rotation() for ax in figure.get_axes() for t in ax.get_xticklabels()}


def test_category_ticks_horizontal_when_they_fit(specs: list[FigureSpec]) -> None:
    vsn = specs[FIGURE_IDS.index("vsn_weights")]
    assert _rotations(vsn, PRESENTATION_STYLE) == {0.0}
    assert _rotations(vsn, DOSSIER_STYLE) == {30.0}


def test_ticks_fit_measures_the_labels() -> None:
    with rc_context(PRESENTATION_STYLE.rc):  # type: ignore[arg-type]
        assert ticks_fit(["Preço", "Técnico", "Sentimento", "Fundamento"], columns=1)
        assert not ticks_fit(["Sentimento", "Fundamento"] * 4, columns=2)
        assert ticks_fit(["um rótulo comprido que não tem vizinho"], columns=2)


def test_presentation_bytes_repeat_and_differ_from_dossier(specs: list[FigureSpec]) -> None:
    renderer = MatplotlibFigureRenderer(PRESENTATION_STYLE)
    spec = specs[FIGURE_IDS.index("native_vs_conformal")]
    first = renderer.render(spec)
    assert first.startswith(b"%PDF")
    assert renderer.render(spec) == first
    assert MatplotlibFigureRenderer().render(spec) != first


def test_identity_names_the_style_only_in_presentation() -> None:
    dossier = MatplotlibFigureRenderer().identity()
    assert "style" not in dossier
    assert MatplotlibFigureRenderer(DOSSIER_STYLE).identity() == dossier
    assert MatplotlibFigureRenderer(PRESENTATION_STYLE).identity() == {
        **dossier,
        "style": "presentation",
    }


def test_default_renderer_is_the_dossier_style(specs: list[FigureSpec]) -> None:
    spec = specs[0]
    assert MatplotlibFigureRenderer().render(spec) == MatplotlibFigureRenderer(
        DOSSIER_STYLE
    ).render(spec)
