"""Guardas de regressão da Stage 7.3 — o que o import-linter não vê.

Os dois executores de cohort (`run_confirmatory_cohort` e `run_ablation_cohort`)
compartilham a máquina de unidades de `cohort_unit_runner` e nunca importam um ao outro
(concept 7.3 D7; ADR 7.3.0003 item 3). O import-linter não cobre o caso: os dois
estão no mesmo slice e na mesma camada, e imports sob `TYPE_CHECKING` são invisíveis a
ele. A guarda lê o AST e acusa as três formas: `from … import …`, `import …` (inclusive
sob `if TYPE_CHECKING:`) e `importlib.import_module("…")` com constante.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]
_USE_CASES = _REPO / "src/financial_forecasting/features/modeling/application/use_cases"
_PACKAGE = "financial_forecasting.features.modeling.application.use_cases"
_CONFIRMATORY = f"{_PACKAGE}.run_confirmatory_cohort"
_ABLATION = f"{_PACKAGE}.run_ablation_cohort"
_RUNNER = f"{_PACKAGE}.cohort_unit_runner"


def _absolute(module: str | None, level: int, package: str) -> str:
    """O nome absoluto de um `from` relativo, resolvido contra `package` (C2-5)."""
    if level == 0:
        return module or ""
    parts = package.split(".")
    base = ".".join(parts[: len(parts) - (level - 1)])
    return f"{base}.{module}" if module else base


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _constant_target(node: ast.Call) -> str | None:
    """O módulo constante de `import_module(...)`/`__import__(...)`, posicional ou `name=`."""
    candidates = [*node.args[:1], *(kw.value for kw in node.keywords if kw.arg == "name")]
    for candidate in candidates:
        if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
            return candidate.value
    return None


def imported_modules(source: str, *, package: str = _PACKAGE) -> set[str]:
    """Módulos importados por qualquer forma (absoluta, relativa ou dinâmica).

    `from pacote import modulo` conta como `pacote.modulo` (o nome pode ser um
    submódulo), além do próprio `pacote`. `from . import x` e `from .x import y` são
    resolvidos contra `package` (o pacote dos executores). `importlib.import_module` e
    `__import__` com o nome constante, posicional ou `name=`, também contam.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = _absolute(node.module, node.level, package)
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and _call_name(node) in {"import_module", "__import__"}:
            target = _constant_target(node)
            if target is not None:
                found.add(target)
    return found


def _imports(path: Path) -> set[str]:
    return imported_modules(path.read_text(encoding="utf-8"))


def test_cohort_runners_never_import_each_other() -> None:
    confirmatory = _imports(_USE_CASES / "run_confirmatory_cohort.py")
    ablation = _imports(_USE_CASES / "run_ablation_cohort.py")

    assert _ABLATION not in confirmatory
    assert _CONFIRMATORY not in ablation
    assert _RUNNER in confirmatory
    assert _RUNNER in ablation


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(f"from {_CONFIRMATORY} import tft_train_command\n", id="from-module"),
        pytest.param(f"from {_PACKAGE} import run_confirmatory_cohort\n", id="from-package"),
        pytest.param(f"import {_CONFIRMATORY} as other\n", id="import"),
        pytest.param(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            f"    from {_CONFIRMATORY} import RunConfirmatoryCohort\n",
            id="type-checking",
        ),
        pytest.param(
            f"import importlib\nmodule = importlib.import_module({_CONFIRMATORY!r})\n",
            id="importlib",
        ),
        pytest.param(
            f"from importlib import import_module\nmodule = import_module({_CONFIRMATORY!r})\n",
            id="import-module-name",
        ),
        pytest.param("from . import run_confirmatory_cohort\n", id="relative-package"),
        pytest.param("from .run_confirmatory_cohort import X\n", id="relative-module"),
        pytest.param(f"module = __import__({_CONFIRMATORY!r})\n", id="dunder-import"),
        pytest.param(
            f"import importlib\nmodule = importlib.import_module(name={_CONFIRMATORY!r})\n",
            id="import-module-keyword",
        ),
    ],
)
def test_guard_catches_every_import_form(tmp_path: Path, source: str) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text(source, encoding="utf-8")
    assert _CONFIRMATORY in _imports(planted)


# --- Task 29: matrícula dos módulos novos e isolamento do evaluation ----------------------

