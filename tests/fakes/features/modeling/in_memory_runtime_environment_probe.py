"""Fake do port `RuntimeEnvironmentProbe` (Stage 5.5): foto fixa e ajustável pelo teste."""

from __future__ import annotations

from collections.abc import Mapping

from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
    REQUIRED_KEYS,
)


class InMemoryRuntimeEnvironmentProbe:
    """Devolve uma foto com todas as chaves; `overrides` simula outro ambiente/código."""

    def __init__(self, **overrides: str) -> None:
        base = {key: f"fake-{key}" for key in REQUIRED_KEYS}
        base[DIRTY_KEY] = "false"
        base.update(overrides)
        self._snapshot = base

    def snapshot(self) -> Mapping[str, str]:
        return dict(self._snapshot)
