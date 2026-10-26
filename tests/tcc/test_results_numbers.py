"""Teste opt-in: os números do capítulo de resultados do TCC conferem com a geração julgada.

Fora do CI por construção, como a equivalência da 8.2: lê a geração julgada de
`TCC_JUDGED_ROOT` (a pasta `judged/<preregistration_ref>/` da partição do cohort
confirmatório, montada `:ro`); sem a variável, ou com caminho inexistente, **pula**.

Cada número de tabela do capítulo 5 e os números de prosa listados em `_PROSE` são lidos do
LaTeX e conferidos contra o valor gravado: o número exibido tem de ser o arredondamento do
valor às casas exibidas (`consistent`). Nunca recalcula métrica; só lê scorecard e tabelas.

    TCC_JUDGED_ROOT=/judged uv run --no-sync pytest tests/tcc/test_results_numbers.py -rs -q
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from statistics import mean
from typing import Any, Final

import pyarrow.parquet as pq
import pytest

from tests.tcc.latex_numbers import (
    consistent,
    normalize,
    parse_interval,
    parse_number,
    table_rows,
)

_ROOT_VAR: Final = "TCC_JUDGED_ROOT"
_RESULTS_TEX: Final = Path(__file__).parents[2] / "text" / "5_Resultados" / "5_Resultados.tex"
_HORIZONS: Final = (1, 7)
_TFT: Final = "tft_quantile"
_N_SEEDS: Final = 10
_ALPHA: Final = 0.05
_VAR_LEVEL: Final = 0.98
_VAR_BAND: Final = 0.95
_WINKLER_LOW: Final = 0.10
_MODELS: Final[Mapping[str, str]] = {
    "Retorno nulo": "baseline_zero_return",
    "Média histórica": "baseline_historical_mean",
    "AR(1)": "baseline_ar1",
    "EWMA-vol": "baseline_ewma_vol",
    "Quantis empíricos": "baseline_historical_quantiles",
    "GBM quantílico": "gbm_quantile",
    "TFT": _TFT,
}
_FAMILIES: Final[Mapping[str, str]] = {
    "Técnico": "technical",
    "Preço": "price",
    "Sentimento": "sentiment",
    "Fundamento": "fundamental",
}

Rows = list[dict[str, Any]]


def _root() -> Path:
    raw = os.environ.get(_ROOT_VAR)
    if not raw or not Path(raw).is_dir():
        pytest.skip(f"{_ROOT_VAR} ausente ou inexistente ({raw!r}): conferência opt-in")
    return Path(raw)


def _table(root: Path, name: str) -> Rows:
    path = root / "generation" / f"{name}.parquet"
    file = pq.ParquetFile(path)  # type: ignore[no-untyped-call]
    rows: Rows = file.read().to_pylist()  # type: ignore[no-untyped-call]
    return rows


@pytest.fixture(scope="module")
def judged() -> dict[str, Any]:
    root = _root()
    scorecard = json.loads(
        (root / "gold_model_comparison_confirmatory_scorecard.json").read_text(encoding="utf-8")
    )
    return {
        "scorecard": scorecard,
        **{
            name: _table(root, f"gold_{name}")
            for name in (
                "metrics_by_run",
                "dm_results",
                "mcs_results",
                "mcs_block_sensitivity",
                "h3_shares",
                "h3_vsn",
                "conformal_coverage",
                "calibration_table",
            )
        },
    }


@pytest.fixture(scope="module")
def tex() -> str:
    return _RESULTS_TEX.read_text(encoding="utf-8")


def _check(cell: str, value: float, where: str, *, scale: float = 1.0) -> None:
    shown, decimals = parse_number(cell)
    expected = value * scale
    assert consistent(shown, decimals, expected), f"{where}: texto {cell!r}, gravado {expected!r}"


def _h1(judged: Mapping[str, Any], horizon: int) -> dict[str, Any]:
    for entry in judged["scorecard"]["verdict"]["horizons"]:
        if entry["horizon"] == horizon:
            h1: dict[str, Any] = entry["h1"]
            return h1
    raise AssertionError(f"horizon {horizon} missing from the scorecard")


def _pinball(judged: Mapping[str, Any], model: str, horizon: int) -> list[float]:
    return [
        row["value"]
        for row in judged["metrics_by_run"]
        if row["model"] == model
        and row["horizon"] == horizon
        and row["sample"] == "common"
        and row["metric"] == "pinball_grid_mean"
    ]


def _one(rows: Rows, where: str, **match: object) -> dict[str, Any]:
    found = [row for row in rows if all(row[k] == v for k, v in match.items())]
    assert len(found) == 1, f"{where}: {len(found)} rows for {match}"
    return found[0]


def test_h1_gate_table(tex: str, judged: dict[str, Any]) -> None:
    rows = {row[0].split(" ")[0]: row for row in table_rows(tex, "tab:h1")}
    for name, band in (("Inferior", "lower_band"), ("Superior", "upper_band")):
        for i, horizon in enumerate(_HORIZONS):
            gold = _h1(judged, horizon)[band]
            _check(rows[name][1 + 2 * i], gold["estimate"], f"H1 {name} h+{horizon}")
            (low, low_d), (high, high_d) = parse_interval(rows[name][2 + 2 * i])
            assert consistent(low, low_d, gold["lower"]), f"Wilson inferior {name} h+{horizon}"
            assert consistent(high, high_d, gold["upper"]), f"Wilson superior {name} h+{horizon}"


def test_h1_power_table(tex: str, judged: dict[str, Any]) -> None:
    order = (
        "width_5pp_wide",
        "width_5pp_narrow",
        "location_0_2_sigma",
        "width_3pp_wide",
        "width_3pp_narrow",
        "location_0_1_sigma",
    )
    rows = table_rows(tex, "tab:h1-poder")[1:]
    assert len(rows) == len(order)
    for row, label in zip(rows, order, strict=True):
        for i, horizon in enumerate(_HORIZONS):
            power = {p["label"]: p["failure_probability"] for p in _h1(judged, horizon)["power"]}
            _check(row[2 + i], power[label], f"poder {label} h+{horizon}")


def test_pinball_table(tex: str, judged: dict[str, Any]) -> None:
    for row in table_rows(tex, "tab:h2-perdas"):
        if row[1] not in _MODELS:
            continue
        model = _MODELS[row[1]]
        for i, horizon in enumerate(_HORIZONS):
            values = _pinball(judged, model, horizon)
            if model == _TFT:
                assert len(values) == _N_SEEDS, f"TFT h+{horizon}: {len(values)} seeds"
                head, interval = row[2 + i].split(" ", 1)
                _check(head, mean(values), f"TFT h+{horizon} média", scale=1e3)
                (low, low_d), (high, high_d) = parse_interval(interval)
                assert consistent(low, low_d, min(values) * 1e3), f"TFT h+{horizon} mínimo"
                assert consistent(high, high_d, max(values) * 1e3), f"TFT h+{horizon} máximo"
            else:
                assert len(values) == 1, f"{model} h+{horizon}: {len(values)} rows"
                _check(row[2 + i], values[0], f"{model} h+{horizon}", scale=1e3)


def test_dm_table(tex: str, judged: dict[str, Any]) -> None:
    for row in table_rows(tex, "tab:h2-dm"):
        if row[0] not in _MODELS:
            continue
        comparator = _MODELS[row[0]]
        for i, horizon in enumerate(_HORIZONS):
            gold = _one(
                judged["dm_results"],
                "DM",
                horizon=horizon,
                comparator=comparator,
                variance_estimator="rectangular",
            )
            where = f"DM {comparator} h+{horizon}"
            _check(row[1 + 3 * i], gold["mean_differential"], f"{where} d", scale=1e5)
            _check(row[2 + 3 * i], gold["statistic"], f"{where} estatística")
            p_cell = row[3 + 3 * i]
            if p_cell.startswith("<10^"):
                bound = 10.0 ** int(p_cell.removeprefix("<10^").strip("{}"))
                assert gold["adjusted_p_value"] < bound, f"{where} p_Holm"
            else:
                _check(p_cell, gold["adjusted_p_value"], f"{where} p_Holm")


def test_mcs_table(tex: str, judged: dict[str, Any]) -> None:
    primary: Callable[[str, int, str], float] = lambda model, horizon, scheme: _one(  # noqa: E731
        judged["mcs_results"], "MCS", model=model, horizon=horizon, scheme=scheme
    )["mcs_p_value"]
    block: Callable[[str, int, str], float] = lambda model, horizon, rule: _one(  # noqa: E731
        judged["mcs_block_sensitivity"], "MCS bloco", model=model, horizon=horizon, block_rule=rule
    )["mcs_p_value"]
    for row in table_rows(tex, "tab:h2-mcs"):
        if row[0] not in _MODELS:
            continue
        model = _MODELS[row[0]]
        for i, horizon in enumerate(_HORIZONS):
            values = (
                primary(model, horizon, "stationary"),
                primary(model, horizon, "moving_block"),
                block(model, horizon, "h"),
                block(model, horizon, "sqrt_T"),
            )
            for j, value in enumerate(values):
                _check(row[1 + 4 * i + j], value, f"MCS {model} h+{horizon} coluna {j}")


def test_h3_table(tex: str, judged: dict[str, Any]) -> None:
    method = ""
    for row in table_rows(tex, "tab:h3"):
        if row[1] not in _FAMILIES:
            continue
        method = {"Permutação": "permutation", "Ablação": "loco"}.get(row[0], method)
        gold = _one(judged["h3_shares"], "H3", method=method, family=_FAMILIES[row[1]])
        where = f"H3 {method} {row[1]}"
        _check(row[2], gold["share_h1"], f"{where} s(h+1)")
        _check(row[3], gold["share_h7"], f"{where} s(h+7)")
        _check(row[4], gold["delta"], f"{where} delta")
        if row[5].startswith("ilimitado"):
            assert gold["lower_infinite"] and gold["upper_infinite"], f"{where} intervalo"
        else:
            (low, low_d), (high, high_d) = parse_interval(row[5])
            assert consistent(low, low_d, gold["lower"]), f"{where} limite inferior"
            assert consistent(high, high_d, gold["upper"]), f"{where} limite superior"


def _prose(judged: Mapping[str, Any]) -> list[tuple[str, float]]:
    """(prefixo normalizado do texto, valor gravado) dos números de prosa conferidos."""
    tft = {h: mean(_pinball(judged, _TFT, h)) for h in _HORIZONS}
    ewma = {h: _pinball(judged, "baseline_ewma_vol", h)[0] for h in _HORIZONS}
    mcs_tft = {
        h: _one(judged["mcs_results"], "MCS", model=_TFT, horizon=h, scheme="stationary")[
            "mcs_p_value"
        ]
        for h in _HORIZONS
    }
    block_h7 = _one(
        judged["mcs_block_sensitivity"], "MCS bloco", model=_TFT, horizon=7, block_rule="h"
    )["mcs_p_value"]
    vsn = {row["family"]: row["p50"] for row in judged["h3_vsn"] if row["kind"] == "family"}
    record = "split_cqr_asymmetric_unweighted_v1"

    def coverage(variant: str, horizon: int) -> dict[str, Any]:
        return _one(
            judged["conformal_coverage"],
            "conformal",
            variant=variant,
            horizon=horizon,
            kind="pair",
            lower_level=0.1,
            upper_level=0.9,
            seed=None,
        )

    lr_uc = {h: _h1(judged, h)["lr_uc"]["p_value"] for h in _HORIZONS}
    return [
        ("A perda do TFT ficou ", (tft[1] / ewma[1] - 1) * 100),
        ("acima da do EWMA-vol em h+1 e ", (tft[7] / ewma[7] - 1) * 100),
        ("e elimina o TFT (p_{\\text{MCS}} = ", mcs_tft[1]),
        ("o TFT permanece no conjunto (p_{\\text{MCS}} = ", mcs_tft[7]),
        ("o TFT seria eliminado (p_{\\text{MCS}} = ", block_h7),
        ("medianas sobre as decisões de ", vsn["technical"]),
        ("medianas sobre as decisões|para a família técnica, ", vsn["price"]),
        ("medianas sobre as decisões|para preço, ", vsn["sentiment"]),
        ("medianas sobre as decisões|para sentimento e ", vsn["fundamental"]),
        (
            "levou a cobertura do intervalo de 80% para ",
            coverage(record, 1)["mean_of_seed_coverages"],
        ),
        (
            "levou a cobertura do intervalo de 80%|em h+1 e ",
            coverage(record, 7)["mean_of_seed_coverages"],
        ),
        (
            "produziu coberturas de ",
            coverage("nexcp_fixed_geometric_weights_v1", 1)["mean_of_seed_coverages"],
        ),
        ("não rejeitou a calibração do par (p = ", lr_uc[1]),
        ("não rejeitou a calibração do par|em h+1; p = ", lr_uc[7]),
    ]


def test_prose_numbers(tex: str, judged: dict[str, Any]) -> None:
    """Prefixo `âncora|trecho` procura o trecho só depois da âncora (trecho repetido no texto)."""
    text = normalize(tex.replace("\n", " ")).replace("\\%", "%")
    for spec, value in _prose(judged):
        anchor, _, prefix = spec.rpartition("|")
        start = text.find(anchor) if anchor else 0
        assert start >= 0, f"âncora não encontrada: {anchor!r}"
        at = text.find(prefix, start)
        assert at >= 0, f"trecho não encontrado: {prefix!r}"
        token = text[at + len(prefix) :].split(" ", 1)[0].rstrip(").,;%")
        _check(token, value, f"prosa {prefix!r}")


def test_common_sample_size(tex: str, judged: dict[str, Any]) -> None:
    for horizon, shown in ((1, "1.511"), (7, "1.505")):
        assert _h1(judged, horizon)["common_points"] == parse_number(shown)[0]
        assert f"n = {shown}" in normalize(tex), f"n de h+{horizon} ausente do texto"


def _var_rows(judged: Mapping[str, Any], model: str, horizon: int) -> Rows:
    """Backtest do VaR de 98% (cauda inferior 0,02) na amostra comum, sem degenerados."""
    return [
        row
        for row in judged["calibration_table"]
        if row["model"] == model
        and row["horizon"] == horizon
        and row["sample"] == "common"
        and row["kind"] == "lower_tail"
        and row["var_level"] == _VAR_LEVEL
        and row["band_level"] == _VAR_BAND
        and row["dgt_offset"] is None
        and not row["includes_degenerate"]
    ]


def _check_p(cell: str, value: float, where: str) -> None:
    if cell.startswith("<"):
        shown, _ = parse_number(cell.removeprefix("<"))
        assert value < shown, f"{where}: texto {cell!r}, gravado {value!r}"
    else:
        _check(cell, value, where)


def test_var_table(tex: str, judged: dict[str, Any]) -> None:
    for row in table_rows(tex, "tab:var"):
        if row[0] not in _MODELS:
            continue
        model = _MODELS[row[0]]
        for i, horizon in enumerate(_HORIZONS):
            rows = _var_rows(judged, model, horizon)
            rates = [r["n_violations"] / r["n_observed"] for r in rows]
            where = f"VaR {model} h+{horizon}"
            if model == _TFT:
                assert len(rows) == _N_SEEDS, f"{where}: {len(rows)} seeds"
                head, interval = row[1 + 2 * i].split(" ", 1)
                _check(head, mean(rates), f"{where} média")
                (low, low_d), (high, high_d) = parse_interval(interval)
                assert consistent(low, low_d, min(rates)), f"{where} mínimo"
                assert consistent(high, high_d, max(rates)), f"{where} máximo"
                rejecting = sum(r["kupiec_pof_p_value"] < _ALPHA for r in rows)
                assert row[2 + 2 * i] == f"{rejecting} de {_N_SEEDS}", f"{where} rejeições"
            else:
                assert len(rows) == 1, f"{where}: {len(rows)} rows"
                _check(row[1 + 2 * i], rates[0], f"{where} taxa")
                _check_p(row[2 + 2 * i], rows[0]["kupiec_pof_p_value"], f"{where} Kupiec")


def test_winkler_prose(tex: str, judged: dict[str, Any]) -> None:
    def score(model: str, horizon: int) -> float:
        return mean(
            float(value)
            for value in (
                row["value"]
                for row in judged["metrics_by_run"]
                if row["model"] == model
                and row["horizon"] == horizon
                and row["sample"] == "common"
                and row["metric"] == "interval_score"
                and row["level_low"] == _WINKLER_LOW
            )
        )

    text = normalize(tex.replace("\n", " ")).replace("\\%", "%")
    start = text.find("O interval score de Winkler")
    assert start >= 0, "parágrafo do Winkler ausente"
    claims = (
        ("ordena os modelos da mesma forma em h+1: ", "baseline_ewma_vol", 1),
        ("para o EWMA-vol, ", "gbm_quantile", 1),
        ("para o GBM, ", "baseline_historical_quantiles", 1),
        ("para os quantis empíricos, ", _TFT, 1),
        ("na média das sementes, e ", "baseline_ar1", 1),
        ("exceto que o TFT (", _TFT, 7),
        ("fica à frente dos quantis empíricos (", "baseline_historical_quantiles", 7),
    )
    for prefix, model, horizon in claims:
        at = text.find(prefix, start)
        assert at >= 0, f"trecho não encontrado: {prefix!r}"
        token = text[at + len(prefix) :].split(" ", 1)[0].rstrip(").,;%")
        _check(token, score(model, horizon), f"Winkler {model} h+{horizon}")
