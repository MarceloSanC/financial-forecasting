"""Ponta a ponta do `audit-reproduction` sobre o mundo julgado sintético (Stage 8.2, Task 05).

Mundo: o `_judged_world` da 8.1 (`test_run_confirmatory_evaluation`) — a cadeia r0 → r3
ancorada no `config/preregistration/` temporário, a cópia julgada selada pelo
`ParquetGoldStore` real e o `ATTEMPTS.jsonl` — mais o `.judged.toml` com o digest da cópia.
Cada teste copia o mundo para o seu `tmp_path` (raiz julgada = `<cópia>/data`) e monta a raiz
reproduzida = cópia do `data/` com o `gold/` vivo (sem `judged/`) + `reproduction/
scorecard.json` = `document_bytes` do scorecard da cópia. Critérios A3 (lê sem recalcular,
só leitura, exit 0 só com `bit_identical`) e §6 do concept (raízes iguais, cópia adulterada).
Nenhum teste lê o cohort real.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from financial_forecasting import cli
from financial_forecasting.features.evaluation.adapters.out.duckdb.parquet_gold_store import (
    ParquetGoldStore,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    GENERATION_DIR,
    SCORECARD_DOCUMENT,
    AttemptPhase,
    document_bytes,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import GoldPartition
from tests.integration.features.evaluation.test_build_confirmatory_scorecard import _ASSET
from tests.integration.features.evaluation.test_conformal_refresh_end_to_end import _COHORT
from tests.integration.features.evaluation.test_run_confirmatory_evaluation import (
    _Judged,
    _judged_world,
    _record,
)
from tests.unit.features.evaluation._preregistration_payload import to_toml

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.xdist_group("audit_reproduction_cli"),
]

_EXIT_DIFFERENT = 1
_EXIT_ERROR = 2
_PARTITION_DIR = Path("gold") / f"asset={_ASSET}" / f"parent_sweep_id={_COHORT}"
_METRICS = "gold_metrics_by_run.parquet"


@pytest.fixture(scope="module")
def judged(tmp_path_factory: pytest.TempPathFactory) -> _Judged:
    world = _judged_world(tmp_path_factory.mktemp("audit-judged"))
    path = world.root / "config" / "preregistration" / f"{world.name}-r3.judged.toml"
    path.write_text(to_toml(_record(world, world.first.generation_digest)), encoding="utf-8")
    return world


@dataclass(frozen=True)
class _Roots:
    repo: Path
    judged: Path
    reproduced: Path
    name: str
    reference: str

    def run(self, *, judged: Path | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(
            [
                "audit-reproduction",
                "--judged-data-root",
                str(judged or self.judged),
                "--reproduced-data-root",
                str(self.reproduced),
                "--preregistration",
                self.name,
                "--revision",
                "3",
                "--preregistration-ref",
                self.reference,
            ],
            wiring=cli.CliWiring(settings_overrides={"_env_file": None, "repo_root": self.repo}),
            out=out,
            err=err,
        )
        return code, out.getvalue(), err.getvalue()

    @property
    def copy_dir(self) -> Path:
        return self.judged / _PARTITION_DIR / "judged" / self.reference


@pytest.fixture
def roots(judged: _Judged, tmp_path: Path) -> _Roots:
    repo = tmp_path / "world"
    shutil.copytree(judged.root / "config", repo / "config")
    shutil.copytree(judged.root / "data", repo / "data")
    reproduced = tmp_path / "reproduced"
    shutil.copytree(judged.root / "data" / "gold", reproduced / "gold")
    shutil.rmtree(reproduced / _PARTITION_DIR / "judged")
    scorecard = judged.sealed().documents[SCORECARD_DOCUMENT]
    (reproduced / "reproduction").mkdir()
    (reproduced / "reproduction" / "scorecard.json").write_bytes(document_bytes(scorecard))
    return _Roots(repo, repo / "data", reproduced, judged.name, judged.reference)


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _line(output: str, prefix: str) -> str:
    return next(line for line in output.splitlines() if line.startswith(prefix))


def test_copy_of_judged_is_bit_identical_exit_0(roots: _Roots) -> None:
    code, out, err = roots.run()

    assert code == 0, err
    lines = out.splitlines()
    assert lines[0] == (
        f"reproduction {roots.reference}: bit_identical true partition {_ASSET}/{_COHORT}"
    )
    assert sum(line.startswith("identity ") for line in lines) == 4  # noqa: PLR2004
    assert all(line.endswith("equal true") for line in lines if line.startswith("identity "))
    for cls in ("R1", "R2", "R3"):
        assert " different 0 max_abs_diff " in _line(out, f"class {cls} ")
    assert sum(line.startswith("table ") for line in lines) == 19  # noqa: PLR2004
    assert _line(out, "scorecard ").startswith("scorecard equal true ")


def test_one_float_changed_in_reproduced_table_exit_1_with_r2_line(roots: _Roots) -> None:
    path = roots.reproduced / _PARTITION_DIR / "current" / _METRICS
    table = pq.read_table(path, partitioning=None)  # type: ignore[no-untyped-call]
    rows = table.to_pylist()
    rows[0]["value"] = math.nextafter(rows[0]["value"], math.inf)
    pq.write_table(table.from_pylist(rows, schema=table.schema), path)  # type: ignore[no-untyped-call]

    code, out, _ = roots.run()

    assert code == _EXIT_DIFFERENT
    assert " bit_identical false " in out.splitlines()[0]
    r2 = _line(out, "class R2 ")
    assert " different 1 " in r2
    assert "max_abs_diff 0.0" not in r2
    assert " R2 " in _line(out, "table gold_metrics_by_run ")
    assert _line(out, "class R1 ").split(" different ")[1].startswith("0 ")


def test_altered_leaf_in_reproduced_scorecard_json_exit_1_with_scorecard_line(
    roots: _Roots,
) -> None:
    """Uma folha numérica do arquivo trocada, geração intacta: o subcomando lê o arquivo."""
    path = roots.reproduced / "reproduction" / "scorecard.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["manifest_read"]["realized"]["returns_fsum"] += 1.0
    path.write_bytes(document_bytes(document))

    code, out, _ = roots.run()

    assert code == _EXIT_DIFFERENT
    assert _line(out, "scorecard ").startswith("scorecard equal false leaves ")
    assert " different 1 max_abs_diff 1.0" in _line(out, "scorecard ")
    for cls in ("R1", "R2", "R3"):
        assert " different 0 " in _line(out, f"class {cls} ")


def test_tampered_judged_copy_exit_2(roots: _Roots) -> None:
    table = roots.copy_dir / GENERATION_DIR / _METRICS
    data = table.read_bytes()
    table.write_bytes(bytes([data[0] ^ 0x01]) + data[1:])

    code, out, err = roots.run()

    assert code == _EXIT_ERROR
    assert "error: JudgedGenerationTamperedError" in err
    assert out == ""


def test_judged_toml_with_other_digest_exit_2(roots: _Roots, judged: _Judged) -> None:
    record = roots.repo / "config" / "preregistration" / f"{roots.name}-r3.judged.toml"
    record.write_text(to_toml(_record(judged, "3" * 64)), encoding="utf-8")

    code, _, err = roots.run()

    assert code == _EXIT_ERROR
    assert "error: JudgedGenerationTamperedError" in err
    assert "names digest" in err


def test_missing_reproduced_scorecard_exit_2(roots: _Roots) -> None:
    (roots.reproduced / "reproduction" / "scorecard.json").unlink()

    code, _, err = roots.run()

    assert code == _EXIT_ERROR
    assert "error: ReproductionAuditError: no reproduced scorecard" in err


def test_nothing_written_in_either_root(roots: _Roots) -> None:
    before = (_hashes(roots.judged), _hashes(roots.reproduced))

    code, _, _ = roots.run()

    assert code == 0
    assert (_hashes(roots.judged), _hashes(roots.reproduced)) == before


def test_equal_roots_refused_exit_2(roots: _Roots) -> None:
    code, out, err = roots.run(judged=roots.reproduced)

    assert code == _EXIT_ERROR
    assert "error: EqualReproductionRootsError" in err
    assert out == ""


def test_input_read_digest_other_than_both_sides_exit_1(roots: _Roots) -> None:
    """Uma `input_read` posterior da mesma referência com outro `result_digest`: o esperado é o
    da última linha, as duas gerações batem entre si mas não com ele → exit 1 (T2)."""
    store = ParquetGoldStore(roots.judged)
    partition = GoldPartition(_ASSET, _COHORT)
    last = [a for a in store.attempts(partition=partition) if a.phase is AttemptPhase.INPUT_READ][
        -1
    ]
    other = "ab" * 32
    store.record_attempt(
        partition=partition,
        attempt=dataclasses.replace(
            last, attempt_id=f"{last.attempt_id}-rerun", result_digest=other
        ),
    )

    code, out, _ = roots.run()

    lines = out.splitlines()
    assert code == _EXIT_DIFFERENT
    assert " bit_identical false " in lines[0]
    assert _line(out, "result_digest ").endswith(f"expected {other}")
    judged_digest = _line(out, "result_digest ").split()[2]
    assert f"reproduced {judged_digest}" in _line(out, "result_digest ")  # os lados batem
