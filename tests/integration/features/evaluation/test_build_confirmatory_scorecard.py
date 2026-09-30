"""E2E do scorecard confirmatório sobre silver sintético, pelo grafo wirado (Stage 6.5 Task 11).

Tudo num único `tmp_path` (fixture de módulo): `Settings(_env_file=None, data_root,
repo_root, artifacts_root)` sob o `tmp_path` — nenhum `.env` do checkout, nenhum dado
real (cegamento, I15). O plano de teste (`valid_payload()` com horizontes (1, 2),
candidato com seeds [1, 2], os seis comparadores, `cohort_id = "e2e-cohort"` e o
fingerprint da grade sintética) é gravado por `to_toml` em
`<tmp>/config/preregistration/`, com âncora (`to_toml` também) de 2020-01-01 e o
`preregistration_ref` calculado com o `CanonicalJsonHasher`.

Silver sintético gravado pelo `ParquetAnalyticsRepository` real e dataset com as colunas
de `modeling_columns()` (padrão da 6.4). **Hits determinísticos por construção**: o
candidato emite quantis centrados no realizado deslocado de d_t, com d_t abaixo do
q0,10 quando `t % 20 ∈ {0, 11}` e acima do q0,90 quando `t % 20 ∈ {5, 16}` — 10 % por
cauda, uma violação de cada cauda por paridade (as duas sub-séries DGT de h = 2) a
cada 20 pontos; os comparadores têm viés grande (e ruído próprio, para nenhum
diferencial ser constante) → o DM rejeita contra todos.

Sequência: refresh com `refresh_command_from(plano, ref)` → `COMPLETED`; scorecard →
`BEATS_NAIVE_AND_STRONG` com vencedor `tft_quantile` nos dois horizontes e pronto.
Recusas: (a) **plano alterado** (arquivo próprio, ancorado, `mcs.seed` diferente, mesmo
cohort) sobre o mesmo gold → mismatch em `preregistration_ref`; (b) **seed a mais no
silver** — plano B (`cohort_id = "e2e-cohort-extra-seed"`, seeds [1, 2]) com silver do
candidato nas seeds {1, 2, 3}: o refresh completa e o scorecard dá mismatch em `seeds`.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from financial_forecasting.composition_root import ApplicationDependencies, wire_dependencies
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    BuildConfirmatoryScorecardCommand,
    PreregistrationMismatchError,
    ScorecardResult,
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    RefreshStatus,
)
from financial_forecasting.features.evaluation.domain.services.confirmatory_scorecard import (
    H2Outcome,
)
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
)
from financial_forecasting.features.modeling.application.use_cases.train_gbm_quantile import (
    grid_fingerprint,
    modeling_columns,
)
from financial_forecasting.features.modeling.domain.services.training_grid import (
    build_training_grid,
)
from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from financial_forecasting.shared.infrastructure.config.settings import Settings
from tests.unit.features.evaluation._preregistration_payload import (
    to_toml,
    valid_payload,
    with_leaf,
)

pytestmark = pytest.mark.integration

_ASSET = "AAPL"
_SILVER = "silver"
_COHORT = "e2e-cohort"
_COHORT_EXTRA = "e2e-cohort-extra-seed"
_CANDIDATE = "tft_quantile"
_N_SESSIONS = 130
_FIRST_DECISION = 5
_WARMUP = 5
_HORIZONS = (1, 2)
_EPOCH = datetime(2024, 1, 2, tzinfo=UTC)
_ANCHORED_AT = datetime(2020, 1, 1, tzinfo=UTC)
# desvios padronizados (sigma = 0,02) da grade (0,02; 0,1; 0,25; 0,5; 0,75; 0,9; 0,98)
_OFFSETS = (-0.041, -0.0256, -0.0135, 0.0, 0.0135, 0.0256, 0.041)
_LOWER_HITS = {0, 11}
_UPPER_HITS = {5, 16}
_BIAS = {
    "baseline_zero_return": (0.030, 1.2),
    "baseline_historical_mean": (0.035, 1.4),
    "baseline_ar1": (0.025, 1.6),
    "baseline_ewma_vol": (0.040, 1.8),
    "baseline_historical_quantiles": (0.028, 2.0),
    "gbm_quantile": (0.022, 1.1),
}


def _session(index: int) -> str:
    return (_EPOCH + timedelta(days=index)).isoformat()


def _deviation(t: int) -> float:
    """d_t = realizado - centro do candidato: fixa as violações do q0,10 e do q0,90."""
    position = t % 20
    if position in _LOWER_HITS:
        return -0.03
    if position in _UPPER_HITS:
        return 0.03
    return random.Random(f"inside|{t}").uniform(-0.015, 0.015)


def _center(t: int) -> float:
    return random.Random(f"center|{t}").uniform(-0.01, 0.01)


def _realized() -> list[float]:
    return [_center(t) + _deviation(t) for t in range(_N_SESSIONS)]


def _quantiles(model: str, seed: int | None, horizon: int, target: int) -> list[float]:
    rng = random.Random(f"{model}|{seed}|{horizon}|{target}")
    if model == _CANDIDATE:
        center, scale = _center(target) + rng.uniform(-0.001, 0.001), 1.0
    else:
        bias, scale = _BIAS[model]
        center = _center(target) + bias + rng.uniform(-0.004, 0.004)
    return [center + scale * offset for offset in _OFFSETS]


def _seeds(prereg: Preregistration, model: str, extra: tuple[int, ...]) -> list[int | None]:
    spec = prereg.seeds[model]
    seeds: list[int | None] = [None] if spec.seeds is None else list(spec.seeds)
    return seeds + list(extra) if model == prereg.candidate else seeds


def _write_silver(
    deps: ApplicationDependencies, prereg: Preregistration, *, extra_seeds: tuple[int, ...] = ()
) -> None:
    repo = deps.analytics_repository
    sweep = prereg.cohort.cohort_id
    middle = (_FIRST_DECISION + _N_SESSIONS) // 2
    facts: list[dict[str, object]] = []
    for model in prereg.models:
        for seed in _seeds(prereg, model, extra_seeds):
            for fold in ("f0", "f1"):
                repo.write(  # um write por run (#119)
                    layer=_SILVER,
                    table="dim_run",
                    rows=[
                        {
                            "schema_version": 1,
                            "run_id": f"{sweep}-{model}-s{seed}-{fold}",
                            "asset": _ASSET,
                            "parent_sweep_id": sweep,
                            "feature_set_name": "fs-core",
                            "config_signature": f"sig-{model}",
                            "split_fingerprint": "split-e2e",
                            "fold": fold,
                            "seed": seed,
                            "model_version": model,
                        }
                    ],
                )
            for horizon in _HORIZONS:
                for decision in range(_FIRST_DECISION, _N_SESSIONS - horizon):
                    fold = "f0" if decision < middle else "f1"
                    target = decision + horizon
                    values = _quantiles(model, seed, horizon, target)
                    for level, value in zip(prereg.quantile_levels, values, strict=True):
                        facts.append(
                            {
                                "schema_version": 1,
                                "run_id": f"{sweep}-{model}-s{seed}-{fold}",
                                "model_version": model,
                                "asset": _ASSET,
                                "feature_set_name": "fs-core",
                                "split": "test",
                                "horizon": horizon,
                                "decision_idx": decision,
                                "timestamp_utc": _session(decision),
                                "target_timestamp_utc": _session(target),
                                "quantile_level": level,
                                "value_raw": value,
                                "value_guardrail": value,
                                "guardrail_applied": 0,
                                "year": int(_session(target)[:4]),
                            }
                        )
    repo.write(layer=_SILVER, table="fact_oos_predictions", rows=facts)


def _dataset_rows() -> list[dict[str, object]]:
    """`_WARMUP` linhas de aquecimento (NaN na 1ª feature) + as sessões do realizado."""
    features = [name for name in modeling_columns() if name != "target_return"]
    stamps = [_EPOCH - timedelta(days=_WARMUP - i) for i in range(_WARMUP)]
    stamps += [_EPOCH + timedelta(days=i) for i in range(_N_SESSIONS)]
    returns = [0.0] * _WARMUP + _realized()
    rows: list[dict[str, object]] = []
    for i, (stamp, target) in enumerate(zip(stamps, returns, strict=True)):
        row: dict[str, object] = {"timestamp": stamp, "asset_id": _ASSET, "target_return": target}
        for j, name in enumerate(features):
            row[name] = math.nan if (i < _WARMUP and j == 0) else math.sin(i + 1.5 * j)
        rows.append(row)
    return rows


def _write_dataset(data_root: Path) -> str:
    rows = _dataset_rows()
    target = data_root / "processed" / "dataset_tft" / _ASSET
    target.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(target / f"dataset_tft_{_ASSET}.parquet", index=False)
    grid = build_training_grid(rows, columns=modeling_columns())
    return grid_fingerprint(grid, hasher=CanonicalJsonHasher(), asset_id=_ASSET)


def _plan_payload(name: str, cohort: str, fingerprint: str) -> dict[str, object]:
    payload = valid_payload()
    for path, value in (
        ("name", name),
        ("horizons", [1, 2]),
        ("seeds.tft_quantile", [1, 2]),
        ("cohort.cohort_id", cohort),
        ("realized.dataset_fingerprint", fingerprint),
    ):
        payload = with_leaf(payload, path, value)
    return payload


def _freeze(root: Path, payload: dict[str, object]) -> tuple[Preregistration, str]:
    """Grava o plano e a âncora (por `to_toml`) e devolve o plano e a referência."""
    plan = Preregistration.from_mapping(payload)
    reference = plan.reference(
        PreregistrationHash.compute(hasher=CanonicalJsonHasher(), payload=plan.as_payload())
    )
    folder = root / "config" / "preregistration"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{plan.name}-r0.toml").write_text(to_toml(payload), encoding="utf-8")
    anchor = {
        "tag": f"preregistration/{reference}",
        "commit": "0123456789abcdef0123456789abcdef01234567",
        "comment_url": "https://github.com/example/repo/issues/1#issuecomment-1",
        "anchored_at": _ANCHORED_AT,
    }
    (folder / f"{plan.name}-r0.anchor.toml").write_text(to_toml(anchor), encoding="utf-8")
    return plan, reference


def _command(plan: Preregistration, reference: str) -> BuildConfirmatoryScorecardCommand:
    return BuildConfirmatoryScorecardCommand(
        name=plan.name, revision=0, preregistration_ref=reference
    )


@dataclass(frozen=True)
class _Scenario:
    tmp: Path
    settings: Settings
    refresh_status: RefreshStatus
    result: ScorecardResult
    changed_error: PreregistrationMismatchError
    extra_refresh_status: RefreshStatus
    extra_error: PreregistrationMismatchError


@pytest.fixture(scope="module")
def scenario(tmp_path_factory: pytest.TempPathFactory) -> _Scenario:
    tmp = tmp_path_factory.mktemp("e2e-scorecard")
    settings = Settings(
        _env_file=None,
        data_root=tmp / "data",
        repo_root=tmp,
        artifacts_root=tmp / "art",
        mlflow_tracking_uri=f"sqlite:///{tmp}/mlruns.db",
    )
    for root in (settings.data_root, settings.repo_root, settings.artifacts_root):
        assert Path(root).resolve().is_relative_to(tmp.resolve())  # antes de qualquer escrita
    deps = wire_dependencies(settings=settings)
    fingerprint = _write_dataset(settings.data_root)

    plan, reference = _freeze(tmp, _plan_payload("test_plan", _COHORT, fingerprint))
    _write_silver(deps, plan)
    refresh_status = deps.refresh_gold(refresh_command_from(plan, reference)).status
    result = deps.build_confirmatory_scorecard(_command(plan, reference))

    changed_payload = with_leaf(
        _plan_payload("test_plan_changed", _COHORT, fingerprint), "mcs.seed", 128
    )
    changed, changed_reference = _freeze(tmp, changed_payload)
    with pytest.raises(PreregistrationMismatchError) as changed_error:
        deps.build_confirmatory_scorecard(_command(changed, changed_reference))

    extra, extra_reference = _freeze(
        tmp, _plan_payload("test_plan_extra_seed", _COHORT_EXTRA, fingerprint)
    )
    _write_silver(deps, extra, extra_seeds=(3,))
    extra_status = deps.refresh_gold(refresh_command_from(extra, extra_reference)).status
    with pytest.raises(PreregistrationMismatchError) as extra_error:
        deps.build_confirmatory_scorecard(_command(extra, extra_reference))

    return _Scenario(
        tmp=tmp,
        settings=settings,
        refresh_status=refresh_status,
        result=result,
        changed_error=changed_error.value,
        extra_refresh_status=extra_status,
        extra_error=extra_error.value,
    )


def test_e2e_paths_under_tmp(scenario: _Scenario) -> None:
    tmp = scenario.tmp.resolve()
    for root in (
        scenario.settings.data_root,
        scenario.settings.repo_root,
        scenario.settings.artifacts_root,
    ):
        assert Path(root).resolve().is_relative_to(tmp)
    written = [p for p in tmp.rglob("*") if p.is_file()]
    assert written
    assert all(p.resolve().is_relative_to(tmp) for p in written)


def test_e2e_scorecard_expected_verdict(scenario: _Scenario) -> None:
    assert scenario.refresh_status is RefreshStatus.COMPLETED
    verdict = scenario.result.verdict
    assert [h.horizon for h in verdict.horizons] == [1, 2]
    for horizon in verdict.horizons:
        assert horizon.h1.passed is True, horizon.h1
        assert horizon.h2 is H2Outcome.BEATS_NAIVE_AND_STRONG
        assert horizon.primary_winner == _CANDIDATE
    assert verdict.study_success_h1 is True


def test_e2e_ready_after_anchor(scenario: _Scenario) -> None:
    result = scenario.result
    assert result.academic_decision_ready is True
    assert result.readiness_reasons == ()
    assert result.anchor.anchored_at == _ANCHORED_AT
    assert result.manifest_read.started_at >= _ANCHORED_AT


def test_e2e_parameter_changed_mismatch(scenario: _Scenario) -> None:
    assert scenario.changed_error.field == "preregistration_ref"


def test_e2e_extra_seed_mismatch(scenario: _Scenario) -> None:
    assert scenario.extra_refresh_status is RefreshStatus.COMPLETED
    assert scenario.extra_error.field == "seeds"


def test_e2e_result_mapping_serializable(scenario: _Scenario) -> None:
    decoded = json.loads(json.dumps(scenario.result.as_mapping()))
    assert decoded["preregistration_ref"] == scenario.result.preregistration_ref
    assert decoded["academic_decision_ready"] is True
    assert decoded["manifest_read"]["status"] == "COMPLETED"
    assert len(decoded["profile"]["horizons"]) == len(_HORIZONS)
