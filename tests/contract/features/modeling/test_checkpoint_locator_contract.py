"""Contrato do port `CheckpointLocator` (Stage 7.1, C3; ADR 7.1.0004 item 1).

A fixture devolve `(locator, make_dir)`: `make_dir(files)` cria um diretório de
artefato com os arquivos `{nome: bytes}` — no fake, registrando; no
`FilesystemCheckpointLocator`, escrevendo em `tmp_path`. As duas pernas provam:
exatamente um `*.ckpt` → caminho e sha256 dos bytes; nenhum → não encontrado
(a mensagem nomeia o diretório); dois → ambíguo. Só na perna real: o módulo do
adapter, importado e usado num subprocesso limpo, não carrega a pilha de DL; e
`sha256_of_stream` em blocos = `hashlib` dos bytes inteiros.
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import textwrap
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from financial_forecasting.features.modeling.adapters.out.filesystem.checkpoint_locator import (
    FilesystemCheckpointLocator,
)
from financial_forecasting.features.modeling.application.ports.out.checkpoint_locator import (
    AmbiguousCheckpointError,
    CheckpointLocator,
    CheckpointNotFoundError,
    sha256_of_stream,
)
from tests.fakes.features.modeling.in_memory_checkpoint_locator import InMemoryCheckpointLocator

_MakeDir = Callable[[Mapping[str, bytes]], str]
_ADAPTER_MODULE = FilesystemCheckpointLocator.__module__
_CHECKPOINT_BYTES = b"checkpoint-bytes-" * 100


def _fake_leg() -> tuple[CheckpointLocator, _MakeDir]:
    locator = InMemoryCheckpointLocator()
    counter = iter(range(1_000))

    def make_dir(files: Mapping[str, bytes]) -> str:
        directory = f"/artifacts/tft/run-{next(counter)}"
        for name, data in files.items():
            locator.add_file(directory, name, data)
        return directory

    return locator, make_dir


def _real_leg(tmp_path: Path) -> tuple[CheckpointLocator, _MakeDir]:
    counter = iter(range(1_000))

    def make_dir(files: Mapping[str, bytes]) -> str:
        directory = tmp_path / "artifacts" / "tft" / f"run-{next(counter)}"
        directory.mkdir(parents=True)
        for name, data in files.items():
            (directory / name).write_bytes(data)
        return str(directory)

    return FilesystemCheckpointLocator(), make_dir


@pytest.fixture(params=["fake", "real"])
def leg(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[CheckpointLocator, _MakeDir]:
    if request.param == "fake":
        return _fake_leg()
    return _real_leg(tmp_path)


@pytest.mark.contract
def test_locate_returns_the_single_ckpt_and_its_sha256(
    leg: tuple[CheckpointLocator, _MakeDir],
) -> None:
    locator, make_dir = leg
    directory = make_dir({"epoch=3-step=40.ckpt": _CHECKPOINT_BYTES, "metrics.csv": b"x"})

    location = locator.locate(artifact_dir=directory)

    assert Path(location.path).is_absolute()
    assert Path(location.path).name == "epoch=3-step=40.ckpt"
    assert Path(location.path).parent.as_posix().endswith(Path(directory).as_posix())
    assert location.sha256 == hashlib.sha256(_CHECKPOINT_BYTES).hexdigest()


@pytest.mark.contract
def test_locate_without_ckpt_raises_not_found(leg: tuple[CheckpointLocator, _MakeDir]) -> None:
    locator, make_dir = leg
    directory = make_dir({"metrics.csv": b"x"})

    with pytest.raises(CheckpointNotFoundError, match="C3") as raised:
        locator.locate(artifact_dir=directory)

    assert str(Path(directory)) in str(raised.value) or directory in str(raised.value)


@pytest.mark.contract
def test_locate_missing_directory_raises_not_found(
    leg: tuple[CheckpointLocator, _MakeDir], tmp_path: Path
) -> None:
    locator, _ = leg

    with pytest.raises(CheckpointNotFoundError):
        locator.locate(artifact_dir=str(tmp_path / "never-created"))


@pytest.mark.contract
def test_relative_directory_resolves_to_an_absolute_path(
    leg: tuple[CheckpointLocator, _MakeDir], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    locator, make_dir = leg
    directory = make_dir({"best.ckpt": _CHECKPOINT_BYTES})
    monkeypatch.chdir(tmp_path)
    relative = os.path.relpath(directory, tmp_path)
    assert not Path(relative).is_absolute()

    location = locator.locate(artifact_dir=relative)

    assert Path(location.path).is_absolute()
    assert Path(location.path).parent == Path(directory)
    assert location.sha256 == hashlib.sha256(_CHECKPOINT_BYTES).hexdigest()


@pytest.mark.contract
def test_locate_with_two_ckpts_raises_ambiguous(leg: tuple[CheckpointLocator, _MakeDir]) -> None:
    locator, make_dir = leg
    directory = make_dir({"a.ckpt": b"a", "b.ckpt": b"b"})

    with pytest.raises(AmbiguousCheckpointError, match="exactly one"):
        locator.locate(artifact_dir=directory)


# -- só na perna real -------------------------------------------------------------


@pytest.mark.contract
def test_locator_module_does_not_import_the_dl_stack(tmp_path: Path) -> None:
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "best.ckpt").write_bytes(_CHECKPOINT_BYTES)
    script = textwrap.dedent(
        f"""
        import importlib
        import sys
        module = importlib.import_module({_ADAPTER_MODULE!r})
        module.FilesystemCheckpointLocator().locate(artifact_dir={str(directory)!r})
        print(sorted({{"torch", "lightning", "pytorch_forecasting"}} & set(sys.modules)))
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )

    assert completed.stdout.strip() == "[]"


@pytest.mark.contract
def test_sha256_of_stream_equals_hashlib_of_whole_bytes() -> None:
    data = bytes(range(256)) * 41  # 10_496 bytes: vários blocos e um resto

    assert sha256_of_stream(io.BytesIO(data), chunk_size=1_000) == hashlib.sha256(data).hexdigest()
    assert sha256_of_stream(io.BytesIO(b"")) == hashlib.sha256(b"").hexdigest()
    with pytest.raises(ValueError, match="chunk_size"):
        sha256_of_stream(io.BytesIO(data), chunk_size=0)
