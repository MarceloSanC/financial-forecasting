"""Unit test do ponto de entrada `cli.py` (Stage 5.5, Task 29).

Prova: `--data-root` é obrigatório em todos os subcomandos (erro de uso);
`materialize` e `run` se excluem pelo lock do `data_root` (a mensagem nomeia o
dono); sem modelo de sentimento injetado e sem o extra, `materialize` erra com a
instrução; com modelo injetado, não checa; o despacho chega aos comandos do
cohort com as dependências do composition root.
"""

from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting import cli
from financial_forecasting.features.feature_engineering.application.ports.out.sentiment_model import (  # noqa: E501
    SentimentModel,
)
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.unit.features.modeling.adapters.in_.test_cohort_file import (
    _draft,
    _frozen,
    cohort_file,
)

_SUBCOMMANDS = ("materialize", "sweep", "freeze", "run", "verify")
_EXIT_ERROR = 2  # erro esperado e erro de uso do argparse usam o mesmo código


def _wiring(tmp_path: Path, sentiment: SentimentModel | None = None) -> cli.CliWiring:
    return cli.CliWiring(
        sentiment_model=sentiment,
        runtime_probe_factory=lambda path, device: InMemoryRuntimeEnvironmentProbe(),
        settings_overrides={
            "_env_file": None,
            "artifacts_root": tmp_path / "artifacts",
            "repo_root": tmp_path,
            "mlflow_tracking_uri": f"sqlite:///{tmp_path / 'mlruns.db'}",
        },
    )


def _cohort(tmp_path: Path, *, frozen: bool = False) -> Path:
    """Um arquivo de cohort mínimo válido (rascunho) — o conteúdo não importa aqui."""
    path = tmp_path / "cohort.toml"
    path.write_text(cohort_file.dump(_frozen() if frozen else _draft()), encoding="utf-8")
    return path


def _lock(data_root: Path, owner: str = "pid=424242 host=elsewhere") -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / ".writer.lock").write_text(
        json.dumps({"pid": 424242, "host": "elsewhere", "started_at": "t", "token": owner}),
        encoding="utf-8",
    )


@pytest.mark.unit
@pytest.mark.parametrize("command", _SUBCOMMANDS)
def test_every_subcommand_requires_data_root(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([command, "--cohort", str(tmp_path / "c.toml")], wiring=_wiring(tmp_path))

    assert exc.value.code == _EXIT_ERROR  # erro de uso do argparse
    assert "--data-root" in capsys.readouterr().err


@pytest.mark.unit
@pytest.mark.parametrize("command", ["materialize", "run"])
def test_a_held_lock_blocks_materialize_and_run_naming_the_owner(
    command: str, tmp_path: Path
) -> None:
    data_root = tmp_path / "data"
    _lock(data_root)
    err = io.StringIO()

    code = cli.main(
        [command, "--data-root", str(data_root), "--cohort", str(_cohort(tmp_path, frozen=True))],
        wiring=_wiring(tmp_path, sentiment=InMemorySentimentModel()),
        out=io.StringIO(),
        err=err,
    )

    assert code == _EXIT_ERROR
    assert "CohortRunLockedError" in err.getvalue()
    assert "424242" in err.getvalue()


@pytest.mark.unit
def test_materialize_without_the_extra_and_without_injection_explains_the_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli.importlib.util, "find_spec", lambda name: None)
    err = io.StringIO()

    code = cli.main(
        ["materialize", "--data-root", str(tmp_path / "d"), "--cohort", str(_cohort(tmp_path))],
        wiring=_wiring(tmp_path),
        err=err,
    )

    assert code == _EXIT_ERROR
    assert "--extra sentiment" in err.getvalue()


