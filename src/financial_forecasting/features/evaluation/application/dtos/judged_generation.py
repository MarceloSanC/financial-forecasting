"""DTOs da geração julgada e do registro de tentativas (Stage 8.1).

DTOs de aplicação **frozen** (concept 8.1 §4, D5, D12; ADRs `8_1_0003` itens 2, 3, 5b e
`8_1_0004` item 1) e o **dono único** do formato que o fake e o real do port
`JudgedGenerationStore` escrevem e conferem (gate `check_fake_parity.py`):

- os nomes do layout da cópia julgada (`GENERATION_DIR`, `CONTENTS_NAME`,
  `SCORECARD_DOCUMENT`, `RUN_RECORD_DOCUMENT`, `ATTEMPTS_NAME`);
- `document_bytes` — a serialização dos documentos JSON (`sort_keys`, `indent=2`, LF);
- `contents_listing` / `parse_contents_listing` / `verify_listing` — a listagem
  `sha256sum` de `CONTENTS.sha256`: linhas `<64 hex>  <caminho>\\n`, caminhos relativos a
  `judged/<ref>/` em POSIX, ordenados pelos bytes do caminho, UTF-8, LF; o
  `generation_digest` é o sha256 dos bytes dessa listagem (`generation_digest_of`);
- `JudgedGeneration` — a cópia selada lida (ou recém-selada);
- `AttemptPhase` / `JudgedAttempt` — uma linha de `ATTEMPTS.jsonl`: `started` (antes do
  E1, com código e ambiente) e `input_read` (logo depois do E1, com a entrada lida); as
  duas linhas de uma tentativa compartilham o `attempt_id` (= `started_at` ISO da
  `started`). `attempts_jsonl` / `parse_attempts_jsonl` são a serialização do arquivo;
- `result_layer_digest` — o digest da **camada de resultado** de uma geração (tabelas por
  valor e manifesto sem `started_at`/`finished_at`), gravado na linha `input_read`: é o
  que as re-execuções sem `--deviation` têm de reproduzir (I13; ADR 8.1.0004 item 2b,
  emenda do Checkpoint C 8.1 bloco 5).

`hashlib` sobre bytes de arquivo não é chamada do port `Hasher` (precedente ADR
7.1.0004): a integridade da cópia é sha256 dos bytes, verificável por `sha256sum -c`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    MANIFEST_NAME,
    GoldGeneration,
    GoldManifest,
    GoldPartition,
    RefreshStatus,
)
from financial_forecasting.features.evaluation.application.dtos.silver_content import (
    SilverContent,
)
from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    CODE_PREFIX,
    ENV_PREFIX,
)
from financial_forecasting.shared.domain.services.git_commit import validate_git_commit_sha
from financial_forecasting.shared.domain.services.path_identifier import (
    validate_path_identifier,
)
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

GENERATION_DIR: Final = "generation"
CONTENTS_NAME: Final = "CONTENTS.sha256"
SCORECARD_DOCUMENT: Final = "gold_model_comparison_confirmatory_scorecard.json"
RUN_RECORD_DOCUMENT: Final = "run_record.json"
ATTEMPTS_NAME: Final = "ATTEMPTS.jsonl"
DOCUMENT_NAMES: Final = frozenset({SCORECARD_DOCUMENT, RUN_RECORD_DOCUMENT})
GENERATION_MANIFEST: Final = f"{GENERATION_DIR}/{MANIFEST_NAME}"
"""O manifesto copiado de `current/`."""

_LISTING_LINE: Final = re.compile(r"([0-9a-f]{64})  ([^\r\n]+)")


def check_judged_ref(preregistration_ref: object) -> str:
    """A referência como nome de `judged/<ref>/`: identificador de caminho fora do layout.

    Além da regra única de identificador, recusa o que colide com o próprio `judged/`: nome
    começando com `.` (o staging, `.` e `..`) e o nome do log (Checkpoint C bloco 3, CC3-1).

    Raises:
        ValueError: identificador inválido ou que colide com o layout.
    """
    validate_path_identifier(preregistration_ref, field="preregistration_ref")
    assert isinstance(preregistration_ref, str)  # garantido pela regra acima
    if preregistration_ref.startswith(".") or preregistration_ref == ATTEMPTS_NAME:
        raise ValueError(
            f"preregistration_ref {preregistration_ref!r} collides with the judged/ layout"
        )
    return preregistration_ref


def check_identity(
    *, partition: GoldPartition, preregistration_ref: str, manifest: GoldManifest
) -> None:
    """O manifesto é da partição e da revisão de `judged/<ref>/` (CC3-2).

    Raises:
        ValueError: manifesto de outra partição ou de outra `preregistration_ref`.
    """
    if manifest.parameters.preregistration_ref != preregistration_ref:
        raise ValueError(
            f"the manifest is for {manifest.parameters.preregistration_ref!r}, "
            f"not {preregistration_ref!r}"
        )
    if manifest.partition != partition:
        raise ValueError(f"the manifest is for partition {manifest.partition}, not {partition}")


# --- listagem `sha256sum` ---------------------------------------------------------------


def check_relative_path(path: object) -> str:
    """Caminho relativo POSIX de um arquivo da cópia (sem `..`, `\\`, raiz nem quebra).

    Raises:
        ValueError: caminho fora dessa forma, ou o próprio `CONTENTS.sha256`.
    """
    if not isinstance(path, str) or not path:
        raise ValueError(f"listed path must be a non-empty str, got {path!r}")
    parts = path.split("/")
    if (
        "\\" in path
        or "\n" in path
        or "\r" in path
        or path.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"listed path must be a relative POSIX path, got {path!r}")
    if path == CONTENTS_NAME:
        raise ValueError(f"{CONTENTS_NAME} does not list itself")
    return path


def contents_listing(files: Mapping[str, str]) -> bytes:
    """Os bytes de `CONTENTS.sha256`: `<hex>  <caminho>\\n` ordenado pelos bytes do caminho.

    Raises:
        ValueError: caminho fora da forma (`check_relative_path`) ou digest não-hex.
    """
    for path, digest in files.items():
        check_relative_path(path)
        validate_sha256_hex(digest, field=f"sha256 of {path!r}")
    ordered = sorted(files, key=lambda path: path.encode("utf-8"))
    return "".join(f"{files[path]}  {path}\n" for path in ordered).encode("utf-8")


def parse_contents_listing(data: bytes) -> dict[str, str]:
    """Inversa de `contents_listing`: caminho → sha256.

    Raises:
        ValueError: não-UTF-8, CRLF, sem LF final, linha fora do formato, hex inválido,
            caminho repetido ou fora de ordem.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{CONTENTS_NAME} is not UTF-8: {error}") from error
    if "\r" in text:
        raise ValueError(f"{CONTENTS_NAME} must use LF line endings, found CR")
    if text and not text.endswith("\n"):
        raise ValueError(f"{CONTENTS_NAME} must end with a LF")
    files: dict[str, str] = {}
    previous: bytes | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = _LISTING_LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"{CONTENTS_NAME} line {number} is not '<sha256>  <path>'")
        digest, path = match.groups()
        check_relative_path(path)
        if path in files:
            raise ValueError(f"{CONTENTS_NAME} lists {path!r} twice")
        key = path.encode("utf-8")
        if previous is not None and key < previous:
            raise ValueError(f"{CONTENTS_NAME} is not sorted by path bytes at {path!r}")
        previous = key
        files[path] = digest
    return files


