"""Checagem e gerador do registro da evidência anterior (Stage 8.2, Task 08; A13).

Sempre ativo (roda no CI): Parquet sintético em `tmp_path`; nenhum arquivo de
`data/analytics/` é lido.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tests.equivalence import prior_evidence
from tests.equivalence.prior_evidence import (
    DefinitionSource,
    PriorEvidenceHashError,
    PriorEvidenceRegistryError,
    build_registry,
    load_registry,
    parse_registry,
    registered_path,
    verify_registered_files,
)

pytestmark = pytest.mark.unit

_GOLD = "gold/gold_oos_consolidated.parquet"
_DM = "reports/phase/dm.parquet"


def _write(root: Path, relative: str, columns: dict[str, list[object]]) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(columns), path)  # type: ignore[no-untyped-call]
    return path


@pytest.fixture
def oracle(tmp_path: Path) -> Path:
    root = tmp_path / "analytics"
    _write(root, _GOLD, {"schema_version": [1, 1, 1], "y_true": [0.1, -0.2, 0.3]})
    _write(root, _DM, {"horizon": [1, 7], "label": ["a", "b"]})
    return root


def _registry(oracle: Path, tmp_path: Path, paths: tuple[str, ...] = (_GOLD, _DM)) -> Path:
    path = tmp_path / "registry.toml"
    path.write_text(build_registry(oracle_root=oracle, paths=paths), encoding="utf-8")
    return path


def test_registered_files_matching_pass_and_return_paths(oracle: Path, tmp_path: Path) -> None:
    verified = verify_registered_files(
        oracle_root=oracle, registry=load_registry(_registry(oracle, tmp_path))
    )

    assert dict(verified) == {_GOLD: oracle / _GOLD, _DM: oracle / _DM}


def test_altered_byte_fails(oracle: Path, tmp_path: Path) -> None:
    registry = load_registry(_registry(oracle, tmp_path))
    data = (oracle / _GOLD).read_bytes()
    (oracle / _GOLD).write_bytes(data[:-1] + bytes([data[-1] ^ 0x01]))

    with pytest.raises(PriorEvidenceHashError, match=f"{_GOLD}: sha256"):
        verify_registered_files(oracle_root=oracle, registry=registry)


def test_missing_registered_file_fails(oracle: Path, tmp_path: Path) -> None:
    registry = load_registry(_registry(oracle, tmp_path))
    (oracle / _DM).unlink()

    with pytest.raises(PriorEvidenceHashError, match=f"{_DM}: missing") as exc:
        verify_registered_files(oracle_root=oracle, registry=registry)
    assert exc.value.divergences == (f"{_DM}: missing",)


def _rewritten(text: str, old: str, new: str) -> str:
    assert old in text
    return text.replace(old, new, 1)


@pytest.mark.parametrize("change", ["rows", "type", "name", "order"])
def test_row_count_or_column_type_other_than_registry_fails(
    oracle: Path, tmp_path: Path, change: str
) -> None:
    text = _registry(oracle, tmp_path).read_text(encoding="utf-8")
    edits = {
        "rows": ("rows = 3", "rows = 4"),
        "type": ('name = "y_true", type = "double"', 'name = "y_true", type = "float"'),
        "name": ('name = "y_true"', 'name = "y_pred"'),
        "order": (
            '{ name = "schema_version", type = "int64" }, { name = "y_true", type = "double" }',
            '{ name = "y_true", type = "double" }, { name = "schema_version", type = "int64" }',
        ),
    }
    registry = parse_registry(_rewritten(text, *edits[change]))

    with pytest.raises(PriorEvidenceHashError, match=_GOLD):
        verify_registered_files(oracle_root=oracle, registry=registry)


def test_unregistered_file_in_root_is_never_read(
    oracle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (oracle / "gold" / "unregistered.parquet").write_bytes(b"not even parquet")
    registry = load_registry(_registry(oracle, tmp_path, (_GOLD,)))
    opened: list[Path] = []
    real_sha = prior_evidence.sha256_file

    def recording(path: Path) -> str:
        opened.append(Path(path))
        return real_sha(path)

    monkeypatch.setattr(prior_evidence, "sha256_file", recording)

    verified = verify_registered_files(oracle_root=oracle, registry=registry)

    assert opened == [oracle / _GOLD]
    assert registered_path(verified, _GOLD) == oracle / _GOLD
    for path in ("gold/unregistered.parquet", _DM):
        with pytest.raises(PriorEvidenceHashError, match="not in the registry"):
            registered_path(verified, path)


_VALID = """registry_version = 1
root = "data/analytics"

