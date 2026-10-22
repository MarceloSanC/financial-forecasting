"""Contract test do port `JudgedGenerationStore` — suíte ÚNICA para o fake e o real (A6).

Prova (concept 8.1 A6, D5, D12, I9; ADRs 8.1.0003 itens 3-5b e 8.1.0004 item 1) que toda
implementação copia a geração viva, sela com `CONTENTS.sha256` por último, relê
conferindo o digest, recusa adulteração, nunca sobrescreve uma cópia selada, não sela
nada quando o manifesto diverge ou a escrita falha, limpa o staging sobrante e guarda o
log de tentativas em ordem.

Pernas (*harness*): `fake` (`InMemoryJudgedGenerationStore` sobre o `InMemoryGoldStore`)
e `parquet` (o `ParquetGoldStore` num `tmp_path`, que satisfaz `GoldStore` e
`JudgedGenerationStore`), sem `skipif`. Os testes `real_*` são só do adapter: bytes da
cópia iguais aos de `current/`, ordem de escrita e `mtime_ns`, `sha256sum -c` em
subprocesso e o identificador da referência validado antes de montar caminho.
"""

from __future__ import annotations

import dataclasses
import hashlib
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import pytest

from financial_forecasting.features.evaluation.adapters.out.duckdb import (
    parquet_gold_store as parquet_gold_store_module,
)
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    CONTENTS_NAME,
    GENERATION_DIR,
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
    AttemptPhase,
    JudgedAttempt,
    contents_listing,
    generation_digest_of,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldManifest,
    GoldManifestNotFoundError,
    GoldTable,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_store import (
    GoldStore,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationExistsError,
    JudgedGenerationMismatchError,
    JudgedGenerationStore,
    JudgedGenerationTamperedError,
)
from tests.contract.features.evaluation.test_gold_store_contract import (
    _PARTITION,
    _manifest,
    _table,
)
from tests.fakes.features.evaluation.in_memory_gold_store import InMemoryGoldStore
from tests.fakes.features.evaluation.in_memory_judged_generation_store import (
    InMemoryJudgedGenerationStore,
)
from tests.unit.features.evaluation._silver_content import SAMPLE_SILVER_CONTENT

_REF = "test_plan-r3-0123456789ab"
_OTHER_REF = "test_plan-r2-ba9876543210"
_TABLE = "gold_quality_checks"
_DOCUMENTS: dict[str, dict[str, object]] = {
    SCORECARD_DOCUMENT: {"verdict": {"h1": "sustained"}, "academic_decision_ready": True},
    RUN_RECORD_DOCUMENT: {"commit": "0" * 40, "attempts": []},
}


class Harness(Protocol):
    gold: GoldStore
    judged: JudgedGenerationStore

    def live_files(self) -> set[str]: ...

    def sealed_bytes(self, ref: str, path: str) -> bytes: ...

    def tamper(self, ref: str, path: str, data: bytes | None) -> None: ...

    def rewrite_contents(self, ref: str) -> None: ...

    def leave_staging(self) -> None: ...

    def staging_exists(self) -> bool: ...

    def fail_writes(self, names: set[str]) -> None: ...


class _FakeHarness:
    def __init__(self, _root: Path, _monkeypatch: pytest.MonkeyPatch) -> None:
        self._gold = InMemoryGoldStore()
        self._judged = InMemoryJudgedGenerationStore(self._gold)
        self.gold: GoldStore = self._gold
        self.judged: JudgedGenerationStore = self._judged

    def live_files(self) -> set[str]:
        live = self._gold.current(_PARTITION)
        assert live is not None
        return {"MANIFEST.json", *(f"{name}.parquet" for name in live[1])}

    def sealed_bytes(self, ref: str, path: str) -> bytes:
        return self._judged._sealed[_PARTITION, ref][path]

    def tamper(self, ref: str, path: str, data: bytes | None) -> None:
        self._judged.tamper(partition=_PARTITION, preregistration_ref=ref, path=path, data=data)

    def rewrite_contents(self, ref: str) -> None:
        self._judged.rewrite_contents(partition=_PARTITION, preregistration_ref=ref)

    def leave_staging(self) -> None:
        self._judged.leave_staging(_PARTITION)

    def staging_exists(self) -> bool:
        return self._judged.staging_exists(_PARTITION)

    def fail_writes(self, names: set[str]) -> None:
        self._judged.fail_writes = set(names)


