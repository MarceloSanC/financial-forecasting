"""Unit test do VO `Preregistration` (Stage 6.5, A1, I1, I4, I14, C1).

`from_mapping` sobre o payload sintético de `_preregistration_payload`: chaves
desconhecidas/ausentes nomeando o caminho, identificadores de regra só do
catálogo, cada bloco pela mensagem do validador dono, regras cruzadas, coerção
int/float, emenda (ADR 6.5.0002), declaração de cegamento opcional (ADR
6.5.0010) e ida e volta pelo `as_payload`. O escritor TOML de teste é provado
por `tomllib.loads` (texto em memória; nenhum arquivo).
"""

from __future__ import annotations

import dataclasses
import re
import tomllib

import pytest

from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    MCS_STATISTIC,
)
from financial_forecasting.features.evaluation.domain.value_objects import (
    preregistration as preregistration_module,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    PROFILE_CATALOG,
    RULE_CATALOG,
    BlindStatus,
    Preregistration,
    RuleIdentifiers,
    ScenarioRole,
    SeedSpec,
)
from tests.unit.features.evaluation._preregistration_payload import (
    PAYLOAD_TOML,
    key_paths,
    to_toml,
    valid_payload,
    with_leaf,
    without_key,
)

_PROFILE_BLOCK: dict[str, object] = {
    "subset_multiplicity": "none_raw_p_descriptive_v1",
    "partial_degeneracy_pairs": "symmetric_and_adjacent_non_degenerate_rows_v1",
    "mcs_block_sensitivity_scheme": "primary_scheme",
    "stationarity": {
        "acf_max_lag": "min_floor_10_log10_T_T_minus_1",
        "break_test": "cusum_mean_dm_primary_variance_kolmogorov_v1",
        "break_alpha": 0.05,
    },
}

_R1_AMENDMENT: dict[str, object] = {
    "revision": 1,
    "amends": "test_plan-r0-0123456789ab",
    "justification": "a blinded correction",
    "blind_status": "blinded",
}


def _plan(payload: dict[str, object] | None = None) -> Preregistration:
    return Preregistration.from_mapping(valid_payload() if payload is None else payload)


def _raises(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Preregistration.from_mapping(payload)


# --- chaves ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "path", ["surprise", "h1_gate.surprise", "rules.dm.surprise", "h1_gate.power_scenarios[0].x"]
)
def test_prereg_unknown_key_rejected(path: str) -> None:
    payload = with_leaf(valid_payload(), path, 1)

    with pytest.raises(ValueError, match="unknown key") as raised:
        Preregistration.from_mapping(payload)
    assert path in str(raised.value)


@pytest.mark.unit
@pytest.mark.parametrize("path", key_paths(valid_payload()))
def test_prereg_missing_key_rejected(path: str) -> None:
    with pytest.raises(ValueError, match="misses the key") as raised:
        Preregistration.from_mapping(without_key(valid_payload(), path))
    assert f"'{path}'" in re.sub(r"\[\d+\]", "", str(raised.value))


# --- regras nomeadas ------------------------------------------------------------------


def _rule_path(key: str) -> str:
    return f"rules.{key}"


@pytest.mark.unit
@pytest.mark.parametrize("key", list(RULE_CATALOG))
def test_prereg_rule_identifier_unimplemented(key: str) -> None:
    payload = with_leaf(valid_payload(), _rule_path(key), RULE_CATALOG[key] + "_v2")

    _raises(
        payload,
        re.escape(f"rules.{key} must be {RULE_CATALOG[key]} (the only rule the domain implements)"),
    )


@pytest.mark.unit
def test_prereg_rule_catalog_complete() -> None:
    fields = {field.name for field in dataclasses.fields(RuleIdentifiers)}

    assert {key.replace(".", "_") for key in RULE_CATALOG} == fields
    assert len(RULE_CATALOG) == len(fields)
    assert RULE_CATALOG["mcs.statistic"] is MCS_STATISTIC
    plan = _plan()
    for key, identifier in RULE_CATALOG.items():
        assert plan.rules.value_of(key) == identifier


