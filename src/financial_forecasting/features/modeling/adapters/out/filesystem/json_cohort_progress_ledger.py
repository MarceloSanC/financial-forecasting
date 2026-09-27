"""Adapter `JsonCohortProgressLedger` — implementa o port `CohortProgressLedger` (Stage 5.5).

Layout (ADR 5.5.0003):

- `<artifacts_root>/cohorts/<cohort_id>/progress.json` — unidades concluídas,
  ambiente e instante de início;
- `<artifacts_root>/cohorts/<scope_id>/sweeps.json` — resultados dos sweeps;
- `<data_root>/.writer.lock` — lock de escritor único do `data_root`.

Toda gravação de JSON vai para um temporário no mesmo diretório e troca por
`os.replace` (atômico no mesmo sistema de arquivos): uma queda no meio deixa o
arquivo anterior intacto. O lock é criado com `O_CREAT | O_EXCL` (falha se já
existe) e guarda pid, host e início para identificar o dono; esta instância só
remove o lock que ela mesma adquiriu, e `break_stale=True` o remove de propósito.
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from financial_forecasting.features.modeling.application.ports.out.cohort_progress_ledger import (
    CohortRunLockedError,
)

_LOCK_NAME = ".writer.lock"
_PROGRESS_FILE = "progress.json"
_SWEEPS_FILE = "sweeps.json"


class JsonCohortProgressLedger:
    """Ledger do cohort em JSON sob `artifacts_root`, com lock no `data_root`."""

    def __init__(self, *, artifacts_root: Path | str, data_root: Path | str) -> None:
        self._cohorts_dir = Path(artifacts_root) / "cohorts"
        self._lock_path = Path(data_root) / _LOCK_NAME
        self._holds_lock = False

    # -- lock -----------------------------------------------------------------

    def acquire_writer(self, *, break_stale: bool = False) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        if break_stale:
            self._lock_path.unlink(missing_ok=True)
        owner = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started_at": datetime.now(tz=UTC).isoformat(),
        }
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise CohortRunLockedError(
                f"writer lock {self._lock_path} already held by {self._describe_owner()} — "
                "wait for it to finish or remove a stale lock with --break-stale-lock"
            ) from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(owner, handle)
        self._holds_lock = True

    def release_writer(self) -> None:
        if self._holds_lock:
            self._lock_path.unlink(missing_ok=True)
            self._holds_lock = False

    def _describe_owner(self) -> str:
        try:
            owner = json.loads(self._lock_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "an unknown owner (unreadable lock file)"
        return f"pid={owner.get('pid')} host={owner.get('host')} since={owner.get('started_at')}"

    # -- progresso ------------------------------------------------------------

    def completed_units(self, cohort_id: str) -> Mapping[str, Mapping[str, int]]:
        units = self._read(cohort_id, _PROGRESS_FILE).get("units", {})
        return {
            unit: {run: int(rows) for run, rows in runs.items()} for unit, runs in units.items()
        }

    def mark_completed(
        self, cohort_id: str, unit_key: str, rows_by_run: Mapping[str, int]
    ) -> None:
        state = self._read(cohort_id, _PROGRESS_FILE)
        units = state.setdefault("units", {})
        units[unit_key] = {run: int(rows) for run, rows in rows_by_run.items()}
        self._write(cohort_id, _PROGRESS_FILE, state)

    def environment(self, cohort_id: str) -> Mapping[str, str] | None:
        env = self._read(cohort_id, _PROGRESS_FILE).get("environment")
        return {str(key): str(value) for key, value in env.items()} if env is not None else None

    def record_environment(
        self, cohort_id: str, env: Mapping[str, str], *, started_at: str
    ) -> None:
        state = self._read(cohort_id, _PROGRESS_FILE)
        state["environment"] = dict(env)
        state.setdefault("run_started_at", started_at)
        self._write(cohort_id, _PROGRESS_FILE, state)

    def run_started_at(self, cohort_id: str) -> str | None:
        started = self._read(cohort_id, _PROGRESS_FILE).get("run_started_at")
        return str(started) if started is not None else None

    # -- sweeps ---------------------------------------------------------------

    def record_sweep_result(
        self, scope_id: str, model: str, result: Mapping[str, object]
    ) -> None:
        state = self._read(scope_id, _SWEEPS_FILE)
        state[model] = dict(result)
        self._write(scope_id, _SWEEPS_FILE, state)

    def sweep_results(self, scope_id: str) -> Mapping[str, Mapping[str, object]]:
        return {model: dict(result) for model, result in self._read(scope_id, _SWEEPS_FILE).items()}

    # -- JSON atômico ---------------------------------------------------------

    def _path(self, key: str, name: str) -> Path:
        return self._cohorts_dir / key / name

    def _read(self, key: str, name: str) -> dict[str, Any]:
        path = self._path(key, name)
        if not path.exists():
            return {}
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return dict(loaded)

    def _write(self, key: str, name: str, state: Mapping[str, object]) -> None:
        path = self._path(key, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        try:
            temp.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")
            os.replace(temp, path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
