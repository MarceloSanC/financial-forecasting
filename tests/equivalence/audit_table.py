"""Tabela da auditoria de equivalência: cálculo, renderização e parse (Stage 8.2, Task 11).

Concept 8.2 A9-A12; ADR 8.2.0003 item 5. `compute(oracle_root, official_root)` devolve uma
linha por comparação (id, horizonte, grandeza, valores, tolerância, `RawStatus`):

- **A9** (D13): por horizonte, A1 do realizado em T∩ (y_ant da janela mais recente — D7 —,
  y_novo do `ReadTrainingGrid` real); A1 fora num horizonte ⇒ a comparação de modelo daquele
  horizonte para (linha A11 `not_realizable`);
- **A10** (D12 c, e): por linha de métrica por run do anterior e por coluna de valor, m_A (o
  código novo sobre as predições do run, na variante do nome da coluna) contra m_ant;
- **A11** (D12 a, b, d): candidato x candidato em T∩ — deltas m_novo - m_A (status
  `reported`: EQ-DESC, sem limiar) e o lado do nominal do PICP 80 % (célula de sentido) —; por
  baseline comum, o sinal de (candidato - baseline) por nível dentro de cada lado e o DM
  reportado por cada lado (D8).

`render(rows)` escreve as tabelas markdown entre os marcadores; `parse(markdown)` lê de volta
a classificação declarada. `python -m tests.equivalence.audit_table <oracle> <oficial>`
**imprime** a tabela (nunca grava arquivo).
"""

from __future__ import annotations

import difflib
import math
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from financial_forecasting.features.evaluation.domain.services.pinball_score import (
    pinball_loss,
)
from tests.equivalence import comparison_set as cs
from tests.equivalence.alignment import mean_loss_by_timestamp, mean_over_seeds, window_starts
from tests.equivalence.comparisons import (
    U_Q_PICP,
    RawStatus,
    a1_check,
    a2_compare,
    dm_sense,
    pair_measures,
    pinball_at,
    sense_cell,
    side_of_nominal,
    sign,
    signed_delta,
    u_q_mpiw,
    u_q_pinball,
)
from tests.equivalence.prior_evidence import REGISTRY_PATH, load_registry
from tests.equivalence.readers import OfficialSide, PriorSide, read_official, read_prior

BEGIN_MARKER: Final = "<!-- BEGIN: declared-classification -->"
END_MARKER: Final = "<!-- END: declared-classification -->"
REPORTED: Final = "reported"
"""Status de um delta de modelo (EQ-DESC: documentado com sinal, sem limiar)."""
SECTIONS: Final = ("A9", "A10", "A11")
_HEADER: Final = "| id | h | grandeza | valores | tolerância | status |"
_RULE: Final = "|---|---|---|---|---|---|"
_TS: Final = cs.TIMESTAMP_COLUMN
_LEVEL_COLUMN: Final = re.compile(r"pinball_q(\d0)_(raw|post_guardrail)")

Status = RawStatus | None


@dataclass(frozen=True)
class AuditRow:
    """Uma comparação da auditoria."""

    id: str
    horizon: int
    quantity: str
    values: str
    tolerance: str
    status: Status

    @property
    def section(self) -> str:
        return self.id.split("/", 1)[0]


@dataclass(frozen=True)
class Declared:
    """A classificação declarada de uma comparação (id e status)."""

    id: str
    status: Status


def _status_text(status: Status) -> str:
    return REPORTED if status is None else status.value


def _status_of(text: str) -> Status:
    return None if text == REPORTED else RawStatus(text)


# --- render / parse -----------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render(rows: Iterable[AuditRow]) -> str:
    """As tabelas A9, A10 e A11 entre os marcadores da classificação declarada."""
    rows = list(rows)
    lines = [BEGIN_MARKER]
    for section in SECTIONS:
        lines += ["", f"### {section}", "", _HEADER, _RULE]
        lines += [
            f"| {_cell(row.id)} | {row.horizon} | {_cell(row.quantity)} | {_cell(row.values)} "
            f"| {_cell(row.tolerance)} | {_status_text(row.status)} |"
            for row in rows
            if row.section == section
        ]
    lines += ["", END_MARKER]
    return "\n".join(lines) + "\n"


