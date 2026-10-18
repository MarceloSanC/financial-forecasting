"""VO `PredictionRow` — uma linha LONGA de predição out-of-sample (H-1).

Value object de domínio **frozen, stdlib-only** (concept 4.1 §4 / I1 / I5). Materializa
a decisão humana H-1 (ledger, fechada/imutável): a representação de quantis no silver é
LONGA/agnóstica à grade — `quantile_level` é um **campo**, NÃO colunas por quantil
(`quantile_p10/p50/p90` e variantes `_post_guardrail` são PROIBIDAS). A grade densa
~7-9 fica decidida no Step 5, sem migração de schema.

`decision_idx`, `timestamp_utc` e `target_timestamp_utc` são contrato de schema (âncora
ADR-0003 do old, *mechanical > procedural*); a lógica de off-by-one que os preenche é da
Stage 4.3 — aqui o campo apenas existe (I11).

Valida a FORMA na construção (issue #160): `run_id` sha256 hex (regra única
`validate_sha256_hex`), `horizon >= 1`, `decision_idx >= 0`, `quantile_level` em (0, 1)
(entra na PK) e `guardrail_applied` em {0, 1}. Inteiros recusam `bool`.

Importa só stdlib e o domínio de `shared`; o mapeamento para `DataFrame` vive no adapter.
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex


@dataclass(frozen=True)
class PredictionRow:
    """Uma linha LONGA de predição OOS — um nível de quantil por linha (H-1).

    Campos:
        run_id: identidade da execução produtora (hash hex da 1.4).
        split: rótulo do split (ex.: ``"test"``, ``"val"``).
        horizon: horizonte de previsão em dias de pregão (>= 1).
        decision_idx: índice da barra de decisão na grade do dataset (âncora 4.3).
        timestamp_utc: timestamp UTC da barra de decisão (string ISO).
        target_timestamp_utc: timestamp UTC do alvo previsto (string ISO).
        quantile_level: nível do quantil (ex.: ``0.1``, ``0.5``, ``0.9``) — NA PK.
        value_raw: valor previsto bruto para o nível (saída do modelo).
        value_guardrail: valor após guardrail de monotonicidade.
        guardrail_applied: flag ``0/1`` indicando se o guardrail alterou o valor.
    """

    run_id: str
    split: str
    horizon: int
    decision_idx: int
    timestamp_utc: str
    target_timestamp_utc: str
    quantile_level: float
    value_raw: float
    value_guardrail: float
    guardrail_applied: int

    def __post_init__(self) -> None:
        validate_sha256_hex(self.run_id, field="run_id")
        if not _is_int(self.horizon) or self.horizon < 1:
            raise ValueError(f"horizon must be an int >= 1, got {self.horizon!r}")
        if not _is_int(self.decision_idx) or self.decision_idx < 0:
            raise ValueError(f"decision_idx must be an int >= 0, got {self.decision_idx!r}")
        level = self.quantile_level
        if isinstance(level, bool) or not isinstance(level, int | float) or not 0.0 < level < 1.0:
            raise ValueError(f"quantile_level must be in (0, 1), got {level!r}")
        if not _is_int(self.guardrail_applied) or self.guardrail_applied not in (0, 1):
            raise ValueError(f"guardrail_applied must be 0 or 1, got {self.guardrail_applied!r}")


def _is_int(value: object) -> bool:
    """`True` para `int` que não é `bool` (`bool` é subclasse de `int`)."""
    return isinstance(value, int) and not isinstance(value, bool)
