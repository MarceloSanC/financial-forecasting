"""Mapeador linhas do gold → evidência por horizonte, com a conferência do gold (Stage 6.5).

Módulo auxiliar do use case `BuildConfirmatoryScorecard` (concept 6.5 §4, D4, I6, I8,
I10, C6, C8; ADRs `6_5_0004` item 5, `6_5_0006` itens 1, 6). `evidence_from_generation`
roda, nesta ordem (regra única: diferença de **conjunto** é mismatch; presente com linha
faltando é corrupção — e todo mismatch antes de toda corrupção):

1. manifesto x comando derivado do plano — `partition`, `preregistration_ref`,
   `parameters`, `horizons`, `window_deficits`, `dataset_fingerprint`
   (`PreregistrationMismatchError`; o `preregistration_ref` mascara os campos seguintes
   num gold refrescado com outro plano);
2. conjuntos por tabela — modelos (DM, MCS, calibração, métricas), seeds por modelo
   (métricas e calibração; sem seed ↔ `{None}`) e níveis da grade (`level_low` das
   linhas `pinball`);
3. MCS — `statistic` pré-registrada e `block_size = block_length_rule(h, max b̂)` por
   linha (a regra reaplicada à estimativa persistida);
4. corrupção (`GoldGenerationCorruptError`) — `max_block_estimate` ausente, linha
   `ERROR` + `FAIL` num gold `COMPLETED`, linha esperada faltando para um modelo/seed
   presente, `n_points` divergente entre as linhas DM de um horizonte;
5. monta um `HorizonEvidence` por horizonte do plano.

Nada é recomputado (I8): só cópia de colunas e médias entre seeds (`SeedSpread`); os
únicos donos da 6.2 chamados são `block_length_rule` e o identificador da estatística.
As colunas são lidas **só** pelo schema (`gold_schema`): uma coluna fora de `key` +
`read_columns` ergue `KeyError`. As caudas do gate e da amostra comum vêm **só** das
linhas com `band_level == gate_band_level` (a calibração tem uma linha por nível de
banda, com as mesmas contagens por construção da 6.4).

A evidência é montada pelos acessores tipados de `refresh_gold` (`col_int`,
`col_float`, `col_bool`, ...; F6): tipo divergente do schema é corrupção nomeada
(`GoldGenerationCorruptError`), não deriva silenciosa. As fases 1-3 (mismatch) leem com
`col` cru **de propósito** — comparam valores e conjuntos por igualdade, e um acessor
tipado ali ergueria corrupção antes de um mismatch posterior, quebrando a regra
"todo mismatch antes de toda corrupção"; o tipo é conferido na fase 4/5.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    MismatchField,
    PreregistrationMismatchError,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_DM_RESULTS,
    GOLD_MCS_RESULTS,
    GOLD_METRICS_BY_RUN,
    GOLD_QUALITY_CHECKS,
    GoldTableSchema,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldGenerationCorruptError,
    GoldManifest,
    RefreshGoldCommand,
    Row,
    col,
    col_bool,
    col_float,
    col_int,
)
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    block_length_rule,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    is_multi_step,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    CheckOutcome,
    CheckSeverity,
)
from financial_forecasting.features.evaluation.domain.value_objects.scorecard_evidence import (
    COMMON_SAMPLE,
    GATE_SAMPLE,
    CalibrationEvidence,
    ComparatorCalibration,
    DgtTailEvidence,
    DmEvidence,
    HorizonEvidence,
    McsEvidence,
    SeedSpread,
    SeedTailCounts,
    TailEvidence,
)

PINBALL_GRID_MEAN = "pinball_grid_mean"
PINBALL = "pinball"
LOWER_TAIL = "lower_tail"
UPPER_TAIL = "upper_tail"

Seed = int | None


def _mismatch(field: MismatchField, detail: str) -> PreregistrationMismatchError:
    return PreregistrationMismatchError(field, detail)


# --- 1. manifesto x comando -----------------------------------------------------------


def check_manifest(command: RefreshGoldCommand, manifest: GoldManifest) -> None:
    """Manifesto lido x comando derivado do plano, na ordem fixa (C8)."""
    checks: list[tuple[MismatchField, object, object]] = [
        (MismatchField.PARTITION, manifest.partition, command.partition),
        (
            MismatchField.PREREGISTRATION_REF,
            manifest.parameters.preregistration_ref,
            command.parameters.preregistration_ref,
        ),
        (
            MismatchField.PARAMETERS,
            manifest.parameters.as_mapping(),
            command.parameters.as_mapping(),
        ),
        (MismatchField.HORIZONS, tuple(manifest.horizons), tuple(command.horizons)),
        (
            MismatchField.WINDOW_DEFICITS,
            dict(manifest.window_deficits),
            dict(command.window_deficits),
        ),
        (
            MismatchField.DATASET_FINGERPRINT,
            manifest.dataset_fingerprint.value,
            command.dataset_fingerprint,
        ),
    ]
    for field, found, expected in checks:
        if found != expected:
            raise _mismatch(field, f"manifest has {found!r}, the plan derives {expected!r}")


# --- 2. conjuntos ---------------------------------------------------------------------


def _expected_seeds(prereg: Preregistration, model: str) -> frozenset[Seed]:
    spec = prereg.seeds[model]
    return frozenset({None}) if spec.seeds is None else frozenset(spec.seeds)


def _check_set(field: MismatchField, where: str, found: set[object], expected: set[object]) -> None:
    if found != expected:
        missing = sorted(map(repr, expected - found))
        extra = sorted(map(repr, found - expected))
        raise _mismatch(field, f"{where}: missing {missing}, extra {extra}")


def check_sets(prereg: Preregistration, tables: _Tables) -> None:
    """Modelos, seeds por modelo e níveis da grade, nos dois sentidos (C8)."""
    models = set(prereg.models)
    dm_models = {col(r, GOLD_DM_RESULTS, "candidate") for r in tables.dm} | {
        col(r, GOLD_DM_RESULTS, "comparator") for r in tables.dm
    }
    for where, found in (
        (GOLD_DM_RESULTS.name, dm_models),
        (GOLD_MCS_RESULTS.name, {col(r, GOLD_MCS_RESULTS, "model") for r in tables.mcs}),
        (
            GOLD_CALIBRATION_TABLE.name,
            {col(r, GOLD_CALIBRATION_TABLE, "model") for r in tables.cal},
        ),
        (GOLD_METRICS_BY_RUN.name, {col(r, GOLD_METRICS_BY_RUN, "model") for r in tables.metrics}),
    ):
        _check_set(MismatchField.MODELS, where, found, set(models))
    for schema, rows in (
        (GOLD_METRICS_BY_RUN, tables.metrics),
        (GOLD_CALIBRATION_TABLE, tables.cal),
    ):
        for model in prereg.models:
            found = {col(r, schema, "seed") for r in rows if col(r, schema, "model") == model}
            _check_set(
                MismatchField.SEEDS,
                f"{schema.name} {model}",
                found,
                set(_expected_seeds(prereg, model)),
            )
    levels = {
        col(r, GOLD_METRICS_BY_RUN, "level_low")
        for r in tables.metrics
        if col(r, GOLD_METRICS_BY_RUN, "metric") == PINBALL
    }
    _check_set(
        MismatchField.QUANTILE_LEVELS, GOLD_METRICS_BY_RUN.name, levels, set(prereg.quantile_levels)
    )


# --- 3. MCS ---------------------------------------------------------------------------


def check_mcs_rules(prereg: Preregistration, tables: _Tables) -> None:
    """Estatística e regra de bloco em toda linha do MCS (a estimativa ausente é C6)."""
    for row in tables.mcs:
        statistic = col(row, GOLD_MCS_RESULTS, "statistic")
        if statistic != prereg.rules.mcs_statistic:
            raise _mismatch(
                MismatchField.MCS_STATISTIC,
                f"row {_describe(row, GOLD_MCS_RESULTS)} has {statistic!r}",
            )
    for row in tables.mcs:
        expected = _block_rule(row)
        if expected is None:
            continue  # estimativa ausente ou inválida: corrupção, conferida depois de todo mismatch
        if col(row, GOLD_MCS_RESULTS, "block_size") != expected:
            raise _mismatch(
                MismatchField.MCS_BLOCK_RULE,
                f"row {_describe(row, GOLD_MCS_RESULTS)} has block_size "
                f"{col(row, GOLD_MCS_RESULTS, 'block_size')!r}, the rule gives {expected}",
            )


# --- 4. corrupção ---------------------------------------------------------------------


def _describe(row: Row, schema: GoldTableSchema) -> str:
    return "(" + ", ".join(f"{k}={row[k]!r}" for k in schema.key) + ")"


def _block_rule(row: Row) -> int | None:
    """O bloco que a regra dá para a linha; `None` se o dono (`block_length_rule`) recusa.

    A validade da estimativa é do dono da regra (uma escrita do predicado): ausente ou
    recusada por ele é corrupção, erguida por `check_completed`.
    """
    estimate = col(row, GOLD_MCS_RESULTS, "max_block_estimate")
    # não-número também é estimativa recusada (corrupção depois de todo mismatch); a
    # finitude e o sinal são do dono da regra
    if isinstance(estimate, bool) or not isinstance(estimate, int | float):
        return None
    horizon = col(row, GOLD_MCS_RESULTS, "horizon")
    if isinstance(horizon, bool) or not isinstance(horizon, int):
        return None  # horizonte de tipo errado: corrupção, depois de todo mismatch
    try:
        return block_length_rule(horizon=horizon, max_estimate=estimate)
    except ValueError:
        return None


def check_completed(tables: _Tables) -> None:
    """Estimativa de bloco ausente ou inválida e `ERROR` + `FAIL` num `COMPLETED` são corrupção."""
    for row in tables.mcs:
        estimate = col(row, GOLD_MCS_RESULTS, "max_block_estimate")
        if estimate is None:
            raise GoldGenerationCorruptError(
                f"{GOLD_MCS_RESULTS.name} row {_describe(row, GOLD_MCS_RESULTS)} has no "
                "max_block_estimate in a COMPLETED generation"
            )
        if _block_rule(row) is None:
            raise GoldGenerationCorruptError(
                f"{GOLD_MCS_RESULTS.name} row {_describe(row, GOLD_MCS_RESULTS)} has an invalid "
                f"max_block_estimate {estimate!r} (the block rule needs a finite number >= 0)"
            )
    for row in tables.checks:
        failed = (
            col(row, GOLD_QUALITY_CHECKS, "severity") == CheckSeverity.ERROR.value
            and col(row, GOLD_QUALITY_CHECKS, "outcome") == CheckOutcome.FAIL.value
        )
        if failed:
            raise GoldGenerationCorruptError(
                f"a COMPLETED generation holds the blocking check "
                f"{_describe(row, GOLD_QUALITY_CHECKS)}"
            )


class _Tables:
    """As linhas das cinco tabelas e índices pela chave (uma linha por chave)."""

    def __init__(self, generation: GoldGeneration) -> None:
        self.dm = generation.table(GOLD_DM_RESULTS).rows
        self.mcs = generation.table(GOLD_MCS_RESULTS).rows
        self.cal = generation.table(GOLD_CALIBRATION_TABLE).rows
        self.metrics = generation.table(GOLD_METRICS_BY_RUN).rows
        self.checks = generation.table(GOLD_QUALITY_CHECKS).rows
        self._index: dict[str, dict[tuple[object, ...], Row]] = {}
        for schema, rows in (
            (GOLD_DM_RESULTS, self.dm),
            (GOLD_MCS_RESULTS, self.mcs),
            (GOLD_CALIBRATION_TABLE, self.cal),
            (GOLD_METRICS_BY_RUN, self.metrics),
        ):
            self._index[schema.name] = {
                tuple(col(row, schema, column) for column in schema.key): row for row in rows
            }

    def row(self, schema: GoldTableSchema, **key: object) -> Row:
        """A linha da chave completa; ausente → corrupção nomeando a linha."""
        values = tuple(key[column] for column in schema.key)
        found = self._index[schema.name].get(values)
        if found is None:
            described = ", ".join(f"{column}={key[column]!r}" for column in schema.key)
            raise GoldGenerationCorruptError(f"{schema.name} misses the expected row ({described})")
        return found


# --- 5. evidência ---------------------------------------------------------------------


def _counts(
    tables: _Tables, row_key: Callable[[Seed], dict[str, object]], seeds: Sequence[Seed]
) -> tuple[SeedTailCounts, ...]:
    counts: list[SeedTailCounts] = []
    for seed in seeds:
        row = tables.row(GOLD_CALIBRATION_TABLE, **row_key(seed))
        counts.append(
            SeedTailCounts(
                seed=seed,
                n_violations=col_int(row, GOLD_CALIBRATION_TABLE, "n_violations"),
                n_observed=col_int(row, GOLD_CALIBRATION_TABLE, "n_observed"),
                degeneracy_rate=col_float(row, GOLD_CALIBRATION_TABLE, "degeneracy_rate"),
            )
        )
    return tuple(counts)


def _tail(  # noqa: PLR0913 - a chave completa de uma linha de calibração
    tables: _Tables,
    *,
    model: str,
    seeds: Sequence[Seed],
    horizon: int,
    sample: str,
    kind: str,
    level: float,
    band_level: float,
    dgt: tuple[int | None, int | None] = (None, None),
) -> TailEvidence:
    def key(seed: Seed) -> dict[str, object]:
        return {
            "model": model,
            "seed": seed,
            "horizon": horizon,
            "sample": sample,
            "kind": kind,
            "level_low": level,
            "level_high": None,
            "includes_degenerate": False,
            "dgt_offset": dgt[0],
            "dgt_step": dgt[1],
            "band_level": band_level,
        }

    return TailEvidence(level=level, seeds=_counts(tables, key, seeds))


def _calibration(  # noqa: PLR0913 - amostra de um modelo num horizonte
    prereg: Preregistration,
    tables: _Tables,
    *,
    model: str,
    horizon: int,
    sample: str,
    with_dgt: bool,
) -> CalibrationEvidence:
    gate = prereg.h1_gate
    seeds = sorted(_expected_seeds(prereg, model), key=lambda s: -1 if s is None else s)

    def pair(dgt: tuple[int | None, int | None]) -> tuple[TailEvidence, TailEvidence]:
        lower, upper = (
            _tail(
                tables,
                model=model,
                seeds=seeds,
                horizon=horizon,
                sample=sample,
                kind=kind,
                level=level,
                band_level=gate.gate_band_level,
                dgt=dgt,
            )
            for kind, level in ((LOWER_TAIL, gate.lower_level), (UPPER_TAIL, gate.upper_level))
        )
        return lower, upper

    lower, upper = pair((None, None))
    subs: list[DgtTailEvidence] = []
    if with_dgt and is_multi_step(horizon):
        for offset in range(horizon):
            sub_lower, sub_upper = pair((offset, horizon))
            subs.append(DgtTailEvidence(offset, horizon, sub_lower, sub_upper))
    return CalibrationEvidence(sample=sample, lower=lower, upper=upper, dgt=tuple(subs))


def _dm_rows(
    prereg: Preregistration, command: RefreshGoldCommand, tables: _Tables, horizon: int
) -> tuple[DmEvidence, ...]:
    rows: list[DmEvidence] = []
    points: set[object] = set()
    for estimator in command.parameters.dm_variance_estimators:
        for comparator in prereg.comparators:
            row = tables.row(
                GOLD_DM_RESULTS,
                horizon=horizon,
                variance_estimator=estimator.value,
                candidate=prereg.candidate,
                comparator=comparator,
            )
            points.add(col(row, GOLD_DM_RESULTS, "n_points"))
            rows.append(
                DmEvidence(
                    comparator=comparator,
                    estimator=estimator,
                    n_points=col_int(row, GOLD_DM_RESULTS, "n_points"),
                    mean_differential=col_float(row, GOLD_DM_RESULTS, "mean_differential"),
                    statistic=col_float(row, GOLD_DM_RESULTS, "statistic"),
                    adjusted_p_value=col_float(row, GOLD_DM_RESULTS, "adjusted_p_value"),
                    rejected=col_bool(row, GOLD_DM_RESULTS, "rejected"),
                    fallback_applied=col_bool(row, GOLD_DM_RESULTS, "fallback_applied"),
                )
            )
    if len(points) != 1:
        raise GoldGenerationCorruptError(
            f"{GOLD_DM_RESULTS.name} rows of horizon {horizon} disagree on n_points: "
            f"{sorted(map(repr, points))}"
        )
    return tuple(rows)


def _mcs_rows(
    prereg: Preregistration, command: RefreshGoldCommand, tables: _Tables, horizon: int
) -> tuple[McsEvidence, ...]:
    return tuple(
        McsEvidence(
            scheme,
            model,
            included=col_bool(
                tables.row(GOLD_MCS_RESULTS, horizon=horizon, scheme=scheme.value, model=model),
                GOLD_MCS_RESULTS,
                "included",
            ),
        )
        for scheme in command.parameters.mcs_schemes
        for model in prereg.models
    )


def _mean_pinball(prereg: Preregistration, tables: _Tables, horizon: int) -> dict[str, float]:
    means: dict[str, float] = {}
    for model in prereg.models:
        values = []
        for seed in sorted(_expected_seeds(prereg, model), key=lambda s: -1 if s is None else s):
            row = tables.row(
                GOLD_METRICS_BY_RUN,
                model=model,
                seed=seed,
                horizon=horizon,
                sample=COMMON_SAMPLE,
                metric=PINBALL_GRID_MEAN,
                level_low=None,
                level_high=None,
            )
            values.append(col_float(row, GOLD_METRICS_BY_RUN, "value"))
        means[model] = SeedSpread.of(values).mean
    return means


def _horizon_evidence(
    prereg: Preregistration, command: RefreshGoldCommand, tables: _Tables, horizon: int
) -> HorizonEvidence:
    dm = _dm_rows(prereg, command, tables, horizon)
    mcs = _mcs_rows(prereg, command, tables, horizon)
    gate = _calibration(
        prereg, tables, model=prereg.candidate, horizon=horizon, sample=GATE_SAMPLE, with_dgt=True
    )
    common = _calibration(
        prereg,
        tables,
        model=prereg.candidate,
        horizon=horizon,
        sample=COMMON_SAMPLE,
        with_dgt=False,
    )
    comparators = tuple(
        ComparatorCalibration(model=model, lower=calibration.lower, upper=calibration.upper)
        for model in prereg.comparators
        for calibration in (
            _calibration(
                prereg, tables, model=model, horizon=horizon, sample=GATE_SAMPLE, with_dgt=False
            ),
        )
    )
    mean_pinball = _mean_pinball(prereg, tables, horizon)
    return HorizonEvidence(
        horizon=horizon,
        common_points=dm[0].n_points,
        gate=gate,
        common=common,
        comparators_calibration=comparators,
        mean_pinball=mean_pinball,
        dm=dm,
        mcs=mcs,
    )


def evidence_from_generation(
    *, prereg: Preregistration, command: RefreshGoldCommand, generation: GoldGeneration
) -> tuple[HorizonEvidence, ...]:
    """A evidência por horizonte do plano, depois de conferir o gold (ver docstring do módulo).

    Raises:
        PreregistrationMismatchError: gold de outro plano ou cohort (C8), nomeando o campo.
        GoldGenerationCorruptError: linha esperada faltando ou gold incoerente (C6).
    """
    check_manifest(command, generation.manifest)
    tables = _Tables(generation)
    check_sets(prereg, tables)
    check_mcs_rules(prereg, tables)
    check_completed(tables)
    try:
        return tuple(_horizon_evidence(prereg, command, tables, h) for h in prereg.horizons)
    except ValueError as error:
        raise GoldGenerationCorruptError(f"the gold rows do not form evidence: {error}") from error
