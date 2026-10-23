"""Ponta a ponta do `evaluate` pela CLI (Stage 8.1, Task 16; A10, D1, D7).

Roda o `cli.main` de verdade sobre o fluxo da 7.1 (`test_run_inference`): dado bruto
sintético da 5.5, `materialize` → `run` (cohort congelado, uma seed, TFT real de uma
época). O `repo_root` temporário é um repositório git com o plano r0 (sem `[conformal]` e
sem `[h3]`, derivado do cohort) e a sua âncora commitados; o `IMAGE_ID` entra pelos
`settings_overrides` e o probe é a foto fixa do `run` e do `infer` (modo `strict`).

Sequência (fixture do módulo): um `evaluate` com um `.ckpt` movido para fora (exit 2,
nenhum `gold/`; o arquivo volta depois), o primeiro `evaluate` e o segundo. O e2e prova o
encadeamento `infer` → use case e a impressão, não o veredito: `JUDGED` ou `BLOCKED` são
aceitos. Nenhum dado real é lido.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import torch

from financial_forecasting import cli
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from tests.e2e.fixtures.cohort.raw_cohort_fixture import write_raw
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.integration.features.inference.test_run_inference import (
    _ASSET,
    _FIRST_SESSION,
    _N_SESSIONS,
    _draft,
    _frozen,
    _score,
)
from tests.unit.features.evaluation._preregistration_payload import (
    to_toml,
    valid_payload,
    with_leaf,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]

cohort_file: Any = cli.importlib.import_module(f"{cli._CLI_PACKAGE}.cohort_file")

_PLAN = "e2e_plan"
_IMAGE = "sha256:" + "d" * 64
_ANCHORED_AT = "2020-01-01T00:00:00+00:00"
_STATUS_LINE = re.compile(
    r"^evaluation (\S+): (JUDGED|BLOCKED|ALREADY_JUDGED) generation_digest ([0-9a-f]{64}) "
    r"partition (\S+)/(\S+)$"
)
_SUMMARY_LINE = re.compile(
    r"^inference \S+: (\d+) runs \((\d+) strict, (\d+) tolerance\); "
    r"calib rows written (\d+), verified (\d+)$"
)
_GIT_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _plan(spec: CohortSpec) -> tuple[dict[str, object], str]:
    """O r0 do cohort do e2e: modelos, seeds, níveis e identidade do cohort congelado."""
    cohort_hash = CohortHash.compute(hasher=CanonicalJsonHasher(), payload=spec.hash_payload())
    payload = valid_payload()
    for path, value in (
        ("name", _PLAN),
        ("horizons", list(spec.horizons)),
        ("quantile_levels", list(spec.quantile_levels)),
        ("seeds.tft_quantile", list(spec.seeds)),
        ("seeds.gbm_quantile", [spec.gbm_params.seed]),  # type: ignore[union-attr]
        ("cohort.cohort_id", spec.cohort_id(cohort_hash)),
        ("cohort.cohort_hash", cohort_hash.value),
        ("realized.dataset_fingerprint", spec.dataset_fingerprint),
    ):
        payload = with_leaf(payload, path, value)
    plan = Preregistration.from_mapping(payload)
    reference = plan.reference(
        PreregistrationHash.compute(hasher=CanonicalJsonHasher(), payload=plan.as_payload())
    )
    return payload, reference


def _commit_plan(root: Path, payload: dict[str, object], reference: str) -> None:
    folder = root / "config" / "preregistration"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{_PLAN}-r0.toml").write_text(to_toml(payload), encoding="utf-8")
    anchor = (
        f'tag = "preregistration/{reference}"\n'
        'commit = "0123456789abcdef0123456789abcdef01234567"\n'
        'comment_url = "https://github.com/example/repo/issues/1#issuecomment-1"\n'
        f"anchored_at = {_ANCHORED_AT}\n"
    )
    (folder / f"{_PLAN}-r0.anchor.toml").write_text(anchor, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "config/preregistration")
    _git(root, "commit", "-q", "-m", "plan r0 and its anchor")


@dataclass(frozen=True)
class _Outcome:
    data: Path
    reference: str
    missing_checkpoint: tuple[int, str]
    gold_after_missing: bool
    first: str
    second: str


@pytest.fixture(scope="module")
def outcome(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_Outcome]:
    root = tmp_path_factory.mktemp("evaluate_e2e")
    data, cohort = root / "data", root / "cohort.toml"
    probe = InMemoryRuntimeEnvironmentProbe(
        torch_threads=str(torch.get_num_threads()), device="cpu"
    )
    wiring = cli.CliWiring(
        sentiment_model=InMemorySentimentModel(score_fn=_score),
        runtime_probe_factory=lambda path, device: probe,
        settings_overrides={
            "_env_file": None,
            "artifacts_root": root / "artifacts",
            "repo_root": root,
            "mlflow_tracking_uri": f"sqlite:///{root / 'mlruns.db'}",
            "image_id": _IMAGE,
        },
    )

    def call(command: str, *extra: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = [command, "--data-root", str(data), "--cohort", str(cohort), *extra]
        code = cli.main(argv, wiring=wiring, out=out, err=err)
        return code, out.getvalue() + err.getvalue()

    def ok(command: str, *extra: str) -> str:
        code, text = call(command, *extra)
        assert code == 0, f"{command}: exit {code}\n{text}"
        return text

    with pytest.MonkeyPatch.context() as patch:
        # O container do `make check` exporta GIT_DIR/GIT_WORK_TREE da worktree; o
        # repositório do e2e é o `root`.
        for variable in _GIT_VARIABLES:
            patch.delenv(variable, raising=False)
        write_raw(data, asset=_ASSET, first=_FIRST_SESSION, n_sessions=_N_SESSIONS)
        cohort.write_text(cohort_file.dump(_draft()), encoding="utf-8")
        ok("materialize")
        spec = _frozen(data)
        cohort.write_text(cohort_file.dump(spec), encoding="utf-8")
        ok("run")
        payload, reference = _plan(spec)
        _commit_plan(root, payload, reference)
        evaluate = ("--preregistration", _PLAN, "--revision", "0", "--preregistration-ref")

        checkpoint = next((root / "artifacts").rglob("*.ckpt"))
        parked = root / "parked.ckpt"
        os.replace(checkpoint, parked)
        try:
            missing = call("evaluate", *evaluate, reference)
        finally:
            os.replace(parked, checkpoint)
        gold_after_missing = (data / "gold").exists()
        first = ok("evaluate", *evaluate, reference)
        second = ok("evaluate", *evaluate, reference)
    yield _Outcome(data, reference, missing, gold_after_missing, first, second)


def _status(output: str) -> re.Match[str]:
    matches = [m for line in output.splitlines() if (m := _STATUS_LINE.match(line))]
    assert len(matches) == 1, output
    return matches[0]


def test_missing_checkpoint_exits_2_and_writes_no_gold(outcome: _Outcome) -> None:
    code, text = outcome.missing_checkpoint
    assert code == 2, text  # noqa: PLR2004 — o exit de erro do `main`
    assert "error:" in text
    assert "evaluation " not in text  # o use case nunca rodou
    assert not outcome.gold_after_missing


def test_evaluate_runs_infer_first_and_records_its_summary_in_run_record(
    outcome: _Outcome,
) -> None:
    lines = outcome.first.splitlines()
    summary_index = next(i for i, line in enumerate(lines) if _SUMMARY_LINE.match(line))
    status_index = next(i for i, line in enumerate(lines) if _STATUS_LINE.match(line))
    assert any(line.startswith("run ") for line in lines[:summary_index])
    assert summary_index < status_index  # o infer antes do use case
    runs, strict, tolerance, written, verified = map(
        int,
        _SUMMARY_LINE.match(lines[summary_index]).groups(),  # type: ignore[union-attr]
    )
    asset, sweep = _status(outcome.first).group(4, 5)
    record_path = (
        outcome.data
        / "gold"
        / f"asset={asset}"
        / f"parent_sweep_id={sweep}"
        / "judged"
        / outcome.reference
        / "run_record.json"
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    summary = record["inference_summary"]
    assert (summary["runs"], summary["strict"], summary["tolerance"]) == (runs, strict, tolerance)
    assert (summary["calib_rows_written"], summary["calib_rows_verified"]) == (written, verified)
    assert record["environment"]["env.image_id"] == _IMAGE
    assert len(record["environment"]["commit"]) == 40  # noqa: PLR2004 — sha do git


def test_evaluate_prints_status_digest_and_body(outcome: _Outcome) -> None:
    match = _status(outcome.first)
    assert match.group(1) == outcome.reference
    assert match.group(2) in {"JUDGED", "BLOCKED"}
    lines = outcome.first.splitlines()
    separator = lines.index("--- attestation ---")
    assert separator > lines.index(match.group(0))
    body = "\n".join(lines[separator + 1 :])
    assert body.startswith(f"## Corrida confirmatória — `{outcome.reference}`")
    assert f"- generation_digest: `{match.group(3)}`" in body
    assert "### Leitura de H3 (descritiva)" in body


def test_second_evaluate_is_already_judged(outcome: _Outcome) -> None:
    first, second = _status(outcome.first), _status(outcome.second)
    assert second.group(2) == "ALREADY_JUDGED"
    assert second.group(3) == first.group(3)
    first_body = outcome.first.split("--- attestation ---\n", 1)[1]
    second_body = outcome.second.split("--- attestation ---\n", 1)[1]
    assert second_body == first_body
