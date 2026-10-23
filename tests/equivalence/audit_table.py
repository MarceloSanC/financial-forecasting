"""Tabela da auditoria de equivalência: cálculo, classificação, renderização e parse (Stage 8.2).

Concept 8.2 A9-A12, D6; ADR 8.2.0003 item 5; doc de domínio §5.4-§5.6.
`compute(oracle_root, official_root)` devolve uma linha por comparação (id, horizonte, tipo,
grandeza, valores, tolerância, `RawStatus`):

- **A9** (D13): por horizonte, A1 do realizado em T∩ (y_ant da janela mais recente - D7 -, na
  precisão do tipo registrado; y_novo do `ReadTrainingGrid` real); A1 fora num horizonte ⇒ a
  comparação de modelo daquele horizonte para (`not_compared:A1`);
- **A10** (D12 c, e): por linha de métrica por run do anterior e por coluna de valor, m_A (o
  código novo sobre as predições do run, na variante do nome da coluna) contra m_ant;
- **A11** (D12 a, b, d): candidato x candidato em T∩ - deltas m_novo - m_A (`reported`:
  EQ-DESC, sem limiar) e o lado do nominal do PICP 80 % (célula de sentido) -; por baseline
  comum, o sinal de (candidato - baseline) por nível dentro de cada lado e o DM reportado por
  cada lado (D8).

A **classificação declarada** de cada linha (`classificação`) é `within_tolerance` /
`same_sense` (passou), `explained:<categoria>` ou `not_explained` (não passou; a categoria tem
de estar na tabela de aplicabilidade da §5.6 para o tipo da linha - `APPLICABILITY`),
`not_compared:<motivo>` (não comparada) ou `reported` (delta sem limiar). O `parse` recusa
classificação incoerente com o status ou categoria não aplicável ao tipo.

D7 e T∩ têm dono único em `alignment.py` (`latest_window_points`, `timestamps_by_horizon`,
`intersection`); B-SEEDS em `mean_loss_by_timestamp`/`mean_over_seeds`.
`python -m tests.equivalence.audit_table <oracle> <oficial>` **imprime** a tabela.
"""

from __future__ import annotations

import difflib
import math
import os
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
from tests.equivalence.alignment import (
    intersection,
    latest_window_points,
    mean_loss_by_timestamp,
    mean_over_seeds,
    timestamps_by_horizon,
)
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
"""Status/classificação de um delta de modelo (EQ-DESC: documentado com sinal, sem limiar)."""
SECTIONS: Final = ("A9", "A10", "A11")
_COLUMNS: Final = (
    "id",
    "h",
    "tipo",
    "grandeza",
    "valores",
    "tolerância",
    "status",
    "classificação",
)
_HEADER: Final = "| " + " | ".join(_COLUMNS) + " |"
_RULE: Final = "|" + "---|" * len(_COLUMNS)
_TS: Final = cs.TIMESTAMP_COLUMN
_LEVEL_COLUMN: Final = re.compile(r"pinball_q(\d0)_(raw|post_guardrail)")

# --- tipos de comparação e aplicabilidade (doc de domínio §5.6, transcrita) -------------------

KIND_A1: Final = "a1_realized"
KIND_A2_PINBALL: Final = "a2_pinball"
KIND_A2_PICP: Final = "a2_picp"
KIND_A2_MPIW: Final = "a2_mpiw"
KIND_SIGN: Final = "model_sign"
KIND_NOMINAL: Final = "model_nominal_side"
KIND_DM: Final = "dm_sense"
KIND_DELTA: Final = "model_delta"
"""Delta candidato x candidato: reportado, sem explicação exigida (doc §5.5)."""

