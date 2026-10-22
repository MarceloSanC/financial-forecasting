"""Fábricas da geração gold servida para os testes da Stage 7.4 (Checkpoint C1-2).

Linhas das quatro tabelas que a API serve (`gold_conformal_corrections`,
`gold_h3_shares`, `gold_h3_reading`, `gold_h3_vsn`) com as colunas e os valores que os
builders da 7.2/7.3 gravam (método `loco`, `side` inteiro em {-1, 0, +1}, unidade sem
seed sempre `undefined` e sem medidas), e a geração inteira (manifesto + toda tabela de
`GOLD_SCHEMAS`). Usadas pelo teste unitário do `ReadServingGold`, pelo contrato do
`ServingGoldReader` e pelo e2e da API. Nada aqui vem do cohort real.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    CONFIRMATORY_TABLES,
    GOLD_CONFORMAL_CORRECTIONS,
    GOLD_H3_READING,
    GOLD_H3_SHARES,
    GOLD_H3_VSN,
    GOLD_SCHEMAS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldManifest,
    GoldPartition,
    GoldTable,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.domain.services.contribution_agreement import (
    H3_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.services.vsn_summary import VSN_LABEL
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from tests.unit.features.evaluation._conformal_parameters import conformal_parameters
from tests.unit.features.evaluation._h3_parameters import h3_parameters
from tests.unit.features.evaluation._silver_content import SAMPLE_SILVER_CONTENT

ASSET = "AAPL"
COHORT = "aapl_confirmatory-r0-abc"
PARTITION = GoldPartition(ASSET, COHORT)
REF = "aapl_confirmatory-r3-0123456789ab"
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
SPLIT = "split_cqr_asymmetric_unweighted_v1"
Rows = Mapping[str, Sequence[Mapping[str, object]]]


def refresh_parameters(*, conformal: bool = True, h3: bool = True) -> RefreshParameters:
    return RefreshParameters(
        preregistration_ref=REF,
        degeneracy_tolerance=1e-12,
        band_levels=(0.95, 0.975),
        min_violations=2,
        candidate="tft_quantile",
        dm_alpha=0.05,
        dm_variance_estimators=(DmVarianceEstimator.RECTANGULAR,),
        mcs_alpha=0.10,
        mcs_reps=1000,
        mcs_seed=127,
        mcs_schemes=(BootstrapScheme.STATIONARY,),
        monte_carlo_draws=999,
        monte_carlo_seed=128,
        mcs_block_sensitivities=("h",),
        profile_parameters=None,
        conformal_parameters=conformal_parameters() if conformal else None,
        h3_parameters=h3_parameters() if h3 else None,
    )


def _base(**extra: object) -> dict[str, object]:
    return {"asset": ASSET, "parent_sweep_id": COHORT, "preregistration_ref": REF, **extra}


def correction_row(  # noqa: PLR0913
    fold_raw: str,
    seed: int | None,
    tail: str,
    *,
    status: str = "ok",
    reason: str | None = None,
    n: int | None = 200,
    rank: int | None = 190,
    correction: float | None = 0.004,
    infinite: bool | None = False,
    horizon: int = 1,
) -> dict[str, object]:
    """Uma linha de `gold_conformal_corrections` com as colunas do builder da 7.2."""
    return _base(
        fold_raw=fold_raw,
        fold=int(fold_raw),
        seed=seed,
        horizon=horizon,
        lower_level=0.1,
        upper_level=0.9,
        variant=SPLIT,
        tail=tail,
        tail_level=0.1 if tail == "lower" else 0.9,
        rho=None,
        status=status,
        reason=reason,
        n=n,
        rank=rank,
        correction=correction,
        infinite=infinite,
        beta_a=None,
        beta_b=None,
        beta_mean=None,
        beta_sd=None,
    )


def share_row(method: str, family: str, **fields: object) -> dict[str, object]:
    """Uma linha de `gold_h3_shares` com as colunas do builder da 7.3."""
    values: dict[str, object] = {
        "share_h1": 0.5,
        "share_h7": 0.25,
        "delta": -0.25,
        "lower": -0.5,
        "upper": 0.125,
        "lower_infinite": False,
        "upper_infinite": False,
        "level": 0.9875,
        "side": -1,
        "excludes_zero": False,
        "status": "ok",
        "reason": None,
        "nonpositive_replicas_h1": 0,
        "nonpositive_replicas_h7": 0,
        "method_status": "ok",
        "method_reason": None,
    }
    values.update(fields)
    return _base(method=method, family=family, **values)


def reading_row(**fields: object) -> dict[str, object]:
    """A linha de `gold_h3_reading` com as colunas do builder da 7.3."""
    values: dict[str, object] = {
        "reading_rule": "interval_side_agreement_same_family_v1",
        "heterogeneous_permutation": True,
        "heterogeneous_ablation": False,
        "sustained": True,  # != heterogeneous_ablation (auditoria TA-2)
        "agreeing_families": "price,technical",
        "block_length": 7,
        "max_block_estimate": 6.5,
        "reps": 1000,
        "bootstrap_seed": 129,
        "n_points": 1505,
        "nonpositive_permutation_h1": 0,
        "nonpositive_permutation_h7": 0,
        "nonpositive_ablation_h1": 0,
        "nonpositive_ablation_h7": 0,
        "ablation_cohort_id": "synthetic_ablation_r0_b2b2b2b2b2b2",
        "label": H3_LABEL,
        "status": "ok",
        "reason": None,
    }
    values.update(fields)
    return _base(**values)


def vsn_row(kind: str, name: str, **fields: object) -> dict[str, object]:
    """Uma linha de `gold_h3_vsn` com as colunas do builder da 7.3."""
    values: dict[str, object] = {
        "family": name,
        "p10": 0.125,
        "p50": 0.25,
        "p90": 0.5,
        "n_decisions": 1505,
        "label": VSN_LABEL,
        "status": "ok",
        "reason": None,
    }
    values.update(fields)
    return _base(kind=kind, name=name, **values)


def complete_rows() -> dict[str, list[dict[str, object]]]:
    """As quatro tabelas servidas de uma geração COMPLETED com os dois blocos."""
    return {
        GOLD_CONFORMAL_CORRECTIONS.name: [
            correction_row("0", 1, "lower", correction=0.00390625),
            correction_row("0", 1, "upper", correction=None, infinite=True, n=10, rank=11),
            # a mesma unidade em h+7, com correções próprias (auditoria TA-2)
            correction_row("0", 1, "lower", correction=0.0078125, horizon=7),
            correction_row("0", 1, "upper", correction=0.015625, horizon=7),
            # unidade de run sem seed: sempre undefined e sem medidas (o builder grava
            # assim); o leitor a descarta
            *[
                correction_row(
                    "0",
                    None,
                    tail,
                    status="undefined",
                    reason="run sem seed",
                    n=None,
                    rank=None,
                    correction=None,
                    infinite=None,
                )
                for tail in ("lower", "upper")
            ],
            correction_row(
                "1",
                2,
                "lower",
                status="undefined",
                reason="n < 1/alpha",
                n=None,
                rank=None,
                correction=None,
                infinite=None,
            ),
            correction_row(
                "1",
                2,
                "upper",
                status="undefined",
                reason="n < 1/alpha",
                n=None,
                rank=None,
                correction=None,
                infinite=None,
            ),
        ],
        GOLD_H3_SHARES.name: [
            share_row("loco", "price", lower=None, lower_infinite=True, excludes_zero=True),
            share_row(
                "loco",
                "technical",
                status="undefined",
                reason="Σ* <= 0",
                upper=None,
                upper_infinite=None,
            ),
            share_row("permutation", "price", upper=None, upper_infinite=True),
            share_row(
                "permutation",
                "technical",
                share_h1=None,
                share_h7=None,
                delta=None,
                lower=None,
                upper=None,
                lower_infinite=None,
                upper_infinite=None,
                level=None,
                side=None,
                excludes_zero=None,
                status="undefined",
                reason="método indefinido",
            ),
        ],
        GOLD_H3_READING.name: [reading_row()],
        GOLD_H3_VSN.name: [
            vsn_row("family", "price"),
            vsn_row("variable", "log_return", family="price"),  # family != name
        ],
    }


def generation(
    status: RefreshStatus = RefreshStatus.COMPLETED,
    *,
    rows: Rows | None = None,
    parameters: RefreshParameters | None = None,
) -> tuple[list[GoldTable], GoldManifest]:
    """Tabelas e manifesto de uma geração da partição (COMPLETED lista toda tabela)."""
    given = dict(rows or {})
    names = [
        name
        for name in GOLD_SCHEMAS
        if status is RefreshStatus.COMPLETED or name not in CONFIRMATORY_TABLES
    ]
    tables = [
        GoldTable.sorted_by_key(name, GOLD_SCHEMAS[name].key, given.get(name, ())) for name in names
    ]
    manifest = GoldManifest(
        status=status,
        partition=PARTITION,
        rows_by_table={table.name: len(table.rows) for table in tables},
        parameters=parameters or refresh_parameters(),
        horizons=(1, 7),
        window_deficits={"tft_quantile": 0},
        dataset_fingerprint=DatasetContentFingerprint("ab" * 32),
        grid_trimmed_prefix=0,
        realized_sessions=250,
        realized_returns_fsum=0.125,
        realized_first_timestamp="2024-01-02T00:00:00+00:00",
        realized_last_timestamp="2024-12-31T00:00:00+00:00",
        n_runs=12,
        build_order=tuple(table.name.removeprefix("gold_") for table in tables),
        started_at=NOW,
        finished_at=NOW,
        silver_content=SAMPLE_SILVER_CONTENT,
    )
    return tables, manifest
