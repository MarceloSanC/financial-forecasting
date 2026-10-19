"""Piloto de custo com o `PfTftTrainer` real minúsculo em CPU (Stage 7.3, Task 09; CA6, I9).

Treino real de 1 época sobre o dataset sintético de `test_train_tft.py`, em `tmp_path`:
o piloto não grava silver nem `dim_run`, e o artefato fica só no diretório do piloto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting.pf_tft_trainer import (  # noqa: E501
    PfTftTrainer,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.measure_ablation_cost import (
    MeasureAblationCost,
    MeasureAblationCostCommand,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar
from financial_forecasting.shared.domain.value_objects.trading_sessions import TradingSessions
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.unit.features.modeling.application.test_ablation_cohort_spec import (
    _spec as _ablation_spec,
)
from tests.unit.features.modeling.application.test_cohort_spec import _spec as _cohort_spec
from tests.unit.features.modeling.application.test_train_tft import (
    _SCOPE,
    _SESSIONS,
    _seeded_store,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _base() -> Any:  # noqa: ANN401
    return _cohort_spec(
        asset_id=_SCOPE.asset_id,
        horizons=(1, 2),
        quantile_levels=(0.1, 0.5, 0.9),
        geometry=CohortGeometry(n_folds=2, test_size=3, val_size=5, calib_size=5, embargo=1),
        tft_params=TftTrainingParams(
            seed=0,
            max_encoder_length=12,
            max_epochs=1,
            hidden_size=4,
            hidden_continuous_size=2,
            attention_head_size=1,
            batch_size=16,
        ),
    )


def test_pilot_on_a_tiny_real_trainer_writes_no_silver(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    pilot_dir = tmp_path / "pilot"
    use_case = MeasureAblationCost(
        store=_seeded_store(),
        splitter=WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=_SESSIONS))),
        trainer=PfTftTrainer(),
        probe=InMemoryRuntimeEnvironmentProbe(device="cpu", torch="2.13.0+cpu"),
        clock=SystemClock(),
        hasher=CanonicalJsonHasher(),
    )

    report = use_case(
        MeasureAblationCostCommand(spec=_ablation_spec(), base=_base(), pilot_dir=str(pilot_dir))
    )

    assert report.epochs_run == 1
    assert report.wall_seconds > 0
    assert report.ceiling_seconds[1] == pytest.approx(5 * 2 * 1 * 1 * report.seconds_per_epoch)
    assert not (data_root / "silver").exists()
    assert not (tmp_path / "artifacts").exists()
    written = [p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()]
    assert written
    assert all(path.parts[0] == "pilot" for path in written)
