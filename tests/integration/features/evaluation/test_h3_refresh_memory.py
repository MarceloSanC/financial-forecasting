"""Teto de memória da leitura de H3 do refresh (Stage 7.3, Tasks 31 e C8-5; CA14b, I19).

O silver de atribuição real tem ~8,7 M linhas; o `RefreshGold` lê um run por chamada
(permutadas e VSN, filtro `run_id`) e a partição da ablação uma vez por `year`, reduz e
descarta. Aqui um leitor gera as linhas sob demanda, nos volumes reais, e devolve o
superconjunto da partição pedida, como o adapter. Nenhum dado real.

- `test_ablation_partition_read_once_per_year_at_real_size`: a leitura da ablação
  (~1 M linhas), pico pelo `tracemalloc`;
- `test_h3_step_peak_bounded_and_flat_in_runs` (C8-5b): o `RefreshGold._h3` inteiro e os
  quatro builders de H3, na geometria real — 10 seeds x 6 folds (T ≈ 1 506), 50 runs de
  ablação por ano, K_p = 10 e um bootstrap de 1 000 x T. Cada tamanho roda num processo
  próprio; o pico é o VmHWM zerado no começo da etapa menos o RSS de então (o
  `tracemalloc` deixaria o teste ~3x mais lento). Teto de 512 MiB e inclinação
  (pico(60) - pico(30)) / 30 dentro do orçamento por run declarado na §7 do technical.
"""

from __future__ import annotations

