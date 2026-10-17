"""Unit da política de reprodução no domain do `inference` (Stage 7.2, Task 01; ADR 7.2.0005)."""

from __future__ import annotations

import math

from financial_forecasting.features.inference.domain.services.reproduction_policy import (
    STRICT,
    TOLERANCE,
    TOLERANCE_ATOL,
    TOLERANCE_RTOL,
    ReproductionComparison,
    ReproductionMode,
    compare_reproduction,
    reproduction_mode,
    within_mode,
)

_IGNORED = frozenset({"git_sha", "code_dirty"})
_BASE = {"torch": "2.5.1", "cpu": "x86", "git_sha": "aaa", "code_dirty": "false"}


def test_equal_non_ignored_keys_without_justification_is_strict() -> None:
    mode = reproduction_mode(dict(_BASE), dict(_BASE), None, ignored_keys=_IGNORED)
    assert mode == ReproductionMode(STRICT, "non-code keys equal", forced=False)


def test_difference_only_in_an_ignored_key_stays_strict() -> None:
    current = {**_BASE, "git_sha": "bbb", "code_dirty": "true"}
    mode = reproduction_mode(dict(_BASE), current, None, ignored_keys=_IGNORED)
    assert mode.name == STRICT
    # sem a lista de ignoradas, a mesma diferença vira tolerance
    assert reproduction_mode(dict(_BASE), current, None, ignored_keys=frozenset()).name == TOLERANCE


def test_differing_key_is_tolerance_with_sorted_keys_in_reason() -> None:
    current = {**_BASE, "torch": "2.6.0", "cpu": "arm"}
    del current["git_sha"]
    extra_ref = {**_BASE, "zeta": "1"}
    mode = reproduction_mode(extra_ref, current, None, ignored_keys=_IGNORED)
    assert mode == ReproductionMode(
        TOLERANCE, "non-code keys differ: ['cpu', 'torch', 'zeta']", forced=False
    )


def test_justification_with_equal_keys_forces_tolerance() -> None:
    mode = reproduction_mode(dict(_BASE), dict(_BASE), "[finding] x", ignored_keys=_IGNORED)
    assert mode == ReproductionMode(TOLERANCE, "forced: cross-environment", forced=True)


def test_differing_keys_win_over_justification() -> None:
    current = {**_BASE, "torch": "2.6.0"}
    mode = reproduction_mode(dict(_BASE), current, "[finding] x", ignored_keys=_IGNORED)
    assert mode.name == TOLERANCE
    assert mode.forced is False
    assert mode.reason == "non-code keys differ: ['torch']"


def test_within_mode_strict_is_exact_equality() -> None:
    ref = 0.123
    assert within_mode(new=ref, ref=ref, center=0.0, scale=1.0, mode=STRICT)
    assert not within_mode(
        new=math.nextafter(ref, math.inf), ref=ref, center=0.0, scale=1.0, mode=STRICT
    )


def test_within_mode_tolerance_boundary() -> None:
    # Escala potência de 2 e z_ref = 0 deixam o limite exatamente representável.
    scale, center, ref = 0.5, 0.25, 0.25
    allowed = TOLERANCE_ATOL * scale
    at_limit = ref + allowed
    assert abs(at_limit - ref) / scale <= TOLERANCE_ATOL
    assert within_mode(new=at_limit, ref=ref, center=center, scale=scale, mode=TOLERANCE)
    above = math.nextafter(at_limit, math.inf)
    assert not within_mode(new=above, ref=ref, center=center, scale=scale, mode=TOLERANCE)
    # o termo relativo usa |z_ref|: longe do centro o limite cresce
    far = 10.0
    bound = (TOLERANCE_ATOL + TOLERANCE_RTOL * abs((far - center) / scale)) * scale
    assert within_mode(new=far + 0.99 * bound, ref=far, center=center, scale=scale, mode=TOLERANCE)
    assert not within_mode(
        new=far + 1.01 * bound, ref=far, center=center, scale=scale, mode=TOLERANCE
    )


def test_tolerance_constants() -> None:
    assert (STRICT, TOLERANCE) == ("strict", "tolerance")
    assert (TOLERANCE_ATOL, TOLERANCE_RTOL) == (1e-5, 1.3e-6)  # float32 do assert_close


def test_compare_reproduction_counts_failures_and_max_diffs() -> None:
    reference = {(0, 1, 0.1): 1.0, (0, 1, 0.5): 2.0, (1, 1, 0.1): 3.0}
    predicted = {(0, 1, 0.1): 1.0, (0, 1, 0.5): 2.5, (1, 1, 0.1): 2.75}
    got = compare_reproduction(reference, predicted, mode=STRICT, center=0.0, scale=2.0)
    assert got == ReproductionComparison(
        compared=3, failures=2, missing=0, extra=0, max_abs_diff=0.5, max_normalized_diff=0.25
    )
    # o mesmo par em tolerance larga não falha, e as diferenças máximas não mudam
    exact = compare_reproduction(reference, dict(reference), mode=TOLERANCE, center=0.0, scale=2.0)
    assert (exact.failures, exact.max_abs_diff, exact.max_normalized_diff) == (0, 0.0, 0.0)


def test_compare_reproduction_reports_missing_and_extra_keys() -> None:
    reference = {(0, 1, 0.1): 1.0, (0, 1, 0.5): 2.0, (0, 1, 0.9): 3.0}
    predicted = {(0, 1, 0.1): 1.0, (0, 2, 0.1): 9.0}
    got = compare_reproduction(reference, predicted, mode=STRICT, center=0.0, scale=1.0)
    assert (got.compared, got.missing, got.extra, got.failures) == (1, 2, 1, 0)
    assert got.max_abs_diff == 0.0


def test_compare_reproduction_with_nothing_compared() -> None:
    got = compare_reproduction({}, {(0, 1, 0.1): 1.0}, mode=STRICT, center=0.0, scale=1.0)
    assert got.compared == 0
    assert (got.missing, got.extra, got.failures) == (0, 1, 0)
    empty = compare_reproduction({}, {}, mode=STRICT, center=0.0, scale=1.0)
    assert empty == ReproductionComparison(0, 0, 0, 0, 0.0, 0.0)
