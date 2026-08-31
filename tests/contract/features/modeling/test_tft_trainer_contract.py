"""Contract test do port `TftTrainer` — paridade fake ↔ `PfTftTrainer`.

Um ÚNICO contrato parametrizado sobre `[fake, real]` prova a semântica
observável COMPARTILHADA (concept 5.4 §4; skill `pytest-with-fakes`):

- forma da grade: 1:1 com `quantile_levels`, por (decisão x horizonte emitido);
- **I16** — regra de emissão na cauda: o par sai sse `t + h` existe no painel;
- **I17** — contagens efetivas de decisões ajustadas e monitoradas;
- **C3/C4** — mesmos limiares, com o mesmo marcador na mensagem;
- **determinismo** — duas chamadas idênticas produzem a mesma grade;
- **fit-only** — grade e artefato vazios, nenhum arquivo escrito.

**Exclusivo da perna REAL, por construção** (declarado aqui para a auditoria não
ler como lacuna, na linha do finding herdado da Stage 5.3 sobre o C5):

- **C5** (emissão não finita): a emissão do fake é sempre finita;
- **C10** (checkpoint inutilizável): o fake sempre grava;
- **A4(c)** (normalizador ajustado no quadro de treino): o fake não tem um
  normalizador de biblioteca — ele reproduz a POPULAÇÃO, não a fórmula, e por
  isso `normalizer_scale` **não** é comparável entre as pernas (o fake usa
  desvio amostral puro; a real usa a fórmula da lib, com epsilon). O contrato
  compara `normalizer_center`, que é a média simples nos dois.

**Divergência conhecida e aceita:** o nome do arquivo de checkpoint difere
(`epoch=N.ckpt` no fake, `epoch=N-step=M.ckpt` no real). O contrato assere
EXISTÊNCIA, nunca o nome — o caminho é opaco para o chamador.
"""

from __future__ import annotations

import math
import statistics
from typing import TYPE_CHECKING, Any

import pytest

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainer,
    TftTrainingParams,
)
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.contract

# Geometria canônica do technical §1.
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
_TRAIN_FRAME_END = 32
_EXPECTED_FITTED = 19
_EXPECTED_MONITORED = 5
_EXPECTED_H1 = (49, 50, 51, 52)
_EXPECTED_H2 = (49, 50, 51)

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


