"""Arquivo do cohort confirmatório: leitura (`parse`) e escrita (`dump`) do TOML.

ATENÇÃO — `in` é keyword do Python: este módulo não é importável por
`from ...adapters.in.cli import ...`. Quem o usa o carrega com
`importlib.import_module` (o `cli.py` da raiz e os testes) — LAYOUT §8.

Borda do slice (concept D1): o TOML de `config/cohorts/<nome>.toml` vira
`CohortSpec` aqui, e só aqui. O schema é FECHADO: chave desconhecida, chave
obrigatória ausente, tipo errado ou valor que o DTO recusa (seed repetida,
revisão negativa, …) erguem `CohortFileError` nomeando o campo pelo caminho
pontuado (`geometry.n_folds`, `baselines[2].window`). TOML não tem nulo: campo
opcional ausente é `None` — os campos de congelamento (`tft_params`,
`gbm_params`, `provenance`, `dataset_fingerprint`) e `sweep.n_trials` só
aparecem no arquivo depois de decididos.

`dump` escreve o mesmo schema (tabelas e escalares) sem dependência nova
(technical §1: `tomli-w`/`tomlkit` descartados para um schema fechado); a ida e
volta `parse(dump(spec)) == spec` é o teste que o valida.
"""

from __future__ import annotations

import json
import math
import tomllib
import types
import typing
from dataclasses import MISSING, fields
from typing import TYPE_CHECKING, Any, cast

