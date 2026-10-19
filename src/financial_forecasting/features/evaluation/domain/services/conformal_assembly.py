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
  também vira `undefined`. Dois folds crus distintos com o mesmo inteiro (`"01"` e
  `"1"`) na mesma seed e horizonte viram `undefined` os dois (C4-8): a identidade da
  unidade é o `fold_raw`, e o port só aceita uma unidade por inteiro.

Qualquer violação vira `status = "undefined"` com o motivo — nunca `AlignmentFinding`,
porque o conformal não está no caminho do veredito.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
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
    # (seed, h) → alvos da série nativa que nenhuma unidade ok cobre (só os não vazios);
    # essa (seed, h) não tem cobertura conformal (o RefreshGold a publica undefined)
    uncovered_targets: Mapping[tuple[int, int], tuple[str, ...]]


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


def _unit_order(unit: ConformalUnitAssembly) -> tuple[bool, int, str, tuple[int, int], int]:
    """Fold inteiro em ordem numérica ("10" depois de "2"), não inteiros no fim (C3-8 b)."""
    return (
        unit.fold_index is None,
        0 if unit.fold_index is None else unit.fold_index,
        unit.fold_raw,
        (0, 0) if unit.seed is None else (1, unit.seed),
        unit.horizon,
    )


def _without_fold_collisions(units: list[ConformalUnitAssembly]) -> list[ConformalUnitAssembly]:
    """Unidades `ok` ambíguas viram `undefined` (C4-8, C5-6).

    - a mesma `(fold_raw, seed, h)` em mais de um run (unidade duplicada);
    - folds crus distintos com o mesmo inteiro na mesma seed e horizonte.
    """
    counts: dict[tuple[str, int | None, int], int] = defaultdict(int)
    raws: dict[tuple[int | None, int | None, int], set[str]] = defaultdict(set)
    for unit in units:
        if unit.status == OK:
            counts[(unit.fold_raw, unit.seed, unit.horizon)] += 1
            raws[(unit.fold_index, unit.seed, unit.horizon)].add(unit.fold_raw)
    result = []
    for unit in units:
        if unit.status == OK:
            count = counts[(unit.fold_raw, unit.seed, unit.horizon)]
            same = raws[(unit.fold_index, unit.seed, unit.horizon)]
            reason = None
            if count > 1:
                reason = f"unit fold {unit.fold_raw!r} appears in {count} runs"
            elif len(same) > 1:
                reason = f"folds {sorted(same)} map to the same integer fold {unit.fold_index}"
            if reason is not None:
                # PLW2901: a unidade da iteração é trocada pela sua versão `undefined`
                # (VO frozen, `replace` cria outra); a original não é mais lida
                unit = replace(unit, status=UNDEFINED, reason=reason)  # noqa: PLW2901
        result.append(unit)
    return result


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
        units = _without_fold_collisions(units)
        units.sort(key=_unit_order)
        return ConformalAssemblyResult(
            units=tuple(units),
            full_series_folds=_full_series_folds(records, runs, native_full, candidate),
            uncovered_targets=_uncovered_targets(units, native_full),
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


def _uncovered_targets(
    units: Sequence[ConformalUnitAssembly],
    native_full: Mapping[tuple[int, int], CoverageSeries],
) -> Mapping[tuple[int, int], tuple[str, ...]]:
    """Alvos nativos fora da união dos testes das unidades ok, por (seed, h).

    O join por unidade só olha o intervalo do fold; um ponto nativo no vão entre dois
    folds (ou antes do primeiro, ou depois do último) só aparece aqui.
    """
    covered: dict[tuple[int, int], set[str]] = defaultdict(set)
    for unit in units:
        if unit.status == OK and unit.seed is not None:
            covered[(unit.seed, unit.horizon)].update(point[1] for point in unit.test)
    result: dict[tuple[int, int], tuple[str, ...]] = {}
    for key, series in sorted(native_full.items()):
        left = tuple(t for t in series.target_timestamps if t not in covered[key])
        if left:
            result[key] = left
    return result