class _ParquetHarness:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.store = ParquetGoldStore(root)
        self.gold: GoldStore = self.store
        self.judged: JudgedGenerationStore = self.store
        self._monkeypatch = monkeypatch
        self.judged_root: Path = self.store.partition_root(_PARTITION) / "judged"
        self._write_bytes = parquet_gold_store_module._write_bytes

    def live_files(self) -> set[str]:
        return {path.name for path in self.store.current_dir(_PARTITION).iterdir()}

    def sealed_bytes(self, ref: str, path: str) -> bytes:
        return (self.judged_root / ref / path).read_bytes()

    def tamper(self, ref: str, path: str, data: bytes | None) -> None:
        target = self.judged_root / ref / path
        if data is None:
            target.unlink()
        else:
            target.write_bytes(data)

    def rewrite_contents(self, ref: str) -> None:
        directory = self.judged_root / ref
        actual = {
            path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*")
            if path.is_file() and path.name != CONTENTS_NAME
        }
        (directory / CONTENTS_NAME).write_bytes(contents_listing(actual))

    def leave_staging(self) -> None:
        leftover = self.judged_root / ".staging" / GENERATION_DIR
        leftover.mkdir(parents=True)
        (leftover / "leftover.parquet").write_bytes(b"partial")

    def staging_exists(self) -> bool:
        return (self.judged_root / ".staging").exists()

    def fail_writes(self, names: set[str]) -> None:
        real = self._write_bytes

        def failing(path: Path, data: bytes) -> None:
            if path.name in names:
                raise OSError(f"injected write failure on {path.name}")
            real(path, data)

        self._monkeypatch.setattr(parquet_gold_store_module, "_write_bytes", failing)


HARNESSES: dict[str, Callable[[Path, pytest.MonkeyPatch], Harness]] = {
    "fake": _FakeHarness,
    "parquet": _ParquetHarness,
}


