"""E2E da API de inferência pela app completa (Stage 7.4, Task 07) — CA1-CA5, CA7, CA11, CA13.

`create_app(Settings(...))` com `data_root = tmp_path` e o arquivo de cohort real
(`config/cohorts/aapl_confirmatory.toml`): o `cohort_id` sai do mesmo leitor + hasher da
composition root, e **nenhum dado real é lido**. O silver é sintético, gravado pelo
`ParquetAnalyticsRepository` (10 seeds, folds "0" e "1", teste e calib sobrepostos, um
`gbm_quantile` no mesmo cohort); o gold é publicado pelo `ParquetGoldStore` real.
Valores diádicos: os literais esperados são exatos.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CONFORMAL_CORRECTIONS,
    GOLD_H3_VSN,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
    GoldTable,
    RefreshParameters,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    EMPIRICAL_COVERAGE_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.contribution_agreement import (
    H3_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.vsn_summary import VSN_LABEL
from financial_forecasting.features.modeling.application.use_cases.cohort_unit_runner import (
    CohortNotFrozenError,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.infrastructure.config.settings import Settings
from financial_forecasting.shared.infrastructure.http.app import create_app
from tests.fakes.shared.in_memory_clock import FakeClock
from tests.unit.features.evaluation._serving_gold_rows import (
    complete_rows,
    correction_row,
    generation,
)

pytestmark = pytest.mark.e2e

_REPO = Path(__file__).resolve().parents[4]
_COHORT_FILE = _REPO / "config" / "cohorts" / "aapl_confirmatory.toml"
_SRC_INFERENCE = _REPO / "src" / "financial_forecasting" / "features" / "inference"
_ASSET = "AAPL"
_FS = "fs_all"
_LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
_OFFSETS = (-0.0625, -0.03125, -0.015625, 0.0, 0.0078125, 0.03125, 0.0625)
_SEEDS = tuple(range(1, 11))
_CALIB_ONLY = date(2024, 3, 8)
_TEST_0 = [date(2024, 3, d) for d in (11, 12, 13, 14, 15)]
_CALIB_1 = [date(2024, 3, 14), date(2024, 3, 15)]
_TEST_1 = [date(2024, 3, d) for d in (18, 19, 20, 21, 22)]
_LAST = date(2024, 3, 22)  # só h+1
_H7 = 7
_NOT_FOUND = "não há dados para o pedido solicitado"
_Post = Callable[[dict[str, object]], tuple[int, dict[str, Any]]]


def _cohort_id() -> str:
    cohort_file = importlib.import_module(
        "financial_forecasting.features.modeling.adapters.in.cli.cohort_file"
    )
    spec = cohort_file.load(_COHORT_FILE)
    cohort_hash = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())
    cohort_id: str = spec.cohort_id(cohort_hash)
    return cohort_id


_COHORT = _cohort_id()


def _ts(day: date) -> str:
    return f"{day.isoformat()}T00:00:00+00:00"


def _grid(seed: int, fold: int, horizon: int) -> tuple[float, ...]:
    base = seed / 512 + horizon / 4096 + fold / 8192
    return tuple(base + offset for offset in _OFFSETS)


def _facts(
    run: tuple[str, int, int], split: str, day: date, horizon: int
) -> list[dict[str, object]]:
    run_id, seed, fold = run
    model = "gbm_quantile" if run_id.startswith("gbm") else "tft_quantile"
    return [
        {
            "schema_version": 1,
            "run_id": run_id,
            "model_version": model,
            "asset": _ASSET,
            "feature_set_name": _FS,
            "split": split,
            "horizon": horizon,
            "decision_idx": 0,
            "timestamp_utc": _ts(day),
            "target_timestamp_utc": _ts(day + timedelta(days=horizon)),
            "quantile_level": level,
            "value_raw": value,
            "value_guardrail": value,
            "guardrail_applied": 0,
            "year": day.year,
        }
        for level, value in zip(_LEVELS, _grid(seed, fold, horizon), strict=True)
    ]


def _dim(run_id: str, seed: int, fold: int, model: str = "tft_quantile") -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "asset": _ASSET,
        "parent_sweep_id": _COHORT,
        "feature_set_name": _FS,
        "config_signature": "sig",
        "split_fingerprint": "split",
        "fold": str(fold),
        "seed": seed,
        "model_version": model,
    }


def _write_silver(root: Path) -> None:
    dims = [_dim(f"f{fold}s{seed}", seed, fold) for fold in (0, 1) for seed in _SEEDS]
    dims.append(_dim("gbm0", 1, 0, model="gbm_quantile"))
    facts: list[dict[str, object]] = []
    for seed in _SEEDS:
        for horizon in (1, _H7):
            facts += _facts((f"f0s{seed}", seed, 0), "calib", _CALIB_ONLY, horizon)
            for day in _TEST_0:
                facts += _facts((f"f0s{seed}", seed, 0), "test", day, horizon)
            for day in _CALIB_1:
                facts += _facts((f"f1s{seed}", seed, 1), "calib", day, horizon)
            for day in _TEST_1:
                if not (horizon == _H7 and day == _LAST):
                    facts += _facts((f"f1s{seed}", seed, 1), "test", day, horizon)
    for day in _TEST_0:
        facts += _facts(("gbm0", 1, 0), "test", day, 1)
    repository = ParquetAnalyticsRepository(data_root=root, clock=FakeClock())
    repository.write(layer="silver", table="dim_run", rows=dims)
    repository.write(layer="silver", table="fact_oos_predictions", rows=facts)


def _inner_pair(tail: str, correction: float) -> dict[str, object]:
    row = correction_row("0", 1, tail, correction=correction)
    return {
        **row,
        "lower_level": 0.25,
        "upper_level": 0.75,
        "tail_level": 0.25 if tail == "lower" else 0.75,
    }


def _publish(
    root: Path,
    status: RefreshStatus = RefreshStatus.COMPLETED,
    *,
    parameters: RefreshParameters | None = None,
) -> Path:
    rows = complete_rows()
    rows[GOLD_CONFORMAL_CORRECTIONS.name] += [
        _inner_pair("lower", 0.001953125),
        _inner_pair("upper", 0.0009765625),
    ]
    tables, manifest = generation(status, rows=rows, parameters=parameters)
    partition = GoldPartition(_ASSET, _COHORT)
    tables = [
        GoldTable.sorted_by_key(t.name, t.key, [{**r, "parent_sweep_id": _COHORT} for r in t.rows])
        for t in tables
    ]
    store = ParquetGoldStore(root)
    store.publish(
        partition=partition, tables=tables, manifest=replace(manifest, partition=partition)
    )
    return store.current_dir(partition)


def _settings(root: Path, cohort_file: Path | None = _COHORT_FILE) -> Settings:
    return Settings(
        _env_file=None,
        data_root=root,
        artifacts_root=root / "artifacts",
        mlflow_tracking_uri=f"sqlite:///{root}/mlruns.db",
        serving_cohort_file=cohort_file,
    )


@pytest.fixture
def api(tmp_path: Path) -> Iterator[_Post]:
    _write_silver(tmp_path)
    client = TestClient(create_app(_settings(tmp_path)), raise_server_exceptions=False)

    def post(body: dict[str, object]) -> tuple[int, dict[str, Any]]:
        response = client.post("/inference/run", json=body)
        return response.status_code, response.json()

    yield post
    client.close()


def _request(day: date = date(2024, 3, 15), **extra: object) -> dict[str, object]:
    return {"asset": _ASSET, "decision_date": day.isoformat(), **extra}


# --- CA1 / CA4 / CA5: caminho feliz -----------------------------------------------------


def test_happy_path_serves_the_recorded_grid_with_literal_intervals(
    api: _Post, tmp_path: Path
) -> None:
    _publish(tmp_path)
    status, body = api(_request())
    assert status == 200  # noqa: PLR2004
    assert body["schema_version"] == 1
    assert (body["cohort_id"], body["model_version"]) == (_COHORT, "tft_quantile")
    assert body["quantile_levels"] == list(_LEVELS)
    forecasts = body["forecasts"]
    assert [f["horizon"] for f in forecasts] == [1, 7]
    assert [f["target_date"] for f in forecasts] == ["2024-03-16", "2024-03-22"]
    for forecast in forecasts:
        assert [m["seed"] for m in forecast["members"]] == list(_SEEDS)
        assert {m["fold"] for m in forecast["members"]} == {"0"}
    member = forecasts[0]["members"][0]
    assert member["run_id"] == "f0s1"
    # seed 1, h+1, fold 0: base = 1/512 + 1/4096
    assert member["quantiles"] == [
        -0.060302734375,
        -0.029052734375,
        -0.013427734375,
        0.002197265625,
        0.010009765625,
        0.033447265625,
        0.064697265625,
    ]
    conformal = member["conformal"]
    assert (conformal["status"], conformal["label"]) == ("available", EMPIRICAL_COVERAGE_LABEL)
    outer, middle, inner = conformal["intervals"]
    assert (outer["status"], outer["reason"]) == ("unavailable", "unidade ausente na geração gold")
    assert (outer["lower"], outer["lower_infinite"], outer["upper"], outer["upper_infinite"]) == (
        None,
        False,
        None,
        False,
    )
    # (0.1, 0.9): Q_lo = 2^-8, Q_hi = +inf
    assert (
        middle["lower"],
        middle["lower_infinite"],
        middle["upper"],
        middle["upper_infinite"],
    ) == (
        -0.032958984375,
        False,
        None,
        True,
    )
    # (0.25, 0.75): Q_lo = 2^-9 != Q_hi = 2^-10
    assert (inner["lower"], inner["upper"], inner["status"]) == (
        -0.015380859375,
        0.010986328125,
        "ok",
    )
    explainability = body["explainability"]
    assert (explainability["status"], explainability["label"], explainability["vsn_label"]) == (
        "available",
        H3_LABEL,
        VSN_LABEL,
    )
    share = explainability["shares"][0]
    assert (share["method"], share["lower"], share["lower_infinite"]) == ("loco", None, True)
    assert body["gold"]["published"] is True
    assert body["gold"]["generation_status"] == "COMPLETED"


def test_overlap_of_test_and_next_calib_is_served_by_the_test_run(
    api: _Post, tmp_path: Path
) -> None:
    status, body = api(_request(date(2024, 3, 14)))
    assert status == 200  # noqa: PLR2004
    assert {m["fold"] for f in body["forecasts"] for m in f["members"]} == {"0"}


# --- CA2: 404 ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        ({"asset": "MSFT", "decision_date": "2024-03-15"}, "ativo 'MSFT'"),
        (_request(horizons=[1, 3]), "horizonte(s) [3]"),
        (_request(seeds=[11]), "seed(s) [11]"),
        (_request(date(2023, 1, 2)), "decisão 2023-01-02 sem linha de teste"),
        (_request(_CALIB_ONLY), "decisão 2024-03-08 sem linha de teste"),
        (_request(_LAST), "(seed 1, h+7)"),
    ],
    ids=["asset", "horizon", "seed", "outside-test", "calib-only", "last-session-h7"],
)
def test_not_found_says_what_is_missing(api: _Post, body: dict[str, object], missing: str) -> None:
    status, response = api(body)
    assert status == 404  # noqa: PLR2004
    assert response["type"] == "not_found"
    assert str(response["detail"]).startswith(_NOT_FOUND)
    assert missing in str(response["detail"])


def test_last_session_with_h1_only_is_served(api: _Post) -> None:
    status, body = api(_request(_LAST, horizons=[1]))
    assert status == 200  # noqa: PLR2004
    assert [f["horizon"] for f in body["forecasts"]] == [1]


# --- CA3: gold indisponível -------------------------------------------------------------


def _blocks(body: dict[str, Any]) -> tuple[set[tuple[str, str]], tuple[str, str]]:
    conformal = {
        (m["conformal"]["status"], m["conformal"]["reason"])
        for f in body["forecasts"]
        for m in f["members"]
    }
    explainability = body["explainability"]
    return conformal, (explainability["status"], explainability["reason"])


def _labels(body: dict[str, Any]) -> set[str]:
    labels = {m["conformal"]["label"] for f in body["forecasts"] for m in f["members"]}
    return labels | {body["explainability"]["label"], body["explainability"]["vsn_label"]}


def test_without_gold_the_grid_is_served_and_both_blocks_are_unavailable(api: _Post) -> None:
    status, body = api(_request())
    assert status == 200  # noqa: PLR2004
    reason = f"gold não publicado para o cohort {_COHORT}"
    assert _blocks(body) == ({("unavailable", reason)}, ("unavailable", reason))
    assert _labels(body) == {EMPIRICAL_COVERAGE_LABEL, H3_LABEL, VSN_LABEL}
    assert body["gold"] == {
        "published": False,
        "generation_status": None,
        "preregistration_ref": None,
        "candidate": None,
        "finished_at": None,
    }
    assert body["forecasts"][0]["members"][0]["quantiles"][3] == 0.002197265625  # noqa: PLR2004


def test_blocked_gold_makes_both_blocks_unavailable(api: _Post, tmp_path: Path) -> None:
    _publish(tmp_path, RefreshStatus.BLOCKED)
    status, body = api(_request())
    assert status == 200  # noqa: PLR2004
    blocked = ("unavailable", "geração gold BLOCKED")
    assert _blocks(body) == ({blocked}, blocked)
    assert _labels(body) == {EMPIRICAL_COVERAGE_LABEL, H3_LABEL, VSN_LABEL}


def test_gold_of_another_candidate_makes_both_blocks_unavailable(
    api: _Post, tmp_path: Path
) -> None:
    default = generation()[1].parameters
    _publish(tmp_path, parameters=replace(default, candidate="gbm_quantile"))
    status, body = api(_request())
    assert status == 200  # noqa: PLR2004
    other = ("unavailable", "geração gold de outro candidato: gbm_quantile (servido: tft_quantile)")
    assert _blocks(body) == ({other}, other)


def test_no_label_literal_lives_in_the_inference_slice() -> None:
    sources = [path.read_text(encoding="utf-8") for path in _SRC_INFERENCE.rglob("*.py")]
    assert sources
    for label in (EMPIRICAL_COVERAGE_LABEL, H3_LABEL, VSN_LABEL):
        assert not [text for text in sources if label in text], label


# --- CA7 / CA11 / CA13 ------------------------------------------------------------------


def test_corrupt_generation_is_a_500(api: _Post, tmp_path: Path) -> None:
    current = _publish(tmp_path)
    (current / f"{GOLD_H3_VSN.name}.parquet").unlink()
    status, body = api(_request())
    assert status == 500  # noqa: PLR2004
    assert body["type"] == "application_error"


def test_without_cohort_file_the_route_answers_500(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path, None)), raise_server_exceptions=False)
    response = client.post("/inference/run", json=_request())
    assert response.status_code == 500  # noqa: PLR2004
    assert response.json() == {
        "detail": "serviço de inferência sem cohort configurado",
        "type": "application_error",
    }


def test_unreadable_cohort_file_fails_the_app_at_startup(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        create_app(_settings(tmp_path, tmp_path / "missing.toml"))


def test_draft_cohort_fails_the_app_at_startup(tmp_path: Path) -> None:
    draft = tmp_path / "draft.toml"
    text = _COHORT_FILE.read_text(encoding="utf-8")
    draft.write_text(text.split("\n[provenance]")[0] + "\n", encoding="utf-8")
    with pytest.raises(CohortNotFrozenError, match="is not frozen"):
        create_app(_settings(tmp_path, draft))


def test_two_equal_requests_give_equal_bodies(api: _Post, tmp_path: Path) -> None:
    _publish(tmp_path)
    assert api(_request()) == api(_request())


def test_the_app_exposes_one_inference_route(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, None))
    paths = app.openapi()["paths"]
    assert sorted(p for p in paths if "inference" in p) == ["/inference/run"]
    assert set(paths["/inference/run"]) == {"post"}