# --- validadores donos (um caso por bloco) --------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        pytest.param("name", "bad name", "name must match", id="identity-path-identifier"),
        pytest.param("asset", "AA/PL", "asset must match", id="asset-path-identifier"),
        pytest.param("revision", -1, r"revision must be an int >= 0", id="revision"),
        pytest.param("horizons[0]", 0, r"horizons\[0\] must be an int >= 1", id="horizon-owner"),
        pytest.param(
            "quantile_levels[0]", 1.5, r"quantile_levels\[0\] must be in \(0, 1\)", id="grid-rate"
        ),
        pytest.param(
            "cohort.cohort_id", "a b", "cohort.cohort_id must match", id="cohort-identifier"
        ),
        pytest.param(
            "cohort.cohort_hash", "ABC", "cohort.cohort_hash must be a lowercase", id="cohort-hash"
        ),
        pytest.param(
            "realized.source", "other", "realized.source must be one of", id="realized-source"
        ),
        pytest.param(
            "horizons_not_evaluated[0].horizon",
            0,
            "horizons_not_evaluated.horizon must be an int >= 1",
            id="not-evaluated-horizon",
        ),
        pytest.param("dm.alpha", 1.5, r"alpha must be a finite number in \(0, 1\)", id="dm-alpha"),
        pytest.param(
            "dm.primary_estimator", "parzen", "dm.primary_estimator must be one of", id="dm-enum"
        ),
        pytest.param(
            "mcs.alpha", 0.0, r"alpha must be a finite number in \(0, 1\)", id="mcs-alpha"
        ),
        pytest.param("mcs.reps", 999, r"reps must be >= 1000", id="mcs-reps-floor"),
        pytest.param("mcs.seed", -1, r"seed must be an int >= 0", id="mcs-bootstrap-seed"),
        pytest.param(
            "mcs.block_sensitivities[0]", "T", "mcs.block_sensitivities must hold", id="mcs-block"
        ),
        pytest.param(
            "h1_gate.gate_band_level",
            1.0,
            r"h1_gate.gate_band_level must be in \(0, 1\)",
            id="gate-rate",
        ),
        pytest.param(
            "h1_gate.degeneracy_tolerance",
            -1e-12,
            "h1_gate.degeneracy_tolerance must be a finite number >= 0",
            id="gate-tolerance",
        ),
        pytest.param(
            "h1_gate.sensitivity_alpha",
            1.0,
            r"alpha must be a finite number in \(0, 1\)",
            id="gate-alpha",
        ),
        pytest.param(
            "backtests.min_violations",
            -1,
            r"min_violations must be an int >= 0",
            id="backtests-min-violations",
        ),
        pytest.param(
            "backtests.monte_carlo.draws", 0, r"draws must be an int >= 1", id="monte-carlo-draws"
        ),
        pytest.param(
            "backtests.monte_carlo.seed",
            "x",
            r"backtests.monte_carlo.seed must be an int",
            id="monte-carlo-seed-type",
        ),
    ],
)
def test_prereg_owner_validator_messages(path: str, value: object, message: str) -> None:
    _raises(with_leaf(valid_payload(), path, value), message)


# --- regras cruzadas ------------------------------------------------------------------


@pytest.mark.unit
def test_prereg_tiers_overlap_rejected() -> None:
    payload = with_leaf(valid_payload(), "comparators.ml", ["gbm_quantile", "baseline_ar1"])

    _raises(payload, "comparator tiers must be disjoint, 'baseline_ar1' is in two tiers")


@pytest.mark.unit
def test_prereg_candidate_in_tier_rejected() -> None:
    payload = with_leaf(valid_payload(), "comparators.ml", ["gbm_quantile", "tft_quantile"])

    _raises(payload, "candidate 'tft_quantile' must not be a comparator")


@pytest.mark.unit
def test_prereg_model_without_seed_rejected() -> None:
    _raises(
        without_key(valid_payload(), "seeds.gbm_quantile"),
        "misses the key 'seeds.gbm_quantile'",
    )
    _raises(with_leaf(valid_payload(), "seeds.other_model", [1]), "unknown key 'seeds.other_model'")


