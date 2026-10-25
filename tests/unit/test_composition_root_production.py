"""Fábricas da Stage 8.4 na composition root (Task 04 / CA5, I5).

`wire_dependencies` real em `tmp_path` (proxies lazy: nada de torch) com uma fábrica de
probe espiã. Prova: só o runner de `production_cohort_for` herda hiperparâmetros; o
probe da fábrica de produção recebe o caminho do modelo versionado (é ele que ancora a
árvore limpa); e `writer_lock_for(raiz)` trava `<raiz>/.writer.lock`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from financial_forecasting.composition_root import wire_dependencies
from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (
    CohortRunLockedError,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)


@pytest.fixture
def wired(tmp_path: Path) -> tuple[object, list[tuple[Path, str]]]:
    probes: list[tuple[Path, str]] = []

    def probe_for(path: Path, device: str) -> InMemoryRuntimeEnvironmentProbe:
        probes.append((path, device))
        return InMemoryRuntimeEnvironmentProbe()

    deps = wire_dependencies(
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            data_root=tmp_path / "data",
            artifacts_root=tmp_path / "artifacts",
            repo_root=tmp_path,
            mlflow_tracking_uri=f"sqlite:///{tmp_path / 'mlruns.db'}",
        ),
        runtime_probe_factory=probe_for,
    )
    return deps, probes


def test_only_the_production_factory_inherits_hyperparameters(
    wired: tuple[object, list[tuple[Path, str]]], tmp_path: Path
) -> None:
    deps, probes = wired
    template = tmp_path / "aapl_production.toml"

    confirmatory = deps.confirmatory_cohort_for(tmp_path / "c.toml", "cpu")  # type: ignore[attr-defined]
    production = deps.production_cohort_for(template, "cpu")  # type: ignore[attr-defined]

    assert confirmatory._inherited_hyperparameters is False
    assert production._inherited_hyperparameters is True
    assert probes == [(tmp_path / "c.toml", "cpu"), (template, "cpu")]


def test_writer_lock_for_locks_the_given_root(
    wired: tuple[object, list[tuple[Path, str]]], tmp_path: Path
) -> None:
    deps, _ = wired
    root = tmp_path / "production"
    first = deps.writer_lock_for(root)  # type: ignore[attr-defined]
    second = deps.writer_lock_for(root)  # type: ignore[attr-defined]

    first.acquire_writer()
    try:
        assert (root / ".writer.lock").is_file()
        with pytest.raises(CohortRunLockedError):
            second.acquire_writer()
    finally:
        first.release_writer()
    assert not (root / ".writer.lock").exists()
    assert sorted(p.name for p in root.iterdir()) == []