_SPLIT_CELLS: Final = re.compile(r"(?<!\\)\|")


def parse(markdown: str) -> tuple[Declared, ...]:
    """A classificação declarada do bloco entre os marcadores.

    Raises:
        ValueError: marcador ausente/fora de ordem, linha de tabela com outro número de
            células ou status desconhecido.
    """
    start, end = markdown.find(BEGIN_MARKER), markdown.find(END_MARKER)
    if start < 0 or end < 0 or end < start:
        raise ValueError("declared-classification markers missing or out of order")
    declared: list[Declared] = []
    for line in markdown[start + len(BEGIN_MARKER) : end].splitlines():
        if not line.startswith("|") or line in (_HEADER, _RULE):
            continue
        cells = [cell.strip() for cell in _SPLIT_CELLS.split(line.strip())[1:-1]]
        if len(cells) != len(_HEADER.split("|")) - 2:
            raise ValueError(f"malformed table row: {line!r}")
        try:
            status = _status_of(cells[-1])
        except ValueError as error:
            raise ValueError(f"unknown status in row {line!r}") from error
        declared.append(Declared(cells[0].replace("\\|", "|"), status))
    return tuple(declared)


def declared_diff(declared: Sequence[Declared], parsed: Sequence[Declared]) -> str:
    """O diff (unified) entre a tabela declarada no teste e a do relatório; vazio = iguais."""

    def lines(items: Sequence[Declared]) -> list[str]:
        return [f"{item.id} {_status_text(item.status)}" for item in items]

    return "\n".join(
        difflib.unified_diff(lines(declared), lines(parsed), "declared", "parsed", lineterm="")
    )


def classification(rows: Iterable[AuditRow]) -> tuple[Declared, ...]:
    """A classificação recomputada (id e status) das linhas."""
    return tuple(Declared(row.id, row.status) for row in rows)


# --- A9 -----------------------------------------------------------------------------------


def _floats_equal(a: object, b: object) -> bool:
    return isinstance(a, float) and isinstance(b, float) and a.hex() == b.hex()


def prior_realized(rows: Sequence[Mapping[str, object]]) -> dict[int, dict[str, float]]:
    """y_ant por (h, timestamp): o `y_true` da janela de teste mais recente (D7).

    Raises:
        ValueError: dois `y_true` diferentes para o mesmo (h, timestamp) na mesma janela.
    """
    starts = window_starts(rows, window="config_signature", horizon="horizon", timestamp=_TS)
    best: dict[tuple[int, str], tuple[str, float]] = {}
    for row in rows:
        horizon, ts, y = row["horizon"], str(row[_TS]), row["y_true"]
        assert isinstance(horizon, int) and isinstance(y, float)
        start = starts[(row["config_signature"], horizon)]
        key = (horizon, ts)
        if key not in best or start > best[key][0]:
            best[key] = (start, y)
        elif start == best[key][0] and not _floats_equal(best[key][1], y):
            raise ValueError(f"two y_true for {key} in the window starting {start}")
    out: dict[int, dict[str, float]] = defaultdict(dict)
    for (horizon, ts), (_, y) in best.items():
        out[horizon][ts] = y
    return dict(out)


def _new_timestamps(official: OfficialSide, model: str) -> dict[int, set[str]]:
    found: dict[int, set[str]] = defaultdict(set)
    for row in official.predictions:
        if row["model"] == model:
            horizon = row["horizon"]
            assert isinstance(horizon, int)
            found[horizon].add(str(row["target_timestamp"]))
    return found