@pytest.mark.unit
def test_prereg_model_without_deficit_rejected() -> None:
    _raises(
        without_key(valid_payload(), "window_deficits.baseline_ar1"),
        "misses the key 'window_deficits.baseline_ar1'",
    )


@pytest.mark.unit
def test_prereg_repeated_seeds_rejected() -> None:
    _raises(
        with_leaf(valid_payload(), "seeds.tft_quantile", [1, 2, 2]),
        "seeds.tft_quantile must not repeat seeds",
    )


@pytest.mark.unit
def test_prereg_negative_deficit_rejected() -> None:
    _raises(
        with_leaf(valid_payload(), "window_deficits.gbm_quantile", -1),
        "window_deficits.gbm_quantile must be an int >= 0",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        pytest.param(
            "h1_gate.power_scenarios[0].lower_rate",
            0.0,
            r"lower_rate must be in \(0, 1\)",
            id="rate-zero",
        ),
        pytest.param(
            "h1_gate.power_scenarios[0].upper_rate",
            0.9,
            "lower_rate \\+ upper_rate must be < 1",
            id="sum-not-below-one",
        ),
        pytest.param(
            "h1_gate.power_scenarios[1].label",
            "width_5pp_wide",
            "labels must be unique",
            id="repeated-label",
        ),
        pytest.param(
            "h1_gate.power_scenarios[0].role",
            "tertiary",
            "role must be one of",
            id="unknown-role",
        ),
    ],
)
def test_prereg_power_scenario_invalid(path: str, value: object, message: str) -> None:
    _raises(with_leaf(valid_payload(), path, value), message)


@pytest.mark.unit
def test_prereg_power_scenario_invalid_without_primary() -> None:
    payload = valid_payload()
    for index in range(3):
        payload = with_leaf(payload, f"h1_gate.power_scenarios[{index}].role", "secondary")

    _raises(payload, "at least one primary scenario")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        pytest.param("h1_gate.lower_level", 0.3, "lower_level \\+ upper_level == 1", id="asym"),
        pytest.param("h1_gate.lower_level", 0.6, "lower_level < 0.5 < upper_level", id="order"),
        pytest.param("h1_gate.lower_level", 0.15, "a level of quantile_levels", id="off-grid"),
        pytest.param(
            "horizons_not_evaluated[0].horizon", 7, "disjoint from horizons", id="not-evaluated"
        ),
        pytest.param("horizons", [7, 1], "horizons must be strictly increasing", id="h-order"),
        pytest.param(
            "dm.sensitivity_estimators", ["rectangular"], "must not hold the primary", id="dm-sens"
        ),
        pytest.param(
            "mcs.sensitivity_schemes",
            ["moving_block", "moving_block"],
            "must not repeat values",
            id="mcs-sens",
        ),
    ],
)
def test_prereg_gate_and_grid_cross_rules(path: str, value: object, message: str) -> None:
    payload = with_leaf(valid_payload(), path, value)
    if path == "h1_gate.lower_level" and value == 0.15:  # noqa: PLR2004 — o caso fora da grade
        payload = with_leaf(payload, "h1_gate.upper_level", 0.85)
    _raises(payload, message)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("declared", "message"),
    [
        pytest.param(["dm_bartlett", "dm_new_idea"], "outside the catalog", id="unknown"),
        pytest.param(["dm_bartlett", "dm_bartlett"], "must not repeat", id="repeated"),
    ],
)
def test_prereg_profile_unknown_rejected(declared: list[str], message: str) -> None:
    _raises(with_leaf(valid_payload(), "profiles.declared", declared), message)


@pytest.mark.unit
def test_prereg_profile_catalog_declared_by_payload() -> None:
    assert _plan().profiles.declared == PROFILE_CATALOG


