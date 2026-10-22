"""Testes da regra única de sha de commit git (`validate_git_commit_sha`, Stage 8.1 CC3-3)."""

from __future__ import annotations

import pytest

from financial_forecasting.shared.domain.services.git_commit import validate_git_commit_sha

_SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.unit
def test_accepts_the_rev_parse_output() -> None:
    validate_git_commit_sha(_SHA, field="commit")


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_SHA.upper(), id="upper"),
        pytest.param(_SHA[:-1], id="short"),
        pytest.param(_SHA + "0", id="long"),
        pytest.param(_SHA + "\n", id="trailing-newline"),
        pytest.param("g" * 40, id="not-hex"),
        pytest.param(40, id="not-str"),
        pytest.param(None, id="none"),
    ],
)
def test_refuses_anything_else_naming_the_field(value: object) -> None:
    with pytest.raises(ValueError, match=r"run_record\.commit must be 40 lowercase hex"):
        validate_git_commit_sha(value, field="run_record.commit")
