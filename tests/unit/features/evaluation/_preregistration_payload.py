"""Fábrica de payload de pré-registro de teste (Stage 6.5, technical §1).

Módulo privado (sem `test_`), usado pelos testes unitários, pelo contrato do
`PreregistrationSource` (Task 06) e pelo e2e (Task 11):

- `valid_payload()` — cópia profunda de um plano sintético completo: os valores do
  r0 (ADRs 6.5.0009 e 6.5.0010), salvo `name = "test_plan"` e cohort/fingerprint
  sintéticos; sem `blinding_statement` (opcional) e sem emenda (r0);
- `to_toml(payload)` — **escritor TOML só de teste** (a stdlib só lê, `tomllib`);
  cobre exatamente o que o esquema usa; `PAYLOAD_TOML = to_toml(valid_payload())`;
- `key_paths(payload)` — caminhos pontuados de **chave**, sem índices;
- `leaf_paths(payload)` — toda folha, com caminho indexado; `leaf_value(payload, path)`;
- `with_leaf(payload, path, value)` e `without_key(payload, key_path)` — cópias
  profundas com uma folha trocada / uma chave removida;
- `FloatRefusingHasher` — dublê do `Hasher` que recusa float (prova que o
  `PreregistrationHash` codifica todo float antes de delegar). Fora de
  `tests/fakes/` e sem prefixo `Fake`/`InMemory` de propósito: o `Hasher` não tem
  fake por desenho (#70) e o `check_port_coverage` o tomaria por um.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256

TEST_COHORT_HASH = "0123456789abcdef" * 4
TEST_FINGERPRINT = "fedcba9876543210" * 4

_RULES: dict[str, object] = {
    "primary_metric": "mean_pinball_grid",
    "secondary_roles": "profile_only",
    "exclusions": "none",
    "seed_aggregation": "mean_losses_mean_counts",
    "success_criterion": "h1_not_rejected_in_at_least_one_horizon",
    "dm": {
        "direction": "candidate_lower_loss_one_sided",
        "kernel_lag": "rectangular_lag_h_minus_1",
        "small_sample": "hln_student_t_T_minus_1",
        "negative_variance_fallback": "recompute_with_h_1_and_record",
    },
    "mcs": {"statistic": "R", "block_rule": "max_h_ceil_max_bsb"},
    "h1_gate": {"form": "per_tail_wilson_model_full_masked_seed_mean_v1"},
    "verdict": {"form": "h1_gate_then_h2_tree_v1"},
}

_BASELINES = (
    "baseline_zero_return",
    "baseline_historical_mean",
    "baseline_ar1",
    "baseline_ewma_vol",
    "baseline_historical_quantiles",
)

_PAYLOAD: dict[str, object] = {
    "name": "test_plan",
    "revision": 0,
    "asset": "AAPL",
    "horizons": [1, 7],
    "quantile_levels": [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98],
    "candidate": "tft_quantile",
    "cohort": {"cohort_id": "test_cohort-r0-0123456789ab", "cohort_hash": TEST_COHORT_HASH},
    "realized": {
        "source": "training_grid_target_return",
        "dataset_fingerprint": TEST_FINGERPRINT,
    },
    "horizons_not_evaluated": [{"horizon": 30, "reason": "not in the cohort"}],
    "comparators": {
        "naive": ["baseline_zero_return", "baseline_historical_mean"],
        "strong_statistical": [
            "baseline_ar1",
            "baseline_ewma_vol",
            "baseline_historical_quantiles",
        ],
        "ml": ["gbm_quantile"],
    },
    "seeds": {
        "tft_quantile": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "gbm_quantile": [0],
        **dict.fromkeys(_BASELINES, "seedless"),
    },
    "window_deficits": {"tft_quantile": 0, "gbm_quantile": 0, **dict.fromkeys(_BASELINES, 0)},
    "rules": _RULES,
    "dm": {
        "alpha": 0.05,
        "primary_estimator": "rectangular",
        "sensitivity_estimators": ["bartlett"],
    },
    "mcs": {
        "alpha": 0.1,
        "reps": 1000,
        "seed": 127,
        "primary_scheme": "stationary",
        "sensitivity_schemes": ["moving_block"],
        "block_sensitivities": ["h", "sqrt_T"],
    },
    "h1_gate": {
        "lower_level": 0.1,
        "upper_level": 0.9,
        "gate_band_level": 0.975,
        "profile_band_level": 0.95,
        "degeneracy_threshold": 0.01,
        "degeneracy_tolerance": 1e-12,
        "sensitivity_alpha": 0.05,
        "power_scenarios": [
            {
                "label": "width_5pp_wide",
                "role": "primary",
                "lower_rate": 0.125,
                "upper_rate": 0.125,
            },
            {
                "label": "width_5pp_narrow",
                "role": "primary",
                "lower_rate": 0.075,
                "upper_rate": 0.075,
            },
            {
                "label": "location_0_2_sigma",
                "role": "primary",
                "lower_rate": 0.06922982732177752,
                "upper_rate": 0.1397259180118744,
            },
            {
                "label": "width_3pp_wide",
                "role": "secondary",
                "lower_rate": 0.115,
                "upper_rate": 0.115,
            },
            {
                "label": "width_3pp_narrow",
                "role": "secondary",
                "lower_rate": 0.085,
                "upper_rate": 0.085,
            },
            {
                "label": "location_0_1_sigma",
                "role": "secondary",
                "lower_rate": 0.08355471719060237,
                "upper_rate": 0.1186918406956069,
            },
        ],
    },
    "backtests": {"min_violations": 2, "monte_carlo": {"draws": 999, "seed": 128}},
    "profiles": {
        "declared": [
            "dm_bartlett",
            "mcs_moving_block",
            "mcs_block_h",
            "mcs_block_sqrt_t",
            "gate_common_sample",
            "gate_lr_uc_three_state",
            "gate_dgt",
            "band_95_isolated",
            "without_gaps_variant",
            "comparators_calibration",
            "dm_effect_ci",
            "dm_fallback_applied",
            "tier_outcomes",
            "lowest_mean_pinball",
            "metrics_descriptors",
            "christoffersen_monte_carlo_h1",
            "dm_per_fold",
            "dm_per_seed",
            "dm_per_tau",
            "dm_differential_stationarity",
            "partial_degeneracy_per_pair",
            "sharpness_diagram",
        ]
    },
}


def valid_payload() -> dict[str, object]:
    """Cópia profunda do plano sintético completo (r0, sem declaração de cegamento)."""
    return copy.deepcopy(_PAYLOAD)


# --- escritor TOML só de teste --------------------------------------------------------

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_ESCAPES = {'"': '\\"', "\\": "\\\\", "\n": "\\n", "\t": "\\t", "\r": "\\r"}


def _key(key: str) -> str:
    return key if _BARE_KEY.fullmatch(key) else _string(key)


def _string(text: str) -> str:
    out: list[str] = []
    for char in text:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:  # noqa: PLR2004 — faixas de controle
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_scalar(item) for item in value) + "]"
    raise TypeError(f"to_toml does not write {type(value).__name__}: {value!r}")


def _is_table_array(value: object) -> bool:
    return (
        isinstance(value, list | tuple)
        and bool(value)
        and all(isinstance(item, Mapping) for item in value)
    )


def _write_table(lines: list[str], table: Mapping[str, object], path: tuple[str, ...]) -> None:
    subtables = [(k, v) for k, v in table.items() if isinstance(v, Mapping)]
    arrays = [(k, v) for k, v in table.items() if _is_table_array(v)]
    for key, value in table.items():
        if not isinstance(value, Mapping) and not _is_table_array(value):
            lines.append(f"{_key(key)} = {_scalar(value)}")
    for key, value in subtables:
        assert isinstance(value, Mapping)
        header = ".".join(_key(part) for part in (*path, key))
        lines.extend(["", f"[{header}]"])
        _write_table(lines, value, (*path, key))
    for key, value in arrays:
        assert isinstance(value, list | tuple)
        header = ".".join(_key(part) for part in (*path, key))
        for item in value:
            lines.extend(["", f"[[{header}]]"])
            _write_table(lines, item, (*path, key))


def to_toml(payload: Mapping[str, object]) -> str:
    """Texto TOML do payload (chaves escalares antes das tabelas)."""
    lines: list[str] = []
    _write_table(lines, payload, ())
    return "\n".join(lines) + "\n"


PAYLOAD_TOML = to_toml(valid_payload())


# --- caminhos ------------------------------------------------------------------------


def key_paths(payload: Mapping[str, object]) -> list[str]:
    """Caminhos pontuados de toda chave (sem índices; tabelas de listas pelo nome)."""
    found: list[str] = []

    def walk(table: Mapping[str, object], prefix: str) -> None:
        for key, value in table.items():
            path = f"{prefix}{key}"
            if path not in found:
                found.append(path)
            if isinstance(value, Mapping):
                walk(value, f"{path}.")
            elif _is_table_array(value):
                assert isinstance(value, list | tuple)
                for item in value:
                    walk(item, f"{path}.")

    walk(payload, "")
    return found


def leaf_paths(payload: Mapping[str, object]) -> list[str]:
    """Toda folha com caminho indexado (`"dm.alpha"`, `"horizons[1]"`), ordenados."""
    found: list[str] = []

    def walk(value: object, path: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                walk(item, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list | tuple):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        else:
            found.append(path)

    walk(payload, "")
    return sorted(found)


_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _tokens(path: str) -> list[str | int]:
    return [int(index) if index else name for name, index in _TOKEN.findall(path)]


def leaf_value(payload: Mapping[str, object], path: str) -> object:
    """O valor da folha de `path` (caminho indexado)."""
    value: object = payload
    for token in _tokens(path):
        value = value[token]  # type: ignore[index]
    return value


def with_leaf(payload: Mapping[str, object], path: str, value: object) -> dict[str, object]:
    """Cópia profunda com a folha de `path` (caminho indexado) trocada por `value`."""
    result = copy.deepcopy(dict(payload))
    *parents, last = _tokens(path)
    target: object = result
    for token in parents:
        target = target[token]  # type: ignore[index]
    target[last] = value  # type: ignore[index]
    return result


def without_key(payload: Mapping[str, object], key_path: str) -> dict[str, object]:
    """Cópia profunda sem a chave `key_path` (em lista de tabelas, no 1º elemento)."""
    result = copy.deepcopy(dict(payload))
    *parents, last = key_path.split(".")
    target: object = result
    for name in parents:
        target = target[name]  # type: ignore[index]
        if isinstance(target, list):
            target = target[0]
    del target[last]  # type: ignore[attr-defined]
    return result


# --- dublê do Hasher -----------------------------------------------------------------


def _refuse_floats(value: object) -> None:
    if isinstance(value, float):
        raise AssertionError(f"the hasher received a float: {value!r}")
    if isinstance(value, Mapping):
        for item in value.values():
            _refuse_floats(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _refuse_floats(item)


class FloatRefusingHasher:
    """Dublê stdlib do `Hasher`: recusa float; sha256 do `json.dumps` ordenado."""

    def hash_mapping(self, payload: Mapping[str, object]) -> str:
        """sha256 hex do JSON ordenado; `AssertionError` se achar `float`."""
        _refuse_floats(payload)
        return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def hash_text(self, text: str) -> str:
        """sha256 hex do texto."""
        return sha256(text.encode("utf-8")).hexdigest()