from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepPlan,
    SweepProvenance,
)
from financial_forecasting.features.modeling.application.ports.out.hyperparameter_search import (
    SearchDimension,
)
from financial_forecasting.features.modeling.application.ports.out.quantile_model_trainer import (
    GbmTrainingParams,
)
from financial_forecasting.features.modeling.application.ports.out.tft_trainer import (
    TftTrainingParams,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BaselineSpec,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path


# Chaves escalares do topo, na ordem em que `dump` as escreve.
_TOP_SCALARS = (
    "name",
    "revision",
    "asset_id",
    "feature_set_name",
    "feature_set_hash",
    "pipeline_version",
    "horizons",
    "quantile_levels",
    "device",
    "seeds",
    "dataset_fingerprint",
)
_TOP_TABLES = ("geometry", "sweep", "baselines", "tft_params", "gbm_params", "provenance")
_SWEEP_KEYS = (
    "n_trials",
    "sampler_seed",
    "tft_base_params",
    "gbm_base_params",
    "tft_space",
    "gbm_space",
)


class CohortFileError(ValueError):
    """Arquivo do cohort inválido — a mensagem nomeia o campo (concept §6)."""


# -- leitura -------------------------------------------------------------------------


def parse(text: str) -> CohortSpec:
    """TOML → `CohortSpec`; qualquer defeito vira `CohortFileError` com o campo."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise CohortFileError(f"cohort file is not valid TOML: {exc}") from exc
    _reject_unknown(raw, (*_TOP_SCALARS, *_TOP_TABLES), path="")
    geometry = _dataclass_from(CohortGeometry, _table(raw, "geometry", ""), "geometry")
    sweep_raw = _table(raw, "sweep", "")
    _reject_unknown(sweep_raw, _SWEEP_KEYS, path="sweep")
    sweep = _build(
        "sweep",
        lambda: SweepPlan(
            tft_space=_space(sweep_raw, "tft_space"),
            tft_base_params=_dataclass_from(
                TftTrainingParams,
                _table(sweep_raw, "tft_base_params", "sweep"),
                "sweep.tft_base_params",
            ),
            gbm_space=_space(sweep_raw, "gbm_space"),
            gbm_base_params=_dataclass_from(
                GbmTrainingParams,
                _table(sweep_raw, "gbm_base_params", "sweep"),
                "sweep.gbm_base_params",
            ),
            n_trials=_optional(sweep_raw, "n_trials", int, "sweep"),
            sampler_seed=_required(sweep_raw, "sampler_seed", int, "sweep"),
        ),
    )
    baselines = _array_of_tables(raw, "baselines", "")
    baseline_specs = tuple(
        _dataclass_from(BaselineSpec, table, f"baselines[{i}]") for i, table in enumerate(baselines)
    )
    tft_params = _optional_dataclass(raw, "tft_params", TftTrainingParams)
    gbm_params = _optional_dataclass(raw, "gbm_params", GbmTrainingParams)
    provenance = _optional_dataclass(raw, "provenance", SweepProvenance)
    return _build(
        "cohort",
        lambda: CohortSpec(
            name=_required(raw, "name", str, ""),
            revision=_required(raw, "revision", int, ""),
            asset_id=_required(raw, "asset_id", str, ""),
            feature_set_name=_required(raw, "feature_set_name", str, ""),
            feature_set_hash=_required(raw, "feature_set_hash", str, ""),
            pipeline_version=_required(raw, "pipeline_version", str, ""),
            horizons=_array(raw, "horizons", int),
            quantile_levels=_array(raw, "quantile_levels", float),
            geometry=geometry,
            device=_required(raw, "device", str, ""),
            seeds=_array(raw, "seeds", int),
            sweep=sweep,
            tft_params=tft_params,
            gbm_params=gbm_params,
            baseline_specs=baseline_specs,
            provenance=provenance,
            dataset_fingerprint=_optional(raw, "dataset_fingerprint", str, ""),
        ),
    )


def load(path: Path) -> CohortSpec:
    """Lê e parseia o arquivo; o caminho entra na mensagem de erro."""
    try:
        return parse(path.read_text(encoding="utf-8"))
    except CohortFileError as exc:
        raise CohortFileError(f"{path}: {exc}") from exc


def _dotted(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _reject_unknown(table: Mapping[str, object], allowed: Iterable[str], *, path: str) -> None:
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        where = f"in [{path}]" if path else "at the top level"
        raise CohortFileError(f"unknown field(s) {unknown} {where}")


def _coerce[T](value: object, expected: type[T], field: str) -> T:
    """Aceita o tipo pedido; `bool` nunca passa por inteiro e inteiro passa por float."""
    if expected is float and isinstance(value, int) and not isinstance(value, bool):
        return cast("T", float(value))
    if isinstance(value, expected) and not (expected is int and isinstance(value, bool)):
        return value
    raise CohortFileError(
        f"field {field!r} must be {expected.__name__}; got {type(value).__name__} {value!r}"
    )


def _required[T](table: Mapping[str, object], key: str, expected: type[T], path: str) -> T:
    field = _dotted(path, key)
    if key not in table:
        raise CohortFileError(f"missing required field {field!r}")
    return _coerce(table[key], expected, field)


def _optional[T](table: Mapping[str, object], key: str, expected: type[T], path: str) -> T | None:
    if key not in table:
        return None
    return _coerce(table[key], expected, _dotted(path, key))


def _array[T](table: Mapping[str, object], key: str, expected: type[T]) -> tuple[T, ...]:
    value = _required(table, key, list, "")
    return tuple(_coerce(item, expected, f"{key}[{i}]") for i, item in enumerate(value))


def _table(table: Mapping[str, object], key: str, path: str) -> dict[str, object]:
    return cast("dict[str, object]", _required(table, key, dict, path))


def _array_of_tables(table: Mapping[str, object], key: str, path: str) -> list[dict[str, object]]:
    items = _required(table, key, list, path)
    field = _dotted(path, key)
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise CohortFileError(f"field '{field}[{i}]' must be a table")
    return cast("list[dict[str, object]]", items)


def _space(sweep_raw: Mapping[str, object], key: str) -> tuple[SearchDimension, ...]:
    tables = _array_of_tables(sweep_raw, key, "sweep")
    return tuple(
        _dataclass_from(SearchDimension, table, f"sweep.{key}[{i}]")
        for i, table in enumerate(tables)
    )


def _optional_dataclass[T](raw: Mapping[str, object], key: str, cls: type[T]) -> T | None:
    if key not in raw:
        return None
    return _dataclass_from(cls, _table(raw, key, ""), key)


def _field_type(annotation: object) -> type:
    """`int`, `float`, `str`, `bool` ou `X | None` (o `None` vem da ausência)."""
    if isinstance(annotation, types.UnionType):
        members = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
        (only,) = members
        return cast("type", only)
    return cast("type", annotation)


def _dataclass_from[T](cls: type[T], table: Mapping[str, object], path: str) -> T:
    """Monta um dataclass de escalares: chaves conferidas, tipos coeridos, erro nomeado."""
    declared = {f.name: f for f in fields(cast("Any", cls))}
    _reject_unknown(table, declared, path=path)
    hints = typing.get_type_hints(cls)
    kwargs: dict[str, object] = {}
    for name, spec in declared.items():
        if name not in table:
            if spec.default is MISSING and spec.default_factory is MISSING:
                raise CohortFileError(f"missing required field {_dotted(path, name)!r}")
            continue
        kwargs[name] = _coerce(table[name], _field_type(hints[name]), _dotted(path, name))
    return _build(path, lambda: cls(**kwargs))


def _build[T](path: str, factory: typing.Callable[[], T]) -> T:
    """Erro de validação do DTO/VO vira `CohortFileError` com o contexto."""
    try:
        return factory()
    except CohortFileError:
        raise
    except (ValueError, TypeError) as exc:
        raise CohortFileError(f"invalid [{path}]: {exc}") from exc


# -- escrita --------------------------------------------------------------------------


def dump(spec: CohortSpec) -> str:
    """`CohortSpec` → TOML do mesmo schema; `None` é omitido (TOML não tem nulo)."""
    lines: list[str] = []
    top: dict[str, object] = {
        "name": spec.name,
        "revision": spec.revision,
        "asset_id": spec.asset_id,
        "feature_set_name": spec.feature_set_name,
        "feature_set_hash": spec.feature_set_hash,
        "pipeline_version": spec.pipeline_version,
        "horizons": list(spec.horizons),
        "quantile_levels": list(spec.quantile_levels),
        "device": spec.device,
        "seeds": list(spec.seeds),
        "dataset_fingerprint": spec.dataset_fingerprint,
    }
    _emit_pairs(lines, top)
    _emit_table(lines, "geometry", _scalars(spec.geometry))
    sweep = spec.sweep
    _emit_table(lines, "sweep", {"n_trials": sweep.n_trials, "sampler_seed": sweep.sampler_seed})
    _emit_table(lines, "sweep.tft_base_params", _scalars(sweep.tft_base_params))
    _emit_table(lines, "sweep.gbm_base_params", _scalars(sweep.gbm_base_params))
    for dimension in sweep.tft_space:
        _emit_table(lines, "sweep.tft_space", _scalars(dimension), array=True)
    for dimension in sweep.gbm_space:
        _emit_table(lines, "sweep.gbm_space", _scalars(dimension), array=True)
    for baseline in spec.baseline_specs:
        _emit_table(lines, "baselines", _scalars(baseline), array=True)
    for key in ("tft_params", "gbm_params", "provenance"):
        value = getattr(spec, key)
        if value is not None:
            _emit_table(lines, key, _scalars(value))
    return "\n".join(lines) + "\n"


def _scalars(obj: object) -> dict[str, object]:
    return {f.name: getattr(obj, f.name) for f in fields(cast("Any", obj))}


def _emit_table(
    lines: list[str], name: str, pairs: Mapping[str, object], *, array: bool = False
) -> None:
    lines.append("")
    lines.append(f"[[{name}]]" if array else f"[{name}]")
    _emit_pairs(lines, pairs)


def _emit_pairs(lines: list[str], pairs: Mapping[str, object]) -> None:
    lines.extend(f"{key} = {_literal(value)}" for key, value in pairs.items() if value is not None)


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CohortFileError(f"cannot write non-finite float {value!r} to the cohort file")
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_literal(item) for item in value) + "]"
    raise CohortFileError(f"cannot write {type(value).__name__} to the cohort file")
