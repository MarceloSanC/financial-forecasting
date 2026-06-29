"""Mapper `RunRecord` → row de `dim_run` (write-time concern do adapter).

O VO `RunRecord` (domínio, 4.1) NÃO carrega `created_at_utc`, mas o schema
`pandera` de `dim_run` exige a coluna (`nullable=False`). Este mapper, que vive no
**adapter** (não no domínio — manter o VO puro, concept 4.2 I5/D3/OBS-1), traduz o
VO numa `Row` dict-like e injeta `created_at_utc` via um `Clock` injetado
(`clock.now().isoformat()`, ISO 8601 UTC `string`). NUNCA `datetime.now()`
hardcoded — determinismo testável via `FakeClock`.

Mantém-se stdlib-only (`dataclasses.asdict`): o mapper não toca pandas/pandera (a
validação `pandera` acontece no `write` do adapter, sobre o DataFrame montado a
partir das rows). ADR docs/adr/4_2_0002-created-at-utc-via-injected-clock.md.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from financial_forecasting.features.analytics_store.domain.value_objects.run_record import (
        RunRecord,
    )
    from financial_forecasting.shared.application.ports.out.clock import Clock

Row = dict[str, object]


def run_record_to_row(record: RunRecord, *, clock: Clock) -> Row:
    """Converte um `RunRecord` numa row de `dim_run`, com `created_at_utc` write-time.

    Os campos do VO mapeiam 1:1 para as colunas do schema `dim_run`; a única
    coluna extra (`created_at_utc`, `nullable=False`) é preenchida aqui via
    `clock.now()` em ISO 8601 UTC. Não recomputa hashes (`config_signature`/
    `split_fingerprint` vêm prontos do VO, produzidos pela Stage 1.4).
    """
    row: Row = dict(asdict(record))
    row["created_at_utc"] = clock.now().isoformat()
    return row
