"""Ponto de entrada da linha de comando — runner do cohort confirmatório (Stage 5.5).

    python -m financial_forecasting.cli <subcomando> --data-root <dir> [...]

Subcomandos: `materialize` (brutos → bronze → dataset), `sweep`, `freeze`,
`run` e `verify` (comandos do cohort, em `features/modeling/adapters/in/cli`) e
`infer` (Stage 7.1: reproduz o teste a partir dos checkpoints e completa a partição
`calib`; `--break-stale-lock`, `--cross-environment "<justificativa>"`; comando em
`features/inference/adapters/in/cli`).
Stage 7.3: `ablation-pilot`, `ablation-run`, `ablation-verify` e `ablation-freeze
--seeds 1,2,…` (cohort de ablação; `--cohort` é o arquivo de ablação; comandos em
`features/modeling/adapters/in/cli/ablation_commands.py`) e `attribute --ablation-cohort
<toml>` (predições de atribuição do candidato no silver; `--cohort` é o confirmatório e o
`[partition]` vem do arquivo de ablação, lido aqui pelo loader do `modeling` — o slice
`inference` nunca importa esse loader).
Stage 8.1: `evaluate --preregistration <nome> --revision <r> --preregistration-ref <ref>
[--deviation "<justificativa com [deviation]>"]` — a corrida confirmatória: roda, no mesmo
processo, o `infer` da 7.1 sobre o mesmo cohort (`infer_with_summary`) e, só se ele
terminar sem exceção, o `RunConfirmatoryEvaluation` do `evaluation` com o resumo do
`infer` como dado (concept 8.1 D1). O encadeamento fica AQUI: o comando do `evaluation`
(`features/evaluation/adapters/in/cli`) não importa o `inference`.
Stage 8.2: `audit-reproduction --judged-data-root <dir> --reproduced-data-root <dir>
--preregistration <nome> --revision <r> --preregistration-ref <ref>` — só leitura, sem
`--data-root`, `--cohort` nem lock (não usa o helper `add()`); despachado ANTES do
`wire_dependencies` (não monta o grafo inteiro): monta só o `AuditReproduction` por
`composition_root.wire_reproduction_audit` (que recusa as duas raízes iguais, após
`resolve()`, antes de montar qualquer adapter), com `Settings(**settings_overrides)` (o
`repo_root` do pré-registro). Exit 0 só com `bit_identical`, 1 com diferença, 2 em erro.
Stage 8.3: `report-artifacts --data-root <dir> --cohort <toml> --preregistration <nome>
--revision <r> --preregistration-ref <ref> [--output <dir>] [--register <toml>]` — figuras
canônicas e dossiê da cópia julgada; só leitura sobre `data/` (sem lock). O cohort é lido
aqui (seeds e device); `--output` padrão `<repo_root>/docs/reports` e `--register` padrão
`<repo_root>/docs/reports/dossier_register.toml`; o registro é parseado pelo comando do
`evaluation` (fronteira) antes do use case.
`--data-root` é obrigatório nos demais, sem default: o dado de um cohort vive
isolado em `data/cohorts/<nome>/` (concept D10) e um default silencioso poderia
misturá-lo com o `data/` de desenvolvimento.

Como o `main.py` do servidor HTTP, este módulo fica na raiz do pacote: é um
adapter primário de processo que monta `Settings`, chama `wire_dependencies` e
despacha. Os comandos do cohort vivem sob `adapters/in/` (keyword `in`) e são
carregados por `importlib` (LAYOUT §8).

`main(argv, wiring=...)` aceita pontos de injeção para o ponta a ponta: o modelo
de sentimento, a fábrica do probe e overrides de `Settings` (`repo_root`,
`artifacts_root`). Em produção, nada é injetado: `Settings` vem do ambiente.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import logging
import sys
import traceback
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from financial_forecasting.composition_root import (
    wire_dependencies,
    wire_reproduction_audit,
)
from financial_forecasting.features.feature_engineering.application.use_cases.build_dataset import (
    BuildDatasetRequest,
)
from financial_forecasting.features.market_data.application.use_cases.ingest_candles import (
    IngestCandlesRequest,
)
from financial_forecasting.features.market_data.application.use_cases.ingest_fundamentals import (
    IngestFundamentalsRequest,
)
from financial_forecasting.features.market_data.application.use_cases.ingest_news import (
    IngestNewsRequest,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.exceptions.base import DomainError
from financial_forecasting.shared.infrastructure.config.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from types import ModuleType

    from financial_forecasting.composition_root import (
        ApplicationDependencies,
        RuntimeProbeFactory,
    )
    from financial_forecasting.features.feature_engineering.application.ports.out.sentiment_model import (  # noqa: E501
        SentimentModel,
    )

_CLI_PACKAGE = "financial_forecasting.features.modeling.adapters.in.cli"
_INFERENCE_COMMANDS = "financial_forecasting.features.inference.adapters.in.cli.inference_commands"
_EVALUATION_COMMANDS = (
    "financial_forecasting.features.evaluation.adapters.in.cli.evaluation_commands"
)
# Janela da materialização: a mesma janela ampla fixa do calendário do composition
# root. O que entra no dataset é decidido pelos brutos em `data_root`, não por ela.
_MATERIALIZE_START = datetime(1990, 1, 1, tzinfo=UTC)
_MATERIALIZE_END = datetime(2035, 12, 31, 23, 59, 59, tzinfo=UTC)
_SENTIMENT_MODULE = "transformers"
_EXIT_ERROR = 2
_ABLATION_PREFIX = "ablation-"
_INFERENCE_SUBCOMMANDS = frozenset({"infer", "attribute"})
_AUDIT_REPRODUCTION = "audit-reproduction"
_REPORT_ARTIFACTS = "report-artifacts"
_REPORTS_DIR = Path("docs") / "reports"
_REGISTER_FILE = "dossier_register.toml"


class MissingSentimentExtraError(ApplicationError):
    """O FinBERT real precisa do extra `sentiment` instalado no ambiente."""


class DatasetStartConflictError(ApplicationError):
    """`--start` e o `dataset_start` do arquivo do cohort declaram datas diferentes."""


@dataclass(frozen=True)
class CliWiring:
    """Injeções do ponta a ponta; vazio em produção."""

    sentiment_model: SentimentModel | None = None
    runtime_probe_factory: RuntimeProbeFactory | None = None
    settings_overrides: Mapping[str, Any] = field(default_factory=dict)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m financial_forecasting.cli",
        description="Runner do cohort confirmatório (Stage 5.5).",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def add(
        name: str, help_text: str, *, cohort: bool = True, lock: bool = True
    ) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--data-root", type=Path, required=True, help="raiz do dado do cohort")
        if cohort:
            sub.add_argument("--cohort", type=Path, required=True, help="arquivo TOML do cohort")
        if lock:
            sub.add_argument(
                "--break-stale-lock",
                action="store_true",
                help="remove um lock órfão (processo morto) antes de adquirir",
            )
        return sub

    materialize = add("materialize", "ingere os brutos e materializa o dataset do ativo do cohort")
    materialize.add_argument(
        "--start",
        type=date.fromisoformat,
        default=None,
        help=(
            "primeira sessão do dataset (AAAA-MM-DD); os brutos são ingeridos inteiros. "
            "Usado quando o gate de qualidade recusa o começo da série (R9 da 5.5). "
            "Sem ele, vale o dataset_start do arquivo do cohort; os dois diferentes é erro."
        ),
    )
    sweep = add("sweep", "roda os dois sweeps exploratórios e grava os resultados")
    sweep.add_argument("--n-trials", type=int, default=None, help="sobrepõe sweep.n_trials")
    add("freeze", "congela o cohort com os resultados gravados dos sweeps")
    add("run", "corre o cohort congelado (retomável)")
    add("verify", "confere a corrida pela contagem no silver", lock=False)
    infer = add("infer", "reproduz o teste dos checkpoints e completa a partição calib")
    infer.add_argument(
        "--cross-environment",
        default=None,
        metavar="JUSTIFICATIVA",
        help="força o modo tolerance com a justificativa gravada no manifesto",
    )
    attribute = add("attribute", "grava as predições de atribuição e os pesos da VSN do candidato")
    attribute.add_argument(
        "--ablation-cohort",
        type=Path,
        required=True,
        help="arquivo TOML do cohort de ablação (fonte do [partition])",
    )
    attribute.add_argument(
        "--cross-environment",
        default=None,
        metavar="JUSTIFICATIVA",
        help="força o modo tolerance com a justificativa gravada no manifesto",
    )
    evaluate = add(
        "evaluate", "roda o infer e a corrida confirmatória do cohort contra uma revisão julgada"
    )
    evaluate.add_argument(
        "--preregistration", required=True, metavar="NOME", help="nome do plano pré-registrado"
    )
    evaluate.add_argument(
        "--revision", type=int, required=True, help="revisão julgada do plano (ex.: 3)"
    )
    evaluate.add_argument(
        "--preregistration-ref",
        required=True,
        metavar="REF",
        help="referência esperada da revisão (<nome>-r<rev>-<hash12>)",
    )
    evaluate.add_argument(
        "--deviation",
        default=None,
        metavar="JUSTIFICATIVA",
        help="re-tentativa com código, ambiente ou entrada diferentes; cita um [deviation]",
    )
    add("ablation-pilot", "mede o custo de uma unidade da ablação (não grava nada)", lock=False)
    add("ablation-run", "corre o cohort de ablação congelado (retomável)")
    add("ablation-verify", "confere a corrida da ablação pela contagem no silver", lock=False)
    ablation_freeze = add(
        "ablation-freeze",
        "congela o cohort de ablação com as seeds e o torch observado",
        lock=False,
    )
    ablation_freeze.add_argument(
        "--seeds", type=_seed_list, required=True, help="seeds do cohort, ex.: 1,2,3"
    )
    # Stage 8.3: só leitura sobre `data/` — pelo helper, sem lock
    report = add(
        _REPORT_ARTIFACTS, "gera as figuras canônicas e o dossiê da cópia julgada", lock=False
    )
    report.add_argument(
        "--preregistration", required=True, metavar="NOME", help="nome do plano pré-registrado"
    )
    report.add_argument("--revision", type=int, required=True, help="revisão julgada do plano")
    report.add_argument(
        "--preregistration-ref",
        required=True,
        metavar="REF",
        help="referência esperada da revisão (<nome>-r<rev>-<hash12>)",
    )
    report.add_argument(
        "--output", type=Path, default=None, help="diretório de saída (padrão docs/reports)"
    )
    report.add_argument(
        "--register",
        type=Path,
        default=None,
        help="registro curado (padrão docs/reports/dossier_register.toml)",
    )
    # Stage 8.2: só leitura, sem `--data-root`/`--cohort`/lock — fora do helper `add()`
    audit = commands.add_parser(
        _AUDIT_REPRODUCTION, help="compara a geração reproduzida com a cópia julgada"
    )
    audit.add_argument(
        "--judged-data-root", type=Path, required=True, help="raiz com a cópia julgada"
    )
    audit.add_argument(
        "--reproduced-data-root",
        type=Path,
        required=True,
        help="raiz descartável com a geração e o reproduction/scorecard.json do driver",
    )
    audit.add_argument(
        "--preregistration", required=True, metavar="NOME", help="nome do plano pré-registrado"
    )
    audit.add_argument("--revision", type=int, required=True, help="revisão julgada do plano")
    audit.add_argument(
        "--preregistration-ref",
        required=True,
        metavar="REF",
        help="referência esperada da revisão (<nome>-r<rev>-<hash12>)",
    )
    return parser


def _seed_list(text: str) -> tuple[int, ...]:
    """`1,2,3` → `(1, 2, 3)`; o spec recusa seed repetida ou não positiva."""
    try:
        return tuple(int(part) for part in text.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"seeds must be integers separated by commas: {text!r}"
        ) from exc


def main(  # noqa: PLR0911 — um return por família de subcomando
    argv: Sequence[str] | None = None,
    *,
    wiring: CliWiring | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Despacha o subcomando; erros esperados viram mensagem e exit code 2."""
    args = _parser().parse_args(argv)
    # Uma linha por unidade do cohort (início, desfecho, tempo) no stderr.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    injected = wiring or CliWiring()
    stdout = out or sys.stdout
    stderr = err or sys.stderr
    cohort_file = importlib.import_module(f"{_CLI_PACKAGE}.cohort_file")
    try:
        if args.command == _AUDIT_REPRODUCTION:
            return _dispatch_audit_reproduction(args, injected, stdout)
        settings = Settings(data_root=args.data_root, **injected.settings_overrides)
        deps = wire_dependencies(
            settings,
            sentiment_model=injected.sentiment_model,
            runtime_probe_factory=injected.runtime_probe_factory,
        )
        if args.command == "materialize":
            spec = cohort_file.load(args.cohort)
            return _materialize(
                deps,
                asset_id=spec.asset_id,
                sentiment_injected=injected.sentiment_model is not None,
                break_stale_lock=args.break_stale_lock,
                dataset_start=_dataset_start(args.start, spec.dataset_start),
                out=stdout,
            )
        if args.command in _INFERENCE_SUBCOMMANDS or args.command == "evaluate":
            # `evaluate` (8.1) encadeia o `infer` do `inference` ao use case do `evaluation`
            dispatch = (
                _dispatch_evaluate if args.command == "evaluate" else _dispatch_inference_command
            )
            return dispatch(args, deps, cohort_file, stdout)
        if args.command == _REPORT_ARTIFACTS:
            return _dispatch_report_artifacts(args, deps, settings, cohort_file, stdout)
        if args.command.startswith(_ABLATION_PREFIX):
            return _dispatch_ablation_command(args, deps, stdout)
        return _dispatch_cohort_command(args, deps, cohort_file, stdout)
    except (ApplicationError, DomainError, ValueError, RuntimeError, OSError, TypeError) as exc:
        # Erro de execução sai com 2; divergência do `verify` sai com 1
        # (`EXIT_MISMATCH`): um script distingue "diverge" de "quebrou".
        stderr.write(f"error: {type(exc).__name__}: {exc}\n")
        return _EXIT_ERROR
    except Exception:
        # Falha inesperada (bug): traceback completo, e ainda assim exit 2 —
        # nunca o 1 do `verify` ("a corrida diverge").
        traceback.print_exc(file=stderr)
        return _EXIT_ERROR


