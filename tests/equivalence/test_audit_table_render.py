"""Tabela da auditoria, leitor do anterior e cálculo (Stage 8.2, Task 11; A9-A13 - sempre ativos).

Parquet, registro e lados sintéticos em memória/`tmp_path`; nenhum arquivo de
`data/analytics/` é lido. O mundo sintético do `compute_rows` (CC4-2 do Checkpoint C final)
tem duas janelas de teste sobrepostas com valores diferentes, duas seeds distintas no
anterior, um horizonte com A1 fora, um baseline comum e DM dos dois lados; os valores e os
status esperados são calculados aqui à mão, independentes do código sob teste.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
)
from financial_forecasting.features.evaluation.application.use_cases.silver_content_accumulator import (  # noqa: E501
    SilverContentAccumulator,
)
from financial_forecasting.features.evaluation.domain.services.wilson_band import (
    wilson_interval,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.silver_content_hash import (
    KIND_FLOAT,
    KIND_INT,
    KIND_STR,
)
from tests.equivalence import audit_table, readers
from tests.equivalence import comparison_set as cs
from tests.equivalence.audit_table import (
    APPLICABILITY,
    APPLICABILITY_TEXT,
    BEGIN_MARKER,
    END_MARKER,
    KIND_A1,
    KIND_A2_PICP,
    KIND_DELTA,
    KIND_DM,
    KIND_NOMINAL,
    KIND_SIGN,
    AuditRow,
    Declared,
    a9_rows,
    check_classification,
    classification,
    compute_rows,
    declared_diff,
    parse,
    recomputed_matches,
    render,
)
from tests.equivalence.comparisons import RawStatus
from tests.equivalence.prior_evidence import (
    PriorEvidenceHashError,
    build_registry,
    parse_registry,
    verify_registered_files,
)
from tests.equivalence.readers import (
    OfficialSide,
    OfficialSilverMismatchError,
    PriorSide,
    check_silver_units,
    read_prior,
    read_prior_table,
)

pytestmark = pytest.mark.unit

_ROWS = (
    AuditRow(
        "A9/h1/realized", 1, KIND_A1, "realizado y_t", "T∩=3 out=0", "x", RawStatus.WITHIN_TOLERANCE
    ),
    AuditRow(
        "A10/m/r1/h7/picp_raw",
        7,
        KIND_A2_PICP,
        "picp_raw",
        "m_A=0.8 | m_ant=0.81",
        "1e-09",
        RawStatus.OUT_OF_TOLERANCE,
    ),
    AuditRow(
        "A11/h1/candidate/pinball_q10", 1, KIND_DELTA, "pinball_q10", "delta=-0.01", "s", None
    ),
    AuditRow(
        "A11/h7/stopped", 7, KIND_SIGN, "modelo", "A1 out", "-", RawStatus.NOT_REALIZABLE, "A1"
    ),
)


# --- aplicabilidade e classificação (CC4-1) -----------------------------------------------


def test_applicability_is_the_section_5_6_table() -> None:
    """Transcrição literal da tabela "Aplicabilidade por comparação" do doc de domínio §5.6."""
    doc = Path(__file__).resolve().parents[2] / "docs" / "domain" / "evaluation"
    text = (doc / "reproduction-equivalence-and-reporting.md").read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    start = lines.index("| Comparação | Categorias que podem explicá-la |")
    assert lines[start + 1] == "|---|---|"
    table: set[tuple[str, tuple[str, ...]]] = set()
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        comparison, categories = (cell.strip() for cell in line.strip("|").split("|"))
        table.add((comparison, tuple(c.strip() for c in categories.split(";"))))
    # igualdade de CONJUNTO nos dois sentidos: linha nova no doc (ou no código) reprova
    assert table == set(APPLICABILITY_TEXT.values())
    assert APPLICABILITY[KIND_A1] == {"alvo"}
    assert "convencao_empate" in APPLICABILITY[KIND_A2_PICP]
    assert "escala" not in APPLICABILITY[KIND_A2_PICP]
    assert APPLICABILITY[KIND_DM] == {"agregacao_seeds", "defeito_referenciado"}


def test_classification_must_fit_status_and_applicability() -> None:
    check_classification(KIND_A2_PICP, RawStatus.OUT_OF_TOLERANCE, "explained:convencao_empate")
    check_classification(KIND_A2_PICP, RawStatus.OUT_OF_TOLERANCE, "not_explained")
    check_classification(KIND_SIGN, RawStatus.NOT_REALIZABLE, "not_compared:A1")
    check_classification(KIND_DELTA, None, "reported")
    for kind, status, label, message in (
        (KIND_A2_PICP, RawStatus.OUT_OF_TOLERANCE, "explained:escala", "cannot explain"),
        (KIND_A1, RawStatus.OUT_OF_TOLERANCE, "explained:amostra", "cannot explain"),
        (KIND_NOMINAL, RawStatus.DIVERGENT_SENSE, "within_tolerance", "does not fit"),
        (KIND_A1, RawStatus.WITHIN_TOLERANCE, "explained:alvo", "does not fit"),
        (KIND_SIGN, RawStatus.NOT_REALIZABLE, "not_compared:", "does not fit"),
        (KIND_A1, None, "reported", f"only a {KIND_DELTA}"),
        ("bogus", RawStatus.SAME_SENSE, "same_sense", "unknown comparison kind"),
    ):
        with pytest.raises(ValueError, match=message):
            check_classification(kind, status, label)


def test_render_then_parse_round_trip() -> None:
    declared = {"A10/m/r1/h7/picp_raw": "explained:convencao_empate"}

    text = render(_ROWS, declared)

    assert text.startswith(BEGIN_MARKER)
    assert text.rstrip().endswith(END_MARKER)
    assert parse(f"# relatório\n\n{text}\nfim\n") == classification(_ROWS, declared)
    assert [line for line in text.splitlines() if line.startswith("### ")] == [
        "### A9",
        "### A10",
        "### A11",
    ]
    assert "| reported | reported |" in text
    assert "| not_realizable | not_compared:A1 |" in text
    assert "| out_of_tolerance | explained:convencao_empate |" in text


def test_parse_refuses_missing_markers_or_malformed_row() -> None:
    text = render(_ROWS)
    with pytest.raises(ValueError, match="markers"):
        parse(text.replace(BEGIN_MARKER, ""))
    with pytest.raises(ValueError, match="markers"):
        parse(text.replace(END_MARKER, ""))
    with pytest.raises(ValueError, match="malformed table row"):
        parse(text.replace("| A9/h1/realized | 1 |", "| A9/h1/realized |"))
    with pytest.raises(ValueError, match="unknown status"):
        parse(text.replace("| within_tolerance | within_tolerance |", "| fine | fine |"))
    with pytest.raises(ValueError, match="cannot explain"):
        parse(
            text.replace(
                "| out_of_tolerance | not_explained |", "| out_of_tolerance | explained:escala |"
            )
        )


def test_declared_vs_parsed_mismatch_shows_the_diff() -> None:
    declared = classification(_ROWS)
    parsed = parse(render(_ROWS, {"A10/m/r1/h7/picp_raw": "explained:amostra"}))

    diff = declared_diff(declared, parsed)

    assert "-A10/m/r1/h7/picp_raw a2_picp out_of_tolerance not_explained" in diff
    assert "+A10/m/r1/h7/picp_raw a2_picp out_of_tolerance explained:amostra" in diff
    assert declared_diff(declared, declared) == ""
    assert recomputed_matches(list(_ROWS), parsed)  # a explicação é humana; o status não
    assert Declared("x", KIND_DELTA, None, "reported") != Declared("x", KIND_SIGN, None, "reported")


# --- leitor do anterior ------------------------------------------------------------------

_FLOATY = ("pinball", "picp", "mpiw", "y_true", "quantile_p", "mean_loss", "pvalue")


def _synthetic_value(column: str, keep: bool) -> object:
    special: dict[str, object] = {
        "parent_sweep_id": cs.PARENT_SWEEP_ID if keep else "other_sweep",
        "split": cs.SPLIT if keep else "val",
        "horizon": 1 if keep else 3,
        "hln_applied": True,
    }
    if column in special:
        return special[column]
    if column.startswith(("n_", "hac_", "seed", "quantile_guardrail")):
        return 1
    return 0.5 if column.startswith(_FLOATY) else "x"


def _oracle(tmp_path: Path) -> Path:
    root = tmp_path / "analytics"
    for path in cs.PRIOR_FILES:
        columns = [*cs.FILTER_COLUMNS[path], *cs.VALUE_COLUMNS[path], _LABEL, "secret"]
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {c: [_synthetic_value(c, True), _synthetic_value(c, False)] for c in columns}
        pq.write_table(pa.table(data), target)  # type: ignore[no-untyped-call]
    (root / "gold" / "gold_mcs_results.parquet").write_bytes(b"unregistered, never read")
    return root


@pytest.mark.parametrize("label", [None, "model_version_x"], ids=["before_e1", "after_e1"])
def test_prior_reader_reads_only_registered_columns_and_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str | None
) -> None:
    monkeypatch.setattr(cs, "MODEL_LABEL_COLUMN", label)
    root = _oracle(tmp_path)
    registry = parse_registry(build_registry(oracle_root=root, paths=cs.PRIOR_FILES))

    prior = read_prior(oracle_root=root, registry=registry)

    assert set(prior.tables) == set(cs.PRIOR_FILES)
    for path, rows in prior.tables.items():
        assert len(rows) == 1, path  # a linha de outro sweep/split/horizonte saiu
        expected = [*cs.FILTER_COLUMNS[path], *cs.VALUE_COLUMNS[path]]
        if path == cs.GOLD_OOS and label is not None:
            expected.append(label)  # o rótulo de modelo só no gold_oos, só depois da E1
        assert list(rows[0]) == list(dict.fromkeys(expected))
        assert "secret" not in rows[0]
    assert prior.column_types[cs.GOLD_OOS]["y_true"] == "double"
    assert cs.GOLD_OOS in prior.source_ids
    verified = verify_registered_files(oracle_root=root, registry=registry)
    with pytest.raises(PriorEvidenceHashError, match="not in the registry"):
        read_prior_table(verified, "gold/gold_mcs_results.parquet")
    (root / cs.DM_FAMILY_6).write_bytes(b"tampered")
    with pytest.raises(PriorEvidenceHashError, match="sha256"):
        read_prior(oracle_root=root, registry=registry)


# --- mundo sintético do compute_rows (CC4-2) --------------------------------------------------

_TS = tuple(f"2024-01-0{day}T00:00:00+00:00" for day in (2, 3, 4, 5))
_Y = (0.01, -0.02, 0.005, 0.03)
_LABEL = "model_version_x"
_CANDIDATE_LABELS = (
    "BTSF_w1_s1",
    "BTSF_w1_s2",
    "BTSF_w2_s1",
    "BTSF_w2_s2",
    "BTSF_w7_s1",
    "BTSF_w7_s2",
)
_BASE = cs.CommonBaseline("zero_v1", "baseline_zero_return", "prior-repo@c0ffee:baselines.py")
_WINDOWS = {"w1": _TS[:3], "w2": _TS[1:]}  # sobrepostas em t1, t2; w2 é a mais recente
_STALE_Y = 1.0  # y da janela antiga em t1: só entra se o D7 errar a janela


def _prior_quantiles(window: str, seed: int) -> dict[float, float]:
    """Pós-guardrail do candidato anterior: cobre todo y (|y| ≤ 0.03)."""
    shift = 0.001 * seed + (0.004 if window == "w1" else 0.0)
    return {0.1: -0.05 + shift, 0.5: shift, 0.9: 0.05 + shift}


def _oos_row(  # noqa: PLR0913 — os eixos de uma linha sintética
    label: str, window: str, seed: int, horizon: int, index: int, q: dict[float, float]
) -> dict[str, object]:
    y = _Y[index] + (0.5 if horizon == 7 else 0.0)  # noqa: PLR2004 — h=7 com A1 fora
    if window == "w1" and index == 1:
        y = _STALE_Y
    return {
        "run_id": f"{label}-h{horizon}",
        "parent_sweep_id": cs.PARENT_SWEEP_ID,
        "split": cs.SPLIT,
        "config_signature": f"{label}-{window}-cfg",
        "seed": seed,
        "fold": "none",
        "horizon": horizon,
        cs.TIMESTAMP_COLUMN: _TS[index],
        "y_true": y,
        _LABEL: label,
        **{cols["post_guardrail"]: q[level] for level, cols in cs.PRIOR_QUANTILE_COLUMNS.items()},
        **{cols["raw"]: q[level] + 0.01 for level, cols in cs.PRIOR_QUANTILE_COLUMNS.items()},
        "quantile_guardrail_applied": 0,
    }


def _prior_oos() -> list[dict[str, object]]:
    rows = []
    for window, stamps in _WINDOWS.items():
        for seed in (1, 2):
            for ts in stamps:
                index = _TS.index(ts)
                label = f"BTSF_{window}_s{seed}"
                rows.append(_oos_row(label, window, seed, 1, index, _prior_quantiles(window, seed)))
                zero = {0.1: -0.04, 0.5: 0.0, 0.9: 0.04}
                rows.append(_oos_row("zero_v1", window, seed, 1, index, zero))
    for seed in (1, 2):
        for index in range(4):
            rows.append(
                _oos_row(f"BTSF_w7_s{seed}", "w7", seed, 7, index, _prior_quantiles("w7", seed))
            )
    return rows


def _pin(y: float, q: float, tau: float) -> float:
    r = y - q
    return tau * r if r >= 0 else (tau - 1) * r


def _run_metric(rows: list[dict[str, object]]) -> dict[str, object]:
    """A linha de métrica do run `BTSF_w2_s1-h1`, com m_ant calculado à mão (n_samples = 3)."""
    sample = [r for r in rows if r["run_id"] == "BTSF_w2_s1-h1"]
    values: dict[str, object] = {}
    for variant in ("raw", "post_guardrail"):
        cols = {lv: c[variant] for lv, c in cs.PRIOR_QUANTILE_COLUMNS.items()}
        for level in cs.COMMON_LEVELS:
            losses = [_pin(r["y_true"], r[cols[level]], level) for r in sample]  # type: ignore[arg-type]
            values[f"pinball_q{round(level * 100)}_{variant}"] = math.fsum(losses) / len(sample)
        covered = sum(r[cols[0.1]] <= r["y_true"] <= r[cols[0.9]] for r in sample)  # type: ignore[operator]
        values[f"picp_{variant}"] = covered / len(sample)
        widths = [r[cols[0.9]] - r[cols[0.1]] for r in sample]  # type: ignore[operator]
        values[f"mpiw_{variant}"] = math.fsum(widths) / len(sample)
    return {"run_id": "BTSF_w2_s1-h1", "horizon": 1, "n_samples": 3, **values}


def _prior_side() -> PriorSide:
    oos = _prior_oos()
    metric = _run_metric(oos)
    doubles = {c: "double" for c in ("y_true", *cs.VALUE_COLUMNS[cs.GOLD_METRICS_BY_RUN])}
    return PriorSide(
        tables={
            cs.GOLD_OOS: oos,
            cs.GOLD_METRICS_BY_RUN: [
                metric,
                {**metric, "run_id": "BTSF_w7_s1-h7", "horizon": 7, "n_samples": 4},
            ],
            cs.GOLD_CALIBRATION: [{**metric, "n_samples": 99}],  # amostra não reconstruível
            cs.MARGINAL_COVERAGE: [],
            cs.DM_FAMILY_6: [
                {
                    "horizon": 1,
                    "baseline_model_version": "zero_v1",
                    "analysis_role": cs.PRIOR_DM_ANALYSIS_ROLE,
                    cs.PRIOR_DM_MEAN_DIFF: 0.2,
                    cs.PRIOR_DM_P_VALUE: 0.6,
                }
            ],
        },
        column_types={
            cs.GOLD_OOS: doubles,
            cs.GOLD_METRICS_BY_RUN: doubles,
            cs.GOLD_CALIBRATION: doubles,
        },
        source_ids=frozenset({_BASE.source}),
    )


_NEW_CANDIDATE = {1: {0.1: 0.10, 0.5: 0.15, 0.9: 0.20}, 2: {0.1: 0.11, 0.5: 0.16, 0.9: 0.22}}
"""Candidato novo: intervalo acima de todo y — nunca cobre (lado do nominal `above`)."""
_NEW_ZERO = {0.1: -0.04, 0.5: 0.0, 0.9: 0.04}


def _official_side() -> OfficialSide:
    predictions = [
        {
            "model": "tft_quantile",
            "seed": seed,
            "horizon": h,
            "target_timestamp": ts,
            "level": lv,
            "value": v,
        }
        for seed, quantiles in _NEW_CANDIDATE.items()
        for h in (1, 7)
        for ts in _TS
        for lv, v in quantiles.items()
    ] + [
        {
            "model": "baseline_zero_return",
            "seed": None,
            "horizon": 1,
            "target_timestamp": ts,
            "level": lv,
            "value": v,
        }
        for ts in _TS
        for lv, v in _NEW_ZERO.items()
    ]
    return OfficialSide(
        partition=GoldPartition("AAPL", "sweep-01"),
        preregistration_ref="plan-r3-0123456789ab",
        candidate="tft_quantile",
        realized=RealizedReturns(timestamps=_TS, returns=_Y),
        predictions=tuple(predictions),
        dm_rows=(
            {
                "horizon": 1,
                "variance_estimator": cs.NEW_DM_ESTIMATOR,
                "candidate": "tft_quantile",
                "comparator": "baseline_zero_return",
                "mean_differential": -0.1,
                "p_value": 0.01,
                "alpha": 0.05,
            },
        ),
    )


@pytest.fixture
def e1_fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cs, "MODEL_LABEL_COLUMN", _LABEL)
    monkeypatch.setattr(cs, "PRIOR_CANDIDATE_LABELS", _CANDIDATE_LABELS)
    monkeypatch.setattr(cs, "COMMON_BASELINES", (_BASE,))


def _mean_pinball(quantile_of: dict[object, dict[str, float]], level: float) -> float:
    """Média em T∩ da perda média entre seeds (B-SEEDS), à mão."""
    per_ts = [
        math.fsum(_pin(_Y[i], quantile_of[seed][_TS[i]], level) for seed in quantile_of)
        / len(quantile_of)
        for i in range(4)
    ]
    return math.fsum(per_ts) / 4


def _prior_latest(seed: int, level: float) -> dict[str, float]:
    """O ponto do D7: w1 em t0, w2 em t1-t3."""
    return {ts: _prior_quantiles("w1" if ts == _TS[0] else "w2", seed)[level] for ts in _TS}


@pytest.mark.usefixtures("e1_fixed")
def test_compute_rows_on_a_rich_synthetic_world() -> None:
    rows = compute_rows(_prior_side(), _official_side())

    status = {row.id: row.status for row in rows}
    values = {row.id: row.values for row in rows}
    stem, calibration = Path(cs.GOLD_METRICS_BY_RUN).stem, Path(cs.GOLD_CALIBRATION).stem
    a10 = {
        f"A10/{stem}/BTSF_w2_s1-h1/h1/{c}": RawStatus.WITHIN_TOLERANCE
        for c in cs.VALUE_COLUMNS[cs.GOLD_METRICS_BY_RUN]
    }
    a10 |= {  # A1 fora em h=7: as linhas A10 do horizonte param (runbook E4 passo 2)
        f"A10/{stem}/BTSF_w7_s1-h7/h7/{c}": RawStatus.NOT_REALIZABLE
        for c in cs.VALUE_COLUMNS[cs.GOLD_METRICS_BY_RUN]
    }
    a10 |= {
        f"A10/{calibration}/BTSF_w2_s1-h1/h1/{c}": RawStatus.NOT_REALIZABLE
        for c in cs.VALUE_COLUMNS[cs.GOLD_CALIBRATION]
    }
    a11 = {
        f"A11/h1/candidate/{q}": None
        for q in ("pinball_q10", "pinball_q50", "pinball_q90", "picp_80", "mpiw_80")
    }
    expected = {
        "A9/h1/realized": RawStatus.WITHIN_TOLERANCE,  # D7 escolhe w2 em t1 (w1 tem y velho)
        "A9/h7/realized": RawStatus.OUT_OF_TOLERANCE,
        **a10,
        **a11,
        "A11/h1/candidate/nominal_side_80": RawStatus.DIVERGENT_SENSE,
        "A11/h1/baseline_zero_return/pinball_q10_sign": RawStatus.SAME_SENSE,
        "A11/h1/baseline_zero_return/pinball_q50_sign": RawStatus.DIVERGENT_SENSE,
        "A11/h1/baseline_zero_return/pinball_q90_sign": RawStatus.SAME_SENSE,
        "A11/h1/baseline_zero_return/dm": RawStatus.DIVERGENT_SENSE,
        "A11/h7/stopped": RawStatus.NOT_REALIZABLE,  # A1 fora: a comparação de modelo para
    }
    assert status == expected
    assert (
        values["A9/h1/realized"]
        == "T∩=4 out=0 max_abs_diff=0.0 float32_exact=0/4 rule=double out_double=0 max_rel=0.0"
    )
    assert values["A9/h7/realized"].startswith("T∩=4 out=4 ")
    assert values["A11/h1/candidate/nominal_side_80"] == "novo=above anterior=inside"
    assert values["A11/h1/baseline_zero_return/dm"] == "novo=(-1, True) anterior=(1, False)"
    for level in cs.COMMON_LEVELS:
        new = _mean_pinball(
            {s: dict.fromkeys(_TS, _NEW_CANDIDATE[s][level]) for s in (1, 2)}, level
        )
        old = _mean_pinball({s: _prior_latest(s, level) for s in (1, 2)}, level)
        assert values[f"A11/h1/candidate/pinball_q{round(level * 100)}"] == (
            f"m_novo={new!r} m_A={old!r} delta={new - old!r}"
        )
        zero = _mean_pinball({None: dict.fromkeys(_TS, _NEW_ZERO[level])}, level)  # igual nos 2
        same = (new > zero) == (old > zero)
        name = f"A11/h1/baseline_zero_return/pinball_q{round(level * 100)}_sign"
        assert status[name] is (RawStatus.SAME_SENSE if same else RawStatus.DIVERGENT_SENSE)
    lower, upper = wilson_interval(count=4, n=4, band_level=0.95)
    assert lower <= cs.NOMINAL_80 <= upper  # o anterior cobre tudo e fica dentro
    reasons = {row.id: row.reason for row in rows if row.status is RawStatus.NOT_REALIZABLE}
    assert reasons[f"A10/{stem}/BTSF_w7_s1-h7/h7/picp_raw"] == "A1"
    assert reasons[f"A10/{calibration}/BTSF_w2_s1-h1/h1/picp_raw"] == "sample"
    assert reasons["A11/h7/stopped"] == "A1"
    assert parse(render(rows)) == classification(rows)


def test_check_silver_units_compares_dim_run_and_fact_units() -> None:
    """CC4-6: as unidades do cohort lidas do silver vivo = as do `silver_content` julgado."""
    partition = GoldPartition("AAPL", "sweep-01")
    units = {
        "dim_run|sweep-01": "a" * 64,
        "dim_run|ablation": "b" * 64,  # outra unidade do refresh: não é conferida aqui
        "fact_oos_predictions|run-a|2024": "c" * 64,
        "fact_oos_predictions|abl-1|2023": "7" * 64,  # run da ablação: não lido, não conferido
        "fact_oos_predictions|abl-1|2024": "8" * 64,
        "realized|AAPL": "d" * 64,
    }
    cohort = frozenset({"run-a"})
    judged = SilverContent(digest="e" * 64, tables={"dim_run": "f" * 64}, units=units)
    read = SilverContent(
        digest="0" * 64,
        tables={"dim_run": "1" * 64},
        units={
            k: v
            for k, v in units.items()
            if k in {"dim_run|sweep-01", "fact_oos_predictions|run-a|2024"}
        },
    )

    check_silver_units(read, judged, partition, cohort)
    for changed in (
        {**read.units, "fact_oos_predictions|run-a|2024": "9" * 64},
        {**read.units, "fact_oos_predictions|run-b|2024": "9" * 64},
        {**read.units, "fact_oos_predictions|abl-1|2024": "8" * 64},  # leu a ablação: a mais
        {**read.units, "dim_run|sweep-01": "9" * 64},  # dim_run do cohort com outro digest
        {"dim_run|sweep-01": "a" * 64},
    ):
        other = SilverContent(digest="0" * 64, tables={"dim_run": "1" * 64}, units=changed)
        with pytest.raises(OfficialSilverMismatchError, match="differs from the judged copy"):
            check_silver_units(other, judged, partition, cohort)


def test_main_reads_the_roots_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """O runbook da E4 chama `python -m tests.equivalence.audit_table` sem argumentos."""
    seen: list[tuple[Path, Path]] = []

    def fake_compute(oracle: Path, official: Path) -> tuple[()]:
        seen.append((oracle, official))
        return ()

    monkeypatch.setattr(audit_table, "compute", fake_compute)
    monkeypatch.setenv("EQUIVALENCE_ORACLE_ROOT", "/oracle")
    monkeypatch.setenv("EQUIVALENCE_OFFICIAL_ROOT", "/official")

    assert audit_table.main([]) == 0
    assert seen == [(Path("/oracle"), Path("/official"))]
    assert capsys.readouterr().out.startswith(BEGIN_MARKER)
    monkeypatch.delenv("EQUIVALENCE_OFFICIAL_ROOT")
    assert audit_table.main([]) == 2  # noqa: PLR2004


@pytest.mark.usefixtures("e1_fixed")
def test_compute_rows_refuses_a_seed_that_misses_the_intersection() -> None:
    official = _official_side()
    kept = tuple(
        r
        for r in official.predictions
        if not (r["seed"] == 2 and r["target_timestamp"] == _TS[3] and r["horizon"] == 1)  # noqa: PLR2004
    )
    broken = OfficialSide(**{**official.__dict__, "predictions": kept})

    with pytest.raises(ValueError, match=r"seeds \['2'\] do not cover"):
        compute_rows(_prior_side(), broken)


@pytest.mark.usefixtures("e1_fixed")
def test_compute_rows_refuses_repeated_new_predictions() -> None:
    official = _official_side()
    broken = OfficialSide(
        **{**official.__dict__, "predictions": (*official.predictions, official.predictions[0])}
    )

    with pytest.raises(ValueError, match="repeated prediction"):
        compute_rows(_prior_side(), broken)


_F32_TS = tuple(f"2024-02-0{day}T00:00:00+00:00" for day in (1, 2, 5, 6, 7))
_F32_Y = (0.5, -0.25, 0.125, 0.75)  # float32-exatos; o 5º ponto (fora de T∩) é 0.1


def _a9_world(*, extra_y: float | None) -> tuple[PriorSide, OfficialSide]:
    """y_ant em T∩ float32-exatos; y_novo = y_ant + 2⁻³⁰ (dentro do meio ulp de float32, fora
    do de double); `extra_y` é um y_ant do mesmo horizonte num timestamp fora de T∩."""
    prior_y = [*_F32_Y, *([] if extra_y is None else [extra_y])]
    oos = [
        {
            _LABEL: "BTSF_w2_s1",
            "seed": 1,
            "horizon": 1,
            "config_signature": "cfg",
            cs.TIMESTAMP_COLUMN: _F32_TS[i],
            "y_true": y,
            "run_id": "BTSF_w2_s1-h1",
            **{
                c[variant]: lv - 0.5 for lv, c in cs.PRIOR_QUANTILE_COLUMNS.items() for variant in c
            },
        }
        for i, y in enumerate(prior_y)
    ]
    prior = PriorSide(
        tables={
            cs.GOLD_OOS: oos,
            cs.GOLD_METRICS_BY_RUN: [],
            cs.GOLD_CALIBRATION: [],
            cs.MARGINAL_COVERAGE: [],
            cs.DM_FAMILY_6: [],
        },
        column_types={cs.GOLD_OOS: {"y_true": "double"}},
        source_ids=frozenset(),
    )
    official = OfficialSide(
        partition=GoldPartition("AAPL", "sweep-01"),
        preregistration_ref="plan-r3-0123456789ab",
        candidate="tft_quantile",
        realized=RealizedReturns(
            timestamps=_F32_TS[:4], returns=tuple(y + 2.0**-30 for y in _F32_Y)
        ),
        predictions=tuple(
            {
                "model": "tft_quantile",
                "seed": 1,
                "horizon": 1,
                "target_timestamp": ts,
                "level": lv,
                "value": lv - 0.4,
            }
            for ts in _F32_TS[:4]
            for lv in cs.COMMON_LEVELS
        ),
        dm_rows=(),
    )
    return prior, official


@pytest.mark.usefixtures("e1_fixed")
def test_post_a1_label_marks_model_rows_of_float32_horizons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B3: toda linha A10/A11 de um horizonte julgado pela regra float32 leva o rótulo."""
    monkeypatch.setattr(cs, "COMMON_BASELINES", ())
    rows = compute_rows(*_a9_world(extra_y=None))
    model_h1 = [r for r in rows if r.horizon == 1 and not r.id.startswith("A9/")]
    assert {r.id for r in model_h1} >= {"A11/h1/candidate/picp_80", "A11/h1/candidate/mpiw_80"}
    assert all(r.tolerance.endswith(f"[{cs.A1_FLOAT32_DEVIATION}]") for r in model_h1)
    others = [r for r in rows if r.horizon != 1]  # h=7 sem y_ant (regra double) e a linha geral
    assert others
    assert all(cs.A1_FLOAT32_DEVIATION not in r.tolerance for r in others)

    rows = compute_rows(*_a9_world(extra_y=0.1))  # regra double, A1 fora: sem rótulo
    assert all(cs.A1_FLOAT32_DEVIATION not in r.tolerance for r in rows)
    stopped = next(r for r in rows if r.id == "A11/h1/stopped")
    assert stopped.reason == "A1"


