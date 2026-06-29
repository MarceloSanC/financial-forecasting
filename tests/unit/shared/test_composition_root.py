"""Teste de wiring do composition root (Stages 1.5 + 2.1).

Exercita `wire_dependencies` com um `Settings` INJETADO (não o `lru_cache`
global, I6) cujo `mlflow_tracking_uri` aponta para um SQLite em `tmp_path` (D4)
e cujo `data_root` aponta para `tmp_path` (2.1 I9), e verifica que o contêiner
expõe os concretos certos atrás dos ports: `hasher: Hasher` =
`CanonicalJsonHasher`, `tracker: ExperimentTracker` = `MlflowTracker` e
`store: MedallionStore` = `ParquetMedallionStore` (A5/A7). Cobre o caminho real
de `wire_dependencies` — necessário para a cobertura ≥90% (composition_root fora
do omit).
"""

from pathlib import Path

import pytest

from financial_forecasting.composition_root import (
    ApplicationDependencies,
    wire_dependencies,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.adapters.out.mlflow.mlflow_tracker import MlflowTracker
from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings


@pytest.mark.unit
def test_wire_dependencies_with_injected_settings(tmp_path: Path) -> None:
    """A5/A7: wiring instancia os concretos a partir do Settings injetado."""
    settings = Settings(
        _env_file=None,
        mlflow_tracking_uri=f"sqlite:///{tmp_path}/mlruns.db",
        data_root=tmp_path,
    )

    deps = wire_dependencies(settings=settings)

    assert isinstance(deps, ApplicationDependencies)
    assert isinstance(deps.hasher, CanonicalJsonHasher)
    assert isinstance(deps.tracker, MlflowTracker)
    assert isinstance(deps.store, ParquetMedallionStore)


@pytest.mark.unit
def test_wire_dependencies_tracker_uses_settings_uri(tmp_path: Path) -> None:
    """I6: o tracker recebe o tracking_uri vindo do Settings injetado."""
    tracking_uri = f"sqlite:///{tmp_path}/mlruns.db"
    settings = Settings(_env_file=None, mlflow_tracking_uri=tracking_uri)

    deps = wire_dependencies(settings=settings)

    assert isinstance(deps.tracker, MlflowTracker)
    assert deps.tracker._tracking_uri == tracking_uri


@pytest.mark.unit
def test_wire_dependencies_store_uses_settings_data_root(tmp_path: Path) -> None:
    """A7/I9: o store recebe o `data_root` vindo do Settings injetado (não o global)."""
    settings = Settings(_env_file=None, data_root=tmp_path)

    deps = wire_dependencies(settings=settings)

    assert isinstance(deps.store, ParquetMedallionStore)
    assert deps.store._data_root == tmp_path