def generation_digest_of(listing: bytes) -> str:
    """O `generation_digest`: sha256 dos bytes de `CONTENTS.sha256` (ADR 8.1.0003 item 5b)."""
    return hashlib.sha256(listing).hexdigest()


def verify_listing(listing: bytes, actual: Mapping[str, str]) -> dict[str, str]:
    """Confere a listagem contra o sha256 recalculado de cada arquivo da cópia.

    `actual` é caminho → sha256 de todo arquivo encontrado (sem o `CONTENTS.sha256`).

    Raises:
        ValueError: listagem malformada, arquivo faltando, a mais ou com outro sha256, ou
            nenhum arquivo sob `generation/`.
    """
    listed = parse_contents_listing(listing)
    missing = sorted(set(listed) - set(actual))
    extra = sorted(set(actual) - set(listed))
    if missing or extra:
        raise ValueError(
            f"judged copy files differ from {CONTENTS_NAME}: missing {missing}, extra {extra}"
        )
    altered = sorted(path for path in listed if listed[path] != actual[path])
    if altered:
        raise ValueError(f"judged copy files {altered} differ from their sha256 in {CONTENTS_NAME}")
    if not any(path.startswith(f"{GENERATION_DIR}/") for path in listed):
        raise ValueError(f"judged copy has an empty {GENERATION_DIR}/")
    return listed