# --- emenda e cegamento ---------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("key", ["amends", "justification", "blind_status"])
def test_prereg_amendment_in_revision_zero(key: str) -> None:
    payload = {**valid_payload(), **{k: v for k, v in _R1_AMENDMENT.items() if k != "revision"}}

    _raises(payload, "forbidden in revision 0")
    only_one = {**valid_payload(), key: _R1_AMENDMENT[key]}
    with pytest.raises(ValueError, match=r"misses the key|forbidden in revision 0"):
        Preregistration.from_mapping(only_one)


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["amends", "justification", "blind_status"])
def test_prereg_amendment_required_after_zero(missing: str) -> None:
    _raises({**valid_payload(), "revision": 1}, "revision 1 requires the amendment fields")
    partial = {**valid_payload(), **_R1_AMENDMENT}
    del partial[missing]
    _raises(partial, f"misses the key '{missing}'")


@pytest.mark.unit
def test_prereg_amendment_complete_accepted() -> None:
    plan = _plan({**valid_payload(), **_R1_AMENDMENT})

    assert plan.revision == 1
    assert plan.amendment is not None
    assert plan.amendment.amends == "test_plan-r0-0123456789ab"
    assert plan.amendment.blind_status is BlindStatus.BLINDED
    _raises({**valid_payload(), **_R1_AMENDMENT, "blind_status": "peeked"}, "blind_status must be")
    _raises({**valid_payload(), **_R1_AMENDMENT, "justification": ""}, "justification must be")


@pytest.mark.unit
def test_prereg_blinding_absent_accepted() -> None:
    plan = _plan()

    assert "blinding_statement" not in valid_payload()
    assert plan.blinding_statement is None
    assert "blinding_statement" not in plan.as_payload()
    stated = _plan({**valid_payload(), "blinding_statement": "a statement"})
    assert stated.blinding_statement == "a statement"


@pytest.mark.unit
def test_prereg_blinding_empty_rejected() -> None:
    _raises({**valid_payload(), "blinding_statement": ""}, "blinding_statement must be a non-empty")


# --- coerção --------------------------------------------------------------------------


@pytest.mark.unit
def test_prereg_int_coerced_to_float() -> None:
    plan = _plan(with_leaf(valid_payload(), "h1_gate.degeneracy_tolerance", 0))

    assert plan.h1_gate.degeneracy_tolerance == 0.0
    assert type(plan.h1_gate.degeneracy_tolerance) is float
    assert type(plan.as_payload()["h1_gate"]["degeneracy_tolerance"]) is float  # type: ignore[index]


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    ["mcs.reps", "revision", "horizons[0]", "backtests.min_violations", "seeds.gbm_quantile[0]"],
)
def test_prereg_float_rejected_where_int(path: str) -> None:
    _raises(with_leaf(valid_payload(), path, 1.0), "must be an int")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("dm.alpha", "dm.alpha must be a number"),
        ("h1_gate.power_scenarios[0].lower_rate", "lower_rate must be a number"),
        ("mcs.reps", "mcs.reps must be an int"),
        ("window_deficits.tft_quantile", "window_deficits.tft_quantile must be an int"),
    ],
)
def test_prereg_bool_rejected_as_number(path: str, message: str) -> None:
    _raises(with_leaf(valid_payload(), path, True), message)


# --- ida e volta ----------------------------------------------------------------------


@pytest.mark.unit
def test_prereg_payload_round_trip() -> None:
    plan = _plan()

    assert Preregistration.from_mapping(plan.as_payload()) == plan
    assert plan.as_payload() == valid_payload()
    r1 = _plan({**valid_payload(), **_R1_AMENDMENT, "blinding_statement": "text"})
    assert Preregistration.from_mapping(r1.as_payload()) == r1
    assert plan.seeds["baseline_ar1"] == SeedSpec(None)
    assert plan.seeds["tft_quantile"].seeds == tuple(range(1, 11))
    assert plan.h1_gate.power_scenarios[0].role is ScenarioRole.PRIMARY
    assert plan.models[0] == "tft_quantile"
    assert plan.comparators == plan.models[1:]
    assert plan.strong == (
        "baseline_ar1",
        "baseline_ewma_vol",
        "baseline_historical_quantiles",
        "gbm_quantile",
    )