def a9_rows(
    prior: PriorSide, official: OfficialSide
) -> tuple[list[AuditRow], dict[int, tuple[str, ...]]]:
    """A1 por horizonte e T∩ (timestamps do realizado anterior ∩ do candidato novo)."""
    y_prior = prior_realized(prior.tables[cs.GOLD_OOS])
    new = _new_timestamps(official, official.candidate)
    rows: list[AuditRow] = []
    common: dict[int, tuple[str, ...]] = {}
    for horizon in cs.HORIZONS:
        shared = sorted(set(y_prior.get(horizon, {})) & new.get(horizon, set()))
        pairs = [
            (official.realized.realized_at(ts), y_prior[horizon][ts])
            for ts in shared
            if official.realized.index_of(ts) is not None
        ]
        common[horizon] = tuple(ts for ts in shared if official.realized.index_of(ts) is not None)
        result = a1_check(pairs)
        rows.append(
            AuditRow(
                id=f"A9/h{horizon}/realized",
                horizon=horizon,
                quantity="realizado y_t",
                values=(
                    f"T∩={result.n_points} out={result.n_out} max_abs_diff={result.max_abs_diff!r}"
                ),
                tolerance="2^-53·|y_ant|",
                status=result.status,
            )
        )
    return rows, common


# --- A10 ----------------------------------------------------------------------------------


def _quantity(column: str) -> tuple[str, float | None]:
    """(grandeza, nível) de uma coluna de valor: `pinball` por nível, `picp`, `mpiw`."""
    match = _LEVEL_COLUMN.fullmatch(column)
    if match is not None:
        return "pinball", int(match.group(1)) / 100
    return ("picp" if column.startswith("picp") else "mpiw"), None


def _m_a(
    sample: Sequence[Mapping[str, object]], column: str, variant: str
) -> tuple[float, float] | None:
    """(m_A, u_q) pelo código novo; `None` se a amostra tem valor ausente."""
    quantity, level = _quantity(column)
    realized = [row["y_true"] for row in sample]
    if quantity == "pinball":
        assert level is not None
        quantiles = [row[cs.PRIOR_QUANTILE_COLUMNS[level][variant]] for row in sample]
        if any(not isinstance(v, float) for v in (*realized, *quantiles)):
            return None
        value = pinball_at(realized, quantiles, level)  # type: ignore[arg-type]
        return value, u_q_pinball(value)
    low_level, high_level = cs.PAIR_80
    lows = [row[cs.PRIOR_QUANTILE_COLUMNS[low_level][variant]] for row in sample]
    highs = [row[cs.PRIOR_QUANTILE_COLUMNS[high_level][variant]] for row in sample]
    if any(not isinstance(v, float) for v in (*realized, *lows, *highs)):
        return None
    measures = pair_measures(realized, lows, highs)  # type: ignore[arg-type]
    if quantity == "picp":
        return measures.picp, U_Q_PICP
    return measures.mpiw, u_q_mpiw(measures.widths)


_A10_FILES: Final = (
    (cs.GOLD_METRICS_BY_RUN, "n_samples"),
    (cs.GOLD_CALIBRATION, "n_samples"),
    (cs.MARGINAL_COVERAGE, "n_obs"),
)


def a10_rows(prior: PriorSide) -> list[AuditRow]:
    """A2 por linha de métrica por run e por coluna de valor (amostra = a do run, D7)."""
    by_run: dict[tuple[object, object], list[Mapping[str, object]]] = defaultdict(list)
    for row in prior.tables[cs.GOLD_OOS]:
        by_run[(row["run_id"], row["horizon"])].append(row)
    rows: list[AuditRow] = []
    for path, size_column in _A10_FILES:
        stem = Path(path).stem
        for metric in prior.tables[path]:
            horizon, run_id = metric["horizon"], metric["run_id"]
            assert isinstance(horizon, int)
            sample = by_run.get((run_id, horizon), [])
            for column in cs.VALUE_COLUMNS[path]:
                variant = cs.variant_of_column(column)
                rows.append(
                    _a10_row(stem, run_id, horizon, column, variant, metric, sample, size_column)
                )
    return rows


