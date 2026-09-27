"""Fake in-memory do port `CohortRunIndex` (Stage 5.5).

Os testes registram runs com `record(...)` — o que o silver teria — e o use case
do cohort lê pelo port. Paridade com o adapter real pelo contrato `[fake, real]`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

RunSummary = tuple[str, int, Mapping[int, frozenset[str]]]
_RunsByModel = dict[tuple[str, int | None], dict[str, RunSummary]]


class InMemoryCohortRunIndex:
    """Índice em memória: (cohort, asset, feature set) -> runs registrados."""

    def __init__(self) -> None:
        self._runs: dict[tuple[str, str, str], _RunsByModel] = {}

    def record(  # noqa: PLR0913 — espelha as colunas que o silver carrega
        self,
        *,
        asset_id: str,
        feature_set_name: str,
        cohort_id: str,
        model_version: str,
        seed: int | None,
        run_id: str,
        fold: str,
        targets_by_horizon: Mapping[int, Iterable[str]],
        rows: int | None = None,
    ) -> None:
        """Registra um run; sem `rows`, conta um por alvo (soma dos conjuntos)."""
        targets = {h: frozenset(ts) for h, ts in targets_by_horizon.items()}
        count = rows if rows is not None else sum(len(ts) for ts in targets.values())
        bucket = self._runs.setdefault((cohort_id, asset_id, feature_set_name), {})
        bucket.setdefault((model_version, seed), {})[run_id] = (fold, count, targets)

    def recorded_runs(
        self, *, asset_id: str, feature_set_name: str, cohort_id: str
    ) -> Mapping[tuple[str, int | None], Mapping[str, RunSummary]]:
        bucket = self._runs.get((cohort_id, asset_id, feature_set_name), {})
        return {key: dict(runs) for key, runs in bucket.items()}