import json
import math
import random
import subprocess
import sys
import tracemalloc
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.application.use_cases.refresh_gold import (
    RefreshGold,
)
from financial_forecasting.features.evaluation.domain.value_objects.ablation_run_losses import (
    AblationRunLosses,
)
from financial_forecasting.features.evaluation.domain.value_objects.cohort_run import CohortRun
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    ForecastRecord,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
    LOCO_REFERENCE_MODEL,
    loco_model_of,
)
from financial_forecasting.features.evaluation.domain.value_objects.realized_returns import (
    RealizedReturns,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from tests.fakes.features.evaluation.fake_conformal_calibration import FakeConformalCalibration
from tests.fakes.features.evaluation.fake_mcs_backend import FakeMcsBackend
from tests.fakes.features.evaluation.fake_silver_table_reader import SILVER_COLUMNS
from tests.fakes.features.evaluation.fake_training_grid_reader import FakeTrainingGridReader
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore
from tests.fakes.shared.in_memory_clock import FakeClock

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_ASSET = "AAPL"
_LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
_OFFSETS = (-0.041, -0.0256, -0.0135, 0.0, 0.0135, 0.0256, 0.041)
_HORIZONS = (1, 7)
_DECISIONS = 251  # decisões de teste de um fold real (6 folds: T ≈ 1 506)
_YEARS = tuple(range(2019, 2025))  # ~6 blocos anuais, um fold por ano
_SEEDS = 10
_VARIABLES = 59
_MIB = 1024 * 1024
_CEILING = 512 * _MIB
# Orçamento de memória por run do candidato (declarado na §7 do technical, C8-5b).
_PER_RUN_BUDGET = 2 * _MIB
_EPOCH = datetime(2019, 1, 1, tzinfo=UTC)
_SESSIONS = (len(_YEARS) + 1) * 366
_PARTITION = GoldPartition(_ASSET, "sweep-memory")
_ABLATION_COHORT = "synthetic_ablation-r0-memory"
_PARTITION_HASH = "a1" * 32  # o `SYNTHETIC_PARTITION_HASH` do helper `_h3_parameters`
# a LOCO piora mais a cada configuração (importâncias positivas e distintas por família)
_LOCO_SHIFT = {
    LOCO_REFERENCE_MODEL: 0.0,
    **{loco_model_of(f): 0.004 * (2 + i) for i, f in enumerate(H3_FAMILIES)},
}


def _session(index: int) -> str:
    return (_EPOCH + timedelta(days=index)).isoformat()


def _first_session_of(year: int) -> int:
    return (datetime(year, 1, 1, tzinfo=UTC) - _EPOCH).days


_REALIZED = RealizedReturns(
    timestamps=tuple(_session(i) for i in range(_SESSIONS)),
    returns=tuple(random.Random("realized").uniform(-0.03, 0.03) for _ in range(_SESSIONS)),
)


def _grid(seed: int, decision: int, horizon: int, shift: float = 0.0) -> list[float]:
    center = math.sin(decision * 0.01 + seed) * 0.01 + shift
    return [center + offset for offset in _OFFSETS]


def _points(year: int) -> Iterator[tuple[int, int]]:
    first = _first_session_of(year)
    for horizon in _HORIZONS:
        for decision in range(first, first + _DECISIONS):
            yield horizon, decision


def _fact(run: CohortRun, horizon: int, decision: int, level: float, value: float) -> dict:  # type: ignore[type-arg]
    return {
        "run_id": run.run_id,
        "model_version": run.model,
        "asset": _ASSET,
        "feature_set_name": run.feature_set_name,
        "split": "test",
        "horizon": horizon,
        "decision_idx": decision,
        "timestamp_utc": _session(decision),
        "target_timestamp_utc": _session(decision + horizon),
        "quantile_level": level,
        "value_raw": value,
        "value_guardrail": value,
        "guardrail_applied": 0,
        "year": int(_session(decision)[:4]),
    }


def _variables() -> list[tuple[str, str]]:
    """As 7 features da partição sintética do helper e 52 variáveis fora das famílias."""
    from tests.unit.features.evaluation._h3_parameters import (  # noqa: PLC0415
        SYNTHETIC_PARTITION,
    )

    named = [(f, family) for family, features in SYNTHETIC_PARTITION.items() for f in features]
    return named + [(f"other_{i:02d}", "none") for i in range(_VARIABLES - len(named))]


class _GeneratingReader:
    """`SilverTableReader` que gera as linhas da partição pedida na hora (nada guardado)."""

    def __init__(
        self,
        *,
        candidate: Sequence[CohortRun],
        ablation: Sequence[CohortRun],
        year_of: Callable[[CohortRun], int],
    ) -> None:
        self._candidate = {run.run_id: run for run in candidate}
        self._ablation = list(ablation)
        self._year_of = year_of
        self._variables = _variables()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.rows = 0

    def read(
        self, *, layer: str, table: str, filters: Mapping[str, object] | None = None
    ) -> Sequence[Mapping[str, object]]:
        wanted = dict(filters or {})
        self.calls.append((table, wanted))
        rows = list(self._generate(table, wanted))
        self.rows += len(rows)
        return rows

    def columns(self, *, layer: str, table: str) -> Mapping[str, tuple[str, bool]]:
        """Tipos declarados do fake (Stage 8.1): mantém o leitor no Protocol."""
        return SILVER_COLUMNS[table]

    def _generate(self, table: str, wanted: Mapping[str, object]) -> Iterator[dict]:  # type: ignore[type-arg]  # noqa: PLR0912 — um ramo por tabela
        if table == "dim_run":
            for run in self._ablation:
                yield {
                    "run_id": run.run_id,
                    "asset": _ASSET,
                    "parent_sweep_id": _ABLATION_COHORT,
                    "feature_set_name": run.feature_set_name,
                    "config_signature": run.config_signature,
                    "fold": run.fold,
                    "seed": run.seed,
                    "model_version": run.model,
                }
            return
        if table == "fact_oos_predictions":
            year = int(str(wanted["year"]))
            for run in self._ablation:
                if self._year_of(run) != year:
                    continue
                shift = _LOCO_SHIFT[run.model]
                for horizon, decision in _points(year):
                    grid = _grid(run.seed or 0, decision, horizon, shift)
                    for level, value in zip(_LEVELS, grid, strict=True):
                        yield _fact(run, horizon, decision, level, value)
            return
        run = self._candidate[str(wanted["run_id"])]
        year = self._year_of(run)
        if table == "fact_permuted_predictions":
            labels = [("none", 0)] + [(f, k) for f in H3_FAMILIES for k in range(1, 11)]
            for family, k in labels:
                for horizon, decision in _points(year):
                    grid = _grid(run.seed or 0, decision, horizon, 0.001 * k)
                    for level, value in zip(_LEVELS, grid, strict=True):
                        row = _fact(run, horizon, decision, level, value)
                        row.update(
                            permuted_family=family,
                            permutation_index=k,
                            permutation_seed=130,
                            permutation_algorithm="fisher_yates_random_random_v1",
                            partition_hash=_PARTITION_HASH,
                        )
                        yield row
        elif table == "fact_vsn_weights":
            first = _first_session_of(year)
            weight = 1.0 / len(self._variables)
            for decision in range(first, first + _DECISIONS):
                for variable, family in self._variables:
                    yield {
                        "run_id": run.run_id,
                        "model_version": run.model,
                        "asset": _ASSET,
                        "feature_set_name": run.feature_set_name,
                        "decision_idx": decision,
                        "timestamp_utc": _session(decision),
                        "variable": variable,
                        "family": family,
                        "weight": weight,
                        "year": year,
                    }


def _use_case(reader: _GeneratingReader, builders: Sequence[object] = ()) -> RefreshGold:
    return RefreshGold(
        silver_reader=reader,
        grid_reader=FakeTrainingGridReader(
            {}, columns=("target_return",), hasher=CanonicalJsonHasher()
        ),
        clock=FakeClock(),
        mcs_backend=FakeMcsBackend(),
        gold_store=InMemoryGoldStore(),
        builders=list(builders),  # type: ignore[arg-type]
        conformal_calibration=FakeConformalCalibration(),
        hasher=CanonicalJsonHasher(),
    )


def _run(run_id: str, model: str, seed: int, fold: int, feature_set: str) -> CohortRun:
    return CohortRun(
        run_id=run_id,
        model=model,
        seed=seed,
        fold=str(fold),
        feature_set_name=feature_set,
        config_signature=f"sig-{model}",
    )


def _ablation_runs(seeds: int, folds: int) -> list[CohortRun]:
    models = (LOCO_REFERENCE_MODEL, *(loco_model_of(f) for f in H3_FAMILIES))
    return [
        _run(f"{model}-s{seed}-{fold}", model, seed, fold, "fs_all_ablation")
        for model in models
        for seed in range(1, seeds + 1)
        for fold in range(folds)
    ]


def _year_of(run: CohortRun) -> int:
    return _YEARS[int(str(run.fold))]


def test_ablation_partition_read_once_per_year_at_real_size() -> None:
    """~1 M linhas: 5 configurações x 6 anos x 10 seeds x ~3 500, lidas uma vez por ano."""
    runs = _ablation_runs(_SEEDS, len(_YEARS))
    reader = _GeneratingReader(candidate=(), ablation=runs, year_of=_year_of)
    use_case = _use_case(reader)

    tracemalloc.start()
    try:
        reductions = use_case._ablation_reductions(_PARTITION, runs, _YEARS, _REALIZED, _LEVELS)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert [table for table, _ in reader.calls] == ["fact_oos_predictions"] * len(_YEARS)
    assert [filters["year"] for _, filters in reader.calls] == list(_YEARS)
    assert reader.rows == len(runs) * _DECISIONS * len(_HORIZONS) * len(_LEVELS)
    assert reader.rows > 1_000_000  # noqa: PLR2004
    assert all(isinstance(r, AblationRunLosses) for r in reductions)
    assert peak <= _CEILING, f"peak {peak / _MIB:.0f} MiB"


# --- C8-5b: o passo `_h3` inteiro, com os builders, por processo -------------------------


def _status(field: str) -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{field}:"):
            return int(line.split()[1]) * 1024
    raise AssertionError(f"no {field}")  # pragma: no cover — só Linux (o container de teste)


def _reset_peak() -> None:
    """Zera o VmHWM do processo (`clear_refs` = 5): o pico passa a ser o da etapa.

    Sem isso, o pico do processo inteiro (o dos imports) menos um RSS-base que o kernel
    encolheu ao recuperar páginas sob pressão do cgroup infla a diferença — foi o que
    deu 1,18 GiB no `make check` com -n 4 (TA, Ponto C) para 264 MiB isolado.
    """
    Path("/proc/self/clear_refs").write_text("5", encoding="ascii")


def probe(seeds: int) -> dict[str, object]:
    """Roda `_h3` + os 4 builders com `seeds` x 6 folds e devolve o pico acima da base."""
    import copy  # noqa: PLC0415
    import dataclasses  # noqa: PLC0415

    from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_importance import (  # noqa: E501, PLC0415
        H3ImportanceGoldBuilder,
    )
    from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_reading import (  # noqa: E501, PLC0415
        H3ReadingGoldBuilder,
    )
    from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_shares import (  # noqa: E501, PLC0415
        H3SharesGoldBuilder,
    )
    from financial_forecasting.features.evaluation.adapters.out.duckdb.gold_builders.h3_vsn import (  # noqa: PLC0415
        H3VsnGoldBuilder,
    )
    from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (  # noqa: PLC0415
        H3Parameters,
    )
    from tests.contract.features.evaluation._gold_inputs import (  # noqa: PLC0415
        completed_inputs_without_h3,
    )
    from tests.unit.features.evaluation._h3_parameters import h3_block  # noqa: PLC0415

    block = copy.deepcopy(h3_block())
    block["ablation"].update(cohort_id=_ABLATION_COHORT, seeds=list(range(1, seeds + 1)))
    h3 = H3Parameters.from_mapping(block)
    folds = len(_YEARS)
    candidate = [
        _run(f"tft-s{s}-{f}", "tft", s, f, "fs-core")
        for s in range(1, seeds + 1)
        for f in range(folds)
    ]
    ablation = _ablation_runs(seeds, folds)
    reader = _GeneratingReader(candidate=candidate, ablation=ablation, year_of=_year_of)
    use_case = _use_case(reader)
    records = [
        ForecastRecord(
            run_id=run.run_id,
            model="tft",
            seed=run.seed,
            fold=run.fold,
            horizon=1,
            decision_idx=_first_session_of(_year_of(run)),
            decision_timestamp=_session(_first_session_of(_year_of(run))),
            target_timestamp=_session(_first_session_of(_year_of(run)) + 1),
            split="test",
            quantile_level=level,
            value_raw=0.0,
            value_guardrail=0.0,
            guardrail_applied=False,
        )
        for run in candidate
        for level in _LEVELS
    ]
    base_inputs = completed_inputs_without_h3()
    parameters = dataclasses.replace(base_inputs.parameters, candidate="tft", h3_parameters=h3)
    builders = (
        H3ImportanceGoldBuilder(),
        H3SharesGoldBuilder(),
        H3ReadingGoldBuilder(),
        H3VsnGoldBuilder(),
    )
    _reset_peak()
    before = _status("VmRSS")
    reports = use_case._h3(
        partition=_PARTITION,
        runs=candidate,
        records=records,
        parameters=parameters,
        realized=_REALIZED,
        h3=h3,
    )
    inputs = dataclasses.replace(base_inputs, parameters=parameters, h3_reports=reports)
    tables = [builder.build(inputs) for builder in builders]
    peak = _status("VmHWM")
    return {
        "peak": peak - before,
        "permutation": reports.permutation.status if reports.permutation else None,
        "ablation": reports.ablation.status if reports.ablation else None,
        "vsn": reports.vsn.status if reports.vsn else None,
        "n_points": reports.n_points,
        "rows": sum(len(table.rows) for table in tables),
    }


def _probe_in_subprocess(seeds: int) -> dict[str, object]:
    script = (
        "import json, sys\n"
        "from tests.integration.features.evaluation.test_h3_refresh_memory import probe\n"
        f"print(json.dumps(probe({seeds})))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    return dict(json.loads(completed.stdout.strip().splitlines()[-1]))


def test_h3_step_peak_bounded_and_flat_in_runs() -> None:
    """C8-5b: pico do `_h3` + builders <= 512 MiB e inclinação por run no orçamento."""
    half = _probe_in_subprocess(_SEEDS // 2)  # 30 runs do candidato
    full = _probe_in_subprocess(_SEEDS)  # 60 runs do candidato
    for result in (half, full):
        assert (result["permutation"], result["ablation"], result["vsn"]) == ("ok", "ok", "ok")
        assert result["n_points"] == _DECISIONS * len(_YEARS)
        assert int(str(result["peak"])) <= _CEILING, result
    slope = (int(str(full["peak"])) - int(str(half["peak"]))) / 30
    assert slope <= _PER_RUN_BUDGET, (half, full, slope / _MIB)
