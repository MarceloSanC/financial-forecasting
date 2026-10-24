"""`compare_reproduction` — a geração reproduzida contra a julgada, por valor (Stage 8.2).

Função pura, sem I/O (concept 8.2 §4; ADR `8_2_0002` itens 1-3; technical 8.2 §1
"Igualdade de valor" e "Scorecard"):

- **identidade** — `preregistration_ref`, partição, `silver_content.digest` e
  `dataset_fingerprint` dos dois manifestos (I3);
- **digests** — `result_layer_digest` dos dois lados (o dono é
  `dtos/judged_generation.py`) e o esperado do `ATTEMPTS.jsonl`;
- **tabelas** — linhas casadas pela `key` do `GOLD_SCHEMAS`; toda coluna comparada com a
  classe de `REPRODUCTION_CLASSES` (coluna sem classe → `ValueError`, sem fallback por
  tipo); `float` contra `float` pelos bits (`struct.pack(">d", x)`), os demais por `==` **e**
  mesmo tipo (`1` contra `1.0` e `True` contra `1` diferem); chave só de um lado →
  `keys_equal = false` e uma diferença R1;
- **scorecard** — as folhas dos dois `Mapping` JSON, sem `manifest_read.started_at` /
  `manifest_read.finished_at` (as chaves de `RESULT_EXCLUDED_KEYS`).

max |Δ| só entre dois numéricos não-`bool`; NaN ou ±inf num lado com bits diferentes →
`inf`.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from financial_forecasting.features.evaluation.application.dtos.gold_schema import GOLD_SCHEMAS
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    RESULT_EXCLUDED_KEYS,
    result_layer_digest,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldManifest,
    GoldTable,
    Row,
)
from financial_forecasting.features.evaluation.application.dtos.reproduction_comparison import (
    IDENTITY_FIELDS,
    MAX_SCORECARD_PATHS,
    REPRODUCTION_CLASSES,
    ClassComparison,
    IdentityComparison,
    ReproductionClass,
    ReproductionComparison,
    ScorecardComparison,
    TableComparison,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_real_number,
)
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

_MANIFEST_READ = "manifest_read"
_MISSING = object()
"""Marca de valor ausente num lado (coluna, chave ou folha só do outro)."""


def _same(left: object, right: object) -> bool:
    """Mesmo tipo e mesmo valor; `float` pelos bits (distingue `-0.0` e payloads de NaN)."""
    if type(left) is not type(right):
        return False
    if isinstance(left, float):
        assert isinstance(right, float)  # mesmo tipo, acima
        return struct.pack(">d", left) == struct.pack(">d", right)
    return left == right


def _abs_diff(left: float, right: float) -> float:
    """|Δ| entre dois numéricos já sabidos diferentes ou iguais pelos bits."""
    if _same(left, right):
        return 0.0
    if not (math.isfinite(left) and math.isfinite(right)):
        return math.inf
    return float(abs(left - right))


@dataclass
class _Tally:
    """Acumulador mutável de uma classe (local à comparação)."""

    compared: int = 0
    different: int = 0
    numeric: int = 0
    max_abs_diff: float | None = None
    paths: list[str] = field(default_factory=list)

    def add(self, left: object, right: object, *, path: str = "") -> None:
        self.compared += 1
        same = left is not _MISSING and right is not _MISSING and _same(left, right)
        if not same:
            self.different += 1
            if path and len(self.paths) < MAX_SCORECARD_PATHS:
                self.paths.append(path)
        # número não-`bool`: a regra tem dono único (`_finite_number`, issue #167)
        if is_real_number(left) and is_real_number(right):
            self.numeric += 1
            delta = _abs_diff(left, right)
            self.max_abs_diff = (
                delta if self.max_abs_diff is None else max(self.max_abs_diff, delta)
            )

    def as_class(self, reproduction_class: ReproductionClass) -> ClassComparison:
        return ClassComparison(
            reproduction_class=reproduction_class,
            compared=self.compared,
            different=self.different,
            numeric=self.numeric,
            max_abs_diff=self.max_abs_diff,
        )


# --- identidade -------------------------------------------------------------------------


def _identity_of(manifest: GoldManifest) -> dict[str, str]:
    partition = manifest.partition
    return {
        "preregistration_ref": manifest.parameters.preregistration_ref,
        "partition": f"{partition.asset}/{partition.parent_sweep_id}",
        "silver_content.digest": manifest.silver_content.digest,
        "dataset_fingerprint": manifest.dataset_fingerprint.value,
    }


def _identity(judged: GoldManifest, reproduced: GoldManifest) -> tuple[IdentityComparison, ...]:
    left, right = _identity_of(judged), _identity_of(reproduced)
    return tuple(IdentityComparison(name, left[name], right[name]) for name in IDENTITY_FIELDS)


# --- tabelas ----------------------------------------------------------------------------


def _declared_classes(
    name: str, tables: Sequence[GoldTable | None]
) -> Mapping[str, ReproductionClass]:
    """As classes das colunas da tabela; coluna gravada sem classe → `ValueError`."""
    classes = REPRODUCTION_CLASSES.get(name)
    if classes is None:
        raise ValueError(f"table {name!r} has no declared reproduction classes")
    columns = {column for table in tables if table is not None for column in table.columns}
    undeclared = sorted(columns - set(classes))
    if undeclared:
        raise ValueError(f"{name}: columns without a declared reproduction class {undeclared}")
    return classes


def _keyed(table: GoldTable | None, key: tuple[str, ...]) -> dict[tuple[object, ...], Row]:
    if table is None:
        return {}
    return {tuple(row[column] for column in key): row for row in table.rows}


def _compare_table(
    name: str, judged: GoldTable | None, reproduced: GoldTable | None
) -> TableComparison:
    classes = _declared_classes(name, (judged, reproduced))
    key = GOLD_SCHEMAS[name].key  # o mapa de classes só tem tabelas do GOLD_SCHEMAS
    left, right = _keyed(judged, key), _keyed(reproduced, key)
    tallies = {cls: _Tally() for cls in ReproductionClass}
    unmatched = set(left) ^ set(right)
    for _ in unmatched:
        tallies[ReproductionClass.R1].add(_MISSING, _MISSING)
    for row_key in left.keys() & right.keys():
        judged_row, reproduced_row = left[row_key], right[row_key]
        for column in sorted(set(judged_row) | set(reproduced_row)):
            tallies[classes[column]].add(
                judged_row.get(column, _MISSING), reproduced_row.get(column, _MISSING)
            )
    return TableComparison(
        name=name,
        judged_rows=0 if judged is None else len(judged.rows),
        reproduced_rows=0 if reproduced is None else len(reproduced.rows),
        keys_equal=not unmatched,
        classes=tuple(tallies[cls].as_class(cls) for cls in ReproductionClass),
    )


def _tables(judged: GoldGeneration, reproduced: GoldGeneration) -> tuple[TableComparison, ...]:
    names = sorted(set(judged.tables) | set(reproduced.tables))
    return tuple(
        _compare_table(name, judged.tables.get(name), reproduced.tables.get(name)) for name in names
    )


# --- scorecard --------------------------------------------------------------------------


def _join(path: str, step: str) -> str:
    return step if not path else f"{path}{step}" if step.startswith("[") else f"{path}.{step}"


def _leaves(left: object, right: object, path: str) -> Iterator[tuple[str, object, object]]:
    """Pares de folhas (caminho, esquerda, direita); subárvore só de um lado ou de forma
    diferente é uma folha só."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        for key in sorted({str(k) for k in left} | {str(k) for k in right}):
            if path == _MANIFEST_READ and key in RESULT_EXCLUDED_KEYS:
                continue
            yield from _leaves(left.get(key, _MISSING), right.get(key, _MISSING), _join(path, key))
        return
    if isinstance(left, list | tuple) and isinstance(right, list | tuple):
        for index in range(max(len(left), len(right))):
            yield from _leaves(
                left[index] if index < len(left) else _MISSING,
                right[index] if index < len(right) else _MISSING,
                _join(path, f"[{index}]"),
            )
        return
    yield path or "$", left, right


