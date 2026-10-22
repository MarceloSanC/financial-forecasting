"""Hash do silver consumido sobre o leitor real do analytics store (Stage 8.1, Task 05; A2, R12).

Mundo sintético do e2e de H3 (`test_h3_refresh_end_to_end`): composition root real,
`ParquetAnalyticsRepository` real, plano r3 com `[conformal]` e `[h3]`, silver de
atribuição e ablação gravados pelo próprio repositório. O mundo base é montado uma vez
por módulo; cada caso copia a raiz inteira para um diretório novo, religa as dependências
sobre a cópia, muda o silver (ou o dataset) e roda o refresh de novo. Nenhum teste lê o
cohort real.

- (a) duas execuções e o mesmo silver dividido em dois arquivos → o mesmo digest;
- (b) uma linha consumida alterada, por origem → muda a sua unidade, a sua tabela e o
  combinado, e nada mais (o realizado muda por `math.nextafter`: o
  `DatasetContentFingerprint`, que arredonda a 10 casas, fica igual);
- (c) linhas lidas e descartadas (ou nem pedidas) → digest igual;
- `seed` nulo e não nulo no `dim_run` lidos pelo leitor real são aceitos e distintos.
"""

from __future__ import annotations

import math
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from financial_forecasting.composition_root import ApplicationDependencies, wire_dependencies
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    RefreshGoldResult,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.silver_content_hash import (
    SilverContentHash,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.integration.features.evaluation.test_build_confirmatory_scorecard import (
    _ASSET,
    _SILVER,
)
from tests.integration.features.evaluation.test_conformal_refresh_end_to_end import _COHORT
from tests.integration.features.evaluation.test_h3_refresh_end_to_end import (
    _HASH,
    _SUSTAINED,
    _r3,
    _world,
    _write_ablation,
    _write_attribution,
)

pytestmark = pytest.mark.integration

_ABLATION = "ablation-sustained"
_ABLATION_FS = "fs_all_ablation"
_OOS = "fact_oos_predictions"
_PERMUTED = "fact_permuted_predictions"
_VSN = "fact_vsn_weights"
Row = dict[str, object]


@dataclass(frozen=True)
class _Base:
    root: Path
    plan: Preregistration
    reference: str
    result: RefreshGoldResult


def _settings(root: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_root=root / "data",
        repo_root=root,
        artifacts_root=root / "art",
        mlflow_tracking_uri=f"sqlite:///{root}/mlruns.db",
    )


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> _Base:
    root = tmp_path_factory.mktemp("silver-content-base")
    world = _world(root)
    _write_attribution(world.deps, world.plans[2], _SUSTAINED, str(_HASH))
    _write_ablation(world.deps, world.plans[2], _ABLATION, _SUSTAINED)
    plan, reference = _r3(world, cohort_id=_ABLATION)
    result = world.deps.refresh_gold(refresh_command_from(plan, reference))
    assert result.status is RefreshStatus.COMPLETED
    return _Base(root, plan, reference, result)


Change = Callable[[ApplicationDependencies, Path], str | None]
"""Muda o silver (ou o dataset) da cópia; devolve a chave da unidade mudada, se houver."""


def _variant_with_unit(
    base: _Base, tmp_path: Path, change: Change
) -> tuple[RefreshGoldResult, str | None]:
    """Copia o mundo base, aplica `change` sobre a cópia e roda o refresh nela."""
    root = tmp_path / "world"
    shutil.copytree(base.root, root)
    deps = wire_dependencies(settings=_settings(root))
    unit = change(deps, root / "data")
    return deps.refresh_gold(refresh_command_from(base.plan, base.reference)), unit


def _variant(base: _Base, tmp_path: Path, change: Change) -> RefreshGoldResult:
    return _variant_with_unit(base, tmp_path, change)[0]


def _content(result: RefreshGoldResult) -> SilverContent:
    return result.manifest.silver_content


def _read(deps: ApplicationDependencies, table: str, **filters: object) -> list[Row]:
    rows = deps.analytics_repository.read(layer=_SILVER, table=table, filters=filters)
    return [dict(row) for row in rows]


def _upsert(deps: ApplicationDependencies, table: str, rows: list[Row]) -> None:
    deps.analytics_repository.write(layer=_SILVER, table=table, rows=rows, allow_upsert=True)


def _append(deps: ApplicationDependencies, table: str, rows: list[Row]) -> None:
    deps.analytics_repository.write(layer=_SILVER, table=table, rows=rows)


def _first(rows: list[Row], **wanted: object) -> Row:
    return next(row for row in rows if all(row[k] == v for k, v in wanted.items()))


def _nudged(row: Row, column: str) -> Row:
    value = row[column]
    assert isinstance(value, float)
    return {**row, column: math.nextafter(value, math.inf)}


def _candidate(base: _Base) -> str:
    return str(base.plan.candidate)


# --- (b) uma linha consumida alterada, por origem -----------------------------------------


def _change_dim_run(sweep: str) -> Change:
    def change(deps: ApplicationDependencies, _: Path) -> str:
        row = _read(deps, "dim_run", asset=_ASSET, parent_sweep_id=sweep)[0]
        _upsert(deps, "dim_run", [{**row, "split_fingerprint": "split-changed"}])
        return f"dim_run|{sweep}"

    return change


def _change_fact(table: str, feature_set: str, **wanted: object) -> Change:
    column = "weight" if table == _VSN else "value_raw"

    def change(deps: ApplicationDependencies, _: Path) -> str:
        row = _first(_read(deps, table, asset=_ASSET, feature_set_name=feature_set), **wanted)
        _upsert(deps, table, [_nudged(row, column)])
        return f"{table}|{row['run_id']}|{row['year']}"

    return change


def _change_realized(_: ApplicationDependencies, data_root: Path) -> str:
    path = data_root / "processed" / "dataset_tft" / _ASSET / f"dataset_tft_{_ASSET}.parquet"
    frame = pd.read_parquet(path)
    last = frame.index[-1]
    frame.loc[last, "target_return"] = math.nextafter(
        float(frame.loc[last, "target_return"]), math.inf
    )
    frame.to_parquet(path, index=False)
    return f"realized|{_ASSET}"


_CHANGED: dict[str, tuple[Change, str]] = {
    "dim_run-cohort": (_change_dim_run(_COHORT), "dim_run"),
    "dim_run-ablation": (_change_dim_run(_ABLATION), "dim_run"),
    "oos-test-cohort": (_change_fact(_OOS, "fs-core", split="test"), _OOS),
    "oos-calib-cohort": (_change_fact(_OOS, "fs-core", split="calib"), _OOS),
    "oos-test-ablation": (_change_fact(_OOS, _ABLATION_FS, split="test"), _OOS),
    "permuted": (_change_fact(_PERMUTED, "fs-core"), _PERMUTED),
    "vsn": (_change_fact(_VSN, "fs-core"), _VSN),
    "realized": (_change_realized, "realized"),
}


def _changed(before: Mapping[str, str], after: Mapping[str, str]) -> set[str]:
    return {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}


def test_two_runs_same_digest(base: _Base, tmp_path: Path) -> None:
    again = _variant(base, tmp_path, lambda _deps, _root: None)

    assert _content(again) == _content(base.result)
    assert set(_content(base.result).tables) == {"dim_run", _OOS, _PERMUTED, _VSN, "realized"}


def test_same_silver_split_in_two_files_same_digest(base: _Base, tmp_path: Path) -> None:
    def split(_: ApplicationDependencies, data_root: Path) -> None:
        files = sorted((data_root / _SILVER / _OOS).rglob("*.parquet"))
        assert files
        for path in files:
            # `ParquetFile` lê só o arquivo, sem inferir partição hive pelo caminho
            table = pq.ParquetFile(path).read()  # type: ignore[no-untyped-call]
            half = table.num_rows // 2
            pq.write_table(table.slice(0, half), path)  # type: ignore[no-untyped-call]
            second = path.with_name("second-half.parquet")
            pq.write_table(table.slice(half), second)  # type: ignore[no-untyped-call]
        assert len(list((data_root / _SILVER / _OOS).rglob("*.parquet"))) == 2 * len(files)

    result = _variant(base, tmp_path, split)

    assert _content(result) == _content(base.result)


@pytest.mark.parametrize("origin", list(_CHANGED))
def test_one_consumed_row_changed_changes_its_unit_table_and_total(
    origin: str, base: _Base, tmp_path: Path
) -> None:
    change, table = _CHANGED[origin]

    result, unit = _variant_with_unit(base, tmp_path, change)

    before, after = _content(base.result), _content(result)
    assert result.status is RefreshStatus.COMPLETED
    assert _changed(before.units, after.units) == {unit}
    assert _changed(before.tables, after.tables) == {table}
    assert after.digest != before.digest
    if origin == "realized":
        # |Δ| < 1e-10: a identidade arredondada do cohort não vê, a exata vê
        assert result.manifest.dataset_fingerprint == base.result.manifest.dataset_fingerprint


# --- (c) linhas lidas e descartadas -------------------------------------------------------


def _other_sweep_rows(deps: ApplicationDependencies, _: Path) -> None:
    run = _read(deps, "dim_run", asset=_ASSET, parent_sweep_id=_COHORT)[0]
    alien = f"other-{run['run_id']}"
    _append(deps, "dim_run", [{**run, "run_id": alien, "parent_sweep_id": "other-sweep"}])
    facts = _read(deps, _OOS, asset=_ASSET, feature_set_name="fs-core")
    _append(deps, _OOS, [{**row, "run_id": alien} for row in facts[:20]])


def _ablation_calib_rows(deps: ApplicationDependencies, _: Path) -> None:
    rows = _read(deps, _OOS, asset=_ASSET, feature_set_name=_ABLATION_FS)
    _append(deps, _OOS, [{**row, "split": "calib", "value_raw": 9.0} for row in rows[:20]])


def _ablation_year_outside(deps: ApplicationDependencies, _: Path) -> None:
    rows = _read(deps, _OOS, asset=_ASSET, feature_set_name=_ABLATION_FS)
    _append(deps, _OOS, [{**row, "year": 1999} for row in rows[:20]])


def _non_candidate_attribution(base: _Base) -> Change:
    def change(deps: ApplicationDependencies, _: Path) -> None:
        runs = _read(deps, "dim_run", asset=_ASSET, parent_sweep_id=_COHORT)
        other = next(run for run in runs if run["model_version"] != _candidate(base))
        for table in (_PERMUTED, _VSN):
            rows = _read(deps, table, asset=_ASSET, feature_set_name="fs-core")[:20]
            _append(
                deps,
                table,
                [
                    {**row, "run_id": other["run_id"], "model_version": other["model_version"]}
                    for row in rows
                ],
            )

    return change


@pytest.mark.parametrize(
    "case", ["other-sweep", "ablation-calib", "ablation-year-outside", "non-candidate-attribution"]
)
def test_read_and_discarded_rows_do_not_change_digest(
    case: str, base: _Base, tmp_path: Path
) -> None:
    change = {
        "other-sweep": _other_sweep_rows,
        "ablation-calib": _ablation_calib_rows,
        "ablation-year-outside": _ablation_year_outside,
        "non-candidate-attribution": _non_candidate_attribution(base),
    }[case]

    result = _variant(base, tmp_path, change)

    assert result.status is RefreshStatus.COMPLETED
    assert _content(result) == _content(base.result)


@pytest.mark.parametrize(
    ("column", "unusable"), [("fold", "fold-x"), ("seed", None)], ids=["fold", "seed"]
)
def test_run_with_unusable_fold_or_seed_attribution_does_not_change_digest(
    base: _Base, tmp_path: Path, column: str, unusable: object
) -> None:
    """Run do candidato com fold não inteiro ou sem seed vira `undefined`: nada dele entra."""

    def unusable_run(deps: ApplicationDependencies) -> Row:
        runs = _read(deps, "dim_run", asset=_ASSET, parent_sweep_id=_COHORT)
        template = next(run for run in runs if run["model_version"] == _candidate(base))
        return {**template, "run_id": "unusable-fold-run", column: unusable}

    def with_run(deps: ApplicationDependencies, _: Path) -> None:
        _append(deps, "dim_run", [unusable_run(deps)])

    def with_run_and_attribution(deps: ApplicationDependencies, root: Path) -> None:
        with_run(deps, root)
        for table in (_PERMUTED, _VSN):
            rows = _read(deps, table, asset=_ASSET, feature_set_name="fs-core")[:20]
            _append(deps, table, [{**row, "run_id": "unusable-fold-run"} for row in rows])

    without = _variant(base, tmp_path / "without", with_run)
    with_attribution = _variant(base, tmp_path / "with", with_run_and_attribution)

    assert with_attribution.status is without.status
    assert _content(with_attribution) == _content(without)
    assert not any("unusable-fold-run" in key for key in _content(without).units if "|" in key)


def test_dim_run_seed_null_and_not_null_hash(base: _Base) -> None:
    deps = wire_dependencies(settings=_settings(base.root))
    runs = _read(deps, "dim_run", asset=_ASSET, parent_sweep_id=_COHORT)
    without_seed = next(run for run in runs if run["seed"] is None)
    with_seed = next(run for run in runs if run["seed"] is not None)
    columns = deps.analytics_repository.columns(layer=_SILVER, table="dim_run")
    hasher = CanonicalJsonHasher()

    def digest(row: Row) -> SilverContentHash:
        return SilverContentHash.of_unit(
            hasher=hasher, table="dim_run", columns=columns, rows=[row]
        )

    assert columns["seed"] == ("int", True)
    assert digest(without_seed) != digest({**without_seed, "seed": 1})
    assert digest(with_seed) == digest({**with_seed, "seed": float(with_seed["seed"])})  # type: ignore[arg-type]
    assert f"dim_run|{_COHORT}" in _content(base.result).units