def _dispatch_audit_reproduction(args: argparse.Namespace, injected: CliWiring, out: TextIO) -> int:
    """`audit-reproduction` (8.2): o `wire_reproduction_audit` recusa raízes iguais antes de
    montar adapter algum (dono único da recusa, CC2-1)."""
    judged_root: Path = args.judged_data_root
    reproduced_root: Path = args.reproduced_data_root
    audit = wire_reproduction_audit(
        Settings(**injected.settings_overrides),
        judged_data_root=judged_root,
        reproduced_data_root=reproduced_root,
    )
    evaluation = importlib.import_module(_EVALUATION_COMMANDS)
    exit_code: int = evaluation.audit_reproduction(
        audit,
        reproduced_data_root=reproduced_root,
        name=args.preregistration,
        revision=args.revision,
        preregistration_ref=args.preregistration_ref,
        out=out,
    )
    return exit_code


def _dispatch_report_artifacts(
    args: argparse.Namespace,
    deps: ApplicationDependencies,
    settings: Settings,
    cohort_file: ModuleType,
    out: TextIO,
) -> int:
    """`report-artifacts` (8.3): seeds e device do cohort lidos aqui (o `evaluation` não
    importa o `modeling`); saída e registro com padrão sob o `repo_root`."""
    spec = cohort_file.load(args.cohort)
    reports = Path(settings.repo_root) / _REPORTS_DIR
    output: Path = args.output if args.output is not None else reports
    register: Path = args.register if args.register is not None else reports / _REGISTER_FILE
    evaluation = importlib.import_module(_EVALUATION_COMMANDS)
    exit_code: int = evaluation.report_artifacts(
        deps.generate_report_artifacts_for(args.cohort, spec.device, output),
        register_path=register,
        name=args.preregistration,
        revision=args.revision,
        preregistration_ref=args.preregistration_ref,
        cohort_seeds=tuple(spec.seeds),
        out=out,
    )
    return exit_code