@pytest.mark.usefixtures("e1_fixed")
def test_a1_float32_precondition_covers_the_whole_horizon_not_only_the_intersection() -> None:
    """B3 (ADR 8.2.0004): um y_ant fora de T∩ não float32-exato derruba a regra float32."""
    rows, common = a9_rows(*_a9_world(extra_y=None))
    h1 = rows[0]
    assert len(common[1]) == 4  # noqa: PLR2004
    assert h1.status is RawStatus.WITHIN_TOLERANCE
    assert "float32_exact=4/4 rule=float32" in h1.values
    assert cs.A1_FLOAT32_DEVIATION in h1.tolerance

    rows, common = a9_rows(*_a9_world(extra_y=0.1))
    h1 = rows[0]
    assert len(common[1]) == 4  # noqa: PLR2004 — o 5º ponto não entra em T∩
    assert h1.status is RawStatus.OUT_OF_TOLERANCE
    assert "float32_exact=4/5 rule=double" in h1.values
    assert cs.A1_FLOAT32_DEVIATION not in h1.tolerance


@pytest.mark.usefixtures("e1_fixed")
def test_horizon_without_new_predictions_is_an_empty_intersection() -> None:
    """Re-auditoria (n): sem predição nova num horizonte, T∩ vazio é registrado, não comparado."""
    official = _official_side()
    only_h1 = tuple(r for r in official.predictions if r["horizon"] == 1)
    rows = compute_rows(
        _prior_side(), OfficialSide(**{**official.__dict__, "predictions": only_h1})
    )

    by_id = {row.id: row for row in rows}
    assert by_id["A9/h7/realized"].status is RawStatus.EMPTY_INTERSECTION
    assert (
        by_id["A9/h7/realized"].values
        == "T∩=0 out=0 max_abs_diff=None float32_exact=0/4 rule=double out_double=0 max_rel=None"
    )
    stopped = by_id["A11/h7/stopped"]
    assert (stopped.status, stopped.reason) == (RawStatus.EMPTY_INTERSECTION, "empty_intersection")
    stem = Path(cs.GOLD_METRICS_BY_RUN).stem
    # sem A1 fora, o A10 de h=7 é calculado (a amostra do run anterior existe por si)
    assert by_id[f"A10/{stem}/BTSF_w7_s1-h7/h7/picp_raw"].reason == "sample"
    assert [d.classification for d in classification(rows) if d.id == "A11/h7/stopped"] == [
        "not_compared:empty_intersection"
    ]


