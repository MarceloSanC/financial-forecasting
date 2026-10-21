"""Arquivo do cohort de ablação: leitura (`load_ablation_cohort`) e escrita (`dump`) do TOML.

ATENÇÃO — `in` é keyword do Python: este módulo é carregado por
`importlib.import_module` (o `cli.py` da raiz, o composition root e os testes) —
LAYOUT §8.

Borda do slice (Stage 7.3; ADR 7.3.0003 item 1): `config/cohorts/aapl_ablation.toml`
vira `AblationCohortSpec` aqui, e só aqui. O schema é FECHADO:

- topo: `name`, `revision`, `feature_set_name`, `device`, `seeds` e `torch_build`
  (ausente no rascunho; TOML não tem nulo);
- `[base]`: `cohort_file`, `cohort_id`, `cohort_hash`;
- `[partition]`: família → lista de features;
- `[configurations.<nome>]`: só `feature_set_hash`. `excluded_family` e
  `model_version` são derivados do nome, nunca declarados.

Qualquer outra chave, inclusive as do procedimento que vêm da base (`tft_params`,
`geometry`, `horizons`, `quantile_levels`, `dataset_fingerprint`,
`pipeline_version` — I4), ergue `AblationFileError` com o caminho pontuado.

Conferências contra a base e a registry (C2, `AblationDeclarationError`): o loader
relê o arquivo da base e chama `check_ablation_declarations` (application,
`run_ablation_cohort`; o executor chama a mesma antes do lock — achado C2-6): hash e
`cohort_id` da base, partição da registry e `feature_set_hash` de cada subconjunto.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.application.dtos.ablation_cohort_spec import (
    ABLATION_CONFIGURATIONS,
    AblationCohortSpec,
    AblationConfiguration,
)
from financial_forecasting.features.modeling.application.use_cases.run_ablation_cohort import (
    check_ablation_declarations,
)
from financial_forecasting.features.modeling.domain.services.loco_identity import TFT_FAMILIES

if TYPE_CHECKING:
    from pathlib import Path

    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

_TOP_SCALARS = ("name", "revision", "feature_set_name", "device", "seeds", "torch_build")
_TOP_TABLES = ("base", "partition", "configurations")
_BASE_KEYS = ("cohort_file", "cohort_id", "cohort_hash")
_CONFIGURATION_KEYS = ("feature_set_hash",)


class AblationFileError(ValueError):
    """Arquivo de ablação malformado: chave desconhecida, ausente ou de tipo errado."""


def _dotted(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _reject_unknown(table: Mapping[str, object], allowed: tuple[str, ...], *, path: str) -> None:
    for key in sorted(set(table) - set(allowed)):
        raise AblationFileError(f"unknown field {_dotted(path, key)!r} in the ablation file")


def _required(table: Mapping[str, object], key: str, path: str) -> object:
    if key not in table:
        raise AblationFileError(f"missing required field {_dotted(path, key)!r}")
    return table[key]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise AblationFileError(f"field {field!r} must be a string, got {value!r}")
    return value


def _int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AblationFileError(f"field {field!r} must be an integer, got {value!r}")
    return value


def _table(raw: Mapping[str, object], key: str, path: str = "") -> Mapping[str, object]:
    value = _required(raw, key, path)
    if not isinstance(value, dict):
        raise AblationFileError(f"field {_dotted(path, key)!r} must be a table")
    return value


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AblationFileError(f"field {field!r} must be a list, got {value!r}")
    return tuple(_text(item, f"{field}[{i}]") for i, item in enumerate(value))


def parse_ablation_cohort(text: str) -> AblationCohortSpec:
    """O spec do texto do arquivo, só pela forma (sem conferir base nem registry)."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise AblationFileError(f"ablation file is not valid TOML: {exc}") from exc
    _reject_unknown(raw, (*_TOP_SCALARS, *_TOP_TABLES), path="")
    base = _table(raw, "base")
    _reject_unknown(base, _BASE_KEYS, path="base")
    partition = _table(raw, "partition")
    _reject_unknown(partition, TFT_FAMILIES, path="partition")
    configurations = _table(raw, "configurations")
    _reject_unknown(configurations, ABLATION_CONFIGURATIONS, path="configurations")
    declared = []
    for name in ABLATION_CONFIGURATIONS:
        table = _table(configurations, name, "configurations")
        path = f"configurations.{name}"
        _reject_unknown(table, _CONFIGURATION_KEYS, path=path)
        fsh = _text(_required(table, "feature_set_hash", path), f"{path}.feature_set_hash")
        declared.append((name, fsh))
    seeds_raw = _required(raw, "seeds", "")
    if not isinstance(seeds_raw, list):
        raise AblationFileError(f"field 'seeds' must be a list, got {seeds_raw!r}")
    torch_build = raw.get("torch_build")
    try:
        return AblationCohortSpec(
            name=_text(_required(raw, "name", ""), "name"),
            revision=_int(_required(raw, "revision", ""), "revision"),
            base_cohort_file=_text(_required(base, "cohort_file", "base"), "base.cohort_file"),
            base_cohort_id=_text(_required(base, "cohort_id", "base"), "base.cohort_id"),
            base_cohort_hash=_text(_required(base, "cohort_hash", "base"), "base.cohort_hash"),
            feature_set_name=_text(_required(raw, "feature_set_name", ""), "feature_set_name"),
            configurations=tuple(
                AblationConfiguration.of(name, feature_set_hash=fsh) for name, fsh in declared
            ),
            family_partition={
                family: _strings(features, f"partition.{family}")
                for family, features in partition.items()
            },
            seeds=tuple(_int(seed, f"seeds[{i}]") for i, seed in enumerate(seeds_raw)),
            device=_text(_required(raw, "device", ""), "device"),
            torch_build=None if torch_build is None else _text(torch_build, "torch_build"),
        )
    except AblationFileError:
        raise
    except ValueError as exc:
        raise AblationFileError(f"invalid ablation file: {exc}") from exc


