"""Unit — DTOs do port `TftTrainer` (validação C2-params + imutabilidade).

Cobre o contrato do concept 5.4 §4/§6-C2 (parcela dos params): defaults
pré-registrados válidos, cada violação de faixa ergue `ValueError` nomeando o
campo, e os DTOs são frozen (identidade do run não muta após construída).
"""

import dataclasses

import pytest

from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
    TftTrainingResult,
)

pytestmark = pytest.mark.unit

_SEED = 42
# Contrato pré-registrado do concept §4 — o ponto de partida do candidato.
_EXPECTED_ENCODER_LENGTH = 60
_EXPECTED_HIDDEN_SIZE = 16
_EXPECTED_ATTENTION_HEAD_SIZE = 4
_EXPECTED_DROPOUT = 0.1
_EXPECTED_HIDDEN_CONTINUOUS_SIZE = 8
_EXPECTED_LEARNING_RATE = 0.03
_EXPECTED_MAX_EPOCHS = 50
_EXPECTED_PATIENCE = 8
_EXPECTED_BATCH_SIZE = 64


class TestTftTrainingParamsDefaults:
    def test_defaults_are_the_preregistered_contract(self) -> None:
        """Defaults do concept §4 — congelados pela 5.5 no cohort confirmatório."""
        params = TftTrainingParams(seed=_SEED)

        assert params.seed == _SEED
        assert params.max_encoder_length == _EXPECTED_ENCODER_LENGTH
        assert params.hidden_size == _EXPECTED_HIDDEN_SIZE
        assert params.attention_head_size == _EXPECTED_ATTENTION_HEAD_SIZE
        assert params.dropout == _EXPECTED_DROPOUT
        assert params.hidden_continuous_size == _EXPECTED_HIDDEN_CONTINUOUS_SIZE
        assert params.learning_rate == _EXPECTED_LEARNING_RATE
        assert params.max_epochs == _EXPECTED_MAX_EPOCHS
        assert params.patience == _EXPECTED_PATIENCE
        assert params.batch_size == _EXPECTED_BATCH_SIZE

    def test_params_are_frozen(self) -> None:
        params = TftTrainingParams(seed=_SEED)

        with pytest.raises(dataclasses.FrozenInstanceError):
            params.seed = 7  # type: ignore[misc]

    def test_dropout_zero_is_valid(self) -> None:
        """Fronteira inclusiva: sem dropout é configuração legítima."""
        assert TftTrainingParams(seed=_SEED, dropout=0.0).dropout == 0.0


class TestTftTrainingParamsValidation:
    """C2-params: cada violação ergue `ValueError` NOMEANDO o campo.

    A mensagem nomear o campo não é cosmético: é o que faz a varredura
    exploratória (que monta params a partir de valores amostrados) apontar qual
    dimensão saiu da faixa, em vez de um erro opaco.
    """

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("max_encoder_length", 0),
            ("hidden_size", 0),
            ("attention_head_size", 0),
            ("hidden_continuous_size", 0),
            ("max_epochs", 0),
            ("patience", 0),
            ("batch_size", 0),
        ],
    )
    def test_positive_integer_fields_reject_below_one(self, field: str, value: int) -> None:
        with pytest.raises(ValueError, match=field):
            TftTrainingParams(seed=_SEED, **{field: value})

    @pytest.mark.parametrize("dropout", [-0.1, 1.0, 1.5])
    def test_dropout_outside_unit_interval_rejected(self, dropout: float) -> None:
        with pytest.raises(ValueError, match="dropout"):
            TftTrainingParams(seed=_SEED, dropout=dropout)

    @pytest.mark.parametrize("learning_rate", [0.0, -0.01])
    def test_non_positive_learning_rate_rejected(self, learning_rate: float) -> None:
        with pytest.raises(ValueError, match="learning_rate"):
            TftTrainingParams(seed=_SEED, learning_rate=learning_rate)


class TestTftTrainingResult:
    def test_result_is_frozen(self) -> None:
        result = TftTrainingResult(
            grids={},
            best_epoch=0,
            best_val_loss=1.0,
            val_loss_by_epoch=(1.0,),
            fitted_decision_count=1,
            monitored_decision_count=1,
            normalizer_center=0.0,
            normalizer_scale=1.0,
            artifact_path="",
        )

        with pytest.raises(dataclasses.FrozenInstanceError):
            result.best_epoch = 3  # type: ignore[misc]
