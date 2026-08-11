"""Integração — datasets do `PfTftTrainer`: tipagem, recorte e normalizador.

Roda o `pytorch-forecasting` de verdade (sem `skipif` — ADR 5.4.0003). Prova:

- **mecânica (R3):** os três datasets se constroem, as colunas conhecidas e
  desconhecidas chegam onde deveriam, e o conjunto de amostras de treino tem
  exatamente `fitted_decision_count` entradas;
- **A4(c):** centro e escala do normalizador batem com a média e o desvio
  amostral do alvo sobre o **quadro de treino** — não sobre o painel inteiro,
  não sobre as decisões. A mutação que isso detecta é construir o dataset de
  treino a partir do painel completo;
- **A12 (parte):** as contagens efetivas de I17 batem com a aritmética da
  geometria canônica, e janela maior que o bloco de treino dispara C3;
- **C4:** estrutura inconsistente ergue, inclusive faixa não contígua.

Geometria canônica do technical §1: `train [0,30)`, gap, `early_stop [33,38)`,
gap, `calib [41,46)`, gap, `test [49,54)`, com `max_horizon=2`, `embargo=1`
(logo `gap=3`), `L=12` e painel de 54 sessões.
"""

from __future__ import annotations

import statistics

import pytest

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)

pytestmark = pytest.mark.integration

_PANEL = 54
_ENCODER_LENGTH = 12
_MAX_HORIZON = 2
_HORIZONS = (1, 2)
_TRAIN = tuple(range(30))
_EARLY_STOP = tuple(range(33, 38))
_TEST = tuple(range(49, 54))
_FEATURES = ("close_return", "rsi_14", "day_of_week", "month")
_KNOWN = ("day_of_week", "month")
# Quadro de treino: bloco `train` + as `max_horizon` sessões de purga que são
# os rótulos das últimas decisões de treino (I4b).
_TRAIN_FRAME_END = 32
_CALIB_START = 41
_EXPECTED_FITTED = 19  # t em [11, 29]
_EXPECTED_MONITORED = 5  # t em [33, 37]


def _panel() -> tuple[list[list[float]], list[float]]:
    rows = [
        [0.01 * index, 50.0 + index, float(index % 5), float(index % 12 + 1)]
        for index in range(_PANEL)
    ]
    target = [0.001 * index for index in range(_PANEL)]
    return rows, target


def _build(**overrides: object) -> object:
    rows, target = _panel()
    kwargs: dict[str, object] = {
        "params": TftTrainingParams(seed=7, max_encoder_length=_ENCODER_LENGTH),
        "feature_names": _FEATURES,
        "known_feature_names": _KNOWN,
        "rows": rows,
        "target": target,
        "train_decision_indices": _TRAIN,
        "early_stop_decision_indices": _EARLY_STOP,
        "test_decision_indices": _TEST,
        "max_horizon": _MAX_HORIZON,
        "horizons": _HORIZONS,
    }
    kwargs.update(overrides)
    return PfTftTrainer().build_datasets(**kwargs)  # type: ignore[arg-type]


class TestMechanics:
    """R3 — a API da biblioteca faz o que o plano assume."""

    def test_three_datasets_are_built(self) -> None:
        datasets = _build()

        assert datasets.training is not None
        assert datasets.monitor is not None
        assert datasets.prediction is not None

    def test_typing_reaches_the_dataset_as_declared(self) -> None:
        datasets = _build()
        parameters = datasets.training.get_parameters()

        assert set(_KNOWN) <= set(parameters["time_varying_known_reals"])
        assert "close_return" in parameters["time_varying_unknown_reals"]
        assert "rsi_14" in parameters["time_varying_unknown_reals"]
        # O alvo é entrada DESCONHECIDA (entra no codificador só até t).
        assert "target" in parameters["time_varying_unknown_reals"]
        for known in _KNOWN:
            assert known not in parameters["time_varying_unknown_reals"]

    def test_training_sample_count_matches_the_declared_discard(self) -> None:
        """I17 — o descarte por janela incompleta é DECLARADO, não silencioso."""
        datasets = _build()

        assert datasets.fitted_decision_count == _EXPECTED_FITTED
        assert datasets.monitored_decision_count == _EXPECTED_MONITORED
        assert len(datasets.training) == _EXPECTED_FITTED

    def test_monitor_frame_stops_before_calibration(self) -> None:
        """A4(a) estrutural: `calib` sequer existe no quadro do monitor."""
        datasets = _build()
        monitor_max_time = int(datasets.monitor.data["time"].max())

        assert monitor_max_time < _CALIB_START