@pytest.fixture(params=list(HARNESSES), ids=list(HARNESSES))
def harness(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Harness:
    return HARNESSES[request.param](tmp_path, monkeypatch)


def _tables() -> list[GoldTable]:
    return [_table(_TABLE, 4), _table("gold_dm_results", 6)]


def _publish(harness: Harness, tables: list[GoldTable] | None = None) -> GoldManifest:
    chosen = _tables() if tables is None else tables
    manifest = _manifest(chosen)
    harness.gold.publish(partition=_PARTITION, tables=chosen, manifest=manifest)
    return manifest


def _preserve(harness: Harness, manifest: GoldManifest, ref: str = _REF) -> object:
    return harness.judged.preserve(
        partition=_PARTITION,
        preregistration_ref=ref,
        expected_manifest=manifest,
        documents=_DOCUMENTS,
    )


def _find(harness: Harness, ref: str = _REF) -> object:
    return harness.judged.find(partition=_PARTITION, preregistration_ref=ref)


def _attempt(minutes: int) -> JudgedAttempt:
    started_at = datetime(2026, 10, 23, 9, 0, tzinfo=UTC) + timedelta(minutes=minutes)
    return JudgedAttempt(
        phase=AttemptPhase.STARTED,
        attempt_id=started_at.isoformat(),
        preregistration_ref=_REF,
        commit="0123456789abcdef0123456789abcdef01234567",
        code={"code.src": "a" * 64, "code.uv_lock": "b" * 64},
        environment={"env.image_id": "sha256:" + "c" * 64},
        started_at=started_at,
    )


# --- selagem e leitura ----------------------------------------------------------------


@pytest.mark.contract
def test_preserve_copies_current_and_seals_last(harness: Harness) -> None:
    manifest = _publish(harness)

    sealed = harness.judged.preserve(
        partition=_PARTITION,
        preregistration_ref=_REF,
        expected_manifest=manifest,
        documents=_DOCUMENTS,
    )

    generation = {path for path in sealed.files if path.startswith(f"{GENERATION_DIR}/")}
    assert generation
    assert generation == {f"{GENERATION_DIR}/{name}" for name in harness.live_files()}
    assert set(sealed.files) - generation == set(_DOCUMENTS)
    assert CONTENTS_NAME not in sealed.files
    assert sealed.refresh_status is manifest.status
    assert sealed.preregistration_ref == _REF


@pytest.mark.contract
def test_generation_digest_is_sha256_of_contents_file(harness: Harness) -> None:
    sealed = harness.judged.preserve(
        partition=_PARTITION,
        preregistration_ref=_REF,
        expected_manifest=_publish(harness),
        documents=_DOCUMENTS,
    )

    contents = harness.sealed_bytes(_REF, CONTENTS_NAME)
    assert contents == contents_listing(sealed.files)
    assert sealed.generation_digest == generation_digest_of(contents)
    assert sealed.generation_digest == hashlib.sha256(contents).hexdigest()


@pytest.mark.contract
def test_find_returns_none_without_copy(harness: Harness) -> None:
    assert _find(harness) is None
    _publish(harness)
    assert _find(harness) is None


@pytest.mark.contract
def test_find_round_trip_with_manifest_and_documents(harness: Harness) -> None:
    manifest = _publish(harness)
    sealed = _preserve(harness, manifest)

    found = harness.judged.find(partition=_PARTITION, preregistration_ref=_REF)

    assert found == sealed
    assert found is not None
    assert found.manifest == manifest
    assert found.manifest.silver_content == SAMPLE_SILVER_CONTENT
    assert found.documents == _DOCUMENTS


@pytest.mark.contract
@pytest.mark.parametrize(
    "damage", ["altered-byte", "missing-file", "extra-file", "empty-generation", "no-contents"]
)
def test_find_refuses_tampered_copy(harness: Harness, damage: str) -> None:
    """`_altered_byte` / `_missing_file` / `_extra_file` / `_empty_generation_dir`."""
    _preserve(harness, _publish(harness))
    table = f"{GENERATION_DIR}/{_TABLE}.parquet"
    if damage == "altered-byte":
        original = harness.sealed_bytes(_REF, table)
        harness.tamper(_REF, table, bytes([original[0] ^ 0x01]) + original[1:])
    elif damage == "missing-file":
        harness.tamper(_REF, RUN_RECORD_DOCUMENT, None)
    elif damage == "extra-file":
        harness.tamper(_REF, "notes.txt", b"added after the seal")
    elif damage == "empty-generation":
        for name in harness.live_files():
            harness.tamper(_REF, f"{GENERATION_DIR}/{name}", None)
    else:
        harness.tamper(_REF, CONTENTS_NAME, None)

    with pytest.raises(JudgedGenerationTamperedError, match=_REF):
        _find(harness)


@pytest.mark.contract
def test_find_with_coherently_rewritten_contents_returns_new_digest(harness: Harness) -> None:
    """O store não conhece o digest esperado: a comparação com o registro é do use case."""
    sealed = _preserve(harness, _publish(harness))
    harness.tamper(_REF, RUN_RECORD_DOCUMENT, b'{"commit": "rewritten"}\n')
    harness.rewrite_contents(_REF)

    found = harness.judged.find(partition=_PARTITION, preregistration_ref=_REF)

    assert found is not None
    assert found.generation_digest != sealed.generation_digest  # type: ignore[attr-defined]
    assert found.documents[RUN_RECORD_DOCUMENT] == {"commit": "rewritten"}


# --- recusas sem efeito ----------------------------------------------------------------


@pytest.mark.contract
def test_preserve_with_other_manifest_raises_mismatch_and_seals_nothing(harness: Harness) -> None:
    manifest = _publish(harness)
    other = dataclasses.replace(manifest, n_runs=manifest.n_runs + 1)

    with pytest.raises(JudgedGenerationMismatchError):
        _preserve(harness, other)

    assert _find(harness) is None
    assert harness.judged.judged_refs(partition=_PARTITION) == ()
    assert not harness.staging_exists()


@pytest.mark.contract
def test_preserve_over_sealed_raises_exists_and_touches_nothing(harness: Harness) -> None:
    sealed = _preserve(harness, _publish(harness))
    contents = harness.sealed_bytes(_REF, CONTENTS_NAME)
    republished = _publish(harness, [_table(_TABLE, 2, offset=5.0)])

    with pytest.raises(JudgedGenerationExistsError, match=_REF):
        _preserve(harness, republished)

    assert _find(harness) == sealed
    assert harness.sealed_bytes(_REF, CONTENTS_NAME) == contents


@pytest.mark.contract
def test_preserve_without_live_generation_raises_and_seals_nothing(harness: Harness) -> None:
    with pytest.raises(GoldManifestNotFoundError):
        _preserve(harness, _manifest(_tables()))
    assert harness.judged.judged_refs(partition=_PARTITION) == ()


@pytest.mark.contract
def test_preserve_removes_staging_leftover(harness: Harness) -> None:
    manifest = _publish(harness)
    harness.leave_staging()
    assert harness.staging_exists()

    sealed = _preserve(harness, manifest)

    assert f"{GENERATION_DIR}/leftover.parquet" not in sealed.files  # type: ignore[attr-defined]
    assert not harness.staging_exists()


@pytest.mark.contract
@pytest.mark.parametrize(
    "failing", [RUN_RECORD_DOCUMENT, CONTENTS_NAME], ids=["document", "contents"]
)
def test_write_failure_during_preserve_seals_nothing(harness: Harness, failing: str) -> None:
    """I9/E3: a falha propaga, nada é selado; o `preserve` seguinte limpa e sela."""
    manifest = _publish(harness)
    harness.fail_writes({failing})

    with pytest.raises(OSError, match="injected write failure"):
        _preserve(harness, manifest)

    assert _find(harness) is None
    assert harness.judged.judged_refs(partition=_PARTITION) == ()
    harness.fail_writes(set())
    sealed = _preserve(harness, manifest)
    assert _find(harness) == sealed
    assert not harness.staging_exists()


# --- referências e tentativas ------------------------------------------------------------


@pytest.mark.contract
def test_record_attempt_appends_and_attempts_reads_in_order(harness: Harness) -> None:
    assert harness.judged.attempts(partition=_PARTITION) == ()
    attempts = [_attempt(minutes) for minutes in (5, 0, 9)]

    for attempt in attempts:
        harness.judged.record_attempt(partition=_PARTITION, attempt=attempt)

    assert harness.judged.attempts(partition=_PARTITION) == tuple(attempts)


@pytest.mark.contract
def test_judged_refs_lists_sealed_refs_only(harness: Harness) -> None:
    manifest = _publish(harness)
    _preserve(harness, manifest, _REF)
    _preserve(harness, manifest, _OTHER_REF)
    harness.judged.record_attempt(partition=_PARTITION, attempt=_attempt(0))
    harness.leave_staging()

    assert harness.judged.judged_refs(partition=_PARTITION) == tuple(sorted((_REF, _OTHER_REF)))


# --- só a perna real ---------------------------------------------------------------------


def _real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _ParquetHarness:
    return _ParquetHarness(tmp_path, monkeypatch)


@pytest.mark.contract
def test_real_generation_bytes_equal_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _real(tmp_path, monkeypatch)
    _preserve(harness, _publish(harness))

    current = harness.store.current_dir(_PARTITION)
    for path in current.iterdir():
        assert harness.sealed_bytes(_REF, f"{GENERATION_DIR}/{path.name}") == path.read_bytes()


@pytest.mark.contract
def test_contents_written_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _real(tmp_path, monkeypatch)
    manifest = _publish(harness)
    order: list[str] = []
    real = parquet_gold_store_module._write_bytes

    def recording(path: Path, data: bytes) -> None:
        order.append(path.name)
        real(path, data)

    monkeypatch.setattr(parquet_gold_store_module, "_write_bytes", recording)
    _preserve(harness, manifest)

    assert order[-1] == CONTENTS_NAME
    assert set(order[:-1]) == set(_DOCUMENTS)
    directory = harness.judged_root / _REF
    contents_mtime = (directory / CONTENTS_NAME).stat().st_mtime_ns
    others = [
        path for path in directory.rglob("*") if path.is_file() and path.name != CONTENTS_NAME
    ]
    assert others
    assert all(path.stat().st_mtime_ns <= contents_mtime for path in others)


@pytest.mark.contract
def test_sha256sum_check_passes_on_sealed_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _real(tmp_path, monkeypatch)
    sealed = _preserve(harness, _publish(harness))
    directory = harness.judged_root / _REF

    check = subprocess.run(
        ["sha256sum", "-c", CONTENTS_NAME],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )
    digest = subprocess.run(
        ["sha256sum", CONTENTS_NAME],
        cwd=directory,
        capture_output=True,
        text=True,
        check=True,
    )

    assert check.returncode == 0, check.stdout + check.stderr
    assert digest.stdout.split()[0] == sealed.generation_digest  # type: ignore[attr-defined]


@pytest.mark.contract
@pytest.mark.parametrize("ref", ["../escape", "a/b", "a b", ""])
def test_preregistration_ref_validated_as_path_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ref: str
) -> None:
    harness = _real(tmp_path, monkeypatch)
    manifest = _publish(harness)

    with pytest.raises(ValueError, match="preregistration_ref must match"):
        harness.store.find(partition=_PARTITION, preregistration_ref=ref)
    with pytest.raises(ValueError, match="preregistration_ref must match"):
        _preserve(harness, manifest, ref)
    assert not harness.judged_root.exists()