RESULT_EXCLUDED_KEYS: Final = frozenset({"started_at", "finished_at"})
"""As chaves do manifesto fora da camada de resultado: os instantes do `Clock`."""


def result_layer_digest(generation: GoldGeneration) -> str:
    """sha256 hex da camada de resultado da geração (ADR 8.1.0004 item 2b).

    Payload: o `manifest.as_mapping()` **sem** as chaves de `RESULT_EXCLUDED_KEYS` (as
    chaves somem; nenhum instante é trocado por outro) e cada tabela pelo nome, com as
    linhas na ordem da chave; JSON com `sort_keys`, separadores fixos e `allow_nan=False`.
    Dois refreshes das mesmas entradas no mesmo código e ambiente dão o mesmo digest
    (R-BIT); qualquer valor diferente numa tabela ou no manifesto o muda. Integridade de
    comparação entre tentativas, como o sha256 da cópia (ADR 7.1.0004): não é chamada do
    port `Hasher`.
    """
    manifest = {
        key: value
        for key, value in generation.manifest.as_mapping().items()
        if key not in RESULT_EXCLUDED_KEYS
    }
    tables = {
        name: [dict(row) for row in generation.tables[name].rows]
        for name in sorted(generation.tables)
    }
    payload = json.dumps(
        {"manifest": manifest, "tables": tables},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def document_bytes(document: Mapping[str, object]) -> bytes:
    """Os bytes de um documento JSON da cópia (`sort_keys`, `indent=2`, LF final)."""
    return (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")


def check_documents(documents: Mapping[str, Mapping[str, object]]) -> None:
    """`run_record.json` sempre; o scorecard opcional; nenhum outro nome.

    Raises:
        ValueError: nome fora de `DOCUMENT_NAMES`, `run_record.json` ausente ou documento
            que não é `Mapping`.
    """
    unknown = sorted(str(name) for name in documents if name not in DOCUMENT_NAMES)
    if unknown or RUN_RECORD_DOCUMENT not in documents:
        raise ValueError(
            f"documents must hold {RUN_RECORD_DOCUMENT} and only {sorted(DOCUMENT_NAMES)}, "
            f"got {sorted(str(name) for name in documents)}"
        )
    for name, document in documents.items():
        if not isinstance(document, Mapping):
            raise ValueError(f"document {name} must be a Mapping, got {type(document).__name__}")


def judged_generation_from(
    *,
    partition: GoldPartition,
    preregistration_ref: str,
    listing: bytes,
    actual: Mapping[str, str],
    read: Callable[[str], bytes],
) -> JudgedGeneration:
    """A cópia selada montada a partir da listagem conferida (fake e real).

    `actual` é caminho → sha256 recalculado de todo arquivo da cópia (sem o
    `CONTENTS.sha256`); `read(caminho)` devolve os bytes de um arquivo listado.

    Raises:
        ValueError: listagem que não confere (`verify_listing`), manifesto ou documento
            ilegível. O store traduz para `JudgedGenerationTamperedError`.
    """
    files = verify_listing(listing, actual)
    if GENERATION_MANIFEST not in files:
        raise ValueError(f"judged copy has no {GENERATION_MANIFEST}")
    manifest = GoldManifest.from_mapping(json.loads(read(GENERATION_MANIFEST).decode("utf-8")))
    documents = {
        name: json.loads(read(name).decode("utf-8")) for name in sorted(DOCUMENT_NAMES & set(files))
    }
    return JudgedGeneration(
        preregistration_ref=preregistration_ref,
        partition=partition,
        generation_digest=generation_digest_of(listing),
        refresh_status=manifest.status,
        files=files,
        manifest=manifest,
        documents=documents,
    )


# --- geração julgada --------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class JudgedGeneration:
    """Uma cópia selada: identidade, arquivos com sha256, manifesto e documentos lidos.

    Campos:
        preregistration_ref: a revisão julgada (nome de `judged/<ref>/`).
        partition: a partição do gold.
        generation_digest: sha256 hex dos bytes de `CONTENTS.sha256`.
        refresh_status: o status do manifesto copiado.
        files: caminho relativo → sha256 hex (sem o `CONTENTS.sha256`), não vazio.
        manifest: o `GoldManifest` da cópia.
        documents: nome do documento → JSON lido (`run_record.json` sempre; o scorecard
            só quando houve).

    Raises:
        ValueError: campo de tipo ou forma errada, na construção.
    """

    preregistration_ref: str
    partition: GoldPartition
    generation_digest: str
    refresh_status: RefreshStatus
    files: Mapping[str, str]
    manifest: GoldManifest
    documents: Mapping[str, Mapping[str, object]]

    def __post_init__(self) -> None:
        if not isinstance(self.preregistration_ref, str) or not self.preregistration_ref:
            raise ValueError(
                f"preregistration_ref must be a non-empty str, got {self.preregistration_ref!r}"
            )
        if not isinstance(self.partition, GoldPartition):
            raise ValueError(f"partition must be a GoldPartition, got {self.partition!r}")
        validate_sha256_hex(self.generation_digest, field="generation_digest")
        if not isinstance(self.refresh_status, RefreshStatus):
            raise ValueError(f"refresh_status must be a RefreshStatus, got {self.refresh_status!r}")
        if not isinstance(self.files, Mapping) or not self.files:
            raise ValueError("files must be a non-empty Mapping of path to sha256")
        for path, digest in self.files.items():
            check_relative_path(path)
            validate_sha256_hex(digest, field=f"sha256 of {path!r}")
        if not isinstance(self.manifest, GoldManifest):
            raise ValueError(f"manifest must be a GoldManifest, got {self.manifest!r}")
        check_identity(
            partition=self.partition,
            preregistration_ref=self.preregistration_ref,
            manifest=self.manifest,
        )
        check_documents(self.documents)
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))
        object.__setattr__(self, "documents", MappingProxyType(dict(self.documents)))