def _a10_row(  # noqa: PLR0913 — os eixos de uma linha A10
    stem: str,
    run_id: object,
    horizon: int,
    column: str,
    variant: str,
    metric: Mapping[str, object],
    sample: Sequence[Mapping[str, object]],
    size_column: str,
) -> AuditRow:
    identity = f"A10/{stem}/{run_id}/h{horizon}/{column}"
    m_ant, n_recorded = metric[column], metric[size_column]
    computed = _m_a(sample, column, variant) if sample else None
    if computed is None or not isinstance(m_ant, float) or not isinstance(n_recorded, int):
        return AuditRow(
            identity, horizon, column, f"n_read={len(sample)}", "-", RawStatus.NOT_REALIZABLE
        )
    m_a, u_q = computed
    result = a2_compare(m_a=m_a, m_ant=m_ant, u_q=u_q, n_recorded=n_recorded, n_points=len(sample))
    values = f"m_A={m_a!r} m_ant={m_ant!r} n={len(sample)}/{n_recorded}"
    if result.abs_diff is not None:
        values += f" abs_diff={result.abs_diff!r}"
    tolerance = "-" if result.tolerance is None else repr(result.tolerance)
    return AuditRow(identity, horizon, column, values, tolerance, result.status)


# --- A11 ----------------------------------------------------------------------------------

# por (h, modelo/papel) → seed → ts → nível → valor
Grid = dict[object, dict[str, dict[float, float]]]


def _prior_points(rows: Sequence[Mapping[str, object]], labels: Iterable[str]) -> dict[int, Grid]:
    """Predições anteriores dos rótulos (pós-guardrail), um ponto por (seed, h, ts) — D7."""
    if cs.MODEL_LABEL_COLUMN is None:
        raise ValueError("MODEL_LABEL_COLUMN is not fixed: run the E1 before the E4")
    wanted = set(labels)
    selected = [row for row in rows if row[cs.MODEL_LABEL_COLUMN] in wanted]
    starts = window_starts(selected, window="config_signature", horizon="horizon", timestamp=_TS)
    best: dict[tuple[object, int, str], tuple[str, Mapping[str, object]]] = {}
    for row in selected:
        horizon = row["horizon"]
        assert isinstance(horizon, int)
        key = (row["seed"], horizon, str(row[_TS]))
        start = starts[(row["config_signature"], horizon)]
        if key not in best or start > best[key][0]:
            best[key] = (start, row)
    out: dict[int, Grid] = defaultdict(lambda: defaultdict(dict))
    for (seed, horizon, ts), (_, row) in best.items():
        out[horizon][seed][ts] = {
            level: row[columns[cs.PRIOR_LOSS_VARIANT]]  # type: ignore[misc]
            for level, columns in cs.PRIOR_QUANTILE_COLUMNS.items()
        }
    return out


def _new_points(official: OfficialSide, model: str) -> dict[int, Grid]:
    out: dict[int, Grid] = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for row in official.predictions:
        if row["model"] == model:
            horizon, level, value = row["horizon"], row["level"], row["value"]
            assert isinstance(horizon, int) and isinstance(level, float)
            assert isinstance(value, float)
            out[horizon][row["seed"]][str(row["target_timestamp"])][level] = value
    return out


@dataclass(frozen=True)
class _Side:
    """As medidas de um lado em T∩ (seeds agregadas por B-SEEDS)."""

    pinball: dict[float, float]
    picp: float
    mpiw: float
    covered_mean: float
    n: int