APPLICABILITY_TEXT: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    # tipo: (comparação, categorias que podem explicá-la) - LITERAL da tabela "Aplicabilidade
    # por comparação" do doc de domínio reproduction-equivalence-and-reporting.md §5.6
    KIND_A1: ("A1 — realizado", ("alvo",)),
    KIND_A2_PINBALL: (
        "A2 — pinball por nível",
        (
            "escala (fator 2)",
            "bruto × rearranjado",  # noqa: RUF001 — transcrição literal do doc
            "amostra",
            "pesos na grade (se o anterior gravou só P̄_G)",
            "defeito referenciado",
        ),
    ),
    KIND_A2_PICP: (
        "A2 — PICP do par 80 %",
        (
            "convenção de empate",
            "bruto × rearranjado",  # noqa: RUF001 — transcrição literal do doc
            "amostra",
            "defeito referenciado",
        ),
    ),
    KIND_A2_MPIW: (
        "A2 — MPIW do par 80 %",
        ("bruto × rearranjado", "amostra", "defeito referenciado"),  # noqa: RUF001
    ),
    KIND_SIGN: (
        "modelo — sinal de (candidato − baseline comum) na pinball por nível",  # noqa: RUF001
        (
            "alvo (se A1 falhou)",
            "agregação de seeds do candidato",
            "defeito referenciado do modelo ou da pipeline anterior",
        ),
    ),
    KIND_NOMINAL: (
        "modelo — lado do nominal do PICP 80 %",
        ("alvo (se A1 falhou)", "agregação de seeds do candidato", "defeito referenciado"),
    ),
    KIND_DM: (
        "DM e grandezas só agregadas — sentido",
        (
            "agregação de seeds do candidato",
            "defeito referenciado (condição (c) dispensada, §5.5)",
        ),
    ),
}

CATEGORY_SLUGS: Final[dict[str, str]] = {
    "alvo": "alvo",
    "alvo (se A1 falhou)": "alvo",
    "escala (fator 2)": "escala",
    "bruto × rearranjado": "bruto_rearranjado",  # noqa: RUF001 — transcrição literal do doc
    "amostra": "amostra",
    "pesos na grade (se o anterior gravou só P̄_G)": "pesos_grade",
    "defeito referenciado": "defeito_referenciado",
    "defeito referenciado do modelo ou da pipeline anterior": "defeito_referenciado",
    "defeito referenciado (condição (c) dispensada, §5.5)": "defeito_referenciado",
    "convenção de empate": "convencao_empate",
    "agregação de seeds do candidato": "agregacao_seeds",
}
"""Rótulo da categoria (doc) → token da classificação `explained:<token>`."""

APPLICABILITY: Final[dict[str, frozenset[str]]] = {
    kind: frozenset(CATEGORY_SLUGS[label] for label in labels)
    for kind, (_, labels) in APPLICABILITY_TEXT.items()
}
"""Tipo de comparação → tokens de categoria que podem explicá-la (mecânico, doc §5.6)."""

_PASSING: Final = frozenset({RawStatus.WITHIN_TOLERANCE, RawStatus.SAME_SENSE})
_FAILING: Final = frozenset({RawStatus.OUT_OF_TOLERANCE, RawStatus.DIVERGENT_SENSE})
_NOT_COMPARED: Final = frozenset({RawStatus.NOT_REALIZABLE, RawStatus.EMPTY_INTERSECTION})
_NOT_EXPLAINED: Final = "not_explained"

Status = RawStatus | None


@dataclass(frozen=True)
class AuditRow:
    """Uma comparação da auditoria; `reason` é o motivo de uma linha não comparada."""

    id: str
    horizon: int
    kind: str
    quantity: str
    values: str
    tolerance: str
    status: Status
    reason: str = ""

    @property
    def section(self) -> str:
        return self.id.split("/", 1)[0]


@dataclass(frozen=True)
class Declared:
    """A classificação declarada de uma comparação: id, tipo, status e classificação."""

    id: str
    kind: str
    status: Status
    classification: str


def _status_text(status: Status) -> str:
    return REPORTED if status is None else status.value


def _status_of(text: str) -> Status:
    return None if text == REPORTED else RawStatus(text)


def default_classification(row: AuditRow) -> str:
    """A classificação antes da explicação humana: o status, `not_compared:<motivo>`,
    `reported` ou `not_explained`."""
    if row.status is None:
        return REPORTED
    if row.status in _NOT_COMPARED:
        return f"not_compared:{row.reason or row.status.value}"
    if row.status in _FAILING:
        return _NOT_EXPLAINED
    return row.status.value


