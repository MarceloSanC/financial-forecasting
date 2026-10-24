"""Leitura do silver e do realizado das figuras, conferida por unidade (Stage 8.3, D4, I2).

O sharpness diagram e o fan chart precisam de quantis por ponto, que o gold não guarda
(concept 8.3 §3): saem do silver do cohort, identificado pelo `silver_content` que o
refresh julgado registrou no manifesto (ADR `8_1_0002`; ADR `8_3_0002` item 3).
`read_verified_silver` lê como o `RefreshGold` lê e só devolve o que confere:

- `dim_run` por `{asset, parent_sweep_id}` com o pós-filtro de igualdade;
- `fact_oos_predictions` por `{asset, feature_set_name}` de cada `feature_set_name` do
  cohort, mantendo as linhas cujo `run_id` é do cohort — **todas** as linhas, de todos
  os splits (o digest de uma unidade cobre o `test` e o `calib`, I2);
- o realizado pelo `TrainingGridReader` (`timestamps_iso()` + `target_return`), com o
  fingerprint do dono conferido contra o `dataset_fingerprint` do plano.

Os digests são recalculados por um `SilverContentAccumulator` novo (dono único). O
**esperado** é formado pelos pares lidos: as chaves julgadas `fact_oos_predictions|<run>|*`
de todo run do cohort, `dim_run|<parent_sweep_id>` e `realized|<asset>`. Chave julgada de
par não lido (ablação; `fact_permuted_predictions|…`/`fact_vsn_weights|…` do mesmo
`run_id`) fica fora — lição do `[finding]` E4 da 8.2. Diferença, falta ou sobra →
`SilverContentMismatchError` com as chaves (nunca valores).

O pós-filtro **não** é extraído do `RefreshGold` (código da geração julgada; technical 8.3
§1): a duplicação é de ~20 linhas, e a própria conferência por unidade prova a
equivalência — um filtro diferente produz digest diferente e recusa.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
    GridFingerprintMismatchError,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    ReportSourceMismatchError,
    SilverContentMismatchError,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    REALIZED_TABLE,
    UNIT_KEY_SEPARATOR,
    SilverContent,
    unit_key,
)
from financial_forecasting.features.evaluation.application.ports.out.silver_table_reader import (
    SilverTableReader,
)
from financial_forecasting.features.evaluation.application.ports.out.training_grid_reader import (
    TrainingGridReader,
)
from financial_forecasting.features.evaluation.application.use_cases.silver_content_accumulator import (  # noqa: E501
    DIM_RUN_TABLE,
    SilverContentAccumulator,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

SILVER_LAYER: Final = "silver"
FACT_TABLE: Final = "fact_oos_predictions"
_TARGET: Final = "target_return"
_GUARDRAIL_FLAGS: Final = {0: False, 1: True}

Row = Mapping[str, object]


@dataclass(frozen=True, kw_only=True)
class VerifiedSilver:
    """O silver do cohort conferido contra a cópia julgada.

    `units` são as unidades recalculadas (chave → digest), iguais às julgadas dos pares
    lidos; o registro de cada figura cita as que usou.

    Raises:
        ValueError: contêiner de outro tipo.
    """

    runs: tuple[CohortRun, ...]
    records: tuple[ForecastRecord, ...]
    realized: RealizedReturns
    units: Mapping[str, str]
    split_fingerprints: Mapping[str, str | None] = field(default_factory=dict)
    """`run_id` → `split_fingerprint` do `dim_run` (identidade da entrada no dossiê, doc §7)."""

    def __post_init__(self) -> None:
        if not isinstance(self.runs, tuple) or not isinstance(self.records, tuple):
            raise ValueError("runs and records must be tuples")
        if not isinstance(self.realized, RealizedReturns):
            raise ValueError("realized must be a RealizedReturns")
        object.__setattr__(self, "units", MappingProxyType(dict(sorted(self.units.items()))))
        object.__setattr__(
            self,
            "split_fingerprints",
            MappingProxyType(dict(sorted(self.split_fingerprints.items()))),
        )


def read_verified_silver(  # noqa: PLR0913 — os colaboradores e as referências da conferência
    *,
    silver_reader: SilverTableReader,
    grid_reader: TrainingGridReader,
    hasher: Hasher,
    partition: GoldPartition,
    expected_fingerprint: str,
    judged: SilverContent,
) -> VerifiedSilver:
    """Lê `dim_run`, os fatos e o realizado do cohort e confere unidade a unidade (I2).

    Raises:
        ReportSourceMismatchError: o cohort não tem linha no `dim_run`.
        GridFingerprintMismatchError: a grade lida não é a do plano.
        SilverContentMismatchError: alguma unidade difere, falta ou sobra.
    """
    accumulator = SilverContentAccumulator(hasher=hasher)
    runs, split_fingerprints = _read_runs(silver_reader, partition, accumulator)
    records = _read_records(silver_reader, partition, runs, accumulator)
    realized = _read_realized(grid_reader, partition.asset, expected_fingerprint, accumulator)
    read_units = accumulator.result().units
    _check_units(
        judged.units,
        read_units,
        run_ids=frozenset(run.run_id for run in runs),
        parent_sweep_id=partition.parent_sweep_id,
        asset=partition.asset,
    )
    return VerifiedSilver(
        runs=runs,
        records=records,
        realized=realized,
        units=read_units,
        split_fingerprints=split_fingerprints,
    )


def _check_units(
    judged: Mapping[str, str],
    read: Mapping[str, str],
    *,
    run_ids: frozenset[str],
    parent_sweep_id: str,
    asset: str,
) -> None:
    """Esperado = as chaves julgadas dos pares lidos; igualdade exata de chaves e digests.

    Raises:
        SilverContentMismatchError: as chaves que diferem, faltam ou sobram (ordenadas).
    """
    fixed = {unit_key(DIM_RUN_TABLE, parent_sweep_id), unit_key(REALIZED_TABLE, asset)}

    def expected_key(key: str) -> bool:
        parts = key.split(UNIT_KEY_SEPARATOR)
        return key in fixed or (len(parts) > 1 and parts[0] == FACT_TABLE and parts[1] in run_ids)

    expected = {key: digest for key, digest in judged.items() if expected_key(key)}
    differing = {key for key in expected.keys() | read.keys() if expected.get(key) != read.get(key)}
    if differing:
        raise SilverContentMismatchError(sorted(differing))


def _read_runs(
    reader: SilverTableReader, partition: GoldPartition, accumulator: SilverContentAccumulator
) -> tuple[tuple[CohortRun, ...], dict[str, str | None]]:
    rows = [
        row
        for row in reader.read(
            layer=SILVER_LAYER,
            table=DIM_RUN_TABLE,
            filters={"asset": partition.asset, "parent_sweep_id": partition.parent_sweep_id},
        )
        if (row.get("asset"), row.get("parent_sweep_id"))
        == (partition.asset, partition.parent_sweep_id)
    ]
    if not rows:
        raise ReportSourceMismatchError(f"cohort {partition.parent_sweep_id!r} has no dim_run rows")
    accumulator.add_dim_run(
        columns=reader.columns(layer=SILVER_LAYER, table=DIM_RUN_TABLE),
        parent_sweep_id=partition.parent_sweep_id,
        rows=rows,
    )
    runs = (
        CohortRun(
            run_id=str(row["run_id"]),
            model=str(row["model_version"]),
            seed=row["seed"],  # type: ignore[arg-type]
            fold=row["fold"],  # type: ignore[arg-type]
            feature_set_name=str(row["feature_set_name"]),
            config_signature=str(row["config_signature"]),
        )
        for row in rows
    )
    fingerprints = {
        str(row["run_id"]): None
        if row.get("split_fingerprint") is None
        else str(row["split_fingerprint"])
        for row in rows
    }
    return tuple(sorted(runs, key=lambda run: run.run_id)), fingerprints


def _read_records(
    reader: SilverTableReader,
    partition: GoldPartition,
    runs: Sequence[CohortRun],
    accumulator: SilverContentAccumulator,
) -> tuple[ForecastRecord, ...]:
    by_id = {run.run_id: run for run in runs}
    columns = reader.columns(layer=SILVER_LAYER, table=FACT_TABLE)
    records: list[ForecastRecord] = []
    for feature_set in sorted({run.feature_set_name for run in runs}):
        kept: list[Row] = []
        for row in reader.read(
            layer=SILVER_LAYER,
            table=FACT_TABLE,
            filters={"asset": partition.asset, "feature_set_name": feature_set},
        ):
            run = by_id.get(str(row["run_id"]))
            if row.get("asset") != partition.asset or run is None:
                continue  # fora do cohort: descartado antes do hash (como o refresh)
            kept.append(row)
            records.append(_record(row, run))
        accumulator.add_facts(table=FACT_TABLE, columns=columns, rows=kept)
    return tuple(records)


def _record(row: Row, run: CohortRun) -> ForecastRecord:
    """O `ForecastRecord` pelas regras do refresh (`guardrail_applied` int 0/1)."""
    flag = row["guardrail_applied"]
    if isinstance(flag, bool) or flag not in _GUARDRAIL_FLAGS:
        raise ValueError(f"guardrail_applied must be the int 0 or 1, got {flag!r}")
    return ForecastRecord(
        run_id=run.run_id,
        model=str(row["model_version"]),
        seed=run.seed,
        fold=run.fold,
        horizon=row["horizon"],  # type: ignore[arg-type]
        decision_idx=row["decision_idx"],  # type: ignore[arg-type]
        decision_timestamp=str(row["timestamp_utc"]),
        target_timestamp=str(row["target_timestamp_utc"]),
        split=str(row["split"]),
        quantile_level=row["quantile_level"],  # type: ignore[arg-type]
        value_raw=row["value_raw"],  # type: ignore[arg-type]
        value_guardrail=row["value_guardrail"],  # type: ignore[arg-type]
        guardrail_applied=_GUARDRAIL_FLAGS[flag],
    )


def _read_realized(
    grid_reader: TrainingGridReader,
    asset: str,
    expected: str,
    accumulator: SilverContentAccumulator,
) -> RealizedReturns:
    grid, fingerprint = grid_reader(asset_id=asset)
    if fingerprint.value != expected:
        raise GridFingerprintMismatchError(
            f"training grid of {asset!r} is not the one the plan froze (dataset fingerprint)"
        )
    realized = RealizedReturns(timestamps=grid.timestamps_iso(), returns=grid.column(_TARGET))
    accumulator.add_realized(asset=asset, realized=realized)
    return realized
