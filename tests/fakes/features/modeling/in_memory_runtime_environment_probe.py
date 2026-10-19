"""Fake do port `RuntimeEnvironmentProbe` (Stage 5.5): foto fixa e ajustável pelo teste.

Stage 7.3: `with_gpu(...)` monta a foto de um device fora do `cpu`, com as `GPU_KEYS`
configuráveis (o que o probe real observaria).
"""

from __future__ import annotations

from collections.abc import Mapping

from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
    GPU_KEYS,
    REQUIRED_KEYS,
)


class InMemoryRuntimeEnvironmentProbe:
    """Devolve uma foto com todas as chaves; `overrides` simula outro ambiente/código."""

    def __init__(self, **overrides: str) -> None:
        base = {key: f"fake-{key}" for key in REQUIRED_KEYS}
        base[DIRTY_KEY] = "false"
        base.update(overrides)
        self._snapshot = base

    @classmethod
    def with_gpu(
        cls,
        *,
        device: str = "rocm",
        available: str = "true",
        name: str = "fake-gpu",
        hip_version: str = "fake-hip",
        **overrides: str,
    ) -> InMemoryRuntimeEnvironmentProbe:
        """Foto de um device fora do `cpu`, com as chaves de GPU dadas."""
        available_key, name_key, hip_key = GPU_KEYS
        gpu = {available_key: available, name_key: name, hip_key: hip_version}
        return cls(**{"device": device, **gpu, **overrides})

    def snapshot(self) -> Mapping[str, str]:
        return dict(self._snapshot)
