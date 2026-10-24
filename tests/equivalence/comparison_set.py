"""Conjunto de comparação da equivalência, fixado antes de qualquer valor (Stage 8.2).

Constantes do technical 8.2 §1 ("Conjunto lido da evidência anterior", "D8 fechado na
coluna", "D7 na mecânica", "Variante e níveis do lado novo") e do concept 8.2 D7, D8, D12,
D13. Nada aqui vem de um número: os arquivos, colunas e filtros são do §1; o lado anterior
vem dos NOMES de coluna; o lado novo, do código (caminho citado em cada constante).

`MODEL_LABEL_COLUMN` e `COMMON_BASELINES` são preenchidos só na E1 (rótulos distintos do
`gold_oos_consolidated` e fontes de definição dos baselines — D12 a), no commit do registro
e antes da leitura de valores (D10); até lá ficam vazios (zero comuns ⇒ tabela de baseline
vazia registrada).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# --- evidência anterior (data/analytics/) -----------------------------------------------

PARENT_SWEEP_ID: Final = "phase_b_confirmatorio_20260524"
SPLIT: Final = "test"
HORIZONS: Final = (1, 7)
_REPORTS: Final = f"reports/phase_b/cohort={PARENT_SWEEP_ID}"

GOLD_OOS: Final = "gold/gold_oos_consolidated.parquet"
GOLD_METRICS_BY_RUN: Final = "gold/gold_prediction_metrics_by_run_split_horizon.parquet"
GOLD_CALIBRATION: Final = "gold/gold_prediction_calibration.parquet"
MARGINAL_COVERAGE: Final = f"{_REPORTS}/phase_b_marginal_coverage.parquet"
DM_FAMILY_6: Final = f"{_REPORTS}/phase_b_dm_family_6.parquet"

PRIOR_FILES: Final = (
    GOLD_OOS,
    GOLD_METRICS_BY_RUN,
    GOLD_CALIBRATION,
    MARGINAL_COVERAGE,
    DM_FAMILY_6,
)
"""Os arquivos do registro, e nenhum outro (D5; technical §1)."""

_VARIANT_VALUES: Final = tuple(
    f"{stem}_{variant}"
    for stem in ("pinball_q10", "pinball_q50", "pinball_q90", "picp", "mpiw")
    for variant in ("raw", "post_guardrail")
)

MODEL_LABEL_COLUMN: str | None = "model_version_x"
"""`model_version_x` ou `model_version_y` — o que D-M2 usou; fixado na E1 (só rótulos).

