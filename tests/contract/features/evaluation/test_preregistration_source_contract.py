"""Contract test do port `PreregistrationSource` — suíte ÚNICA para o fake e o real.

Prova (concept 6.5 A9, C2; ADR 6.5.0003 itens 2-3) que toda implementação devolve o
payload cru da revisão igual ao gravado, ergue `PreregistrationNotFoundError` para
revisão inexistente, devolve `anchor is None` sem âncora e uma
`PreregistrationAnchor` com fuso UTC com âncora, e recusa âncora sem fuso.

Pernas (*harness*): `fake` (`InMemoryPreregistrationSource`) e `toml`
(`TomlPreregistrationSource` num `tmp_path`, com o plano e a âncora gravados pelo
escritor de teste `to_toml` — nenhum TOML escrito à mão), sem `skipif`. Os testes
`real_*` são só do adapter: âncora com chave a mais, TOML malformado e `name` que
não é identificador de caminho (antes de tocar o disco).

Stage 8.1 (Task 07; concept 8.1 §4, D12): `judged_records` — vazio sem arquivo, ida e
volta de todos os campos, ordenado pela revisão; na perna real, chave a mais ou a menos,
tag que não é `confirmatory-run/<ref>` e `commented_at` sem ser date-time com fuso.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pytest

from financial_forecasting.features.evaluation.adapters.out.toml.toml_preregistration_source import (  # noqa: E501
    TomlPreregistrationSource,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    JudgedRecord,
    PreregistrationAnchor,
    PreregistrationNotFoundError,
    PreregistrationSource,
)
from tests.fakes.features.evaluation.in_memory_preregistration_source import (
    InMemoryPreregistrationSource,
)
from tests.unit.features.evaluation._preregistration_payload import (
    PAYLOAD_TOML,
    to_toml,
    valid_payload,
)

_NAME = "test_plan"
_ANCHOR: dict[str, object] = {
    "tag": "preregistration/test_plan-r0-0123456789ab",
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "comment_url": "https://github.com/example/repo/issues/1#issuecomment-1",
    "anchored_at": datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
}


class Harness(Protocol):
    source: PreregistrationSource

    def put(
        self, revision: int, payload: Mapping[str, object], anchor: Mapping[str, object] | None
    ) -> None: ...

    def put_judged(self, revision: int, fields: Mapping[str, object]) -> None: ...


class _FakeHarness:
    def __init__(self, _: Path) -> None:
        self.fake = InMemoryPreregistrationSource()
        self.source: PreregistrationSource = self.fake

    def put(
        self, revision: int, payload: Mapping[str, object], anchor: Mapping[str, object] | None
    ) -> None:
        built = None if anchor is None else PreregistrationAnchor(**anchor)  # type: ignore[arg-type]
        self.fake.add(_NAME, revision, payload, built)

    def put_judged(self, revision: int, fields: Mapping[str, object]) -> None:
        status = RefreshStatus(str(fields["refresh_status"]))
        record = JudgedRecord(**{**fields, "refresh_status": status, "revision": revision})  # type: ignore[arg-type]
        self.fake.add_judged(_NAME, record)


class _TomlHarness:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.source: PreregistrationSource = TomlPreregistrationSource(root)

    def put(
        self, revision: int, payload: Mapping[str, object], anchor: Mapping[str, object] | None
    ) -> None:
        text = PAYLOAD_TOML if payload == valid_payload() else to_toml(payload)
        (self.root / f"{_NAME}-r{revision}.toml").write_text(text, encoding="utf-8")
        if anchor is not None:
            (self.root / f"{_NAME}-r{revision}.anchor.toml").write_text(
                to_toml(anchor), encoding="utf-8"
            )

    def put_judged(self, revision: int, fields: Mapping[str, object]) -> None:
        path = self.root / f"{_NAME}-r{revision}.judged.toml"
        path.write_text(to_toml(fields), encoding="utf-8")


HARNESSES: dict[str, Callable[[Path], Harness]] = {"fake": _FakeHarness, "toml": _TomlHarness}


@pytest.fixture(params=list(HARNESSES), ids=list(HARNESSES))
def harness(request: pytest.FixtureRequest, tmp_path: Path) -> Harness:
    return HARNESSES[request.param](tmp_path)


@pytest.mark.contract
def test_source_reads_payload(harness: Harness) -> None:
    harness.put(0, valid_payload(), None)

    record = harness.source.read(name=_NAME, revision=0)

    assert record.payload == valid_payload()
    record.payload["name"] = "changed"  # type: ignore[index]
    assert harness.source.read(name=_NAME, revision=0).payload == valid_payload()


@pytest.mark.contract
def test_source_missing_revision_raises(harness: Harness) -> None:
    harness.put(0, valid_payload(), None)

    with pytest.raises(PreregistrationNotFoundError, match="revision 1"):
        harness.source.read(name=_NAME, revision=1)
    with pytest.raises(PreregistrationNotFoundError):
        harness.source.read(name="other_plan", revision=0)


@pytest.mark.contract
def test_source_anchor_absent_none(harness: Harness) -> None:
    harness.put(0, valid_payload(), None)

    assert harness.source.read(name=_NAME, revision=0).anchor is None


@pytest.mark.contract
def test_source_anchor_present_parsed(harness: Harness) -> None:
    harness.put(0, valid_payload(), _ANCHOR)

    record = harness.source.read(name=_NAME, revision=0)
    anchor = record.anchor

    assert record.payload == valid_payload()
    assert anchor == PreregistrationAnchor(**_ANCHOR)  # type: ignore[arg-type]
    assert anchor is not None
    assert anchor.anchored_at.utcoffset() is not None
    assert anchor.anchored_at.astimezone(UTC) == datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.mark.contract
def test_source_anchor_naive_rejected(harness: Harness) -> None:
    naive = {**_ANCHOR, "anchored_at": datetime(2026, 10, 1, 12, 0)}

    with pytest.raises(ValueError, match="timezone-aware"):
        harness.put(0, valid_payload(), naive)
        harness.source.read(name=_NAME, revision=0)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"tag": "v1"}, "anchor tag must start with 'preregistration/'", id="tag"),
        pytest.param({"commit": ""}, "anchor commit must be a non-empty str", id="commit"),
        pytest.param({"commit": 7}, "anchor commit must be a non-empty str", id="commit-int"),
        pytest.param({"comment_url": ""}, "anchor comment_url must be a non-empty", id="url"),
    ],
)
def test_source_anchor_invariants_rejected(
    harness: Harness, changes: dict[str, object], message: str
) -> None:
    """Checkpoint C bloco 2, F5/R1: as invariantes da âncora valem nas duas pernas."""
    with pytest.raises(ValueError, match=message):
        harness.put(0, valid_payload(), {**_ANCHOR, **changes})
        harness.source.read(name=_NAME, revision=0)


@pytest.mark.contract
def test_real_anchor_extra_key_rejected(tmp_path: Path) -> None:
    _TomlHarness(tmp_path).put(0, valid_payload(), {**_ANCHOR, "note": "x"})

    with pytest.raises(ValueError, match="must have exactly the keys"):
        TomlPreregistrationSource(tmp_path).read(name=_NAME, revision=0)
    missing = {k: v for k, v in _ANCHOR.items() if k != "commit"}
    _TomlHarness(tmp_path).put(0, valid_payload(), missing)
    with pytest.raises(ValueError, match="must have exactly the keys"):
        TomlPreregistrationSource(tmp_path).read(name=_NAME, revision=0)


@pytest.mark.contract
def test_real_malformed_toml_raises(tmp_path: Path) -> None:
    (tmp_path / f"{_NAME}-r0.toml").write_text(PAYLOAD_TOML + "\n[cohort\n", encoding="utf-8")

    with pytest.raises(ValueError, match=rf"{_NAME}-r0\.toml is not valid TOML"):
        TomlPreregistrationSource(tmp_path).read(name=_NAME, revision=0)


@pytest.mark.contract
@pytest.mark.parametrize("name", ["../escape", "a/b", "a b"])
def test_real_name_identifier_checked(tmp_path: Path, name: str) -> None:
    root = tmp_path / "missing-root"

    with pytest.raises(ValueError, match="name must match"):
        TomlPreregistrationSource(root).read(name=name, revision=0)
    with pytest.raises(ValueError, match="revision must be an int >= 0"):
        TomlPreregistrationSource(root).read(name=_NAME, revision=True)
    with pytest.raises(ValueError, match="revision must be an int >= 0"):
        TomlPreregistrationSource(root).read(name=_NAME, revision=-1)
    assert not root.exists()


# --- extras da auditoria de testes (rodada 1) -----------------------------------------


@pytest.mark.contract
def test_real_anchor_date_not_datetime(tmp_path: Path) -> None:
    """Auditoria (cobertura): `anchored_at` como texto (não date-time TOML) é recusado."""
    _TomlHarness(tmp_path).put(0, valid_payload(), {**_ANCHOR, "anchored_at": "2026-10-01"})

    with pytest.raises(ValueError, match="anchored_at must be a TOML date-time"):
        TomlPreregistrationSource(tmp_path).read(name=_NAME, revision=0)


# --- extras da auditoria de testes (rodada 2) -----------------------------------------


@pytest.mark.contract
def test_source_anchor_per_revision(harness: Harness) -> None:
    """Auditoria N5: a âncora é a da revisão pedida (não a da r0)."""
    commit_a, commit_b = "a" * 40, "b" * 40
    harness.put(0, valid_payload(), {**_ANCHOR, "commit": commit_a})
    harness.put(1, valid_payload(), None)

    assert harness.source.read(name=_NAME, revision=1).anchor is None
    anchor0 = harness.source.read(name=_NAME, revision=0).anchor
    assert anchor0 is not None
    assert anchor0.commit == commit_a
    harness.put(1, valid_payload(), {**_ANCHOR, "commit": commit_b})
    anchor1 = harness.source.read(name=_NAME, revision=1).anchor
    assert anchor1 is not None
    assert anchor1.commit == commit_b


# --- Stage 8.1: registros `.judged.toml` (Task 07) -------------------------------------


def _judged(revision: int, **changes: object) -> dict[str, object]:
    reference = f"{_NAME}-r{revision}-0123456789ab"
    fields: dict[str, object] = {
        "preregistration_ref": reference,
        "generation_digest": "ab" * 32,
        "refresh_status": "COMPLETED",
        "commit": "0123456789abcdef0123456789abcdef01234567",
        "tag": f"confirmatory-run/{reference}",
        "comment_url": "https://github.com/example/repo/issues/211#issuecomment-2",
        "commented_at": datetime(2026, 10, 23, 9, 30, tzinfo=UTC),
        "input_backup": "/backups/aapl-input-2026-10-23",
        "input_backup_sha256": "cd" * 32,
        "judged_backup": "/backups/aapl-judged-2026-10-23",
        "judged_backup_sha256": "ef" * 32,
    }
    fields.update(changes)
    return fields


@pytest.mark.contract
def test_judged_records_empty_without_files(harness: Harness) -> None:
    harness.put(0, valid_payload(), _ANCHOR)

    assert harness.source.judged_records(name=_NAME) == ()


@pytest.mark.contract
def test_judged_record_round_trip(harness: Harness) -> None:
    fields = _judged(3)
    harness.put_judged(3, fields)

    [record] = harness.source.judged_records(name=_NAME)

    assert record == JudgedRecord(
        **{**fields, "refresh_status": RefreshStatus.COMPLETED, "revision": 3}  # type: ignore[arg-type]
    )
    assert record.commented_at.utcoffset() is not None
    assert record.tag == f"confirmatory-run/{record.preregistration_ref}"


@pytest.mark.contract
def test_judged_records_sorted_by_revision(harness: Harness) -> None:
    for revision in (10, 2, 3):
        harness.put_judged(revision, _judged(revision, refresh_status="BLOCKED"))

    records = harness.source.judged_records(name=_NAME)

    assert [record.revision for record in records] == [2, 3, 10]
    assert {record.refresh_status for record in records} == {RefreshStatus.BLOCKED}


@pytest.mark.contract
def test_judged_file_with_extra_or_missing_key_raises(tmp_path: Path) -> None:
    harness = _TomlHarness(tmp_path)
    harness.put_judged(3, {**_judged(3), "note": "x"})
    with pytest.raises(ValueError, match="must have exactly the keys"):
        TomlPreregistrationSource(tmp_path).judged_records(name=_NAME)

    harness.put_judged(3, {k: v for k, v in _judged(3).items() if k != "judged_backup"})
    with pytest.raises(ValueError, match="must have exactly the keys"):
        TomlPreregistrationSource(tmp_path).judged_records(name=_NAME)


@pytest.mark.contract
@pytest.mark.parametrize(
    "tag",
    ["preregistration/test_plan-r3-0123456789ab", "confirmatory-run/test_plan-r2-0123456789ab"],
    ids=["anchor-prefix", "other-reference"],
)
def test_judged_tag_must_be_confirmatory_run_of_its_reference(tmp_path: Path, tag: str) -> None:
    _TomlHarness(tmp_path).put_judged(3, _judged(3, tag=tag))

    with pytest.raises(ValueError, match="judged tag must be"):
        TomlPreregistrationSource(tmp_path).judged_records(name=_NAME)


@pytest.mark.contract
def test_commented_at_must_be_offset_datetime(tmp_path: Path) -> None:
    harness = _TomlHarness(tmp_path)
    harness.put_judged(3, _judged(3, commented_at="2026-10-23T09:30:00+00:00"))
    with pytest.raises(ValueError, match="commented_at must be a TOML date-time"):
        TomlPreregistrationSource(tmp_path).judged_records(name=_NAME)

    harness.put_judged(3, _judged(3, commented_at=datetime(2026, 10, 23, 9, 30)))
    with pytest.raises(ValueError, match="commented_at must be a timezone-aware datetime"):
        TomlPreregistrationSource(tmp_path).judged_records(name=_NAME)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"refresh_status": "RUNNING"}, "is not a valid RefreshStatus"),
        ({"commit": "ABC"}, "judged commit must be 40 lowercase hex"),
        ({"generation_digest": "xyz"}, r"judged generation_digest must be a lowercase sha256"),
        ({"input_backup": ""}, "judged input_backup must be a non-empty str"),
    ],
    ids=["status", "commit", "digest", "backup"],
)
def test_real_judged_fields_validated(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    _TomlHarness(tmp_path).put_judged(3, _judged(3, **changes))

    with pytest.raises(ValueError, match=message):
        TomlPreregistrationSource(tmp_path).judged_records(name=_NAME)