def _dispatch_cohort_command(
    args: argparse.Namespace, deps: ApplicationDependencies, cohort_file: ModuleType, out: TextIO
) -> int:
    commands = importlib.import_module(f"{_CLI_PACKAGE}.cohort_commands")
    command_deps = commands.CohortCommandDeps(
        store=deps.store,
        hasher=deps.hasher,
        ledger=deps.cohort_ledger,
        run_index=deps.cohort_run_index,
        run_tft_sweep=deps.run_tft_sweep,
        run_gbm_sweep=deps.run_gbm_sweep,
        confirmatory_cohort_for=deps.confirmatory_cohort_for,
        modeling_columns=deps.modeling_columns,
        load_spec=cohort_file.load,
        parse_spec=cohort_file.parse,
        dump_spec=cohort_file.dump,
    )
    if args.command == "sweep":
        exit_code: int = commands.sweep(
            command_deps,
            args.cohort,
            out=out,
            n_trials=args.n_trials,
            break_stale_lock=args.break_stale_lock,
        )
    elif args.command == "freeze":
        exit_code = commands.freeze(
            command_deps, args.cohort, out=out, break_stale_lock=args.break_stale_lock
        )
    elif args.command == "run":
        exit_code = commands.run(
            command_deps, args.cohort, out=out, break_stale_lock=args.break_stale_lock
        )
    else:
        exit_code = commands.verify(command_deps, args.cohort, out=out)
    return exit_code


