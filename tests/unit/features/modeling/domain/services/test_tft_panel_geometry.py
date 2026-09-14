"""Testes unitários de `tft_panel_geometry` (issue #75) — a regra do painel, isolada.

Cobre, sem torch e sem o adapter:

- **`eligible_decisions` (I17)** — as duas bordas da regra, uma a uma: `t == L-1` entra e
  `t == L-2` não (janela `[t-L+1, t]` inclusive); `t + H == N-1` entra e `t + H == N`
  não (decodificador completo). Ordem preservada; vazio quando nada cabe.
- **`validate_contiguous` (C4/D5)** — fora do painel (negativo e `== panel_size`),
  salto, repetição, decrescente; vazio é aceito (o teste fit-only usa `test=()`).
- **`validate_structure` (C4)** — cada guarda com a sua mensagem; devolve `len(rows)`.
- **`resolve_panel_geometry` (C3)** — treino/monitor vazios após a filtragem erguem
  nomeando a partição; sucesso devolve as faixas elegíveis e o tamanho do painel.

O texto exato das mensagens nas duas pernas é o golden `test_tft_trainer_golden.py`;
aqui os asserts usam o marcador e o trecho discriminante.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.modeling.domain.services.tft_panel_geometry import (
    PanelGeometry,
    eligible_decisions,
    resolve_panel_geometry,
    validate_contiguous,
    validate_structure,
)

pytestmark = pytest.mark.unit

_PANEL = 20
_ROWS = [[float(i), float(i % 3)] for i in range(_PANEL)]
_TARGET = [0.001 * i for i in range(_PANEL)]
_FEATURES = ("a", "b")


# -- eligible_decisions (I17) ---------------------------------------------------


def test_window_boundary_is_encoder_length_minus_one_inclusive() -> None:
    """`t = L-1` tem janela `[0, L-1]` completa; `t = L-2` não."""
    encoder_length = 5
    out = eligible_decisions(
        range(_PANEL), encoder_length=encoder_length, max_horizon=1, panel_size=_PANEL
    )
    assert encoder_length - 2 not in out
    assert out[0] == encoder_length - 1


def test_decoder_boundary_is_panel_size_minus_one_minus_horizon_inclusive() -> None:
    """`t + H = N-1` cabe (último rótulo existe); `t + H = N` não."""
    out = eligible_decisions(range(_PANEL), encoder_length=1, max_horizon=3, panel_size=_PANEL)
    assert out[-1] == _PANEL - 1 - 3
    assert _PANEL - 3 not in out


def test_eligibility_preserves_order_and_filters_only() -> None:
    out = eligible_decisions((7, 8, 9, 10), encoder_length=9, max_horizon=2, panel_size=12)
    assert out == (8, 9)


def test_eligibility_is_empty_when_nothing_fits() -> None:
    assert eligible_decisions(range(5), encoder_length=10, max_horizon=1, panel_size=5) == ()


# -- validate_contiguous (C4/D5) --------------------------------------------------


@pytest.mark.parametrize(
    ("indices", "fragment"),
    [
        pytest.param((-1, 0), "[0]=-1 fora do painel", id="negative"),
        pytest.param((18, 19, 20), "[2]=20 fora do painel de 20", id="equal-to-size"),
        pytest.param((1, 2, 4), "2 seguido de 4", id="gap"),
        pytest.param((1, 1), "1 seguido de 1", id="repeat"),
        pytest.param((3, 2), "3 seguido de 2", id="decreasing"),
    ],
)
def test_contiguous_rejects_each_shape_naming_the_range(
    indices: tuple[int, ...], fragment: str
) -> None:
    with pytest.raises(ValueError, match=r"\(C4\)") as raised:
        validate_contiguous("probe", indices, _PANEL)
    assert fragment in str(raised.value)
    assert str(raised.value).startswith("probe")


def test_contiguous_accepts_empty_and_full_ranges() -> None:
    validate_contiguous("probe", (), _PANEL)
    validate_contiguous("probe", tuple(range(_PANEL)), _PANEL)


# -- validate_structure (C4) ------------------------------------------------------


def _structure(**overrides: object) -> int:
    kwargs: dict[str, object] = {
        "feature_names": _FEATURES,
        "known_feature_names": ("b",),
        "rows": _ROWS,
        "target": _TARGET,
        "train_decision_indices": tuple(range(10)),
        "early_stop_decision_indices": (12, 13),
        "test_decision_indices": (16, 17),
        "max_horizon": 2,
        "horizons": (1, 2),
    }
    kwargs.update(overrides)
    return validate_structure(**kwargs)  # type: ignore[arg-type]


def test_structure_returns_panel_size_on_success() -> None:
    assert _structure() == _PANEL


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        pytest.param(
            {"target": _TARGET[:-1]}, "len(target)=19 != len(rows)=20", id="target-length"
        ),
        pytest.param(
            {"rows": [*_ROWS[:5], [1.0], *_ROWS[6:]]},
            "rows[5] tem 1 colunas, esperado 2",
            id="row-width",
        ),
        pytest.param(
            {"known_feature_names": ("zz",)},
            "não contido em feature_names: ['zz']",
            id="known-not-contained",
        ),
        pytest.param(
            {"max_horizon": 0, "horizons": ()},
            "max_horizon deve ser >= 1, recebido 0",
            id="max-horizon",
        ),
        pytest.param({"horizons": ()}, "horizons não pode ser vazio", id="empty-horizons"),
        pytest.param({"horizons": (1, 3)}, "horizons [3] fora de 1..2", id="horizon-out-of-range"),
        pytest.param(
            {"early_stop_decision_indices": ()},
            "early_stop_decision_indices vazio",
            id="empty-monitor",
        ),
        pytest.param(
            {"test_decision_indices": (16, 18)},
            "test_decision_indices deve ser uma faixa contígua",
            id="test-not-contiguous",
        ),
    ],
)
def test_structure_rejects_each_guard_with_its_message(
    override: dict[str, object], fragment: str
) -> None:
    with pytest.raises(ValueError, match=r"\(C4\)") as raised:
        _structure(**override)
    assert fragment in str(raised.value)


# -- resolve_panel_geometry (C3) --------------------------------------------------


def _geometry(**overrides: object) -> PanelGeometry:
    kwargs: dict[str, object] = {
        "encoder_length": 5,
        "feature_names": _FEATURES,
        "known_feature_names": ("b",),
        "rows": _ROWS,
        "target": _TARGET,
        "train_decision_indices": tuple(range(10)),
        "early_stop_decision_indices": (12, 13),
        "test_decision_indices": (16, 17),
        "max_horizon": 2,
        "horizons": (1, 2),
    }
    kwargs.update(overrides)
    return resolve_panel_geometry(**kwargs)  # type: ignore[arg-type]


def test_geometry_returns_panel_size_and_eligible_ranges() -> None:
    geometry = _geometry()
    assert geometry == PanelGeometry(
        panel_size=_PANEL, fitted_decisions=(4, 5, 6, 7, 8, 9), monitored_decisions=(12, 13)
    )


def test_geometry_raises_c3_when_no_train_decision_survives() -> None:
    with pytest.raises(ValueError, match=r"^nenhuma decisão de treino sobrou .* \(C3\)$"):
        _geometry(encoder_length=15)


def test_geometry_raises_c3_when_no_monitor_decision_survives() -> None:
    with pytest.raises(ValueError, match=r"^nenhuma decisão de monitor sobrou .* \(C3\)$"):
        _geometry(early_stop_decision_indices=(18, 19))


def test_geometry_validates_structure_before_eligibility() -> None:
    """Estrutura inválida ergue C4 mesmo quando a elegibilidade também falharia."""
    with pytest.raises(ValueError, match=r"\(C4\)"):
        _geometry(encoder_length=15, horizons=())