@pytest.mark.usefixtures("e1_fixed")
def test_empty_common_baselines_are_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """A11: zero baselines comuns → a tabela vazia é registrada numa linha, não omitida."""
    monkeypatch.setattr(cs, "COMMON_BASELINES", ())

    rows = compute_rows(_prior_side(), _official_side())

    empty = [row for row in rows if row.id == "A11/baselines/none"]
    assert len(empty) == 1
    assert (empty[0].status, empty[0].reason) == (RawStatus.NOT_REALIZABLE, "no_common_baseline")
    assert not any("/baseline_zero_return/" in row.id for row in rows)
    assert "not_compared:no_common_baseline" in render(rows)


@pytest.mark.usefixtures("e1_fixed")
def test_declared_not_compared_reason_must_match_the_recomputed_one() -> None:
    rows = compute_rows(_prior_side(), _official_side())
    declared = classification(rows)
    assert recomputed_matches(rows, declared)

    wrong = tuple(
        Declared(d.id, d.kind, d.status, "not_compared:sample") if d.id == "A11/h7/stopped" else d
        for d in declared
    )

    assert not recomputed_matches(rows, wrong)


class _FakeSilver:
    """Leitor silver sintético (duck typing do `ParquetAnalyticsRepository`)."""

    def __init__(self, tables: dict[str, list[dict[str, object]]]) -> None:
        self._tables = tables

    def read(self, *, layer: str, table: str, filters: object = None) -> list[dict[str, object]]:
        return [dict(row) for row in self._tables[table]]

    def columns(self, *, layer: str, table: str) -> dict[str, tuple[str, bool]]:
        sample = self._tables[table][0]
        kinds = {int: KIND_INT, float: KIND_FLOAT, str: KIND_STR}
        return {name: (kinds[type(value)], False) for name, value in sample.items()}


