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

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    CONFIRMATORY_TABLES,
    GOLD_SCHEMAS,
    GoldTableSchema,
)
from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    validate_draws_and_seed,
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
    validate_block_sensitivities,
    validate_mcs_reps,
)
from financial_forecasting.features.evaluation.domain.services.profile_reports import (
    HorizonProfileReport,
    ProfileSettings,
    UnitStatus,
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
from financial_forecasting.features.evaluation.domain.value_objects.profile_parameters import (
    ProfileParameters,
)
from financial_forecasting.features.evaluation.domain.value_objects.quality_check_result import (
    QualityCheckResult,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.services.path_identifier import (
    validate_path_identifier,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
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


def _require_keys(mapping: object, expected: Iterable[str], *, where: str) -> Mapping[str, object]:
    """`mapping` é um `Mapping` com exatamente as chaves `expected` (inversas de `as_mapping`)."""
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{where} must be a Mapping, got {type(mapping).__name__}")
    expected_set = set(expected)
    unknown = sorted(str(key) for key in mapping if key not in expected_set)
    if unknown:
        raise ValueError(f"{where} has unknown keys {unknown}")
    missing = sorted(key for key in expected_set if key not in mapping)
    if missing:
        raise ValueError(f"{where} misses the keys {missing}")
    return mapping


def _as_list(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"{field} must be a list, got {value!r}")
    return list(value)


def _as_int_map(value: object, *, field: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a Mapping, got {value!r}")
    return {str(key): item for key, item in value.items()}  # tipos: o __post_init__


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
    monte_carlo_draws: int
    monte_carlo_seed: int
    mcs_block_sensitivities: tuple[str, ...]
    profile_parameters: ProfileParameters | None

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
        # Stage 6.6 (F8a): os parâmetros dos perfis pelos donos (ADR 6.6.0002 item 5)
        validate_draws_and_seed(self.monte_carlo_draws, self.monte_carlo_seed)
        validate_block_sensitivities(self.mcs_block_sensitivities, field="mcs_block_sensitivities")
        if self.profile_parameters is not None and not isinstance(
            self.profile_parameters, ProfileParameters
        ):
            raise ValueError(
                f"profile_parameters must be a ProfileParameters or None, got "
                f"{self.profile_parameters!r}"
            )

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
            "monte_carlo_draws": self.monte_carlo_draws,
            "monte_carlo_seed": self.monte_carlo_seed,
            "mcs_block_sensitivities": list(self.mcs_block_sensitivities),
            "profile_parameters": (
                None if self.profile_parameters is None else self.profile_parameters.as_payload()
            ),
        }

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> RefreshParameters:
        """Inversa de `as_mapping` (listas → tuplas, enums pelo valor; ADR 6.5.0005 item 3).

        Raises:
            ValueError: chave desconhecida/ausente, enum desconhecido ou valor inválido
                pelo validador dono (o `__post_init__`).
        """
        fields = _require_keys(mapping, _PARAMETER_KEYS, where="parameters")
        estimators = _as_list(fields["dm_variance_estimators"], field="dm_variance_estimators")
        schemes = _as_list(fields["mcs_schemes"], field="mcs_schemes")
        return cls(
            preregistration_ref=fields["preregistration_ref"],  # type: ignore[arg-type]
            degeneracy_tolerance=fields["degeneracy_tolerance"],  # type: ignore[arg-type]
            band_levels=tuple(_as_list(fields["band_levels"], field="band_levels")),  # type: ignore[arg-type]
            min_violations=fields["min_violations"],  # type: ignore[arg-type]
            candidate=fields["candidate"],  # type: ignore[arg-type]
            dm_alpha=fields["dm_alpha"],  # type: ignore[arg-type]
            dm_variance_estimators=tuple(DmVarianceEstimator(str(v)) for v in estimators),
            mcs_alpha=fields["mcs_alpha"],  # type: ignore[arg-type]
            mcs_reps=fields["mcs_reps"],  # type: ignore[arg-type]
            mcs_seed=fields["mcs_seed"],  # type: ignore[arg-type]
            mcs_schemes=tuple(BootstrapScheme(str(v)) for v in schemes),
            monte_carlo_draws=fields["monte_carlo_draws"],  # type: ignore[arg-type]
            monte_carlo_seed=fields["monte_carlo_seed"],  # type: ignore[arg-type]
            mcs_block_sensitivities=tuple(
                str(v)
                for v in _as_list(
                    fields["mcs_block_sensitivities"], field="mcs_block_sensitivities"
                )
            ),
            profile_parameters=(
                None
                if fields["profile_parameters"] is None
                else ProfileParameters.from_mapping(fields["profile_parameters"])
            ),
        )


_PARAMETER_KEYS = (
    "preregistration_ref",
    "degeneracy_tolerance",
    "band_levels",
    "min_violations",
    "candidate",
    "dm_alpha",
    "dm_variance_estimators",
    "mcs_alpha",
    "mcs_reps",
    "mcs_seed",
    "mcs_schemes",
    "monte_carlo_draws",
    "monte_carlo_seed",
    "mcs_block_sensitivities",
    "profile_parameters",
)


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
    dataset_fingerprint: str
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
        # o fingerprint congelado do cohort (ADR 6.4.0009 item 5); o formato hex é do VO
        _check_text(self.dataset_fingerprint, field="dataset_fingerprint")


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
        ValueError: campo de tipo errado, contagem negativa, soma do realizado não-finita,
            timestamp sem fuso ou início depois do fim.
    """

    status: RefreshStatus
    partition: GoldPartition
    rows_by_table: Mapping[str, int]
    parameters: RefreshParameters
    horizons: tuple[int, ...]
    window_deficits: Mapping[str, int]
    dataset_fingerprint: DatasetContentFingerprint
    grid_trimmed_prefix: int
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
        self._check_counts()
        self._check_identity()
        self._check_times()

    def _check_counts(self) -> None:
        for table, count in self.rows_by_table.items():
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"rows_by_table[{table!r}] must be an int >= 0, got {count!r}")
        for name in ("realized_sessions", "n_runs", "grid_trimmed_prefix"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be an int >= 0, got {value!r}")
        fsum = self.realized_returns_fsum
        if not is_finite_number(fsum):
            raise ValueError(f"realized_returns_fsum must be a finite number, got {fsum!r}")

    def _check_identity(self) -> None:
        fingerprint = self.dataset_fingerprint
        if not isinstance(fingerprint, DatasetContentFingerprint):
            raise ValueError(
                f"dataset_fingerprint must be a DatasetContentFingerprint, got {fingerprint!r}"
            )
        for name in ("horizons", "build_order"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(f"{name} must be a tuple, got {getattr(self, name)!r}")

    def _check_times(self) -> None:
        for name in ("started_at", "finished_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError(f"{name} must be a timezone-aware datetime, got {value!r}")
        if self.started_at > self.finished_at:
            raise ValueError(
                f"started_at {self.started_at.isoformat()} is after finished_at "
                f"{self.finished_at.isoformat()}"
            )

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
            "grid_trimmed_prefix": self.grid_trimmed_prefix,
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

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> GoldManifest:
        """Inversa de `as_mapping` (ADR 6.5.0005 item 3) — `from_mapping(m.as_mapping()) == m`.

        Raises:
            ValueError: chave desconhecida/ausente (no topo ou em `realized`),
                `preregistration_ref` de topo ≠ o dos parâmetros, status/enum
                desconhecido, timestamp não-ISO ou campo inválido pelo `__post_init__`.
        """
        fields = _require_keys(mapping, _MANIFEST_KEYS, where="manifest")
        realized = _require_keys(fields["realized"], _REALIZED_KEYS, where="manifest.realized")
        # `_require_keys` do `from_mapping` dos parâmetros recusa o não-`Mapping`
        parameters = RefreshParameters.from_mapping(fields["parameters"])  # type: ignore[arg-type]
        top_ref = fields["preregistration_ref"]
        if top_ref != parameters.preregistration_ref:
            raise ValueError(
                f"manifest preregistration_ref {top_ref!r} differs from "
                f"parameters.preregistration_ref {parameters.preregistration_ref!r}"
            )
        fingerprint = fields["dataset_fingerprint"]
        if not isinstance(fingerprint, str):
            raise ValueError(f"dataset_fingerprint must be a str, got {fingerprint!r}")
        return cls(
            status=RefreshStatus(str(fields["status"])),
            partition=GoldPartition(
                fields["asset"],  # type: ignore[arg-type]
                fields["parent_sweep_id"],  # type: ignore[arg-type]
            ),
            rows_by_table=_as_int_map(fields["rows_by_table"], field="rows_by_table"),
            parameters=parameters,
            horizons=tuple(_as_list(fields["horizons"], field="horizons")),  # type: ignore[arg-type]
            window_deficits=_as_int_map(fields["window_deficits"], field="window_deficits"),
            dataset_fingerprint=DatasetContentFingerprint(fingerprint),
            grid_trimmed_prefix=fields["grid_trimmed_prefix"],  # type: ignore[arg-type]
            realized_sessions=realized["n_sessions"],  # type: ignore[arg-type]
            realized_returns_fsum=realized["returns_fsum"],  # type: ignore[arg-type]
            realized_first_timestamp=realized["first_timestamp"],  # type: ignore[arg-type]
            realized_last_timestamp=realized["last_timestamp"],  # type: ignore[arg-type]
            n_runs=fields["n_runs"],  # type: ignore[arg-type]
            build_order=tuple(_as_list(fields["build_order"], field="build_order")),  # type: ignore[arg-type]
            started_at=_as_datetime(fields["started_at"], field="started_at"),
            finished_at=_as_datetime(fields["finished_at"], field="finished_at"),
        )


_MANIFEST_KEYS = (
    "status",
    "asset",
    "parent_sweep_id",
    "preregistration_ref",
    "rows_by_table",
    "parameters",
    "horizons",
    "window_deficits",
    "dataset_fingerprint",
    "grid_trimmed_prefix",
    "realized",
    "n_runs",
    "build_order",
    "started_at",
    "finished_at",
)
_REALIZED_KEYS = ("n_sessions", "returns_fsum", "first_timestamp", "last_timestamp")


def _as_datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 str, got {value!r}")
    return datetime.fromisoformat(value)


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


class GoldManifestNotFoundError(ApplicationError):
    """A partição não tem geração publicada (sem `MANIFEST.json`; C6, ADR 6.5.0005)."""


class GoldGenerationCorruptError(ApplicationError):
    """A geração lida não se sustenta (C6, ADR 6.5.0005 item 5).

    Manifesto inválido, tabela ausente, contagem divergente, linha inválida, fora de
    ordem ou de outra partição.
    """


# --- leitura de células (F6, Stage 6.6; política de tipo: concept 6.6 D9) -------------


def col(row: Row, schema: GoldTableSchema, column: str) -> object:
    """A célula `column` da linha — só colunas do schema (`key` + `read_columns`).

    Raises:
        KeyError: coluna fora do schema da tabela (leitura por nome sem dono).
    """
    if column not in schema.key and column not in schema.read_columns:
        raise KeyError(f"{column!r} is not a column of the {schema.name} schema")
    return row[column]


def _wrong_type(schema: GoldTableSchema, column: str, expected: str, value: object) -> Exception:
    return GoldGenerationCorruptError(
        f"{schema.name}.{column}: expected {expected}, got {type(value).__name__} {value!r}"
    )


def col_int(row: Row, schema: GoldTableSchema, column: str) -> int:
    """A célula como `int` não-`bool`; outro tipo → `GoldGenerationCorruptError`."""
    value = col(row, schema, column)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _wrong_type(schema, column, "int", value)
    return value


def col_int_or_none(row: Row, schema: GoldTableSchema, column: str) -> int | None:
    """Como `col_int`, aceitando `None`."""
    return None if col(row, schema, column) is None else col_int(row, schema, column)


def col_float(row: Row, schema: GoldTableSchema, column: str) -> float:
    """A célula como `float` (aceita `int` não-`bool`, devolve `float`); senão corrupção."""
    value = col(row, schema, column)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _wrong_type(schema, column, "float", value)
    return float(value)


def col_float_or_none(row: Row, schema: GoldTableSchema, column: str) -> float | None:
    """Como `col_float`, aceitando `None`."""
    return None if col(row, schema, column) is None else col_float(row, schema, column)


def col_bool(row: Row, schema: GoldTableSchema, column: str) -> bool:
    """A célula como `bool`; outro tipo (inclusive `int`) → `GoldGenerationCorruptError`."""
    value = col(row, schema, column)
    if not isinstance(value, bool):
        raise _wrong_type(schema, column, "bool", value)
    return value


def col_bool_or_none(row: Row, schema: GoldTableSchema, column: str) -> bool | None:
    """Como `col_bool`, aceitando `None`."""
    return None if col(row, schema, column) is None else col_bool(row, schema, column)


def col_str(row: Row, schema: GoldTableSchema, column: str) -> str:
    """A célula como `str`; outro tipo → `GoldGenerationCorruptError`."""
    value = col(row, schema, column)
    if not isinstance(value, str):
        raise _wrong_type(schema, column, "str", value)
    return value


def col_str_or_none(row: Row, schema: GoldTableSchema, column: str) -> str | None:
    """Como `col_str`, aceitando `None`."""
    return None if col(row, schema, column) is None else col_str(row, schema, column)


@dataclass(frozen=True)
class GoldGeneration:
    """Uma geração lida: o manifesto e as tabelas pelo nome (ADR 6.5.0005 item 5)."""

    manifest: GoldManifest
    tables: Mapping[str, GoldTable]

    def __post_init__(self) -> None:
        """Mapa das tabelas como cópia somente-leitura."""
        object.__setattr__(self, "tables", MappingProxyType(dict(self.tables)))

    def table(self, schema: GoldTableSchema) -> GoldTable:
        """A tabela do `schema`.

        Raises:
            GoldGenerationCorruptError: a geração não tem a tabela.
        """
        if schema.name not in self.tables:
            raise GoldGenerationCorruptError(f"the generation has no table {schema.name!r}")
        return self.tables[schema.name]

    @classmethod
    def from_stored(
        cls,
        manifest: Mapping[str, object],
        rows_by_table: Mapping[str, Sequence[Row]],
        *,
        partition: GoldPartition,
    ) -> GoldGeneration:
        """Montagem única de uma geração lida — usada pelo fake e pelo real (I7).

        Uma `GoldTable` por tabela do manifesto, com a chave do `GOLD_SCHEMAS`;
        `check_generation` no fim. Uma geração `BLOCKED` volta normal (a recusa é do
        use case). `partition` é a partição pedida ao leitor: manifesto de outra
        partição (ex. pasta copiada) é corrupção, conferida aqui — dono único, fake e
        real (Checkpoint C bloco 2, F2).

        Raises:
            GoldGenerationCorruptError: manifesto inválido; tabela desconhecida,
                ausente de `rows_by_table` ou a mais nele; contagem divergente; linha
                inválida ou fora de ordem; geração incoerente (`check_generation`);
                manifesto de outra partição que a pedida; geração `COMPLETED` sem alguma
                tabela de `GOLD_SCHEMAS` ou `BLOCKED` com tabela confirmatória (6.6).
        """
        try:
            parsed = GoldManifest.from_mapping(manifest)
        except ValueError as error:
            raise GoldGenerationCorruptError(f"invalid manifest: {error}") from error
        if parsed.partition != partition:
            raise GoldGenerationCorruptError(
                f"the manifest is for partition {parsed.partition}, read as {partition}"
            )
        listed = dict(parsed.rows_by_table)
        extra = sorted(set(rows_by_table) - set(listed))
        if extra:
            raise GoldGenerationCorruptError(f"tables {extra} are not in the manifest")
        defect = _table_set_defect(parsed.status, set(listed))
        if defect is not None:
            raise GoldGenerationCorruptError(defect)
        tables: list[GoldTable] = []
        for name, count in listed.items():
            schema = GOLD_SCHEMAS.get(name)
            if schema is None:
                raise GoldGenerationCorruptError(f"unknown gold table {name!r} in the manifest")
            if name not in rows_by_table:
                raise GoldGenerationCorruptError(f"table {name!r} of the manifest is missing")
            rows = rows_by_table[name]
            if len(rows) != count:
                raise GoldGenerationCorruptError(
                    f"table {name!r} has {len(rows)} rows, the manifest says {count}"
                )
            try:
                tables.append(GoldTable(name, schema.key, tuple(rows)))
            except ValueError as error:
                raise GoldGenerationCorruptError(f"table {name!r}: {error}") from error
        try:
            check_generation(parsed.partition, tables, parsed)
        except ValueError as error:
            raise GoldGenerationCorruptError(f"incoherent generation: {error}") from error
        return cls(manifest=parsed, tables={table.name: table for table in tables})


def _table_set_defect(status: RefreshStatus, listed: set[str]) -> str | None:
    """O conjunto de tabelas que o status exige (Stage 6.6, Task 17).

    `COMPLETED` lista **toda** tabela de `GOLD_SCHEMAS` (tabela de perfil ausente é
    corrupção, não "perfil não calculado" — concept A6); `BLOCKED` só as que rodam
    bloqueadas (`GOLD_SCHEMAS` menos `CONFIRMATORY_TABLES`), sem o DTO conhecer builders.
    """
    if status is RefreshStatus.COMPLETED:
        missing = sorted(set(GOLD_SCHEMAS) - listed)
        return None if not missing else f"a COMPLETED generation lacks tables {missing}"
    confirmatory = sorted(listed & set(CONFIRMATORY_TABLES))
    return None if not confirmatory else f"a BLOCKED generation lists {confirmatory}"


def profile_settings_from(parameters: RefreshParameters) -> ProfileSettings:
    """Os parâmetros que os perfis usam, tirados do `RefreshParameters` — escrita única.

    O estimador dos perfis é o **primário** do plano (`dm_variance_estimators[0]`, a ordem
    que `refresh_command_from` fixa); alpha dos recortes = `dm_alpha` (concept 6.6 D3).
    """
    return ProfileSettings(
        candidate=parameters.candidate,
        alpha=parameters.dm_alpha,
        variance_estimator=parameters.dm_variance_estimators[0],
        min_violations=parameters.min_violations,
        tolerance=parameters.degeneracy_tolerance,
        draws=parameters.monte_carlo_draws,
        seed=parameters.monte_carlo_seed,
        profile_parameters=parameters.profile_parameters,
    )


@dataclass(frozen=True, kw_only=True)
class McsBlockRun:
    """Uma rodada do MCS com bloco de sensibilidade (Stage 6.6; ADR 6.6.0002 item 3).

    `report` presente ⇔ `status` `computed`; numa falha do backend ou do MCS (`error`),
    `detail` traz a mensagem e o relatório falta — os demais perfis seguem.
    """

    horizon: int
    block_rule: str
    block_size: int
    scheme: BootstrapScheme
    status: UnitStatus
    detail: str
    report: McsReport | None

    def __post_init__(self) -> None:
        """Relatório presente exatamente quando a rodada foi calculada."""
        if (self.report is not None) != (self.status is UnitStatus.COMPUTED):
            raise ValueError(
                f"McsBlockRun report must be set exactly when status is computed, got "
                f"status={self.status!r}"
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
        profile_reports: os perfis de séries novas por horizonte (Stage 6.6; vazio se
            `BLOCKED`).
        mcs_block_reports: as rodadas do MCS por bloco de sensibilidade (vazio se
            `BLOCKED` ou sem regras de perfil na revisão).

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
    profile_reports: tuple[HorizonProfileReport, ...]
    mcs_block_reports: tuple[McsBlockRun, ...]

    def __post_init__(self) -> None:
        """Coerência status x conteúdo; mapa como cópia somente-leitura."""
        if not isinstance(self.status, RefreshStatus):
            raise ValueError(f"status must be a RefreshStatus, got {self.status!r}")
        if not isinstance(self.block_estimates, Mapping):
            raise ValueError("block_estimates must be a Mapping")
        object.__setattr__(self, "block_estimates", MappingProxyType(dict(self.block_estimates)))
        blocking = any(result.is_blocking for result in self.check_results)
        if self.status is RefreshStatus.BLOCKED and (
            self.horizon_reports
            or self.mcs_reports
            or self.profile_reports
            or self.mcs_block_reports
        ):
            raise ValueError("a BLOCKED generation has no horizon, MCS or profile reports")
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
    profile_error_units: int
