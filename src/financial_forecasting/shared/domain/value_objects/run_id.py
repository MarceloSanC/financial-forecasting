"""Value object RunId — identidade determinística composta de um run.

Frozen, domínio puro (stdlib-only). O valor é uma string hex sha256 sobre o
JSON canônico de 9 campos que, juntos, identificam univocamente um run:
`{asset, feature_set_hash, trial_number, fold, seed, model_version,
config_signature, split_signature, pipeline_version}`. Replica
`compute_run_id` do repo antigo (analytics_store_schema.py:101-124). Variar
QUALQUER um dos 9 campos (inclusive `None -> valor`) muda o `run_id` (I1).

Os opcionais `trial_number/fold/seed` entram EXPLICITAMENTE no payload e
mapeiam para `null` via JSON (`None -> null`); nunca são omitidos, logo
participam da chave de identidade (invariante I7). O `feature_set_hash` chega
pré-calculado como string (via `hasher.hash_text("|".join(features_ordered))`
no chamador — concept D5); não é um VO próprio. O hash é delegado ao port
`Hasher` injetado na factory; o domínio não importa o port em runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from financial_forecasting.shared.application.ports.out.hasher import Hasher


@dataclass(frozen=True)
class RunId:
    """Identidade sha256 composta de 9 campos de um run.

    Attributes:
        value: string hex sha256 do JSON canônico dos 9 campos.
    """

    value: str

    @classmethod
    def compute(  # noqa: PLR0913 — a identidade do run é composta de 9 campos
        # fixos (concept §4 / old analytics_store_schema.py:101-124); a
        # assinatura explícita keyword-only É o contrato de identidade, não
        # acidente — colapsar em dict perderia type safety e o significado.
        cls,
        *,
        hasher: Hasher,
        asset: str,
        feature_set_hash: str,
        trial_number: int | None,
        fold: str | None,
        seed: int | None,
        model_version: str,
        config_signature: str,
        split_signature: str,
        pipeline_version: str,
    ) -> RunId:
        """Monta o payload de 9 campos e delega o hash ao port.

        Os opcionais `trial_number/fold/seed` entram explicitamente (mesmo
        quando `None`, viram `null` e participam da chave — I7).
        """
        payload: dict[str, object | None] = {
            "asset": asset,
            "feature_set_hash": feature_set_hash,
            "trial_number": trial_number,
            "fold": fold,
            "seed": seed,
            "model_version": model_version,
            "config_signature": config_signature,
            "split_signature": split_signature,
            "pipeline_version": pipeline_version,
        }
        return cls(value=hasher.hash_mapping(payload))