def _silver() -> _FakeSilver:
    dim_run = [
        {
            "asset": "AAPL",
            "parent_sweep_id": "sweep-01",
            "run_id": run,
            "model_version": model,
            "seed": seed,
            "feature_set_name": "fs",
        }
        for run, model, seed in (("r1", "tft_quantile", 1), ("r2", "baseline_ar1", 0))
    ]
    facts = [
        {
            "asset": "AAPL",
            "feature_set_name": "fs",
            "run_id": run,
            "year": 2024,
            "split": "test",
            "horizon": 1,
            "target_timestamp_utc": _TS[0],
            "quantile_level": level,
            "value_guardrail": 0.1,
        }
        for run in ("r1", "r2")
        for level in (0.1, 0.5, 0.9, 0.98)
    ]
    return _FakeSilver({"dim_run": dim_run, "fact_oos_predictions": facts})


def _consumed(silver: _FakeSilver) -> SilverContent:
    """O `silver_content` que a cópia julgada gravou para este silver (mesmo pós-filtro)."""
    accumulator = SilverContentAccumulator(hasher=CanonicalJsonHasher())
    accumulator.add_dim_run(
        columns=silver.columns(layer="silver", table="dim_run"),
        parent_sweep_id="sweep-01",
        rows=silver.read(layer="silver", table="dim_run"),
    )
    accumulator.add_facts(
        table="fact_oos_predictions",
        columns=silver.columns(layer="silver", table="fact_oos_predictions"),
        rows=silver.read(layer="silver", table="fact_oos_predictions"),
    )
    return accumulator.result()


