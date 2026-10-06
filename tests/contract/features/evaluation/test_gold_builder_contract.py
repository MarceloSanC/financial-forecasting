"""Contract test do port `GoldBuilder` — suíte ÚNICA para o fake e os builders reais.

Prova (concept 6.4 A8, I14, I17; ADR 6.4.0001) que todo builder é um **mapeamento
puro**: `build` duas vezes com os mesmos `GoldInputs` dá tabelas iguais e não toca os
inputs; a tabela chama-se `gold_<name>`; toda linha carrega `asset`/`parent_sweep_id`
da partição; as confirmatórias (builders que não rodam bloqueados) carregam
`preregistration_ref` em toda linha; um builder `runs_when_blocked` constrói sobre os
`GoldInputs` de um refresh `BLOCKED`; `depends_on` não contém o próprio nome.

Os `GoldInputs` vêm de `_gold_inputs.py` (só domínio + `FakeMcsBackend`). Pernas:
`fake` e um id por builder real (`quality_checks`, `metrics_by_run`,
`calibration_table`, `dm_results`, `mcs_results`) — sem `skipif`. Os testes de
mapeamento de cada builder real ficam fora da parametrização, no mesmo arquivo
(technical 6.4 §1: adapter não entra em `tests/unit/features/evaluation/**`).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.calibration_table import (  # noqa: E501
    CalibrationTableGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_profiles import (  # noqa: E501
    DmProfilesGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_results import (
    DmResultsGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.dm_seed_fraction import (  # noqa: E501
    DmSeedFractionGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.mcs_results import (  # noqa: E501
    McsResultsGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.metrics_by_run import (  # noqa: E501
    MetricsByRunGoldBuilder,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.quality_checks import (  # noqa: E501
    QualityChecksGoldBuilder,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import GOLD_SCHEMAS
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import GoldInputs
from financial_forecasting.features.evaluation.application.ports.out.gold_builder import (
    GoldBuilder,
)
from financial_forecasting.features.evaluation.domain.services.coverage_metrics import (
    MPIW_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.crps_score import CRPS_Q_LABEL
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    SampleKind,
    SeriesReports,
)
from financial_forecasting.features.evaluation.domain.services.var_descriptive import (
    VAR_DESCRIPTIVE_LABEL,
)
from tests.contract.features.evaluation._gold_inputs import (
    PARTITION,
    PREREGISTRATION_REF,
    blocked_inputs,
    completed_inputs,
)
from tests.fakes.features.evaluation.fake_gold_builder import FakeGoldBuilder

BUILDERS: dict[str, Callable[[], GoldBuilder]] = {
    "fake": lambda: FakeGoldBuilder(
        "probe", depends_on=frozenset({"quality_checks"}), runs_when_blocked=True
    ),
    "quality_checks": QualityChecksGoldBuilder,
    "metrics_by_run": MetricsByRunGoldBuilder,
    "calibration_table": CalibrationTableGoldBuilder,
    "dm_results": DmResultsGoldBuilder,
    "mcs_results": McsResultsGoldBuilder,
    "dm_profiles": DmProfilesGoldBuilder,
    "dm_seed_fraction": DmSeedFractionGoldBuilder,
}


@pytest.fixture(params=list(BUILDERS), ids=list(BUILDERS))
def builder(request: pytest.FixtureRequest) -> GoldBuilder:
    return BUILDERS[request.param]()


@pytest.mark.contract
def test_builder_pure_mapping(builder: GoldBuilder) -> None:
    inputs = completed_inputs()
    snapshot = repr(inputs)
    first = builder.build(inputs)
    second = builder.build(inputs)
    assert first == second
    assert repr(inputs) == snapshot
    assert first.rows, "a completed refresh maps to at least one row"


@pytest.mark.contract
def test_table_named_after_builder(builder: GoldBuilder) -> None:
    assert builder.build(completed_inputs()).name == f"gold_{builder.name}"


@pytest.mark.contract
def test_rows_carry_partition(builder: GoldBuilder) -> None:
    for row in builder.build(completed_inputs()).rows:
        assert (row["asset"], row["parent_sweep_id"]) == (
            PARTITION.asset,
            PARTITION.parent_sweep_id,
        )


@pytest.mark.contract
def test_confirmatory_rows_carry_prereg(builder: GoldBuilder) -> None:
    """Confirmatória (não roda bloqueada) → `preregistration_ref` em toda linha."""
    table = builder.build(completed_inputs())
    if builder.runs_when_blocked:
        assert all("preregistration_ref" not in row for row in table.rows)
    else:
        assert all(row["preregistration_ref"] == PREREGISTRATION_REF for row in table.rows)


@pytest.mark.contract
def test_blocked_inputs_tolerated(builder: GoldBuilder) -> None:
    """Quem roda bloqueado constrói sobre um refresh `BLOCKED` (sem relatórios)."""
    if builder.runs_when_blocked:
        table = builder.build(blocked_inputs())
        assert table.name == f"gold_{builder.name}"
        assert table.rows
    else:
        # confirmatória: sem relatórios não há linha (e nada é inventado)
        assert builder.build(blocked_inputs()).rows == ()


@pytest.mark.contract
def test_no_self_dependency(builder: GoldBuilder) -> None:
    assert isinstance(builder.depends_on, frozenset)
    assert builder.name not in builder.depends_on
    assert isinstance(builder.runs_when_blocked, bool)


@pytest.mark.contract
def test_fake_counts_results_per_check() -> None:
    """Só do fake: uma linha por check com a contagem, e a chamada registrada."""
    fake = FakeGoldBuilder("probe", runs_when_blocked=True)
    inputs = blocked_inputs()
    table = fake.build(inputs)
    assert [row["check"] for row in table.rows] == sorted({r.check for r in inputs.check_results})
    assert sum(row["n_results"] for row in table.rows) == len(inputs.check_results)  # type: ignore[misc]
    assert fake.calls == [inputs]


# --- mapeamento dos builders reais (fora da parametrização) -----------------------------


def _one(rows: tuple[Mapping[str, object], ...], **match: object) -> Mapping[str, object]:
    found = [row for row in rows if all(row[k] == v for k, v in match.items())]
    assert len(found) == 1, (match, len(found))
    return found[0]


@pytest.mark.contract
@pytest.mark.parametrize("inputs", [completed_inputs, blocked_inputs], ids=["completed", "blocked"])
def test_quality_checks_rows(inputs: Callable[[], GoldInputs]) -> None:
    """Uma linha por `QualityCheckResult`, com todos os campos copiados."""
    given = inputs()
    table = QualityChecksGoldBuilder().build(given)
    assert len(table.rows) == len(given.check_results)
    for result in given.check_results:
        row = _one(
            table.rows,
            check=result.check,
            kind=result.kind,
            horizon=result.horizon,
            model=result.model,
            seed=result.seed,
        )
        assert (row["severity"], row["outcome"]) == (result.severity.value, result.outcome.value)
        assert (row["occurrences"], row["value"], row["detail"]) == (
            result.occurrences,
            result.value,
            result.detail,
        )


@pytest.mark.contract
def test_quality_rows_no_prereg() -> None:
    table = QualityChecksGoldBuilder().build(completed_inputs())
    assert all("preregistration_ref" not in row for row in table.rows)
    assert QualityChecksGoldBuilder().runs_when_blocked is True


def _series(horizon: int, model: str, seed: int | None, sample: SampleKind) -> SeriesReports:
    [report] = [r for r in completed_inputs().horizon_reports if r.horizon == horizon]
    [series] = [s for s in report.series if (s.model, s.seed, s.sample) == (model, seed, sample)]
    return series


def _expected_metric_rows(series: SeriesReports) -> int:
    k = len(series.pinball.per_level)
    pairs = len(series.interval.per_pair)
    coverage = len(series.coverage.per_level) + 2 * len(series.coverage.per_pair)
    # grid_mean + pinball por τ + crps + (IS, largura) por par + ĉ por τ + (PICP, MPIW)
    # por par (vazios se não aplicável) + degeneração + guardrail + n avaliado
    return 1 + k + 1 + 2 * pairs + coverage + 3


@pytest.mark.contract
def test_metrics_rows_match_reports() -> None:
    inputs = completed_inputs()
    table = MetricsByRunGoldBuilder().build(inputs)
    series = _series(1, "tft", 1, SampleKind.MODEL_FULL)
    base = {"model": "tft", "seed": 1, "horizon": 1, "sample": "model_full"}
    grid = _one(table.rows, **base, metric="pinball_grid_mean")
    assert grid["value"] == series.pinball.grid_mean
    assert (grid["n_points"], grid["first_target_timestamp"], grid["last_target_timestamp"]) == (
        series.n_points,
        series.first_target_timestamp,
        series.last_target_timestamp,
    )
    assert grid["degeneracy_tolerance"] == inputs.parameters.degeneracy_tolerance
    for level, value in series.pinball.per_level:
        assert _one(table.rows, **base, metric="pinball", level_low=level)["value"] == value
    crps = _one(table.rows, **base, metric="crps_q")
    assert (crps["value"], crps["label"]) == (series.crps.crps_q, CRPS_Q_LABEL)
    for pair in series.interval.per_pair:
        levels = {"level_low": pair.lower_level, "level_high": pair.upper_level}
        assert _one(table.rows, **base, metric="interval_score", **levels)["value"] == (
            pair.mean_score
        )
        assert _one(table.rows, **base, metric="interval_width", **levels)["value"] == (
            pair.mean_width
        )
    for level, rate in series.coverage.per_level:
        assert _one(table.rows, **base, metric="coverage_rate", level_low=level)["value"] == rate
    for pair_coverage in series.coverage.per_pair:
        levels = {"level_low": pair_coverage.lower_level, "level_high": pair_coverage.upper_level}
        assert _one(table.rows, **base, metric="picp", **levels)["value"] == pair_coverage.picp
        mpiw = _one(table.rows, **base, metric="mpiw", **levels)
        assert (mpiw["value"], mpiw["label"]) == (pair_coverage.mpiw, MPIW_LABEL)
    assert _one(table.rows, **base, metric="degeneracy_rate")["value"] == (
        series.coverage.degeneracy.rate
    )
    assert _one(table.rows, **base, metric="guardrail_applied_rate")["value"] == (
        series.guardrail_applied_rate
    )
    assert _one(table.rows, **base, metric="coverage_n_evaluated")["value"] == (
        series.coverage.n_evaluated
    )
    naive = _series(1, "naive", None, SampleKind.MODEL_FULL)
    assert not naive.coverage.applicable
    assert (
        _one(
            table.rows,
            model="naive",
            seed=None,
            horizon=1,
            sample="model_full",
            metric="degeneracy_rate",
        )["value"]
        == 1.0
    )
    expected = sum(_expected_metric_rows(s) for r in inputs.horizon_reports for s in r.series)
    assert len(table.rows) == expected


@pytest.mark.contract
def test_calibration_rows_match_reports() -> None:
    """Linha escolhida (h = 2, cauda superior 0,95, DGT j = 1, banda 0,975) e cobertura."""
    inputs = completed_inputs()
    table = CalibrationTableGoldBuilder().build(inputs)
    series = _series(2, "tft", 2, SampleKind.COMMON)
    [row] = [
        c
        for c in series.calibration
        if c.christoffersen.levels == (0.95,)
        and not c.christoffersen.includes_degenerate
        and c.christoffersen.dgt_offset == 1
    ]
    band = row.wilson[1]
    report, stats = row.christoffersen, row.christoffersen.statistics
    got = _one(
        table.rows,
        model="tft",
        seed=2,
        horizon=2,
        sample="common",
        kind=report.kind.value,
        level_low=0.95,
        level_high=None,
        includes_degenerate=False,
        dgt_offset=1,
        dgt_step=2,
        band_level=band.band_level,
    )
    assert (got["n00"], got["n01"], got["n10"], got["n11"]) == stats.transitions
    assert (got["n_observed"], got["n_violations"]) == (stats.n_observed, stats.n_violations)
    assert (got["lr_uc"], got["p_uc"], got["lr_ind"], got["p_ind"], got["lr_cc"], got["p_cc"]) == (
        stats.lr_uc,
        report.p_uc,
        stats.lr_ind,
        report.p_ind,
        stats.lr_cc,
        report.p_cc,
    )
    assert (got["kupiec_pof"], got["kupiec_pof_p_value"]) == (
        stats.kupiec_pof,
        report.kupiec_pof_p_value,
    )
    assert got["independence_status"] == stats.independence_status.value
    assert got["independence_descriptive"] == report.independence_descriptive
    assert (got["wilson_lower"], got["wilson_upper"], got["wilson_contains_nominal"]) == (
        band.lower,
        band.upper,
        band.contains_nominal,
    )
    assert (got["var_level"], got["var_label"]) == (row.var_level, VAR_DESCRIPTIVE_LABEL)
    assert got["min_violations"] == inputs.parameters.min_violations
    interval = _one(
        table.rows,
        model="tft",
        seed=2,
        horizon=2,
        sample="common",
        kind="interval",
        level_low=0.05,
        level_high=0.95,
        includes_degenerate=True,
        dgt_offset=None,
        dgt_step=None,
        band_level=0.95,
    )
    assert (interval["var_level"], interval["var_label"]) == (None, None)
    # linha "sem lacunas" (includes_degenerate=True) do intervalo: todos os campos
    [gapless] = [
        c
        for c in series.calibration
        if c.christoffersen.levels == (0.05, 0.95)
        and c.christoffersen.includes_degenerate
        and c.christoffersen.dgt_step is None
    ]
    g_report, g_stats, g_band = (
        gapless.christoffersen,
        gapless.christoffersen.statistics,
        gapless.wilson[0],
    )
    assert (
        interval["n00"],
        interval["n01"],
        interval["n10"],
        interval["n11"],
    ) == g_stats.transitions
    assert (interval["lr_uc"], interval["p_uc"], interval["lr_ind"], interval["p_ind"]) == (
        g_stats.lr_uc,
        g_report.p_uc,
        g_stats.lr_ind,
        g_report.p_ind,
    )
    assert (interval["lr_cc"], interval["p_cc"]) == (g_stats.lr_cc, g_report.p_cc)
    assert (interval["violation_rate"], interval["tolerance"], interval["degeneracy_rate"]) == (
        g_report.violation_rate,
        g_report.tolerance,
        g_report.degeneracy_rate,
    )
    assert interval["violation_rate"] != interval["degeneracy_rate"]
    assert (
        interval["n_points"],
        interval["first_target_timestamp"],
        interval["last_target_timestamp"],
    ) == (series.n_points, series.first_target_timestamp, series.last_target_timestamp)
    assert interval["first_target_timestamp"] != interval["last_target_timestamp"]
    assert (
        interval["wilson_applicable"],
        interval["wilson_estimate"],
        interval["serial_dependence_warning"],
    ) == (g_band.applicable, g_band.estimate, g_band.serial_dependence_warning)
    assert all(r["dgt_step"] is None for r in table.rows if r["horizon"] == 1)
    expected = sum(
        len(c.wilson) for r in inputs.horizon_reports for s in r.series for c in s.calibration
    )
    assert len(table.rows) == expected


@pytest.mark.contract
def test_dm_rows_match_families() -> None:
    inputs = completed_inputs()
    table = DmResultsGoldBuilder().build(inputs)
    k = len(inputs.horizon_reports[0].paired.models)
    estimators = len(inputs.parameters.dm_variance_estimators)
    assert len(table.rows) == (k - 1) * estimators * len(inputs.horizon_reports)
    report = inputs.horizon_reports[1]
    family = report.dm_families[1]
    comparison = family.comparisons[0]
    got = _one(
        table.rows,
        horizon=report.horizon,
        variance_estimator=family.variance_estimator.value,
        candidate=family.candidate,
        comparator=comparison.comparator,
    )
    dm = comparison.dm
    assert (got["statistic"], got["p_value"], got["degrees_of_freedom"]) == (
        dm.statistic,
        dm.p_value,
        dm.degrees_of_freedom,
    )
    assert (got["mean_differential"], got["long_run_variance"]) == (
        dm.mean_differential,
        dm.long_run_variance,
    )
    assert (got["horizon_used"], got["fallback_applied"], got["n_points"]) == (
        dm.horizon_used,
        dm.fallback_applied,
        dm.n_points,
    )
    assert (got["adjusted_p_value"], got["rejected"], got["alpha"]) == (
        comparison.adjusted_p_value,
        comparison.rejected,
        family.alpha,
    )
    assert (got["common_first_target_timestamp"], got["common_last_target_timestamp"]) == (
        report.common_first_target_timestamp,
        report.common_last_target_timestamp,
    )


@pytest.mark.contract
def test_mcs_rows_match_reports() -> None:
    inputs = completed_inputs()
    table = McsResultsGoldBuilder().build(inputs)
    k = len(inputs.horizon_reports[0].paired.models)
    assert len(table.rows) == k * len(inputs.parameters.mcs_schemes) * len(inputs.horizon_reports)
    for report in inputs.mcs_reports:
        estimates = inputs.block_estimates[report.horizon]
        for rank, elimination in enumerate(report.eliminations, start=1):
            got = _one(
                table.rows,
                horizon=report.horizon,
                scheme=report.scheme.value,
                model=elimination.model,
            )
            assert got["elimination_rank"] == rank
            assert (got["step_p_value"], got["mcs_p_value"]) == (
                elimination.step_p_value,
                elimination.mcs_p_value,
            )
            assert got["included"] == (elimination.model in report.included)
            assert (got["reps"], got["seed"], got["block_size"], got["generator"]) == (
                report.reps,
                report.seed,
                report.block_size,
                report.generator,
            )
            assert (got["alpha"], got["statistic"], got["n_points"]) == (
                report.alpha,
                report.statistic,
                report.n_points,
            )
            assert got["max_block_estimate"] == max(e.value for e in estimates)  # type: ignore[type-var]
            assert got["block_estimates"] == ";".join(
                f"{a}|{b}={e.value!r}" for e in estimates for a, b in (e.pair,)
            )


@pytest.mark.contract
def test_row_keys_unique(builder: GoldBuilder) -> None:
    table = builder.build(completed_inputs())
    keys = [tuple(row[column] for column in table.key) for row in table.rows]
    assert len(keys) == len(set(keys))


# Chave e colunas LITERAIS do technical 6.4 §1 "Tabelas gold" (cópia deliberada: a
# suíte reprova renomear/remover coluna ou reordenar a chave do builder).
_PARTITION_COLUMNS = {"asset", "parent_sweep_id"}
_PREREG = {"preregistration_ref"}
_SCHEMAS: dict[str, tuple[tuple[str, ...], set[str]]] = {
    "quality_checks": (
        ("check", "kind", "horizon", "model", "seed"),
        {"severity", "outcome", "occurrences", "value", "detail"} | _PARTITION_COLUMNS,
    ),
    "metrics_by_run": (
        ("model", "seed", "horizon", "sample", "metric", "level_low", "level_high"),
        {
            "value",
            "label",
            "n_points",
            "first_target_timestamp",
            "last_target_timestamp",
            "degeneracy_tolerance",
        }
        | _PARTITION_COLUMNS
        | _PREREG,
    ),
    "calibration_table": (
        (
            "model",
            "seed",
            "horizon",
            "sample",
            "kind",
            "level_low",
            "level_high",
            "includes_degenerate",
            "dgt_offset",
            "dgt_step",
            "band_level",
        ),
        {
            "n_points",
            "first_target_timestamp",
            "last_target_timestamp",
            "violation_rate",
            "tolerance",
            "degeneracy_rate",
            "min_violations",
            "n_observed",
            "n_violations",
            "n00",
            "n01",
            "n10",
            "n11",
            "kupiec_pof",
            "kupiec_pof_p_value",
            "lr_uc",
            "p_uc",
            "lr_ind",
            "p_ind",
            "lr_cc",
            "p_cc",
            "independence_status",
            "independence_descriptive",
            "wilson_applicable",
            "wilson_estimate",
            "wilson_lower",
            "wilson_upper",
            "wilson_contains_nominal",
            "serial_dependence_warning",
            "var_level",
            "var_label",
        }
        | _PARTITION_COLUMNS
        | _PREREG,
    ),
    "dm_results": (
        ("horizon", "variance_estimator", "candidate", "comparator"),
        {
            "n_points",
            "common_first_target_timestamp",
            "common_last_target_timestamp",
            "mean_differential",
            "long_run_variance",
            "statistic",
            "degrees_of_freedom",
            "p_value",
            "horizon_used",
            "fallback_applied",
            "adjusted_p_value",
            "rejected",
            "alpha",
        }
        | _PARTITION_COLUMNS
        | _PREREG,
    ),
    "mcs_results": (
        ("horizon", "scheme", "model"),
        {
            "elimination_rank",
            "step_p_value",
            "mcs_p_value",
            "included",
            "alpha",
            "statistic",
            "reps",
            "seed",
            "block_size",
            "generator",
            "n_points",
            "max_block_estimate",
            "block_estimates",
        }
        | _PARTITION_COLUMNS
        | _PREREG,
    ),
}


@pytest.mark.contract
@pytest.mark.parametrize("name", list(_SCHEMAS))
def test_real_tables_match_schema(name: str) -> None:
    """Chave e conjunto de colunas de cada tabela real = o §1 do technical, literalmente."""
    builder = BUILDERS[name]()
    table = builder.build(completed_inputs())
    key, others = _SCHEMAS[name]
    assert table.key == key
    assert set(table.columns) == set(key) | others


@pytest.mark.contract
def test_dm_rows_adjusted_all_comparisons() -> None:
    """Toda comparação de toda família: p ajustado e decisão de Holm copiados do relatório."""
    inputs = completed_inputs()
    table = DmResultsGoldBuilder().build(inputs)
    comparisons = [
        (report, family, comparison)
        for report in inputs.horizon_reports
        for family in report.dm_families
        for comparison in family.comparisons
    ]
    # pré-condição: o ajuste de Holm muda algum p (senão o teste não discrimina)
    assert any(c.adjusted_p_value != c.dm.p_value for _, _, c in comparisons)
    for report, family, comparison in comparisons:
        got = _one(
            table.rows,
            horizon=report.horizon,
            variance_estimator=family.variance_estimator.value,
            candidate=family.candidate,
            comparator=comparison.comparator,
        )
        assert got["adjusted_p_value"] == comparison.adjusted_p_value
        assert got["rejected"] == comparison.rejected
        assert got["p_value"] == comparison.dm.p_value


@pytest.mark.contract
def test_mcs_rows_max_block_distinct() -> None:
    """Estimativas b̂_sb distintas por par (2,2; 4,7; 3,1): o máximo e a lista em ordem."""
    inputs = completed_inputs()
    values = (2.2, 4.7, 3.1)
    distinct = {
        horizon: tuple(
            dataclasses.replace(estimate, value=values[i % len(values)])
            for i, estimate in enumerate(estimates)
        )
        for horizon, estimates in inputs.block_estimates.items()
    }
    assert all(len(estimates) == len(values) for estimates in distinct.values())
    table = McsResultsGoldBuilder().build(dataclasses.replace(inputs, block_estimates=distinct))
    assert table.rows
    for row in table.rows:
        estimates = distinct[row["horizon"]]  # type: ignore[index]
        assert row["max_block_estimate"] == max(values)
        assert row["block_estimates"] == ";".join(
            f"{e.pair[0]}|{e.pair[1]}={e.value!r}" for e in estimates
        )


# --- Stage 6.5: builders com as chaves do schema dono (gold_schema) --------------------

_REAL_BUILDERS = [name for name in BUILDERS if name != "fake"]


@pytest.mark.contract
@pytest.mark.parametrize("name", _REAL_BUILDERS)
def test_builders_use_schema_keys(name: str) -> None:
    """Nome e chave de cada tabela real são os do `gold_schema` (ADR 6.5.0005 item 2)."""
    table = BUILDERS[name]().build(completed_inputs())

    schema = GOLD_SCHEMAS[f"gold_{name}"]
    assert table.name == schema.name
    assert table.key == schema.key


@pytest.mark.contract
@pytest.mark.parametrize("name", _REAL_BUILDERS)
def test_schema_columns_written(name: str) -> None:
    """Chave e colunas lidas do schema são colunas escritas pelo builder."""
    table = BUILDERS[name]().build(completed_inputs())
    schema = GOLD_SCHEMAS[table.name]

    assert table.rows, f"{name} built no rows from the completed inputs"
    written = set(table.columns)
    assert set(schema.key) <= written
    assert set(schema.read_columns) <= written
