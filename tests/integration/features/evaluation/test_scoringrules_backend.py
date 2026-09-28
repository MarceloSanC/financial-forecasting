"""Integration test do `ScoringrulesBackend`: o backend `numpy` é fixado em TODA chamada.

A suíte de contrato prova os valores; ela não prova que o backend foi passado — num
ambiente sem numba o default já é `numpy` e um adapter que esquecesse o `backend=`
passaria verde lá e mudaria de caminho de cálculo num ambiente com numba (doc de
domínio §11.3). Aqui as três funções da lib são embrulhadas por um espião que registra
os kwargs e delega à original.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from financial_forecasting.features.evaluation.adapters.out.scoring import (
    scoringrules_backend,
)
from financial_forecasting.features.evaluation.adapters.out.scoring.scoringrules_backend import (
    ScoringrulesBackend,
)

_FUNCTIONS = ("quantile_score", "crps_quantile", "interval_score")


@pytest.fixture
def recorded_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    """Espiona as três funções nativas da scoringrules usadas pelo adapter."""
    calls: dict[str, list[dict[str, Any]]] = {name: [] for name in _FUNCTIONS}
    library = scoringrules_backend.sr

    def spy(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 — espião genérico
            calls[name].append(kwargs)
            return original(*args, **kwargs)

        return wrapper

    for name in _FUNCTIONS:
        monkeypatch.setattr(library, name, spy(name, getattr(library, name)))
    return calls


@pytest.mark.integration
def test_every_scoringrules_call_pins_the_numpy_backend(
    recorded_calls: dict[str, list[dict[str, Any]]],
) -> None:
    backend = ScoringrulesBackend()

    backend.mean_pinball(realized=[0.01, -0.02], quantiles=[0.0, 0.0], level=0.1)
    backend.mean_crps_quantile(
        realized=[0.01, -0.02],
        quantile_grid=[(-0.01, 0.0, 0.01), (-0.02, 0.0, 0.02)],
        levels=(0.1, 0.5, 0.9),
    )
    backend.mean_interval_score(
        realized=[0.01, -0.02], lower=[-0.01, -0.01], upper=[0.01, 0.01], miscoverage=0.2
    )

    for name in _FUNCTIONS:
        assert len(recorded_calls[name]) == 1, name
        assert recorded_calls[name][0]["backend"] == "numpy", name