def _normalizer_fitted_on(values: list[float]) -> tuple[float, float]:
    """Ajusta um normalizador igual ao do adapter sobre `values`.

    Compara a POPULAÇÃO, não a fórmula: qual conjunto de linhas o normalizador
    viu é a pergunta de A4(c); como a biblioteca calcula a escala é assunto
    dela. Refazer a conta à mão aqui tornaria o teste refém da fórmula interna e
    quebraria a cada release, sem ganho de garantia.
    """
    import pandas as pd  # noqa: PLC0415
    from pytorch_forecasting.data.encoders import GroupNormalizer  # noqa: PLC0415

    series = pd.Series(values)
    normalizer = GroupNormalizer(groups=[])
    normalizer.fit(series, pd.DataFrame({"target": series}))
    return float(normalizer.norm_["center"]), float(normalizer.norm_["scale"])


class TestNormalizer:
    """A4(c) — ajustado no QUADRO de treino (ADR 5.4.0006)."""

    def test_center_and_scale_come_from_the_training_frame(self) -> None:
        _, target = _panel()
        expected_center, expected_scale = _normalizer_fitted_on(target[:_TRAIN_FRAME_END])
        datasets = _build()

        assert datasets.normalizer_center == pytest.approx(expected_center, rel=1e-9)
        assert datasets.normalizer_scale == pytest.approx(expected_scale, rel=1e-9)
        # O centro é a média simples do quadro — âncora legível, independente da
        # fórmula de escala da biblioteca.
        assert datasets.normalizer_center == pytest.approx(
            statistics.fmean(target[:_TRAIN_FRAME_END]), rel=1e-9
        )

    def test_full_panel_would_change_the_parameters(self) -> None:
        """A mutação que A4(c) detecta: ajustar o normalizador no painel inteiro.

        Sem esta asserção, a de cima passaria também para um adapter que
        construísse o dataset de treino sobre o painel completo — que é
        exatamente o vazamento da cláusula 2 do ADR 5.4.0001.
        """
        _, target = _panel()
        panel_center, _ = _normalizer_fitted_on(target)
        datasets = _build()

        assert datasets.normalizer_center != pytest.approx(panel_center, rel=1e-6)

    def test_derived_datasets_inherit_the_fitted_normalizer(self) -> None:
        """Monitor e predição HERDAM — reajustar seria o vazamento da cláusula 2."""
        datasets = _build()

        training_params = datasets.training.target_normalizer.norm_
        monitor_params = datasets.monitor.target_normalizer.norm_
        prediction_params = datasets.prediction.target_normalizer.norm_

        assert monitor_params == training_params
        assert prediction_params == training_params


class TestStructuralValidation:
    def test_encoder_longer_than_train_block_raises(self) -> None:
        with pytest.raises(ValueError, match="treino"):
            _build(params=TftTrainingParams(seed=7, max_encoder_length=40))

    def test_non_contiguous_range_raises(self) -> None:
        with pytest.raises(ValueError, match="contígua"):
            _build(train_decision_indices=(*range(20), 25))

    def test_row_width_mismatch_raises(self) -> None:
        rows, _ = _panel()
        rows[3] = [1.0]
        with pytest.raises(ValueError, match="colunas"):
            _build(rows=rows)

    def test_known_names_not_contained_raises(self) -> None:
        with pytest.raises(ValueError, match="known_feature_names"):
            _build(known_feature_names=("not_a_column",))

    def test_horizon_outside_decoder_raises(self) -> None:
        with pytest.raises(ValueError, match="horizons"):
            _build(horizons=(1, 7))

    def test_empty_monitor_raises(self) -> None:
        with pytest.raises(ValueError, match="early_stop_decision_indices"):
            _build(early_stop_decision_indices=())