[[file]]
path = "gold/a.parquet"
sha256 = "{sha}"
rows = 2
columns = [{{ name = "x", type = "int64" }}]
"""


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('sha256 = "' + "a" * 64 + '"', 'sha256 = "xyz"', "not 64 hex"),
        ('sha256 = "' + "a" * 64 + '"', 'sha256 = "' + "A" * 64 + '"', "not 64 hex"),
        ("rows = 2", 'rows = "2"', "rows must be an int"),
        ("rows = 2", "rows = true", "rows must be an int"),
        ("rows = 2", "rows = -1", "rows must be an int"),
        ('path = "gold/a.parquet"', 'path = "/abs/a.parquet"', "path must be relative"),
        ('path = "gold/a.parquet"', 'path = "gold/../a.parquet"', "path must be relative"),
        ('path = "gold/a.parquet"', 'path = "gold\\\\a.parquet"', "relative POSIX"),
        ("registry_version = 1", "registry_version = 2", "registry_version must be 1"),
        ('root = "data/analytics"', 'root = "data"', "root must be"),
        ("rows = 2", "rows = 2\nextra = 1", "must have exactly"),
        ('{ name = "x", type = "int64" }', '{ name = "x" }', "column must be"),
        ("registry_version = 1", "registry_version = 1\nother = 1", "unknown registry keys"),
        ("[[file]]", "[[file]", "not TOML"),
    ],
)
def test_malformed_registry_fails(old: str, new: str, message: str) -> None:
    text = _VALID.format(sha="a" * 64)

    with pytest.raises(PriorEvidenceRegistryError, match=message):
        parse_registry(_rewritten(text, old, new))


def test_registry_without_files_or_with_repeated_path_fails() -> None:
    text = _VALID.format(sha="a" * 64)
    with pytest.raises(PriorEvidenceRegistryError, match="at least one"):
        parse_registry('registry_version = 1\nroot = "data/analytics"\n')
    with pytest.raises(PriorEvidenceRegistryError, match="repeats a path"):
        parse_registry(text + text.split("\n", 2)[2])


def test_built_registry_round_trips_and_verifies(oracle: Path) -> None:
    source = DefinitionSource("prior-repo", "c" * 40, "src/baselines.py", "d" * 40)

    text = build_registry(oracle_root=oracle, paths=(_GOLD, _DM), definition_sources=(source,))
    registry = parse_registry(text)

    gold = registry.files[0]
    assert (gold.path, gold.rows) == (_GOLD, 3)
    assert gold.sha256 == hashlib.sha256((oracle / _GOLD).read_bytes()).hexdigest()
    assert [(c.name, c.type) for c in gold.columns] == [
        ("schema_version", "int64"),
        ("y_true", "double"),
    ]
    assert [(c.name, c.type) for c in registry.files[1].columns] == [
        ("horizon", "int64"),
        ("label", "string"),
    ]
    assert registry.definition_sources == (source,)
    assert set(verify_registered_files(oracle_root=oracle, registry=registry)) == {_GOLD, _DM}


def test_builder_reads_footer_only(oracle: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("the registry builder must not read values")

    monkeypatch.setattr(pq, "read_table", forbidden)
    monkeypatch.setattr(pq.ParquetFile, "read", forbidden)
    monkeypatch.setattr(pq, "read_pandas", forbidden)
    monkeypatch.setattr(pq.ParquetFile, "read_row_group", forbidden)
    monkeypatch.setattr(pq.ParquetFile, "iter_batches", forbidden)
    # `pyarrow.Table.to_pylist` é tipo imutável (extensão C): sem `read_table`/`read`
    # nenhuma `Table` com valores chega a existir no gerador

    text = build_registry(oracle_root=oracle, paths=(_GOLD,))
    verify_registered_files(oracle_root=oracle, registry=parse_registry(text))

    assert "y_true" in text
    assert "0.1" not in text


def test_build_refuses_bad_paths(oracle: Path) -> None:
    with pytest.raises(PriorEvidenceRegistryError, match="distinct"):
        build_registry(oracle_root=oracle, paths=(_GOLD, _GOLD))
    with pytest.raises(PriorEvidenceRegistryError, match="path must be relative"):
        build_registry(oracle_root=oracle, paths=("../outside.parquet",))
    with pytest.raises(FileNotFoundError):
        build_registry(oracle_root=oracle, paths=("gold/absent.parquet",))


def test_main_prints_the_registry(oracle: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = prior_evidence.main(
        ["build", str(oracle), _GOLD, "--definition-source", "r", "c" * 40, "p.py", "b" * 40]
    )

    assert code == 0
    printed = capsys.readouterr().out
    assert printed == build_registry(
        oracle_root=oracle,
        paths=(_GOLD,),
        definition_sources=(DefinitionSource("r", "c" * 40, "p.py", "b" * 40),),
    )


def test_registry_path_is_under_docs_reports() -> None:
    assert prior_evidence.REGISTRY_PATH.parts[-3:] == (
        "docs",
        "reports",
        "prior_evidence_registry.toml",
    )