def check_classification(kind: str, status: Status, classification: str) -> None:
    """Coerência da classificação com o status e a aplicabilidade da §5.6.

    Raises:
        ValueError: tipo desconhecido, classificação que não cabe no status ou categoria fora
            da tabela de aplicabilidade do tipo.
    """
    if kind != KIND_DELTA and kind not in APPLICABILITY:
        raise ValueError(f"unknown comparison kind {kind!r}")
    if status is None or kind == KIND_DELTA:
        if status is not None or kind != KIND_DELTA or classification != REPORTED:
            raise ValueError(f"only a {KIND_DELTA} row is {REPORTED}, got {kind}/{classification}")
        return
    if status in _PASSING:
        ok = classification == status.value
    elif status in _NOT_COMPARED:
        ok = classification.startswith("not_compared:") and len(classification) > len(
            "not_compared:"
        )
    else:
        category = classification.removeprefix("explained:")
        if classification.startswith("explained:") and category not in APPLICABILITY[kind]:
            raise ValueError(
                f"category {category!r} cannot explain a {kind} comparison "
                f"(§5.6 applicability: {sorted(APPLICABILITY[kind])})"
            )
        ok = classification == _NOT_EXPLAINED or classification.startswith("explained:")
    if not ok:
        raise ValueError(f"classification {classification!r} does not fit status {status.value}")


# --- render / parse -----------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render(rows: Iterable[AuditRow], classifications: Mapping[str, str] | None = None) -> str:
    """As tabelas A9, A10 e A11 entre os marcadores; `classifications` (id → classificação)
    sobrepõe a `default_classification` com a explicação declarada.

    Raises:
        ValueError: classificação incoerente (`check_classification`).
    """
    chosen = dict(classifications or {})
    rows = list(rows)
    lines = [BEGIN_MARKER]
    for section in SECTIONS:
        lines += ["", f"### {section}", "", _HEADER, _RULE]
        for row in rows:
            if row.section != section:
                continue
            label = chosen.get(row.id, default_classification(row))
            check_classification(row.kind, row.status, label)
            cells = (
                row.id,
                str(row.horizon),
                row.kind,
                row.quantity,
                row.values,
                row.tolerance,
                _status_text(row.status),
                label,
            )
            lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    lines += ["", END_MARKER]
    return "\n".join(lines) + "\n"


_SPLIT_CELLS: Final = re.compile(r"(?<!\\)\|")


def parse(markdown: str) -> tuple[Declared, ...]:
    """A classificação declarada do bloco entre os marcadores.

    Raises:
        ValueError: marcador ausente/fora de ordem, linha com outro número de células, status
            desconhecido ou classificação incoerente/não aplicável (`check_classification`).
    """
    start, end = markdown.find(BEGIN_MARKER), markdown.find(END_MARKER)
    if start < 0 or end < 0 or end < start:
        raise ValueError("declared-classification markers missing or out of order")
    declared: list[Declared] = []
    for line in markdown[start + len(BEGIN_MARKER) : end].splitlines():
        if not line.startswith("|") or line in (_HEADER, _RULE):
            continue
        cells = [
            cell.strip().replace("\\|", "|") for cell in _SPLIT_CELLS.split(line.strip())[1:-1]
        ]
        if len(cells) != len(_COLUMNS):
            raise ValueError(f"malformed table row: {line!r}")
        try:
            status = _status_of(cells[6])
        except ValueError as error:
            raise ValueError(f"unknown status in row {line!r}") from error
        check_classification(cells[2], status, cells[7])
        declared.append(Declared(cells[0], cells[2], status, cells[7]))
    return tuple(declared)


def declared_diff(declared: Sequence[Declared], parsed: Sequence[Declared]) -> str:
    """O diff (unified) entre duas classificações; vazio = iguais."""

    def lines(items: Sequence[Declared]) -> list[str]:
        return [
            f"{item.id} {item.kind} {_status_text(item.status)} {item.classification}"
            for item in items
        ]

    return "\n".join(
        difflib.unified_diff(lines(declared), lines(parsed), "declared", "parsed", lineterm="")
    )


