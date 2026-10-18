"""VO `RunRecord` — metadados de uma execução (linha de `dim_run`).

Value object de domínio **frozen, stdlib-only** (concept 4.1 §4 / I1). Identidade
pela PK lógica de `dim_run` (`run_id`); a igualdade do dataclass frozen é por valor
(I9). Os campos `config_signature`/`split_fingerprint` guardam o hash hex (`str`)
produzido pela Stage 1.4 — NUNCA recomputados aqui (I10), mas a FORMA é checada na
construção: `run_id`, `config_signature` e `split_fingerprint` são sha256 hex (regra
única `validate_sha256_hex`) e `schema_version` é inteiro >= 1 (issue #160).

O mapeamento para `DataFrame` vive no adapter (`adapters/out/parquet/schemas`),
nunca no domínio: este módulo importa só stdlib e o domínio de `shared`. O gate
`store-no-storage-leak`/`domain-purity` reprova qualquer import de pandas/pandera.
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

_HASH_FIELDS = ("run_id", "config_signature", "split_fingerprint")


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

    def __post_init__(self) -> None:
        for field in _HASH_FIELDS:
            validate_sha256_hex(getattr(self, field), field=field)
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise ValueError(f"schema_version must be an int >= 1, got {self.schema_version!r}")
