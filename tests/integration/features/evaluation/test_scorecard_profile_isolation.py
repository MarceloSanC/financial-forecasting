"""Isolamento do veredito em relação aos perfis de séries novas (Stage 6.6, CA11, I12).

A camada evidência + `ConfirmatoryScorecard.decide` nunca lê uma tabela de perfil: um
leitor espião registra cada `table(schema)` pedido; o veredito é o mesmo com as tabelas de
perfil vazias, com conteúdo adversarial (MCS por bloco excluindo o candidato, nenhum DM
por recorte rejeitando, quebra em toda d_t) e sem elas (geração montada direto, sem o
`from_stored`, que recusaria a geração incompleta). O perfil, ao contrário, as lê.
"""

from __future__ import annotations

import dataclasses

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CHRISTOFFERSEN_MONTE_CARLO,
    GOLD_DIFFERENTIAL_ACF,
    GOLD_DIFFERENTIAL_BREAKS,
    GOLD_DM_PROFILES,
    GOLD_DM_SEED_FRACTION,
    GOLD_LOSS_DIFFERENTIALS,
    GOLD_MCS_BLOCK_SENSITIVITY,
    GOLD_PARTIAL_DEGENERACY,
    GoldTableSchema,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldTable,
)
from financial_forecasting.features.evaluation.application.use_cases.scorecard_evidence import (
    evidence_from_generation,
)
from financial_forecasting.features.evaluation.application.use_cases.scorecard_profile import (
    build_profile,
)
from financial_forecasting.features.evaluation.domain.services.confirmatory_scorecard import (
    ConfirmatoryScorecard,
    ScorecardVerdict,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from tests.unit.features.evaluation._preregistration_payload import r1_payload
from tests.unit.features.evaluation._scorecard_factory import REFERENCE, StoredGold, make_stored

pytestmark = pytest.mark.integration

_PLAN = Preregistration.from_mapping(r1_payload())
_COMMAND = refresh_command_from(_PLAN, REFERENCE)
_PROFILE_TABLES = frozenset(
    schema.name
    for schema in (
        GOLD_DM_PROFILES,
        GOLD_DM_SEED_FRACTION,
        GOLD_MCS_BLOCK_SENSITIVITY,
        GOLD_CHRISTOFFERSEN_MONTE_CARLO,
        GOLD_PARTIAL_DEGENERACY,
        GOLD_DIFFERENTIAL_ACF,
        GOLD_DIFFERENTIAL_BREAKS,
        GOLD_LOSS_DIFFERENTIALS,
    )
)


@dataclasses.dataclass(frozen=True)
class _SpyGeneration(GoldGeneration):
    """`GoldGeneration` que registra cada tabela pedida."""

    reads: list[str] = dataclasses.field(default_factory=list)

    def table(self, schema: GoldTableSchema) -> GoldTable:
        self.reads.append(schema.name)
        return super().table(schema)


def _spy(generation: GoldGeneration) -> _SpyGeneration:
    return _SpyGeneration(manifest=generation.manifest, tables=generation.tables)


def _verdict(generation: GoldGeneration) -> ScorecardVerdict:
    evidence = evidence_from_generation(prereg=_PLAN, command=_COMMAND, generation=generation)
    return ConfirmatoryScorecard.decide(_PLAN, evidence)


def _baseline() -> StoredGold:
    stored = make_stored(_PLAN)
    assert all(stored.rows[name] for name in _PROFILE_TABLES)  # forma da r1: tudo preenchido
    return stored


@pytest.mark.integration
def test_evidence_and_decide_read_no_profile_table() -> None:
    spy = _spy(_baseline().generation())
    _verdict(spy)
    assert spy.reads
    assert not set(spy.reads) & _PROFILE_TABLES


@pytest.mark.integration
def test_the_profile_does_read_the_profile_tables() -> None:
    """Controle do espião: o perfil lê as tabelas que o veredito não lê."""
    spy = _spy(_baseline().generation())
    evidence = evidence_from_generation(prereg=_PLAN, command=_COMMAND, generation=spy)
    verdict = ConfirmatoryScorecard.decide(_PLAN, evidence)
    before = len(spy.reads)
    build_profile(prereg=_PLAN, evidence=evidence, verdict=verdict, generation=spy)
    assert _PROFILE_TABLES - {GOLD_LOSS_DIFFERENTIALS.name} <= set(spy.reads[before:])


@pytest.mark.integration
def test_verdict_identical_with_empty_profile_tables() -> None:
    baseline = _verdict(_baseline().generation())
    stored = _baseline()
    for name in _PROFILE_TABLES:
        stored.drop_rows(name, lambda _row: True)
    assert _verdict(stored.generation()) == baseline


@pytest.mark.integration
def test_verdict_identical_with_adversarial_profile_content() -> None:
    """MCS por bloco excluindo o candidato, nenhum recorte do DM rejeitando, quebra em toda
    d_t, MC rejeitando: o veredito não muda."""
    baseline = _verdict(_baseline().generation())
    stored = _baseline()
    candidate = _PLAN.candidate
    assert stored.set_cell(
        GOLD_MCS_BLOCK_SENSITIVITY.name, lambda r: r["model"] == candidate, "included", False
    )
    assert stored.set_cell(GOLD_DM_PROFILES.name, lambda _r: True, "rejected", False)
    assert stored.set_cell(GOLD_DM_SEED_FRACTION.name, lambda _r: True, "n_rejecting", 0)
    assert stored.set_cell(GOLD_DIFFERENTIAL_BREAKS.name, lambda _r: True, "rejected", True)
    assert stored.set_cell(GOLD_CHRISTOFFERSEN_MONTE_CARLO.name, lambda _r: True, "mc_p_cc", 0.0)
    assert stored.set_cell(GOLD_PARTIAL_DEGENERACY.name, lambda _r: True, "collapse_rate", 1.0)
    assert _verdict(stored.generation()) == baseline


@pytest.mark.integration
def test_verdict_identical_without_the_profile_tables() -> None:
    """Geração sem as oito tabelas, montada direto (o `from_stored` a recusaria)."""
    full = _baseline().generation()
    without = GoldGeneration(
        manifest=full.manifest,
        tables={name: t for name, t in full.tables.items() if name not in _PROFILE_TABLES},
    )
    assert _PROFILE_TABLES.isdisjoint(without.tables)
    assert _verdict(without) == _verdict(full)
