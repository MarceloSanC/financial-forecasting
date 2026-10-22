"""Fake do port `EvaluationEnvironment` — foto fixa, limpa por padrão (Stage 8.1).

`InMemoryEvaluationEnvironment(changes=...)` devolve a foto `CLEAN_SNAPSHOT` com as
chaves de `changes` sobrescritas (ou removidas, com valor `None`); `image_id=None`
reproduz a recusa do real (`MissingImageIdError`). `snapshots` conta as chamadas (testes
de ordem do use case: a foto é tirada antes de qualquer efeito).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    CODE_DIRTY_KEY,
    COMMIT_KEY,
    CPU_CAPABILITY_KEY,
    CPU_COUNT_KEY,
    FALSE,
    GOLD_LIBRARIES,
    IMAGE_ID_KEY,
    PLATFORM_KEY,
    PREREGISTRATION_DIRTY_KEY,
    MissingImageIdError,
    library_key,
    probe_key,
)

CLEAN_SNAPSHOT: Mapping[str, str] = MappingProxyType(
    {
        COMMIT_KEY: "0123456789abcdef0123456789abcdef01234567",
        CODE_DIRTY_KEY: FALSE,
        PREREGISTRATION_DIRTY_KEY: FALSE,
        "code.src": "a" * 40,
        "code.uv_lock": "b" * 40,
        "code.cohort_file": "c" * 40,
        IMAGE_ID_KEY: "sha256:" + "d" * 64,
        PLATFORM_KEY: "Linux-6.6-x86_64-with-glibc2.36",
        CPU_COUNT_KEY: "12",
        CPU_CAPABILITY_KEY: "AVX2",
        **{library_key(name): "1.0.0" for name in GOLD_LIBRARIES},
        probe_key("python"): "3.12.7",
        probe_key("torch"): "2.4.1",
        probe_key("cpu"): "x86_64",
    }
)
_DEFAULT_IMAGE = CLEAN_SNAPSHOT[IMAGE_ID_KEY]


class InMemoryEvaluationEnvironment:
    """Satisfaz `EvaluationEnvironment` com uma foto fixa."""

    def __init__(
        self,
        changes: Mapping[str, str | None] | None = None,
        *,
        image_id: str | None = _DEFAULT_IMAGE,
    ) -> None:
        photo = dict(CLEAN_SNAPSHOT)
        for key, value in (changes or {}).items():
            if value is None:
                photo.pop(key, None)
            else:
                photo[key] = value
        self._photo = photo
        self._image_id = image_id
        self.snapshots = 0

    def snapshot(self) -> Mapping[str, str]:
        self.snapshots += 1
        if not self._image_id:
            raise MissingImageIdError("the Docker image id is required (IMAGE_ID)")
        return MappingProxyType({**self._photo, IMAGE_ID_KEY: self._image_id})
