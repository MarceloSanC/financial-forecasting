"""Adapter `GitEvaluationEnvironment` — satisfaz o port `EvaluationEnvironment` (Stage 8.1).

Foto do código e do ambiente da corrida confirmatória (concept 8.1 D6, I13; ADR
`8_1_0003` item 6; technical 8.1 §1 "Chaves do `EvaluationEnvironment`"), com os nomes
de chave do `evaluation`:

- `commit` = `git rev-parse HEAD`;
- `preregistration_dir` sujo = `git status --porcelain --untracked-files=all -- <dir>`
  não vazio (um `.judged.toml` não commitado seria lido pelo G4);
- o probe da 5.5, recebido do composition root junto com o mapa chave-do-probe →
  chave-do-evaluation (`probe_keys`: as de código, que viram `code.*`) e a chave de
  sujeira do probe (`probe_dirty_key` → `code_dirty`); as demais chaves do probe viram
  `env.probe.<chave>`. Fail-closed (Checkpoint C 8.1, CC4-2): chave mapeada ausente da
  foto do probe, chave `code.*` do probe fora do mapa (mudança de código não pode virar
  mudança de ambiente no I13) ou sujeira fora de `"true"`/`"false"` → `RuntimeError`.
  Este módulo não importa o `modeling` (como o hash de `src/` é calculado continua sendo
  só do probe);
- `env.image_id` (obrigatório: sem ele → `MissingImageIdError`, antes de tocar o git),
  `env.platform` (`platform.platform()`), `env.cpu_count` (`os.cpu_count()`),
  `env.cpu_capability` (função injetada; no composition root, a do torch — o
  `evaluation` não importa `torch`) e `env.lib.<dist>` das `GOLD_LIBRARIES`
  (`importlib.metadata`; ausente → `"absent"`).

Usa o `git` do ambiente e respeita `GIT_DIR`/`GIT_WORK_TREE` (no container, o runbook
monta o `.git` do checkout principal para a worktree). Git indisponível é erro explícito.
"""

from __future__ import annotations

import os
import platform
import subprocess
from collections.abc import Callable, Mapping
from importlib import metadata
from pathlib import Path
from typing import Protocol

from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    CODE_DIRTY_KEY,
    CODE_PREFIX,
    COMMIT_KEY,
    CPU_CAPABILITY_KEY,
    CPU_COUNT_KEY,
    FALSE,
    GOLD_LIBRARIES,
    IMAGE_ID_KEY,
    PLATFORM_KEY,
    PREREGISTRATION_DIRTY_KEY,
    TRUE,
    MissingImageIdError,
    library_key,
    probe_key,
)
from financial_forecasting.shared.domain.services.git_commit import validate_git_commit_sha

_ABSENT = "absent"


class _Probe(Protocol):
    """O que o adapter usa do probe da 5.5 (uma foto chave → texto)."""

    def snapshot(self) -> Mapping[str, str]: ...


class GitEvaluationEnvironment:
    """Foto do código e do ambiente de um checkout git com o probe da 5.5."""

    def __init__(  # noqa: PLR0913 — as entradas do concept 8.1 D6, keyword-only
        self,
        *,
        repo_root: Path | str,
        probe: _Probe,
        probe_keys: Mapping[str, str],
        probe_dirty_key: str,
        image_id: str | None,
        cpu_capability: Callable[[], str],
        preregistration_dir: Path | str,
    ) -> None:
        """Guarda as entradas; o mapa do probe só pode produzir chaves `code.*`.

        Raises:
            ValueError: chave mapeada sem o prefixo `code.`, ou `preregistration_dir` fora
                do repositório.
        """
        for source, target in probe_keys.items():
            if not target.startswith(CODE_PREFIX):
                raise ValueError(
                    f"probe key {source!r} must map to a {CODE_PREFIX}* key, got {target!r}"
                )
        self._repo_root = Path(repo_root).resolve()
        directory = Path(preregistration_dir)
        if directory.is_absolute():
            try:
                directory = directory.resolve().relative_to(self._repo_root)
            except ValueError as exc:
                raise ValueError(
                    f"preregistration_dir {directory} is outside the repository {self._repo_root}"
                ) from exc
        self._preregistration_dir = directory.as_posix()
        self._probe = probe
        self._probe_keys = dict(probe_keys)
        self._probe_dirty_key = probe_dirty_key
        self._image_id = image_id
        self._cpu_capability = cpu_capability

    def snapshot(self) -> Mapping[str, str]:
        """A foto completa (ver docstring do módulo).

        Raises:
            MissingImageIdError: `image_id` ausente ou vazio.
            RuntimeError: git indisponível ou fora de um repositório; foto do probe sem
                uma chave mapeada, com chave `code.*` fora do mapa ou com sujeira fora de
                `"true"`/`"false"`.
        """
        if not self._image_id:
            raise MissingImageIdError(
                "the Docker image id is required (IMAGE_ID from `docker image inspect`)"
            )
        commit = self._git("rev-parse", "HEAD")
        validate_git_commit_sha(commit, field=COMMIT_KEY)
        status = self._git(
            "status", "--porcelain", "--untracked-files=all", "--", self._preregistration_dir
        )
        photo: dict[str, str] = {
            COMMIT_KEY: commit,
            PREREGISTRATION_DIRTY_KEY: TRUE if status else FALSE,
        }
        probe_photo = self._probe.snapshot()
        missing = sorted(set(self._probe_keys) - set(probe_photo))
        if missing:
            raise RuntimeError(f"the probe snapshot lacks the mapped code keys {missing}")
        for key, value in probe_photo.items():
            if key == self._probe_dirty_key:
                if value not in {TRUE, FALSE}:
                    raise RuntimeError(
                        f"the probe {key!r} must be {TRUE!r} or {FALSE!r}, got {value!r}"
                    )
                photo[CODE_DIRTY_KEY] = value
            elif key in self._probe_keys:
                photo[self._probe_keys[key]] = value
            elif key.startswith(CODE_PREFIX):
                raise RuntimeError(
                    f"the probe code key {key!r} is not mapped (it would be recorded as "
                    "environment, not code)"
                )
            else:
                photo[probe_key(key)] = value
        if CODE_DIRTY_KEY not in photo:
            raise RuntimeError(f"the probe snapshot has no {self._probe_dirty_key!r} key")
        photo[IMAGE_ID_KEY] = self._image_id
        photo[PLATFORM_KEY] = platform.platform()
        photo[CPU_COUNT_KEY] = str(os.cpu_count())
        photo[CPU_CAPABILITY_KEY] = self._cpu_capability()
        for name in GOLD_LIBRARIES:
            photo[library_key(name)] = self._version(name)
        return photo

    @staticmethod
    def _version(distribution: str) -> str:
        try:
            return metadata.version(distribution)
        except metadata.PackageNotFoundError:
            return _ABSENT

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
                f"git unavailable ({' '.join(args)}): {detail.strip()} — the code identity "
                "is required in the run record"
            ) from exc
        return completed.stdout.strip()