def classification(
    rows: Iterable[AuditRow], classifications: Mapping[str, str] | None = None
) -> tuple[Declared, ...]:
    """A classificação das linhas (a padrão, ou a declarada por id)."""
    chosen = dict(classifications or {})
    return tuple(
        Declared(row.id, row.kind, row.status, chosen.get(row.id, default_classification(row)))
        for row in rows
    )


def recomputed_matches(rows: Sequence[AuditRow], declared: Sequence[Declared]) -> bool:
    """Ids, tipos e status recomputados = os declarados (a classificação humana à parte)."""
    return [(r.id, r.kind, r.status) for r in rows] == [(d.id, d.kind, d.status) for d in declared]


# --- guardas e precisão -----------------------------------------------------------------------


def check_e1_fixed(prior: PriorSide) -> None:
    """O conjunto de comparação está fechado pela E1 (CC4-7).

    Raises:
        ValueError: `MODEL_LABEL_COLUMN` ou `PRIOR_CANDIDATE_LABELS` vazios, ou baseline comum
            cuja `source` não está no registro (D12 a).
    """
    if cs.MODEL_LABEL_COLUMN is None or not cs.PRIOR_CANDIDATE_LABELS:
        raise ValueError(
            "MODEL_LABEL_COLUMN and PRIOR_CANDIDATE_LABELS are not fixed: run the E1 before the E4"
        )
    unregistered = [b.source for b in cs.COMMON_BASELINES if b.source not in prior.source_ids]
    if unregistered:
        raise ValueError(f"common baselines with unregistered definition sources: {unregistered}")


def storage_half_ulp(prior: PriorSide, path: str, column: str) -> float:
    """Meio ulp do tipo físico registrado da coluna (CC4-5)."""
    return cs.half_ulp_of(prior.column_types[path][column])


# --- lado anterior: D7 por `alignment` --------------------------------------------------------

# h → seed → timestamp → nível → valor
Grid = dict[int, dict[object, dict[str, dict[float, float]]]]


def _prior_selected(
    rows: Sequence[Mapping[str, object]], labels: Iterable[str]
) -> list[Mapping[str, object]]:
    """Um ponto por (seed, h, ts) dos rótulos: o da janela mais recente (D7, `alignment`)."""
    assert cs.MODEL_LABEL_COLUMN is not None  # check_e1_fixed
    wanted = set(labels)
    return latest_window_points(
        [row for row in rows if row[cs.MODEL_LABEL_COLUMN] in wanted],
        point_key=lambda row: (row["seed"], row["horizon"], str(row[_TS])),
        window="config_signature",
        horizon="horizon",
        timestamp=_TS,
    )


def prior_grid(rows: Sequence[Mapping[str, object]], labels: Iterable[str]) -> Grid:
    """Predições anteriores dos rótulos na variante da loss (`post_guardrail`), D7 aplicado."""
    out: Grid = defaultdict(lambda: defaultdict(dict))
    for row in _prior_selected(rows, labels):
        horizon = row["horizon"]
        assert isinstance(horizon, int)
        out[horizon][row["seed"]][str(row[_TS])] = {
            level: row[columns[cs.PRIOR_LOSS_VARIANT]]  # type: ignore[misc]
            for level, columns in cs.PRIOR_QUANTILE_COLUMNS.items()
        }
    return out


def prior_realized(rows: Sequence[Mapping[str, object]]) -> dict[int, dict[str, float]]:
    """y_ant por (h, ts): o `y_true` dos pontos do candidato depois do D7; as seeds concordam.

    Raises:
        ValueError: duas seeds com `y_true` diferentes no mesmo (h, ts).
    """
    out: dict[int, dict[str, float]] = defaultdict(dict)
    for row in _prior_selected(rows, cs.PRIOR_CANDIDATE_LABELS):
        horizon, ts, y = row["horizon"], str(row[_TS]), row["y_true"]
        assert isinstance(horizon, int) and isinstance(y, float)
        seen = out[horizon].get(ts)
        if seen is not None and seen.hex() != y.hex():
            raise ValueError(f"prior seeds disagree on y_true at h={horizon} {ts}")
        out[horizon][ts] = y
    return dict(out)


