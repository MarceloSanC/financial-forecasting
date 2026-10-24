"""Contrato do port `FigureRenderer` — fake e real (Stage 8.3, Task 11; A9).

Pernas `[fake, real]`: `InMemoryFigureRenderer` e `MatplotlibFigureRenderer`. As duas
devolvem bytes que começam com `%PDF`, iguais para a mesma spec e diferentes para dado
diferente, e a identidade traz o formato. Só no real: bytes iguais entre dois
subprocessos com `PYTHONHASHSEED` diferentes, bytes iguais sob ruído de último bit do
solver do layout restrito (o kiwisolver varia entre chamadas no mesmo processo), sem
`/CreationDate`, fontes TrueType embutidas (`/FontFile2`, nenhuma `Type3`), uma página e
recusa de modelo sem estilo fixo.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from matplotlib import layout_engine
from matplotlib.figure import Figure
from matplotlib.transforms import Bbox

from financial_forecasting.features.evaluation.adapters.out.plots.matplotlib_figure_renderer import (  # noqa: E501
    MatplotlibFigureRenderer,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    ElementLabel,
    FigureSpec,
    PanelScope,
    PanelSpec,
    SeriesKind,
    SeriesSpec,
    StatusLabel,
)
from financial_forecasting.features.evaluation.application.ports.out.figure_renderer import (
    FigureRenderer,
)
from tests.fakes.features.evaluation.in_memory_figure_renderer import InMemoryFigureRenderer

_REPO = Path(__file__).resolve().parents[4]
_PAGE = re.compile(rb"/Type\s*/Page\b")


def sample_spec(value: float = 0.11, model: str = "tft_quantile") -> FigureSpec:
    """Uma `FigureSpec` pequena (quantile score, um painel por horizonte)."""
    label = ElementLabel(status=StatusLabel.DESCRIPTIVE_PROFILE)
    panels = tuple(
        PanelSpec(
            panel_id=f"h{h}",
            scope=PanelScope.HORIZON,
            horizon=h,
            title=f"h+{h}",
            x_label="τ",
            y_label="P̄_τ",
            series=(
                SeriesSpec(
                    series_id="candidate",
                    kind=SeriesKind.LINE,
                    name="candidato",
                    model=model,
                    label=label,
                    x=(0.1, 0.5, 0.9),
                    y=(value, 0.2, 0.12),
                    low=(0.1, 0.18, 0.11),
                    high=(0.12, 0.22, 0.13),
                ),
            ),
            label=label,
        )
        for h in (1, 7)
    )
    return FigureSpec(
        figure_id="quantile_score_plot",
        title="Quantile score plot",
        panels=panels,
        notes=(),
        omissions=(),
    )


@pytest.fixture(params=["fake", "real"])
def renderer(request: pytest.FixtureRequest) -> FigureRenderer:
    if request.param == "fake":
        return InMemoryFigureRenderer()
    return MatplotlibFigureRenderer()


@pytest.mark.contract
def test_same_spec_same_bytes_twice(renderer: FigureRenderer) -> None:
    assert renderer.render(sample_spec()) == renderer.render(sample_spec())


@pytest.mark.contract
def test_starts_with_pdf_magic(renderer: FigureRenderer) -> None:
    assert renderer.render(sample_spec()).startswith(b"%PDF")


@pytest.mark.contract
def test_identity_has_format(renderer: FigureRenderer) -> None:
    identity = renderer.identity()
    assert identity["format"] == "pdf"
    if isinstance(renderer, MatplotlibFigureRenderer):
        assert identity["matplotlib"] == "3.11.0"
        assert identity["freetype"]


@pytest.mark.contract
def test_different_data_different_bytes(renderer: FigureRenderer) -> None:
    assert renderer.render(sample_spec(0.11)) != renderer.render(sample_spec(0.15))


_SUBPROCESS = (
    "import hashlib, sys\n"
    "from tests.contract.features.evaluation.test_figure_renderer_contract import sample_spec\n"
    "from financial_forecasting.features.evaluation.adapters.out.plots."
    "matplotlib_figure_renderer import MatplotlibFigureRenderer\n"
    "sys.stdout.write(hashlib.sha256(MatplotlibFigureRenderer().render(sample_spec())).hexdigest())\n"
)


@pytest.mark.contract
def test_bytes_equal_across_subprocesses_with_different_hash_seeds() -> None:
    digests = []
    for seed in ("0", "12345"):
        result = subprocess.run(  # o próprio interpretador, código literal
            [sys.executable, "-c", _SUBPROCESS],
            cwd=_REPO,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        digests.append(result.stdout.strip())
    local = hashlib.sha256(MatplotlibFigureRenderer().render(sample_spec())).hexdigest()
    assert digests[0] == digests[1] == local


_SOLVER_NOISE = 1e-15
"""Ordem do ruído de arredondamento do kiwisolver visto no PDF real (fundo do rodapé
`-2.4e-16` vs `0.0` entre duas chamadas no mesmo processo)."""
_CONSTRAINED_LAYOUT: Callable[..., object] = vars(layout_engine)["do_constrained_layout"]


def _noisy_constrained_layout(sign: float) -> Callable[..., object]:
    """O layout restrito real, seguido de um ruído de último bit com o sinal dado.

    Reproduz de forma determinística o que o solver faz ao acaso: as mesmas posições, a
    menos de ~1e-15 para cima ou para baixo, em toda subfigura e todo eixo.
    """

    def run(figure: Figure, *args: object, **kwargs: object) -> object:
        result = _CONSTRAINED_LAYOUT(figure, *args, **kwargs)
        subfigures = list(figure.subfigs)
        for sub in subfigures:
            subfigures += sub.subfigs
            sub.bbox_relative.set_points(sub.bbox_relative.get_points() + sign * _SOLVER_NOISE)
        for ax in figure.get_axes():
            points = ax.get_position(original=False).get_points() + sign * _SOLVER_NOISE
            ax.set_position(Bbox(points), which="active")
        return result

    return run


@pytest.mark.contract
def test_bytes_ignore_layout_solver_rounding_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ruído de último bit no resultado do layout restrito não muda um byte do PDF."""
    rendered = []
    for sign in (-1.0, 1.0, -1.0):
        monkeypatch.setattr(layout_engine, "do_constrained_layout", _noisy_constrained_layout(sign))
        rendered.append(MatplotlibFigureRenderer().render(sample_spec()))
    assert rendered[0] == rendered[1] == rendered[2]


@pytest.mark.contract
def test_no_creation_date() -> None:
    assert b"/CreationDate" not in MatplotlibFigureRenderer().render(sample_spec())


@pytest.mark.contract
def test_type42_fonts_embedded() -> None:
    content = MatplotlibFigureRenderer().render(sample_spec())
    assert b"/FontFile2" in content
    assert not re.search(rb"/Subtype\s*/Type3", content)


@pytest.mark.contract
def test_unknown_model_raises() -> None:
    spec = sample_spec(model="a_new_model")
    with pytest.raises(ValueError, match="a_new_model"):
        MatplotlibFigureRenderer().render(spec)


@pytest.mark.contract
def test_one_page() -> None:
    content = MatplotlibFigureRenderer().render(replace(sample_spec()))
    assert len(_PAGE.findall(content)) == 1
