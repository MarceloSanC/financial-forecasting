"""`DmSeedFractionGoldBuilder` — satisfaz o port `GoldBuilder` (`gold_dm_seed_fraction`).

Uma linha por (horizonte, comparador): a fração de seeds do candidato cujo DM rejeita a
alpha, já calculada pelo domínio (`SeedFractionRow`; denominador n_seeds - n_undefined,
ADR 6.6.0003 DM4) — o builder só copia. Sem regras de perfil → nenhuma linha.
"""

from __future__ import annotations

from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders import (
    QUALITY_CHECKS,
    partition_columns,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_DM_SEED_FRACTION,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldInputs,
    GoldTable,
)


class DmSeedFractionGoldBuilder:
    """Fração de seeds que rejeitam, por horizonte e comparador."""

    name = "dm_seed_fraction"
    depends_on = frozenset({QUALITY_CHECKS})
    runs_when_blocked = False

    def build(self, inputs: GoldInputs) -> GoldTable:
        """Uma linha por comparador de cada horizonte com regras de perfil."""
        base = partition_columns(inputs, confirmatory=True)
        rows = [
            {
                **base,
                "horizon": profile.dm_profiles.horizon,
                "comparator": fraction.comparator,
                "candidate": profile.dm_profiles.candidate,
                "n_seeds": fraction.n_seeds,
                "n_rejecting": fraction.n_rejecting,
                "n_undefined": fraction.n_undefined,
                "fraction_rejecting": fraction.fraction_rejecting,
                "alpha": profile.dm_profiles.alpha,
            }
            for profile in inputs.profile_reports
            if profile.dm_profiles is not None
            for fraction in profile.dm_profiles.seed_fractions
        ]
        return GoldTable.sorted_by_key(GOLD_DM_SEED_FRACTION.name, GOLD_DM_SEED_FRACTION.key, rows)
