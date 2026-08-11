"""Integração — emissão quantílica do `PfTftTrainer` (Task 09).

Fecha o adapter: `train_and_predict` completo, com a saída recortada pelo
comprimento real do decodificador. Prova:

- **A2:** grade completa por par emitido, alinhada 1:1 a `quantile_levels`;
- **A15 (perna real):** o passo `h` corresponde a `t + h` — verificado por
  caixa-branca sobre o índice devolvido pela predição, não por proximidade
  numérica (um modelo de 2 épocas não tem precisão para um oráculo de valor);
- **A13 (parte):** o conjunto de pares emitidos é exatamente
  `{(t, h) : t ∈ test, t + h <= 53}` na geometria canônica — 4 pares para h=1,
  3 para h=2. É a cauda que a regra I16 recorta;
- **A5 (fecho):** a predição é idêntica à de um modelo recarregado do
  `artifact_path` — a mutação "predizer com os pesos da última época" reprova;
- **A4(b):** mutar sessões dentro da janela da decisão `t=49` **altera** a
  grade dela. Sem este caso, a invariância de A4(a) passaria também para um
  modelo que ignora as entradas;
- **A9:** duas chamadas idênticas devolvem grades idênticas;
- **A2/I8:** exatamente **um** ajuste por chamada;
- **C5:** não finito em posição realmente prevista ergue — e o padding da cauda
  NÃO ergue (é o que o recorte protege).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting import (
    pf_tft_trainer as module,
)
from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
    _assert_finite,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)

pytestmark = pytest.mark.integration

_PANEL = 54
_LAST_INDEX = _PANEL - 1
_ENCODER_LENGTH = 12
_MAX_HORIZON = 2
_HORIZONS = (1, 2)
_TRAIN = tuple(range(30))
_EARLY_STOP = tuple(range(33, 38))
_TEST = tuple(range(49, 54))
_FEATURES = ("close_return", "rsi_14", "day_of_week", "month")
_KNOWN = ("day_of_week", "month")
_LEVELS = (0.1, 0.5, 0.9)
_FIRST_DECISION = 49
# Janela de `t=49` é [38, 49] e cobre `calib` [41, 46) — o alcance que a
# geometria canônica garante com folga (technical §1).
_IN_WINDOW_OF_FIRST_DECISION = (41, 42, 43)
_EXPECTED_H1 = (49, 50, 51, 52)
_EXPECTED_H2 = (49, 50, 51)
# Última decisão que só alcança h=1 (52 + 2 = 54 > 53).
_LAST_H1_ONLY_DECISION = 52

_PARAMS = TftTrainingParams(
    seed=7,
    max_encoder_length=_ENCODER_LENGTH,
    hidden_size=4,
    attention_head_size=1,
    hidden_continuous_size=2,
    max_epochs=2,
    patience=2,
    batch_size=8,
    learning_rate=0.01,
)


def _panel(mutated: tuple[int, ...] = ()) -> tuple[list[list[float]], list[float]]:
    rows = [
        [0.01 * index, 50.0 + index, float(index % 5), float(index % 12 + 1)]
        for index in range(_PANEL)
    ]
    target = [
        (5.0 if index in mutated else 0.0) + 0.001 * index for index in range(_PANEL)
    ]
    return rows, target


def _run(
    tmp_path: Path,
    *,
    mutated: tuple[int, ...] = (),
    test_indices: tuple[int, ...] = _TEST,
) -> Any:  # noqa: ANN401 — TftTrainingResult
    rows, target = _panel(mutated)
    return PfTftTrainer().train_and_predict(
        params=_PARAMS,
        feature_names=_FEATURES,
        known_feature_names=_KNOWN,
        rows=rows,
        target=target,
        train_decision_indices=_TRAIN,
        early_stop_decision_indices=_EARLY_STOP,
        test_decision_indices=test_indices,
        max_horizon=_MAX_HORIZON,
        horizons=_HORIZONS,
        quantile_levels=_LEVELS,
        artifact_dir=str(tmp_path / "ckpt"),
    )


class TestEmission:
    def test_grid_is_aligned_one_to_one_with_levels(self, tmp_path: Path) -> None:
        result = _run(tmp_path)

        assert result.grids
        for by_horizon in result.grids.values():
            for grid in by_horizon.values():
                assert len(grid) == len(_LEVELS)
                assert all(math.isfinite(value) for value in grid)

    def test_tail_rule_selects_exactly_the_available_pairs(self, tmp_path: Path) -> None:
        """A13/I16 — `t + h <= 53`, nada fabricado pelo padding da cauda."""
        result = _run(tmp_path)

        shorter, longer = _HORIZONS
        emitted_h1 = tuple(sorted(t for t, by_h in result.grids.items() if shorter in by_h))
        emitted_h2 = tuple(sorted(t for t, by_h in result.grids.items() if longer in by_h))

        assert emitted_h1 == _EXPECTED_H1
        assert emitted_h2 == _EXPECTED_H2
        # Redundância deliberada: a regra aritmética, não a lista literal.
        for decision, by_horizon in result.grids.items():
            for horizon in by_horizon:
                assert decision + horizon <= _LAST_INDEX

    def test_fit_only_emits_nothing(self, tmp_path: Path) -> None:
        result = _run(tmp_path, test_indices=())

        assert result.grids == {}
        assert result.artifact_path == ""
        assert result.val_loss_by_epoch


class TestAlignment:
    """A15 (perna real) — caixa-branca sobre o índice devolvido pela predição."""

    def test_decision_key_comes_from_the_returned_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A chave é `time_idx - 1`; deslocar em um passo muda o conjunto emitido.

        O `time_idx` do índice é o PRIMEIRO passo do decodificador, então a
        decisão é `time_idx - 1`. Este teste captura o índice real e prova que
        as chaves de `grids` são exatamente essa transformação — se alguém
        trocar por uma contagem paralela ou deslocar o offset, o conjunto muda.
        """
        captured: dict[str, Any] = {}
        original = module.PfTftTrainer._emit

        def _spy(**kwargs: Any) -> Any:  # noqa: ANN401
            prediction = kwargs["model"].predict(
                kwargs["prediction_dataset"],
                mode="quantiles",
                return_index=True,
                return_decoder_lengths=True,
                batch_size=kwargs["batch_size"],
                num_workers=0,
            )
            captured["time_idx"] = [int(v) for v in prediction.index["time_idx"]]
            captured["lengths"] = [int(v) for v in prediction.decoder_lengths]
            return original(**kwargs)

        monkeypatch.setattr(module.PfTftTrainer, "_emit", staticmethod(_spy))
        result = _run(tmp_path)

        expected_decisions = {time_idx - 1 for time_idx in captured["time_idx"]}
        # Decisões cujo decodificador real não cobre nenhum horizonte pedido
        # não entram; por isso `<=` e não igualdade estrita.
        assert set(result.grids) <= expected_decisions
        assert set(result.grids) == {
            time_idx - 1
            for time_idx, length in zip(captured["time_idx"], captured["lengths"], strict=True)
            if length >= min(_HORIZONS)
        }

    def test_longest_decoder_wins_when_a_decision_repeats(self, tmp_path: Path) -> None:
        """Com decodificador variável a lib gera janelas curtas repetidas.

        A decisão 49 aparece com comprimento 2 e com 1; fica a de comprimento 2,
        que é a geometria com que o modelo foi treinado. Se a curta vencesse,
        `h=2` sumiria para essa decisão.
        """
        result = _run(tmp_path)

        assert set(result.grids[_FIRST_DECISION]) == set(_HORIZONS)