def new_grid(official: OfficialSide, model: str) -> Grid:
    """Predições novas de `model` (pós-guardrail).

    Raises:
        ValueError: (seed, h, ts, nível) repetido - premissa D-M4 (CC4-8).
    """
    out: Grid = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for row in official.predictions:
        if row["model"] != model:
            continue
        horizon, level, value = row["horizon"], row["level"], row["value"]
        assert isinstance(horizon, int) and isinstance(level, float)
        assert isinstance(value, float)
        point = out[horizon][row["seed"]][str(row["target_timestamp"])]
        if level in point:
            raise ValueError(
                f"repeated prediction of {model} seed {row['seed']} h={horizon} "
                f"{row['target_timestamp']} level {level}"
            )
        point[level] = value
    return out


# --- A9 -----------------------------------------------------------------------------------


def a9_rows(
    prior: PriorSide, official: OfficialSide
) -> tuple[list[AuditRow], dict[int, tuple[str, ...]]]:
    """A1 por horizonte e T∩ (realizado anterior ∩ candidato novo, por `alignment`).

    Raises:
        ValueError: timestamp de T∩ fora das sessões do realizado novo.
    """
    y_prior = prior_realized(prior.tables[cs.GOLD_OOS])
    new_ts = timestamps_by_horizon(
        [r for r in official.predictions if r["model"] == official.candidate],
        horizon="horizon",
        timestamp="target_timestamp",
    )
    common = intersection({h: list(ys) for h, ys in y_prior.items()}, new_ts)
    half_ulp = storage_half_ulp(prior, cs.GOLD_OOS, "y_true")
    rows: list[AuditRow] = []
    for horizon in cs.HORIZONS:
        shared = common.get(horizon, ())
        pairs = [(official.realized.realized_at(ts), y_prior[horizon][ts]) for ts in shared]
        result = a1_check(pairs, half_ulp=half_ulp)
        rows.append(
            AuditRow(
                id=f"A9/h{horizon}/realized",
                horizon=horizon,
                kind=KIND_A1,
                quantity="realizado y_t",
                values=(
                    f"T∩={result.n_points} out={result.n_out} max_abs_diff={result.max_abs_diff!r}"
                ),
                tolerance=f"{half_ulp!r}·|y_ant|",
                status=result.status,
                reason="empty_intersection",
            )
        )
    return rows, {h: common.get(h, ()) for h in cs.HORIZONS}


# --- A10 ----------------------------------------------------------------------------------


def _quantity(column: str) -> tuple[str, float | None]:
    match = _LEVEL_COLUMN.fullmatch(column)
    if match is not None:
        return "pinball", int(match.group(1)) / 100
    return ("picp" if column.startswith("picp") else "mpiw"), None


_KIND_OF: Final = {"pinball": KIND_A2_PINBALL, "picp": KIND_A2_PICP, "mpiw": KIND_A2_MPIW}


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


def a10_rows(prior: PriorSide, a1_ok: Mapping[int, bool] | None = None) -> list[AuditRow]:
    """A2 por linha de métrica por run e por coluna de valor (amostra = a do run, D7).

    Num horizonte com A1 fora, as linhas A10 ficam `not_compared:A1` (runbook E4 passo 2).
    """
    by_run: dict[tuple[object, object], list[Mapping[str, object]]] = defaultdict(list)
    for row in prior.tables[cs.GOLD_OOS]:
        by_run[(row["run_id"], row["horizon"])].append(row)
    rows: list[AuditRow] = []
    for path, size_column in _A10_FILES:
        for metric in prior.tables[path]:
            horizon = metric["horizon"]
            assert isinstance(horizon, int)
            sample = by_run.get((metric["run_id"], horizon), [])
            for column in cs.VALUE_COLUMNS[path]:
                audited = _a10_row(prior, path, column, metric, sample, size_column)
                if a1_ok is not None and not a1_ok.get(horizon, False):
                    audited = AuditRow(
                        audited.id,
                        horizon,
                        audited.kind,
                        column,
                        "A1 out of tolerance",
                        "-",
                        RawStatus.NOT_REALIZABLE,
                        "A1",
                    )
                rows.append(audited)
    return rows


