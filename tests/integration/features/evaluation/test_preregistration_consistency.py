"""Consistência do pré-registro AAPL r0 com o cohort, os ADRs e o espelho (Stage 6.5 Task 13).

Teste de integração sobre **arquivos versionados** (nenhum dado): lê o r0 pelo
`TomlPreregistrationSource` (o mesmo caminho do use case), monta o VO e o hash com o
`CanonicalJsonHasher`; lê o arquivo do cohort pelo carregador da `modeling`
(`cohort_file.parse`) e o hash por `CohortHash` — o teste, não o `src/`, cruza para a
`modeling` (ADR 6.5.0004 item 4), e os nomes de modelo vêm das constantes dos
escritores. Confere ainda os valores dos ADRs 6.5.0009/0010, as taxas de locação pelo
`NormalDist`, a citação do hash completo de toda revisão no espelho e a regra
`CLAIM_TERMS`: nenhuma frase do TOML nem do espelho afirma algo sobre o passado do
cohort (ADR 6.5.0010 P1).
"""

from __future__ import annotations

import importlib
import re
from datetime import UTC, datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any

import pytest

from financial_forecasting.features.evaluation.adapters.out.toml.toml_preregistration_source import (  # noqa: E501
    TomlPreregistrationSource,
)
from financial_forecasting.features.evaluation.domain.services.diebold_mariano import (
    DmVarianceEstimator,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    PROFILE_CATALOG,
    Preregistration,
    ScenarioRole,
)
from financial_forecasting.features.modeling.application.use_cases import (
    train_gbm_quantile,
    train_tft,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)

pytestmark = pytest.mark.integration

# `in` é palavra reservada: o pacote `adapters/in/` entra por `importlib` (LAYOUT §8).
cohort_file: Any = importlib.import_module(
    "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
)

_REPO = Path(__file__).resolve().parents[4]
_PREREG_DIR = _REPO / "config" / "preregistration"
_COHORT_FILE = _REPO / "config/cohorts/aapl_confirmatory.toml"
_MIRROR = _REPO / "docs" / "preregistration" / "aapl_confirmatory.md"
_REVISION_FILE = re.compile(r"^(?P<name>.+)-r(?P<rev>\d+)\.toml$")
_RATE_TOLERANCE = 1e-12  # repr gravado uma vez vs recálculo (technical §5)

# Regra da afirmação proibida (technical §2 Task 13 item 3; Checkpoint B r2, item 1):
# uma frase casa os QUATRO termos, em qualquer ordem, sem caixa, com fronteira de palavra.
CLAIM_TERMS = (
    r"\b(nenhuma|nenhum|nunca|jamais|never)\b|\bno\s+metrics?\b",
    r"\b(métricas?|metrics?)\b",
    r"\b(comput\w*|calcul\w*)\b",
    r"\b(r0|cohort|coorte)\b",
)


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n\s*\n", flat) if s.strip()]


def claims_about_past(text: str) -> list[str]:
    """As frases do texto que casam os quatro termos do `CLAIM_TERMS`."""
    return [
        sentence
        for sentence in _sentences(text)
        if all(re.search(term, sentence, re.IGNORECASE) for term in CLAIM_TERMS)
    ]


def _r0() -> tuple[Preregistration, PreregistrationHash]:
    record = TomlPreregistrationSource(root=_PREREG_DIR).read(name="aapl_confirmatory", revision=0)
    prereg = Preregistration.from_mapping(record.payload)
    digest = PreregistrationHash.compute(hasher=CanonicalJsonHasher(), payload=prereg.as_payload())
    return prereg, digest


def test_r0_matches_cohort() -> None:
    prereg, _ = _r0()
    spec = cohort_file.parse(_COHORT_FILE.read_text(encoding="utf-8"))
    cohort_hash = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())

    assert prereg.asset == spec.asset_id
    assert prereg.cohort.cohort_id == spec.cohort_id(cohort_hash)
    assert prereg.cohort.cohort_hash == cohort_hash.value
    assert prereg.realized.dataset_fingerprint == spec.dataset_fingerprint
    assert prereg.horizons == spec.horizons
    assert prereg.quantile_levels == spec.quantile_levels
    assert prereg.candidate == train_tft.MODEL_VERSION
    assert prereg.seeds[train_tft.MODEL_VERSION].seeds == spec.seeds
    assert spec.gbm_params is not None
    assert prereg.seeds[train_gbm_quantile.MODEL_VERSION].seeds == (spec.gbm_params.seed,)
    baselines = {b.model_version for b in spec.baseline_specs}
    for model in baselines:
        assert prereg.seeds[model].seeds is None
    assert (
        set(prereg.models)
        == {
            train_tft.MODEL_VERSION,
            train_gbm_quantile.MODEL_VERSION,
        }
        | baselines
    )


