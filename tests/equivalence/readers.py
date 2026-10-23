"""Leitores do andaime da equivalência: evidência anterior e partição oficial (Stage 8.2).

Concept 8.2 I6, I7, D5, D-M6; technical 8.2 §1 ("Andaime", "Realizado do lado novo").

- **anterior** — só depois do `verify_registered_files` (o conjunto lido é o do registro e
  nenhum outro, D5) e só as colunas do `comparison_set` (filtro/forma + valor + rótulo de
  modelo), com os filtros fixos (`parent_sweep_id`, `split`, horizonte) aplicados onde a
  coluna existe;
- **oficial** — a partição viva montada `:ro` (nada é escrito): a cópia julgada por
  `ParquetGoldStore(<oficial>).read_judged_generation`; as predições pelo leitor silver real
  do `RefreshGold` (`ParquetAnalyticsRepository`, `dim_run` + `fact_oos_predictions`); o
  realizado pelo `ReadTrainingGrid` real sobre o `ParquetMedallionStore`, com o
  `dataset_fingerprint` lido conferido contra o do manifesto da cópia (senão para). Só os
  adaptadores de leitura — nada de `wire_dependencies`, ledger, MLflow ou lock.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
)
from financial_forecasting.features.evaluation.application.use_cases.silver_content_accumulator import (  # noqa: E501
    SilverContentAccumulator,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.features.feature_engineering.domain.services.dataset_tft_contract import (  # noqa: E501
    TARGET_COLUMN,
)
from financial_forecasting.features.modeling.application.use_cases.read_training_grid import (
    ReadTrainingGrid,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    modeling_columns,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.adapters.out.parquet.parquet_medallion_store import (
    ParquetMedallionStore,
)
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from tests.equivalence import comparison_set as cs
from tests.equivalence.prior_evidence import (
    PriorEvidenceRegistry,
    registered_path,
    verify_registered_files,
)

Row = dict[str, object]
_SILVER = "silver"
_DIM_RUN = "dim_run"
_FACT = "fact_oos_predictions"


# --- anterior ------------------------------------------------------------------------------


def prior_columns(path: str) -> tuple[str, ...]:
    """As colunas lidas de um arquivo do registro: filtro/forma, valor e rótulo de modelo."""
    columns = [*cs.FILTER_COLUMNS[path], *cs.VALUE_COLUMNS[path]]
    if path == cs.GOLD_OOS and cs.MODEL_LABEL_COLUMN is not None:
        columns.append(cs.MODEL_LABEL_COLUMN)
    return tuple(dict.fromkeys(columns))


def _keep(row: Mapping[str, object]) -> bool:
    checks = (
        ("parent_sweep_id", lambda v: v == cs.PARENT_SWEEP_ID),
        ("split", lambda v: v == cs.SPLIT),
        ("horizon", lambda v: v in cs.HORIZONS),
    )
    return all(check(row[column]) for column, check in checks if column in row)


def read_prior_table(verified: Mapping[str, Path], path: str) -> list[Row]:
    """As linhas filtradas de um arquivo conferido, só com as colunas do `comparison_set`.

    Raises:
        PriorEvidenceHashError: `path` fora do registro conferido.
    """
    table = pq.read_table(  # type: ignore[no-untyped-call]
        registered_path(verified, path), columns=list(prior_columns(path))
    )
    return [row for row in table.to_pylist() if _keep(row)]


@dataclass(frozen=True)
class PriorSide:
    """As tabelas lidas da evidência anterior e o que o registro declara sobre elas.

    Campos:
        tables: arquivo do `comparison_set` → linhas filtradas.
        column_types: arquivo → coluna → tipo físico do footer registrado (a precisão de
            armazenamento de m_ant e de y_ant sai daqui — D12 e, D13).
        source_ids: as fontes de definição registradas (`repo@commit:path` de cada
            `[[definition_source]]` e o caminho de cada arquivo) — um `CommonBaseline` só
            vale com a sua `source` aqui (D12 a).
    """

    tables: Mapping[str, list[Row]]
    column_types: Mapping[str, Mapping[str, str]]
    source_ids: frozenset[str]


def registry_source_ids(registry: PriorEvidenceRegistry) -> frozenset[str]:
    """As fontes de definição aceitas por D12 a: código (`repo@commit:path`) ou arquivo."""
    code = {f"{s.repo}@{s.commit}:{s.path}" for s in registry.definition_sources}
    return frozenset(code | {item.path for item in registry.files})


def read_prior(*, oracle_root: Path, registry: PriorEvidenceRegistry) -> PriorSide:
    """Confere o registro (falha, nunca pula) e lê os arquivos do `comparison_set`.

    Raises:
        PriorEvidenceHashError: arquivo diferente do registro, ausente ou fora dele.
    """
    verified = verify_registered_files(oracle_root=oracle_root, registry=registry)
    return PriorSide(
        tables={path: read_prior_table(verified, path) for path in cs.PRIOR_FILES},
        column_types={
            item.path: {column.name: column.type for column in item.columns}
            for item in registry.files
        },
        source_ids=registry_source_ids(registry),
    )


# --- oficial -------------------------------------------------------------------------------


class OfficialFingerprintMismatchError(AssertionError):
    """O `dataset_fingerprint` da grade lida difere do manifesto da cópia julgada: parar."""


class OfficialSilverMismatchError(AssertionError):
    """O silver lido (`dim_run`/`fact_oos_predictions`) não é o que a cópia julgada consumiu."""


@dataclass(frozen=True)
class OfficialSide:
    """A partição oficial lida: realizado, predições (pós-guardrail) e o DM da cópia julgada."""

    partition: GoldPartition
    preregistration_ref: str
    candidate: str
    realized: RealizedReturns
    predictions: Sequence[Row]
    """`model`, `seed`, `horizon`, `target_timestamp`, `level`, `value` (o `value_guardrail`)
    por ponto do candidato e dos baselines comuns em `split = test`, nos níveis comuns."""
    dm_rows: Sequence[Row]
    """As linhas de `gold_dm_results` da cópia julgada (`read_judged_generation`)."""


def judged_partition(official_root: Path) -> tuple[GoldPartition, str]:
    """A única (partição, referência) com cópia julgada sob `<oficial>/gold/`.

    Raises:
        ValueError: nenhuma ou mais de uma.
    """
    found: list[tuple[GoldPartition, str]] = []
    store = ParquetGoldStore(official_root)
    for directory in sorted((Path(official_root) / "gold").glob("asset=*/parent_sweep_id=*")):
        partition = GoldPartition(
            directory.parent.name.removeprefix("asset="),
            directory.name.removeprefix("parent_sweep_id="),
        )
        found += [(partition, ref) for ref in store.judged_refs(partition=partition)]
    if len(found) != 1:
        raise ValueError(f"expected one judged copy under {official_root}/gold, got {found}")
    return found[0]


def _model_predictions(
    repository: ParquetAnalyticsRepository,
    partition: GoldPartition,
    models: frozenset[str],
    consumed: SilverContent,
) -> list[Row]:
    """As predições dos `models`, depois de conferir o silver lido contra a cópia julgada.

    O `dim_run` do cohort e as linhas de `fact_oos_predictions` dos seus runs são lidos com o
    MESMO pós-filtro do `RefreshGold` e hasheados pelo `SilverContentAccumulator`; cada unidade
    tem de ter o digest do `silver_content` da cópia julgada (CC4-6).

    Raises:
        OfficialSilverMismatchError: unidade ausente, a mais ou com outro digest.
    """
    accumulator = SilverContentAccumulator(hasher=CanonicalJsonHasher())
    cohort = [
        row
        for row in repository.read(
            layer=_SILVER,
            table=_DIM_RUN,
            filters={"asset": partition.asset, "parent_sweep_id": partition.parent_sweep_id},
        )
        if (row.get("asset"), row.get("parent_sweep_id"))
        == (partition.asset, partition.parent_sweep_id)
    ]
    accumulator.add_dim_run(
        columns=repository.columns(layer=_SILVER, table=_DIM_RUN),
        parent_sweep_id=partition.parent_sweep_id,
        rows=cohort,
    )
    by_id = {str(row["run_id"]): row for row in cohort}
    fact_columns = repository.columns(layer=_SILVER, table=_FACT)
    points: list[Row] = []
    for feature_set in sorted({str(run["feature_set_name"]) for run in cohort}):
        kept = [
            row
            for row in repository.read(
                layer=_SILVER,
                table=_FACT,
                filters={"asset": partition.asset, "feature_set_name": feature_set},
            )
            if row.get("asset") == partition.asset and str(row["run_id"]) in by_id
        ]
        accumulator.add_facts(table=_FACT, columns=fact_columns, rows=kept)
        for row in kept:
            run = by_id[str(row["run_id"])]
            if (
                run.get("model_version") not in models
                or row.get("split") != cs.SPLIT
                or row.get("quantile_level") not in cs.COMMON_LEVELS
            ):
                continue
            points.append(
                {
                    "model": run["model_version"],
                    "seed": run["seed"],
                    "horizon": row["horizon"],
                    "target_timestamp": str(row["target_timestamp_utc"]),
                    "level": row["quantile_level"],
                    "value": row["value_guardrail"],  # NEW_SCORED_VARIANT
                }
            )
    check_silver_units(accumulator.result(), consumed, partition)
    return points


def check_silver_units(
    read: SilverContent, consumed: SilverContent, partition: GoldPartition
) -> None:
    """As unidades de `dim_run` do cohort e de `fact_oos_predictions` lidas = as consumidas.

    Raises:
        OfficialSilverMismatchError: unidade ausente, a mais ou com outro digest.
    """

    def ours(units: Mapping[str, str]) -> dict[str, str]:
        dim_run = f"{_DIM_RUN}|{partition.parent_sweep_id}"
        return {
            key: value
            for key, value in units.items()
            if key == dim_run or key.startswith(f"{_FACT}|")
        }

    got, expected = ours(read.units), ours(consumed.units)
    if got != expected:
        differing = sorted(k for k in set(got) | set(expected) if got.get(k) != expected.get(k))
        raise OfficialSilverMismatchError(
            f"official silver differs from the judged copy's silver_content in {differing[:10]}"
        )


def read_official(official_root: Path) -> OfficialSide:
    """A partição oficial lida só por adaptadores de leitura.

    Raises:
        OfficialFingerprintMismatchError: a grade lida não é a do manifesto da cópia.
        JudgedGenerationTamperedError / JudgedGenerationNotFoundError: cópia adulterada ou
            ausente.
    """
    root = Path(official_root)
    partition, ref = judged_partition(root)
    judged = ParquetGoldStore(root).read_judged_generation(
        partition=partition, preregistration_ref=ref
    )
    grid, fingerprint = ReadTrainingGrid(
        store=ParquetMedallionStore(data_root=root),
        columns=modeling_columns(),
        hasher=CanonicalJsonHasher(),
    )(asset_id=partition.asset)
    expected = judged.manifest.dataset_fingerprint.value
    if fingerprint.value != expected:
        raise OfficialFingerprintMismatchError(
            f"training grid fingerprint {fingerprint.value} != judged copy {expected}"
        )
    realized = RealizedReturns(timestamps=grid.timestamps_iso(), returns=grid.column(TARGET_COLUMN))
    candidate = judged.manifest.parameters.candidate
    models = frozenset({candidate, *(b.new_label for b in cs.COMMON_BASELINES)})
    repository = ParquetAnalyticsRepository(data_root=root, clock=SystemClock())
    dm_table = judged.tables.get(cs.NEW_DM_TABLE)
    return OfficialSide(
        partition=partition,
        preregistration_ref=ref,
        candidate=candidate,
        realized=realized,
        predictions=tuple(
            _model_predictions(repository, partition, models, judged.manifest.silver_content)
        ),
        dm_rows=tuple(dict(row) for row in (dm_table.rows if dm_table is not None else ())),
    )