def _measure(grid: Grid, realized: Mapping[str, float], common: Sequence[str]) -> _Side:
    seeds = {seed: points for seed, points in grid.items() if all(ts in points for ts in common)}
    if not seeds or not common:
        raise ValueError("no seed covers the whole intersection")
    pinball = {
        level: math.fsum(
            mean_loss_by_timestamp(
                {
                    seed: {
                        ts: pinball_loss(
                            realized=realized[ts], quantile=points[ts][level], level=level
                        )
                        for ts in common
                    }
                    for seed, points in seeds.items()
                },
                common,
            ).values()
        )
        / len(common)
        for level in cs.COMMON_LEVELS
    }
    low, high = cs.PAIR_80
    per_seed = {
        seed: pair_measures(
            [realized[ts] for ts in common],
            [points[ts][low] for ts in common],
            [points[ts][high] for ts in common],
        )
        for seed, points in seeds.items()
    }
    return _Side(
        pinball=pinball,
        picp=mean_over_seeds({s: m.picp for s, m in per_seed.items()}),
        mpiw=mean_over_seeds({s: m.mpiw for s, m in per_seed.items()}),
        covered_mean=mean_over_seeds({s: float(m.covered) for s, m in per_seed.items()}),
        n=len(common),
    )


def _delta_row(horizon: int, quantity: str, new: float, prior: float) -> AuditRow:
    return AuditRow(
        f"A11/h{horizon}/candidate/{quantity}",
        horizon,
        quantity,
        f"m_novo={new!r} m_A={prior!r} delta={signed_delta(new, prior)!r}",
        "sentido (EQ-DESC)",
        None,
    )


def a11_rows(
    prior: PriorSide,
    official: OfficialSide,
    common: Mapping[int, tuple[str, ...]],
    a1_ok: Mapping[int, bool],
) -> list[AuditRow]:
    """Tabela de sentido por horizonte (D12 a, b, d) e o DM reportado por baseline (D8)."""
    rows: list[AuditRow] = []
    y_prior = prior_realized(prior.tables[cs.GOLD_OOS])
    prior_candidate = _prior_points(prior.tables[cs.GOLD_OOS], cs.PRIOR_CANDIDATE_LABELS)
    new_candidate = _new_points(official, official.candidate)
    y_new = {
        ts: official.realized.realized_at(ts) for ts in {t for ts in common.values() for t in ts}
    }
    for horizon in cs.HORIZONS:
        shared = common.get(horizon, ())
        if not a1_ok.get(horizon, False) or not shared:
            reason = "A1 out of tolerance" if shared else "empty intersection"
            status = RawStatus.NOT_REALIZABLE if shared else RawStatus.EMPTY_INTERSECTION
            rows.append(AuditRow(f"A11/h{horizon}/stopped", horizon, "modelo", reason, "-", status))
            continue
        new = _measure(new_candidate[horizon], y_new, shared)
        old = _measure(prior_candidate[horizon], y_prior[horizon], shared)
        rows += [
            _delta_row(
                horizon, f"pinball_q{round(level * 100)}", new.pinball[level], old.pinball[level]
            )
            for level in cs.COMMON_LEVELS
        ]
        rows += [
            _delta_row(horizon, "picp_80", new.picp, old.picp),
            _delta_row(horizon, "mpiw_80", new.mpiw, old.mpiw),
        ]
        new_side = side_of_nominal(count=new.covered_mean, n=new.n)
        old_side = side_of_nominal(count=old.covered_mean, n=old.n)
        rows.append(
            AuditRow(
                f"A11/h{horizon}/candidate/nominal_side_80",
                horizon,
                "lado do nominal PICP 80 %",
                f"novo={new_side} anterior={old_side}",
                "categórico",
                sense_cell(new_side, old_side),
            )
        )
        rows += _baseline_rows(prior, official, horizon, shared, new, old, y_new, y_prior[horizon])
    return rows


def _baseline_rows(  # noqa: PLR0913 — as duas medidas do candidato e os realizados
    prior: PriorSide,
    official: OfficialSide,
    horizon: int,
    shared: Sequence[str],
    new: _Side,
    old: _Side,
    y_new: Mapping[str, float],
    y_prior: Mapping[str, float],
) -> list[AuditRow]:
    rows: list[AuditRow] = []
    for baseline in cs.COMMON_BASELINES:
        new_b = _measure(_new_points(official, baseline.new_label)[horizon], y_new, shared)
        old_b = _measure(
            _prior_points(prior.tables[cs.GOLD_OOS], (baseline.prior_label,))[horizon],
            y_prior,
            shared,
        )
        for level in cs.COMMON_LEVELS:
            new_sign = sign(new.pinball[level] - new_b.pinball[level])
            old_sign = sign(old.pinball[level] - old_b.pinball[level])
            rows.append(
                AuditRow(
                    f"A11/h{horizon}/{baseline.new_label}/pinball_q{round(level * 100)}_sign",
                    horizon,
                    "sinal (candidato - baseline)",
                    f"novo={new_sign} anterior={old_sign}",
                    "categórico",
                    sense_cell(new_sign, old_sign),
                )
            )
        rows.append(_dm_row(prior, official, horizon, baseline))
    return rows


