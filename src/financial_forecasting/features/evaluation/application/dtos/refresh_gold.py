"""DTOs do refresh do gold (Stage 6.4) — parâmetros, comando, partição, tabelas e manifesto.

DTOs de aplicação **frozen** (concept 6.4 §4 "Application", C2, C3, I16, I17; ADRs
`6_4_0005`, `6_4_0006`):

- `RefreshParameters` — todos os parâmetros do refresh, keyword, **sem default**,
  validados na construção só pelos validadores públicos donos (ADR `6_4_0006` item 2):
  nenhum parâmetro inválido chega à leitura, nem ao manifesto `BLOCKED`;
- `GoldPartition` — `(asset, parent_sweep_id)`, ambos pela regra única de identificador
  de caminho (`validate_path_identifier`, C3);
- `RefreshGoldCommand` — o comando do use case; constrói a `partition` no
  `__post_init__` (C3 antes de qualquer leitura);
- `GoldTable` — `name`, `key` (as colunas do grão) e `rows` com as mesmas colunas em
  toda linha, a chave contida nelas e as linhas **estritamente** ordenadas pela chave
  (`None` antes de qualquer valor) — dono único da regra "rows are sorted by the
  table's key" (ADR `6_4_0005` item 5); valores só `str`/`int`/`float` finito/`bool`/
  `None`;
- `GoldManifest` — o que identifica uma geração (ADR `6_4_0005` item 8), com
  `as_mapping()` como a única serialização (JSON-safe);
- `GoldInputs` — o que os builders mapeiam; `FailedCheck`/`failed_checks_of` e
  `RefreshGoldResult` — o que o use case devolve.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from types import MappingProxyType

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    validate_min_violations,
)
from financial_forecasting.features.evaluation.domain.services.count_input_validation import (
    validate_rate,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.horizon_reports import (
    HorizonReport,
)
from financial_forecasting.features.evaluation.domain.services.inference_input_validation import (
    validate_alpha,
)
from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    McsReport,
    validate_mcs_reps,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._tolerance import (
    validate_tolerance,
)
from financial_forecasting.features.evaluation.domain.value_objects.block_estimate import (
    BlockEstimate,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
    validate_bootstrap_parameters,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    QualityCheckResult,
)
from financial_forecasting.shared.domain.services.path_identifier import (
    validate_path_identifier,
)
from financial_forecasting.shared.domain.value_objects.dataset_fingerprint import (
    DatasetFingerprint,
)

Row = Mapping[str, object]


def _check_text(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty str, got {value!r}")


def _check_distinct_tuple(value: object, *, field: str) -> None:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{field} must be a non-empty tuple, got {value!r}")
    if len(set(value)) != len(value):
        raise ValueError(f"{field} must not repeat values, got {value!r}")


class RefreshStatus(StrEnum):
    """Status de uma geração do gold (ADR `6_4_0005` item 4)."""

    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, kw_only=True)
class RefreshParameters:
    """Parâmetros explícitos do refresh (ADR `6_4_0006` item 1) — sem default.

    Raises:
        ValueError: campo inválido, pela mensagem do validador dono (C2).
    """

    preregistration_ref: str
    degeneracy_tolerance: float
    band_levels: tuple[float, ...]
    min_violations: int
    candidate: str
    dm_alpha: float
    dm_variance_estimators: tuple[DmVarianceEstimator, ...]
    mcs_alpha: float
    mcs_reps: int
    mcs_seed: int
    mcs_schemes: tuple[BootstrapScheme, ...]

    def __post_init__(self) -> None:
        """Presença, estrutura e os validadores públicos donos (ADR `6_4_0006` item 2)."""
        _check_text(self.preregistration_ref, field="preregistration_ref")
        _check_text(self.candidate, field="candidate")
        for name in ("band_levels", "dm_variance_estimators", "mcs_schemes"):
            _check_distinct_tuple(getattr(self, name), field=name)
        validate_tolerance(self.degeneracy_tolerance, field="degeneracy_tolerance")
        for level in self.band_levels:
            validate_rate(level, field="band_level")
        validate_min_violations(self.min_violations)
        validate_alpha(self.dm_alpha)
        validate_alpha(self.mcs_alpha)
        # tipo antes do piso: `validate_mcs_reps` só compara (Checkpoint C bloco 1, I3)
        validate_bootstrap_parameters(reps=self.mcs_reps, seed=self.mcs_seed)
        validate_mcs_reps(self.mcs_reps)
        for estimator in self.dm_variance_estimators:
            if not isinstance(estimator, DmVarianceEstimator):
                raise ValueError(
                    f"dm_variance_estimators must hold DmVarianceEstimator, got {estimator!r}"
                )
        for scheme in self.mcs_schemes:
            if not isinstance(scheme, BootstrapScheme):
                raise ValueError(f"mcs_schemes must hold BootstrapScheme, got {scheme!r}")

    def as_mapping(self) -> dict[str, object]:
        """Os parâmetros em forma JSON-safe (enums pelo valor, tuplas como listas)."""
        return {
            "preregistration_ref": self.preregistration_ref,
            "degeneracy_tolerance": self.degeneracy_tolerance,
            "band_levels": list(self.band_levels),
            "min_violations": self.min_violations,
            "candidate": self.candidate,
            "dm_alpha": self.dm_alpha,
            "dm_variance_estimators": [e.value for e in self.dm_variance_estimators],
            "mcs_alpha": self.mcs_alpha,
            "mcs_reps": self.mcs_reps,
            "mcs_seed": self.mcs_seed,
            "mcs_schemes": [s.value for s in self.mcs_schemes],
        }


@dataclass(frozen=True)
class GoldPartition:
    """A partição do gold: um cohort de um ativo (ADR `6_4_0005` item 1).

    Raises:
        ValueError: `asset`/`parent_sweep_id` fora da regra única de identificador (C3).
    """

    asset: str
    parent_sweep_id: str

    def __post_init__(self) -> None:
        """C3 na construção — antes de qualquer caminho ou leitura."""
        validate_path_identifier(self.asset, field="asset")
        validate_path_identifier(self.parent_sweep_id, field="parent_sweep_id")


@dataclass(frozen=True, kw_only=True)
class RefreshGoldCommand:
    """Comando do `RefreshGold`: o cohort, os horizontes, os déficits e os parâmetros.

    Raises:
        ValueError: identificador inválido (C3), `horizons` vazio/repetido/não-`tuple`,
            `window_deficits` não-`Mapping` ou `parameters` de outro tipo.
    """

    asset: str
    parent_sweep_id: str
    horizons: tuple[int, ...]
    window_deficits: Mapping[str, int]
    parameters: RefreshParameters
    partition: GoldPartition = field(init=False)

    def __post_init__(self) -> None:
        """Partição (C3) primeiro; depois a estrutura dos demais campos."""
        object.__setattr__(self, "partition", GoldPartition(self.asset, self.parent_sweep_id))
        _check_distinct_tuple(self.horizons, field="horizons")
        if not isinstance(self.window_deficits, Mapping):
            raise ValueError(
                f"window_deficits must be a Mapping, got {type(self.window_deficits).__name__}"
            )
        object.__setattr__(self, "window_deficits", MappingProxyType(dict(self.window_deficits)))
        if not isinstance(self.parameters, RefreshParameters):
            raise ValueError(f"parameters must be RefreshParameters, got {self.parameters!r}")


def _cell_ok(value: object) -> bool:
    if value is None or isinstance(value, str | bool | int):
        return True
    return isinstance(value, float) and is_finite_number(value)


def _key_of(row: Row, key: tuple[str, ...]) -> tuple[tuple[int, object], ...]:
    # `None` antes de qualquer valor (convenção de ordem do technical 6.4 §1)
    return tuple((0, 0) if row[column] is None else (1, row[column]) for column in key)


@dataclass(frozen=True)
class GoldTable:
    """Uma tabela gold: nome, colunas da chave e linhas ordenadas pela chave.

    Raises:
        ValueError: nome/chave mal-formados, linha não-`Mapping`, colunas diferentes
            entre linhas, chave fora das colunas, valor de tipo não suportado (ou
            float não-finito), linhas fora de ordem ou chave repetida.
    """

    name: str
    key: tuple[str, ...]
    rows: tuple[Row, ...]

    def __post_init__(self) -> None:
        """Forma, colunas uniformes e ordem estrita pela chave."""
        _check_text(self.name, field="name")
        _check_distinct_tuple(self.key, field="key")
        for column in self.key:
            _check_text(column, field="key column")
        if not isinstance(self.rows, tuple):
            raise ValueError(f"rows must be a tuple, got {type(self.rows).__name__}")
        frozen: list[Row] = []
        columns: frozenset[str] | None = None
        for index, row in enumerate(self.rows):
            if not isinstance(row, Mapping):
                raise ValueError(f"row {index} must be a Mapping, got {row!r}")
            row_columns = frozenset(row)
            if columns is None:
                columns = row_columns
                missing = sorted(set(self.key) - columns)
                if missing:
                    raise ValueError(f"key columns {missing} are not columns of {self.name}")
            elif row_columns != columns:
                raise ValueError(
                    f"row {index} columns {sorted(row_columns)} differ from {sorted(columns)}"
                )
            bad = sorted(c for c, v in row.items() if not _cell_ok(v))
            if bad:
                raise ValueError(f"row {index}: unsupported values in columns {bad}")
            frozen.append(MappingProxyType(dict(row)))
        try:
            keys = [_key_of(row, self.key) for row in frozen]
            ordered = all(a < b for a, b in pairwise(keys))
        except TypeError as error:
            raise ValueError(f"key columns of {self.name} mix types: {error}") from None
        if not ordered:
            raise ValueError(
                f"rows of {self.name} must be strictly increasing by key {self.key} "
                "(sorted, no repeated key)"
            )
        object.__setattr__(self, "rows", tuple(frozen))

    @classmethod
    def sorted_by_key(cls, name: str, key: tuple[str, ...], rows: Iterable[Row]) -> GoldTable:
        """Ordena `rows` pela chave (a mesma regra da validação) e constrói a tabela.

        Linhas sem alguma coluna da chave ou com tipos misturados seguem sem ordenar:
        a validação do construtor as recusa com a mensagem própria.
        """
        materialized = list(rows)
        with suppress(KeyError, TypeError):
            materialized.sort(key=lambda row: _key_of(row, key))
        return cls(name, key, tuple(materialized))

    @property
    def columns(self) -> tuple[str, ...]:
        """Colunas da tabela (ordenadas); vazio sem linhas."""
        return tuple(sorted(self.rows[0])) if self.rows else ()


@dataclass(frozen=True, kw_only=True)
class GoldManifest:
    """O manifesto de uma geração (ADR `6_4_0005` item 8).

    Raises:
        ValueError: campo de tipo errado, contagem negativa ou timestamp sem fuso.
    """

    status: RefreshStatus
    partition: GoldPartition
    rows_by_table: Mapping[str, int]
    parameters: RefreshParameters
    horizons: tuple[int, ...]
    window_deficits: Mapping[str, int]
    dataset_fingerprint: DatasetFingerprint
    realized_sessions: int
    realized_returns_fsum: float
    realized_first_timestamp: str
    realized_last_timestamp: str
    n_runs: int
    build_order: tuple[str, ...]
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        """Tipos e contagens; mapas guardados como cópias somente-leitura."""
        if not isinstance(self.status, RefreshStatus):
            raise ValueError(f"status must be a RefreshStatus, got {self.status!r}")
        for name in ("rows_by_table", "window_deficits"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise ValueError(f"{name} must be a Mapping, got {type(value).__name__}")
            object.__setattr__(self, name, MappingProxyType(dict(value)))
        for table, count in self.rows_by_table.items():
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"rows_by_table[{table!r}] must be an int >= 0, got {count!r}")
        for name in ("realized_sessions", "n_runs"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be an int >= 0, got {value!r}")
        for name in ("started_at", "finished_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError(f"{name} must be a timezone-aware datetime, got {value!r}")

    def as_mapping(self) -> dict[str, object]:
        """A única serialização do manifesto (JSON-safe; o store grava com `sort_keys`)."""
        return {
            "status": self.status.value,
            "asset": self.partition.asset,
            "parent_sweep_id": self.partition.parent_sweep_id,
            "preregistration_ref": self.parameters.preregistration_ref,
            "rows_by_table": dict(self.rows_by_table),
            "parameters": self.parameters.as_mapping(),
            "horizons": list(self.horizons),
            "window_deficits": dict(self.window_deficits),
            "dataset_fingerprint": self.dataset_fingerprint.value,
            "realized": {
                "n_sessions": self.realized_sessions,
                "returns_fsum": self.realized_returns_fsum,
                "first_timestamp": self.realized_first_timestamp,
                "last_timestamp": self.realized_last_timestamp,
            },
            "n_runs": self.n_runs,
            "build_order": list(self.build_order),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


def check_generation(
    partition: GoldPartition, tables: Sequence[GoldTable], manifest: GoldManifest
) -> None:
    """Coerência de uma geração antes de publicar — dono único, chamado pelos dois stores.

    Raises:
        ValueError: manifesto de outra partição; nomes de tabela repetidos;
            `manifest.rows_by_table` diferente das tabelas publicadas; linha cujo
            `asset`/`parent_sweep_id` não é o da partição (Checkpoint C bloco 3).
    """
    if manifest.partition != partition:
        raise ValueError(f"manifest is for partition {manifest.partition}, publishing {partition}")
    names = [table.name for table in tables]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ValueError(f"table names must be unique in a generation, repeated: {repeated}")
    counts = {table.name: len(table.rows) for table in tables}
    if dict(manifest.rows_by_table) != counts:
        raise ValueError(
            f"manifest rows_by_table {dict(manifest.rows_by_table)} != tables {counts}"
        )
    expected = (partition.asset, partition.parent_sweep_id)
    for table in tables:
        for index, row in enumerate(table.rows):
            got = (row.get("asset"), row.get("parent_sweep_id"))
            if got != expected:
                raise ValueError(
                    f"{table.name} row {index} is for {got}, not the partition {expected}"
                )


@dataclass(frozen=True, kw_only=True)
class GoldInputs:
    """O que os builders mapeiam — resultados prontos, nenhum a recomputar.

    Campos:
        partition, parameters, status: a geração e o que a produziu.
        check_results: os resultados do `QualityCheckRegistry`, em ordem.
        horizon_reports: um `HorizonReport` por horizonte (vazio se `BLOCKED`).
        mcs_reports: os `McsReport`s (horizonte x esquema; vazio se `BLOCKED`).
        block_estimates: horizonte → as b̂_sb por par (as que foram ao MCS).

    Raises:
        ValueError: `BLOCKED` com relatórios ou sem resultado bloqueante; `COMPLETED`
            com resultado bloqueante (bloqueado ⇔ algum ERROR + FAIL, nos dois sentidos).
    """

    partition: GoldPartition
    parameters: RefreshParameters
    status: RefreshStatus
    check_results: tuple[QualityCheckResult, ...]
    horizon_reports: tuple[HorizonReport, ...]
    mcs_reports: tuple[McsReport, ...]
    block_estimates: Mapping[int, tuple[BlockEstimate, ...]]

    def __post_init__(self) -> None:
        """Coerência status x conteúdo; mapa como cópia somente-leitura."""
        if not isinstance(self.status, RefreshStatus):
            raise ValueError(f"status must be a RefreshStatus, got {self.status!r}")
        if not isinstance(self.block_estimates, Mapping):
            raise ValueError("block_estimates must be a Mapping")
        object.__setattr__(self, "block_estimates", MappingProxyType(dict(self.block_estimates)))
        blocking = any(result.is_blocking for result in self.check_results)
        if self.status is RefreshStatus.BLOCKED and (self.horizon_reports or self.mcs_reports):
            raise ValueError("a BLOCKED generation has no horizon or MCS reports")
        if self.status is RefreshStatus.COMPLETED and blocking:
            raise ValueError("a COMPLETED generation cannot hold a blocking check result")
        if self.status is RefreshStatus.BLOCKED and not blocking:
            raise ValueError("a BLOCKED generation needs a blocking (ERROR + FAIL) check result")

    @property
    def preregistration_ref(self) -> str:
        """A referência do pré-registro (dos parâmetros — uma fonte só)."""
        return self.parameters.preregistration_ref


@dataclass(frozen=True)
class FailedCheck:
    """Um resultado bloqueante (ERROR + FAIL), devolvido ao chamador do refresh."""

    check: str
    kind: str
    horizon: int | None
    model: str | None
    seed: int | None
    occurrences: int
    detail: str


def failed_checks_of(results: Sequence[QualityCheckResult]) -> tuple[FailedCheck, ...]:
    """Os resultados ERROR + FAIL, na ordem, como `FailedCheck`."""
    return tuple(
        FailedCheck(
            check=result.check,
            kind=result.kind,
            horizon=result.horizon,
            model=result.model,
            seed=result.seed,
            occurrences=result.occurrences,
            detail=result.detail,
        )
        for result in results
        if result.is_blocking
    )


@dataclass(frozen=True)
class RefreshGoldResult:
    """Resultado do refresh: status, linhas por tabela publicada e os checks que falharam."""

    status: RefreshStatus
    rows_by_table: Mapping[str, int]
    failed_checks: tuple[FailedCheck, ...]
