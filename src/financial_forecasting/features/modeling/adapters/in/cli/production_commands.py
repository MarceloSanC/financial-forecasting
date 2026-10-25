"""Comandos da rodada de produção: spec da rodada e ponteiro servido (Stage 8.4).

ATENÇÃO — `in` é keyword do Python: este módulo é carregado por
`importlib.import_module` (o `cli.py` da raiz e os testes) — LAYOUT §8.

O `production-round` do `cli.py` encadeia a rodada (ADR 8.4.0002); aqui ficam as
peças do slice `modeling` que ele usa:

- `parse_round_name` — o nome da rodada é uma data ISO, com sufixo `.N` opcional
  para refazer o dia (`2026-10-25`, `2026-10-25.1`). Ordena as rodadas e fecha os
  nomes de diretório perigosos (`.`, `..`) que o `validate_path_identifier` aceita.
- `prepare_round_spec` — deriva do modelo de produção versionado o spec congelado
  da rodada (`CohortSpec.production_round`) com a impressão digital do grid que a
  rodada materializou (a MESMA leitura e a MESMA fórmula do `freeze` e do runner),
  confere a geometria e a ida e volta do arquivo e o grava. Arquivo existente igual
  é mantido; diferente para a rodada (ADR 8.4.0001 item 3: derivado, nunca editado).
- `publish_serving_pointer` — troca `<raiz de produção>/serving.env` (`DATA_ROOT` e
  `SERVING_COHORT_FILE`, caminhos absolutos) por `os.replace` a partir de um
  temporário de nome único no mesmo diretório, e só se não há ponteiro, se ele já
  aponta para esta rodada ou se esta rodada é posterior à apontada (monotônico).

Nada aqui avalia: o módulo não importa `features.evaluation` (concept 8.4 I8).
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from financial_forecasting.features.modeling.application.use_cases.run_confirmatory_cohort import (
    load_training_grid,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
)
from financial_forecasting.shared.application.exceptions import ApplicationError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.application.ports.out.medallion_store import (
        MedallionStore,
    )

SERVING_POINTER = "serving.env"
DATA_ROOT_KEY = "DATA_ROOT"
SERVING_COHORT_FILE_KEY = "SERVING_COHORT_FILE"
_ROUND_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\.([1-9]\d*))?")


class ProductionRoundError(ApplicationError):
    """Pré-condição da rodada de produção não atendida (mensagem acionável)."""


@dataclass(frozen=True)
class ProductionCommandDeps:
    """O que os comandos de produção recebem do composition root (via `cli.py`)."""

    store: MedallionStore
    hasher: Hasher
    modeling_columns: Sequence[str]
    load_spec: Callable[[Path], CohortSpec]
    parse_spec: Callable[[str], CohortSpec]
    dump_spec: Callable[[CohortSpec], str]


def parse_round_name(text: str) -> tuple[date, int]:
    """`AAAA-MM-DD` → `(data, 0)`; `AAAA-MM-DD.N` (N ≥ 1) → `(data, N)`; o resto → erro."""
    match = _ROUND_NAME.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        raise ValueError(f"round name must be YYYY-MM-DD or YYYY-MM-DD.N (N >= 1); got {text!r}")
    try:
        day = date.fromisoformat(match.group(1))
    except ValueError as exc:
        raise ValueError(f"round name is not a valid date: {text!r}") from exc
    return day, int(match.group(2) or 0)


# -- spec da rodada -------------------------------------------------------------------


def prepare_round_spec(
    deps: ProductionCommandDeps,
    template_path: Path,
    round_spec_path: Path,
    *,
    out: TextIO,
) -> CohortSpec:
    """Deriva, confere e grava o spec congelado da rodada; devolve o spec.

    Lê o grid materializado na raiz da rodada (o `store` do processo da rodada) e
    calcula a impressão digital como o `freeze` e o runner. Arquivo já existente:
    igual ao derivado → mantido; diferente → `ProductionRoundError`, intacto.
    """
    model = deps.load_spec(template_path)
    grid = load_training_grid(
        store=deps.store, asset_id=model.asset_id, columns=deps.modeling_columns
    )
    fingerprint = grid_fingerprint(grid, hasher=deps.hasher, asset_id=model.asset_id)
    spec = model.production_round(fingerprint)
    spec.geometry.fits(n_sessions=len(grid.timestamps), max_horizon=spec.max_horizon)
    text = deps.dump_spec(spec)
    if deps.parse_spec(text) != spec:
        raise ProductionRoundError(
            "the round spec does not survive a write/read round trip — not written"
        )
    if round_spec_path.exists():
        if round_spec_path.read_text(encoding="utf-8") != text:
            raise ProductionRoundError(
                f"{round_spec_path} differs from the spec derived from {template_path} "
                "and the round's data — a round spec is derived, never edited; "
                "start a new round"
            )
        out.write(f"round spec kept: {round_spec_path} (dataset {fingerprint[:12]})\n")
        return spec
    _replace_atomically(round_spec_path, text)
    out.write(f"round spec written: {round_spec_path} (dataset {fingerprint[:12]})\n")
    return spec


# -- ponteiro servido -----------------------------------------------------------------


def publish_serving_pointer(
    production_root: Path,
    round_name: str,
    round_root: Path,
    round_spec_path: Path,
    *,
    out: TextIO,
) -> bool:
    """Troca o `serving.env` para esta rodada se ela não for mais antiga que a apontada.

    Devolve `True` se publicou (ou regravou o mesmo ponteiro) e `False` se a rodada é
    anterior à apontada (escreve `not published: …`). Ponteiro existente sem
    `DATA_ROOT` legível como rodada → `ProductionRoundError`, intacto.
    """
    pointer = production_root / SERVING_POINTER
    this_round = parse_round_name(round_name)
    if pointer.exists():
        current = _pointed_round(pointer)
        if current != round_name and parse_round_name(current) > this_round:
            out.write(f"not published: round {round_name} is older than the published {current}\n")
            return False
    text = (
        f"{DATA_ROOT_KEY}={round_root.resolve().as_posix()}\n"
        f"{SERVING_COHORT_FILE_KEY}={round_spec_path.resolve().as_posix()}\n"
    )
    _replace_atomically(pointer, text)
    return True


def _pointed_round(pointer: Path) -> str:
    """O nome da rodada para a qual o ponteiro aponta (último segmento do `DATA_ROOT`)."""
    for line in pointer.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == DATA_ROOT_KEY:
            name = Path(value.strip()).name
            try:
                parse_round_name(name)
            except ValueError as exc:
                raise ProductionRoundError(
                    f"{pointer} points to {value.strip()!r}, which is not a round — "
                    "fix the pointer by hand before publishing"
                ) from exc
            return name
    raise ProductionRoundError(f"{pointer} has no {DATA_ROOT_KEY} line — fix it by hand")


def _replace_atomically(path: Path, text: str) -> None:
    """Temporário de nome único no mesmo diretório + `os.replace` (ADR 8.4.0002 item 2)."""
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
