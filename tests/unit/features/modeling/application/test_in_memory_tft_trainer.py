"""Unit — o fake do `TftTrainer` honra as regras do contrato sem `torch`.

Cobre o que o fake existe para materializar (concept 5.4 §4): regra de emissão
na cauda (I16), descarte declarado (I17), C3/C4, modo fit-only, determinismo
(I9) e o oráculo de alinhamento decisão↔horizonte na perna fake (A15).

Toda a geometria vem da **geometria canônica de fixture** do technical §1, cuja
aritmética os números abaixo replicam. Se algum número mudar, é a geometria que
mudou — não o teste que precisa ser "ajustado".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer

pytestmark = pytest.mark.unit

# Geometria canônica (technical §1): train [0,30) gap early_stop [33,38) gap
# calib [41,46) gap test [49,54), com gap = max_horizon + embargo = 3.
_PANEL = 54
_ENCODER_LENGTH = 12
_MAX_HORIZON = 2
_HORIZONS = (1, 2)
_TRAIN = tuple(range(30))
_EARLY_STOP = tuple(range(33, 38))
_TEST = tuple(range(49, 54))
_LEVELS = (0.1, 0.5, 0.9)
_MEDIAN_POSITION = 1

# Contagens derivadas da aritmética: janela completa exige t >= L-1 = 11, e
# decodificador completo exige t + 2 <= 53.
_EXPECTED_FITTED = 19  # t em [11, 29]
_EXPECTED_MONITORED = 5  # t em [33, 37]
# Cauda: h=1 emite t em [49,52] (4); h=2 emite t em [49,51] (3).
_EXPECTED_H1_DECISIONS = (49, 50, 51, 52)
_EXPECTED_H2_DECISIONS = (49, 50, 51)


def _target(index: int) -> float:
    """`g` injetiva e com passo grande — o oráculo de alinhamento depende disso."""
    return 100.0 + 10.0 * index


def _panel() -> tuple[list[list[float]], list[float]]:
    rows = [[float(index), float(index % 5)] for index in range(_PANEL)]
    target = [_target(index) for index in range(_PANEL)]
    return rows, target


def _call(
    trainer: InMemoryTftTrainer,
    tmp_path: Path,
    *,
    test_indices: tuple[int, ...] = _TEST,
    encoder_length: int = _ENCODER_LENGTH,
    train_indices: tuple[int, ...] = _TRAIN,
) -> object:
    rows, target = _panel()
    return trainer.train_and_predict(
        params=TftTrainingParams(seed=7, max_encoder_length=encoder_length, max_epochs=5),
        feature_names=("price_feature", "day_of_week"),
        known_feature_names=("day_of_week",),
        rows=rows,
        target=target,
        train_decision_indices=train_indices,
        early_stop_decision_indices=_EARLY_STOP,
        test_decision_indices=test_indices,
        max_horizon=_MAX_HORIZON,
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
        artifact_dir=str(tmp_path / "tft" / "run"),
    )


class TestEmissionRule:
    """I16 — o par (t, h) sai sse `t + h` existe no painel."""

    def test_tail_pairs_are_absent_not_fabricated(self, tmp_path: Path) -> None:
        result = _call(InMemoryTftTrainer(), tmp_path)

        first_horizon, second_horizon = _HORIZONS
        emitted_h1 = tuple(
            sorted(t for t, by_h in result.grids.items() if first_horizon in by_h)
        )
        emitted_h2 = tuple(
            sorted(t for t, by_h in result.grids.items() if second_horizon in by_h)
        )

        assert emitted_h1 == _EXPECTED_H1_DECISIONS
        assert emitted_h2 == _EXPECTED_H2_DECISIONS

    def test_grid_is_aligned_one_to_one_with_levels(self, tmp_path: Path) -> None:
        result = _call(InMemoryTftTrainer(), tmp_path)

        for by_horizon in result.grids.values():
            for grid in by_horizon.values():
                assert len(grid) == len(_LEVELS)


class TestDeclaredDiscard:
    """I17 — o descarte por janela/decodificador incompletos é reportado."""

    def test_counts_match_the_canonical_arithmetic(self, tmp_path: Path) -> None:
        result = _call(InMemoryTftTrainer(), tmp_path)

        assert result.fitted_decision_count == _EXPECTED_FITTED
        assert result.monitored_decision_count == _EXPECTED_MONITORED

    def test_encoder_longer_than_train_block_leaves_nothing_to_fit(
        self, tmp_path: Path
    ) -> None:
        """Janela maior que o bloco de treino zera as decisões elegíveis (C3)."""
        with pytest.raises(ValueError, match="treino"):
            _call(InMemoryTftTrainer(), tmp_path, encoder_length=40)

    def test_monitor_without_full_decoder_raises(self, tmp_path: Path) -> None:
        """C3 tem DOIS ramos; sob a geometria do splitter o do monitor nunca

        dispara, então ele só é alcançável por chamada direta. Sem este caso, a
        metade da regra ficaria sem cobertura nas duas pernas.
        """
        rows, target = _panel()
        with pytest.raises(ValueError, match="monitor"):
            InMemoryTftTrainer().train_and_predict(
                params=TftTrainingParams(seed=7, max_encoder_length=_ENCODER_LENGTH),
                feature_names=("a", "b"),
                known_feature_names=("b",),
                rows=rows,
                target=target,
                train_decision_indices=_TRAIN,
                # Cauda do painel: t + max_horizon > panel_size - 1 para ambas.
                early_stop_decision_indices=(_PANEL - 2, _PANEL - 1),
                test_decision_indices=(),
                max_horizon=_MAX_HORIZON,
                horizons=_HORIZONS,
                quantile_levels=_LEVELS,
                artifact_dir=str(tmp_path),
            )


class TestAlignmentOracle:
    """A15 (perna fake) — mediana emitida ancorada em `target[t + h]`."""

    @pytest.mark.parametrize("horizon", _HORIZONS)
    def test_median_is_closest_to_the_target_of_t_plus_h(
        self, tmp_path: Path, horizon: int
    ) -> None:
        result = _call(InMemoryTftTrainer(), tmp_path)
        decision = 49

        median = result.grids[decision][horizon][_MEDIAN_POSITION]
        distance_to_correct = abs(median - _target(decision + horizon))
        distance_to_shifted_back = abs(median - _target(decision + horizon - 1))
        distance_to_shifted_forward = abs(median - _target(decision + horizon + 1))

        assert distance_to_correct < distance_to_shifted_back
        assert distance_to_correct < distance_to_shifted_forward


class TestFitOnlyMode:
    """Modo da varredura: nada emitido, nenhum arquivo escrito (ADR 5.4.0005)."""

    def test_empty_test_set_emits_nothing_and_writes_no_checkpoint(
        self, tmp_path: Path
    ) -> None:
        result = _call(InMemoryTftTrainer(), tmp_path, test_indices=())

        assert result.grids == {}
        assert result.artifact_path == ""
        assert not (tmp_path / "tft").exists()

    def test_validation_loss_is_still_reported(self, tmp_path: Path) -> None:
        result = _call(InMemoryTftTrainer(), tmp_path, test_indices=())

        assert result.val_loss_by_epoch
        assert result.best_val_loss == min(result.val_loss_by_epoch)


class TestStoppingMechanism:
    def test_best_epoch_is_the_argmin_and_is_interior(self, tmp_path: Path) -> None:
        """`best_epoch < len - 1` é o que torna "não restaurar" observável."""
        result = _call(InMemoryTftTrainer(), tmp_path)

        assert result.best_epoch == result.val_loss_by_epoch.index(
            min(result.val_loss_by_epoch)
        )
        assert result.best_epoch < len(result.val_loss_by_epoch) - 1


class TestArtifact:
    def test_checkpoint_exists_on_disk(self, tmp_path: Path) -> None:
        """O fake do tracker valida existência — devolver só a string reprovaria A8."""
        result = _call(InMemoryTftTrainer(), tmp_path)

        assert Path(result.artifact_path).is_file()


class TestDeterminism:
    """Ausência de estado, NÃO semeadura.

    O fake é função pura dos argumentos e não lê `params.seed` — a cláusula de I9
    que liga semente a saída é da perna real. O que este teste protege é o fake
    não ganhar estado interno (cache, contador) que o torne dependente da ordem
    de chamada e faça a suite de contrato divergir por artefato do dublê.
    """

    def test_two_identical_calls_produce_identical_output(self, tmp_path: Path) -> None:
        first = _call(InMemoryTftTrainer(), tmp_path)
        second = _call(InMemoryTftTrainer(), tmp_path)

        assert first.grids == second.grids
        assert first.best_epoch == second.best_epoch
        assert first.val_loss_by_epoch == second.val_loss_by_epoch


class TestStructuralValidation:
    """C4 — estrutura inconsistente ergue ANTES de qualquer simulação."""

    def test_row_width_mismatch(self, tmp_path: Path) -> None:
        rows, target = _panel()
        rows[3] = [1.0]
        with pytest.raises(ValueError, match="colunas"):
            InMemoryTftTrainer().train_and_predict(
                params=TftTrainingParams(seed=7, max_encoder_length=_ENCODER_LENGTH),
                feature_names=("a", "b"),
                known_feature_names=("b",),
                rows=rows,
                target=target,
                train_decision_indices=_TRAIN,
                early_stop_decision_indices=_EARLY_STOP,
                test_decision_indices=_TEST,
                max_horizon=_MAX_HORIZON,
                horizons=_HORIZONS,
                quantile_levels=_LEVELS,
                artifact_dir=str(tmp_path),
            )

    def test_target_length_mismatch(self, tmp_path: Path) -> None:
        rows, target = _panel()
        with pytest.raises(ValueError, match="len\\(target\\)"):
            InMemoryTftTrainer().train_and_predict(
                params=TftTrainingParams(seed=7, max_encoder_length=_ENCODER_LENGTH),
                feature_names=("a", "b"),
                known_feature_names=("b",),
                rows=rows,
                target=target[:-1],
                train_decision_indices=_TRAIN,
                early_stop_decision_indices=_EARLY_STOP,
                test_decision_indices=_TEST,
                max_horizon=_MAX_HORIZON,
                horizons=_HORIZONS,
                quantile_levels=_LEVELS,
                artifact_dir=str(tmp_path),
            )

    def test_known_names_not_contained_in_feature_names(self, tmp_path: Path) -> None:
        rows, target = _panel()
        with pytest.raises(ValueError, match="known_feature_names"):
            InMemoryTftTrainer().train_and_predict(
                params=TftTrainingParams(seed=7, max_encoder_length=_ENCODER_LENGTH),
                feature_names=("a", "b"),
                known_feature_names=("month",),
                rows=rows,
                target=target,
                train_decision_indices=_TRAIN,
                early_stop_decision_indices=_EARLY_STOP,
                test_decision_indices=_TEST,
                max_horizon=_MAX_HORIZON,
                horizons=_HORIZONS,
                quantile_levels=_LEVELS,
                artifact_dir=str(tmp_path),
            )

    def test_non_contiguous_decision_range(self, tmp_path: Path) -> None:
        """Faixa com buraco: o real não honraria, então o fake não pode aceitar."""
        with pytest.raises(ValueError, match="contígua"):
            _call(InMemoryTftTrainer(), tmp_path, train_indices=(*range(20), 25))

    def test_index_outside_panel(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="fora do painel"):
            _call(InMemoryTftTrainer(), tmp_path, test_indices=(_PANEL, _PANEL + 1))

    def test_horizon_outside_decoder(self, tmp_path: Path) -> None:
        rows, target = _panel()
        with pytest.raises(ValueError, match="horizons"):
            InMemoryTftTrainer().train_and_predict(
                params=TftTrainingParams(seed=7, max_encoder_length=_ENCODER_LENGTH),
                feature_names=("a", "b"),
                known_feature_names=("b",),
                rows=rows,
                target=target,
                train_decision_indices=_TRAIN,
                early_stop_decision_indices=_EARLY_STOP,
                test_decision_indices=_TEST,
                max_horizon=_MAX_HORIZON,
                horizons=(1, 7),
                quantile_levels=_LEVELS,
                artifact_dir=str(tmp_path),
            )

    def test_empty_monitor(self, tmp_path: Path) -> None:
        rows, target = _panel()
        with pytest.raises(ValueError, match="early_stop_decision_indices"):
            InMemoryTftTrainer().train_and_predict(
                params=TftTrainingParams(seed=7, max_encoder_length=_ENCODER_LENGTH),
                feature_names=("a", "b"),
                known_feature_names=("b",),
                rows=rows,
                target=target,
                train_decision_indices=_TRAIN,
                early_stop_decision_indices=(),
                test_decision_indices=_TEST,
                max_horizon=_MAX_HORIZON,
                horizons=_HORIZONS,
                quantile_levels=_LEVELS,
                artifact_dir=str(tmp_path),
            )


class TestCallRecording:
    def test_last_call_records_the_decision_ranges(self, tmp_path: Path) -> None:
        """`last_call` é o que sustenta as asserções estruturais de A6 e A10."""
        trainer = InMemoryTftTrainer()
        _call(trainer, tmp_path)

        assert trainer.call_count == 1
        assert trainer.last_call["train_decision_indices"] == _TRAIN
        assert trainer.last_call["early_stop_decision_indices"] == _EARLY_STOP
        assert trainer.last_call["test_decision_indices"] == _TEST
