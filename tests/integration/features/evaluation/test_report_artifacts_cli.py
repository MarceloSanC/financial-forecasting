"""Ponta a ponta sintético do `report-artifacts` pela CLI (Stage 8.3, Task 14; A2, A3, A11,
A13, A14 na forma sintética).

Mundo: o mundo julgado da 8.1 (`_judged_world` de `test_run_confirmatory_evaluation`, sobre
o e2e de H3 da 7.3, com `[conformal]` e `[h3]`) refeito aqui com um `blinding_statement`
desde a r0 (o dossiê o transcreve; o mundo da 8.1 não tem): a cadeia r0 → r3 ancorada em
`config/preregistration/`, a cópia julgada selada pelo `ParquetGoldStore` real, o
`ATTEMPTS.jsonl` e o `.judged.toml` com o digest da cópia. A raiz do mundo vira repositório
git com `config/` commitado (o `GitEvaluationEnvironment` real lê o checkout); o probe é a
foto fixa do `InMemoryRuntimeEnvironmentProbe` e o `IMAGE_ID` entra pelos
`settings_overrides`; o arquivo de cohort sintético tem as seeds do plano. Nenhum dado real.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from financial_forecasting import cli
from financial_forecasting.composition_root import wire_dependencies
from financial_forecasting.features.analytics_store.adapters.out.parquet.parquet_analytics_repository import (  # noqa: E501
    ParquetAnalyticsRepository,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    FIGURE_IDS,
    find_forbidden,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from financial_forecasting.shared.infrastructure.clock.system_clock import SystemClock
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.fakes.features.modeling.in_memory_runtime_environment_probe import (
    InMemoryRuntimeEnvironmentProbe,
)
from tests.integration.features.evaluation.test_build_confirmatory_scorecard import (
    _ASSET,
    _plan_payload,
    _write_dataset,
)
from tests.integration.features.evaluation.test_conformal_refresh_end_to_end import (
    _COHORT,
    _write_silver,
)
from tests.integration.features.evaluation.test_h3_refresh_end_to_end import (
    _HASH,
    _SUSTAINED,
    _r3,
    _World,
    _write_ablation,
    _write_attribution,
)
from tests.integration.features.evaluation.test_profiles_end_to_end import _freeze
from tests.integration.features.evaluation.test_run_confirmatory_evaluation import (
    _Judged,
    _record,
    _run,
)
from tests.unit.features.evaluation._conformal_parameters import conformal_block
from tests.unit.features.evaluation._preregistration_payload import (
    R1_AMENDMENT,
    R2_AMENDMENT,
    to_toml,
    with_leaf,
)
from tests.unit.features.evaluation._profile_parameters import profile_block
from tests.unit.features.modeling.adapters.in_.test_cohort_file import _frozen, cohort_file

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.xdist_group("report_artifacts_cli"),
]

_EXIT_ERROR = 2
_IMAGE = "sha256:" + "d" * 64
_BLINDING = "Nenhum número confirmatório foi lido antes da âncora (mundo sintético)."
_GIT_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")
_PARTITION_DIR = Path("gold") / f"asset={_ASSET}" / f"parent_sweep_id={_COHORT}"
_PROBE = InMemoryRuntimeEnvironmentProbe()
_REPORT = re.compile(
    r"^report (\S+): generation_digest ([0-9a-f]{64}) figures 10 register_entries (\d+)$"
)
_REGISTER = (
    "[[entry]]\n"
    'kind = "deviation"\n'
    'title = "Errata sintética"\n'
    'summary = "nota de execução"\n'
    'pointer = "docs/stages/8.1-confirmatory-run/technical.md#o1"\n'
    "\n[[entry]]\n"
    'kind = "finding"\n'
    'title = "Achado aberto"\n'
    'summary = "sem resolução"\n'
    'pointer = "docs/stages/7.2-conformal/technical.md#finding"\n'
    'status = "open"\n'
    "\n[[entry]]\n"
    'kind = "pre_anchor"\n'
    'title = "Computação pré-âncora"\n'
    'summary = "sem valor lido"\n'
    'pointer = "docs/adr/6_5_0010-human-decisions-blinding-threshold-deviation-winner.md"\n'
    "\n[[entry]]\n"
    'kind = "environment"\n'
    'title = "Treino (CPU)"\n'
    'summary = "ambiente do treino"\n'
    'pointer = "docs/stages/5.5-cohort/technical.md#ambiente"\n'
    "\n[[entry]]\n"
    'kind = "reproduction"\n'
    'title = "Reprodução R1/R2/R3"\n'
    'summary = "R1/R2/R3 sem diferença"\n'
    'pointer = "docs/reports/reproduction_audit.md#1-claim"\n'
    "\n[[entry]]\n"
    'kind = "internal"\n'
    'title = "Evidência anterior"\n'
    'summary = "registro de hashes"\n'
    'pointer = "docs/reports/prior_evidence_registry.toml"\n'
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _blinded_judged_world(root: Path) -> _Judged:
    """O `_judged_world` da 8.1 com `blinding_statement` desde a r0 (mesmos helpers)."""
    settings = Settings(
        _env_file=None,
        data_root=root / "data",
        repo_root=root,
        artifacts_root=root / "art",
        mlflow_tracking_uri=f"sqlite:///{root}/mlruns.db",
    )
    deps = wire_dependencies(settings=settings)
    fingerprint = _write_dataset(settings.data_root)
    r0_payload = with_leaf(_plan_payload("h3_plan", _COHORT, fingerprint), "horizons", [1, 7])
    r0_payload["blinding_statement"] = _BLINDING
    r0, r0_reference = _freeze(root, r0_payload, 0)
    r1_payload = {**r0_payload, **R1_AMENDMENT, "amends": r0_reference}
    r1_payload["profile_parameters"] = profile_block()
    r1, r1_reference = _freeze(root, r1_payload, 1)
    r2_payload = {**r1_payload, **R2_AMENDMENT, "amends": r1_reference}
    r2_payload["conformal"] = conformal_block()
    r2, r2_reference = _freeze(root, r2_payload, 2)
    _write_silver(deps, r0, drop=None)
    world = _World(deps, (r0, r1, r2), (r0_reference, r1_reference, r2_reference), r2_payload)
    _write_attribution(deps, r2, _SUSTAINED, str(_HASH))
    _write_ablation(deps, r2, "ablation-judged", _SUSTAINED)
    plan, reference = _r3(world, cohort_id="ablation-judged")
    _freeze(root, {**plan.as_payload()}, 3)
    first = _run(world, plan.name, reference)
    return _Judged(root, world, plan.name, reference, first)


@dataclass(frozen=True)
class _Base:
    root: Path
    name: str
    reference: str
    digest: str
    seeds: tuple[int, ...]


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> _Base:
    root = tmp_path_factory.mktemp("report-world")
    with pytest.MonkeyPatch.context() as patch:
        for variable in _GIT_VARIABLES:
            patch.delenv(variable, raising=False)
        judged = _blinded_judged_world(root)
        folder = root / "config" / "preregistration"
        digest = judged.first.generation_digest
        (folder / f"{judged.name}-r3.judged.toml").write_text(
            to_toml(_record(judged, digest)), encoding="utf-8"
        )
        _git(root, "init", "-q")
        _git(root, "add", "config/preregistration")
        _git(root, "commit", "-q", "-m", "plan chain, anchors and judged record")
    seeds = judged.world.plans[0].seeds["tft_quantile"].seeds
    assert seeds is not None
    return _Base(root, judged.name, judged.reference, digest, tuple(seeds))


@dataclass(frozen=True)
class _Copy:
    """O mundo de cada teste: uma cópia da raiz julgada, com cohort, registro e saída."""

    repo: Path
    output: Path
    cohort: Path
    register: Path
    base: _Base

    @property
    def data(self) -> Path:
        return self.repo / "data"

    def run(self, *, reference: str | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(
            [
                "report-artifacts",
                "--data-root",
                str(self.data),
                "--cohort",
                str(self.cohort),
                "--preregistration",
                self.base.name,
                "--revision",
                "3",
                "--preregistration-ref",
                reference or self.base.reference,
                "--output",
                str(self.output),
                "--register",
                str(self.register),
            ],
            wiring=cli.CliWiring(
                runtime_probe_factory=lambda path, device: _PROBE,
                settings_overrides={
                    "_env_file": None,
                    "repo_root": self.repo,
                    "artifacts_root": self.repo / "art",
                    "mlflow_tracking_uri": f"sqlite:///{self.repo / 'mlruns.db'}",
                    "image_id": _IMAGE,
                },
            ),
            out=out,
            err=err,
        )
        return code, out.getvalue(), err.getvalue()


@pytest.fixture
def world(base: _Base, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Copy:
    for variable in _GIT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    repo = tmp_path / "world"
    shutil.copytree(base.root, repo, symlinks=True)
    cohort = tmp_path / "cohort.toml"
    cohort.write_text(cohort_file.dump(replace(_frozen(), seeds=base.seeds)), encoding="utf-8")
    register = tmp_path / "dossier_register.toml"
    register.write_text(_REGISTER, encoding="utf-8")
    return _Copy(repo, tmp_path / "reports", cohort, register, base)


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_generates_ten_pdfs_ten_records_and_two_dossiers_exit_0(world: _Copy) -> None:
    code, out, err = world.run()
    assert code == 0, err
    match = _REPORT.match(out.splitlines()[0])
    assert match is not None, out
    assert match.group(1) == world.base.reference
    assert match.group(2) == world.base.digest
    assert match.group(3) == "6"
    expected = {f"figures/{fid}.{ext}" for fid in FIGURE_IDS for ext in ("pdf", "json")}
    assert set(_hashes(world.output)) == expected | {
        "final_traceability_dossier.md",
        "final_traceability_dossier_internal.md",
    }
    for figure_id in FIGURE_IDS:
        assert (world.output / "figures" / f"{figure_id}.pdf").read_bytes().startswith(b"%PDF")


def test_second_generation_is_byte_identical(world: _Copy) -> None:
    assert world.run()[0] == 0
    first = _hashes(world.output)
    assert world.run()[0] == 0
    assert _hashes(world.output) == first


def test_data_root_unchanged(world: _Copy) -> None:
    before = _hashes(world.data)
    assert world.run()[0] == 0
    assert _hashes(world.data) == before


def test_tampered_judged_copy_exit_2_nothing_written(world: _Copy) -> None:
    copy = world.data / _PARTITION_DIR / "judged" / world.base.reference
    target = next((copy / "generation").glob("gold_dm_results.parquet"))
    target.write_bytes(target.read_bytes() + b"x")
    code, _, err = world.run()
    assert code == _EXIT_ERROR
    assert "JudgedGenerationTamperedError" in err
    assert not world.output.exists()


def test_judged_toml_with_other_digest_exit_2_nothing_written(world: _Copy) -> None:
    path = world.repo / "config" / "preregistration" / f"{world.base.name}-r3.judged.toml"
    text = path.read_text(encoding="utf-8").replace(world.base.digest, "e" * 64)
    path.write_text(text, encoding="utf-8")
    _git(world.repo, "commit", "-q", "-am", "other digest")
    code, _, err = world.run()
    assert code == _EXIT_ERROR
    assert "JudgedGenerationTamperedError" in err
    assert not world.output.exists()


def test_record_data_digest_matches_spec_and_lists_silver_units(world: _Copy) -> None:
    code, out, err = world.run()
    assert code == 0, err
    digests = dict(
        line.removeprefix("figure ").split(" data_digest ")
        for line in out.splitlines()
        if line.startswith("figure ")
    )
    snapshot = _PROBE.snapshot()
    for figure_id in FIGURE_IDS:
        record: dict[str, Any] = json.loads(
            (world.output / "figures" / f"{figure_id}.json").read_text(encoding="utf-8")
        )
        assert record["data_digest"] == digests[figure_id]
        assert record["generation_digest"] == world.base.digest
        assert record["code"] == {
            "code.src": snapshot["code.src"],
            "code.uv_lock": snapshot["code.uv_lock"],
        }
        assert record["renderer"]["matplotlib"] == "3.11.0"
        has_units = figure_id in {"sharpness_diagram", "oos_fan_chart"}
        assert bool(record["silver_units"]) is has_units, figure_id
    fan = json.loads((world.output / "figures" / "oos_fan_chart.json").read_text("utf-8"))
    sharp = json.loads((world.output / "figures" / "sharpness_diagram.json").read_text("utf-8"))
    assert set(fan["silver_units"]) < set(sharp["silver_units"])


def test_citable_dossier_free_of_prior_evidence_terms(world: _Copy) -> None:
    assert world.run()[0] == 0
    citable = (world.output / "final_traceability_dossier.md").read_text(encoding="utf-8")
    internal = (world.output / "final_traceability_dossier_internal.md").read_text("utf-8")
    assert find_forbidden(citable) == ()
    assert _BLINDING in citable
    assert "prior_evidence_registry.toml" in internal


def _markdown_blocks(markdown: str) -> dict[str, dict[str, str]]:
    """`### <bloco>` → as linhas `| campo | valor |` da tabela do bloco."""
    blocks: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in markdown.splitlines():
        if line.startswith("### "):
            current = blocks.setdefault(line[4:], {})
        elif current is not None and line.startswith("| ") and line.count(" | ") == 1:
            field, value = line[2:].removesuffix(" |").split(" | ")
            if (field, value) != ("campo", "valor"):
                current[field] = value
    return blocks


def test_revision_sha256_is_the_hash_of_each_committed_toml(world: _Copy) -> None:
    """CC4-1: o sha256 de r0 a r3 no citável = `PreregistrationHash` de cada TOML commitado,
    e o seu prefixo de 12 é o sufixo da referência (a da r3, a da ref julgada)."""
    assert world.run()[0] == 0
    blocks = _markdown_blocks(
        (world.output / "final_traceability_dossier.md").read_text(encoding="utf-8")
    )
    folder = world.repo / "config" / "preregistration"
    for revision in range(4):
        payload = tomllib.loads(
            (folder / f"{world.base.name}-r{revision}.toml").read_text(encoding="utf-8")
        )
        plan = Preregistration.from_mapping(payload)
        computed = PreregistrationHash.compute(
            hasher=CanonicalJsonHasher(), payload=plan.as_payload()
        )
        rows = blocks[f"r{revision}"]
        assert rows["sha256 da revisão"] == computed.value, revision
        assert rows["preregistration_ref"] == plan.reference(computed)
        assert rows["preregistration_ref"].endswith(f"-{computed.value[:12]}")
    assert blocks["r3"]["preregistration_ref"] == world.base.reference


def test_split_fingerprint_of_the_silver_reaches_the_citable_run_rows(world: _Copy) -> None:
    """CC4-1: o `split_fingerprint` gravado no `dim_run` aparece na linha do run."""
    assert world.run()[0] == 0
    runs = _markdown_blocks(
        (world.output / "final_traceability_dossier.md").read_text(encoding="utf-8")
    )["Runs do cohort (dim_run)"]
    silver = ParquetAnalyticsRepository(data_root=world.data, clock=SystemClock()).read(
        layer="silver", table="dim_run"
    )
    cohort = [row for row in silver if str(row["run_id"]) in runs]
    assert cohort
    assert len(cohort) == len(runs)
    for row in cohort:
        assert runs[str(row["run_id"])].endswith(
            f"; split_fingerprint {row['split_fingerprint']}"
        ), row["run_id"]