def _dispatch_inference_command(
    args: argparse.Namespace, deps: ApplicationDependencies, cohort_file: ModuleType, out: TextIO
) -> int:
    """`infer` (7.1) e `attribute` (7.3): comandos do slice `inference`.

    O `attribute` recebe o `[partition]` do arquivo de ablação lido AQUI, pelo loader do
    `modeling` (`deps.load_ablation_spec`): o slice `inference` nunca importa esse loader.
    """
    commands = importlib.import_module(_INFERENCE_COMMANDS)
    exit_code: int
    if args.command == "infer":
        exit_code = commands.infer(
            deps.run_inference_for,
            cohort_file.load(args.cohort),
            args.cohort,
            out=out,
            break_stale_lock=args.break_stale_lock,
            cross_environment=args.cross_environment,
        )
    else:
        ablation_spec, _ = deps.load_ablation_spec(args.ablation_cohort)
        # C6-8: o use case confere a base; a recusa (ApplicationError) vira exit 2 no `main`
        exit_code = commands.attribute(
            deps.permutation_inference_for,
            cohort_file.load(args.cohort),
            args.cohort,
            ablation_spec.family_partition,
            ablation_spec.base_cohort_hash,
            out=out,
            break_stale_lock=args.break_stale_lock,
            cross_environment=args.cross_environment,
        )
    return exit_code


