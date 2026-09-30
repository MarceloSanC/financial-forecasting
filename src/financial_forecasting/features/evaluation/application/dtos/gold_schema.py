"""Schema das tabelas gold — dono único de nome, chave e colunas lidas (Stage 6.5).

DTO de aplicação **frozen** (concept 6.5 §4 "Application", D5, I7; ADR `6_5_0005`
itens 2-3). Antes cada builder da 6.4 tinha a sua chave privada (`_KEY`) e o nome
`f"gold_{name}"`; um leitor que precisasse da chave a reescreveria. Aqui:

- `name` — o nome da tabela gravada (`gold_<builder>`);
- `key` — as colunas do grão (a ordem das linhas; technical 6.4 §1 "Tabelas gold");
- `read_columns` — as colunas fora da chave que o scorecard e o perfil leem por
  nome; nenhuma outra coluna é lida por nome fora deste schema.

Consumidores: os cinco builders (`build` devolve a tabela com `name`/`key` daqui) e
`GoldGeneration.from_stored` (monta cada tabela lida com a chave daqui).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final


@dataclass(frozen=True)
class GoldTableSchema:
    """Nome, chave e colunas lidas de uma tabela gold."""

    name: str
    key: tuple[str, ...]
    read_columns: tuple[str, ...]


GOLD_QUALITY_CHECKS: Final = GoldTableSchema(
    name="gold_quality_checks",
    key=("check", "kind", "horizon", "model", "seed"),
    read_columns=("severity", "outcome", "occurrences", "detail"),
)
GOLD_METRICS_BY_RUN: Final = GoldTableSchema(
    name="gold_metrics_by_run",
    key=("model", "seed", "horizon", "sample", "metric", "level_low", "level_high"),
    read_columns=("value", "n_points"),
)
GOLD_CALIBRATION_TABLE: Final = GoldTableSchema(
    name="gold_calibration_table",
    key=(
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
    read_columns=(
        "n_observed",
        "n_violations",
        "degeneracy_rate",
        "wilson_contains_nominal",
        "p_ind",
        "p_cc",
        "independence_status",
    ),
)
GOLD_DM_RESULTS: Final = GoldTableSchema(
    name="gold_dm_results",
    key=("horizon", "variance_estimator", "candidate", "comparator"),
    read_columns=(
        "n_points",
        "mean_differential",
        "statistic",
        "adjusted_p_value",
        "rejected",
        "fallback_applied",
        "alpha",
    ),
)
GOLD_MCS_RESULTS: Final = GoldTableSchema(
    name="gold_mcs_results",
    key=("horizon", "scheme", "model"),
    read_columns=(
        "included",
        "statistic",
        "block_size",
        "max_block_estimate",
        "alpha",
        "reps",
        "seed",
    ),
)

GOLD_SCHEMAS: Final[Mapping[str, GoldTableSchema]] = MappingProxyType(
    {
        schema.name: schema
        for schema in (
            GOLD_QUALITY_CHECKS,
            GOLD_METRICS_BY_RUN,
            GOLD_CALIBRATION_TABLE,
            GOLD_DM_RESULTS,
            GOLD_MCS_RESULTS,
        )
    }
)
"""As cinco tabelas pelo nome."""

CONFIRMATORY_TABLES: Final[tuple[str, ...]] = (
    GOLD_METRICS_BY_RUN.name,
    GOLD_CALIBRATION_TABLE.name,
    GOLD_DM_RESULTS.name,
    GOLD_MCS_RESULTS.name,
)
"""As tabelas que carregam `preregistration_ref` (ADR 6.4.0006 item 4)."""
