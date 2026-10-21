"""Adapter `JsonAttributionManifest` — satisfaz o port `AttributionManifest` do `inference` (7.3).

Arquivo `<data_root>/inference/<cohort_id>/attribution_manifest.json` (ADR 7.3.0002 item
2): ao lado do manifesto da inferência do mesmo cohort, sob o mesmo lock de escritor.
Leitura, recusa de manifesto ilegível, mescla (`apply_run_entry`) e escrita atômica
(temporário `<arquivo>.tmp-<pid>` + `os.replace`) são as do `JsonInferenceManifest`
(ADR 7.1.0004 item 4): este adapter só muda o nome do arquivo, para que as duas
proveniências nunca compartilhem um documento.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from financial_forecasting.features.inference.adapters.out.filesystem.json_inference_manifest import (  # noqa: E501
    JsonInferenceManifest,
)

_DIRECTORY = "inference"
_FILE = "attribution_manifest.json"


class JsonAttributionManifest(JsonInferenceManifest):
    """Manifesto da atribuição de um cohort em JSON, com escrita atômica."""

    _label: ClassVar[str] = "attribution manifest"
    _command: ClassVar[str] = "attribute"

    def path(self, cohort_id: str) -> Path:
        """Caminho do manifesto da atribuição de `cohort_id` sob o `data_root`."""
        return self._data_root / _DIRECTORY / cohort_id / _FILE