def test_r0_values_match_adrs() -> None:
    prereg, _ = _r0()
    gate, dm, mcs = prereg.h1_gate, prereg.dm, prereg.mcs

    assert (prereg.name, prereg.revision, prereg.amendment) == ("aapl_confirmatory", 0, None)
    assert [(e.horizon, e.reason) for e in prereg.horizons_not_evaluated] == [
        (30, "not in the cohort")
    ]
    assert prereg.comparator_tiers.naive == ("baseline_zero_return", "baseline_historical_mean")
    assert prereg.comparator_tiers.strong_statistical == (
        "baseline_ar1",
        "baseline_ewma_vol",
        "baseline_historical_quantiles",
    )
    assert prereg.comparator_tiers.ml == ("gbm_quantile",)
    assert set(prereg.window_deficits.values()) == {0}
    assert (dm.alpha, dm.primary_estimator, dm.sensitivity_estimators) == (
        0.05,
        DmVarianceEstimator.RECTANGULAR,
        (DmVarianceEstimator.BARTLETT,),
    )
    assert (mcs.alpha, mcs.reps, mcs.seed) == (0.10, 1000, 127)
    assert (mcs.primary_scheme, mcs.sensitivity_schemes) == (
        BootstrapScheme.STATIONARY,
        (BootstrapScheme.MOVING_BLOCK,),
    )
    assert mcs.block_sensitivities == ("h", "sqrt_T")
    assert (gate.lower_level, gate.upper_level) == (0.1, 0.9)
    assert (gate.gate_band_level, gate.profile_band_level) == (0.975, 0.95)
    assert gate.degeneracy_threshold == 0.01  # noqa: PLR2004 — P2 do ADR 6.5.0010
    assert gate.degeneracy_tolerance == 1e-12  # noqa: PLR2004
    assert gate.sensitivity_alpha == 0.05  # noqa: PLR2004
    scenarios = {s.label: (s.role, s.lower_rate, s.upper_rate) for s in gate.power_scenarios}
    assert scenarios["width_5pp_wide"] == (ScenarioRole.PRIMARY, 0.125, 0.125)
    assert scenarios["width_5pp_narrow"] == (ScenarioRole.PRIMARY, 0.075, 0.075)
    assert scenarios["width_3pp_wide"] == (ScenarioRole.SECONDARY, 0.115, 0.115)
    assert scenarios["width_3pp_narrow"] == (ScenarioRole.SECONDARY, 0.085, 0.085)
    assert scenarios["location_0_2_sigma"][0] is ScenarioRole.PRIMARY
    assert scenarios["location_0_1_sigma"][0] is ScenarioRole.SECONDARY
    assert prereg.min_violations == 2  # noqa: PLR2004
    assert (prereg.monte_carlo.draws, prereg.monte_carlo.seed) == (999, 128)
    assert prereg.profiles.declared == PROFILE_CATALOG
    assert prereg.blinding_statement is not None


@pytest.mark.parametrize(
    ("label", "sigmas"), [("location_0_2_sigma", 0.2), ("location_0_1_sigma", 0.1)]
)
def test_r0_location_rates_normal(label: str, sigmas: float) -> None:
    prereg, _ = _r0()
    scenario = next(s for s in prereg.h1_gate.power_scenarios if s.label == label)
    normal = NormalDist()
    z = normal.inv_cdf(0.9)

    assert scenario.lower_rate == pytest.approx(normal.cdf(-z - sigmas), abs=_RATE_TOLERANCE)
    assert scenario.upper_rate == pytest.approx(1 - normal.cdf(z - sigmas), abs=_RATE_TOLERANCE)


def test_every_revision_hash_quoted() -> None:
    mirror = _MIRROR.read_text(encoding="utf-8")
    revisions = [p for p in sorted(_PREREG_DIR.iterdir()) if _REVISION_FILE.match(p.name)]

    assert [p.name for p in revisions] == ["aapl_confirmatory-r0.toml"]
    for path in revisions:
        match = _REVISION_FILE.match(path.name)
        assert match is not None
        record = TomlPreregistrationSource(root=_PREREG_DIR).read(
            name=match["name"], revision=int(match["rev"])
        )
        prereg = Preregistration.from_mapping(record.payload)
        digest = PreregistrationHash.compute(
            hasher=CanonicalJsonHasher(), payload=prereg.as_payload()
        )
        assert digest.value in mirror, f"{path.name}: full hash not quoted in the mirror"
        assert prereg.reference(digest) in mirror


def test_no_claim_about_r0_past() -> None:
    for sentence in (
        "Nunca foi calculada nenhuma métrica sobre o r0",
        "The r0 cohort has never had a metric computed on it",
        "No metric was ever computed on the cohort",
    ):
        assert claims_about_past(sentence) == [sentence]
    for sentence in (
        "A 8.1 roda o refresh no cohort e cada métrica é calculada sobre o cohort r0",
        "o perfil jamais troca o veredito",
        "Todos os testes da 6.5 usam dados sintéticos",
    ):
        assert claims_about_past(sentence) == []
    prereg, _ = _r0()
    assert prereg.blinding_statement is not None
    assert claims_about_past(prereg.blinding_statement) == []
    for path in (_PREREG_DIR / "aapl_confirmatory-r0.toml", _MIRROR):
        assert claims_about_past(path.read_text(encoding="utf-8")) == [], path.name


_COHORT_ANCHORED_AT = datetime(2026, 9, 28, 20, 27, 9, tzinfo=UTC)  # comentário na #102


def test_anchor_record_matches_ref() -> None:
    prereg, digest = _r0()
    record = TomlPreregistrationSource(root=_PREREG_DIR).read(name="aapl_confirmatory", revision=0)

    assert record.anchor is not None
    assert record.anchor.tag == f"preregistration/{prereg.reference(digest)}"
    assert record.anchor.anchored_at > _COHORT_ANCHORED_AT
    assert record.anchor.comment_url.startswith("https://github.com/")
    assert "/issues/127#issuecomment-" in record.anchor.comment_url
    mirror = _MIRROR.read_text(encoding="utf-8")
    assert record.anchor.comment_url in mirror
    assert record.anchor.commit in mirror
