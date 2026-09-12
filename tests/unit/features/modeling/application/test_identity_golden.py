"""Golden dos hashes de identidade (`run_id` / `config_signature`) dos 3 use cases.

Issue #65: a identidade do run vai mudar de propósito (sai `schema_version` da
chave, entra o `RunId.compute` canônico de 9 campos). Este módulo trava os
valores num cenário FIXO e autocontido para provar duas coisas, nesta ordem:

1. **Antes** — os valores que os payloads hand-rolled produzem HOJE (esta
   versão do arquivo). Qualquer mudança de identidade que não seja a da issue
   reprova aqui primeiro.
2. **Depois** — quando a issue trocar o caminho de hash, o golden é atualizado
   UMA vez, no mesmo commit da quebra, com o par antes/depois registrado no
   histórico (git blame deste arquivo é a trilha da descontinuidade).

O cenário NÃO reutiliza fixtures dos outros módulos de teste de propósito: um
golden que importa `_command()` de `test_train_tft.py` derivaria em silêncio
quando alguém ajustasse aquela fixture. Tudo o que entra no hash está declarado
aqui. Por consequência, o golden também reprova quando o `FeatureRegistry` muda
(a lista ordenada de features entra no payload) — isso é desejado: identidade
mudou, alguém precisa reconhecer.

Marcação de estado deste arquivo: **ANTES da #65** (payloads privados
`_run_payload`/`_config_payload`, `schema_version` dentro da chave).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from financial_forecasting.features.analytics_store.application.use_cases.persist_predictions import (  # noqa: E501
    PersistPredictions,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.application.use_cases.run_baselines import (
    RunBaselines,
    RunBaselinesCommand,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    TrainGbmQuantile,
    TrainGbmQuantileCommand,
    expected_feature_names,
)
from financial_forecasting.features.modeling.application.use_cases.train_tft import (
    TrainTft,
    TrainTftCommand,
    known_feature_names,
    unknown_feature_names,
)
from financial_forecasting.features.modeling.domain.services.walk_forward_splitter import (
    WalkForwardSplitter,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
    ScopeSpec,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.services.trading_calendar import TradingCalendar
from financial_forecasting.shared.domain.value_objects.trading_sessions import (
    TradingSessions,
)
from tests.fakes.features.analytics_store.in_memory_analytics_repository import (
    FakeAnalyticsRepository,
)
from tests.fakes.features.modeling.in_memory_baseline_forecaster import (
    FakeBaselineForecaster,
)
from tests.fakes.features.modeling.in_memory_quantile_model_trainer import (
    FakeQuantileModelTrainer,
)
from tests.fakes.features.modeling.in_memory_tft_trainer import InMemoryTftTrainer
from tests.fakes.shared.in_memory_experiment_tracker import FakeExperimentTracker
from tests.fakes.shared.in_memory_medallion_store import FakeMedallionStore

# -- cenário fixo (tudo o que entra no hash está aqui) ------------------------------

_FRIDAY = 4
_N_SESSIONS = 120
_START = date(2021, 1, 4)  # segunda-feira
_HORIZONS = (1, 2)
_LEVELS = (0.1, 0.5, 0.9)
_GEOMETRY: dict[str, int] = {
    "n_folds": 2,
    "test_size": 3,
    "val_size": 5,
    "calib_size": 5,
    "embargo": 1,
}
_SCHEMA_VERSION = 1
_SCOPE = ScopeSpec(
    asset_id="GOLD", feature_set_name="fs_golden", max_horizon=2, cohort_id="cohort-golden"
)
_HQ_WINDOW = 20
_GBM_PARAMS = GbmTrainingParams(seed=7, min_data_in_leaf=5)
_TFT_PARAMS = TftTrainingParams(seed=7, max_encoder_length=12, max_epochs=3)

# (model_version, fold) -> (run_id, config_signature) — valores observados.
IdentityTable = dict[tuple[str, str], tuple[str, str]]


class _FrozenClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)


def _sessions() -> tuple[date, ...]:
    days: list[date] = []
    current = _START
    while len(days) < _N_SESSIONS:
        if current.weekday() <= _FRIDAY:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _rows(feature_names: tuple[str, ...]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, day in enumerate(_sessions()):
        row: dict[str, object] = {
            "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
            "asset_id": _SCOPE.asset_id,
            "target_return": idx / 1000.0,
            "time_idx": idx,
            "fundamentals_effective_date": None,
        }
        for position, name in enumerate(feature_names):
            row[name] = float(idx) + (position + 1) / 100.0
        rows.append(row)
    return rows


def _store(feature_names: tuple[str, ...]) -> FakeMedallionStore:
    store = FakeMedallionStore()
    store.seed_read_only(
        layer="processed",
        table="dataset_tft",
        asset=_SCOPE.asset_id,
        rows=_rows(feature_names),
    )
    return store


def _splitter() -> WalkForwardSplitter:
    return WalkForwardSplitter(TradingCalendar(TradingSessions(sessions=_sessions())))


def _identity_table(repo: FakeAnalyticsRepository) -> IdentityTable:
    """Lê `dim_run` e indexa por (model_version, fold) -> (run_id, config_signature)."""
    table: IdentityTable = {}
    for row in repo.read(layer="silver", table="dim_run"):
        key = (str(row["model_version"]), str(row["fold"]))
        assert key not in table, f"dim_run deveria ter 1 linha por {key}"
        table[key] = (str(row["run_id"]), str(row["config_signature"]))
    return table


def capture_baselines() -> IdentityTable:
    """Roda `RunBaselines` no cenário fixo e devolve a tabela de identidade."""
    repo = FakeAnalyticsRepository(clock=_FrozenClock())
    use_case = RunBaselines(
        store=_store(()),
        splitter=_splitter(),
        forecaster=FakeBaselineForecaster(),
        persist_predictions=PersistPredictions(repository=repo),
        analytics_repository=repo,
        hasher=CanonicalJsonHasher(),
    )
    use_case(
        RunBaselinesCommand(
            scope=_SCOPE,
            specs=BaselineSpec.canonical_five(historical_quantiles_window=_HQ_WINDOW),
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
            schema_version=_SCHEMA_VERSION,
            **_GEOMETRY,
        )
    )
    return _identity_table(repo)


def capture_gbm() -> IdentityTable:
    """Roda `TrainGbmQuantile` no cenário fixo e devolve a tabela de identidade."""
    repo = FakeAnalyticsRepository(clock=_FrozenClock())
    use_case = TrainGbmQuantile(
        store=_store(expected_feature_names()),
        splitter=_splitter(),
        trainer=FakeQuantileModelTrainer(),
        persist_predictions=PersistPredictions(repository=repo),
        analytics_repository=repo,
        hasher=CanonicalJsonHasher(),
    )
    use_case(
        TrainGbmQuantileCommand(
            scope=_SCOPE,
            params=_GBM_PARAMS,
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
            schema_version=_SCHEMA_VERSION,
            **_GEOMETRY,
        )
    )
    return _identity_table(repo)


def capture_tft(artifacts_root: Path) -> IdentityTable:
    """Roda `TrainTft` no cenário fixo e devolve a tabela de identidade."""
    repo = FakeAnalyticsRepository(clock=_FrozenClock())
    use_case = TrainTft(
        store=_store(unknown_feature_names() + known_feature_names()),
        splitter=_splitter(),
        trainer=InMemoryTftTrainer(),
        persist_predictions=PersistPredictions(repository=repo),
        analytics_repository=repo,
        tracker=FakeExperimentTracker(),
        hasher=CanonicalJsonHasher(),
        artifacts_root=artifacts_root,
    )
    use_case(
        TrainTftCommand(
            scope=_SCOPE,
            params=_TFT_PARAMS,
            horizons=_HORIZONS,
            quantile_levels=_LEVELS,
            schema_version=_SCHEMA_VERSION,
            **_GEOMETRY,
        )
    )
    return _identity_table(repo)


# -- golden (ANTES da #65) ---------------------------------------------------------

GOLDEN_BASELINES: IdentityTable = {
    ("baseline_ar1", "0"): (
        "f1901941e6972c1c72f3f0803d5fa208c6452544e3f1cce02918f669b40cef64",
        "f72105a769215dc298b0104206981c29d39f00b9cc5d18883e8e7f892ec522d1",
    ),
    ("baseline_ar1", "1"): (
        "828026e82d6fc90e5d970b668328c9e372778abc315370f43cb5bc78bbe60d3c",
        "f72105a769215dc298b0104206981c29d39f00b9cc5d18883e8e7f892ec522d1",
    ),
    ("baseline_ewma_vol", "0"): (
        "1cc1dfa051a40b35ec1e4435a51a1712c1a3d9ad31a9d7eb5ee0573dd1c66638",
        "3a151691858644b9e4271e5489968ec5630c7febcb4721d40729f2f232b90004",
    ),
    ("baseline_ewma_vol", "1"): (
        "90e61e90bd145b4bfa40c9c1f99790d43f613792b5048c20a81f783dfe3942f7",
        "3a151691858644b9e4271e5489968ec5630c7febcb4721d40729f2f232b90004",
    ),
    ("baseline_historical_mean", "0"): (
        "df6862613c501b9ade0c6d392898ccc659fe6d8e5017a1eae649344ff2b645dc",
        "663ddf9702f244f6fedcf2aade9c5efff3ed7e9ab9c114d15efb2b627bdb2621",
    ),
    ("baseline_historical_mean", "1"): (
        "d560009005b115c8181e7efb7fabceee0912fb12b2d05623eddbcf4ed116d409",
        "663ddf9702f244f6fedcf2aade9c5efff3ed7e9ab9c114d15efb2b627bdb2621",
    ),
    ("baseline_historical_quantiles", "0"): (
        "e01c39d47516fa83f69bd5b39cfbb33068365bb0a0e6b7fedd71ee15581dad49",
        "550e595841f562200bef338964270783cd3b873bbc3041ec2b09b30f7ddbc674",
    ),
    ("baseline_historical_quantiles", "1"): (
        "b14c8e75fc41e39066269535906c57c1c17193cacfa7638aa57b946a625c4720",
        "550e595841f562200bef338964270783cd3b873bbc3041ec2b09b30f7ddbc674",
    ),
    ("baseline_zero_return", "0"): (
        "1d792ed14d0e4fc00c7cee621781bccc41cee293428c15c4558199d58ecf2064",
        "cc079349e073fa0529043128bc6fa7d4da8c3d4051cb83b8db3e863afdcf62b8",
    ),
    ("baseline_zero_return", "1"): (
        "b78d258821a75b8665e83061d15db744163e27ec2619b252162fdbc3487ae715",
        "cc079349e073fa0529043128bc6fa7d4da8c3d4051cb83b8db3e863afdcf62b8",
    ),
}

GOLDEN_GBM: IdentityTable = {
    ("gbm_quantile", "0"): (
        "c417ec9d7134cee3c1f8d51161498465200c76454c24b342148fa8146fefe338",
        "8c904fe80049741dde80fe26b5540947516ef044b724adce5ecace1a42017ce8",
    ),
    ("gbm_quantile", "1"): (
        "224a2562cf2700cbc3d41bee56bfa7ddece3b7d25680954a688e7549e23bdaf9",
        "8c904fe80049741dde80fe26b5540947516ef044b724adce5ecace1a42017ce8",
    ),
}

GOLDEN_TFT: IdentityTable = {
    ("tft_quantile", "0"): (
        "ffeb88ebdf2059a18d6cc983f5dac93e7fcdcbfd51f57029eafd052c5edea08b",
        "fc56cd97bcb30737acfb0ad276efeba4b27b39a884a5589a6dc21f0ff692d833",
    ),
    ("tft_quantile", "1"): (
        "324be906fa7651d78f361b711b64052839271851e778a7bb2d5096e6caa03244",
        "fc56cd97bcb30737acfb0ad276efeba4b27b39a884a5589a6dc21f0ff692d833",
    ),
}


@pytest.mark.unit
def test_baselines_identity_matches_golden() -> None:
    """`RunBaselines`: (spec x fold) -> (run_id, config_signature) travados."""
    assert capture_baselines() == GOLDEN_BASELINES


@pytest.mark.unit
def test_gbm_identity_matches_golden() -> None:
    """`TrainGbmQuantile`: fold -> (run_id, config_signature) travados."""
    assert capture_gbm() == GOLDEN_GBM


@pytest.mark.unit
def test_tft_identity_matches_golden(tmp_path: Path) -> None:
    """`TrainTft`: fold -> (run_id, config_signature) travados."""
    assert capture_tft(tmp_path / "artifacts") == GOLDEN_TFT