def _dispatch_evaluate(
    args: argparse.Namespace, deps: ApplicationDependencies, cohort_file: ModuleType, out: TextIO
) -> int:
    """`evaluate` (8.1): o `infer` da 7.1 e, só sem exceção, a corrida confirmatória (D1).

    O `infer` toma e libera o seu lock; o use case toma o dele depois (D8). O resumo do
    `infer` passa como dado: nenhum slice importa o outro.
    """
    spec = cohort_file.load(args.cohort)
    inference = importlib.import_module(_INFERENCE_COMMANDS)
    summary = inference.infer_with_summary(
        deps.run_inference_for,
        spec,
        args.cohort,
        out=out,
        break_stale_lock=args.break_stale_lock,
    )
    evaluation = importlib.import_module(_EVALUATION_COMMANDS)
    exit_code: int = evaluation.evaluate(
        deps.run_confirmatory_evaluation_for(args.cohort, spec.device),
        name=args.preregistration,
        revision=args.revision,
        preregistration_ref=args.preregistration_ref,
        inference_summary=summary,
        break_stale_lock=args.break_stale_lock,
        deviation=args.deviation,
        out=out,
    )
    return exit_code


def _dispatch_ablation_command(
    args: argparse.Namespace, deps: ApplicationDependencies, out: TextIO
) -> int:
    commands = importlib.import_module(f"{_CLI_PACKAGE}.ablation_commands")
    command_deps = commands.AblationCommandDeps(
        hasher=deps.hasher,
        ledger=deps.cohort_ledger,
        run_index=deps.cohort_run_index,
        load_spec=deps.load_ablation_spec,
        dump_spec=deps.dump_ablation_spec,
        ablation_cohort_for=deps.ablation_cohort_for,
        measure_ablation_cost_for=deps.measure_ablation_cost_for,
        runtime_probe_for=deps.runtime_probe_for,
        supported_devices=deps.supported_devices,
    )
    exit_code: int
    if args.command == "ablation-pilot":
        exit_code = commands.pilot(command_deps, args.cohort, out=out)
    elif args.command == "ablation-run":
        exit_code = commands.run(
            command_deps, args.cohort, out=out, break_stale_lock=args.break_stale_lock
        )
    elif args.command == "ablation-verify":
        exit_code = commands.verify(command_deps, args.cohort, out=out)
    else:
        exit_code = commands.freeze(command_deps, args.cohort, out=out, seeds=args.seeds)
    return exit_code