def load_ablation_cohort(
    path: Path, *, hasher: Hasher, load_base: Callable[[str], CohortSpec]
) -> AblationCohortSpec:
    """Lê o arquivo, relê a base declarada (`load_base(base.cohort_file)`) e confere (C2)."""
    try:
        spec = parse_ablation_cohort(path.read_text(encoding="utf-8"))
    except AblationFileError as exc:
        raise AblationFileError(f"{path}: {exc}") from exc
    check_ablation_declarations(spec, base=load_base(spec.base_cohort_file), hasher=hasher)
    return spec


def _string(text: str) -> str:
    # string básica TOML: o JSON sem `ensure_ascii` escapa aspas, barra e controles
    return json.dumps(text, ensure_ascii=False)


def _strings_array(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(_string(value) for value in values) + "]"


def dump_ablation_cohort(spec: AblationCohortSpec) -> str:
    """O TOML do spec no schema de `parse_ablation_cohort` (ida e volta exata)."""
    lines = [
        f"name = {_string(spec.name)}",
        f"revision = {spec.revision}",
        f"feature_set_name = {_string(spec.feature_set_name)}",
        f"device = {_string(spec.device)}",
        "seeds = [" + ", ".join(str(seed) for seed in spec.seeds) + "]",
    ]
    if spec.torch_build is not None:
        lines.append(f"torch_build = {_string(spec.torch_build)}")
    lines += [
        "",
        "[base]",
        f"cohort_file = {_string(spec.base_cohort_file)}",
        f"cohort_id = {_string(spec.base_cohort_id)}",
        f"cohort_hash = {_string(spec.base_cohort_hash)}",
        "",
        "[partition]",
    ]
    lines += [
        f"{family} = {_strings_array(features)}"
        for family, features in spec.family_partition.items()
    ]
    for configuration in spec.configurations:
        lines += [
            "",
            f"[configurations.{configuration.name}]",
            f"feature_set_hash = {_string(configuration.feature_set_hash)}",
        ]
    return "\n".join(lines) + "\n"
