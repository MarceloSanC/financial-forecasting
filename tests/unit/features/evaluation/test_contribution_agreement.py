"""Unit do `ContributionAgreement` (Stage 7.3, Task 26; I15; ADR 7.3.0005 H3-READ)."""

from __future__ import annotations

import pytest

from financial_forecasting.features.evaluation.domain.services.contribution_agreement import (
    H3_LABEL,
    ContributionAgreement,
)
from financial_forecasting.features.evaluation.domain.services.family_contribution import (
    FamilyContributionReport,
    FamilyShare,
)
from financial_forecasting.features.evaluation.domain.value_objects.h3_parameters import (
    H3_FAMILIES,
)

pytestmark = pytest.mark.unit


def _share(family: str, *, side: int = 1, excludes: bool = False, ok: bool = True) -> FamilyShare:
    return FamilyShare(
        family=family,
        share_h1=0.25,
        share_h7=0.25 + 0.1 * side,
        delta=0.1 * side,
        lower=0.05 if excludes and side > 0 else -1.0,
        upper=-0.05 if excludes and side < 0 else 1.0,
        side=side,
        excludes_zero=excludes if ok else None,
        status="ok" if ok else "undefined",
        reason=None if ok else "a bound of the interval is exactly 0",
    )


def _report(method: str, *shares: FamilyShare, undefined: bool = False) -> FamilyContributionReport:
    by_family = {share.family: share for share in shares}
    full = tuple(by_family.get(f, _share(f)) for f in H3_FAMILIES)
    return FamilyContributionReport(
        method=method,
        importance={},
        shares=full,
        level=0.9875,
        nonpositive_replicas={1: 0, 7: 0},
        status="undefined" if undefined else "ok",
        reason="the point total of importances is <= 0 (H3-NEG)" if undefined else None,
        heterogeneous=None
        if undefined
        else any(s.status == "ok" and s.excludes_zero for s in full),
    )


def test_sustained_when_same_family_excludes_zero_in_both_with_same_sign() -> None:
    reading = ContributionAgreement.read(
        _report("permutation", _share("sentiment", excludes=True)),
        _report("loco", _share("sentiment", excludes=True), _share("price", excludes=True)),
    )
    assert reading.sustained is True
    assert reading.agreeing_families == ("sentiment",)
    assert reading.status == "ok"
    assert (reading.heterogeneous_permutation, reading.heterogeneous_ablation) == (True, True)


def test_opposite_signs_not_sustained_status_ok() -> None:
    reading = ContributionAgreement.read(
        _report("permutation", _share("price", side=1, excludes=True)),
        _report("loco", _share("price", side=-1, excludes=True)),
    )
    assert reading.sustained is False
    assert reading.status == "ok"
    assert reading.reason is None
    assert reading.agreeing_families == ()


def test_heterogeneity_flags_are_per_method() -> None:
    """TA-3: permutação heterogênea e LOCO não (nenhuma família exclui 0) ⇒ (True, False)."""
    reading = ContributionAgreement.read(
        _report("permutation", _share("price", excludes=True)),
        _report("loco"),
    )
    assert reading.status == "ok"
    assert reading.sustained is False
    assert (reading.heterogeneous_permutation, reading.heterogeneous_ablation) == (True, False)
    swapped = ContributionAgreement.read(
        _report("permutation"),
        _report("loco", _share("price", excludes=True)),
    )
    assert (swapped.heterogeneous_permutation, swapped.heterogeneous_ablation) == (False, True)


def test_different_families_not_sustained() -> None:
    reading = ContributionAgreement.read(
        _report("permutation", _share("price", excludes=True)),
        _report("loco", _share("technical", excludes=True)),
    )
    assert reading.sustained is False
    assert (reading.heterogeneous_permutation, reading.heterogeneous_ablation) == (True, True)


def test_undefined_family_never_agrees() -> None:
    reading = ContributionAgreement.read(
        _report("permutation", _share("price", excludes=True)),
        _report("loco", _share("price", excludes=True, ok=False)),
    )
    assert reading.sustained is False
    assert reading.status == "ok"


@pytest.mark.parametrize("which", ["permutation", "loco", "both"])
def test_any_undefined_method_gives_undefined_with_reason(which: str) -> None:
    permutation = _report(
        "permutation", _share("price", excludes=True), undefined=which in {"permutation", "both"}
    )
    ablation = _report("loco", _share("price", excludes=True), undefined=which in {"loco", "both"})

    reading = ContributionAgreement.read(permutation, ablation)

    assert reading.sustained is False
    assert reading.status == "undefined"
    assert "H3-NEG" in str(reading.reason)
    if which in {"permutation", "both"}:
        assert reading.heterogeneous_permutation is None
        assert "permutation:" in str(reading.reason)
    else:
        assert reading.heterogeneous_permutation is True
    if which in {"loco", "both"}:
        assert reading.heterogeneous_ablation is None
        assert "loco:" in str(reading.reason)


def test_label_is_exact() -> None:
    reading = ContributionAgreement.read(_report("permutation"), _report("loco"))
    assert H3_LABEL == "descritiva (sem claim causal)"
    assert reading.label == H3_LABEL
