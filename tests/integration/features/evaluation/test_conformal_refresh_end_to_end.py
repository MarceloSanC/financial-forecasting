"""E2E do refresh conformal sobre silver sintético, pelo grafo wirado (Stage 7.2 Task 20).

Reusa o realizado, o dataset e os quantis do e2e da 6.5
(`test_build_confirmatory_scorecard`) e o congelamento do e2e da 6.6
(`test_profiles_end_to_end`). O silver tem h em {1, 7}, 2 folds inteiros e 2 seeds do
candidato, mais um calib dedicado do candidato por run, antes do teste do fold e com o
gap de h. Em parte das linhas do candidato (decisão múltipla de 3), a grade crua é
cruzada: `value_raw` troca o q0,10 com o q0,5, enquanto `value_guardrail` guarda a
grade ordenada (`guardrail_applied = 1`). Assim, ler a coluna errada muda as correções
(I2).

O plano é gravado como a cadeia r0 → r1 → r2, com as três revisões ancoradas. A r1 é o
`r1_payload()` (emenda cega + `[profile_parameters]`) e a r2 é o `r2_payload()` (emenda
cega + `[conformal]`), os dois sobre o plano sintético do e2e e com o `amends` da
referência real da revisão anterior. Nenhum teste lê o cohort real.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pytest

from financial_forecasting.composition_root import ApplicationDependencies, wire_dependencies
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    ScorecardResult,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_CONFORMAL_CORRECTIONS,
    GOLD_CONFORMAL_COVERAGE,
    GOLD_SCHEMAS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldPartition,
    RefreshGoldResult,
    RefreshStatus,
    Row,
)
from financial_forecasting.features.evaluation.application.ports.out.conformal_calibration import (
    ConformalCalibration,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    RefreshGold,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalCalibrator,
    ConformalVariant,
    PairCorrection,
)
from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    CalibrationPoint,
    CalibrationSet,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.fakes.features.evaluation.fake_conformal_calibration import FakeConformalCalibration
from tests.integration.features.evaluation.test_build_confirmatory_scorecard import (
    _ASSET,
    _N_SESSIONS,
    _SILVER,
    _plan_payload,
    _quantiles,
    _realized,
    _seeds,
    _session,
    _write_dataset,
)
from tests.integration.features.evaluation.test_profiles_end_to_end import _freeze
from tests.unit.features.evaluation._conformal_parameters import conformal_block
from tests.unit.features.evaluation._preregistration_payload import (
    R1_AMENDMENT,
    R2_AMENDMENT,
    with_leaf,
)
from tests.unit.features.evaluation._profile_parameters import profile_block

pytestmark = pytest.mark.integration

_COHORT = "e2e-conformal"
_HORIZONS = (1, 7)
_CALIB_LEN = 20
_TEST_FIRST = _CALIB_LEN + max(_HORIZONS)  # 1ª decisão de teste: o calib do fold 0 + gap h
_MIDDLE = (_TEST_FIRST + _N_SESSIONS) // 2  # 1ª decisão de teste do fold 1
_CALIB = {  # decisões de calib por fold: alvo + h antes da 1ª decisão de teste do fold
    "0": range(0, _CALIB_LEN),
    "1": range(_MIDDLE - max(_HORIZONS) - _CALIB_LEN, _MIDDLE - max(_HORIZONS)),
}
_CROSSED_EVERY = 3  # decisões do candidato com a grade crua cruzada (q0,10 <-> q0,5)
_SPLIT = ConformalVariant.SPLIT_CQR.value
_NEXCP = ConformalVariant.NEXCP.value
_CONFORMAL = (GOLD_CONFORMAL_CORRECTIONS.name, GOLD_CONFORMAL_COVERAGE.name)
_TAILS = ("lower_tail", "upper_tail")


# --- silver ----------------------------------------------------------------------------


def _fact(  # noqa: PLR0913 — a linha longa do silver
    run_id: str,
    model: str,
    split: str,
    horizon: int,
    decision: int,
    level: float,
    raw: float,
    guardrail: float,
    applied: int,
) -> dict[str, object]:
    target = decision + horizon
    return {
        "schema_version": 1,
        "run_id": run_id,
        "model_version": model,
        "asset": _ASSET,
        "feature_set_name": "fs-core",
        "split": split,
        "horizon": horizon,
        "decision_idx": decision,
        "timestamp_utc": _session(decision),
        "target_timestamp_utc": _session(target),
        "quantile_level": level,
        "value_raw": raw,
        "value_guardrail": guardrail,
        "guardrail_applied": applied,  # flag do PONTO: igual em todos os níveis
        "year": int(_session(target)[:4]),
    }


_DEGENERATE_EVERY = 23  # teste do candidato em d % 23 == 1: grade quase constante (TA-4)
_DEGENERATE_STEP = 1e-14  # níveis distintos (não degenerado com tolerância 0) e dentro de 1e-12


def _grids(  # noqa: PLR0913 — o ponto do silver
    prereg: Preregistration, model: str, seed: int | None, h: int, d: int, split: str = "test"
) -> tuple[list[float], list[float]]:
    """(grade crua, grade do guardrail) do ponto.

    No candidato: crua cruzada em d % 3 == 0; no teste em d % 23 == 1, a grade é quase
    constante (passos de 1e-14), degenerada pela tolerância do plano (1e-12) e não pela
    tolerância zero (I14: o n conformal é o da máscara nativa).
    """
    guardrail = _quantiles(model, seed, h, d + h)
    if model == prereg.candidate and split == "test" and d % _DEGENERATE_EVERY == 1:
        base = guardrail[3]
        flat = [base + k * _DEGENERATE_STEP for k in range(len(guardrail))]
        return flat, flat
    raw = list(guardrail)
    if model == prereg.candidate and d % _CROSSED_EVERY == 0:
        raw[1], raw[3] = raw[3], raw[1]  # o q0,10 cru acima do q0,5: grade cruzada
    return raw, guardrail


def _write_silver(
    deps: ApplicationDependencies, prereg: Preregistration, *, drop: tuple[int, int, int] | None
) -> None:
    """Teste de todos os modelos e calib do candidato; `drop` = (seed, h, decisão) ausente."""
    sweep = prereg.cohort.cohort_id
    runs: list[dict[str, object]] = []
    facts: list[dict[str, object]] = []
    for model in prereg.models:
        for seed in _seeds(prereg, model, ()):
            for fold in _CALIB:
                runs.append(
                    {
                        "schema_version": 1,
                        "run_id": f"{sweep}-{model}-s{seed}-{fold}",
                        "asset": _ASSET,
                        "parent_sweep_id": sweep,
                        "feature_set_name": "fs-core",
                        "config_signature": f"sig-{model}",
                        "split_fingerprint": "split-e2e",
                        "fold": fold,
                        "seed": seed,
                        "model_version": model,
                    }
                )
            for horizon in prereg.horizons:
                points = [
                    ("0" if d < _MIDDLE else "1", "test", d)
                    for d in range(_TEST_FIRST, _N_SESSIONS - horizon)
                ]
                if model == prereg.candidate:
                    points += [(fold, "calib", d) for fold, span in _CALIB.items() for d in span]
                for fold, split, decision in points:
                    if (seed, horizon, decision) == drop and split == "test":
                        continue
                    raw, guardrail = _grids(prereg, model, seed, horizon, decision, split)
                    run_id = f"{sweep}-{model}-s{seed}-{fold}"
                    applied = int(raw != guardrail)
                    facts.extend(
                        _fact(run_id, model, split, horizon, decision, level, r, g, applied)
                        for level, r, g in zip(prereg.quantile_levels, raw, guardrail, strict=True)
                    )
    deps.analytics_repository.write(layer=_SILVER, table="dim_run", rows=runs)
    deps.analytics_repository.write(layer=_SILVER, table="fact_oos_predictions", rows=facts)


# --- cenário ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _World:
    deps: ApplicationDependencies
    plans: tuple[Preregistration, ...]  # r0, r1, r2
    references: tuple[str, ...]


@dataclass(frozen=True)
class _Run:
    refresh: RefreshGoldResult
    generation: GoldGeneration


def _world(root: Path, *, drop: tuple[int, int, int] | None = None) -> _World:
    settings = Settings(
        _env_file=None,
        data_root=root / "data",
        repo_root=root,
        artifacts_root=root / "art",
        mlflow_tracking_uri=f"sqlite:///{root}/mlruns.db",
    )
    deps = wire_dependencies(settings=settings)
    fingerprint = _write_dataset(settings.data_root)
    r0_payload = with_leaf(
        _plan_payload("conformal_plan", _COHORT, fingerprint), "horizons", [1, 7]
    )
    r0, r0_reference = _freeze(root, r0_payload, 0)
    r1_payload = {
        **r0_payload,
        **R1_AMENDMENT,
        "amends": r0_reference,
        "profile_parameters": profile_block(),
    }
    r1, r1_reference = _freeze(root, r1_payload, 1)
    r2_payload = {
        **r1_payload,
        **R2_AMENDMENT,
        "amends": r1_reference,
        "conformal": conformal_block(),
    }
    r2, r2_reference = _freeze(root, r2_payload, 2)
    _write_silver(deps, r0, drop=drop)
    return _World(deps, (r0, r1, r2), (r0_reference, r1_reference, r2_reference))


def _refresh(world: _World, revision: int, port: ConformalCalibration | None = None) -> _Run:
    """O refresh pela revisão; `port` troca o real por outro sobre os mesmos adapters."""
    wired = world.deps.refresh_gold
    use_case = wired
    if port is not None:
        use_case = RefreshGold(
            silver_reader=wired._silver_reader,
            grid_reader=wired._grid_reader,
            clock=wired._clock,
            mcs_backend=wired._mcs_backend,
            gold_store=wired._gold_store,
            builders=wired._builders,
            conformal_calibration=port,
            hasher=wired._hasher,
        )
    plan, reference = world.plans[revision], world.references[revision]
    refresh = use_case(refresh_command_from(plan, reference))
    generation = wired._gold_store.read_generation(partition=GoldPartition(_ASSET, _COHORT))
    return _Run(refresh=refresh, generation=generation)


def _scorecard(world: _World, revision: int) -> ScorecardResult:
    return world.deps.build_confirmatory_scorecard(
        BuildConfirmatoryScorecardCommand(
            name=world.plans[revision].name,
            revision=revision,
            preregistration_ref=world.references[revision],
        )
    )


@dataclass(frozen=True)
class _Scenario:
    world: _World
    r1: _Run
    r2: _Run
    r1_scorecard: ScorecardResult
    r2_scorecard: ScorecardResult
    zero: _Run  # r2 com o `FakeConformalCalibration` (correções zero)
    forced: _Run  # r2 com o fake e a unidade (fold 0, seed 1, h 1) forçada a `error`


_FORCED = (0, 1, 1)


@pytest.fixture(scope="module")
def scenario(tmp_path_factory: pytest.TempPathFactory) -> _Scenario:
    world = _world(tmp_path_factory.mktemp("e2e-conformal"))
    r1 = _refresh(world, 1)
    r1_scorecard = _scorecard(world, 1)
    r2 = _refresh(world, 2)
    r2_scorecard = _scorecard(world, 2)
    zero = _refresh(world, 2, FakeConformalCalibration())
    forced = _refresh(
        world, 2, FakeConformalCalibration(force_status={_FORCED: ("error", "forced")})
    )
    return _Scenario(world, r1, r2, r1_scorecard, r2_scorecard, zero, forced)


def _rows(run: _Run, name: str) -> tuple[Row, ...]:
    return run.generation.table(GOLD_SCHEMAS[name]).rows


def _seed_tail_rows(run: _Run) -> list[Row]:
    return [
        row
        for row in _rows(run, GOLD_CONFORMAL_COVERAGE.name)
        if row["status"] == "ok" and row["seed"] is not None and row["kind"] in _TAILS
    ]


def _native(run: _Run, candidate: str, row: Row) -> Row:
    """A linha da `gold_calibration_table` da mesma cauda: modelo inteiro, sem degenerados."""
    [native] = [
        cal
        for cal in _rows(run, GOLD_CALIBRATION_TABLE.name)
        if (
            cal["model"],
            cal["seed"],
            cal["horizon"],
            cal["sample"],
            cal["kind"],
            cal["level_low"],
            cal["includes_degenerate"],
            cal["dgt_offset"],
            cal["band_level"],
        )
        == (
            candidate,
            row["seed"],
            row["horizon"],
            "model_full",
            row["kind"],
            row["nominal"],
            False,
            None,
            row["band_level"],
        )
    ]
    return native


# --- testes ----------------------------------------------------------------------------


def test_completed_generation_has_both_conformal_tables(scenario: _Scenario) -> None:
    run = scenario.r2
    assert run.refresh.status is RefreshStatus.COMPLETED
    assert all(run.refresh.rows_by_table[name] > 0 for name in _CONFORMAL)
    parameters = run.generation.manifest.as_mapping()["parameters"]
    r2 = scenario.world.plans[2]
    assert r2.conformal is not None
    assert parameters["conformal_parameters"] == r2.conformal.as_payload()


def test_conformal_n_evaluated_equals_native_n_observed(scenario: _Scenario) -> None:
    """I14: o n da linha conformal é o `n_observed` da série nativa da mesma cauda."""
    candidate = scenario.world.plans[2].candidate
    rows = _seed_tail_rows(scenario.r2)
    assert rows
    for row in rows:
        assert row["n_evaluated"] == _native(scenario.r2, candidate, row)["n_observed"], row
        # TA-4 (mutante RG03): há pontos degenerados pela tolerância do plano
        assert row["n_evaluated"] < row["n_points"], row
    by_seed: dict[tuple[object, ...], list[float]] = {}
    for row in rows:
        key = (row["horizon"], row["variant"], row["kind"], row["lower_level"], row["band_level"])
        by_seed.setdefault(key, []).append(float(row["n_evaluated"]))
    means = [
        row
        for row in _rows(scenario.r2, GOLD_CONFORMAL_COVERAGE.name)
        if row["seed"] is None and row["status"] == "ok" and row["kind"] in _TAILS
    ]
    assert means
    for row in means:
        key = (row["horizon"], row["variant"], row["kind"], row["lower_level"], row["band_level"])
        n = by_seed[key]
        assert row["n_mean"] == pytest.approx(sum(n) / len(n)), row
        assert row["n_evaluated"] is None


def test_zero_corrections_coverage_equals_native(scenario: _Scenario) -> None:
    """Correções zero: a contagem da cauda conformal é a da cauda nativa (mesma máscara)."""
    candidate = scenario.world.plans[2].candidate
    assert scenario.zero.refresh.conformal_error_units == 0
    rows = _seed_tail_rows(scenario.zero)
    assert rows
    for row in rows:
        native = _native(scenario.zero, candidate, row)
        violations = native["n_violations"]
        expected = violations if row["kind"] == "lower_tail" else native["n_observed"] - violations
        assert row["count"] == expected, row


def test_r1_plan_writes_empty_conformal_tables(scenario: _Scenario) -> None:
    run = scenario.r1
    assert run.refresh.status is RefreshStatus.COMPLETED
    assert all(run.refresh.rows_by_table[name] == 0 for name in _CONFORMAL)
    assert run.refresh.conformal_error_units == 0
    assert run.generation.manifest.parameters.conformal_parameters is None


def test_blocked_generation_has_no_conformal_tables(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    world = _world(tmp_path_factory.mktemp("e2e-conformal-blocked"), drop=(1, 1, _TEST_FIRST + 10))
    run = _refresh(world, 2)
    assert run.refresh.status is RefreshStatus.BLOCKED
    assert run.refresh.conformal_error_units == 0
    assert all(run.refresh.rows_by_table.get(name, 0) == 0 for name in _CONFORMAL)
    assert all(
        not run.generation.tables.get(name, None) or not _rows(run, name) for name in _CONFORMAL
    )


def test_port_error_unit_row_count_and_undefined_coverage(scenario: _Scenario) -> None:
    run = scenario.forced
    pairs = len(conformal_block()["pairs"])  # type: ignore[arg-type]
    assert run.refresh.conformal_error_units == 1  # unidades distintas (CA15; C4-6)
    fold, seed, horizon = _FORCED
    errors = [
        row
        for row in _rows(run, GOLD_CONFORMAL_CORRECTIONS.name)
        if (row["fold_raw"], row["seed"], row["horizon"]) == (str(fold), seed, horizon)
    ]
    assert len(errors) == pairs * 2 * 2  # pares x variantes x caudas
    assert {(row["status"], row["reason"]) for row in errors} == {("error", "forced")}
    assert {row["status"] for row in _rows(run, GOLD_CONFORMAL_CORRECTIONS.name)} == {
        "ok",
        "error",
    }
    coverage = _rows(run, GOLD_CONFORMAL_COVERAGE.name)
    undefined = {
        (r["seed"], r["horizon"], r["variant"]) for r in coverage if r["status"] == "undefined"
    }
    assert undefined == {(seed, horizon, _SPLIT), (seed, horizon, _NEXCP)}
    means = [r for r in coverage if r["seed"] is None and r["horizon"] == horizon]
    assert {(r["n_seeds_used"], r["seeds_excluded"]) for r in means} == {(1, str(seed))}


def _without_ref(rows: tuple[Row, ...]) -> list[dict[str, object]]:
    return [{k: v for k, v in row.items() if k != "preregistration_ref"} for row in rows]


def _manifest_without_expected_differences(run: _Run) -> dict[str, object]:
    manifest = run.generation.manifest.as_mapping()
    for name in ("preregistration_ref", "started_at", "finished_at"):
        del manifest[name]
    parameters = dict(manifest["parameters"])
    for name in ("preregistration_ref", "conformal_parameters"):
        del parameters[name]
    manifest["parameters"] = parameters
    manifest["rows_by_table"] = {
        k: v for k, v in manifest["rows_by_table"].items() if k not in _CONFORMAL
    }
    return manifest


def test_r1_and_r2_refreshes_same_verdict_and_same_tables(scenario: _Scenario) -> None:
    """I10/I15: o bloco conformal não toca no veredito nem nas tabelas da 6.4-6.6."""
    assert scenario.r2_scorecard.verdict == scenario.r1_scorecard.verdict
    for name in GOLD_SCHEMAS:
        if name in _CONFORMAL:
            continue
        assert _without_ref(_rows(scenario.r2, name)) == _without_ref(_rows(scenario.r1, name)), (
            name
        )
    assert _manifest_without_expected_differences(
        scenario.r2
    ) == _manifest_without_expected_differences(scenario.r1)


def _calibration_set(
    world: _World, fold: str, seed: int, horizon: int, *, column: int
) -> CalibrationSet:
    """O calib da unidade montado à mão; `column` 1 = guardrail, 0 = cru."""
    plan = world.plans[2]
    levels = list(plan.quantile_levels)
    low, high = levels.index(0.1), levels.index(0.9)
    realized = _realized()
    points = []
    for decision in _CALIB[fold]:
        grid = _grids(plan, plan.candidate, seed, horizon, decision, "calib")[column]
        points.append(
            CalibrationPoint(
                decision_timestamp=_session(decision),
                target_timestamp=_session(decision + horizon),
                lower=grid[low],
                upper=grid[high],
                realized=realized[decision + horizon],
            )
        )
    test_start = _TEST_FIRST if fold == "0" else _MIDDLE
    return CalibrationSet(
        fold_index=int(fold),
        seed=seed,
        horizon=horizon,
        lower_level=0.1,
        upper_level=0.9,
        points=tuple(points),
        test_start=_session(test_start),
    )


def _gold_tails(run: _Run, fold: str, seed: int, horizon: int) -> dict[object, Row]:
    return {
        row["tail"]: row
        for row in _rows(run, GOLD_CONFORMAL_CORRECTIONS.name)
        if (row["fold_raw"], row["seed"], row["horizon"], row["variant"])
        == (fold, seed, horizon, _SPLIT)
        and (row["lower_level"], row["upper_level"]) == (0.1, 0.9)
    }


def test_real_use_case_through_the_composition_root(scenario: _Scenario) -> None:
    """Cada linha gold é o `ConformalCalibrator` sobre o calib do `value_guardrail` (I2).

    E em pelo menos uma unidade com linha cruzada o calib do `value_raw` daria outra
    correção: a troca de coluna não passaria em silêncio.
    """
    assert scenario.r2.refresh.conformal_error_units == 0
    differs_from_raw = 0
    for fold in _CALIB:
        for seed in (1, 2):
            for horizon in _HORIZONS:
                rows = _gold_tails(scenario.r2, fold, seed, horizon)
                assert set(rows) == {"lower", "upper"}

                def calibrate(
                    column: int, fold: str = fold, seed: int = seed, h: int = horizon
                ) -> PairCorrection:
                    calib = _calibration_set(scenario.world, fold, seed, h, column=column)
                    return ConformalCalibrator.calibrate(calib, variant=ConformalVariant.SPLIT_CQR)

                expected, raw = calibrate(1), calibrate(0)
                for tail in (expected.lower, expected.upper):
                    row = rows[tail.tail]
                    assert row["status"] == "ok"
                    assert (row["n"], row["rank"], row["infinite"]) == (
                        tail.n,
                        tail.rank,
                        tail.infinite,
                    )
                    # TA-2 (mutante M11): o literal do par, não o objeto do calibrador
                    assert row["tail_level"] == {"lower": 0.1, "upper": 0.9}[tail.tail]
                    assert math.isfinite(tail.correction)
                    assert row["correction"] == tail.correction
                differs_from_raw += raw.lower.correction != expected.lower.correction
    assert differs_from_raw > 0


def test_gold_store_round_trip_keeps_count_and_mean_types(scenario: _Scenario) -> None:
    """C4-9: pelo `ParquetGoldStore` real, n e contagem por seed voltam inteiros e n̄/c̄ float."""
    rows = _rows(scenario.r2, GOLD_CONFORMAL_COVERAGE.name)
    seeds = [r for r in rows if r["seed"] is not None and r["status"] == "ok"]
    means = [r for r in rows if r["seed"] is None and r["status"] == "ok"]
    assert seeds
    assert means
    assert all(type(r["n_evaluated"]) is int for r in seeds)
    assert all(type(r["count"]) is int for r in seeds if r["kind"] in _TAILS)
    assert all(type(r["n_mean"]) is float for r in means)
    assert all(type(r["mean_count"]) is float for r in means if r["kind"] in _TAILS)
    corrections = _rows(scenario.r2, GOLD_CONFORMAL_CORRECTIONS.name)
    assert all(type(r["n"]) is int for r in corrections if r["status"] == "ok")
