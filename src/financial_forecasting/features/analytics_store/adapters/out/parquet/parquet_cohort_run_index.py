"""Adapter `ParquetCohortRunIndex` — satisfaz o port `CohortRunIndex` do slice modeling.

Port consumer-owned (ADR 0.0.0053): definido em
`modeling/application/ports/out/cohort_run_index.py` e satisfeito aqui por
duck-typing, sem importar o modeling (o contrato `bc-independence` reprovaria a
aresta). A assinatura só usa tipos builtin por isso.

Lê o silver pelo `ParquetAnalyticsRepository` do mesmo slot:

- `dim_run` filtrado pela partição `(asset, parent_sweep_id = cohort_id)` — os runs
  do cohort, com `model_version`, `seed` e `fold`;
- `fact_oos_predictions` filtrado por `(asset, feature_set_name)` — os arquivos
  anuais são compartilhados entre cohorts, então as linhas são atribuídas pelo
  `run_id` dos runs do cohort (outro cohort no mesmo arquivo não contamina).

Devolve `(model_version, seed) -> {run_id: (fold, linhas, {horizonte:
frozenset(target_timestamp)})}`; run de `dim_run` sem predição (órfão de uma
queda) aparece com 0 linhas — é o que a retomada do cohort usa para distinguir
órfão, completo e parcial (ADR 5.5.0003).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from financial_forecasting.features.analytics_store.application.ports.out.analytics_repository import (  # noqa: E501
        AnalyticsRepository,
    )

_SILVER = "silver"
_DIM_RUN = "dim_run"
_FACT = "fact_oos_predictions"

RunSummary = tuple[str, int, Mapping[int, frozenset[str]]]


class ParquetCohortRunIndex:
    """Índice de runs de um cohort sobre o silver Parquet (port `CohortRunIndex`)."""

    def __init__(self, *, repository: AnalyticsRepository) -> None:
        self._repository = repository

    def recorded_runs(
        self, *, asset_id: str, feature_set_name: str, cohort_id: str
    ) -> Mapping[tuple[str, int | None], Mapping[str, RunSummary]]:
        runs = self._repository.read(
            layer=_SILVER,
            table=_DIM_RUN,
            filters={"asset": asset_id, "parent_sweep_id": cohort_id},
        )
        runs = [run for run in runs if run.get("feature_set_name") == feature_set_name]
        if not runs:
            return {}
        run_ids = {str(run["run_id"]) for run in runs}
        rows_by_run: dict[str, int] = dict.fromkeys(run_ids, 0)
        targets_by_run: dict[str, dict[int, set[str]]] = {run_id: {} for run_id in run_ids}
        facts = self._repository.read(
            layer=_SILVER,
            table=_FACT,
            filters={"asset": asset_id, "feature_set_name": feature_set_name},
        )
        for fact in facts:
            run_id = str(fact["run_id"])
            if run_id not in run_ids:
                continue
            rows_by_run[run_id] += 1
            # Linha do silver chega como Mapping[str, object]; o schema pandera
            # do fato já garante `horizon` inteiro (o ignore é só do tipo estático).
            horizon = int(fact["horizon"])  # type: ignore[call-overload]
            targets_by_run[run_id].setdefault(horizon, set()).add(str(fact["target_timestamp_utc"]))

        index: dict[tuple[str, int | None], dict[str, RunSummary]] = {}
        for run in runs:
            run_id = str(run["run_id"])
            seed = run["seed"]
            # Idem: `seed` de `dim_run` é inteiro ou nulo pelo schema (ignore estático).
            key = (str(run["model_version"]), int(seed) if seed is not None else None)  # type: ignore[call-overload]
            targets = {h: frozenset(ts) for h, ts in targets_by_run[run_id].items()}
            fold = run.get("fold")
            index.setdefault(key, {})[run_id] = (
                str(fold) if fold is not None else "",
                rows_by_run[run_id],
                targets,
            )
        return index