def _dm_row(
    prior: PriorSide, official: OfficialSide, horizon: int, baseline: cs.CommonBaseline
) -> AuditRow:
    identity = f"A11/h{horizon}/{baseline.new_label}/dm"
    new_rows = [
        row
        for row in official.dm_rows
        if row["horizon"] == horizon
        and row["variance_estimator"] == cs.NEW_DM_ESTIMATOR
        and row["candidate"] == official.candidate
        and row["comparator"] == baseline.new_label
    ]
    old_rows = [
        row
        for row in prior.tables[cs.DM_FAMILY_6]
        if row["horizon"] == horizon
        and row["baseline_model_version"] == baseline.prior_label
        and row["analysis_role"] == cs.PRIOR_DM_ANALYSIS_ROLE
    ]
    if len(new_rows) != 1 or len(old_rows) != 1:
        return AuditRow(
            identity,
            horizon,
            "DM",
            f"rows novo={len(new_rows)} anterior={len(old_rows)}",
            "-",
            RawStatus.NOT_REALIZABLE,
        )
    n, o = new_rows[0], old_rows[0]
    new_sense = dm_sense(
        mean_diff=n["mean_differential"],  # type: ignore[arg-type]
        convention=cs.NEW_DM_SIGN_CONVENTION,
        p_value=n[cs.NEW_DM_P_VALUE],  # type: ignore[arg-type]
        alpha=n["alpha"],  # type: ignore[arg-type]
    )
    old_sense = dm_sense(
        mean_diff=o[cs.PRIOR_DM_MEAN_DIFF],  # type: ignore[arg-type]
        convention=cs.PRIOR_DM_SIGN_CONVENTION,
        p_value=o[cs.PRIOR_DM_P_VALUE],  # type: ignore[arg-type]
        alpha=cs.PRIOR_DM_ALPHA,
    )
    return AuditRow(
        identity,
        horizon,
        "DM (sinal de d̄, rejeição)",
        f"novo={new_sense} anterior={old_sense}",
        "categórico",
        sense_cell(new_sense, old_sense),
    )


# --- cálculo ------------------------------------------------------------------------------


def compute_rows(prior: PriorSide, official: OfficialSide) -> tuple[AuditRow, ...]:
    """As linhas A9, A10 e A11 a partir dos dois lados já lidos."""
    a9, common = a9_rows(prior, official)
    a1_ok = {row.horizon: row.status is RawStatus.WITHIN_TOLERANCE for row in a9}
    return (*a9, *a10_rows(prior), *a11_rows(prior, official, common, a1_ok))


def compute(oracle_root: Path, official_root: Path) -> tuple[AuditRow, ...]:
    """Confere o registro, lê os dois lados e calcula a tabela.

    Raises:
        PriorEvidenceHashError: evidência anterior diferente do registro (falha, nunca pula).
    """
    prior = read_prior(oracle_root=oracle_root, registry=load_registry(REGISTRY_PATH))
    return compute_rows(prior, read_official(official_root))


def main(argv: Sequence[str] | None = None) -> int:
    """`<oracle_root> <official_root>`: imprime a tabela renderizada (nunca grava arquivo)."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:  # noqa: PLR2004
        sys.stderr.write("usage: python -m tests.equivalence.audit_table <oracle> <official>\n")
        return 2
    sys.stdout.write(render(compute(Path(args[0]), Path(args[1]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
