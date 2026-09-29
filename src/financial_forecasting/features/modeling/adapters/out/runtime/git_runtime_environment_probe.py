"""Adapter `GitRuntimeEnvironmentProbe` — implementa o port `RuntimeEnvironmentProbe` (Stage 5.5).

Foto do ambiente da corrida confirmatória:

- versões das bibliotecas (`importlib.metadata`) e do Python;
- device declarado do cohort, threads do torch e CPU;
- identidade do código: `git rev-parse HEAD:<caminho>` de `src`, `uv.lock` e do
  arquivo do cohort — hash de CONTEÚDO do que está commitado, então commits só
  de documentação não mudam a foto;
- `code_dirty`: `git status --porcelain --untracked-files=all` NESSES caminhos —
  mudança rastreada não commitada (inclusive em stage) ou arquivo novo não
  ignorado dentro de `src/` (seria importado) marca `"true"`; fora desses
  caminhos nada conta (`artifacts/` e `data/` são ignorados pelo git).

Usa o `git` do ambiente e respeita `GIT_DIR`/`GIT_WORK_TREE` — no container, o
runbook monta o `.git` do checkout principal para a worktree (ADR 5.5.0003).
Git indisponível é erro explícito: uma foto sem a identidade do código não pode
servir de âncora para a retomada.
"""

from __future__ import annotations

import os
import platform
import subprocess
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path

from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
    LIBRARY_KEYS,
)

_PYTHON = "python"


class GitRuntimeEnvironmentProbe:
    """Foto do ambiente e da identidade do código de um checkout git."""

    def __init__(self, *, repo_root: Path | str, cohort_file: Path | str, device: str) -> None:
        self._repo_root = Path(repo_root).resolve()
        cohort = Path(cohort_file)
        if cohort.is_absolute():
            try:
                cohort = cohort.resolve().relative_to(self._repo_root)
            except ValueError as exc:
                raise RuntimeError(
                    f"cohort file {cohort} is outside the repository {self._repo_root} — "
                    "the code identity is required to anchor a cohort run"
                ) from exc
        self._cohort_path = cohort.as_posix()
        self._device = device

    def snapshot(self) -> Mapping[str, str]:
        # Os pathspecs do `git status` são relativos ao diretório de trabalho:
        # num subdiretório do repositório, `src` não casaria nada e `code_dirty`
        # sairia sempre "false". Por isso a raiz tem de ser a do repositório.
        top = Path(self._git("rev-parse", "--show-toplevel")).resolve()
        if top != self._repo_root:
            raise RuntimeError(
                f"repo_root {self._repo_root} is not the repository root {top} — "
                "run from the repository root (or set REPO_ROOT to it)"
            )
        tracked = {
            "code.src": "src",
            "code.uv_lock": "uv.lock",
            "code.cohort_file": self._cohort_path,
        }
        snapshot = {key: self._version(key) for key in LIBRARY_KEYS}
        snapshot["device"] = self._device
        snapshot["torch_threads"] = self._torch_threads()
        snapshot["cpu"] = f"{platform.machine()}/{os.cpu_count()}"
        for key, path in tracked.items():
            snapshot[key] = self._git("rev-parse", f"HEAD:{path}")
        status = self._git(
            "status", "--porcelain", "--untracked-files=all", "--", *tracked.values()
        )
        snapshot[DIRTY_KEY] = "true" if status else "false"
        return snapshot

    @staticmethod
    def _version(distribution: str) -> str:
        if distribution == _PYTHON:
            return platform.python_version()
        try:
            return metadata.version(distribution)
        except metadata.PackageNotFoundError:
            return "absent"

    @staticmethod
    def _torch_threads() -> str:
        import torch  # noqa: PLC0415 — só quando a foto é tirada

        return str(torch.get_num_threads())

    def _git(self, *args: str) -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise RuntimeError(
                f"git unavailable or path not committed ({' '.join(args)}): {detail.strip()} — "
                "the code identity is required to anchor a cohort run"
            ) from exc
        return completed.stdout.strip()