def test_official_predictions_are_checked_against_the_judged_silver() -> None:
    """Re-auditoria (m): o `_model_predictions` confere o silver lido contra a cópia julgada."""
    silver, partition = _silver(), GoldPartition("AAPL", "sweep-01")
    consumed = _consumed(silver)

    points = readers._model_predictions(silver, partition, frozenset({"tft_quantile"}), consumed)  # type: ignore[arg-type]

    assert sorted(float(str(p["level"])) for p in points) == [
        0.1,
        0.5,
        0.9,
    ]  # só o candidato, níveis comuns
    # a cópia julgada também traz as unidades da ablação (o `RefreshGold` as consome): passa
    with_ablation = {
        **consumed.units,
        "dim_run|ablation-01": "6" * 64,
        "fact_oos_predictions|abl-1|2023": "7" * 64,
        "fact_oos_predictions|abl-1|2024": "8" * 64,
    }
    judged_ablation = SilverContent(
        digest=consumed.digest, tables=consumed.tables, units=with_ablation
    )
    assert (
        readers._model_predictions(  # type: ignore[arg-type]
            silver, partition, frozenset({"tft_quantile"}), judged_ablation
        )
        == points
    )
    tampered = dict(with_ablation)
    tampered["fact_oos_predictions|r2|2024"] = "9" * 64  # unidade do cohort adulterada
    judged = SilverContent(digest=consumed.digest, tables=consumed.tables, units=tampered)
    with pytest.raises(OfficialSilverMismatchError, match="fact_oos_predictions"):
        readers._model_predictions(silver, partition, frozenset({"tft_quantile"}), judged)  # type: ignore[arg-type]
    # um run do cohort some do dim_run vivo: as suas unidades saem do esperado junto, e só a
    # igualdade de `dim_run|<cohort>` o denuncia
    base = _silver()
    shrunk = _FakeSilver(
        {
            "dim_run": [
                r for r in base.read(layer="silver", table="dim_run") if r["run_id"] != "r2"
            ],
            "fact_oos_predictions": base.read(layer="silver", table="fact_oos_predictions"),
        }
    )
    with pytest.raises(OfficialSilverMismatchError, match="dim_run"):
        readers._model_predictions(shrunk, partition, frozenset({"tft_quantile"}), judged_ablation)  # type: ignore[arg-type]