# --- tentativas -------------------------------------------------------------------------


class AttemptPhase(StrEnum):
    """A linha de uma tentativa no `ATTEMPTS.jsonl` (technical 8.1 §1)."""

    STARTED = "started"
    INPUT_READ = "input_read"


_STARTED_KEYS: Final = (
    "phase",
    "attempt_id",
    "preregistration_ref",
    "commit",
    "code",
    "environment",
    "started_at",
    "deviation",
    "prior_live_silver_content",
    "prior_live_result_digest",
)
_INPUT_READ_KEYS: Final = (
    "phase",
    "attempt_id",
    "preregistration_ref",
    "silver_content",
    "dataset_fingerprint",
    "result_digest",
)
_STARTED_ONLY: Final = (
    "commit",
    "code",
    "environment",
    "started_at",
    "deviation",
    "prior_live_silver_content",
    "prior_live_result_digest",
)
_INPUT_READ_ONLY: Final = ("silver_content", "dataset_fingerprint", "result_digest")


def _check_prefixed_map(value: object, *, prefix: str, field: str) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{field} must be a non-empty Mapping, got {value!r}")
    for key, item in value.items():
        if not isinstance(key, str) or not key.startswith(prefix):
            raise ValueError(f"{field} keys must start with {prefix!r}, got {key!r}")
        if not isinstance(item, str):
            raise ValueError(f"{field}[{key!r}] must be a str, got {item!r}")
    return MappingProxyType({key: value[key] for key in sorted(value)})