class TestBestCheckpointIsUsed:
    def test_prediction_matches_a_model_reloaded_from_the_artifact(
        self, tmp_path: Path
    ) -> None:
        """A5 (fecho) — a mutação "predizer com a última época" reprova aqui."""
        from pytorch_forecasting import TemporalFusionTransformer  # noqa: PLC0415

        trainer = PfTftTrainer()
        rows, target = _panel()
        result = _run(tmp_path)

        datasets = trainer.build_datasets(
            params=_PARAMS,
            feature_names=_FEATURES,
            known_feature_names=_KNOWN,
            rows=rows,
            target=target,
            train_decision_indices=_TRAIN,
            early_stop_decision_indices=_EARLY_STOP,
            test_decision_indices=_TEST,
            max_horizon=_MAX_HORIZON,
            horizons=_HORIZONS,
        )
        reloaded = TemporalFusionTransformer.load_from_checkpoint(result.artifact_path)
        replayed = PfTftTrainer._emit(
            model=reloaded,
            prediction_dataset=datasets.prediction,
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
            batch_size=_PARAMS.batch_size,
        )

        assert replayed == result.grids


class TestContextIsNotVacuous:
    """A4(b) — a janela é REALMENTE lida; sem isto A4(a) passaria vazia."""

    def test_mutating_sessions_inside_the_window_changes_the_grid(
        self, tmp_path: Path
    ) -> None:
        baseline = _run(tmp_path / "a")
        mutated = _run(tmp_path / "b", mutated=_IN_WINDOW_OF_FIRST_DECISION)

        assert mutated.grids[_FIRST_DECISION] != baseline.grids[_FIRST_DECISION]


class TestDeterminism:
    def test_two_identical_runs_agree(self, tmp_path: Path) -> None:
        first = _run(tmp_path / "a")
        second = _run(tmp_path / "b")

        assert first.grids == second.grids
        assert first.best_epoch == second.best_epoch


class TestSingleFitPerCall:
    """A2, cláusula de I8 — um ajuste por chamada, nunca um por horizonte.

    Planejada para a Task 08 no technical; migrou para cá porque
    `train_and_predict` só existe agora (registrado como `[deviation]` na §7).
    """

    def test_exactly_one_fit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"count": 0}
        original = module.PfTftTrainer.fit

        def _counting(self: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            calls["count"] += 1
            return original(self, **kwargs)

        monkeypatch.setattr(module.PfTftTrainer, "fit", _counting)
        _run(tmp_path)

        assert calls["count"] == 1


class TestC5:
    """Finitude avaliada DEPOIS do recorte (o padding da cauda não ergue)."""

    def test_non_finite_value_raises(self) -> None:
        with pytest.raises(ValueError, match="C5"):
            _assert_finite((0.1, math.nan, 0.3), decision=49, horizon=1)

    def test_finite_values_pass(self) -> None:
        _assert_finite((0.1, 0.2, 0.3), decision=49, horizon=1)

    def test_padding_in_the_tail_does_not_raise(self, tmp_path: Path) -> None:
        """A decisão 52 só tem h=1; o passo 2 é padding e não pode disparar C5."""
        result = _run(tmp_path)

        shorter, _ = _HORIZONS
        assert set(result.grids[_LAST_H1_ONLY_DECISION]) == {shorter}
