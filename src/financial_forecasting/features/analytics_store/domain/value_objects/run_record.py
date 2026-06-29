"""VO `RunRecord` — metadados de uma execução (linha de `dim_run`).

Value object de domínio **frozen, stdlib-only** (concept 4.1 §4 / I1). Identidade
pela PK lógica de `dim_run` (`run_id`); a igualdade do dataclass frozen é por valor
(I9). Os campos `config_signature`/`split_fingerprint` guardam o hash hex (`str`)
produzido pela Stage 1.4 — NUNCA recomputados aqui (I10).

O mapeamento para `DataFrame` vive no adapter (`adapters/out/parquet/schemas`),
nunca no domínio: este módulo importa SÓ stdlib (`dataclasses`). O gate
`store-no-storage-leak`/`domain-purity` reprova qualquer import de pandas/pandera.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunRecord:
    """Metadados de uma execução de treino/avaliação (uma linha de `dim_run`).

    Campos:
        run_id: identidade da execução (hash hex da 1.4) — PK lógica de `dim_run`.
        asset: ticker do ativo (ex.: ``"AAPL"``).
        parent_sweep_id: id do sweep/cohort pai (``None`` quando avulsa).
        feature_set_name: nome do conjunto de features usado.
        config_signature: hash hex (1.4) da configuração de treino.
        split_fingerprint: hash hex (1.4) da partição walk-forward.
        fold: identificador do fold (``None`` quando sem fold).
        seed: semente aleatória (``None`` quando não fixada).
        model_version: versão/rótulo do modelo (ex.: ``"tft_v1"``, ``"baseline_*"``).
        schema_version: versão do schema da tabela `dim_run`.
    """

    run_id: str
    asset: str
    parent_sweep_id: str | None
    feature_set_name: str
    config_signature: str
    split_fingerprint: str
    fold: str | None
    seed: int | None
    model_version: str
    schema_version: int
