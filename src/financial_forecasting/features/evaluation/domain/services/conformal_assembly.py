"""Serviço de domínio `ConformalAssembly` — unidades calib/teste a partir do silver (ADR 7.2.0003).

Stdlib-only, sem import do `inference` (concept 7.2 §4 "Regras da montagem", C9, I14).
Roda só quando o `SeriesAssembly` não tem achado. Por run do candidato e horizonte do
comando, monta uma unidade (fold, seed, horizonte):

- calib só dos registros `split = "calib"` do próprio run, teste só dos `split = "test"`
  do próprio run (`early_stop` e qualquer outro split nunca entram, I14);
- o calib passa pelas **mesmas** regras que o `SeriesAssembly` aplica ao teste, pelas
  funções públicas dele (`duplicate_levels`, `index_violations`, `missing_levels`): uma
  definição só por regra;
- realizado do calib do `RealizedReturns`, no alvo; grades por nível = `value_guardrail`
  (o vetor rearranjado, I2), nunca `value_raw`;
- o join teste ↔ série nativa é por `target_timestamp`, nunca por posição: os alvos de
  teste da unidade têm de ser exatamente os alvos da série nativa completa no intervalo
  do fold;
- `fold` chega como `str`: a montagem converte com `int(fold)`; fold que não é inteiro
  (inclusive `None`) vira unidade `undefined` com o fold cru em `fold_raw`. Seed `None`
  também vira `undefined`.

Qualquer violação vira `status = "undefined"` com o motivo — nunca `AlignmentFinding`,
porque o conformal não está no caminho do veredito.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

from financial_forecasting.features.evaluation.domain.services.series_assembly import (
    RuleViolation,
    duplicate_levels,
    index_violations,
    missing_levels,
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

OK: str = "ok"
UNDEFINED: str = "undefined"
NO_FOLD = "<none>"
_CALIB = "calib"
_TEST = "test"

CalibPoint = tuple[str, str, Mapping[float, float], float]  # (decisão, alvo, grade, y)
TestPoint = tuple[str, str, Mapping[float, float]]  # (decisão, alvo, grade)


@dataclass(frozen=True)
class ConformalUnitAssembly:
    """Uma unidade (fold, seed, horizonte) em primitivos; o `RefreshGold` mapeia ao DTO."""

    fold_index: int | None  # None ⇔ o fold do run não é inteiro (unidade undefined)
    fold_raw: str  # o fold cru do CohortRun ("<none>" quando None)
    seed: int | None  # None ⇔ seed ausente no run (unidade undefined)
    horizon: int
    calib: tuple[CalibPoint, ...]
    test: tuple[TestPoint, ...]
    status: str  # "ok" | "undefined"
    reason: str | None


@dataclass(frozen=True)
class ConformalAssemblyResult:
    """As unidades e, por (seed, h), o fold de cada ponto da série nativa completa."""

    units: tuple[ConformalUnitAssembly, ...]
    full_series_folds: Mapping[tuple[int, int], tuple[int | None, ...]]


def _fold_index(fold: str | None) -> int | None:
    if fold is None:
        return None
    try:
        return int(fold)
    except ValueError:
        return None


@dataclass(frozen=True)
class _Group:
    target: str
    by_level: Mapping[float, tuple[ForecastRecord, ...]]


def _groups(rows: Sequence[ForecastRecord]) -> list[_Group]:
    grouped: dict[str, dict[float, list[ForecastRecord]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row.target_timestamp][row.quantile_level].append(row)
    return [
        _Group(target, {level: tuple(found) for level, found in by_level.items()})
        for target, by_level in sorted(grouped.items())
    ]


def _violation(
    groups: list[_Group], *, horizon: int, levels: tuple[float, ...], realized: RealizedReturns
) -> RuleViolation | None:
    """A primeira violação das regras do `SeriesAssembly` nos pontos (ou nada)."""
    for group in groups:
        duplicate = duplicate_levels(group.by_level, target_timestamp=group.target)
        if duplicate is not None:
            return duplicate
        missing = missing_levels(
            present=group.by_level, expected=levels, target_timestamp=group.target
        )
        if missing is not None:
            return missing
        found = index_violations(
            target_timestamp=group.target,
            decisions=(
                (row.decision_timestamp, row.decision_idx)
                for rows in group.by_level.values()
                for row in rows
            ),
            horizon=horizon,
            realized=realized,
        )
        if found:
            return found[0]
    return None


def _grid(group: _Group, levels: tuple[float, ...]) -> Mapping[float, float]:
    return {level: group.by_level[level][0].value_guardrail for level in levels}


def _decision(group: _Group) -> tuple[str, int]:
    row = next(iter(group.by_level.values()))[0]
    return row.decision_timestamp, row.decision_idx


class ConformalAssembly:
    """Montagem das unidades conformais do candidato (ver docstring do módulo)."""

    @staticmethod
    def assemble(  # noqa: PLR0913 — assinatura literal do concept 7.2 §4
        records: Sequence[ForecastRecord],
        runs: Sequence[CohortRun],
        realized: RealizedReturns,
        native_full: Mapping[tuple[int, int], CoverageSeries],
        *,
        candidate: str,
        horizons: tuple[int, ...],
        levels: tuple[float, ...],
    ) -> ConformalAssemblyResult:
        """Uma unidade por (run do candidato, horizonte) e os folds da série nativa."""
        by_run: dict[tuple[str, int], list[ForecastRecord]] = defaultdict(list)
        for record in records:
            by_run[(record.run_id, record.horizon)].append(record)
        units = [
            _unit(run, horizon, by_run[(run.run_id, horizon)], realized, native_full, levels)
            for run in runs
            if run.model == candidate
            for horizon in horizons
        ]
        units.sort(key=lambda u: (u.fold_raw, (0, 0) if u.seed is None else (1, u.seed), u.horizon))
        return ConformalAssemblyResult(
            units=tuple(units),
            full_series_folds=_full_series_folds(records, runs, native_full, candidate),
        )


def _unit(  # noqa: PLR0911, PLR0913 — um retorno por regra da montagem (C9)
    run: CohortRun,
    horizon: int,
    rows: Sequence[ForecastRecord],
    realized: RealizedReturns,
    native_full: Mapping[tuple[int, int], CoverageSeries],
    levels: tuple[float, ...],
) -> ConformalUnitAssembly:
    fold_raw = NO_FOLD if run.fold is None else run.fold
    fold_index = _fold_index(run.fold)

    def undefined(reason: str) -> ConformalUnitAssembly:
        return ConformalUnitAssembly(
            fold_index=fold_index,
            fold_raw=fold_raw,
            seed=run.seed,
            horizon=horizon,
            calib=(),
            test=(),
            status=UNDEFINED,
            reason=reason,
        )

    if fold_index is None:
        return undefined(f"fold {fold_raw!r} is not an integer")
    if run.seed is None:
        return undefined("seed is None")
    native = native_full.get((run.seed, horizon))
    if native is None:
        return undefined(f"no native full series for seed {run.seed} and horizon {horizon}")
    calib = _groups([row for row in rows if row.split == _CALIB])
    test = _groups([row for row in rows if row.split == _TEST])
    if not calib:
        return undefined("unit has no calib point")
    if not test:
        return undefined("unit has no test point")
    for name, groups in (("calib", calib), ("test", test)):
        violation = _violation(groups, horizon=horizon, levels=levels, realized=realized)
        if violation is not None:
            return undefined(f"{name}: {violation.kind.value}: {violation.detail}")
    indices = [_decision(group)[1] for group in calib]
    gaps = [(a, b) for a, b in pairwise(indices) if b != a + 1]
    if gaps:
        return undefined(f"calib is partial: decision indices jump {gaps[0][0]} -> {gaps[0][1]}")
    targets = [group.target for group in test]
    span = {t for t in native.target_timestamps if targets[0] <= t <= targets[-1]}
    if span != set(targets):
        extra = sorted(span - set(targets))
        missing = sorted(set(targets) - span)
        return undefined(
            "test targets differ from the native full series of the fold: "
            f"native without test {extra}, test without native {missing}"
        )
    return ConformalUnitAssembly(
        fold_index=fold_index,
        fold_raw=fold_raw,
        seed=run.seed,
        horizon=horizon,
        calib=tuple(
            (
                _decision(group)[0],
                group.target,
                _grid(group, levels),
                realized.realized_at(group.target),
            )
            for group in calib
        ),
        test=tuple((_decision(group)[0], group.target, _grid(group, levels)) for group in test),
        status=OK,
        reason=None,
    )


def _full_series_folds(
    records: Sequence[ForecastRecord],
    runs: Sequence[CohortRun],
    native_full: Mapping[tuple[int, int], CoverageSeries],
    candidate: str,
) -> Mapping[tuple[int, int], tuple[int | None, ...]]:
    """(seed, h) → o fold do run que previu cada alvo da série nativa (None se não inteiro)."""
    folds_by_run = {run.run_id: _fold_index(run.fold) for run in runs if run.model == candidate}
    fold_at: dict[tuple[int, int, str], int | None] = {}
    for record in records:
        if record.split == _TEST and record.run_id in folds_by_run and record.seed is not None:
            fold_at[(record.seed, record.horizon, record.target_timestamp)] = folds_by_run[
                record.run_id
            ]
    return {
        key: tuple(fold_at.get((key[0], key[1], t)) for t in series.target_timestamps)
        for key, series in sorted(native_full.items())
    }
