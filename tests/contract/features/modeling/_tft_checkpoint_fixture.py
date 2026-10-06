"""Checkpoint real minúsculo para a predição a partir do checkpoint (Stage 7.1, Task 04).

Treina UMA vez (o chamador decide o escopo; os módulos usam fixture de módulo
sobre `tmp_path_factory`) o TFT da geometria canônica do contract test do
trainer (`test_tft_trainer_contract.py`) e devolve o que a perna real do
contrato do `TftCheckpointPredictor` e o teste de integração precisam: caminho
e sha256 do checkpoint, as entradas do treino, as threads com que o treino
emitiu o teste e a grade de teste devolvida pelo `train_and_predict`.

`calib_decisions` é uma faixa entre o monitor e o teste da geometria
(`40..46`), com os dois horizontes cabendo no painel.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import torch

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
)
from tests.contract.features.modeling.test_tft_trainer_contract import (
    _EARLY_STOP,
    _FEATURES,
    _HORIZONS,
    _KNOWN,
    _LEVELS,
    _MAX_HORIZON,
    _PARAMS,
    _TEST,
    _TRAIN,
    _panel,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

CALIB_DECISIONS = tuple(range(40, 47))


@dataclass(frozen=True)
class TrainedCheckpoint:
    """Um checkpoint treinado de verdade e as entradas com que foi treinado."""

    path: str
    sha256: str
    feature_names: tuple[str, ...]
    known_feature_names: tuple[str, ...]
    rows: tuple[tuple[float, ...], ...]
    target: tuple[float, ...]
    max_horizon: int
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    batch_size: int
    num_threads: int
    test_decisions: tuple[int, ...]
    calib_decisions: tuple[int, ...]
    test_grids: Mapping[int, Mapping[int, tuple[float, ...]]]
    normalizer_center: float
    normalizer_scale: float


def train_tiny_checkpoint(directory: Path) -> TrainedCheckpoint:
    """Treina o TFT minúsculo em `directory` e devolve o checkpoint e a grade de teste."""
    rows, target = _panel()
    num_threads = torch.get_num_threads()
    result = PfTftTrainer().train_and_predict(
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
        quantile_levels=_LEVELS,
        artifact_dir=str(directory / "ckpt"),
    )
    sha256 = hashlib.sha256(Path(result.artifact_path).read_bytes()).hexdigest()
    return TrainedCheckpoint(
        path=result.artifact_path,
        sha256=sha256,
        feature_names=tuple(_FEATURES),
        known_feature_names=tuple(_KNOWN),
        rows=tuple(tuple(row) for row in rows),
        target=tuple(target),
        max_horizon=_MAX_HORIZON,
        horizons=tuple(_HORIZONS),
        quantile_levels=tuple(_LEVELS),
        batch_size=_PARAMS.batch_size,
        num_threads=num_threads,
        test_decisions=tuple(_TEST),
        calib_decisions=CALIB_DECISIONS,
        test_grids={d: dict(by_h) for d, by_h in result.grids.items()},
        normalizer_center=result.normalizer_center,
        normalizer_scale=result.normalizer_scale,
    )
