"""Tabela da auditoria e leitor do anterior (Stage 8.2, Task 11; A12, A13 — sempre ativos).

Parquet e registro sintéticos em `tmp_path`; nenhum arquivo de `data/analytics/` é lido.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from tests.equivalence import comparison_set as cs
from tests.equivalence.audit_table import (
    BEGIN_MARKER,
    END_MARKER,
    AuditRow,
    Declared,
    classification,
    compute_rows,
    declared_diff,
    parse,
    render,
)
from tests.equivalence.comparisons import RawStatus, pair_measures, pinball_at
from tests.equivalence.prior_evidence import (
    PriorEvidenceHashError,
    build_registry,
    parse_registry,
    verify_registered_files,
)
from tests.equivalence.readers import OfficialSide, PriorSide, read_prior, read_prior_table

pytestmark = pytest.mark.unit

_ROWS = (
    AuditRow(
        "A9/h1/realized",
        1,
        "realizado y_t",
        "T∩=3 out=0",
        "2^-53·|y_ant|",
        RawStatus.WITHIN_TOLERANCE,
    ),
    AuditRow(
        "A10/m/r1/h7/picp_raw",
        7,
        "picp_raw",
        "m_A=0.8 | m_ant=0.8",
        "1e-09",
        RawStatus.OUT_OF_TOLERANCE,
    ),
    AuditRow("A11/h1/candidate/pinball_q10", 1, "pinball_q10", "delta=-0.01", "sentido", None),
    AuditRow("A11/h7/stopped", 7, "modelo", "A1 out of tolerance", "-", RawStatus.NOT_REALIZABLE),
)


def test_render_then_parse_round_trip() -> None:
    text = render(_ROWS)

    assert text.startswith(BEGIN_MARKER)
    assert text.rstrip().endswith(END_MARKER)
    assert parse(f"# relatório\n\n{text}\nfim\n") == classification(_ROWS)
    assert [line for line in text.splitlines() if line.startswith("### ")] == [
        "### A9",
        "### A10",
        "### A11",
    ]
    assert "| reported |" in text


def test_parse_refuses_missing_markers_or_malformed_row() -> None:
    text = render(_ROWS)
    with pytest.raises(ValueError, match="markers"):
        parse(text.replace(BEGIN_MARKER, ""))
    with pytest.raises(ValueError, match="markers"):
        parse(text.replace(END_MARKER, ""))
    with pytest.raises(ValueError, match="malformed table row"):
        parse(text.replace("| A9/h1/realized | 1 |", "| A9/h1/realized |"))
    with pytest.raises(ValueError, match="unknown status"):
        parse(text.replace("| within_tolerance |", "| fine |"))


def test_declared_vs_parsed_mismatch_shows_the_diff() -> None:
    declared = classification(_ROWS)
    parsed = parse(render(_ROWS).replace("| out_of_tolerance |", "| within_tolerance |"))

    diff = declared_diff(declared, parsed)

    assert "-A10/m/r1/h7/picp_raw out_of_tolerance" in diff
    assert "+A10/m/r1/h7/picp_raw within_tolerance" in diff
    assert declared_diff(declared, declared) == ""
    assert Declared("x", None) != Declared("x", RawStatus.SAME_SENSE)


# --- leitor do anterior ------------------------------------------------------------------


def _synthetic_value(column: str, keep: bool) -> object:  # noqa: PLR0911 — um caso por coluna
    if column == "parent_sweep_id":
        return cs.PARENT_SWEEP_ID if keep else "other_sweep"
    if column == "split":
        return cs.SPLIT if keep else "val"
    if column == "horizon":
        return 1 if keep else 3
    if column in {
        "n_samples",
        "n_obs",
        "n_obs_effective",
        "hac_lag_used",
        "seed",
        "quantile_guardrail_applied",
    }:
        return 1
    if column == "hln_applied":
        return True
    if (
        column in cs.VALUE_COLUMNS.get(cs.GOLD_OOS, ())
        or "pinball" in column
        or column
        in {
            "picp_q10_q90",
            "mpiw",
            "mean_loss_diff_tft_minus_baseline",
            "pvalue_one_sided_less",
        }
        or column.startswith(("picp_", "mpiw_"))
    ):
        return 0.5
    return "x"


def _oracle(tmp_path: Path) -> Path:
    root = tmp_path / "analytics"
    for path in cs.PRIOR_FILES:
        columns = [*cs.FILTER_COLUMNS[path], *cs.VALUE_COLUMNS[path], "secret"]
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {c: [_synthetic_value(c, True), _synthetic_value(c, False)] for c in columns}
        pq.write_table(pa.table(data), target)  # type: ignore[no-untyped-call]
    (root / "gold" / "gold_mcs_results.parquet").write_bytes(b"unregistered, never read")
    return root


def test_prior_reader_reads_only_registered_columns_and_filters(tmp_path: Path) -> None:
    root = _oracle(tmp_path)
    registry = parse_registry(build_registry(oracle_root=root, paths=cs.PRIOR_FILES))

    prior = read_prior(oracle_root=root, registry=registry)

    assert set(prior.tables) == set(cs.PRIOR_FILES)
    for path, rows in prior.tables.items():
        assert len(rows) == 1, path  # a linha de outro sweep/split/horizonte saiu
        assert list(rows[0]) == list(
            dict.fromkeys([*cs.FILTER_COLUMNS[path], *cs.VALUE_COLUMNS[path]])
        )
        assert "secret" not in rows[0]
    verified = verify_registered_files(oracle_root=root, registry=registry)
    with pytest.raises(PriorEvidenceHashError, match="not in the registry"):
        read_prior_table(verified, "gold/gold_mcs_results.parquet")
    (root / cs.DM_FAMILY_6).write_bytes(b"tampered")
    with pytest.raises(PriorEvidenceHashError, match="sha256"):
        read_prior(oracle_root=root, registry=registry)


# --- cálculo sobre dois lados sintéticos ------------------------------------------------------

_TS = ("2024-01-02T00:00:00+00:00", "2024-01-03T00:00:00+00:00", "2024-01-04T00:00:00+00:00")
_Y = (0.01, -0.02, 0.005)
_Q = {0.1: -0.02, 0.5: 0.0, 0.9: 0.02}


def _prior_side(label_column: str) -> PriorSide:
    oos = [
        {
            "run_id": "r1",
            "parent_sweep_id": cs.PARENT_SWEEP_ID,
            "split": cs.SPLIT,
            "config_signature": "w1",
            "seed": 1,
            "fold": "none",
            "horizon": 1,
            cs.TIMESTAMP_COLUMN: ts,
            "y_true": y,
            label_column: "BTSF_s1",
            **{
                cols[v]: _Q[level]
                for level, cols in cs.PRIOR_QUANTILE_COLUMNS.items()
                for v in cols
            },
            "quantile_guardrail_applied": 0,
        }
        for ts, y in zip(_TS, _Y, strict=True)
    ]
    pinball = {level: pinball_at(list(_Y), [_Q[level]] * 3, level) for level in cs.COMMON_LEVELS}
    pair = pair_measures(list(_Y), [_Q[0.1]] * 3, [_Q[0.9]] * 3)
    metric = {
        "run_id": "r1",
        "parent_sweep_id": cs.PARENT_SWEEP_ID,
        "config_signature": "w1",
        "split": cs.SPLIT,
        "fold": "none",
        "seed": 1,
        "horizon": 1,
        "n_samples": 3,
        **{
            f"pinball_q{round(lv * 100)}_{v}": pinball[lv]
            for lv in cs.COMMON_LEVELS
            for v in ("raw", "post_guardrail")
        },
        **{f"picp_{v}": pair.picp for v in ("raw", "post_guardrail")},
        **{f"mpiw_{v}": pair.mpiw for v in ("raw", "post_guardrail")},
    }
    marginal = {
        "run_id": "r1",
        "split": cs.SPLIT,
        "horizon": 1,
        "n_obs": 4,
        "picp_q10_q90": pair.picp,
        "mpiw": pair.mpiw,
    }
    return PriorSide(
        {
            cs.GOLD_OOS: oos,
            cs.GOLD_METRICS_BY_RUN: [metric],
            cs.GOLD_CALIBRATION: [],
            cs.MARGINAL_COVERAGE: [marginal],
            cs.DM_FAMILY_6: [],
        }
    )


def _official_side() -> OfficialSide:
    predictions = [
        {
            "model": "tft_quantile",
            "seed": seed,
            "horizon": 1,
            "target_timestamp": ts,
            "level": level,
            "value": value + shift,
        }
        for seed, shift in ((1, 0.0), (2, 0.001))
        for ts in _TS
        for level, value in _Q.items()
    ]
    return OfficialSide(
        partition=GoldPartition("AAPL", "sweep-01"),
        preregistration_ref="plan-r3-0123456789ab",
        candidate="tft_quantile",
        realized=RealizedReturns(timestamps=_TS, returns=_Y),
        predictions=tuple(predictions),
        dm_rows=(),
    )


def test_compute_rows_on_synthetic_sides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cs, "MODEL_LABEL_COLUMN", "model_version_x")
    monkeypatch.setattr(cs, "PRIOR_CANDIDATE_LABELS", ("BTSF_s1",))

    rows = compute_rows(_prior_side("model_version_x"), _official_side())

    status = {row.id: row.status for row in rows}
    assert status["A9/h1/realized"] is RawStatus.WITHIN_TOLERANCE
    assert status["A9/h7/realized"] is RawStatus.EMPTY_INTERSECTION
    stem = Path(cs.GOLD_METRICS_BY_RUN).stem
    assert status[f"A10/{stem}/r1/h1/pinball_q10_post_guardrail"] is RawStatus.WITHIN_TOLERANCE
    assert status[f"A10/{stem}/r1/h1/picp_raw"] is RawStatus.WITHIN_TOLERANCE
    marginal = Path(cs.MARGINAL_COVERAGE).stem
    assert status[f"A10/{marginal}/r1/h1/picp_q10_q90"] is RawStatus.NOT_REALIZABLE  # n_obs 4 ≠ 3
    assert status["A11/h1/candidate/pinball_q50"] is None  # delta reportado
    assert status["A11/h1/candidate/nominal_side_80"] in {
        RawStatus.SAME_SENSE,
        RawStatus.DIVERGENT_SENSE,
    }
    assert status["A11/h7/stopped"] is RawStatus.EMPTY_INTERSECTION
    assert parse(render(rows)) == classification(rows)


def test_compute_rows_requires_the_e1_label_column() -> None:
    with pytest.raises(ValueError, match="run the E1"):
        compute_rows(_prior_side("model_version_x"), _official_side())


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
    import ast  # noqa: PLC0415 — só este detector usa

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
