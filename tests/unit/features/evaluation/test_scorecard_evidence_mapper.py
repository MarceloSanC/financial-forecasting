"""Unit test do mapeador linhas do gold → evidência (Stage 6.5, A8, I6, I7, I10, C6, C8).

Sobre o gold sintético da `_scorecard_factory` (coerente com o plano), cada teste
aplica **uma** violação: campo do manifesto, conjunto de modelos/seeds/níveis, regra do
MCS → `PreregistrationMismatchError` com o `field` exato; linha esperada faltando para
modelo/seed presente → `GoldGenerationCorruptError`; mismatch antes de corrupção; a
evidência montada por horizonte lê as caudas do gate só nas linhas do nível da banda do
gate e só colunas do schema.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    MismatchField,
    PreregistrationMismatchError,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CALIBRATION_TABLE,
    GOLD_DM_RESULTS,
    GOLD_MCS_RESULTS,
    GOLD_METRICS_BY_RUN,
    GOLD_QUALITY_CHECKS,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGenerationCorruptError,
)
from financial_forecasting.features.evaluation.application.use_cases import (
    scorecard_evidence as mapper_module,
)
from financial_forecasting.features.evaluation.application.use_cases.scorecard_evidence import (
    evidence_from_generation,
)
from financial_forecasting.features.evaluation.domain.services.confirmatory_scorecard import (
    ConfirmatoryScorecard,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from tests.unit.features.evaluation._preregistration_payload import valid_payload
from tests.unit.features.evaluation._scorecard_factory import (
    REFERENCE,
    StoredGold,
    make_stored,
)

_PLAN = Preregistration.from_mapping(valid_payload())
_COMMAND = refresh_command_from(_PLAN, REFERENCE)
_CAND = _PLAN.candidate
Row = dict[str, object]


def _map(stored: StoredGold) -> object:
    return evidence_from_generation(prereg=_PLAN, command=_COMMAND, generation=stored.generation())


def _mismatch(stored: StoredGold, field: MismatchField) -> None:
    with pytest.raises(PreregistrationMismatchError) as raised:
        _map(stored)
    assert raised.value.field == field
    assert field.value in str(raised.value)


def _corrupt(stored: StoredGold, match: str) -> None:
    with pytest.raises(GoldGenerationCorruptError, match=match):
        _map(stored)


def _is(**values: object) -> Callable[[Row], bool]:
    return lambda row: all(row.get(k) == v for k, v in values.items())


def _other_cohort() -> StoredGold:
    payload = valid_payload()
    payload["cohort"]["cohort_id"] = "other_cohort-r0-0123456789ab"  # type: ignore[index]
    return make_stored(Preregistration.from_mapping(payload))


def _manifest_change(key: str, value: object) -> Callable[[], StoredGold]:
    def build() -> StoredGold:
        stored = make_stored(_PLAN)
        stored.manifest[key] = value
        return stored

    return build


def _parameters_change() -> StoredGold:
    stored = make_stored(_PLAN)
    stored.manifest["parameters"]["mcs_seed"] = 128  # type: ignore[index]
    return stored


def _deficit_change() -> StoredGold:
    stored = make_stored(_PLAN)
    stored.manifest["window_deficits"]["gbm_quantile"] = 1  # type: ignore[index]
    return stored


@pytest.mark.unit
@pytest.mark.parametrize(
    ("build", "field"),
    [
        pytest.param(_other_cohort, MismatchField.PARTITION, id="partition"),
        pytest.param(
            lambda: make_stored(_PLAN, reference="test_plan-r0-ffffffffffff"),
            MismatchField.PREREGISTRATION_REF,
            id="preregistration_ref",
        ),
        pytest.param(_parameters_change, MismatchField.PARAMETERS, id="parameters"),
        pytest.param(_manifest_change("horizons", [1]), MismatchField.HORIZONS, id="horizons"),
        pytest.param(_deficit_change, MismatchField.WINDOW_DEFICITS, id="window_deficits"),
        pytest.param(
            _manifest_change("dataset_fingerprint", "cd" * 32),
            MismatchField.DATASET_FINGERPRINT,
            id="dataset_fingerprint",
        ),
    ],
)
def test_mismatch_manifest_field(build: Callable[[], StoredGold], field: MismatchField) -> None:
    _mismatch(build(), field)


def _copy_model(stored: StoredGold, table: str, column: str, source: str, target: str) -> None:
    stored.rows[table] += [{**r, column: target} for r in stored.rows[table] if r[column] == source]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column"),
    [
        (GOLD_DM_RESULTS.name, "comparator"),
        (GOLD_MCS_RESULTS.name, "model"),
        (GOLD_CALIBRATION_TABLE.name, "model"),
        (GOLD_METRICS_BY_RUN.name, "model"),
    ],
)
@pytest.mark.parametrize("direction", ["missing", "extra"])
def test_mismatch_model_extra_missing(table: str, column: str, direction: str) -> None:
    stored = make_stored(_PLAN)
    if direction == "missing":
        assert stored.drop_rows(table, _is(**{column: "baseline_ar1"}))
    else:
        _copy_model(stored, table, column, "baseline_ar1", "baseline_new")

    _mismatch(stored, MismatchField.MODELS)


@pytest.mark.unit
@pytest.mark.parametrize("table", [GOLD_METRICS_BY_RUN.name, GOLD_CALIBRATION_TABLE.name])
@pytest.mark.parametrize("direction", ["missing", "extra"])
def test_mismatch_seed_extra_missing(table: str, direction: str) -> None:
    stored = make_stored(_PLAN)
    if direction == "missing":
        assert stored.drop_rows(table, _is(model=_CAND, seed=3))
    else:
        stored.add_seed(_CAND, 11, tables=[table])

    _mismatch(stored, MismatchField.SEEDS)


@pytest.mark.unit
def test_mismatch_seed_extra_missing_seedless() -> None:
    stored = make_stored(_PLAN)
    stored.add_seed("baseline_ar1", 0)

    _mismatch(stored, MismatchField.SEEDS)


@pytest.mark.unit
def test_mismatch_grid_levels() -> None:
    stored = make_stored(_PLAN)
    assert stored.set_cell(
        GOLD_METRICS_BY_RUN.name, _is(metric="pinball", level_low=0.02), "level_low", 0.03
    )

    _mismatch(stored, MismatchField.QUANTILE_LEVELS)


@pytest.mark.unit
def test_mismatch_mcs_statistic() -> None:
    stored = make_stored(_PLAN)
    assert stored.set_cell(GOLD_MCS_RESULTS.name, _is(horizon=7, model=_CAND), "statistic", "SQ")

    _mismatch(stored, MismatchField.MCS_STATISTIC)


@pytest.mark.unit
def test_mismatch_block_rule() -> None:
    stored = make_stored(_PLAN)
    assert stored.set_cell(GOLD_MCS_RESULTS.name, _is(horizon=1, model=_CAND), "block_size", 3)

    _mismatch(stored, MismatchField.MCS_BLOCK_RULE)


_GATE_ROW = {
    "model": _CAND,
    "horizon": 1,
    "sample": "model_full",
    "kind": "lower_tail",
    "includes_degenerate": False,
    "dgt_offset": None,
}


@pytest.mark.unit
def test_corrupt_seed_missing_tail() -> None:
    stored = make_stored(_PLAN)
    assert stored.drop_rows(GOLD_CALIBRATION_TABLE.name, _is(**_GATE_ROW, seed=2))

    _corrupt(stored, "gold_calibration_table misses the expected row")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "where"),
    [
        pytest.param(
            GOLD_METRICS_BY_RUN.name,
            _is(model="gbm_quantile", horizon=7, sample="common", metric="pinball_grid_mean"),
            id="pinball-grid-mean",
        ),
        pytest.param(
            GOLD_CALIBRATION_TABLE.name,
            _is(model="baseline_ewma_vol", horizon=7, sample="model_full"),
            id="comparator-calibration",
        ),
        pytest.param(
            GOLD_CALIBRATION_TABLE.name,
            _is(model=_CAND, seed=4, horizon=7, dgt_offset=3),
            id="dgt-subseries",
        ),
    ],
)
def test_corrupt_horizon_row_missing(table: str, where: Callable[[Row], bool]) -> None:
    stored = make_stored(_PLAN)
    assert stored.drop_rows(table, where)

    _corrupt(stored, f"{table} misses the expected row")


@pytest.mark.unit
def test_corrupt_estimator_row_missing() -> None:
    stored = make_stored(_PLAN)
    assert stored.drop_rows(
        GOLD_DM_RESULTS.name,
        _is(horizon=1, variance_estimator="bartlett", comparator="baseline_ar1"),
    )

    _corrupt(stored, "gold_dm_results misses the expected row")


@pytest.mark.unit
def test_corrupt_scheme_row_missing() -> None:
    stored = make_stored(_PLAN)
    assert stored.drop_rows(
        GOLD_MCS_RESULTS.name, _is(horizon=7, scheme="moving_block", model="gbm_quantile")
    )

    _corrupt(stored, "gold_mcs_results misses the expected row")


@pytest.mark.unit
def test_corrupt_common_points_divergent() -> None:
    stored = make_stored(_PLAN)
    assert stored.set_cell(
        GOLD_DM_RESULTS.name, _is(horizon=7, comparator="gbm_quantile"), "n_points", 249
    )

    _corrupt(stored, "disagree on n_points")


@pytest.mark.unit
def test_corrupt_block_estimate_missing() -> None:
    stored = make_stored(_PLAN)
    assert stored.set_cell(
        GOLD_MCS_RESULTS.name, _is(horizon=7, model=_CAND), "max_block_estimate", None
    )

    _corrupt(stored, "has no max_block_estimate")


@pytest.mark.unit
def test_corrupt_completed_with_failed_check() -> None:
    stored = make_stored(_PLAN, checks=[("degeneracy_check", "error", "fail")])

    _corrupt(stored, "holds the blocking check")


@pytest.mark.unit
def test_mismatch_before_corrupt() -> None:
    stored = make_stored(_PLAN)
    stored.add_seed(_CAND, 11)
    assert stored.drop_rows(GOLD_CALIBRATION_TABLE.name, _is(**_GATE_ROW, seed=2))
    assert stored.set_cell(
        GOLD_MCS_RESULTS.name, _is(horizon=7, model=_CAND), "max_block_estimate", None
    )

    _mismatch(stored, MismatchField.SEEDS)


@pytest.mark.unit
def test_evidence_built_per_horizon() -> None:
    evidence = _map(make_stored(_PLAN))

    assert isinstance(evidence, tuple)
    assert [item.horizon for item in evidence] == [1, 7]
    first, seventh = evidence
    assert first.common_points == 250  # noqa: PLR2004
    assert first.gate.lower.seed_ids == tuple(range(1, 11))
    assert first.gate.lower.mean_violations == 25.0  # noqa: PLR2004
    assert first.gate.lower.mean_observed == 250.0  # noqa: PLR2004
    assert (first.gate.lower.level, first.gate.upper.level) == (0.1, 0.9)
    assert first.gate.dgt == ()
    assert len(seventh.gate.dgt) == 7  # noqa: PLR2004
    assert seventh.gate.dgt[3].lower.mean_observed == 250 // 7
    assert seventh.common.sample == "common"
    assert [c.model for c in first.comparators_calibration] == list(_PLAN.comparators)
    assert first.comparators_calibration[0].lower.seed_ids == (None,)
    assert len(first.dm) == 12  # noqa: PLR2004
    assert len(first.mcs) == 14  # noqa: PLR2004
    assert first.mean_pinball[_CAND] == pytest.approx(0.10)
    assert first.mean_pinball["baseline_ar1"] == pytest.approx(0.12)


@pytest.mark.unit
def test_mapper_reads_schema_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    narrowed = dataclasses.replace(
        GOLD_DM_RESULTS,
        read_columns=tuple(c for c in GOLD_DM_RESULTS.read_columns if c != "n_points"),
    )
    monkeypatch.setattr(mapper_module, "GOLD_DM_RESULTS", narrowed)

    with pytest.raises(KeyError, match="n_points"):
        _map(make_stored(_PLAN))


@pytest.mark.unit
def test_mapper_gate_rows_band_level() -> None:
    stored = make_stored(_PLAN)
    assert stored.set_cell(
        GOLD_CALIBRATION_TABLE.name, _is(**_GATE_ROW, band_level=0.95), "n_violations", 40
    )

    first = _map(stored)[0]  # type: ignore[index]

    assert first.gate.lower.mean_violations == 25.0  # noqa: PLR2004


@pytest.mark.unit
@pytest.mark.parametrize("estimate", [-0.5, -1e-9], ids=["negative", "tiny-negative"])
def test_corrupt_block_estimate_missing_or_invalid(estimate: float) -> None:
    """Checkpoint C bloco 3, L2: estimativa inválida é corrupção (C6), nunca ValueError cru."""
    stored = make_stored(_PLAN)
    assert stored.set_cell(
        GOLD_MCS_RESULTS.name, _is(horizon=7, model=_CAND), "max_block_estimate", estimate
    )

    _corrupt(stored, "has an invalid max_block_estimate")


@pytest.mark.unit
def test_corrupt_seed_missing_tail_invalid_cell() -> None:
    """Checkpoint C bloco 3, R3: célula que o VO de evidência recusa vira corrupção."""
    stored = make_stored(_PLAN)
    assert stored.set_cell(
        GOLD_CALIBRATION_TABLE.name, _is(**_GATE_ROW, seed=2), "n_violations", 999
    )

    _corrupt(stored, "do not form evidence")


@pytest.mark.unit
def test_corrupt_block_estimate_missing_zero_is_valid() -> None:
    """Checkpoint C bloco 4, F2/N5: estimativa 0.0 é válida (bloco = h), sem corrupção."""
    stored = make_stored(_PLAN)
    assert stored.set_cell(
        GOLD_MCS_RESULTS.name, _is(horizon=7, model=_CAND), "max_block_estimate", 0.0
    )

    evidence = _map(stored)

    assert len(evidence) == 2  # type: ignore[arg-type]  # noqa: PLR2004


@pytest.mark.unit
@pytest.mark.parametrize("estimate", [float("nan"), float("inf")], ids=["nan", "inf"])
def test_corrupt_block_estimate_missing_non_finite(estimate: float) -> None:
    """Não-finita: recusada pelo dono da regra → corrupção (o `GoldTable` já a barra antes)."""
    row = {
        **make_stored(_PLAN).rows[GOLD_MCS_RESULTS.name][0],
        "max_block_estimate": estimate,
    }
    tables = SimpleNamespace(mcs=(row,), checks=())

    with pytest.raises(GoldGenerationCorruptError, match="has an invalid max_block_estimate"):
        mapper_module.check_completed(tables)  # type: ignore[arg-type]
    mapper_module.check_mcs_rules(_PLAN, tables)  # type: ignore[arg-type]  # pulada, sem erro


# --- extras da auditoria de testes (rodada 1) -----------------------------------------


@pytest.mark.unit
def test_mismatch_block_above_rule() -> None:
    """Auditoria E4: block_size acima da regra também é mismatch (não só abaixo)."""
    stored = make_stored(_PLAN)
    assert stored.set_cell(GOLD_MCS_RESULTS.name, _is(horizon=7, model=_CAND), "block_size", 8)

    _mismatch(stored, MismatchField.MCS_BLOCK_RULE)


@pytest.mark.unit
@pytest.mark.parametrize("case", ["stat", "block"])
def test_mcs_mismatch_before_missing_estimate(case: str) -> None:
    """Auditoria E5/E16: estimativa ausente numa linha anterior não mascara o mismatch."""
    stored = make_stored(_PLAN)
    first = _is(horizon=1, scheme="moving_block", model="baseline_ar1")
    later = _is(horizon=7, scheme="stationary", model=_CAND)
    assert stored.set_cell(GOLD_MCS_RESULTS.name, first, "max_block_estimate", None)
    if case == "stat":
        assert stored.set_cell(GOLD_MCS_RESULTS.name, later, "statistic", "SQ")
        expected = MismatchField.MCS_STATISTIC
    else:
        assert stored.set_cell(GOLD_MCS_RESULTS.name, later, "block_size", 99)
        expected = MismatchField.MCS_BLOCK_RULE
    rows = list(stored.generation().table(GOLD_MCS_RESULTS).rows)
    order = [i for i, row in enumerate(rows) if first(dict(row)) or later(dict(row))]
    assert first(dict(rows[order[0]])) and later(dict(rows[order[1]]))  # a ausente vem antes

    _mismatch(stored, expected)


@pytest.mark.unit
def test_evidence_pinball_seed_mean() -> None:
    """Auditoria E10: o P̄_G do candidato é a média entre seeds, não uma seed."""

    def pinball(model: str, seed: int | None, _h: int) -> float:
        if model == _CAND:
            return 0.10 if (seed or 0) % 2 else 0.40
        return 0.20

    evidence = _map(make_stored(_PLAN, pinball=pinball))

    assert evidence[0].mean_pinball[_CAND] == pytest.approx(0.25)  # type: ignore[index]
    verdict = ConfirmatoryScorecard.decide(_PLAN, evidence)  # type: ignore[arg-type]
    assert verdict.horizons[0].candidate_has_lowest_mean_pinball is False


@pytest.mark.unit
def test_mcs_horizon_of_wrong_type_does_not_mask_a_later_mismatch() -> None:
    """Checkpoint C bloco 1 (C1): horizonte de tipo errado numa linha do MCS é corrupção,
    conferida **depois** de todo mismatch — o mismatch de bloco numa linha posterior vence."""
    stored = make_stored(_PLAN)
    first = _is(horizon=1, scheme="moving_block", model="baseline_ar1")
    later = _is(horizon=7, scheme="stationary", model=_CAND)
    assert stored.set_cell(GOLD_MCS_RESULTS.name, later, "block_size", 99)
    assert stored.set_cell(GOLD_MCS_RESULTS.name, first, "horizon", 1.0)

    _mismatch(stored, MismatchField.MCS_BLOCK_RULE)


@pytest.mark.unit
def test_mcs_horizon_of_wrong_type_alone_is_named_corruption() -> None:
    """Checkpoint C bloco 1 r2 (N1): sem mismatch, o horizonte de tipo errado é corrupção
    nomeando a coluna `horizon` (não a estimativa, que é válida)."""
    stored = make_stored(_PLAN)
    first = _is(horizon=1, scheme="moving_block", model="baseline_ar1")
    assert stored.set_cell(GOLD_MCS_RESULTS.name, first, "horizon", 1.0)
    with pytest.raises(
        GoldGenerationCorruptError, match=r"gold_mcs_results\.horizon: expected int"
    ):
        _map(stored)


@pytest.mark.unit
@pytest.mark.parametrize("column", ["severity", "outcome"])
def test_quality_check_cell_of_wrong_type_is_named_corruption(column: str) -> None:
    """Checkpoint C bloco 2 (T4): `severity`/`outcome` de tipo errado num `COMPLETED` é
    corrupção nomeada (com `col` cru, `1 != "ERROR"` passaria calado)."""
    stored = make_stored(_PLAN)
    assert stored.set_cell(GOLD_QUALITY_CHECKS.name, lambda _row: True, column, 1)
    with pytest.raises(
        GoldGenerationCorruptError, match=rf"gold_quality_checks\.{column}: expected str"
    ):
        _map(stored)


@pytest.mark.unit
def test_outcome_of_wrong_type_on_a_non_error_row_is_corruption() -> None:
    """Checkpoint C bloco 2 (B1): o tipo do `outcome` é conferido em toda linha, não só nas
    de severidade ERROR (sem curto-circuito)."""
    stored = make_stored(_PLAN)
    assert stored.set_cell(GOLD_QUALITY_CHECKS.name, lambda _row: True, "severity", "warn")
    assert stored.set_cell(GOLD_QUALITY_CHECKS.name, lambda _row: True, "outcome", 123)
    with pytest.raises(GoldGenerationCorruptError, match=r"gold_quality_checks\.outcome"):
        _map(stored)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("monte_carlo_draws", 499),
        ("monte_carlo_seed", 7),
        ("mcs_block_sensitivities", ["h"]),
        (
            "profile_parameters",
            {
                "subset_multiplicity": "none_raw_p_descriptive_v1",
                "partial_degeneracy_pairs": "symmetric_and_adjacent_non_degenerate_rows_v1",
                "mcs_block_sensitivity_scheme": "primary_scheme",
                "stationarity": {
                    "acf_max_lag": "min_floor_10_log10_T_T_minus_1",
                    "break_test": "cusum_mean_dm_primary_variance_kolmogorov_v1",
                    "break_alpha": 0.05,
                },
            },
        ),
    ],
)
def test_mismatch_on_each_profile_parameter(key: str, value: object) -> None:
    """Stage 6.6 (CA9): `check_manifest` recusa divergência em cada campo novo."""
    stored = make_stored(_PLAN)
    stored.manifest["parameters"][key] = value  # type: ignore[index]
    _mismatch(stored, MismatchField.PARAMETERS)
