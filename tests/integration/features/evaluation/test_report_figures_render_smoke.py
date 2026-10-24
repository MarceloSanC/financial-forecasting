"""Smoke de geração: as dez `FigureSpec` sintéticas pelo renderizador real (Stage 8.3, A10).

As specs são montadas pelas funções das Tasks 06-08 sobre o mundo julgado sintético de
`_report_inputs`; cada uma renderiza sem erro em **uma** página PDF.
"""

from __future__ import annotations

import re

import pytest

from financial_forecasting.features.evaluation.adapters.out.plots.matplotlib_figure_renderer import (  # noqa: E501
    MatplotlibFigureRenderer,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FIGURE_IDS,
)
from financial_forecasting.features.evaluation.application.use_cases.report_figures import (
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

_PAGE = re.compile(rb"/Type\s*/Page\b")


@pytest.mark.integration
def test_ten_synthetic_specs_render_one_page_each() -> None:
    world = make_world()
    silver = make_silver(world)
    inputs = world.inputs()
    assemblies = [
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
    assert tuple(a.spec.figure_id for a in assemblies) == FIGURE_IDS
    renderer = MatplotlibFigureRenderer()
    for assembly in assemblies:
        content = renderer.render(assembly.spec)
        assert content.startswith(b"%PDF"), assembly.spec.figure_id
        assert len(_PAGE.findall(content)) == 1, assembly.spec.figure_id