_SRC = _REPO / "src"
_IMPORTLINTER = _REPO / ".importlinter"
_EVALUATION = _SRC / "financial_forecasting/features/evaluation"
# Os módulos de `src/` criados pela Stage 7.3 (diff contra a base 0f461e1, Tasks 01-29).
_STAGE_MODULES = (
    "features/analytics_store/adapters/out/parquet/schemas/fact_permuted_predictions_schema",
    "features/analytics_store/adapters/out/parquet/schemas/fact_vsn_weights_schema",
    "features/analytics_store/application/use_cases/persist_permuted_predictions",
    "features/analytics_store/application/use_cases/persist_vsn_weights",
    "features/evaluation/adapters/out/duckdb/gold_builders/h3_importance",
    "features/evaluation/adapters/out/duckdb/gold_builders/h3_reading",
    "features/evaluation/adapters/out/duckdb/gold_builders/h3_shares",
    "features/evaluation/adapters/out/duckdb/gold_builders/h3_vsn",
    "features/evaluation/domain/services/attribution_assembly",
    "features/evaluation/domain/services/contribution_agreement",
    "features/evaluation/domain/services/family_contribution",
    "features/evaluation/domain/services/vsn_summary",
    "features/evaluation/domain/value_objects/ablation_run_losses",
    "features/evaluation/domain/value_objects/family_loss_differentials",
    "features/evaluation/domain/value_objects/h3_parameters",
    "features/evaluation/domain/value_objects/permuted_forecast_record",
    "features/evaluation/domain/value_objects/permuted_run_losses",
    "features/evaluation/domain/value_objects/vsn_run_weights",
    "features/evaluation/domain/value_objects/vsn_weight_record",
    "features/inference/adapters/out/filesystem/json_attribution_manifest",
    "features/inference/application/ports/out/attribution_manifest",
    "features/inference/application/ports/out/checkpoint_attribution_predictor",
    "features/inference/application/ports/out/permuted_prediction_persister",
    "features/inference/application/ports/out/vsn_weight_persister",
    "features/inference/application/use_cases/run_permutation_inference",
    "features/inference/domain/value_objects/permutation_plan",
    "features/modeling/adapters/in/cli/ablation_cohort_file",
    "features/modeling/adapters/in/cli/ablation_commands",
    "features/modeling/application/dtos/ablation_cohort_spec",
    "features/modeling/application/use_cases/cohort_unit_runner",
    "features/modeling/application/use_cases/measure_ablation_cost",
    "features/modeling/application/use_cases/predict_tft_attribution_from_checkpoints",
    "features/modeling/application/use_cases/run_ablation_cohort",
    "features/modeling/domain/services/loco_identity",
    "shared/domain/value_objects/family_partition_hash",
)


def _contracts() -> dict[str, list[str]]:
    """Contrato → módulos listados em `source_modules`, `containers` ou `modules`."""
    contracts: dict[str, list[str]] = {}
    current: str | None = None
    listing = False
    for raw in _IMPORTLINTER.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if raw.startswith("[importlinter:contract:"):
            current = raw.strip("[]").split(":", 2)[2]
            contracts[current] = []
            listing = False
        elif current is None or not line or line.startswith("#"):
            continue
        elif not raw[0].isspace():
            key = line.split("=", 1)[0].strip()
            listing = key in {"source_modules", "containers", "modules"}
            value = line.split("=", 1)[1].strip() if "=" in line else ""
            if listing and value:
                contracts[current].append(value)
        elif listing:
            contracts[current].append(line)
    return contracts


def _dotted(path: str) -> str:
    return "financial_forecasting." + path.replace("/", ".")


def _covers(entry: str, module: str) -> bool:
    return module == entry or module.startswith(entry + ".")


def _layer_package(module: str) -> str:
    parts = module.split(".")
    return ".".join(parts[:4] if parts[1] == "features" else parts[:3])


@pytest.mark.unit
def test_stage_7_3_new_modules_are_enrolled() -> None:
    """Cada módulo novo está sob todo contrato da sua camada e do seu slice (§1)."""
    contracts = _contracts()
    problems: list[str] = []
    for path in _STAGE_MODULES:
        assert (_SRC / "financial_forecasting" / f"{path}.py").exists(), path
        module = _dotted(path)
        layer = _layer_package(module)
        slice_ = ".".join(module.split(".")[:3])
        applicable = {
            name
            for name, entries in contracts.items()
            if any(_covers(entry, layer) or entry == slice_ for entry in entries)
        }
        for name in sorted(applicable):
            if not any(_covers(entry, module) for entry in contracts[name]):
                problems.append(f"{module} is not enrolled in {name}")
        required = {"hexagonal-layers"}
        required |= {"shared-no-features"} if path.startswith("shared/") else {"bc-independence"}
        if ".domain." in module:
            required |= {"domain-purity", "inward-only"}
        elif ".application." in module:
            required |= {"inward-only"}
        problems += [f"{module} misses {name}" for name in sorted(required - applicable)]
    assert problems == []


def _features_imported(path: Path) -> set[str]:
    return {
        module
        for module in imported_modules(path.read_text(encoding="utf-8"))
        if module.startswith(
            (
                "financial_forecasting.features.inference",
                "financial_forecasting.features.modeling",
            )
        )
    }


@pytest.mark.unit
def test_h3_builders_dtos_and_domain_never_import_inference_or_modeling() -> None:
    """O gold de H3 só vê tipos do `evaluation` (G7): nada do inference nem do modeling."""
    folders = ("application/dtos", "adapters/out/duckdb/gold_builders", "domain")
    offenders = [
        f"{path.relative_to(_EVALUATION).as_posix()}: {sorted(_features_imported(path))}"
        for folder in folders
        for path in sorted((_EVALUATION / folder).rglob("*.py"))
        if _features_imported(path)
    ]
    assert offenders == []
