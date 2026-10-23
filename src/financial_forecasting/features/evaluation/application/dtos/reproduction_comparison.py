"""DTO da comparação da reprodução e o mapa de classes por coluna (Stage 8.2).

DTOs de aplicação **frozen** (concept 8.2 §4 "`ReproductionComparison`"; ADR `8_2_0002`
itens 1-3). A geração reproduzida é comparada com a julgada na **camada de resultado**,
por valor:

- `REPRODUCTION_CLASSES` — tabela → coluna gravada → classe, **completo** (sem fallback
  por tipo): R1 não-float (contagens, decisões, rótulos, timestamps, sementes), R3 float
  que depende de número aleatório (p-valores do MCS e da sensibilidade de bloco, p-valores
  de Monte Carlo do Christoffersen, limites bootstrap de H3), R2 os demais floats. Cobre
  as colunas que os builders de `adapters/out/duckdb/gold_builders/` gravam, não só
  `key` + `read_columns` do `GoldTableSchema` (technical 8.2 §1);
- `IdentityComparison`, `ClassComparison`, `TableComparison`, `ScorecardComparison` e
  `ReproductionComparison` — o resultado do comparador `compare_reproduction`, com
  `bit_identical` composto (identidade, digests, tabelas e scorecard);
- `AuditReproductionCommand` — o pedido do use case `AuditReproduction` (Task 04): a
  revisão julgada e o scorecard reproduzido já lido do `reproduction/scorecard.json`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    CONFIRMATORY_TABLES,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex


class ReproductionClass(StrEnum):
    """A classe de uma coluna gold na comparação (ADR 8.2.0002 item 2)."""

    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


_R1 = ReproductionClass.R1
_R2 = ReproductionClass.R2
_R3 = ReproductionClass.R3


def _classes(r1: str = "", r2: str = "", r3: str = "") -> dict[str, ReproductionClass]:
    """Colunas por classe, separadas por espaço (uma coluna em uma só classe)."""
    out: dict[str, ReproductionClass] = {}
    for names, cls in ((r1, _R1), (r2, _R2), (r3, _R3)):
        for name in names.split():
            if name in out:
                raise ValueError(f"column {name!r} declared twice")
            out[name] = cls
    return out


# Colunas por tabela, conferidas nos builders (`gold_builders/<tabela>.py`).
_DECLARED: Final[dict[str, dict[str, ReproductionClass]]] = {
    "gold_quality_checks": _classes(
        r1="check kind horizon model seed severity outcome occurrences detail",
        r2="value",
    ),
    "gold_metrics_by_run": _classes(
        r1="model seed horizon sample metric label n_points first_target_timestamp "
        "last_target_timestamp",
        r2="level_low level_high value degeneracy_tolerance",
    ),
    "gold_calibration_table": _classes(
        r1="model seed horizon sample kind includes_degenerate dgt_offset dgt_step n_points "
        "first_target_timestamp last_target_timestamp min_violations n_observed n_violations "
        "n00 n01 n10 n11 independence_status independence_descriptive wilson_applicable "
        "wilson_contains_nominal serial_dependence_warning var_label",
        r2="level_low level_high band_level violation_rate tolerance degeneracy_rate "
        "kupiec_pof kupiec_pof_p_value lr_uc p_uc lr_ind p_ind lr_cc p_cc wilson_estimate "
        "wilson_lower wilson_upper var_level",
    ),
    "gold_dm_results": _classes(
        r1="horizon variance_estimator candidate comparator n_points "
        "common_first_target_timestamp common_last_target_timestamp degrees_of_freedom "
        "horizon_used fallback_applied rejected",
        r2="mean_differential long_run_variance statistic p_value adjusted_p_value alpha",
    ),
    "gold_mcs_results": _classes(
        r1="horizon scheme model elimination_rank included statistic reps seed block_size "
        "generator n_points block_estimates",
        r2="alpha max_block_estimate",
        r3="step_p_value mcs_p_value",
    ),
    "gold_dm_profiles": _classes(
        r1="horizon dimension fold seed comparator candidate status undefined_reason detail "
        "n_points first_target_timestamp last_target_timestamp variance_estimator rejected "
        "fallback_applied horizon_used",
        r2="level mean_differential statistic p_value alpha",
    ),
    "gold_dm_seed_fraction": _classes(
        r1="horizon comparator candidate n_seeds n_rejecting n_undefined",
        r2="fraction_rejecting alpha",
    ),
    "gold_mcs_block_sensitivity": _classes(
        r1="horizon block_rule model status undefined_reason detail scheme block_size "
        "elimination_rank included reps seed n_points",
        r2="alpha",
        r3="step_p_value mcs_p_value",
    ),
    "gold_christoffersen_monte_carlo": _classes(
        r1="model seed horizon sample kind includes_degenerate status detail uc_status "
        "ind_status draws mc_seed attempts",
        r2="level_low level_high",
        r3="mc_p_uc mc_p_ind mc_p_cc",
    ),
    "gold_partial_degeneracy": _classes(
        r1="model seed horizon sample pair_kind status detail",
        r2="level_low level_high collapse_rate tolerance",
    ),
    "gold_differential_acf": _classes(
        r1="horizon model_a model_b lag n_points max_lag",
        r2="acf",
    ),
    "gold_differential_breaks": _classes(
        r1="horizon model_a model_b status undefined_reason detail rejected horizon_used "
        "break_target_timestamp n_points max_lag",
        r2="statistic p_value alpha",
    ),
    "gold_loss_differentials": _classes(
        r1="horizon model_a model_b target_timestamp fold",
        r2="differential",
    ),
    "gold_conformal_corrections": _classes(
        r1="fold_raw fold seed horizon variant tail status reason n rank infinite beta_a beta_b",
        r2="lower_level upper_level tail_level rho correction beta_mean beta_sd",
    ),
    "gold_conformal_coverage": _classes(
        r1="horizon variant kind seed status reason label n_points n_evaluated count "
        "n_seeds_used seeds_excluded mpiw_infinite wilson_contains_nominal "
        "serial_dependence_warning",
        r2="lower_level upper_level band_level n_mean nominal mean_count coverage "
        "mean_of_seed_coverages sd_of_seed_coverages mpiw mean_of_seed_mpiws sd_of_seed_mpiws "
        "crossed_rate mean_of_seed_crossed_rates sd_of_seed_crossed_rates "
        "nesting_violation_rate mean_of_seed_nesting_rates sd_of_seed_nesting_rates "
        "wilson_lower wilson_upper",
    ),
    "gold_h3_importance": _classes(
        r1="method family horizon seed permutation_index n_points status reason",
        r2="importance",
    ),
    "gold_h3_shares": _classes(
        r1="method family lower_infinite upper_infinite side excludes_zero status reason "
        "nonpositive_replicas_h1 nonpositive_replicas_h7 method_status method_reason",
        r2="share_h1 share_h7 delta level",
        r3="lower upper",
    ),
    "gold_h3_reading": _classes(
        r1="reading_rule heterogeneous_permutation heterogeneous_ablation sustained "
        "agreeing_families block_length reps bootstrap_seed n_points "
        "nonpositive_permutation_h1 nonpositive_permutation_h7 nonpositive_ablation_h1 "
        "nonpositive_ablation_h7 ablation_cohort_id label status reason",
        r2="max_block_estimate",
    ),
    "gold_h3_vsn": _classes(
        r1="kind name family n_decisions label status reason",
        r2="p10 p50 p90",
    ),
}


def _with_partition_columns(
    declared: Mapping[str, Mapping[str, ReproductionClass]],
) -> Mapping[str, Mapping[str, ReproductionClass]]:
    """Mais as colunas de `partition_columns` (`asset`, `parent_sweep_id` e, só nas
    confirmatórias, `preregistration_ref`) — a escrita única do builder (I17)."""
    out: dict[str, Mapping[str, ReproductionClass]] = {}
    for table, columns in declared.items():
        partition = {"asset": _R1, "parent_sweep_id": _R1}
        if table in CONFIRMATORY_TABLES:
            partition["preregistration_ref"] = _R1
        clash = sorted(set(partition) & set(columns))
        if clash:
            raise ValueError(f"{table}: partition columns {clash} declared twice")
        out[table] = MappingProxyType({**partition, **columns})
    return MappingProxyType(out)


REPRODUCTION_CLASSES: Final[Mapping[str, Mapping[str, ReproductionClass]]] = (
    _with_partition_columns(_DECLARED)
)
"""Tabela gold → coluna gravada → classe (ADR 8.2.0002 item 2; sem fallback por tipo)."""

IDENTITY_FIELDS: Final = (
    "preregistration_ref",
    "partition",
    "silver_content.digest",
    "dataset_fingerprint",
)
"""Os campos de identidade da reprodução, nesta ordem (I3; ADR 8.2.0002 item 1)."""

MAX_SCORECARD_PATHS: Final = 20
"""Quantos caminhos JSON de folhas diferentes do scorecard o DTO carrega."""


def _check_max_abs_diff(value: object, *, field_name: str) -> None:
    if not isinstance(value, float) or math.isnan(value) or value < 0:
        raise ValueError(f"{field_name} must be a float >= 0 (inf allowed), got {value!r}")


@dataclass(frozen=True)
class IdentityComparison:
    """Um campo de identidade dos dois lados; `equal` vem dos lados (I3).

    Raises:
        ValueError: campo fora de `IDENTITY_FIELDS` ou lado que não é `str`.
    """

    field: str
    judged: str
    reproduced: str
    equal: bool = dataclass_field(init=False)

    def __post_init__(self) -> None:
        if self.field not in IDENTITY_FIELDS:
            raise ValueError(f"identity field must be one of {IDENTITY_FIELDS}, got {self.field!r}")
        for side in ("judged", "reproduced"):
            if not isinstance(getattr(self, side), str):
                raise ValueError(f"identity {side} must be a str, got {getattr(self, side)!r}")
        object.__setattr__(self, "equal", self.judged == self.reproduced)


@dataclass(frozen=True, kw_only=True)
class ClassComparison:
    """Contagens e max |Δ| de uma classe (numa tabela ou no total).

    Campos:
        reproduction_class: R1, R2 ou R3.
        compared: valores comparados (uma linha de chave só de um lado conta 1 em R1).
        different: valores com bits ou tipo diferentes.
        numeric: dos comparados, os pares com os dois lados numéricos não-`bool`.
        max_abs_diff: max |Δ| sobre os pares numéricos (`inf` com NaN/±inf de bits
            diferentes); `None` sem par numérico (R1 só de rótulos reporta a contagem).

    Raises:
        ValueError: contagem negativa ou incoerente, ou max |Δ| sem par numérico, ausente
            com par numérico, negativo/NaN, ou ≠ 0 sem diferença.
    """

    reproduction_class: ReproductionClass
    compared: int
    different: int
    numeric: int
    max_abs_diff: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.reproduction_class, ReproductionClass):
            raise ValueError(
                f"reproduction_class must be a ReproductionClass, got {self.reproduction_class!r}"
            )
        for name in ("compared", "different", "numeric"):
            validate_int_at_least(getattr(self, name), minimum=0, field=name)
        if self.different > self.compared or self.numeric > self.compared:
            raise ValueError(
                f"different ({self.different}) and numeric ({self.numeric}) cannot exceed "
                f"compared ({self.compared})"
            )
        if self.numeric == 0:
            if self.max_abs_diff is not None:
                raise ValueError("max_abs_diff is only defined over numeric pairs (numeric = 0)")
            return
        _check_max_abs_diff(self.max_abs_diff, field_name="max_abs_diff")
        if self.different == 0 and self.max_abs_diff != 0.0:
            raise ValueError(
                f"max_abs_diff must be 0.0 without differences, got {self.max_abs_diff!r}"
            )


def _check_classes(classes: object) -> tuple[ClassComparison, ...]:
    if not isinstance(classes, tuple) or tuple(
        getattr(item, "reproduction_class", None) for item in classes
    ) != tuple(ReproductionClass):
        raise ValueError("classes must be a tuple of ClassComparison for R1, R2, R3 in order")
    if not all(isinstance(item, ClassComparison) for item in classes):
        raise ValueError("classes must hold ClassComparison")
    return classes


@dataclass(frozen=True, kw_only=True)
class TableComparison:
    """Uma tabela gold: linhas de cada lado, chaves iguais e as três classes.

    Raises:
        ValueError: nome vazio, contagem de linhas negativa, classes fora de R1/R2/R3 em
            ordem, ou `keys_equal` incoerente (contagens diferentes, ou chaves desiguais sem
            diferença em R1).
    """

    name: str
    judged_rows: int
    reproduced_rows: int
    keys_equal: bool
    classes: tuple[ClassComparison, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(f"table name must be a non-empty str, got {self.name!r}")
        for name in ("judged_rows", "reproduced_rows"):
            validate_int_at_least(getattr(self, name), minimum=0, field=name)
        if not isinstance(self.keys_equal, bool):
            raise ValueError(f"keys_equal must be a bool, got {self.keys_equal!r}")
        classes = _check_classes(self.classes)
        if self.keys_equal and self.judged_rows != self.reproduced_rows:
            raise ValueError("keys_equal requires the same number of rows on both sides")
        if not self.keys_equal and classes[0].different == 0:
            raise ValueError("unequal keys are R1 differences of the table")

    @property
    def different(self) -> int:
        """Valores diferentes nas três classes."""
        return sum(item.different for item in self.classes)


@dataclass(frozen=True, kw_only=True)
class ScorecardComparison:
    """As folhas dos dois scorecards sem os instantes de `manifest_read` (ADR 8.2.0002 item 3).

    Campos:
        leaves: folhas comparadas (subárvore só de um lado ou de forma diferente conta 1).
        different: folhas diferentes.
        numeric: pares de folhas numéricas não-`bool`.
        max_abs_diff: max |Δ| sobre as folhas numéricas (`None` sem par numérico).
        paths: caminhos JSON das primeiras folhas diferentes (até `MAX_SCORECARD_PATHS`).

    Raises:
        ValueError: contagem incoerente, max |Δ| como em `ClassComparison` ou `paths` com
            tamanho ≠ `min(different, MAX_SCORECARD_PATHS)`.
    """

    leaves: int
    different: int
    numeric: int
    max_abs_diff: float | None
    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        # as mesmas regras de contagem e max |Δ| de uma classe
        ClassComparison(
            reproduction_class=_R2,
            compared=self.leaves,
            different=self.different,
            numeric=self.numeric,
            max_abs_diff=self.max_abs_diff,
        )
        if not isinstance(self.paths, tuple) or not all(
            isinstance(path, str) and path for path in self.paths
        ):
            raise ValueError("paths must be a tuple of non-empty str")
        if len(self.paths) != min(self.different, MAX_SCORECARD_PATHS):
            raise ValueError(
                f"paths must list min(different, {MAX_SCORECARD_PATHS}) paths, "
                f"got {len(self.paths)} for {self.different} differences"
            )

    @property
    def equal(self) -> bool:
        """Nenhuma folha diferente."""
        return self.different == 0


def _total(reproduction_class: ReproductionClass, items: list[ClassComparison]) -> ClassComparison:
    maxima = [item.max_abs_diff for item in items if item.max_abs_diff is not None]
    return ClassComparison(
        reproduction_class=reproduction_class,
        compared=sum(item.compared for item in items),
        different=sum(item.different for item in items),
        numeric=sum(item.numeric for item in items),
        max_abs_diff=max(maxima) if maxima else None,
    )


@dataclass(frozen=True, kw_only=True)
class ReproductionComparison:
    """A geração reproduzida contra a julgada (concept 8.2 §4; ADR 8.2.0002).

    Campos:
        preregistration_ref / partition: a revisão e a partição da geração julgada.
        identity: os quatro campos de `IDENTITY_FIELDS`, nessa ordem.
        judged_result_digest / reproduced_result_digest: `result_layer_digest` dos lados.
        expected_result_digest: o `result_digest` da linha `input_read` do `ATTEMPTS.jsonl`.
        tables: uma `TableComparison` por tabela, ordenadas pelo nome, sem repetição.
        scorecard: a comparação dos scorecards.

    Raises:
        ValueError: campo de tipo ou forma errada, na construção.
    """

    preregistration_ref: str
    partition: GoldPartition
    identity: tuple[IdentityComparison, ...]
    judged_result_digest: str
    reproduced_result_digest: str
    expected_result_digest: str
    tables: tuple[TableComparison, ...]
    scorecard: ScorecardComparison

    def __post_init__(self) -> None:
        if not isinstance(self.preregistration_ref, str) or not self.preregistration_ref:
            raise ValueError(
                f"preregistration_ref must be a non-empty str, got {self.preregistration_ref!r}"
            )
        if not isinstance(self.partition, GoldPartition):
            raise ValueError(f"partition must be a GoldPartition, got {self.partition!r}")
        if (
            not isinstance(self.identity, tuple)
            or tuple(getattr(item, "field", None) for item in self.identity) != IDENTITY_FIELDS
        ):
            raise ValueError(f"identity must be IdentityComparison for {IDENTITY_FIELDS} in order")
        for name in ("judged_result_digest", "reproduced_result_digest", "expected_result_digest"):
            validate_sha256_hex(getattr(self, name), field=name)
        if not isinstance(self.tables, tuple) or not all(
            isinstance(table, TableComparison) for table in self.tables
        ):
            raise ValueError("tables must be a tuple of TableComparison")
        names = [table.name for table in self.tables]
        if names != sorted(set(names)):
            raise ValueError(f"tables must be sorted by name without repetition, got {names}")
        if not isinstance(self.scorecard, ScorecardComparison):
            raise ValueError(f"scorecard must be a ScorecardComparison, got {self.scorecard!r}")

    @property
    def identity_equal(self) -> bool:
        """Os quatro campos de identidade iguais (I3)."""
        return all(item.equal for item in self.identity)

    @property
    def digests_equal(self) -> bool:
        """Os dois `result_layer_digest` iguais ao esperado do `ATTEMPTS.jsonl`."""
        return (
            self.judged_result_digest
            == self.reproduced_result_digest
            == self.expected_result_digest
        )

    @property
    def tables_equal(self) -> bool:
        """Toda tabela com as chaves iguais e nenhuma diferença em classe alguma."""
        return all(table.keys_equal and table.different == 0 for table in self.tables)

    @property
    def totals(self) -> tuple[ClassComparison, ...]:
        """Os totais por classe sobre todas as tabelas (R1, R2, R3)."""
        return tuple(
            _total(cls, [table.classes[index] for table in self.tables])
            for index, cls in enumerate(ReproductionClass)
        )

    @property
    def bit_identical(self) -> bool:
        """Identidade, digests, tabelas e scorecard iguais (R-BIT; ADR 8.2.0002 item 1)."""
        return (
            self.identity_equal
            and self.digests_equal
            and self.tables_equal
            and self.scorecard.equal
        )


@dataclass(frozen=True, kw_only=True)
class AuditReproductionCommand:
    """O pedido da auditoria: a revisão julgada e o scorecard reproduzido (ADR 8.2.0002 item 4).

    `reproduced_scorecard` é o JSON lido de `<reproduzida>/reproduction/scorecard.json` pelo
    adapter de entrada — o use case nunca recalcula o scorecard.

    Raises:
        ValueError: `name` ou `preregistration_ref` vazios; `revision` não-`int`, `bool` ou
            negativa; `reproduced_scorecard` que não é `Mapping`.
    """

    name: str
    revision: int
    preregistration_ref: str
    reproduced_scorecard: Mapping[str, object]

    def __post_init__(self) -> None:
        for name in ("name", "preregistration_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty str, got {value!r}")
        validate_int_at_least(self.revision, minimum=0, field="revision")
        if not isinstance(self.reproduced_scorecard, Mapping):
            raise ValueError(
                "reproduced_scorecard must be a Mapping, got "
                f"{type(self.reproduced_scorecard).__name__}"
            )
