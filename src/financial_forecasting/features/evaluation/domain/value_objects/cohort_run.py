"""VO `CohortRun` — um `dim_run` do cohort avaliado pelo refresh do gold (6.4).

Value object de domínio **frozen, stdlib-only** (concept 6.4 §4 "Domínio"; ADR
`6_4_0004` item 2). Carrega a identidade de um run do cohort (`parent_sweep_id`):
`run_id`, `model` (o `model_version` registrado), `seed`, `fold`, `feature_set_name` e
`config_signature`. As regras entre runs (um `feature_set_name` no cohort, uma
`config_signature` por modelo, run órfão, `model_version` divergente do fato) são do
`SeriesAssembly` e viram achados; aqui só a forma de cada campo, com as mesmas regras
de `seed`/`fold` do `ForecastRecord`.
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    check_non_empty_str,
    check_optional_fold,
    check_optional_seed,
)


@dataclass(frozen=True)
class CohortRun:
    """Um run do cohort (linha do `dim_run`).

    Campos:
        run_id, model, feature_set_name, config_signature: `str` não-vazias.
        seed: `int` não-`bool` ou `None`.
        fold: `str` ou `None`.

    Raises:
        ValueError: campo fora da forma acima, na construção (mensagem nomeia o campo).
    """

    run_id: str
    model: str
    seed: int | None
    fold: str | None
    feature_set_name: str
    config_signature: str

    def __post_init__(self) -> None:
        """Forma de cada campo."""
        for field in ("run_id", "model", "feature_set_name", "config_signature"):
            check_non_empty_str(getattr(self, field), field=field)
        check_optional_seed(self.seed)
        check_optional_fold(self.fold)