def test_compute_rows_requires_the_e1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cs, "MODEL_LABEL_COLUMN", None)  # o estado antes da E1
    monkeypatch.setattr(cs, "PRIOR_CANDIDATE_LABELS", ())
    with pytest.raises(ValueError, match="run the E1"):
        compute_rows(_prior_side(), _official_side())
    monkeypatch.setattr(cs, "MODEL_LABEL_COLUMN", _LABEL)
    with pytest.raises(ValueError, match="run the E1"):  # rótulos do candidato ainda vazios
        compute_rows(_prior_side(), _official_side())
    monkeypatch.setattr(cs, "PRIOR_CANDIDATE_LABELS", _CANDIDATE_LABELS)
    monkeypatch.setattr(cs, "COMMON_BASELINES", (cs.CommonBaseline("a", "b", "unregistered"),))
    with pytest.raises(ValueError, match="unregistered definition sources"):
        compute_rows(_prior_side(), _official_side())


@pytest.mark.usefixtures("e1_fixed")
def test_storage_precision_comes_from_the_registered_y_type() -> None:
    prior = _prior_side()
    types = {
        **prior.column_types,
        cs.GOLD_OOS: {**prior.column_types[cs.GOLD_OOS], "y_true": "string"},
    }

    with pytest.raises(ValueError, match="no floating-point storage precision"):
        compute_rows(PriorSide(prior.tables, types, prior.source_ids), _official_side())


