"""Ponta a ponta das rodadas de produção servidas pela API (Stage 8.4, Task 07).

Roda o `cli.main` real (`production-round`) sobre brutos sintéticos, com treinos reais
(baselines, GBM, TFT com uma época) e o probe real do git num repositório descartável
que versiona o modelo de produção. Só o sentimento é fake. Sem override de
`data_root`, `artifacts_root` nem `mlflow_tracking_uri` (o comando os põe dentro da
rodada) e com o diretório de trabalho em `tmp_path`. Depois, a app completa
(`create_app`) sobe com os valores do `serving.env`, como o `--env-file` faria.

Prova CA1 (rodada servível, `verify` OK, tudo dentro da raiz de produção, um
`data/cohorts/` do repositório intacto), CA2 (a API serve a rodada sem mudança de
código: 200 com as seeds e o `cohort_id` da rodada, gold `unavailable`; 404 fora do
teste) e CA3 (retomada sem treino, rodada nova publica sem tocar a anterior, rodada
antiga não volta o ponteiro, spec adulterado recusado).
"""

from __future__ import annotations

import hashlib
import importlib
import io
import subprocess
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from financial_forecasting import cli
from financial_forecasting.features.modeling.application.dtos.cohort_spec import (
    CohortSpec,
    SweepProvenance,
)
from financial_forecasting.features.modeling.domain.value_objects.cohort_geometry import (
    CohortGeometry,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings
from financial_forecasting.shared.infrastructure.http.app import create_app
from tests.e2e import test_cohort_cli as cohort_e2e
from tests.e2e.fixtures.cohort.raw_cohort_fixture import write_raw
from tests.fakes.features.feature_engineering.in_memory_sentiment_model import (
    InMemorySentimentModel,
)

pytestmark = pytest.mark.e2e

cohort_file: Any = importlib.import_module(f"{cli._CLI_PACKAGE}.cohort_file")

_ASSET = "AAPL"
_FIRST_SESSION = date(2019, 1, 2)
_SHORT = 560
_LONG = 600
_SEEDS = (11, 12)
_TEMPLATE_REL = Path("config") / "cohorts" / "e2e_production.toml"
_ROUND_A = "2026-01-01"
_ROUND_B = "2026-01-08"
_EXIT_ERROR = 2
_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")
_OK = 200
_NOT_FOUND = 404


def _template() -> CohortSpec:
    draft = cohort_e2e._draft()
    return replace(
        draft,
        name="e2e_production",
        geometry=CohortGeometry(n_folds=1, test_size=20, val_size=20, calib_size=16, embargo=1),
        seeds=_SEEDS,
        tft_params=replace(draft.sweep.tft_base_params, dropout=0.1),
        gbm_params=replace(draft.sweep.gbm_base_params, num_leaves=8),
        provenance=SweepProvenance(
            tft_study_id="confirmatory-tft",
            tft_best_trial=0,
            tft_best_objective=0.1,
            gbm_study_id="confirmatory-gbm",
            gbm_best_trial=0,
            gbm_best_objective=0.1,
            dataset_fingerprint="9" * 64,  # sweeps do "confirmatório": outro dado
        ),
        dataset_fingerprint=None,
    )


def _digest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class _World:
    def __init__(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "repo"
        self.template = self.repo / _TEMPLATE_REL
        self.production_root = tmp_path / "production"
        self.raw_short = tmp_path / "raw-short"
        self.raw_long = tmp_path / "raw-long"
        write_raw(self.raw_short, asset=_ASSET, first=_FIRST_SESSION, n_sessions=_SHORT)
        write_raw(self.raw_long, asset=_ASSET, first=_FIRST_SESSION, n_sessions=_LONG)
        files = {
            "src/pkg/__init__.py": "x = 1\n",
            "uv.lock": "lock\n",
            "data/cohorts/conf/silver/fact.parquet": "confirmatory facts\n",
            "data/cohorts/conf/gold/current/MANIFEST.json": "{}\n",
        }
        for rel, text in files.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.template.parent.mkdir(parents=True, exist_ok=True)
        self.template.write_text(cohort_file.dump(_template()), encoding="utf-8")
        self._git("init", "-q")
        self._git("add", "src", "uv.lock", "config")
        self._git("commit", "-q", "-m", "init")
        self.wiring = cli.CliWiring(
            sentiment_model=InMemorySentimentModel(score_fn=cohort_e2e._score),
            settings_overrides={"_env_file": None, "repo_root": self.repo},
        )

    def _git(self, *args: str) -> None:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )

    def round(self, name: str, raw: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = [
            "production-round",
            "--production-root",
            str(self.production_root),
            "--round",
            name,
            "--raw-root",
            str(raw),
            "--cohort",
            str(self.template),
        ]
        code = cli.main(argv, wiring=self.wiring, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def ok(self, name: str, raw: Path) -> str:
        code, out, err = self.round(name, raw)
        assert code == 0, f"{name}: exit {code}\n{out}\n{err}"
        return out

    def pointer(self) -> dict[str, str]:
        text = (self.production_root / "serving.env").read_text(encoding="utf-8")
        return dict(line.split("=", 1) for line in text.splitlines())

    def client(self) -> TestClient:
        values = self.pointer()
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            data_root=Path(values["DATA_ROOT"]),
            serving_cohort_file=Path(values["SERVING_COHORT_FILE"]),
            repo_root=self.repo,
        )
        return TestClient(create_app(settings), raise_server_exceptions=False)


def _test_dates(round_root: Path, *, horizon: int = 1) -> list[date]:
    """Datas de decisão de teste do TFT gravadas no silver da rodada."""
    dates: set[date] = set()
    for path in (round_root / "silver" / "fact_oos_predictions").rglob("*.parquet"):
        table = (
            pq.ParquetFile(path)
            .read(columns=["model_version", "split", "horizon", "timestamp_utc"])
            .to_pylist()
        )
        dates.update(
            date.fromisoformat(row["timestamp_utc"][:10])
            for row in table
            if row["model_version"] == "tft_quantile"
            and row["split"] == "test"
            and row["horizon"] == horizon
        )
    return sorted(dates)


def _ask(client: TestClient, day: date) -> tuple[int, dict[str, Any]]:
    response = client.post(
        "/inference/run",
        json={"asset": _ASSET, "decision_date": day.isoformat(), "horizons": [1]},
    )
    return response.status_code, response.json()


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _World:
    # O `make check` roda com GIT_DIR/GIT_WORK_TREE da worktree; o repo aqui é outro.
    for variable in _GIT_ENV:
        monkeypatch.delenv(variable, raising=False)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.chdir(workdir)  # a cópia de artefato do MLflow cai aqui (concept I1)
    return _World(tmp_path)


def test_production_rounds_are_served_by_the_api(world: _World) -> None:  # noqa: PLR0915
    repo_before = _digest(world.repo)
    cohorts_before = _digest(world.repo / "data" / "cohorts")
    round_a = world.production_root.resolve() / "rounds" / _ROUND_A
    round_b = world.production_root.resolve() / "rounds" / _ROUND_B

    # CA1 — rodada A: verificada, publicada, tudo dentro da raiz da rodada
    out_a = world.ok(_ROUND_A, world.raw_short)
    assert "OK" in out_a.splitlines()
    cohort_a = out_a.split("published ", 1)[1].split(" ", 1)[0]
    assert cohort_a.startswith("e2e_production-r0-")
    assert world.pointer() == {
        "DATA_ROOT": round_a.as_posix(),
        "SERVING_COHORT_FILE": (round_a / "cohort.toml").as_posix(),
    }
    assert (round_a / "mlruns.db").is_file()
    assert (round_a / "artifacts" / "cohorts" / cohort_a / "progress.json").is_file()
    assert (round_a / ".materialized").is_file()
    assert sorted(p.name for p in world.production_root.iterdir()) == ["rounds", "serving.env"]

    # CA2 — a API serve a rodada A sem mudança de código
    dates_a = _test_dates(round_a)
    client = world.client()
    status, body = _ask(client, dates_a[0])
    assert status == _OK, body
    assert body["cohort_id"] == cohort_a
    (forecast,) = body["forecasts"]
    assert [member["seed"] for member in forecast["members"]] == list(_SEEDS)
    for member in forecast["members"]:
        assert member["conformal"]["status"] == "unavailable"
        assert "gold não publicado" in member["conformal"]["reason"]
    assert body["explainability"]["status"] == "unavailable"

    # CA3 — retomada da mesma rodada: nada treina, ponteiro igual
    pointer_a = (world.production_root / "serving.env").read_bytes()
    rerun = world.ok(_ROUND_A, world.raw_short)
    statuses = [
        line.split(": ", 1)[1].split(" ", 1)[0]
        for line in rerun.splitlines()
        if line.startswith("  ")
    ]
    assert statuses and set(statuses) == {"skipped_completed"}
    assert (world.production_root / "serving.env").read_bytes() == pointer_a

    # I5 — árvore suja: o probe real sobre o modelo versionado recusa a corrida
    module = world.repo / "src" / "pkg" / "__init__.py"
    module.write_text("x = 2" + chr(10), encoding="utf-8")
    code, _, err = world.round("2026-01-05", world.raw_short)
    assert code == _EXIT_ERROR
    assert "EnvironmentMismatchError" in err
    assert (world.production_root / "serving.env").read_bytes() == pointer_a
    world._git("checkout", "--", "src/pkg/__init__.py")

    # CA3 — rodada B com mais sessões: publica e não toca a rodada A
    digest_a = _digest(round_a)
    out_b = world.ok(_ROUND_B, world.raw_long)
    cohort_b = out_b.split("published ", 1)[1].split(" ", 1)[0]
    assert cohort_b != cohort_a
    assert world.pointer()["DATA_ROOT"] == round_b.as_posix()
    assert _digest(round_a) == digest_a

    # CA2 — data nova: 404 na rodada A, 200 na rodada B
    newest = _test_dates(round_b)[-1]
    assert newest > dates_a[-1]
    assert _ask(client, newest)[0] == _NOT_FOUND
    client.close()
    client_b = world.client()
    status, body = _ask(client_b, newest)
    assert status == _OK, body
    assert body["cohort_id"] == cohort_b
    client_b.close()

    # CA3 — rodada antiga depois da nova: verificada, sem voltar o ponteiro
    pointer_b = (world.production_root / "serving.env").read_bytes()
    late = world.ok(_ROUND_A, world.raw_short)
    assert f"not published: round {_ROUND_A} is older than the published {_ROUND_B}" in late
    assert (world.production_root / "serving.env").read_bytes() == pointer_b

    # CA3 — spec da rodada adulterado: recusado e intacto
    spec_b = round_b / "cohort.toml"
    spec_b.write_text(
        spec_b.read_text(encoding="utf-8").replace("revision = 0", "revision = 5"),
        encoding="utf-8",
    )
    tampered = spec_b.read_bytes()
    code, _, err = world.round(_ROUND_B, world.raw_long)
    assert code == _EXIT_ERROR
    assert "ProductionRoundError" in err
    assert spec_b.read_bytes() == tampered

    # CA1 — o repositório (com o data/cohorts/ dele) fica byte a byte igual
    assert _digest(world.repo / "data" / "cohorts") == cohorts_before
    repo_after = {k: v for k, v in _digest(world.repo).items() if not k.startswith(".git/")}
    assert repo_after == {k: v for k, v in repo_before.items() if not k.startswith(".git/")}
