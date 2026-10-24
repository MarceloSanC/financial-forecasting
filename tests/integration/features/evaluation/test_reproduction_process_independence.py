"""Reprodução em processo novo, com `PYTHONHASHSEED` diferentes (Stage 8.2, Task 07).

Pré-checagem do item (1) do diagnóstico pré-declarado (I5): a 8.1 rodou o refresh no mesmo
processo do `infer`; a reprodução roda em outro processo, com outro `PYTHONHASHSEED`. Mundo:
o `_judged_world` da 8.1 com o `.judged.toml` (como a Task 05); duas cópias do `data/` do
mundo **sem** `gold/`; em cada uma, um subprocesso (`sys.executable`, `cwd` = raiz do mundo,
`PYTHONHASHSEED=0` numa e `4242` noutra) importa o driver pelo caminho e chama `reproduce(...)`
com `deps = wire_dependencies(Settings(data_root=<cópia>, repo_root=<mundo>))` e foto
constante. Critérios A3b, A6 (completude sobre as colunas gravadas) e A4 (forma: nada de
`judged/` no descartável). Nenhum teste lê o cohort real.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_forecasting import cli
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import GOLD_SCHEMAS
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    AttemptPhase,
    result_layer_digest,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldPartition,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.dtos.reproduction_comparison import (
    REPRODUCTION_CLASSES,
)
from tests.integration.features.evaluation.test_build_confirmatory_scorecard import _ASSET
from tests.integration.features.evaluation.test_conformal_refresh_end_to_end import _COHORT
from tests.integration.features.evaluation.test_run_confirmatory_evaluation import (
    _Judged,
    _judged_world,
    _record,
)
from tests.unit.features.evaluation._preregistration_payload import to_toml

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.xdist_group("reproduction_process_independence"),
]

_DRIVER = Path(__file__).resolve().parents[4] / "scripts" / "reproduce_judged_generation.py"
_PARTITION = GoldPartition(_ASSET, _COHORT)
_SEEDS = ("0", "4242")
_CHILD = """
import importlib.util, sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("reproduce_judged_generation", sys.argv[1])
driver = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = driver
spec.loader.exec_module(driver)

from financial_forecasting.composition_root import wire_dependencies
from financial_forecasting.features.evaluation.adapters.out.toml import (
    toml_preregistration_source,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings

data_root, world, name, ref = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5]
settings = Settings(
    _env_file=None,
    data_root=data_root,
    repo_root=world,
    artifacts_root=data_root.parent / "art",
    mlflow_tracking_uri=f"sqlite:///{data_root.parent}/mlruns.db",
)
sys.exit(
    driver.reproduce(
        deps=wire_dependencies(settings=settings),
        source=toml_preregistration_source.TomlPreregistrationSource(
            root=world / "config" / "preregistration"
        ),
        data_root=data_root,
        cohort=Path("config/cohorts/unused.toml"),
        name=name,
        revision=3,
        preregistration_ref=ref,
        snapshot=lambda: {"commit": "0" * 40},
        check=False,
        out=sys.stdout.buffer,
        err=sys.stderr,
    )
)
"""


@dataclass(frozen=True)
class _Reproduced:
    seed: str
    root: Path
    generation: GoldGeneration


@dataclass(frozen=True)
class _Scenario:
    judged: _Judged
    reproduced: tuple[_Reproduced, ...]


def _reproduce(judged: _Judged, base: Path, seed: str) -> _Reproduced:
    root = base / f"seed-{seed}" / "data"
    shutil.copytree(judged.root / "data", root, ignore=shutil.ignore_patterns("gold"))
    assert not (root / "gold").exists()
    env = {**os.environ, "PYTHONHASHSEED": seed}
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            _CHILD,
            str(_DRIVER),
            str(root),
            str(judged.root),
            judged.name,
            judged.reference,
        ],
        cwd=judged.root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"refresh {RefreshStatus.COMPLETED.value} tables {len(GOLD_SCHEMAS)}" in done.stdout
    generation = ParquetGoldStore(root).read_generation(partition=_PARTITION)
    return _Reproduced(seed, root, generation)


@pytest.fixture(scope="module")
def scenario(tmp_path_factory: pytest.TempPathFactory) -> _Scenario:
    judged = _judged_world(tmp_path_factory.mktemp("independence-judged"))
    path = judged.root / "config" / "preregistration" / f"{judged.name}-r3.judged.toml"
    path.write_text(to_toml(_record(judged, judged.first.generation_digest)), encoding="utf-8")
    base = tmp_path_factory.mktemp("independence-reproduced")
    return _Scenario(judged, tuple(_reproduce(judged, base, seed) for seed in _SEEDS))


def _judged_result_digest(judged: _Judged) -> str:
    digests = [
        attempt.result_digest
        for attempt in judged.store.attempts(partition=_PARTITION)
        if attempt.phase is AttemptPhase.INPUT_READ and attempt.result_digest is not None
    ]
    assert len(digests) == 1
    return digests[0]


def test_reproduced_result_digest_is_independent_of_hash_seed(scenario: _Scenario) -> None:
    expected = _judged_result_digest(scenario.judged)

    digests = {item.seed: result_layer_digest(item.generation) for item in scenario.reproduced}

    assert digests == dict.fromkeys(_SEEDS, expected)


def test_audit_reproduction_is_bit_identical_for_both_copies(scenario: _Scenario) -> None:
    judged = scenario.judged
    for item in scenario.reproduced:
        out, err = io.StringIO(), io.StringIO()

        code = cli.main(
            [
                "audit-reproduction",
                "--judged-data-root",
                str(judged.root / "data"),
                "--reproduced-data-root",
                str(item.root),
                "--preregistration",
                judged.name,
                "--revision",
                "3",
                "--preregistration-ref",
                judged.reference,
            ],
            wiring=cli.CliWiring(settings_overrides={"_env_file": None, "repo_root": judged.root}),
            out=out,
            err=err,
        )

        assert code == 0, (item.seed, out.getvalue(), err.getvalue())
        assert " bit_identical true " in out.getvalue().splitlines()[0]


def test_every_stored_column_has_a_declared_class(scenario: _Scenario) -> None:
    generation = scenario.reproduced[0].generation
    assert generation.manifest.status is RefreshStatus.COMPLETED
    assert set(generation.tables) == set(GOLD_SCHEMAS)
    empty = sorted(name for name, table in generation.tables.items() if not table.rows)

    undeclared = {
        name: sorted(set(table.columns) - set(REPRODUCTION_CLASSES[name]))
        for name, table in generation.tables.items()
        if table.rows
    }

    assert not any(undeclared.values()), (
        f"stored columns without a class: {undeclared}; empty tables (not covered): {empty}"
    )


def test_reproduced_root_has_no_judged_dir_nor_attempts(scenario: _Scenario) -> None:
    for item in scenario.reproduced:
        found = sorted(
            path.relative_to(item.root).as_posix()
            for path in item.root.rglob("*")
            if path.name in {"judged", "ATTEMPTS.jsonl"}
        )
        assert found == [], (item.seed, found)
        assert sorted(p.name for p in (item.root / "reproduction").iterdir()) == [
            "environment.json",
            "scorecard.json",
        ]
