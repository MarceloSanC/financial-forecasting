"""Golden do NexCP contra o `splitCP_LS` dos autores (Stage 7.2, Task 04; ADR 7.2.0002 item 5).

Lê a fixture congelada `tests/fixtures/nexcp_oracle/nexcp_cases.json` (o CI nunca
baixa o zip) e confere que o calibrador de registro escolhe, em cada caso, o mesmo
escore que a transcrição do bloco de limiar do código dos autores (ou +∞). Os
casos ficam a ≥ 1e-9 de 1 - alpha no índice escolhido, então float e aritmética exata
concordam.
"""

from __future__ import annotations

import json
import math
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting.features.inference.domain.services.conformal_calibrator import (
    ConformalCalibrator,
    ConformalVariant,
    exact_level,
    weighted_conformal_threshold,
)
from financial_forecasting.features.inference.domain.value_objects.calibration_set import (
    CalibrationPoint,
    CalibrationSet,
)

_FIXTURE = Path(__file__).resolve().parents[4] / "tests/fixtures/nexcp_oracle/nexcp_cases.json"
_RHOS = {1.0, 0.99, 0.95, 0.9}


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return loaded


def _number(value: dict[str, Any]) -> float:
    exact = float.fromhex(value["hex"])
    assert float(value["dec"]) == exact
    return exact


def _scores(case: dict[str, Any]) -> list[float]:
    scores = [float.fromhex(h) for h in case["scores"]["hex"]]
    assert [float(d) for d in case["scores"]["dec"]] == scores
    assert len(scores) == case["n"]
    return scores


def _expected(case: dict[str, Any]) -> float:
    if case["expected"] == "inf":
        return math.inf
    return _number(case["expected"])


def _calib(scores: list[float], alpha: float) -> CalibrationSet:
    """E^lo = E^hi = s na ordem do tempo: y = 0, q̂_lo = s, q̂_hi = -s; τ_lo = alpha."""
    upper_level = float(1 - exact_level(alpha))
    return CalibrationSet(
        fold_index=0,
        seed=1,
        horizon=1,
        lower_level=alpha,
        upper_level=upper_level,
        points=tuple(
            CalibrationPoint(
                decision_timestamp=f"{2000 + i:04d}-01-01T21:00:00+00:00",
                target_timestamp=f"{2000 + i:04d}-01-02T21:00:00+00:00",
                lower=s,
                upper=-s,
                realized=0.0,
            )
            for i, s in enumerate(scores)
        ),
        test_start="2999-01-01T21:00:00+00:00",
    )


def test_every_case_selects_the_authors_score(document: dict[str, Any]) -> None:
    assert document["cases"]
    for case in document["cases"]:
        scores = _scores(case)
        rho, alpha = _number(case["rho"]), _number(case["alpha"])
        n = case["n"]
        expected = _expected(case)
        weights = [exact_level(rho) ** (n + 1 - i) for i in range(1, n + 1)]
        assert weighted_conformal_threshold(scores, weights, exact_level(alpha)) == expected, case[
            "id"
        ]
        pair = ConformalCalibrator.calibrate(
            _calib(scores, alpha), variant=ConformalVariant.NEXCP, rho=rho
        )
        for tail in (pair.lower, pair.upper):
            assert tail.correction == expected, (case["id"], tail.tail)
            assert tail.infinite is math.isinf(expected)
            assert tail.alpha == exact_level(alpha)


def test_provenance_block_complete(document: dict[str, Any]) -> None:
    provenance = document["provenance"]
    assert provenance["source_url"] == "https://rinafb.github.io/code/nonexchangeable_conformal.zip"
    assert re.fullmatch(r"[0-9a-f]{64}", provenance["zip_sha256"])
    assert re.fullmatch(r"[0-9a-f]{8}", provenance["cell_id"])
    assert provenance["notebook"].endswith(".ipynb")
    assert provenance["function"] == "splitCP_LS"
    assert re.fullmatch(r"\d+\.\d+\.\d+", provenance["numpy_version"])
    assert provenance["seed"] == 20261017  # noqa: PLR2004 — a semente do technical
    assert provenance["margin"] == 1e-9  # noqa: PLR2004 — a margem do ADR 7.2.0002 item 5
    assert provenance["transcribed_lines"]
    generator = Path(__file__).resolve().parents[4] / provenance["generator"]
    assert generator.is_file()


def test_cases_cover_each_rho_and_an_infinite_case(document: dict[str, Any]) -> None:
    cases = document["cases"]
    assert {_number(case["rho"]) for case in cases} == _RHOS
    assert any(case["expected"] == "inf" for case in cases)
    assert any(case["expected"] != "inf" for case in cases)
    for rho in _RHOS:
        finite = [c for c in cases if _number(c["rho"]) == rho and c["expected"] != "inf"]
        assert finite, rho
    alphas = {exact_level(_number(case["alpha"])) for case in cases}
    assert alphas == {Fraction(1, 50), Fraction(1, 10), Fraction(1, 4)}