@pytest.fixture(params=["fake", "real"])
def leg(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def trainer(leg: str) -> TftTrainer:
    """Parametriza o contrato sobre as duas implementações do port."""
    return InMemoryTftTrainer() if leg == "fake" else PfTftTrainer()


def _panel() -> tuple[list[list[float]], list[float]]:
    rows = [
        [0.01 * index, 50.0 + index, float(index % 5), float(index % 12 + 1)]
        for index in range(_PANEL)
    ]
    target = [0.001 * index for index in range(_PANEL)]
    return rows, target


def _call(trainer: TftTrainer, tmp_path: Path, **overrides: Any) -> Any:  # noqa: ANN401
    rows, target = _panel()
    kwargs: dict[str, Any] = {
        "params": _PARAMS,
        "feature_names": _FEATURES,
        "known_feature_names": _KNOWN,
        "rows": rows,
        "target": target,
        "train_decision_indices": _TRAIN,
        "early_stop_decision_indices": _EARLY_STOP,
        "test_decision_indices": _TEST,
        "max_horizon": _MAX_HORIZON,
        "horizons": _HORIZONS,
        "quantile_levels": _LEVELS,
        "artifact_dir": str(tmp_path / "ckpt"),
    }
    kwargs.update(overrides)
    return trainer.train_and_predict(**kwargs)


class TestEmissionShape:
    def test_grid_is_aligned_one_to_one_with_levels(
        self, trainer: TftTrainer, tmp_path: Path
    ) -> None:
        result = _call(trainer, tmp_path)

        assert result.grids
        for by_horizon in result.grids.values():
            for grid in by_horizon.values():
                assert len(grid) == len(_LEVELS)
                assert all(math.isfinite(value) for value in grid)

    def test_tail_rule_is_identical_in_both_legs(self, trainer: TftTrainer, tmp_path: Path) -> None:
        """I16 — é o que garante o mesmo conjunto de pontos alinhados de 5.2/5.3."""
        result = _call(trainer, tmp_path)
        shorter, longer = _HORIZONS

        emitted_short = tuple(sorted(t for t, by_h in result.grids.items() if shorter in by_h))
        emitted_long = tuple(sorted(t for t, by_h in result.grids.items() if longer in by_h))

        assert emitted_short == _EXPECTED_H1
        assert emitted_long == _EXPECTED_H2
        for decision, by_horizon in result.grids.items():
            for horizon in by_horizon:
                assert decision + horizon <= _LAST_INDEX

    def test_no_decision_outside_the_requested_range(
        self, trainer: TftTrainer, tmp_path: Path
    ) -> None:
        result = _call(trainer, tmp_path)

        assert set(result.grids) <= set(_TEST)


class TestDeclaredDiscard:
    def test_counts_match_the_canonical_arithmetic(
        self, trainer: TftTrainer, tmp_path: Path
    ) -> None:
        """I17 — o descarte por janela incompleta é declarado nas duas pernas."""
        result = _call(trainer, tmp_path)

        assert result.fitted_decision_count == _EXPECTED_FITTED
        assert result.monitored_decision_count == _EXPECTED_MONITORED


class TestStoppingContract:
    def test_best_epoch_is_the_argmin_of_the_reported_history(
        self, trainer: TftTrainer, tmp_path: Path
    ) -> None:
        result = _call(trainer, tmp_path)

        assert result.val_loss_by_epoch
        assert result.best_val_loss == min(result.val_loss_by_epoch)
        assert result.best_epoch == result.val_loss_by_epoch.index(result.best_val_loss)

    def test_artifact_exists_on_disk(self, trainer: TftTrainer, tmp_path: Path) -> None:
        """Só EXISTÊNCIA: o nome do arquivo é detalhe de cada implementação."""
        from pathlib import Path as _Path  # noqa: PLC0415

        result = _call(trainer, tmp_path)

        assert result.artifact_path
        assert _Path(result.artifact_path).is_file()


class TestNormalizerCenterIsShared:
    """A escala não é comparável entre as pernas; o centro é.

    O fake usa desvio amostral puro e a real a fórmula da lib (com epsilon), mas
    o CENTRO é a média simples do quadro de treino nos dois — e é ele que
    carrega a cláusula que importa de I4(b): qual população o normalizador viu.
    """

    def test_center_is_the_mean_of_the_training_frame(
        self, trainer: TftTrainer, tmp_path: Path
    ) -> None:
        _, target = _panel()
        result = _call(trainer, tmp_path)

        assert result.normalizer_center == pytest.approx(
            statistics.fmean(target[:_TRAIN_FRAME_END]), rel=1e-6
        )
        assert result.normalizer_scale > 0


class TestFitOnly:
    def test_empty_test_set_emits_nothing_and_writes_no_checkpoint(
        self, trainer: TftTrainer, tmp_path: Path
    ) -> None:
        result = _call(trainer, tmp_path, test_decision_indices=())

        assert result.grids == {}
        assert result.artifact_path == ""
        assert not (tmp_path / "ckpt").exists()
        assert result.val_loss_by_epoch


class TestDeterminism:
    def test_two_identical_calls_produce_the_same_grid(
        self, trainer: TftTrainer, tmp_path: Path
    ) -> None:
        first = _call(trainer, tmp_path / "a")
        second = _call(trainer, tmp_path / "b")

        assert first.grids == second.grids
        assert first.best_epoch == second.best_epoch


class TestInsufficientHistory:
    """C3 — mesmo limiar e mesmo marcador nas duas pernas."""

    def test_encoder_longer_than_train_block(self, trainer: TftTrainer, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="treino"):
            _call(
                trainer,
                tmp_path,
                params=TftTrainingParams(seed=7, max_encoder_length=40),
            )

    def test_monitor_without_full_decoder(self, trainer: TftTrainer, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="monitor"):
            _call(
                trainer,
                tmp_path,
                early_stop_decision_indices=(_PANEL - 2, _PANEL - 1),
            )


class TestStructuralErrors:
    """C4 — a mesma estrutura inválida ergue nas duas pernas.

    A paridade de MENSAGEM (não só de tipo) é o que impede o fake de aceitar o
    que o adapter real recusa: uma divergência aqui viraria teste verde com
    produção vermelha.
    """

    def test_row_width_mismatch(self, trainer: TftTrainer, tmp_path: Path) -> None:
        rows, _ = _panel()
        rows[3] = [1.0]
        with pytest.raises(ValueError, match="colunas"):
            _call(trainer, tmp_path, rows=rows)

    def test_target_length_mismatch(self, trainer: TftTrainer, tmp_path: Path) -> None:
        _, target = _panel()
        with pytest.raises(ValueError, match=r"len\(target\)"):
            _call(trainer, tmp_path, target=target[:-1])

    def test_known_names_not_contained(self, trainer: TftTrainer, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="known_feature_names"):
            _call(trainer, tmp_path, known_feature_names=("not_a_column",))

    def test_non_contiguous_decision_range(self, trainer: TftTrainer, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="contígua"):
            _call(trainer, tmp_path, train_decision_indices=(*range(20), 25))

    def test_index_outside_panel(self, trainer: TftTrainer, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="fora do painel"):
            _call(trainer, tmp_path, test_decision_indices=(_PANEL, _PANEL + 1))

    def test_horizon_outside_decoder(self, trainer: TftTrainer, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="horizons"):
            _call(trainer, tmp_path, horizons=(1, 7))

    def test_empty_horizons(self, trainer: TftTrainer, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="horizons"):
            _call(trainer, tmp_path, horizons=())

    def test_empty_monitor(self, trainer: TftTrainer, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="early_stop_decision_indices"):
            _call(trainer, tmp_path, early_stop_decision_indices=())


def test_both_legs_are_exercised(trainer: TftTrainer, leg: str) -> None:
    """Guarda anti-suite-de-uma-perna, agora com dente.

    A versão anterior assertava `isinstance(trainer, Fake | Real)` — satisfeita
    pelo fake nas DUAS parametrizações. Uma fixture que devolvesse sempre o fake
    apagaria a perna real (e com ela C5, C10 e A4c) sem reprovar nada. A
    asserção precisa amarrar o parâmetro ao tipo.
    """
    expected = PfTftTrainer if leg == "real" else InMemoryTftTrainer
    assert isinstance(trainer, expected)
