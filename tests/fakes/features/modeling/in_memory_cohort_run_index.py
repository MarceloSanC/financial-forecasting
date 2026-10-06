"""Fake in-memory do port `CohortRunIndex` (Stage 5.5).

Os testes registram runs com `record(...)` — o que o silver teria — e o use case
do cohort lê pelo port. Paridade com o adapter real pelo contrato `[fake, real]`.

Só linhas de teste contam (ADR 7.1.0002 item 4): `record(..., split="calib")`
não soma linhas nem alvos. Como no silver o run existe em `dim_run` mesmo que só
tenha linhas de calib, um registro de calib de run ainda desconhecido o cria como
órfão (0 linhas) e, de run já registrado, não muda nada — paridade com o
`ParquetCohortRunIndex`, que descarta os fatos de calib antes de contar.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

RunSummary = tuple[str, int, Mapping[int, frozenset[str]]]
_TEST_SPLIT = "test"
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
        rows: int,
        split: str = _TEST_SPLIT,
    ) -> None:
        """Registra um run com a contagem de linhas de predição (níveis inclusos).

        `split != "test"` não conta: o run só nasce como órfão se ainda não existe.
        """
        bucket = self._runs.setdefault((cohort_id, asset_id, feature_set_name), {})
        runs = bucket.setdefault((model_version, seed), {})
        if split != _TEST_SPLIT:
            runs.setdefault(run_id, (fold, 0, {}))
            return
        targets = {h: frozenset(ts) for h, ts in targets_by_horizon.items()}
        runs[run_id] = (fold, rows, targets)

    def recorded_runs(
        self, *, asset_id: str, feature_set_name: str, cohort_id: str
    ) -> Mapping[tuple[str, int | None], Mapping[str, RunSummary]]:
        bucket = self._runs.get((cohort_id, asset_id, feature_set_name), {})
        return {key: dict(runs) for key, runs in bucket.items()}