def _dataset_start(cli_start: date | None, declared: date | None) -> date | None:
    """O início do dataset: o do arquivo do cohort, ou o `--start` (#122).

    Os dois presentes precisam concordar — divergência é erro que nomeia os dois,
    nunca uma precedência silenciosa que materializaria outro dado que o declarado.
    """
    if cli_start is not None and declared is not None and cli_start != declared:
        raise DatasetStartConflictError(
            f"--start {cli_start.isoformat()} differs from the cohort file's "
            f"dataset_start {declared.isoformat()}; drop --start or fix the file"
        )
    return declared or cli_start


def _materialize(  # noqa: PLR0913 — opções coesas do subcomando
    deps: ApplicationDependencies,
    *,
    asset_id: str,
    sentiment_injected: bool,
    break_stale_lock: bool,
    out: TextIO,
    dataset_start: date | None = None,
) -> int:
    """Brutos → bronze (x3) → dataset, sob o lock do `data_root`.

    `dataset_start` corta só o dataset: bronze e sentimento veem os brutos
    inteiros. Serve para começar a série onde os fundamentos já valem (R9).
    """
    if not sentiment_injected and importlib.util.find_spec(_SENTIMENT_MODULE) is None:
        raise MissingSentimentExtraError(
            "the FinBERT sentiment model needs the 'sentiment' extra — "
            "run `uv sync --extra dev --extra sentiment` in the container"
        )
    deps.cohort_ledger.acquire_writer(break_stale=break_stale_lock)
    try:
        candles = deps.ingest_candles.execute(
            IngestCandlesRequest(asset=asset_id, start=_MATERIALIZE_START, end=_MATERIALIZE_END)
        )
        news = deps.ingest_news.execute(
            IngestNewsRequest(asset=asset_id, start=_MATERIALIZE_START, end=_MATERIALIZE_END)
        )
        fundamentals = deps.ingest_fundamentals.execute(
            IngestFundamentalsRequest(asset_id=asset_id)
        )
        dataset = deps.build_dataset.execute(
            BuildDatasetRequest(
                asset=asset_id,
                start=dataset_start or _MATERIALIZE_START.date(),
                end=_MATERIALIZE_END.date(),
            )
        )
    finally:
        deps.cohort_ledger.release_writer()
    out.write(
        f"materialized {asset_id}: {candles.ingested} candles, {news.ingested} news, "
        f"{fundamentals.ingested} fundamentals\n"
        f"dataset rows {dataset.n_rows} ({dataset.start}..{dataset.end}), "
        f"feature_set_hash {dataset.feature_set_hash}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
