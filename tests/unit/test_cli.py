"""Unit test do ponto de entrada `cli.py` (Stage 5.5, Task 29).

Prova: `--data-root` é obrigatório em todos os subcomandos (erro de uso);
`materialize` e `run` se excluem pelo lock do `data_root` (a mensagem nomeia o
dono); sem modelo de sentimento injetado e sem o extra, `materialize` erra com a
instrução; com modelo injetado, não checa; o despacho chega aos comandos do
cohort com as dependências do composition root; o início do dataset vem do
`--start` ou do `dataset_start` do arquivo, e os dois divergentes são erro (#122).
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from financial_forecasting import cli
from financial_forecasting.features.feature_engineering.application.ports.out.sentiment_model import (  # noqa: E501
    SentimentModel,
)
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)
from tests.fakes.features.modeling.in_memory_cohort_progress_ledger import (
    InMemoryCohortProgressLedger,
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
@pytest.mark.parametrize("command", ["materialize", "run", "infer"])
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
def test_materialize_reads_the_start_declared_in_the_cohort_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#122: `dataset_start` do arquivo vale sem `--start`; igual a ele, também."""
    seen: dict[str, object] = {}

    def fake_materialize(deps: object, **kwargs: object) -> int:
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "_materialize", fake_materialize)
    path = tmp_path / "cohort.toml"
    path.write_text(
        cohort_file.dump(replace(_draft(), dataset_start=date(2010, 4, 20))), encoding="utf-8"
    )
    argv = ["materialize", "--data-root", str(tmp_path / "d"), "--cohort", str(path)]

    assert cli.main(argv, wiring=_wiring(tmp_path)) == 0
    assert seen["dataset_start"] == date(2010, 4, 20)
    seen.clear()
    assert cli.main([*argv, "--start", "2010-04-20"], wiring=_wiring(tmp_path)) == 0
    assert seen["dataset_start"] == date(2010, 4, 20)


@pytest.mark.unit
def test_a_start_that_differs_from_the_cohort_file_is_an_error_naming_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[object] = []

    def fake_materialize(deps: object, **kwargs: object) -> int:
        called.append(kwargs)
        return 0

    monkeypatch.setattr(cli, "_materialize", fake_materialize)
    path = tmp_path / "cohort.toml"
    path.write_text(
        cohort_file.dump(replace(_draft(), dataset_start=date(2010, 4, 20))), encoding="utf-8"
    )
    err = io.StringIO()
    argv = ["materialize", "--data-root", str(tmp_path / "d"), "--cohort", str(path)]

    code = cli.main([*argv, "--start", "2011-01-03"], wiring=_wiring(tmp_path), err=err)

    assert code == _EXIT_ERROR
    assert "DatasetStartConflictError" in err.getvalue()
    assert "2011-01-03" in err.getvalue()
    assert "2010-04-20" in err.getvalue()
    assert not called  # nada é ingerido nem materializado


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


@pytest.mark.unit
def test_materialize_start_cuts_only_the_dataset_not_the_ingestion() -> None:
    """Rodada 3 do Checkpoint C 24-31: roda o `_materialize` real com use cases
    falsos e confere os TRÊS pedidos — `--start` só pode chegar ao dataset."""
    requests: dict[str, Any] = {}

    def recorder(name: str, result: object) -> SimpleNamespace:
        def execute(request: object) -> object:
            requests[name] = request
            return result

        return SimpleNamespace(execute=execute)

    ingested = SimpleNamespace(ingested=1)
    deps: Any = SimpleNamespace(
        cohort_ledger=InMemoryCohortProgressLedger(),
        ingest_candles=recorder("candles", ingested),
        ingest_news=recorder("news", ingested),
        ingest_fundamentals=recorder("fundamentals", ingested),
        build_dataset=recorder(
            "dataset",
            SimpleNamespace(
                n_rows=1, start=date(2010, 4, 21), end=date(2025, 12, 31), feature_set_hash="h"
            ),
        ),
    )

    code = cli._materialize(
        deps,
        asset_id="AAPL",
        sentiment_injected=True,
        break_stale_lock=False,
        out=io.StringIO(),
        dataset_start=date(2010, 4, 20),
    )

    assert code == 0
    assert requests["candles"].start == cli._MATERIALIZE_START
    assert requests["news"].start == cli._MATERIALIZE_START
    assert requests["fundamentals"].start is None
    assert requests["dataset"].start == date(2010, 4, 20)
    assert requests["dataset"].end == cli._MATERIALIZE_END.date()
    assert not deps.cohort_ledger.is_locked


