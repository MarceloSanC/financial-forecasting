"""Adapter `JsonInferenceManifest` — satisfaz o port `InferenceManifest` do `inference` (7.1).

Arquivo `<data_root>/inference/<cohort_id>/manifest.json` (ADR 7.1.0004 item 4):
ao lado do silver que descreve e sob o mesmo lock de escritor; uma cópia do
`data_root` leva o próprio manifesto. JSON UTF-8, `indent=2`, `sort_keys=True`.

Toda gravação vai para um temporário no mesmo diretório
(`manifest.json.tmp-<pid>`) e troca por `os.replace` (atômico no mesmo sistema de
arquivos): uma queda do processo no meio deixa o arquivo anterior intacto. A
mescla é a do port (`apply_run_entry`): campos de primeira escrita nunca são
sobrescritos; o cabeçalho `cohort_environment` é gravado uma vez.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from financial_forecasting.features.inference.application.ports.out.inference_manifest import (
    apply_run_entry,
    runs_shape_problem,
)

_DIRECTORY = "inference"
_FILE = "manifest.json"


class JsonInferenceManifest:
    """Manifesto da inferência de um cohort em JSON, com escrita atômica."""

    # rótulo e comando das mensagens de recusa (o manifesto da atribuição os troca, 7.3)
    _label: ClassVar[str] = "inference manifest"
    _command: ClassVar[str] = "inference"

    def __init__(self, *, data_root: Path) -> None:
        self._data_root = Path(data_root)

    def path(self, cohort_id: str) -> Path:
        """Caminho do manifesto de `cohort_id` sob o `data_root`."""
        return self._data_root / _DIRECTORY / cohort_id / _FILE

    def recorded(self, cohort_id: str) -> Mapping[str, object] | None:
        path = self.path(cohort_id)
        if not path.exists():
            return None
        try:
            loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(
                f"{self._label} {path} is unreadable (empty or corrupted) — inspect it "
                f"before running {self._command} again"
            ) from exc
        if not isinstance(loaded, dict):
            raise ValueError(
                f"{self._label} {path} is unreadable (top-level {type(loaded).__name__}, "
                f"expected an object) — inspect it before running {self._command} again"
            )
        problem = runs_shape_problem(loaded)
        if problem is not None:
            raise ValueError(
                f"{self._label} {path} is unreadable ({problem}) — inspect it before "
                f"running {self._command} again"
            )
        return loaded

    def record_run(self, cohort_id: str, run_id: str, entry: Mapping[str, object]) -> None:
        document = apply_run_entry(
            self.recorded(cohort_id), cohort_id=cohort_id, run_id=run_id, entry=entry
        )
        path = self.path(cohort_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        try:
            temp.write_text(json.dumps(document, sort_keys=True, indent=2), encoding="utf-8")
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