@pytest.mark.unit
def test_payload_toml_writer_round_trip() -> None:
    r1 = {**valid_payload(), **_R1_AMENDMENT}
    tricky = {**valid_payload(), "blinding_statement": 'quote " back \\ line\nbell\x07 tab\t'}
    empty_tables = {**valid_payload(), "horizons_not_evaluated": []}

    assert tomllib.loads(PAYLOAD_TOML) == valid_payload()
    for payload in (valid_payload(), r1, tricky, empty_tables):
        assert tomllib.loads(to_toml(payload)) == payload
    assert "\x07" not in to_toml(tricky)
    assert "horizons_not_evaluated = []" in to_toml(empty_tables)
    assert _plan(empty_tables).horizons_not_evaluated == ()


@pytest.mark.unit
def test_prereg_gate_pair_symmetry_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """O par do gate usa o dono da simetria (`is_symmetric_pair`, ADR 6.1.0002)."""
    _plan()
    monkeypatch.setattr(preregistration_module, "is_symmetric_pair", lambda _l, _u: False)
    _raises(valid_payload(), r"lower_level \+ upper_level == 1")


# --- extras da auditoria de testes (rodada 1) -----------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("path", ["cohort.blinding_statement", "h1_gate.amends", "dm.blind_status"])
def test_prereg_nested_optional_key_rejected(path: str) -> None:
    """Auditoria F1: chave opcional e campos de emenda só são aceitos no topo."""
    with pytest.raises(ValueError, match="unknown key") as raised:
        Preregistration.from_mapping(with_leaf(valid_payload(), path, "x"))
    assert f"'{path}'" in str(raised.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        pytest.param(
            "horizons_not_evaluated",
            [{"horizon": 30, "reason": "a"}, {"horizon": 30, "reason": "b"}],
            "horizons_not_evaluated must not repeat horizons",
            id="horizons_not_evaluated",
        ),
        pytest.param(
            "mcs.block_sensitivities",
            ["h", "h"],
            "mcs.block_sensitivities must not repeat values",
            id="block_sensitivities",
        ),
    ],
)
def test_prereg_repeated_list_values_rejected(path: str, value: object, message: str) -> None:
    """Auditoria F6b/F7: valores repetidos nas listas erguem pela mensagem da regra."""
    _raises(with_leaf(valid_payload(), path, value), message)


# --- Stage 6.6 Task 08: bloco opcional `profile_parameters` -----------------------------


@pytest.mark.unit
def test_prereg_profile_parameters_absent_in_r0() -> None:
    plan = _plan()
    assert plan.profile_parameters is None
    assert "profile_parameters" not in plan.as_payload()


@pytest.mark.unit
def test_prereg_profile_parameters_round_trip() -> None:
    payload = {**valid_payload(), **_R1_AMENDMENT, "profile_parameters": _PROFILE_BLOCK}
    plan = _plan(payload)
    assert plan.profile_parameters is not None
    assert plan.profile_parameters.stationarity.break_alpha == 0.05  # noqa: PLR2004
    assert plan.as_payload()["profile_parameters"] == _PROFILE_BLOCK
    assert Preregistration.from_mapping(plan.as_payload()) == plan
    assert tomllib.loads(to_toml(plan.as_payload())) == plan.as_payload()


@pytest.mark.unit
def test_prereg_profile_parameters_rule_outside_the_catalog() -> None:
    block = {**_PROFILE_BLOCK, "subset_multiplicity": "holm_within_subset"}
    _raises(
        {**valid_payload(), "profile_parameters": block},
        r"profile_parameters\.subset_multiplicity must be",
    )


@pytest.mark.unit
def test_prereg_profile_parameters_nested_unknown_key() -> None:
    block = {**_PROFILE_BLOCK, "extra": 1}
    _raises(
        {**valid_payload(), "profile_parameters": block}, "unknown key 'profile_parameters.extra'"
    )


@pytest.mark.unit
def test_prereg_profile_parameters_only_at_the_top() -> None:
    with pytest.raises(ValueError, match="unknown key"):
        Preregistration.from_mapping(with_leaf(valid_payload(), "mcs.profile_parameters", "x"))
