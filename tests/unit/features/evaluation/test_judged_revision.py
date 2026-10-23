"""Testes de `resolve_judged_revision` (Stage 8.1 Task 06, A3).

A validação extraída do `BuildConfirmatoryScorecard`: cadeia → hash → âncora, nessa
ordem, devolvendo todos os registros e planos da cadeia. Com o
`InMemoryPreregistrationSource` e o `FloatRefusingHasher` (o mesmo da suíte do scorecard).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    PreregistrationChainError,
    PreregistrationHashMismatchError,
    PreregistrationNotAnchoredError,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationAnchor,
)
from financial_forecasting.features.evaluation.application.use_cases.judged_revision import (
    JudgedRevision,
    resolve_judged_revision,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from tests.fakes.features.evaluation.in_memory_preregistration_source import (
    InMemoryPreregistrationSource,
)
from tests.unit.features.evaluation._preregistration_payload import (
    FloatRefusingHasher,
    valid_payload,
)

_NAME = "test_plan"
_WRONG = "test_plan-r0-000000000000"


def _reference(payload: dict[str, object]) -> str:
    plan = Preregistration.from_mapping(payload)
    digest = PreregistrationHash.compute(hasher=FloatRefusingHasher(), payload=plan.as_payload())
    return str(plan.reference(digest))


def _anchor(reference: str) -> PreregistrationAnchor:
    return PreregistrationAnchor(
        tag=f"preregistration/{reference}",
        commit="0123456789abcdef0123456789abcdef01234567",
        comment_url="https://github.com/example/repo/issues/1#issuecomment-1",
        anchored_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def _r1(amends: str) -> dict[str, object]:
    return {
        **valid_payload(),
        "revision": 1,
        "amends": amends,
        "justification": "a blinded fix",
        "blind_status": "blinded",
    }


def _source(
    r1_amends: str | None = None, *, anchors: tuple[bool, bool] = (True, True)
) -> tuple[InMemoryPreregistrationSource, str, str]:
    source = InMemoryPreregistrationSource()
    reference0 = _reference(valid_payload())
    payload1 = _r1(reference0 if r1_amends is None else r1_amends)
    reference1 = _reference(payload1)
    source.add(_NAME, 0, valid_payload(), _anchor(reference0) if anchors[0] else None)
    source.add(_NAME, 1, payload1, _anchor(reference1) if anchors[1] else None)
    return source, reference0, reference1


def _resolve(
    source: InMemoryPreregistrationSource, reference: str, revision: int = 1
) -> JudgedRevision:
    return resolve_judged_revision(
        source=source,
        hasher=FloatRefusingHasher(),
        name=_NAME,
        revision=revision,
        preregistration_ref=reference,
    )


@pytest.mark.unit
def test_returns_every_record_plan_and_the_chain() -> None:
    source, reference0, reference1 = _source()

    judged = _resolve(source, reference1)

    assert judged.chain == (reference0, reference1)
    assert [plan.revision for plan in judged.plans] == [0, 1]
    assert len(judged.records) == 2  # noqa: PLR2004 — r0 e r1
    assert judged.plan is judged.plans[-1]
    assert judged.reference == reference1
    assert judged.anchor == _anchor(reference1)
    assert source.reads == [(_NAME, 0), (_NAME, 1)]


@pytest.mark.unit
def test_broken_chain_raises_chain_error() -> None:
    source, _, reference1 = _source(r1_amends=_WRONG)

    with pytest.raises(PreregistrationChainError, match="amends"):
        _resolve(source, reference1)


@pytest.mark.unit
def test_hash_mismatch_raises() -> None:
    source, _, _ = _source()

    with pytest.raises(PreregistrationHashMismatchError, match="the command expects"):
        _resolve(source, "test_plan-r1-000000000000")


@pytest.mark.unit
def test_unanchored_revision_raises() -> None:
    source, _, reference1 = _source(anchors=(False, True))

    with pytest.raises(PreregistrationNotAnchoredError, match=r"revisions \[0\]"):
        _resolve(source, reference1)


@pytest.mark.unit
def test_anchor_of_another_reference_raises() -> None:
    source, _, reference1 = _source()
    source.add(_NAME, 1, _r1(_reference(valid_payload())), _anchor("test_plan-r9-000000000000"))

    with pytest.raises(PreregistrationNotAnchoredError, match=r"revisions \[1\]"):
        _resolve(source, reference1)


@pytest.mark.unit
def test_errors_in_the_same_order_as_the_scorecard() -> None:
    """Cadeia quebrada e hash divergente → erro de cadeia; hash e âncora → erro de hash."""
    broken, _, _ = _source(r1_amends=_WRONG, anchors=(False, False))
    with pytest.raises(PreregistrationChainError):
        _resolve(broken, "test_plan-r1-000000000000")

    unanchored, _, _ = _source(anchors=(False, False))
    with pytest.raises(PreregistrationHashMismatchError):
        _resolve(unanchored, "test_plan-r1-000000000000")


@pytest.mark.unit
def test_judged_revision_requires_aligned_non_empty_chain() -> None:
    source, _, reference1 = _source()
    judged = _resolve(source, reference1)

    with pytest.raises(ValueError, match="same length"):
        JudgedRevision(
            records=judged.records, plans=judged.plans[:1], chain=judged.chain, anchor=judged.anchor
        )
    with pytest.raises(ValueError, match="non-empty"):
        JudgedRevision(records=(), plans=(), chain=(), anchor=judged.anchor)