def _a10_row(  # noqa: PLR0913 — os eixos de uma linha A10
    prior: PriorSide,
    path: str,
    column: str,
    metric: Mapping[str, object],
    sample: Sequence[Mapping[str, object]],
    size_column: str,
) -> AuditRow:
    horizon = metric["horizon"]
    assert isinstance(horizon, int)
    identity = f"A10/{Path(path).stem}/{metric['run_id']}/h{horizon}/{column}"
    kind = _KIND_OF[_quantity(column)[0]]
    m_ant, n_recorded = metric[column], metric[size_column]
    computed = _m_a(sample, column, cs.variant_of_column(column)) if sample else None
    if computed is None or not isinstance(m_ant, float) or not isinstance(n_recorded, int):
        return AuditRow(
            identity,
            horizon,
            kind,
            column,
            f"n_read={len(sample)}",
            "-",
            RawStatus.NOT_REALIZABLE,
            "sample",
        )
    m_a, u_q = computed
    result = a2_compare(
        m_a=m_a,
        m_ant=m_ant,
        u_q=u_q,
        n_recorded=n_recorded,
        n_points=len(sample),
        storage_half_ulp=storage_half_ulp(prior, path, column),
    )
    values = f"m_A={m_a!r} m_ant={m_ant!r} n={len(sample)}/{n_recorded}"
    if result.abs_diff is not None:
        values += f" abs_diff={result.abs_diff!r}"
    tolerance = "-" if result.tolerance is None else repr(result.tolerance)
    return AuditRow(identity, horizon, kind, column, values, tolerance, result.status, "sample")


# --- A11 ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class SideMeasures:
    """As medidas de um lado em T∩ (seeds agregadas por B-SEEDS)."""

    pinball: dict[float, float]
    picp: float
    mpiw: float
    covered_mean: float
    n: int


def measure(
    by_seed: Mapping[object, Mapping[str, Mapping[float, float]]],
    realized: Mapping[str, float],
    common: Sequence[str],
) -> SideMeasures:
    """Pinball pela média das perdas por timestamp entre seeds; PICP/MPIW pela média por seed.

    Raises:
        ValueError: sem seed, ou seed sem algum ponto de T∩ (nomeada — CC4-3).
    """
    missing = sorted(
        (str(seed) for seed, points in by_seed.items() if any(ts not in points for ts in common))
    )
    if not by_seed or missing:
        raise ValueError(f"seeds {missing} do not cover the intersection (B-SEEDS needs all)")
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
                    for seed, points in by_seed.items()
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
        for seed, points in by_seed.items()
    }
    return SideMeasures(
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
        KIND_DELTA,
        quantity,
        f"m_novo={new!r} m_A={prior!r} delta={signed_delta(new, prior)!r}",
        "sentido (EQ-DESC)",
        None,
    )


def _level_name(level: float) -> str:
    return f"pinball_q{round(level * 100)}"