def _scorecard(
    judged: Mapping[str, object], reproduced: Mapping[str, object]
) -> ScorecardComparison:
    if not isinstance(judged, Mapping) or not isinstance(reproduced, Mapping):
        raise ValueError("both scorecards must be Mapping")
    tally = _Tally()
    for path, left, right in _leaves(judged, reproduced, ""):
        tally.add(left, right, path=path)
    return ScorecardComparison(
        leaves=tally.compared,
        different=tally.different,
        numeric=tally.numeric,
        max_abs_diff=tally.max_abs_diff,
        paths=tuple(tally.paths),
    )


def compare_reproduction(
    *,
    judged: GoldGeneration,
    judged_scorecard: Mapping[str, object],
    reproduced: GoldGeneration,
    reproduced_scorecard: Mapping[str, object],
    expected_result_digest: str,
) -> ReproductionComparison:
    """A comparação por classe da geração reproduzida contra a julgada (ADR 8.2.0002).

    Raises:
        ValueError: coluna gravada sem classe em `REPRODUCTION_CLASSES`, tabela fora do
            mapa, scorecard que não é `Mapping` ou `expected_result_digest` fora de
            sha256 hex.
    """
    validate_sha256_hex(expected_result_digest, field="expected_result_digest")
    tables = _tables(judged, reproduced)
    return ReproductionComparison(
        preregistration_ref=judged.manifest.parameters.preregistration_ref,
        partition=judged.manifest.partition,
        identity=_identity(judged.manifest, reproduced.manifest),
        judged_result_digest=result_layer_digest(judged),
        reproduced_result_digest=result_layer_digest(reproduced),
        expected_result_digest=expected_result_digest,
        tables=tables,
        scorecard=_scorecard(judged_scorecard, reproduced_scorecard),
    )