@dataclass(frozen=True, kw_only=True)
class JudgedAttempt:
    """Uma linha do `ATTEMPTS.jsonl` (ADR 8.1.0004 item 1).

    `started` carrega `commit` (40 hex), `code` (chaves `code.*`), `environment` (chaves
    `env.*`), `started_at` (com fuso; `attempt_id` = `started_at.isoformat()`),
    `deviation` (texto ou `None`), `prior_live_silver_content` e `prior_live_result_digest`
    (o `silver_content` e o `result_layer_digest` da geração viva desta revisão antes do
    E1 — a testemunha do que uma tentativa anterior sem `input_read` publicou, CC6-1 — ou
    `None`). `input_read` carrega `silver_content` e
    `dataset_fingerprint` (sha256 hex) do manifesto novo e `result_digest` (sha256 hex,
    `result_layer_digest` da geração publicada). Os campos da outra fase ficam `None`.

    Raises:
        ValueError: campo da fase ausente ou inválido, ou campo da outra fase presente.
    """

    phase: AttemptPhase
    attempt_id: str
    preregistration_ref: str
    commit: str | None = None
    code: Mapping[str, str] | None = None
    environment: Mapping[str, str] | None = None
    started_at: datetime | None = None
    deviation: str | None = None
    prior_live_silver_content: SilverContent | None = None
    prior_live_result_digest: str | None = None
    silver_content: SilverContent | None = None
    dataset_fingerprint: str | None = None
    result_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.phase, AttemptPhase):
            raise ValueError(f"phase must be an AttemptPhase, got {self.phase!r}")
        for name in ("attempt_id", "preregistration_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"attempt {name} must be a non-empty str, got {value!r}")
        others = _INPUT_READ_ONLY if self.phase is AttemptPhase.STARTED else _STARTED_ONLY
        present = [name for name in others if getattr(self, name) is not None]
        if present:
            raise ValueError(f"a {self.phase.value} attempt line cannot carry {present}")
        if self.phase is AttemptPhase.STARTED:
            self._check_started()
        else:
            self._check_input_read()

    def _check_started(self) -> None:
        validate_git_commit_sha(self.commit, field="attempt commit")
        object.__setattr__(
            self, "code", _check_prefixed_map(self.code, prefix=CODE_PREFIX, field="attempt code")
        )
        object.__setattr__(
            self,
            "environment",
            _check_prefixed_map(self.environment, prefix=ENV_PREFIX, field="attempt environment"),
        )
        started_at = self.started_at
        if not isinstance(started_at, datetime) or started_at.tzinfo is None:
            raise ValueError(f"attempt started_at must be timezone-aware, got {started_at!r}")
        if self.attempt_id != started_at.isoformat():
            raise ValueError(
                f"attempt_id must be started_at.isoformat() {started_at.isoformat()!r}, "
                f"got {self.attempt_id!r}"
            )
        if self.deviation is not None and (
            not isinstance(self.deviation, str) or not self.deviation
        ):
            raise ValueError(
                f"attempt deviation must be a non-empty str or None, got {self.deviation!r}"
            )
        prior = self.prior_live_silver_content
        if prior is not None and not isinstance(prior, SilverContent):
            raise ValueError(f"prior_live_silver_content must be a SilverContent, got {prior!r}")
        if (prior is None) != (self.prior_live_result_digest is None):
            raise ValueError(
                "prior_live_silver_content and prior_live_result_digest come together or not at all"
            )
        if self.prior_live_result_digest is not None:
            validate_sha256_hex(self.prior_live_result_digest, field="prior_live_result_digest")

    def _check_input_read(self) -> None:
        if not isinstance(self.silver_content, SilverContent):
            raise ValueError(
                f"an input_read attempt line needs a SilverContent, got {self.silver_content!r}"
            )
        validate_sha256_hex(self.dataset_fingerprint, field="attempt dataset_fingerprint")
        validate_sha256_hex(self.result_digest, field="attempt result_digest")

    def as_mapping(self) -> dict[str, object]:
        """A linha JSON-safe (só as chaves da fase)."""
        if self.phase is AttemptPhase.STARTED:
            assert self.started_at is not None  # garantido pelo __post_init__
            prior = self.prior_live_silver_content
            return {
                "phase": self.phase.value,
                "attempt_id": self.attempt_id,
                "preregistration_ref": self.preregistration_ref,
                "commit": self.commit,
                "code": dict(self.code or {}),
                "environment": dict(self.environment or {}),
                "started_at": self.started_at.isoformat(),
                "deviation": self.deviation,
                "prior_live_silver_content": None if prior is None else prior.as_mapping(),
                "prior_live_result_digest": self.prior_live_result_digest,
            }
        assert self.silver_content is not None  # garantido pelo __post_init__
        return {
            "phase": self.phase.value,
            "attempt_id": self.attempt_id,
            "preregistration_ref": self.preregistration_ref,
            "silver_content": self.silver_content.as_mapping(),
            "dataset_fingerprint": self.dataset_fingerprint,
            "result_digest": self.result_digest,
        }

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> JudgedAttempt:
        """Inversa de `as_mapping` (chaves exatas da fase).

        Raises:
            ValueError: não-`Mapping`, fase desconhecida, chave a mais ou a menos, ou
                campo inválido.
        """
        if not isinstance(mapping, Mapping):
            raise ValueError(f"attempt line must be a Mapping, got {type(mapping).__name__}")
        phase = AttemptPhase(str(mapping.get("phase")))
        expected = _STARTED_KEYS if phase is AttemptPhase.STARTED else _INPUT_READ_KEYS
        if set(mapping) != set(expected):
            raise ValueError(
                f"a {phase.value} attempt line must have exactly the keys {sorted(expected)}, "
                f"got {sorted(str(key) for key in mapping)}"
            )
        common = {
            "phase": phase,
            "attempt_id": mapping["attempt_id"],
            "preregistration_ref": mapping["preregistration_ref"],
        }
        if phase is AttemptPhase.INPUT_READ:
            return cls(
                **common,  # type: ignore[arg-type]
                silver_content=SilverContent.from_mapping(mapping["silver_content"]),  # type: ignore[arg-type]
                dataset_fingerprint=mapping["dataset_fingerprint"],  # type: ignore[arg-type]
                result_digest=mapping["result_digest"],  # type: ignore[arg-type]
            )
        started_at = mapping["started_at"]
        if not isinstance(started_at, str):
            raise ValueError(f"attempt started_at must be an ISO-8601 str, got {started_at!r}")
        prior = mapping["prior_live_silver_content"]
        return cls(
            **common,  # type: ignore[arg-type]
            commit=mapping["commit"],  # type: ignore[arg-type]
            code=mapping["code"],  # type: ignore[arg-type]
            environment=mapping["environment"],  # type: ignore[arg-type]
            started_at=datetime.fromisoformat(started_at),
            deviation=mapping["deviation"],  # type: ignore[arg-type]
            prior_live_silver_content=(
                None if prior is None else SilverContent.from_mapping(prior)  # type: ignore[arg-type]
            ),
            prior_live_result_digest=mapping["prior_live_result_digest"],  # type: ignore[arg-type]
        )


def attempts_jsonl(attempts: Iterable[JudgedAttempt]) -> bytes:
    """Os bytes de `ATTEMPTS.jsonl`: uma linha JSON (`sort_keys`, compacta) por entrada."""
    return "".join(
        json.dumps(attempt.as_mapping(), sort_keys=True, separators=(",", ":")) + "\n"
        for attempt in attempts
    ).encode("utf-8")


def parse_attempts_jsonl(data: bytes) -> tuple[JudgedAttempt, ...]:
    """Inversa de `attempts_jsonl`, na ordem do arquivo.

    Raises:
        ValueError: não-UTF-8, linha que não é JSON ou entrada inválida.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{ATTEMPTS_NAME} is not UTF-8: {error}") from error
    attempts: list[JudgedAttempt] = []
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            mapping = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{ATTEMPTS_NAME} line {number} is not JSON: {error}") from error
        attempts.append(JudgedAttempt.from_mapping(mapping))
    return tuple(attempts)
