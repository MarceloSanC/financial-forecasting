"""Fake in-memory do port `TftCheckpointPredictor` (Stage 7.1).

Cada checkpoint é registrado por caminho com o sha256 esperado dos seus bytes e
as entradas que ele declara (reais conhecidas/desconhecidas, `max_horizon`,
níveis); as grades podem ser configuradas por decisão (`grids`) — as demais
saem de uma regra sintética determinística da decisão, do horizonte e do nível.
A ordem das conferências é a do adapter real: sha256 (C10) antes de "carregar",
depois entradas declaradas (C4), depois a faixa de decisões contígua e crescente;
a emissão segue a regra I16 da cauda (`t + h <= len(target) - 1`) só nos pares
pedidos. Registra cada chamada em `calls`. Paridade pelo contrato `[fake, real]`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from financial_forecasting.features.modeling.application.ports.out.baseline_forecaster import (
    GridByHorizon,
)
from financial_forecasting.features.modeling.application.ports.out.tft_checkpoint_predictor import (
    ArtifactChangedError,
    CheckpointMismatchError,
    TftCheckpointPrediction,
)


@dataclass(frozen=True)
class FakeCheckpoint:
    """O que um checkpoint registrado declara e devolve."""

    sha256: str
    feature_names: tuple[str, ...]
    known_feature_names: tuple[str, ...]
    max_horizon: int
    quantile_levels: tuple[float, ...]
    grids: Mapping[int, GridByHorizon] = field(default_factory=dict)
    normalizer_center: float = 0.0
    normalizer_scale: float = 1.0


class InMemoryTftCheckpointPredictor:
    """Predição sintética a partir de checkpoints registrados por caminho."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, FakeCheckpoint] = {}
        self.calls: list[dict[str, Any]] = []

    def register(self, path: str, checkpoint: FakeCheckpoint) -> None:
        """Registra (ou substitui) o checkpoint gravado em `path`."""
        self._checkpoints[path] = checkpoint

    def predict_from_checkpoint(  # noqa: PLR0913 — espelha a assinatura do port
        self,
        *,
        checkpoint_path: str,
        expected_sha256: str,
        feature_names: Sequence[str],
        known_feature_names: Sequence[str],
        rows: Sequence[Sequence[float]],
        target: Sequence[float],
        decision_indices: Sequence[int],
        max_horizon: int,
        horizons: Sequence[int],
        quantile_levels: Sequence[float],
        batch_size: int,
        num_threads: int,
    ) -> TftCheckpointPrediction:
        self.calls.append(
            {
                "checkpoint_path": checkpoint_path,
                "expected_sha256": expected_sha256,
                "feature_names": tuple(feature_names),
                "known_feature_names": tuple(known_feature_names),
                "rows": len(rows),
                "target": len(target),
                "decision_indices": tuple(decision_indices),
                "max_horizon": max_horizon,
                "horizons": tuple(horizons),
                "quantile_levels": tuple(quantile_levels),
                "batch_size": batch_size,
                "num_threads": num_threads,
            }
        )
        if checkpoint_path not in self._checkpoints:
            raise FileNotFoundError(checkpoint_path)
        checkpoint = self._checkpoints[checkpoint_path]
        if checkpoint.sha256 != expected_sha256:
            raise ArtifactChangedError(
                f"checkpoint {checkpoint_path} sha256 {checkpoint.sha256[:12]} != expected "
                f"{expected_sha256[:12]} — not loaded (C10)"
            )
        _check_declared(
            checkpoint, feature_names, known_feature_names, max_horizon, quantile_levels
        )
        decisions = tuple(decision_indices)
        if any(b != a + 1 for a, b in pairwise(decisions)):
            raise ValueError(f"decision indices must be contiguous and increasing: {decisions!r}")
        last = len(target) - 1
        grids: dict[int, GridByHorizon] = {}
        for decision in decisions:
            emitted = {
                h: self._grid(checkpoint, decision, h, quantile_levels)
                for h in horizons
                if decision + h <= last
            }
            if emitted:
                grids[decision] = emitted
        return TftCheckpointPrediction(
            grids=grids,
            normalizer_center=checkpoint.normalizer_center,
            normalizer_scale=checkpoint.normalizer_scale,
            settings={
                "batch_size": str(batch_size),
                "num_workers": "0",
                "accelerator": "cpu",
                "num_threads": str(num_threads),
                "deterministic_algorithms": "false",
                "cpu_capability": "fake",
                "platform": "fake-platform",
                "scikit-learn": "0",
            },
        )

    @staticmethod
    def _grid(
        checkpoint: FakeCheckpoint, decision: int, horizon: int, levels: Sequence[float]
    ) -> tuple[float, ...]:
        configured = checkpoint.grids.get(decision, {}).get(horizon)
        if configured is not None:
            return tuple(configured)
        return tuple(decision * 1e-3 + horizon * 1e-4 + (tau - 0.5) * 1e-2 for tau in levels)


def _check_declared(
    checkpoint: FakeCheckpoint,
    feature_names: Sequence[str],
    known_feature_names: Sequence[str],
    max_horizon: int,
    quantile_levels: Sequence[float],
) -> None:
    known = tuple(known_feature_names)
    unknown = tuple(name for name in feature_names if name not in known)
    declared_unknown = tuple(
        name for name in checkpoint.feature_names if name not in checkpoint.known_feature_names
    )
    mismatches = []
    if known != checkpoint.known_feature_names:
        mismatches.append("known reals")
    if unknown != declared_unknown:
        mismatches.append("unknown reals")
    if max_horizon != checkpoint.max_horizon:
        mismatches.append("max_prediction_length")
    if tuple(quantile_levels) != checkpoint.quantile_levels:
        mismatches.append("quantile levels")
    if mismatches:
        raise CheckpointMismatchError(
            f"checkpoint declares different {', '.join(mismatches)} than requested (C4)"
        )
