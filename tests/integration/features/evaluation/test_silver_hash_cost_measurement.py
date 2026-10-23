"""Gate de custo do hash do silver em escala sintética (Stage 8.1 Task 17; A17, D11).

Fora do `check-block`, do `make check` e da CI: só roda com `MEASURE_SILVER_HASH_COST=1`
(precedente `test_profile_cost_measurement.py`). Grava, num `data_root` temporário e
pelo `ParquetAnalyticsRepository` real, um silver **sintético** com a forma e as
contagens do cohort (concept 8.1 §3; nenhum dado real, cegamento I12):

- confirmatório: 10 seeds do candidato, o GBM e os 5 baselines x 6 folds (96 runs),
  251 decisões de teste por fold, h ∈ {1, 7}, a grade de 7 níveis, e o calib do
  candidato (252 decisões por fold): ≈ 549 mil linhas de `fact_oos_predictions`;
- ablação: 5 configurações x 10 seeds x 6 folds (300 runs): ≈ 1,05 M linhas;
- atribuição: 41 rótulos (a identidade e 4 famílias x K_p = 10) por run do candidato,
  ≈ 8,6 M linhas de `fact_permuted_predictions` em 60 partições, e a VSN de 59
  variáveis por decisão, ≈ 889 mil linhas de `fact_vsn_weights`.

As grades são as do e2e conformal da 7.2 (não degeneradas, o refresh sai `COMPLETED` e lê
as tabelas de H3), e o plano é a r3 sintética com `[conformal]` e `[h3]`. Duas pernas,
cada uma num subprocesso, sobre o MESMO silver e o `RefreshGold` do composition root:
hash ligado e hash desligado (`SilverContentHash.of_unit`/`combine` trocados por uma
constante só no subprocesso da perna). Mede o tempo por etapa (linhas `step=` do
`_timed`), o tempo total e o pico do processo (`VmHWM`). Asserções do D11, fixadas
antes da medição: pico da perna ligada ≤ 6 GiB e (tempo ligado - tempo desligado) ≤
30 min. A saída bruta vai à §7 do technical.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from financial_forecasting.composition_root import ApplicationDependencies, wire_dependencies
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
    LOCO_REFERENCE_MODEL,
    loco_model_of,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
    modeling_columns,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.integration.features.evaluation.test_build_confirmatory_scorecard import (
    _center,
    _deviation,
    _plan_payload,
)
from tests.integration.features.evaluation.test_conformal_refresh_end_to_end import _grids
from tests.integration.features.evaluation.test_h3_refresh_end_to_end import _SUSTAINED
from tests.unit.features.evaluation._conformal_parameters import conformal_block
from tests.unit.features.evaluation._h3_parameters import SYNTHETIC_PARTITION, h3_block
from tests.unit.features.evaluation._preregistration_payload import (
    R1_AMENDMENT,
    R2_AMENDMENT,
    R3_AMENDMENT,
    with_leaf,
)
from tests.unit.features.evaluation._profile_parameters import profile_block

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("MEASURE_SILVER_HASH_COST") != "1",
        reason="medição opt-in: MEASURE_SILVER_HASH_COST=1",
    ),
]

_ASSET = "AAPL"
_SILVER = "silver"
_COHORT = "cost-cohort-r0-000000000000"
_ABLATION = "cost-ablation-r0-000000000000"
_FS = "fs_all"
_ABLATION_FS = "fs_all_ablation"
_HORIZONS = (1, 7)
_FOLDS = tuple(str(k) for k in range(6))
# Forma do cohort (concept §3). `SILVER_COST_SEEDS`/`SILVER_COST_TEST_PER_FOLD` só encolhem
# a geometria para um ensaio rápido do próprio teste; a medição do A17 usa os padrões.
_TEST_PER_FOLD = int(os.environ.get("SILVER_COST_TEST_PER_FOLD", "251"))
_CALIB_LEN = 252
_SEEDS = tuple(range(1, int(os.environ.get("SILVER_COST_SEEDS", "10")) + 1))
_K_P = 10
_VARIABLES_TOTAL = 59
_WARMUP = 5
_TEST_FIRST = _CALIB_LEN + max(_HORIZONS)
_N_SESSIONS = _TEST_FIRST + len(_FOLDS) * _TEST_PER_FOLD + max(_HORIZONS) + 1
_EPOCH = datetime(2019, 1, 2, tzinfo=UTC)
_GIB = 1024**3
_PEAK_CEILING = 6 * _GIB  # D11
_TIME_BUDGET_S = 30 * 60  # D11: acréscimo do hash
_STEP = re.compile(r"step=(\S+) duration_s=([0-9.]+)")


def _session(index: int) -> str:
    return (_EPOCH + timedelta(days=index)).isoformat()


def _fold_of(decision: int) -> str:
    return str((decision - _TEST_FIRST) // _TEST_PER_FOLD)


def _test_points(fold: str, horizon: int) -> range:
    first = _TEST_FIRST + int(fold) * _TEST_PER_FOLD
    return range(first, min(first + _TEST_PER_FOLD, _N_SESSIONS - horizon))


def _calib_points(fold: str) -> range:
    first_test = _TEST_FIRST + int(fold) * _TEST_PER_FOLD
    return range(first_test - max(_HORIZONS) - _CALIB_LEN, first_test - max(_HORIZONS))


def _variables() -> dict[str, str]:
    named = {f: family for family, features in SYNTHETIC_PARTITION.items() for f in features}
    extra = {f"other_{i:02d}": "none" for i in range(_VARIABLES_TOTAL - len(named))}
    return {**named, **extra}


# --- dataset e plano ---------------------------------------------------------------------


def _write_dataset(data_root: Path) -> str:
    features = [name for name in modeling_columns() if name != "target_return"]
    stamps = [_EPOCH - timedelta(days=_WARMUP - i) for i in range(_WARMUP)]
    stamps += [_EPOCH + timedelta(days=i) for i in range(_N_SESSIONS)]
    returns = [0.0] * _WARMUP + [_center(t) + _deviation(t) for t in range(_N_SESSIONS)]
    rows: list[dict[str, object]] = []
    for i, (stamp, target) in enumerate(zip(stamps, returns, strict=True)):
        row: dict[str, object] = {"timestamp": stamp, "asset_id": _ASSET, "target_return": target}
        for j, name in enumerate(features):
            row[name] = math.nan if (i < _WARMUP and j == 0) else math.sin(i + 1.5 * j)
        rows.append(row)
    target_dir = data_root / "processed" / "dataset_tft" / _ASSET
    target_dir.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(target_dir / f"dataset_tft_{_ASSET}.parquet", index=False)
    grid = build_training_grid(rows, columns=modeling_columns())
    return grid_fingerprint(grid, hasher=CanonicalJsonHasher(), asset_id=_ASSET)


def _reference(payload: dict[str, object]) -> str:
    plan = Preregistration.from_mapping(payload)
    return plan.reference(
        PreregistrationHash.compute(hasher=CanonicalJsonHasher(), payload=plan.as_payload())
    )


def r3_payload(fingerprint: str) -> dict[str, object]:
    """A r3 sintética: r0 do cohort de custo + perfis (r1) + `[conformal]` + `[h3]`."""
    r0 = _plan_payload("cost_plan", _COHORT, fingerprint)
    for path, value in (
        ("horizons", list(_HORIZONS)),
        ("seeds.tft_quantile", list(_SEEDS)),
    ):
        r0 = with_leaf(r0, path, value)
    r1 = {**r0, **R1_AMENDMENT, "amends": _reference(r0), "profile_parameters": profile_block()}
    r2 = {**r1, **R2_AMENDMENT, "amends": _reference(r1), "conformal": conformal_block()}
    block: dict[str, Any] = copy.deepcopy(h3_block())
    block["k_p"] = _K_P
    block["ablation"]["seeds"] = list(_SEEDS)
    block["ablation"]["cohort_id"] = _ABLATION
    return {**r2, **R3_AMENDMENT, "amends": _reference(r2), "h3": block}


# --- silver ------------------------------------------------------------------------------


def _fact(  # noqa: PLR0913 — a linha longa do silver
    run_id: str,
    model: str,
    fs: str,
    split: str,
    h: int,
    d: int,
    level: float,
    raw: float,
    guardrail: float,
    *,
    applied: int = 0,
    year_of_decision: bool = False,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "model_version": model,
        "asset": _ASSET,
        "feature_set_name": fs,
        "split": split,
        "horizon": h,
        "decision_idx": d,
        "timestamp_utc": _session(d),
        "target_timestamp_utc": _session(d + h),
        "quantile_level": level,
        "value_raw": raw,
        "value_guardrail": guardrail,
        "guardrail_applied": applied,  # flag do PONTO: igual em todos os níveis
        "year": int(_session(d if year_of_decision else d + h)[:4]),
    }


def _dim(  # noqa: PLR0913 — as colunas do dim_run
    run_id: str, sweep: str, fs: str, model: str, seed: int | None, fold: str
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": _ASSET,
        "parent_sweep_id": sweep,
        "feature_set_name": fs,
        "config_signature": f"sig-{model}",
        "split_fingerprint": "split-cost",
        "fold": fold,
        "seed": seed,
        "model_version": model,
    }


def _write_confirmatory(deps: ApplicationDependencies, plan: Preregistration) -> int:
    repo, written = deps.analytics_repository, 0
    runs: list[dict[str, object]] = []
    for model in plan.models:
        spec = plan.seeds[model]
        for seed in [None] if spec.seeds is None else list(spec.seeds):
            for fold in _FOLDS:
                run_id = f"{_COHORT}-{model}-s{seed}-{fold}"
                runs.append(_dim(run_id, _COHORT, _FS, model, seed, fold))
                facts: list[dict[str, object]] = []
                for h in _HORIZONS:
                    points = [("test", d) for d in _test_points(fold, h)]
                    if model == plan.candidate:
                        points += [("calib", d) for d in _calib_points(fold)]
                    for split, d in points:
                        raw, guardrail = _grids(plan, model, seed, h, d, split)
                        facts.extend(
                            _fact(
                                run_id,
                                model,
                                _FS,
                                split,
                                h,
                                d,
                                level,
                                r,
                                g,
                                applied=int(raw != guardrail),
                            )
                            for level, r, g in zip(
                                plan.quantile_levels, raw, guardrail, strict=True
                            )
                        )
                repo.write(layer=_SILVER, table="fact_oos_predictions", rows=facts)
                written += len(facts)
    repo.write(layer=_SILVER, table="dim_run", rows=runs)
    return written


def _write_ablation(deps: ApplicationDependencies, plan: Preregistration) -> int:
    repo, written = deps.analytics_repository, 0
    configurations = {LOCO_REFERENCE_MODEL: None, **{loco_model_of(f): f for f in H3_FAMILIES}}
    runs: list[dict[str, object]] = []
    for model, family in configurations.items():
        for seed in _SEEDS:
            for fold in _FOLDS:
                run_id = f"{_ABLATION}-{model}-s{seed}-{fold}"
                runs.append(_dim(run_id, _ABLATION, _ABLATION_FS, model, seed, fold))
                facts: list[dict[str, object]] = []
                for h in _HORIZONS:
                    shift = 0.0 if family is None else _SUSTAINED[(family, h)]
                    for d in _test_points(fold, h):
                        grid = _grids(plan, plan.candidate, seed, h, d)[1]
                        facts.extend(
                            _fact(
                                run_id,
                                model,
                                _ABLATION_FS,
                                "test",
                                h,
                                d,
                                level,
                                v + shift,
                                v + shift,
                                year_of_decision=True,
                            )
                            for level, v in zip(plan.quantile_levels, grid, strict=True)
                        )
                repo.write(layer=_SILVER, table="fact_oos_predictions", rows=facts)
                written += len(facts)
    repo.write(layer=_SILVER, table="dim_run", rows=runs)
    return written


def _write_attribution(deps: ApplicationDependencies, plan: Preregistration) -> tuple[int, int]:
    repo = deps.analytics_repository
    partition_hash = str(h3_block()["partition"]["partition_hash"])  # type: ignore[index]
    variables = _variables()
    share = 1.0 / len(variables)
    labels = [("none", 0)] + [(f, k) for f in H3_FAMILIES for k in range(1, _K_P + 1)]
    permuted_total = vsn_total = 0
    for seed in _SEEDS:
        for fold in _FOLDS:
            run_id = f"{_COHORT}-{plan.candidate}-s{seed}-{fold}"
            permuted: list[dict[str, object]] = []
            for h in _HORIZONS:
                for d in _test_points(fold, h):
                    grid = _grids(plan, plan.candidate, seed, h, d)[1]
                    for family, k in labels:
                        shift = 0.0 if family == "none" else _SUSTAINED[(family, h)] * (1 + 0.1 * k)
                        for level, value in zip(plan.quantile_levels, grid, strict=True):
                            row = _fact(
                                run_id,
                                plan.candidate,
                                _FS,
                                "test",
                                h,
                                d,
                                level,
                                value + shift,
                                value + shift,
                                year_of_decision=True,
                            )
                            del row["split"]
                            row.update(
                                permuted_family=family,
                                permutation_index=k,
                                permutation_seed=130,
                                permutation_algorithm="fisher_yates_random_random_v1",
                                partition_hash=partition_hash,
                            )
                            permuted.append(row)
            repo.write(layer=_SILVER, table="fact_permuted_predictions", rows=permuted)
            permuted_total += len(permuted)
            decisions = sorted({d for h in _HORIZONS for d in _test_points(fold, h)})
            vsn = [
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "model_version": plan.candidate,
                    "asset": _ASSET,
                    "feature_set_name": _FS,
                    "decision_idx": d,
                    "timestamp_utc": _session(d),
                    "variable": variable,
                    "family": family,
                    "weight": share * (1 + 0.01 * ((d + seed) % 3)) / 1.01,
                    "year": int(_session(d)[:4]),
                }
                for d in decisions
                for variable, family in variables.items()
            ]
            repo.write(layer=_SILVER, table="fact_vsn_weights", rows=vsn)
            vsn_total += len(vsn)
    return permuted_total, vsn_total


# --- pernas ------------------------------------------------------------------------------

_LEG = """
import json, logging, os, sys, time
from pathlib import Path
from financial_forecasting.composition_root import wire_dependencies
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.domain.value_objects.silver_content_hash import (
    SilverContentHash,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings

root, hash_on = Path(sys.argv[1]), sys.argv[2] == "on"
if not hash_on:  # a perna sem hash: o VO devolve uma constante (só neste processo)
    constant = SilverContentHash(value="0" * 64)
    SilverContentHash.of_unit = classmethod(lambda cls, **_: constant)
    SilverContentHash.combine = classmethod(lambda cls, **_: constant)
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
stored = json.loads((root / "r3.json").read_text(encoding="utf-8"))
plan = Preregistration.from_mapping(stored["payload"])
deps = wire_dependencies(
    Settings(
        _env_file=None,
        data_root=root / "data",
        repo_root=root,
        artifacts_root=root / "art",
        mlflow_tracking_uri="sqlite:///" + str(root / "mlruns.db"),
    )
)
started = time.monotonic()
result = deps.refresh_gold(refresh_command_from(plan, stored["reference"]))
wall = time.monotonic() - started
peak = 0
for line in Path("/proc/self/status").read_text().splitlines():
    if line.startswith("VmHWM:"):
        peak = int(line.split()[1]) * 1024
print(json.dumps({
    "hash": "on" if hash_on else "off",
    "status": result.status.value,
    "wall_s": round(wall, 1),
    "peak_bytes": peak,
    "units": len(result.manifest.silver_content.units),
    "tables": sorted(result.manifest.silver_content.tables),
    "rows_by_table": dict(result.rows_by_table),
    "failed_checks": [f"{c.check}:{c.kind}:{c.horizon}:{c.model}:{c.seed}:{c.detail}"
                      for c in result.failed_checks],
}))
"""


def _leg(root: Path, hash_on: bool) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-c", _LEG, str(root), "on" if hash_on else "off"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    result: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
    steps: dict[str, float] = {}
    for name, seconds in _STEP.findall(completed.stderr):
        steps[name] = steps.get(name, 0.0) + float(seconds)
    result["steps_s"] = {name: round(value, 1) for name, value in steps.items()}
    return result


@dataclass(frozen=True)
class _Silver:
    root: Path
    counts: dict[str, int]


@pytest.fixture(scope="module")
def silver(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_Silver]:
    root = tmp_path_factory.mktemp("silver-hash-cost")
    settings = Settings(
        _env_file=None,
        data_root=root / "data",
        repo_root=root,
        artifacts_root=root / "art",
        mlflow_tracking_uri=f"sqlite:///{root}/mlruns.db",
    )
    deps = wire_dependencies(settings=settings)
    fingerprint = _write_dataset(settings.data_root)
    payload = r3_payload(fingerprint)
    plan = Preregistration.from_mapping(payload)
    started = datetime.now(tz=UTC)
    confirmatory = _write_confirmatory(deps, plan)
    ablation = _write_ablation(deps, plan)
    permuted, vsn = _write_attribution(deps, plan)
    (root / "r3.json").write_text(
        json.dumps({"payload": payload, "reference": _reference(payload)}, default=str),
        encoding="utf-8",
    )
    counts = {
        "fact_oos_predictions_fs_all": confirmatory,
        "fact_oos_predictions_fs_all_ablation": ablation,
        "fact_permuted_predictions": permuted,
        "fact_vsn_weights": vsn,
        "write_s": int((datetime.now(tz=UTC) - started).total_seconds()),
    }
    yield _Silver(root, counts)


def test_silver_hash_cost_within_d11(silver: _Silver) -> None:
    off = _leg(silver.root, hash_on=False)
    on = _leg(silver.root, hash_on=True)
    print(json.dumps({"silver": silver.counts, "off": off, "on": on}, indent=2))

    assert off["status"] == on["status"] == "COMPLETED"
    assert set(on["tables"]) >= {
        "dim_run",
        "fact_oos_predictions",
        "fact_permuted_predictions",
        "fact_vsn_weights",
        "realized",
    }
    assert on["peak_bytes"] <= _PEAK_CEILING, on
    assert on["wall_s"] - off["wall_s"] <= _TIME_BUDGET_S, (on, off)