@pytest.mark.unit
def test_materialize_with_an_injected_model_does_not_check_the_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(name: str) -> None:
        raise AssertionError(f"find_spec({name!r}) should not be called")

    monkeypatch.setattr(cli.importlib.util, "find_spec", forbidden)
    err = io.StringIO()

    code = cli.main(
        ["materialize", "--data-root", str(tmp_path / "d"), "--cohort", str(_cohort(tmp_path))],
        wiring=_wiring(tmp_path, sentiment=InMemorySentimentModel()),
        err=err,
    )

    # Sem brutos o ingest falha — mas DEPOIS da checagem (que não aconteceu).
    assert code == _EXIT_ERROR
    assert "Raw candle source not found" in err.getvalue()
    assert not (tmp_path / "d" / ".writer.lock").exists()  # lock liberado no erro


@pytest.mark.unit
def test_invalid_cohort_file_is_an_error_naming_the_field(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text('name = "x"\n', encoding="utf-8")
    err = io.StringIO()

    code = cli.main(
        ["verify", "--data-root", str(tmp_path / "d"), "--cohort", str(path)],
        wiring=_wiring(tmp_path),
        err=err,
    )

    assert code == _EXIT_ERROR
    assert "CohortFileError" in err.getvalue()
    assert "bad.toml" in err.getvalue()


@pytest.mark.unit
def test_cohort_commands_are_dispatched_with_the_wired_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.cohort_commands")
    seen: dict[str, Any] = {}

    def fake_sweep(deps: object, path: Path, **kwargs: object) -> int:
        seen.update(deps=deps, path=path, **kwargs)
        return 0

    monkeypatch.setattr(commands, "sweep", fake_sweep)
    cohort = _cohort(tmp_path)

    code = cli.main(
        [
            "sweep",
            "--data-root",
            str(tmp_path / "d"),
            "--cohort",
            str(cohort),
            "--n-trials",
            "1",
            "--break-stale-lock",
        ],
        wiring=_wiring(tmp_path),
    )

    assert code == 0
    assert seen["path"] == cohort
    assert seen["n_trials"] == 1
    assert seen["break_stale_lock"] is True
    deps = seen["deps"]
    assert deps.ledger._lock_path == tmp_path / "d" / ".writer.lock"
    assert deps.store._data_root == tmp_path / "d"
    assert deps.load_spec(cohort) == _draft()


@pytest.mark.unit
def test_unexpected_runtime_error_exits_2_not_the_mismatch_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F5/G7 (Checkpoint C 24-31): "o comando quebrou" ≠ "a corrida diverge"."""
    commands: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.cohort_commands")

    def broken(*args: object, **kwargs: object) -> int:
        raise RuntimeError("git unavailable")

    monkeypatch.setattr(commands, "verify", broken)
    err = io.StringIO()

    code = cli.main(
        ["verify", "--data-root", str(tmp_path / "d"), "--cohort", str(_cohort(tmp_path))],
        wiring=_wiring(tmp_path),
        err=err,
    )

    assert code == _EXIT_ERROR != commands.EXIT_MISMATCH
    assert "RuntimeError: git unavailable" in err.getvalue()


@pytest.mark.unit
def test_materialize_start_reaches_only_the_dataset_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--start` corta o dataset (R9); a ingestão continua lendo os brutos inteiros."""
    seen: dict[str, object] = {}

    def fake_materialize(deps: object, **kwargs: object) -> int:
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "_materialize", fake_materialize)
    argv = ["materialize", "--data-root", str(tmp_path / "d"), "--cohort", str(_cohort(tmp_path))]

    assert cli.main([*argv, "--start", "2010-04-20"], wiring=_wiring(tmp_path)) == 0
    assert seen["dataset_start"] == date(2010, 4, 20)
    assert cli.main(argv, wiring=_wiring(tmp_path)) == 0
    assert seen["dataset_start"] is None


@pytest.mark.unit
def test_any_other_unexpected_exception_also_exits_2_with_the_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.cohort_commands")

    def broken(*args: object, **kwargs: object) -> int:
        raise KeyError("missing")

    monkeypatch.setattr(commands, "verify", broken)
    err = io.StringIO()

    code = cli.main(
        ["verify", "--data-root", str(tmp_path / "d"), "--cohort", str(_cohort(tmp_path))],
        wiring=_wiring(tmp_path),
        err=err,
    )

    assert code == _EXIT_ERROR
    assert "Traceback" in err.getvalue()
    assert "KeyError" in err.getvalue()