# --- porta única de leitura da evidência anterior (Checkpoint C 8.2 bloco 3, CC3-3) ----------

_SCAFFOLD = Path(__file__).resolve().parent
_READ_OWNER = "prior_evidence.py"
_FILE_READS = frozenset(
    {
        "open",
        "read_bytes",
        "read_text",
        "read_table",
        "read_schema",
        "read_metadata",
        "ParquetFile",
        "ParquetDataset",
        "dataset",
    }
)


def read_door_violations(source: str, *, name: str) -> list[str]:
    """Leitura de arquivo fora da porta única: fora do `prior_evidence.py`, toda leitura de
    arquivo é um `pq.read_table(registered_path(...), ...)`; nenhuma outra."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename=name)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if called not in _FILE_READS:
            continue
        through_door = (
            called == "read_table"
            and node.args
            and isinstance(node.args[0], ast.Call)
            and getattr(node.args[0].func, "id", "") == "registered_path"
        )
        if not through_door:
            found.append(f"{name}:{node.lineno} {called}")
    return found


def test_scaffold_reads_prior_files_only_through_the_registry_door() -> None:
    modules = [
        path
        for path in sorted(_SCAFFOLD.glob("*.py"))
        if not path.name.startswith("test_") and path.name not in {_READ_OWNER, "__init__.py"}
    ]
    assert {path.name for path in modules} >= {"readers.py", "audit_table.py"}

    found = [
        violation
        for path in modules
        for violation in read_door_violations(path.read_text(encoding="utf-8"), name=path.name)
    ]

    assert found == []


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("pq.read_table(path)\n", ["read_table"]),
        ("pq.read_table(registered_path(v, p), columns=c)\n", []),
        ("open('x')\n", ["open"]),
        ("Path(x).read_bytes()\n", ["read_bytes"]),
        ("pq.ParquetFile(p).read()\n", ["ParquetFile"]),
        ("ds.dataset(p).to_table()\n", ["dataset"]),
    ],
)
def test_read_door_detector_flags_direct_reads(source: str, flagged: list[str]) -> None:
    found = read_door_violations(source, name="m.py")
    assert [item.split(" ", 1)[1] for item in found] == flagged