E1: nas 52 280 linhas `parent_sweep_id = phase_b_confirmatorio_20260524`, `split = test`, as
duas colunas têm os mesmos 18 rótulos distintos (15 `*_BTSF` + 3 baselines de D-M2), sem nulo,
e coincidem linha a linha (0 linhas com x != y); fica a `_x`."""
PRIOR_CANDIDATE_LABELS: tuple[str, ...] = (
    "20260524_062419_BTSF",
    "20260524_062723_BTSF",
    "20260524_062922_BTSF",
    "20260524_063226_BTSF",
    "20260524_063508_BTSF",
    "20260524_063811_BTSF",
    "20260524_064010_BTSF",
    "20260524_064145_BTSF",
    "20260524_064431_BTSF",
    "20260524_064641_BTSF",
    "20260524_064851_BTSF",
    "20260524_065100_BTSF",
    "20260524_065400_BTSF",
    "20260524_065620_BTSF",
    "20260524_065828_BTSF",
)
"""Os rótulos (na `MODEL_LABEL_COLUMN`) do candidato anterior `BTSF` (D-M2: 15 `model_version`,
3 janelas x 5 seeds); fixados na E1 pela mesma lista de rótulos distintos, sem valor."""

FILTER_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    GOLD_OOS: (
        "run_id",
        "parent_sweep_id",
        "split",
        "config_signature",
        "seed",
        "fold",
        "horizon",
        "target_timestamp_utc",
    ),
    GOLD_METRICS_BY_RUN: (
        "run_id",
        "parent_sweep_id",
        "config_signature",
        "split",
        "fold",
        "seed",
        "horizon",
        "n_samples",
    ),
    GOLD_CALIBRATION: (
        "run_id",
        "parent_sweep_id",
        "config_signature",
        "split",
        "horizon",
        "n_samples",
    ),
    MARGINAL_COVERAGE: ("run_id", "split", "horizon", "n_obs"),
    DM_FAMILY_6: (
        "horizon",
        "baseline_model_version",
        "split",
        "analysis_role",
        "loss_function",
        "dedup_rule",
        "seed_aggregation",
        "hln_applied",
        "hac_lag_used",
        "n_obs_effective",
    ),
}
"""Colunas de filtro/forma por arquivo (technical §1, tabela do conjunto lido)."""

VALUE_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    GOLD_OOS: (
        "y_true",
        "quantile_p10",
        "quantile_p50",
        "quantile_p90",
        "quantile_p10_post_guardrail",
        "quantile_p50_post_guardrail",
        "quantile_p90_post_guardrail",
        "quantile_guardrail_applied",
    ),
    GOLD_METRICS_BY_RUN: _VARIANT_VALUES,
    GOLD_CALIBRATION: _VARIANT_VALUES,
    MARGINAL_COVERAGE: ("picp_q10_q90", "mpiw"),
    DM_FAMILY_6: ("mean_loss_diff_tft_minus_baseline", "pvalue_one_sided_less"),
}
"""Colunas de valor por arquivo — lidas só depois do commit do registro (E4)."""

TIMESTAMP_COLUMN: Final = "target_timestamp_utc"

# --- níveis, par e variantes (D12 c; D-M2/D-M4) -------------------------------------------

COMMON_LEVELS: Final = (0.1, 0.5, 0.9)
"""Níveis comuns às duas grades, sem reinterpolar (doc §5.3 item 3)."""
PAIR_80: Final = (0.1, 0.9)
NOMINAL_80: Final = 0.8
WILSON_BAND_LEVEL: Final = 0.95
"""Banda de Wilson 95 % do lado do nominal (doc §5.5)."""

PRIOR_QUANTILE_COLUMNS: Final[dict[float, dict[str, str]]] = {
    0.1: {"raw": "quantile_p10", "post_guardrail": "quantile_p10_post_guardrail"},
    0.5: {"raw": "quantile_p50", "post_guardrail": "quantile_p50_post_guardrail"},
    0.9: {"raw": "quantile_p90", "post_guardrail": "quantile_p90_post_guardrail"},
}
PRIOR_LOSS_VARIANT: Final = "post_guardrail"
"""A variante que o anterior declara para a loss (`loss_function =
pinball_loss_post_guardrail`, D-M3) — a do m_A e a de toda coluna sem rótulo (D12 c)."""
MARGINAL_COVERAGE_VARIANT: Final = PRIOR_LOSS_VARIANT
"""`phase_b_marginal_coverage` não rotula a variante → `post_guardrail` (D12 c)."""


def variant_of_column(column: str) -> str:
    """A variante que o nome da coluna de valor declara (`*_raw` / `*_post_guardrail`)."""
    if column.endswith("_post_guardrail"):
        return "post_guardrail"
    if column.endswith("_raw"):
        return "raw"
    return PRIOR_LOSS_VARIANT


NEW_SCORED_VARIANT: Final = "post_guardrail"
"""Lado novo: `CoverageSeries.scored_values` devolve `guardrail_values` (pós-guardrail), nunca o
bruto — `src/financial_forecasting/features/evaluation/domain/value_objects/coverage_series.py`
(`scored_values`, I3)."""
NEW_INTERVAL_IS_CLOSED: Final = True
"""Lado novo: cobertura do par por `is_inside_closed` (L ≤ y ≤ U) —
`domain/services/coverage_metrics.py` (`_pair_coverage`) e `coverage_series.is_inside_closed`."""
NEW_NOMINAL_SIDE_RULE: Final = "wilson_interval(count, n, band_level) contra o nominal"
"""Lado novo: a banda é `wilson_band.wilson_interval` (BCD 2001 Eq. 4) e o veredito
`lower ≤ nominal ≤ upper` (`WilsonBandReport.contains_nominal`) —
`domain/services/wilson_band.py`; o lado do nominal estende o veredito para abaixo/acima."""

# --- D8: DM (sinal e rejeição) -------------------------------------------------------------

PRIOR_DM_MEAN_DIFF: Final = "mean_loss_diff_tft_minus_baseline"
PRIOR_DM_SIGN_CONVENTION: Final = "candidate_minus_baseline"
"""O nome da coluna declara d̄ = perda(candidato) - perda(baseline)."""
PRIOR_DM_P_VALUE: Final = "pvalue_one_sided_less"
"""p do teste primário do anterior; alternativa unilateral d̄ < 0 (candidato melhor)."""
PRIOR_DM_ALPHA: Final = 0.05
"""Declarado no nome `significant_adj_0_05` do anterior."""
PRIOR_DM_ANALYSIS_ROLE: Final = "primary_family_6"
NEW_DM_TABLE: Final = "gold_dm_results"
NEW_DM_ESTIMATOR: Final = "rectangular"
"""Estimador primário (ADR 6.5.0006)."""
NEW_DM_SIGN_CONVENTION: Final = "candidate_minus_baseline"
"""Lado novo: d_t = L_candidato - L_comparador (`paired_loss_series.differential`;
`diebold_mariano.py`: "d̄ (< 0 favorece o candidato)")."""
NEW_DM_P_VALUE: Final = "p_value"
"""O `p_value` não ajustado (não o `adjusted_p_value` de Holm), contra o `alpha` da linha."""

# --- D7 e D13 -------------------------------------------------------------------------------

PRIOR_DEDUP_RULE: Final = "operationally_latest_fold"
"""D7: num `target_timestamp` com duas janelas, o ponto da janela de teste mais recente."""
A1_HALF_ULP: Final = 2.0**-53
"""D13: meio ulp do `double` gravado pelo anterior, na magnitude de y_ant."""
A1_FLOAT32_DEVIATION: Final = "desvio B3 (ADR 8.2.0004): A1 por meio ulp de float32"
"""Rótulo de desvio pós-A1 (declarado antes de qualquer número de modelo): marca o A1 de um
horizonte julgado pela regra float32 (pré-condição: todo y_ant exatamente representável em
float32) e, com ele, toda comparação de modelo daquele horizonte."""
STORAGE_HALF_ULP_DOUBLE: Final = 2.0**-53
"""D12 e: precisão de armazenamento de m_ant (`double`)."""
HALF_ULP_BY_TYPE: Final[dict[str, float]] = {"double": 2.0**-53, "float": 2.0**-24}
"""Meio ulp por tipo físico do footer (`str(pyarrow.DataType)`): D12 e, D13 — a precisão de
armazenamento sai do tipo REGISTRADO da coluna, não de uma suposição (CC4-5)."""


def half_ulp_of(physical_type: str) -> float:
    """Meio ulp do tipo físico registrado.

    Raises:
        ValueError: tipo sem precisão de ponto flutuante conhecida (ex.: texto, inteiro).
    """
    if physical_type not in HALF_ULP_BY_TYPE:
        raise ValueError(f"no floating-point storage precision for physical type {physical_type!r}")
    return HALF_ULP_BY_TYPE[physical_type]


R2_RELATIVE: Final = 1e-9
"""Doc §4.3 R2: o default relativo de `math.isclose`."""


@dataclass(frozen=True)
class CommonBaseline:
    """Um baseline comum por definição (D12 a): rótulo de cada lado e a fonte."""

    prior_label: str
    new_label: str
    source: str


COMMON_BASELINES: tuple[CommonBaseline, ...] = ()
"""Preenchido só na E1 (D12 a); vazio = zero comuns, tabela vazia registrada.

E1 (technical 8.2 §7, `[decision:C] E1 — baselines comuns`): zero comuns. (a) o commit do
`dim_run` do anterior (`2dc19116…`, só nas linhas do candidato; baselines com `git_commit`
nulo) não existe em nenhum repositório local; (b) o payload `training_config_json` do
`silver/fact_config` do anterior declara só família e janela (`zero_return` sem janela,
`historical_mean_rolling` W = 30, `historical_quantiles_rolling` W = 252), sem estimador de
quantil nem regra de dispersão; lado novo (`features/modeling/domain/services/
baseline_emission.py`, `quantile_grid_emission.py`): `zero_return` grade degenerada em 0,
`historical_mean` média do train expansivo (grade degenerada), `historical_quantiles` quantil
tipo 7 de W = 252. Nenhum par tem as quatro partes declaradas equivalentes."""
