"""Serviço de domínio `SeriesAssembly` — dono único das regras de alinhamento do gold (6.4).

Stdlib-only + o VO `QuantileForecast` do fornecedor (aresta de DADOS declarada no
contrato `bc-independence` — ADR `6_4_0003` item 3, `6_4_0004` item 5, `0_0_0053` item
3). Concept 6.4 §4 `SeriesAssembly`, I1-I10, D1, D2.

Recebe as linhas longas do silver já juntadas ao `dim_run` (`ForecastRecord`), os runs
do cohort (`CohortRun`) e o realizado do dataset (`RealizedReturns`) e devolve um
`AssembledCohort`:

- toda violação das regras I3-I10 vira um `AlignmentFinding` — **nunca exceção** (D1);
  todos os achados são coletados antes de devolver, em ordem determinística (ordem do
  `AlignmentKind`, depois horizonte, modelo e seed; `None` antes de valor);
- só sem achado as séries são montadas: por horizonte do comando, por (modelo, seed),
  uma `CoverageSeries` `full` (toda a série) e uma `common` (a fatia da interseção dos
  intervalos do horizonte — ADR `6_4_0007`), com o `QuantileForecast` construído
  **direto** dos valores persistidos (`value_raw`, `value_guardrail`,
  `guardrail_applied`) — nunca por `from_raw` (I6) — e `realized` lido do
  `RealizedReturns` (I7);
- a duplicata (mesmo modelo, seed, horizonte, alvo e nível) é achado, sem escolha
  entre as linhas (D2; ADR `6_4_0003`).

`ValueError` só para erro de CHAMADA (entradas estruturais: `horizons`,
`window_deficits`, `required_models`, run duplicado, fato fora dos runs — a leitura já
descartou os fatos fora do cohort, ADR `6_4_0004` item 2). Valor não-finito em
`value_guardrail` com o resto alinhado não é achado: é violação de invariante do
fornecedor e a `CoverageSeries` ergue (ADR `6_1_0002` item 5; technical 6.4 §7).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects._paired_inputs import (
    check_points,
)
from financial_forecasting.features.evaluation.domain.value_objects.assembled_cohort import (
    AlignmentFinding,
    AlignmentKind,
    AlignmentReport,
    AssembledCohort,
    HorizonSamples,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    MIN_BLOCK_LENGTH_OBS,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)

_TEST_SPLIT = "test"
_KIND_ORDER = {kind: position for position, kind in enumerate(AlignmentKind)}

SeriesKey = tuple[str, int | None]  # (modelo, seed)


def _seed_key(seed: int | None) -> tuple[int, int]:
    # `None` (modelo determinístico) antes de qualquer int
    return (0, 0) if seed is None else (1, seed)


def _series_key(key: SeriesKey) -> tuple[str, tuple[int, int]]:
    return (key[0], _seed_key(key[1]))


def _finding_key(finding: AlignmentFinding) -> tuple[object, ...]:
    return (
        _KIND_ORDER[finding.kind],
        (0, 0) if finding.horizon is None else (1, finding.horizon),
        (0, "") if finding.model is None else (1, finding.model),
        _seed_key(finding.seed),
        finding.detail,
    )


@dataclass
class _Findings:
    """Coletor de achados (mutável, local a uma chamada de `assemble`)."""

    items: list[AlignmentFinding] = field(default_factory=list)

    def add(
        self,
        kind: AlignmentKind,
        detail: str,
        *,
        horizon: int | None = None,
        model: str | None = None,
        seed: int | None = None,
    ) -> None:
        self.items.append(
            AlignmentFinding(kind=kind, horizon=horizon, model=model, seed=seed, detail=detail)
        )

    def sorted(self) -> tuple[AlignmentFinding, ...]:
        return tuple(sorted(set(self.items), key=_finding_key))


@dataclass(frozen=True)
class _Point:
    """Um ponto (modelo, seed, h, alvo): as linhas por nível, na ordem dos níveis."""

    target_timestamp: str
    by_level: Mapping[float, tuple[ForecastRecord, ...]]


class SeriesAssembly:
    """Montagem das séries alinhadas do cohort, com achados em vez de exceção (D1)."""

    @staticmethod
    def assemble(  # noqa: PLR0913 — assinatura literal do concept 6.4 §4
        records: Sequence[ForecastRecord],
        runs: Sequence[CohortRun],
        realized: RealizedReturns,
        *,
        horizons: tuple[int, ...],
        window_deficits: Mapping[str, int],
        required_models: frozenset[str],
    ) -> AssembledCohort:
        """Aplica I3-I10 e, sem achado, monta as duas amostras por horizonte.

        Args:
            records: linhas longas do silver juntadas ao `dim_run` (qualquer split).
            runs: runs do cohort (`run_id` únicos).
            realized: sessões do dataset e o `target_return` de cada uma.
            horizons: horizontes do comando (não-vazio, estritamente crescente).
            window_deficits: déficit de janela aceito por modelo (int ≥ 0; ausente ⇒ 0).
            required_models: modelos que o cohort precisa ter (o candidato).

        Returns:
            O `AssembledCohort`: o relatório e, sem achado, as amostras por horizonte.

        Raises:
            ValueError: entrada estrutural inválida (erro de chamada, não de dado).
        """
        _check_call(records, runs, horizons, window_deficits, required_models)
        runs_by_id = {run.run_id: run for run in runs}
        findings = _Findings()
        tested = [record for record in records if record.split == _TEST_SPLIT]
        _check_identity(tested, runs, runs_by_id, findings)
        universe = sorted({(run.model, run.seed) for run in runs}, key=_series_key)
        points = _group_points(tested, runs_by_id, horizons, findings)
        _check_points(points, realized, findings)
        grids = _check_grids(points, findings)
        _check_coverage(points, runs, universe, horizons, required_models, findings)
        intervals = _check_contiguity(points, realized, window_deficits, findings)
        common_points = _common_points(intervals, findings)
        report = AlignmentReport(findings=findings.sorted(), common_points=common_points)
        if report.findings:
            return AssembledCohort(alignment=report, horizons=())
        return AssembledCohort(
            alignment=report,
            horizons=tuple(
                _build_samples(horizon, points[horizon], grids, intervals[horizon], realized)
                for horizon in horizons
            ),
        )


# --- 1. entradas estruturais -----------------------------------------------------------


def _check_call(
    records: Sequence[ForecastRecord],
    runs: Sequence[CohortRun],
    horizons: tuple[int, ...],
    window_deficits: Mapping[str, int],
    required_models: frozenset[str],
) -> None:
    if not isinstance(horizons, tuple) or not horizons:
        raise ValueError(f"horizons must be a non-empty tuple, got {horizons!r}")
    for horizon in horizons:
        validate_horizon(horizon, field="horizons")
    if list(horizons) != sorted(set(horizons)):
        raise ValueError(f"horizons must be strictly increasing, got {horizons}")
    if not isinstance(window_deficits, Mapping):
        raise ValueError(f"window_deficits must be a Mapping, got {window_deficits!r}")
    for model, deficit in window_deficits.items():
        if isinstance(deficit, bool) or not isinstance(deficit, int) or deficit < 0:
            raise ValueError(f"window_deficits[{model!r}] must be an int >= 0, got {deficit!r}")
    if not isinstance(required_models, frozenset):
        raise ValueError(f"required_models must be a frozenset, got {required_models!r}")
    run_ids = [run.run_id for run in runs]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError(f"runs must have unique run_id, got {sorted(run_ids)}")
    known = set(run_ids)
    outside = sorted({record.run_id for record in records} - known)
    if outside:
        raise ValueError(
            f"records reference run_ids outside the cohort runs: {outside} (the read "
            "must discard facts outside the cohort)"
        )


# --- 3. identidade (I3) ----------------------------------------------------------------


def _check_identity(
    tested: Sequence[ForecastRecord],
    runs: Sequence[CohortRun],
    runs_by_id: Mapping[str, CohortRun],
    findings: _Findings,
) -> None:
    feature_sets = sorted({run.feature_set_name for run in runs})
    if len(feature_sets) > 1:
        findings.add(
            AlignmentKind.MULTIPLE_FEATURE_SETS, f"feature_set_name values: {feature_sets}"
        )
    signatures: dict[str, set[str]] = defaultdict(set)
    for run in runs:
        signatures[run.model].add(run.config_signature)
    for model, values in signatures.items():
        if len(values) > 1:
            findings.add(
                AlignmentKind.MULTIPLE_CONFIG_SIGNATURES,
                f"config_signature values: {sorted(values)}",
                model=model,
            )
    with_test = {record.run_id for record in tested}
    for run in runs:
        if run.run_id not in with_test:
            findings.add(
                AlignmentKind.ORPHAN_RUN,
                f"run {run.run_id!r} (fold {run.fold!r}) has no test prediction",
                model=run.model,
                seed=run.seed,
            )
    for record in tested:
        run = runs_by_id[record.run_id]
        if record.model != run.model:
            findings.add(
                AlignmentKind.MODEL_VERSION_MISMATCH,
                f"run {run.run_id!r}: fact model_version {record.model!r} != dim_run "
                f"model_version {run.model!r}",
                horizon=record.horizon,
                model=run.model,
                seed=run.seed,
            )


# --- 4. agrupamento e duplicatas (I4) --------------------------------------------------

Points = dict[int, dict[SeriesKey, list[_Point]]]


def _group_points(
    tested: Sequence[ForecastRecord],
    runs_by_id: Mapping[str, CohortRun],
    horizons: tuple[int, ...],
    findings: _Findings,
) -> Points:
    wanted = set(horizons)
    grouped: dict[tuple[int, SeriesKey, str], dict[float, list[ForecastRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in tested:
        if record.horizon not in wanted:
            continue  # I1: só os horizontes do comando
        run = runs_by_id[record.run_id]
        key = (record.horizon, (run.model, run.seed), record.target_timestamp)
        grouped[key][record.quantile_level].append(record)
    points: Points = {horizon: defaultdict(list) for horizon in horizons}
    for (horizon, series, target), by_level in grouped.items():
        repeated = sorted(level for level, rows in by_level.items() if len(rows) > 1)
        if repeated:
            findings.add(
                AlignmentKind.DUPLICATE_POINT,
                f"target {target!r}: levels {repeated} observed more than once",
                horizon=horizon,
                model=series[0],
                seed=series[1],
            )
        points[horizon][series].append(
            _Point(
                target_timestamp=target,
                by_level={level: tuple(by_level[level]) for level in sorted(by_level)},
            )
        )
    for per_series in points.values():
        for series_points in per_series.values():
            series_points.sort(key=lambda point: point.target_timestamp)
    return points


def _all_rows(point: _Point) -> Iterable[ForecastRecord]:
    for rows in point.by_level.values():
        yield from rows


# --- 5. índices de sessão e realizado (I5, I7) -----------------------------------------


def _check_points(points: Points, realized: RealizedReturns, findings: _Findings) -> None:
    for horizon, per_series in points.items():
        for (model, seed), series_points in per_series.items():
            for point in series_points:
                _check_point(point, horizon, model, seed, realized, findings)


def _check_point(  # noqa: PLR0913 — um ponto e o seu escopo (h, modelo, seed)
    point: _Point,
    horizon: int,
    model: str,
    seed: int | None,
    realized: RealizedReturns,
    findings: _Findings,
) -> None:
    target = point.target_timestamp
    target_index = realized.index_of(target)
    if target_index is None:
        findings.add(
            AlignmentKind.REALIZED_MISSING,
            f"target {target!r} is not a session of the dataset",
            horizon=horizon,
            model=model,
            seed=seed,
        )
    decisions = sorted({(row.decision_timestamp, row.decision_idx) for row in _all_rows(point)})
    for decision_timestamp, decision_idx in decisions:
        decision_index = realized.index_of(decision_timestamp)
        if decision_index != decision_idx:
            findings.add(
                AlignmentKind.DECISION_INDEX_MISMATCH,
                f"target {target!r}: decision {decision_timestamp!r} has dataset index "
                f"{decision_index} but decision_idx {decision_idx}",
                horizon=horizon,
                model=model,
                seed=seed,
            )
        if (
            target_index is not None
            and decision_index is not None
            and target_index - decision_index != horizon
        ):
            findings.add(
                AlignmentKind.HORIZON_LABEL_MISMATCH,
                f"target {target!r} is {target_index - decision_index} sessions after "
                f"decision {decision_timestamp!r}, not h={horizon}",
                horizon=horizon,
                model=model,
                seed=seed,
            )


# --- 6. grade e guardrail (I6) ---------------------------------------------------------


def _check_grids(points: Points, findings: _Findings) -> dict[int, tuple[float, ...]]:
    grids: dict[int, tuple[float, ...]] = {}
    for horizon, per_series in points.items():
        by_model: dict[str, set[float]] = defaultdict(set)
        for (model, _), series_points in per_series.items():
            for point in series_points:
                by_model[model].update(point.by_level)
        for (model, seed), series_points in per_series.items():
            grid = by_model[model]
            for point in series_points:
                missing = sorted(grid - set(point.by_level))
                if missing:
                    findings.add(
                        AlignmentKind.GRID_INCOMPLETE,
                        f"target {point.target_timestamp!r}: missing levels {missing}",
                        horizon=horizon,
                        model=model,
                        seed=seed,
                    )
                flags = {row.guardrail_applied for row in _all_rows(point)}
                if len(flags) > 1:
                    findings.add(
                        AlignmentKind.GUARDRAIL_FLAG_MISMATCH,
                        f"target {point.target_timestamp!r}: guardrail_applied differs "
                        "between levels",
                        horizon=horizon,
                        model=model,
                        seed=seed,
                    )
        distinct = {tuple(sorted(grid)) for grid in by_model.values()}
        if len(distinct) > 1:
            findings.add(
                AlignmentKind.GRID_DIVERGENT,
                "grids by model: "
                + "; ".join(f"{m}={sorted(by_model[m])}" for m in sorted(by_model)),
                horizon=horizon,
            )
        if by_model:
            grids[horizon] = tuple(sorted(next(iter(distinct))))
    return grids


# --- 7. cobertura (I9) -----------------------------------------------------------------


def _check_coverage(  # noqa: PLR0913 — as quatro regras de cobertura do I9
    points: Points,
    runs: Sequence[CohortRun],
    universe: Sequence[SeriesKey],
    horizons: tuple[int, ...],
    required_models: frozenset[str],
    findings: _Findings,
) -> None:
    cohort_folds = {run.fold for run in runs}
    folds: dict[SeriesKey, set[str | None]] = defaultdict(set)
    for run in runs:
        folds[run.model, run.seed].add(run.fold)
    for key in universe:
        if folds[key] != cohort_folds:
            findings.add(
                AlignmentKind.FOLD_COVERAGE,
                f"folds {sorted(map(str, folds[key]))} != cohort folds "
                f"{sorted(map(str, cohort_folds))}",
                model=key[0],
                seed=key[1],
            )
    for horizon in horizons:
        present = points[horizon]
        if not present:
            findings.add(
                AlignmentKind.HORIZON_MISSING, "no test point in this horizon", horizon=horizon
            )
            continue
        for key in universe:
            if key not in present:
                findings.add(
                    AlignmentKind.SEED_HORIZON_COVERAGE,
                    "no test point in this horizon",
                    horizon=horizon,
                    model=key[0],
                    seed=key[1],
                )
    for model in sorted(required_models - {run.model for run in runs}):
        findings.add(
            AlignmentKind.REQUIRED_MODEL_MISSING, "required model not in the cohort", model=model
        )


# --- 8. contiguidade (I8) --------------------------------------------------------------

Intervals = dict[int, dict[SeriesKey, tuple[int, int]]]


def _check_contiguity(
    points: Points,
    realized: RealizedReturns,
    window_deficits: Mapping[str, int],
    findings: _Findings,
) -> Intervals:
    intervals: Intervals = {}
    for horizon, per_series in points.items():
        spans: dict[SeriesKey, tuple[int, int]] = {}
        for (model, seed), series_points in per_series.items():
            indices = sorted(
                index
                for index in (realized.index_of(p.target_timestamp) for p in series_points)
                if index is not None
            )
            if not indices:
                continue  # todo alvo fora do dataset: já é `realized_missing`
            gaps = [b for a, b in pairwise(indices) if b - a != 1]
            if gaps:
                findings.add(
                    AlignmentKind.INTERIOR_GAP,
                    f"{len(gaps)} gap(s) in the session index, first before "
                    f"{realized.timestamps[gaps[0]]!r}",
                    horizon=horizon,
                    model=model,
                    seed=seed,
                )
            spans[model, seed] = (indices[0], indices[-1])
        intervals[horizon] = spans
        if not spans:
            continue
        earliest = min(first for first, _ in spans.values())
        latest = max(last for _, last in spans.values())
        for (model, seed), (first, last) in spans.items():
            if last != latest:
                findings.add(
                    AlignmentKind.TRUNCATED_SUFFIX,
                    f"series ends at {realized.timestamps[last]!r}, the horizon at "
                    f"{realized.timestamps[latest]!r}",
                    horizon=horizon,
                    model=model,
                    seed=seed,
                )
            deficit = window_deficits.get(model, 0)
            if first - earliest > deficit:
                findings.add(
                    AlignmentKind.PREFIX_OVER_DEFICIT,
                    f"series starts {first - earliest} sessions after the earliest "
                    f"series of the horizon; accepted deficit {deficit}",
                    horizon=horizon,
                    model=model,
                    seed=seed,
                )
    return intervals


# --- 9. amostra comum e T mínimo (I8, I10) ---------------------------------------------


def _common_points(intervals: Intervals, findings: _Findings) -> tuple[tuple[int, int], ...]:
    recorded: list[tuple[int, int]] = []
    for horizon in sorted(intervals):
        spans = intervals[horizon]
        if not spans:
            continue
        start = max(first for first, _ in spans.values())
        end = min(last for _, last in spans.values())
        n_points = end - start + 1
        reason = None
        try:
            check_points(n_points, horizon)
        except ValueError as error:
            reason = str(error)
        if reason is None and n_points < MIN_BLOCK_LENGTH_OBS:
            reason = f"T={n_points} < MIN_BLOCK_LENGTH_OBS={MIN_BLOCK_LENGTH_OBS}"
        if reason is not None:
            findings.add(
                AlignmentKind.COMMON_SAMPLE_TOO_SHORT,
                f"common sample: {reason}",
                horizon=horizon,
            )
        if n_points >= 1:  # interseção vazia: só o achado, sem (h, T) (T ≥ 1 no VO)
            recorded.append((horizon, n_points))
    return tuple(recorded)


# --- 10. as duas amostras --------------------------------------------------------------


def _build_samples(
    horizon: int,
    per_series: Mapping[SeriesKey, Sequence[_Point]],
    grids: Mapping[int, tuple[float, ...]],
    spans: Mapping[SeriesKey, tuple[int, int]],
    realized: RealizedReturns,
) -> HorizonSamples:
    levels = grids[horizon]
    start = max(first for first, _ in spans.values())
    end = min(last for _, last in spans.values())
    keys = sorted(per_series, key=_series_key)
    models = tuple(sorted({model for model, _ in keys}))
    seeds: dict[str, tuple[int | None, ...]] = {
        model: tuple(seed for m, seed in keys if m == model) for model in models
    }
    full: dict[str, tuple[CoverageSeries, ...]] = {}
    common: dict[str, tuple[CoverageSeries, ...]] = {}
    for model in models:
        full_series = []
        common_series = []
        for seed in seeds[model]:
            series_points = per_series[model, seed]
            full_series.append(_coverage(horizon, levels, series_points, realized))
            inside = [
                point
                for point in series_points
                if start <= _index(realized, point.target_timestamp) <= end
            ]
            common_series.append(_coverage(horizon, levels, inside, realized))
        full[model] = tuple(full_series)
        common[model] = tuple(common_series)
    return HorizonSamples(
        horizon=horizon,
        models=models,
        levels=levels,
        seeds=seeds,
        full=full,
        common=common,
        n_common=end - start + 1,
        common_first_target_timestamp=realized.timestamps[start],
        common_last_target_timestamp=realized.timestamps[end],
    )


def _index(realized: RealizedReturns, timestamp: str) -> int:
    index = realized.index_of(timestamp)
    if index is None:  # pragma: no cover — sem achado, todo alvo está no índice (I7)
        raise AssertionError(f"target {timestamp!r} outside the dataset without a finding")
    return index


def _coverage(
    horizon: int,
    levels: tuple[float, ...],
    series_points: Sequence[_Point],
    realized: RealizedReturns,
) -> CoverageSeries:
    forecasts = []
    for point in series_points:
        rows = [point.by_level[level][0] for level in levels]
        # I6: o VO do fornecedor com os valores PERSISTIDOS — nunca `from_raw`
        forecasts.append(
            QuantileForecast(
                levels=levels,
                raw_values=tuple(row.value_raw for row in rows),
                guardrail_values=tuple(row.value_guardrail for row in rows),
                guardrail_applied=rows[0].guardrail_applied,
            )
        )
    return CoverageSeries(
        horizon=horizon,
        levels=levels,
        target_timestamps=tuple(point.target_timestamp for point in series_points),
        forecasts=tuple(forecasts),
        realized=tuple(realized.realized_at(point.target_timestamp) for point in series_points),
    )
