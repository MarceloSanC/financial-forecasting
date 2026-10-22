"""E2E da API de inferência pela app completa (Stage 7.4, Task 07) — CA1-CA5, CA7, CA11, CA13.

`create_app(Settings(...))` com `data_root = tmp_path` e o arquivo de cohort real
(`config/cohorts/aapl_confirmatory.toml`): o `cohort_id` sai do mesmo leitor + hasher da
composition root, e **nenhum dado real é lido**. O silver é sintético, gravado pelo
`ParquetAnalyticsRepository` (10 seeds, folds "0" e "1", teste e calib sobrepostos, um
`gbm_quantile` no mesmo cohort); o gold é publicado pelo `ParquetGoldStore` real.
Valores diádicos: os literais esperados são exatos.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_H3_VSN,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
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
from financial_forecasting.shared.infrastructure.http.app import create_app
from tests.e2e.features.inference._scenario import (
    ASSET,
    CALIB_ONLY,
    COHORT,
    COHORT_FILE,
    LAST,
    LEVELS,
    REPO,
    SEEDS,
    publish,
    settings,
    write_silver,
)
from tests.unit.features.evaluation._serving_gold_rows import (
    generation,
)

pytestmark = pytest.mark.e2e

_SRC_INFERENCE = REPO / "src" / "financial_forecasting" / "features" / "inference"
_NOT_FOUND = "não há dados para o pedido solicitado"
_Post = Callable[[dict[str, object]], tuple[int, dict[str, Any]]]


@pytest.fixture
def api(tmp_path: Path) -> Iterator[_Post]:
    write_silver(tmp_path)
    client = TestClient(create_app(settings(tmp_path)), raise_server_exceptions=False)

    def post(body: dict[str, object]) -> tuple[int, dict[str, Any]]:
        response = client.post("/inference/run", json=body)
        return response.status_code, response.json()

    yield post
    client.close()


def _request(day: date = date(2024, 3, 15), **extra: object) -> dict[str, object]:
    return {"asset": ASSET, "decision_date": day.isoformat(), **extra}


# --- CA1 / CA4 / CA5: caminho feliz -----------------------------------------------------


def test_happy_path_serves_the_recorded_grid_with_literal_intervals(
    api: _Post, tmp_path: Path
) -> None:
    publish(tmp_path)
    status, body = api(_request())
    assert status == 200  # noqa: PLR2004
    assert body["schema_version"] == 1
    assert (body["cohort_id"], body["model_version"]) == (COHORT, "tft_quantile")
    assert body["quantile_levels"] == list(LEVELS)
    forecasts = body["forecasts"]
    assert [f["horizon"] for f in forecasts] == [1, 7]
    assert [f["target_date"] for f in forecasts] == ["2024-03-16", "2024-03-22"]
    for forecast in forecasts:
        assert [m["seed"] for m in forecast["members"]] == list(SEEDS)
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


def test_a_fold_1_decision_uses_the_unit_of_fold_1(api: _Post, tmp_path: Path) -> None:
    publish(tmp_path)
    status, body = api(_request(date(2024, 3, 18), horizons=[1], seeds=[1]))
    assert status == 200  # noqa: PLR2004
    (member,) = body["forecasts"][0]["members"]
    assert (member["fold"], member["run_id"]) == ("1", "f1s1")
    _, middle, _ = member["conformal"]["intervals"]
    # seed 1, h+1, fold 1: base = 1/512 + 1/4096 + 1/8192; q(0.1) = base - 2^-5,
    # q(0.9) = base + 2^-5; (q_lo - 2^-4, q_hi + 2^-5)
    assert (middle["lower_level"], middle["upper_level"], middle["status"]) == (0.1, 0.9, "ok")
    assert (middle["lower"], middle["upper"]) == (-0.0914306640625, 0.0648193359375)
    assert (middle["lower_infinite"], middle["upper_infinite"]) == (False, False)


def test_reading_and_vsn_rows_reach_the_client(api: _Post, tmp_path: Path) -> None:
    publish(tmp_path)
    _, body = api(_request())
    reading = body["explainability"]["reading"]
    assert reading == {
        "reading_rule": "interval_side_agreement_same_family_v1",
        "heterogeneous_permutation": True,
        "heterogeneous_ablation": False,
        "sustained": False,
        "agreeing_families": ["price", "technical"],
        "n_points": 1505,
        "status": "ok",
        "reason": None,
    }
    family = next(v for v in body["explainability"]["vsn"] if v["kind"] == "family")
    assert family == {
        "kind": "family",
        "name": "price",
        "family": "price",
        "p10": 0.125,
        "p50": 0.25,
        "p90": 0.5,
        "n_decisions": 1505,
        "status": "ok",
        "reason": None,
    }


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
        (_request(CALIB_ONLY), "decisão 2024-03-08 sem linha de teste"),
        (_request(LAST), "(seed 1, h+7)"),
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
    status, body = api(_request(LAST, horizons=[1]))
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
    reason = f"gold não publicado para o cohort {COHORT}"
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
    publish(tmp_path, RefreshStatus.BLOCKED)
    status, body = api(_request())
    assert status == 200  # noqa: PLR2004
    blocked = ("unavailable", "geração gold BLOCKED")
    assert _blocks(body) == ({blocked}, blocked)
    assert _labels(body) == {EMPIRICAL_COVERAGE_LABEL, H3_LABEL, VSN_LABEL}


def test_gold_of_another_candidate_makes_both_blocks_unavailable(
    api: _Post, tmp_path: Path
) -> None:
    default = generation()[1].parameters
    publish(tmp_path, parameters=replace(default, candidate="gbm_quantile"))
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
    current = publish(tmp_path)
    (current / f"{GOLD_H3_VSN.name}.parquet").unlink()
    status, body = api(_request())
    assert status == 500  # noqa: PLR2004
    assert body["type"] == "application_error"


def test_without_cohort_file_the_route_answers_500(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path, None)), raise_server_exceptions=False)
    response = client.post("/inference/run", json=_request())
    assert response.status_code == 500  # noqa: PLR2004
    assert response.json() == {
        "detail": "serviço de inferência sem cohort configurado",
        "type": "application_error",
    }


def test_unreadable_cohort_file_fails_the_app_at_startup(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        create_app(settings(tmp_path, tmp_path / "missing.toml"))


def test_draft_cohort_fails_the_app_at_startup(tmp_path: Path) -> None:
    draft = tmp_path / "draft.toml"
    text = COHORT_FILE.read_text(encoding="utf-8")
    draft.write_text(text.split("\n[provenance]")[0] + "\n", encoding="utf-8")
    with pytest.raises(CohortNotFrozenError, match="is not frozen"):
        create_app(settings(tmp_path, draft))


def test_two_equal_requests_give_equal_bodies(api: _Post, tmp_path: Path) -> None:
    publish(tmp_path)
    assert api(_request()) == api(_request())


def test_the_app_exposes_one_inference_route(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path, None))
    paths = app.openapi()["paths"]
    assert sorted(p for p in paths if "inference" in p) == ["/inference/run"]
    assert set(paths["/inference/run"]) == {"post"}