_SECTION6_ERRORS = [
    ("CohortNotFrozenError", "run_confirmatory_cohort"),
    ("DatasetMismatchError", "run_confirmatory_cohort"),
    ("CohortDeclarationMismatchError", "run_confirmatory_cohort"),
    ("EnvironmentMismatchError", "run_confirmatory_cohort"),
    ("CompletedUnitCorruptedError", "run_confirmatory_cohort"),
    ("PartialCohortUnitError", "run_confirmatory_cohort"),
    ("GeometryDoesNotFitError", "cohort_domain"),
    ("InteriorMissingValuesError", "cohort_domain"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("name", "module"), _SECTION6_ERRORS, ids=[n for n, _ in _SECTION6_ERRORS])
def test_cohort_errors_exit_2_naming_the_error(
    name: str, module: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auditoria de testes: cada erro do §6 chega ao operador com exit 2 e nome."""
    modules = {
        "run_confirmatory_cohort": "financial_forecasting.features.modeling.application."
        "use_cases.run_confirmatory_cohort",
        "cohort_domain": "financial_forecasting.features.modeling.domain.exceptions.cohort",
    }
    error_type = getattr(cli.importlib.import_module(modules[module]), name)
    commands: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.cohort_commands")

    def raising(*args: object, **kwargs: object) -> int:
        raise error_type.__new__(error_type)

    monkeypatch.setattr(commands, "run", raising)
    err = io.StringIO()

    code = cli.main(
        ["run", "--data-root", str(tmp_path / "d"), "--cohort", str(_cohort(tmp_path))],
        wiring=_wiring(tmp_path),
        err=err,
    )

    assert code == _EXIT_ERROR
    assert f"error: {name}" in err.getvalue()


# -- Stage 7.1, Task 12: subcomando `infer` ----------------------------------------

_INFERENCE_COMMANDS = "financial_forecasting.features.inference.adapters.in.cli.inference_commands"


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["--data-root", "--cohort"])
def test_infer_requires_data_root_and_cohort(
    missing: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    given = {"--data-root": str(tmp_path / "d"), "--cohort": str(tmp_path / "c.toml")}
    argv = ["infer"]
    for flag, value in given.items():
        if flag != missing:
            argv += [flag, value]

    with pytest.raises(SystemExit) as exc:
        cli.main(argv, wiring=_wiring(tmp_path))

    assert exc.value.code == _EXIT_ERROR  # erro de uso do argparse
    assert missing in capsys.readouterr().err


@pytest.mark.unit
def test_infer_dispatches_break_stale_lock_and_cross_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: Any = cli.importlib.import_module(_INFERENCE_COMMANDS)
    seen: dict[str, Any] = {}

    def fake_infer(run_inference_for: object, spec: object, path: Path, **kwargs: object) -> int:
        seen.update(run_inference_for=run_inference_for, spec=spec, path=path, **kwargs)
        return 0

    monkeypatch.setattr(commands, "infer", fake_infer)
    cohort = _cohort(tmp_path, frozen=True)
    out = io.StringIO()
    argv = ["infer", "--data-root", str(tmp_path / "d"), "--cohort", str(cohort)]

    code = cli.main(
        [
            *argv,
            "--break-stale-lock",
            "--cross-environment",
            "kernel upgrade, see [finding] in technical 7.1 §7",
        ],
        wiring=_wiring(tmp_path),
        out=out,
    )

    assert code == 0
    assert seen["spec"] == _frozen()  # o TOML lido pelo `cohort_file.load` da 5.5
    assert seen["path"] == cohort
    assert seen["out"] is out
    assert seen["break_stale_lock"] is True
    assert seen["cross_environment"] == "kernel upgrade, see [finding] in technical 7.1 §7"
    assert callable(seen["run_inference_for"])
    assert cli.main(argv, wiring=_wiring(tmp_path)) == 0
    assert seen["break_stale_lock"] is False
    assert seen["cross_environment"] is None


@pytest.mark.unit
def test_infer_application_error_exits_2(tmp_path: Path) -> None:
    """Cohort em rascunho: o `RunInference` real ergue C1 e o `main` sai com 2."""
    err = io.StringIO()

    code = cli.main(
        ["infer", "--data-root", str(tmp_path / "d"), "--cohort", str(_cohort(tmp_path))],
        wiring=_wiring(tmp_path),
        out=io.StringIO(),
        err=err,
    )

    assert code == _EXIT_ERROR
    assert "error: CohortNotFrozenError" in err.getvalue()
    assert not (tmp_path / "d" / ".writer.lock").exists()  # C1 antes do lock


@pytest.mark.unit
def test_infer_cross_environment_without_finding_exits_2(tmp_path: Path) -> None:
    """C13 pela CLI: justificativa sem `[finding]` sai com 2, antes de tomar o lock."""
    err = io.StringIO()
    cohort = _cohort(tmp_path, frozen=True)

    code = cli.main(
        [
            "infer",
            "--data-root",
            str(tmp_path / "d"),
            "--cohort",
            str(cohort),
            "--cross-environment",
            "x",
        ],
        wiring=_wiring(tmp_path),
        out=io.StringIO(),
        err=err,
    )

    assert code == _EXIT_ERROR
    assert "error: ValueError" in err.getvalue()
    assert "[finding]" in err.getvalue()
    assert not (tmp_path / "d" / ".writer.lock").exists()


# -- Stage 7.3, Task 10: subcomandos do cohort de ablação -------------------------------

_ABLATION_SUBCOMMANDS = ("ablation-pilot", "ablation-run", "ablation-verify", "ablation-freeze")


@pytest.mark.unit
@pytest.mark.parametrize("command", _ABLATION_SUBCOMMANDS)
def test_ablation_subcommands_have_help(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([command, "--help"])

    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert "--data-root" in text
    assert "--cohort" in text
    if command == "ablation-freeze":
        assert "--seeds" in text


@pytest.mark.unit
def test_ablation_freeze_parses_the_seed_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.ablation_commands")
    seen: dict[str, Any] = {}

    def fake_freeze(deps: object, path: Path, **kwargs: object) -> int:
        seen.update(deps=deps, path=path, **kwargs)
        return 0

    monkeypatch.setattr(commands, "freeze", fake_freeze)
    ablation = tmp_path / "ablation.toml"

    code = cli.main(
        [
            "ablation-freeze",
            "--data-root",
            str(tmp_path / "d"),
            "--cohort",
            str(ablation),
            "--seeds",
            "1,2,3",
        ],
        wiring=_wiring(tmp_path),
    )

    assert code == 0
    assert seen["path"] == ablation
    assert seen["seeds"] == (1, 2, 3)
    assert seen["deps"].ledger._lock_path == tmp_path / "d" / ".writer.lock"


@pytest.mark.unit
def test_ablation_freeze_refuses_a_malformed_seed_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "ablation-freeze",
                "--data-root",
                str(tmp_path),
                "--cohort",
                "a.toml",
                "--seeds",
                "1,x",
            ]
        )

    assert exc.value.code == _EXIT_ERROR
    assert "seeds must be integers" in capsys.readouterr().err


# -- Stage 7.3, Task 20: subcomando `attribute` -----------------------------------------


@pytest.mark.unit
def test_attribute_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["attribute", "--help"])

    assert exc.value.code == 0
    text = capsys.readouterr().out
    for flag in (
        "--data-root",
        "--cohort",
        "--ablation-cohort",
        "--cross-environment",
        "--break-stale-lock",
    ):
        assert flag in text, flag


def _ablation_with_base(tmp_path: Path) -> tuple[Path, Path]:
    """Base sintética congelada e arquivo de ablação que a declara (sob `repo_root`)."""
    from tests.unit.shared.test_composition_root import _ablation_files  # noqa: PLC0415

    ablation = _ablation_files(tmp_path, device="rocm")
    return tmp_path / "config" / "cohorts" / "base.toml", ablation


@pytest.mark.unit
def test_attribute_dispatches_the_base_spec_and_the_partition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: Any = cli.importlib.import_module(_INFERENCE_COMMANDS)
    seen: dict[str, Any] = {}

    def fake_attribute(
        factory: object, spec: object, path: Path, partition: object, base: object, **kw: object
    ) -> int:
        seen.update(factory=factory, spec=spec, path=path, partition=partition, base=base, **kw)
        return 0

    monkeypatch.setattr(commands, "attribute", fake_attribute)
    base, ablation = _ablation_with_base(tmp_path)
    argv = ["attribute", "--data-root", str(tmp_path / "d"), "--cohort", str(base)]

    code = cli.main([*argv, "--ablation-cohort", str(ablation)], wiring=_wiring(tmp_path))

    assert code == 0
    assert seen["path"] == base
    assert set(seen["partition"]) == {"price", "technical", "sentiment", "fundamental"}
    assert len(seen["base"]) == 64  # noqa: PLR2004 — o base_cohort_hash do arquivo de ablação
    assert seen["break_stale_lock"] is False
    assert seen["cross_environment"] is None


@pytest.mark.unit
def test_attribute_refuses_a_cohort_other_than_the_ablation_base(tmp_path: Path) -> None:
    """C5-10: o `--cohort` tem de ser a base declarada pelo arquivo de ablação."""
    _, ablation = _ablation_with_base(tmp_path)
    other = _cohort(tmp_path, frozen=True)
    err = io.StringIO()

    code = cli.main(
        [
            "attribute",
            "--data-root",
            str(tmp_path / "d"),
            "--cohort",
            str(other),
            "--ablation-cohort",
            str(ablation),
        ],
        wiring=_wiring(tmp_path),
        out=io.StringIO(),
        err=err,
    )

    assert code == _EXIT_ERROR
    assert "declares base cohort_hash" in err.getvalue()
    assert not (tmp_path / "d" / ".writer.lock").exists()


@pytest.mark.unit
def test_infer_with_summary_prints_the_same_lines_and_returns_the_summary(tmp_path: Path) -> None:
    """Stage 8.1 Task 15: as linhas do `infer` e o resumo como dado (D1)."""
    commands: Any = cli.importlib.import_module(_INFERENCE_COMMANDS)

    def outcome(run: str, mode: str, diff: float, written: int, verified: int) -> SimpleNamespace:
        return SimpleNamespace(
            run_id=run,
            fold_index=0,
            seed=1,
            reproduction_mode=mode,
            test_values_compared=7,
            max_abs_diff=diff,
            max_normalized_diff=diff / 2,
            calib_rows_written=written,
            calib_rows_verified=verified,
        )

    result = SimpleNamespace(
        cohort_id="synthetic-r0",
        outcomes=(
            outcome("run-a", "strict", 0.0, 3, 0),
            outcome("run-b", "tolerance", 2.5e-7, 0, 4),
            outcome("run-c", "strict", 1e-9, 1, 5),
        ),
    )
    commands_seen: list[object] = []

    def run_inference_for(path: Path, device: str) -> Callable[[object], SimpleNamespace]:
        def run(command: object) -> SimpleNamespace:
            commands_seen.append(command)
            return result

        return run

    spec = _frozen()
    summary_out, infer_out = io.StringIO(), io.StringIO()

    summary = commands.infer_with_summary(
        run_inference_for, spec, tmp_path / "c.toml", out=summary_out, break_stale_lock=True
    )
    code = commands.infer(
        run_inference_for, spec, tmp_path / "c.toml", out=infer_out, break_stale_lock=True
    )

    assert code == 0
    assert summary_out.getvalue() == infer_out.getvalue()
    assert summary_out.getvalue().endswith(
        "inference synthetic-r0: 3 runs (2 strict, 1 tolerance); calib rows written 4, verified 9\n"
    )
    assert dict(summary) == {
        "runs": 3,
        "strict": 2,
        "tolerance": 1,
        "max_abs_diff": 2.5e-7,
        "calib_rows_written": 4,
        "calib_rows_verified": 9,
    }
    assert commands_seen[0].break_stale_lock is True  # type: ignore[attr-defined]
    empty = SimpleNamespace(cohort_id="synthetic-r0", outcomes=())
    result = empty
    assert (
        commands.infer_with_summary(
            run_inference_for, spec, tmp_path / "c.toml", out=io.StringIO()
        )["max_abs_diff"]
        == 0.0
    )


# -- Stage 8.1, Task 16: subcomando `evaluate` -------------------------------------------

_EVALUATION_COMMANDS = (
    "financial_forecasting.features.evaluation.adapters.in.cli.evaluation_commands"
)
_REF = "synthetic_plan-r3-0123456789ab"
_SUMMARY = {
    "runs": 2,
    "strict": 2,
    "tolerance": 0,
    "max_abs_diff": 0.0,
    "calib_rows_written": 0,
    "calib_rows_verified": 6,
}


def _evaluate_argv(tmp_path: Path, cohort: Path, *extra: str) -> list[str]:
    return [
        "evaluate",
        "--data-root",
        str(tmp_path / "d"),
        "--cohort",
        str(cohort),
        "--preregistration",
        "synthetic_plan",
        "--revision",
        "3",
        "--preregistration-ref",
        _REF,
        *extra,
    ]


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["--preregistration", "--revision", "--preregistration-ref"])
def test_evaluate_requires_preregistration_revision_and_ref(
    missing: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _evaluate_argv(tmp_path, tmp_path / "c.toml")
    index = argv.index(missing)
    del argv[index : index + 2]

    with pytest.raises(SystemExit) as exc:
        cli.main(argv, wiring=_wiring(tmp_path))

    assert exc.value.code == _EXIT_ERROR  # erro de uso do argparse
    assert missing in capsys.readouterr().err


@pytest.mark.unit
def test_evaluate_dispatch_runs_infer_then_use_case_with_its_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inference: Any = cli.importlib.import_module(_INFERENCE_COMMANDS)
    evaluation: Any = cli.importlib.import_module(_EVALUATION_COMMANDS)
    events: list[tuple[str, dict[str, Any]]] = []

    def fake_infer_with_summary(
        run_inference_for: object, spec: object, path: Path, **kwargs: object
    ) -> dict[str, object]:
        events.append(("infer", {"spec": spec, "path": path, **kwargs}))
        return dict(_SUMMARY)

    def fake_evaluate(use_case: object, **kwargs: object) -> int:
        events.append(("evaluate", {"use_case": use_case, **kwargs}))
        return 0

    monkeypatch.setattr(inference, "infer_with_summary", fake_infer_with_summary)
    monkeypatch.setattr(evaluation, "evaluate", fake_evaluate)
    cohort = _cohort(tmp_path, frozen=True)
    out = io.StringIO()

    code = cli.main(
        _evaluate_argv(tmp_path, cohort, "--break-stale-lock", "--deviation", "[deviation] x"),
        wiring=_wiring(tmp_path),
        out=out,
    )

    assert code == 0
    assert [name for name, _ in events] == ["infer", "evaluate"]
    infer_call, evaluate_call = events[0][1], events[1][1]
    assert infer_call["spec"] == _frozen()
    assert infer_call["path"] == cohort
    assert infer_call["break_stale_lock"] is True
    assert infer_call["out"] is out
    assert type(evaluate_call["use_case"]).__name__ == "RunConfirmatoryEvaluation"
    assert evaluate_call["inference_summary"] == _SUMMARY
    assert (evaluate_call["name"], evaluate_call["revision"]) == ("synthetic_plan", 3)
    assert evaluate_call["preregistration_ref"] == _REF
    assert evaluate_call["deviation"] == "[deviation] x"
    assert evaluate_call["break_stale_lock"] is True
    assert evaluate_call["out"] is out


@pytest.mark.unit
def test_evaluate_infer_failure_never_calls_the_use_case_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluation: Any = cli.importlib.import_module(_EVALUATION_COMMANDS)
    called: list[object] = []
    monkeypatch.setattr(evaluation, "evaluate", lambda *args, **kwargs: called.append(args))
    err = io.StringIO()

    # cohort em rascunho: o `RunInference` real ergue C1 (`CohortNotFrozenError`)
    code = cli.main(
        _evaluate_argv(tmp_path, _cohort(tmp_path)),
        wiring=_wiring(tmp_path),
        out=io.StringIO(),
        err=err,
    )

    assert code == _EXIT_ERROR
    assert "error: CohortNotFrozenError" in err.getvalue()
    assert called == []
    assert not (tmp_path / "d" / "gold").exists()


@pytest.mark.unit
def test_evaluate_prints_status_digest_and_attestation() -> None:
    evaluation: Any = cli.importlib.import_module(_EVALUATION_COMMANDS)
    dtos: Any = cli.importlib.import_module(
        "financial_forecasting.features.evaluation.application.dtos.confirmatory_run"
    )
    refresh: Any = cli.importlib.import_module(
        "financial_forecasting.features.evaluation.application.dtos.refresh_gold"
    )
    commands: list[Any] = []

    def use_case(command: object) -> object:
        commands.append(command)
        return dtos.RunConfirmatoryEvaluationResult(
            status=dtos.ConfirmatoryRunStatus.BLOCKED,
            preregistration_ref=_REF,
            partition=refresh.GoldPartition("AAPL", "synthetic_cohort-r0-000000000000"),
            generation_digest="e" * 64,
            refresh_status=refresh.RefreshStatus.BLOCKED,
            scorecard=None,
            failed_checks=(),
            attestation_body="## Corrida confirmatória\n\n- status: `BLOCKED`\n",
        )

    out = io.StringIO()

    code = evaluation.evaluate(
        use_case,
        name="synthetic_plan",
        revision=3,
        preregistration_ref=_REF,
        inference_summary=_SUMMARY,
        break_stale_lock=False,
        deviation=None,
        out=out,
    )

    assert code == 0
    assert out.getvalue() == (
        f"evaluation {_REF}: BLOCKED generation_digest {'e' * 64} "
        "partition AAPL/synthetic_cohort-r0-000000000000\n"
        "--- attestation ---\n"
        "## Corrida confirmatória\n\n- status: `BLOCKED`\n"
    )
    assert commands[0].inference_summary == dtos.InferenceSummary.from_mapping(_SUMMARY)
    assert (commands[0].name, commands[0].revision) == ("synthetic_plan", 3)