def a11_rows(
    prior: PriorSide,
    official: OfficialSide,
    common: Mapping[int, tuple[str, ...]],
    a1_ok: Mapping[int, bool],
) -> list[AuditRow]:
    """Tabela de sentido por horizonte (D12 a, b, d) e o DM reportado por baseline (D8)."""
    rows: list[AuditRow] = []
    y_prior = prior_realized(prior.tables[cs.GOLD_OOS])
    old_candidate = prior_grid(prior.tables[cs.GOLD_OOS], cs.PRIOR_CANDIDATE_LABELS)
    new_candidate = new_grid(official, official.candidate)
    for horizon in cs.HORIZONS:
        shared = common.get(horizon, ())
        if not shared:
            rows.append(
                AuditRow(
                    f"A11/h{horizon}/stopped",
                    horizon,
                    KIND_SIGN,
                    "modelo",
                    "T∩ vazio",
                    "-",
                    RawStatus.EMPTY_INTERSECTION,
                    "empty_intersection",
                )
            )
            continue
        if not a1_ok.get(horizon, False):
            rows.append(
                AuditRow(
                    f"A11/h{horizon}/stopped",
                    horizon,
                    KIND_SIGN,
                    "modelo",
                    "A1 out of tolerance",
                    "-",
                    RawStatus.NOT_REALIZABLE,
                    "A1",
                )
            )
            continue
        y_new = {ts: official.realized.realized_at(ts) for ts in shared}
        new = measure(new_candidate[horizon], y_new, shared)
        old = measure(old_candidate[horizon], y_prior[horizon], shared)
        rows += [
            _delta_row(horizon, _level_name(level), new.pinball[level], old.pinball[level])
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
                KIND_NOMINAL,
                "lado do nominal PICP 80 %",
                f"novo={new_side} anterior={old_side}",
                "categórico",
                sense_cell(new_side, old_side),
            )
        )
        for baseline in cs.COMMON_BASELINES:
            new_b = measure(new_grid(official, baseline.new_label)[horizon], y_new, shared)
            old_b = measure(
                prior_grid(prior.tables[cs.GOLD_OOS], (baseline.prior_label,))[horizon],
                y_prior[horizon],
                shared,
            )
            for level in cs.COMMON_LEVELS:
                new_sign = sign(new.pinball[level] - new_b.pinball[level])
                old_sign = sign(old.pinball[level] - old_b.pinball[level])
                rows.append(
                    AuditRow(
                        f"A11/h{horizon}/{baseline.new_label}/{_level_name(level)}_sign",
                        horizon,
                        KIND_SIGN,
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
            KIND_DM,
            "DM",
            f"rows novo={len(new_rows)} anterior={len(old_rows)}",
            "-",
            RawStatus.NOT_REALIZABLE,
            "dm_rows",
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
        KIND_DM,
        "DM (sinal de d̄, rejeição)",
        f"novo={new_sense} anterior={old_sense}",
        "categórico",
        sense_cell(new_sense, old_sense),
    )


# --- cálculo ------------------------------------------------------------------------------


def compute_rows(prior: PriorSide, official: OfficialSide) -> tuple[AuditRow, ...]:
    """As linhas A9, A10 e A11 a partir dos dois lados já lidos (guarda da E1 primeiro)."""
    check_e1_fixed(prior)
    a9, common = a9_rows(prior, official)
    a1_ok = {row.horizon: row.status is RawStatus.WITHIN_TOLERANCE for row in a9}
    return (*a9, *a10_rows(prior, a1_ok), *a11_rows(prior, official, common, a1_ok))


def compute(oracle_root: Path, official_root: Path) -> tuple[AuditRow, ...]:
    """Confere o registro, lê os dois lados e calcula a tabela.

    Raises:
        PriorEvidenceHashError: evidência anterior diferente do registro (falha, nunca pula).
    """
    prior = read_prior(oracle_root=oracle_root, registry=load_registry(REGISTRY_PATH))
    check_e1_fixed(prior)
    return compute_rows(prior, read_official(official_root))


ORACLE_ENV: Final = "EQUIVALENCE_ORACLE_ROOT"
OFFICIAL_ENV: Final = "EQUIVALENCE_OFFICIAL_ROOT"


def main(argv: Sequence[str] | None = None) -> int:
    """`[<oracle_root> <official_root>]` (sem argumentos: `EQUIVALENCE_ORACLE_ROOT` e
    `EQUIVALENCE_OFFICIAL_ROOT`, como o runbook da E4 chama): imprime a tabela renderizada,
    nunca grava arquivo."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        args = [os.environ.get(ORACLE_ENV, ""), os.environ.get(OFFICIAL_ENV, "")]
    if len(args) != 2 or not all(args):  # noqa: PLR2004
        sys.stderr.write(
            "usage: python -m tests.equivalence.audit_table <oracle> <official> "
            f"(or {ORACLE_ENV} and {OFFICIAL_ENV})\n"
        )
        return 2
    sys.stdout.write(render(compute(Path(args[0]), Path(args[1]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
