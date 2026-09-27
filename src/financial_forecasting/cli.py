"""Ponto de entrada da linha de comando — runner do cohort confirmatório (Stage 5.5).

    python -m financial_forecasting.cli <subcomando> --data-root <dir> [...]

Subcomandos: `materialize` (brutos → bronze → dataset), `sweep`, `freeze`,
`run` e `verify` (comandos do cohort, em `features/modeling/adapters/in/cli`).
`--data-root` é obrigatório em todos, sem default: o dado de um cohort vive
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
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from financial_forecasting.composition_root import wire_dependencies
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
from financial_forecasting.shared.domain.exceptions.base import ApplicationError, DomainError
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
# Janela da materialização: a mesma janela ampla fixa do calendário do composition
# root. O que entra no dataset é decidido pelos brutos em `data_root`, não por ela.
_MATERIALIZE_START = datetime(1990, 1, 1, tzinfo=UTC)
_MATERIALIZE_END = datetime(2035, 12, 31, 23, 59, 59, tzinfo=UTC)
_SENTIMENT_MODULE = "transformers"
_EXIT_ERROR = 2


class MissingSentimentExtraError(ApplicationError):
    """O FinBERT real precisa do extra `sentiment` instalado no ambiente."""


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

    add("materialize", "ingere os brutos e materializa o dataset do ativo do cohort")
    sweep = add("sweep", "roda os dois sweeps exploratórios e grava os resultados")
    sweep.add_argument("--n-trials", type=int, default=None, help="sobrepõe sweep.n_trials")
    add("freeze", "congela o cohort com os resultados gravados dos sweeps")
    add("run", "corre o cohort congelado (retomável)")
    add("verify", "confere a corrida pela contagem no silver", lock=False)
    return parser


def main(
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
                out=stdout,
            )
        return _dispatch_cohort_command(args, deps, cohort_file, stdout)
    except (ApplicationError, DomainError, ValueError, RuntimeError, OSError, TypeError) as exc:
        # Erro de execução sai com 2; divergência do `verify` sai com 1
        # (`EXIT_MISMATCH`): um script distingue "diverge" de "quebrou".
        stderr.write(f"error: {type(exc).__name__}: {exc}\n")
        return _EXIT_ERROR


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


def _materialize(
    deps: ApplicationDependencies,
    *,
    asset_id: str,
    sentiment_injected: bool,
    break_stale_lock: bool,
    out: TextIO,
) -> int:
    """Brutos → bronze (x3) → dataset, sob o lock do `data_root`."""
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
                asset=asset_id, start=_MATERIALIZE_START.date(), end=date(2035, 12, 31)
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
