"""DTOs do dado plotado, do registro por figura e do dossiê de rastreabilidade (Stage 8.3).

DTOs de aplicação **frozen** (concept 8.3 §4; ADRs `8_3_0002` e `8_3_0004`; technical 8.3
§1 "Decisões de forma"). Validam na construção (`ValueError`) e expõem `as_mapping()`
JSON-safe:

- `FigureSpec` (+ `PanelSpec`, `SeriesSpec`, `ElementLabel`) — o **dado plotado**, sem tipo
  de biblioteca. `FigureSpec.canonical_bytes()` é o dono único da serialização que o
  `data_digest` (sha256) identifica: qualquer bit de qualquer valor muda o digest. O
  `Hasher` do projeto não é usado aqui porque arredonda floats (contrato do port);
- `FIGURE_CATALOG` — as dez figuras do doc §6.2, na ordem do catálogo, com as omissões
  declaradas (coluna "Omissões declaradas" do D13, **lista fechada**) e as frases
  obrigatórias do I11. Uma `FigureSpec` com omissão fora da lista ou sem frase obrigatória
  não constrói (A16);
- `FigureRecord` (+ `SourceRef`) — o registro `<id>.json` de cada figura (A11; I7): o
  digest do dado, a geração julgada, as fontes e o código, sem commit, instante ou caminho
  absoluto (I8);
- `DossierEntry` — uma entrada do registro curado `docs/reports/dossier_register.toml`,
  com a **primeira barreira do A17** na construção (visibilidade decidida pela fonte);
- `TraceabilityDossier` (+ `DossierSection`, `DossierBlock`) — o dossiê citável (seções
  `CITABLE_SECTIONS`, fechadas) e o interno;
- `CITABLE_FORBIDDEN_PATTERNS` e `find_forbidden` — a **segunda barreira do A17**, sobre o
  texto do citável;
- `check_artifacts` — a validação da escrita (dono único do fake e do sink real, CB-4);
- `GenerateReportArtifactsCommand`, `ReportArtifactsResult` e os erros do use case.

Só stdlib (`hashlib`, `json`, `re`).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldPartition,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._integer import (
    validate_int_at_least,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.services.sha256_hex import validate_sha256_hex

# --------------------------------------------------------------------------------------
# Erros do use case
# --------------------------------------------------------------------------------------


class ReportArtifactsError(ApplicationError):
    """Registro commitado da ref ausente, scorecard ausente na cópia ou nenhuma `input_read`."""


class ReportSourceMismatchError(ApplicationError):
    """Fonte persistida incoerente com outra (DM gold ≠ scorecard, seeds, linha ausente…).

    A mensagem leva chaves (tabela, modelo, horizonte), nunca valores.
    """


class SilverContentMismatchError(ApplicationError):
    """Unidade do silver/realizado diferente, faltando ou a mais (concept 8.3 §4, I2).

    A mensagem leva só as chaves de unidade, ordenadas — nunca digests nem valores.
    """

    def __init__(self, keys: Sequence[str]) -> None:
        self.keys: tuple[str, ...] = tuple(sorted(str(key) for key in keys))
        super().__init__(f"silver content differs from the judged copy at units {list(self.keys)}")


# --------------------------------------------------------------------------------------
# Serialização canônica
# --------------------------------------------------------------------------------------


def canonical_json_bytes(document: Mapping[str, object]) -> bytes:
    """Bytes canônicos de um documento JSON: chaves ordenadas, sem espaço, sem NaN.

    Floats saem pelo `repr` do `json` (exato e determinístico); a ordem de inserção dos
    mapas não importa.
    """
    return json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _non_empty_str(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty str, got {value!r}")
    return value


def _optional_note(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _non_empty_str(value, field=field)


def _str_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field} must be a tuple, got {type(value).__name__}")
    for item in value:
        _non_empty_str(item, field=f"{field} item")
    return value


# --------------------------------------------------------------------------------------
# O dado plotado
# --------------------------------------------------------------------------------------


class StatusLabel(StrEnum):
    """Rótulo de estatuto por elemento (doc §2.3; convenção P8-ROT, em PT).

    Não existe `exploratório`: nenhum gráfico exploratório nesta Stage (I3).
    """

    CONFIRMATORY = "confirmatório"
    DESCRIPTIVE_PROFILE = "descritivo (perfil)"
    DESCRIPTIVE = "descritivo"
    DESCRIPTIVE_PROFILE_H2_NOT_APPLICABLE = "descritivo (perfil) — H2 não aplicável"


class PanelScope(StrEnum):
    """O eixo de um painel: um horizonte, nenhum (VSN) ou a comparação entre horizontes (H3)."""

    HORIZON = "horizon"
    HORIZON_INVARIANT = "horizon_invariant"
    HORIZON_COMPARISON = "horizon_comparison"


class SeriesKind(StrEnum):
    """A marca de uma série — o renderer desenha por tipo, nunca recalcula."""

    LINE = "line"
    POINTS = "points"
    BAND = "band"
    INTERVAL = "interval"
    BOXES = "boxes"
    CELLS = "cells"
    STEMS = "stems"
    BARS = "bars"
    VLINES = "vlines"
    REFERENCE = "reference"


@dataclass(frozen=True, kw_only=True)
class ElementLabel:
    """Rótulo de um painel ou série: o estatuto e uma nota opcional.

    Raises:
        ValueError: `status` fora de `StatusLabel` ou `note` vazia.
    """

    status: StatusLabel
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, StatusLabel):
            raise ValueError(f"status must be a StatusLabel, got {self.status!r}")
        _optional_note(self.note, field="ElementLabel.note")

    def as_mapping(self) -> dict[str, object]:
        return {"status": self.status.value, "note": self.note}


_NUMERIC_SERIES_FIELDS: Final = ("y", "low", "high", "whisker_low", "whisker_high")


def _check_numbers(values: object, *, field: str, length: int) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{field} must be a tuple, got {type(values).__name__}")
    if len(values) != length:
        raise ValueError(f"{field} must have the length of x ({length}), got {len(values)}")
    for value in values:
        if value is not None and not is_finite_number(value):
            raise ValueError(f"{field} values must be finite numbers or None, got {value!r}")


@dataclass(frozen=True, kw_only=True)
class SeriesSpec:
    """Uma série de um painel: a marca, os valores e o rótulo (obrigatório).

    `x` são posições numéricas finitas ou categorias (`str`); `y`, `low`, `high`,
    `whisker_low` e `whisker_high` são números finitos ou `None`, com o comprimento de `x`.
    `low`/`high` carregam faixas, intervalos e os quartis das caixas; `whisker_low`/
    `whisker_high` só existem (e são obrigatórios) nas caixas (`boxes`: mínimo e máximo).
    `text` é a anotação por célula/ponto.

    Raises:
        ValueError: id/nome vazios, `kind` fora de `SeriesKind`, rótulo ausente, valor não
            finito, comprimento diferente de `x` ou campos de caixa fora de `boxes`.
    """

    series_id: str
    kind: SeriesKind
    name: str
    label: ElementLabel
    x: tuple[float | str, ...]
    y: tuple[float | None, ...]
    model: str | None = None
    low: tuple[float | None, ...] | None = None
    high: tuple[float | None, ...] | None = None
    whisker_low: tuple[float | None, ...] | None = None
    whisker_high: tuple[float | None, ...] | None = None
    text: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _non_empty_str(self.series_id, field="series_id")
        _non_empty_str(self.name, field="SeriesSpec.name")
        _optional_note(self.model, field="SeriesSpec.model")
        if not isinstance(self.kind, SeriesKind):
            raise ValueError(f"kind must be a SeriesKind, got {self.kind!r}")
        if not isinstance(self.label, ElementLabel):
            raise ValueError(f"series {self.series_id!r} must carry an ElementLabel")
        if not isinstance(self.x, tuple) or not self.x:
            raise ValueError(f"series {self.series_id!r} x must be a non-empty tuple")
        for value in self.x:
            if isinstance(value, str):
                _non_empty_str(value, field="x category")
            elif not is_finite_number(value):
                raise ValueError(f"x values must be finite numbers or str, got {value!r}")
        length = len(self.x)
        _check_numbers(self.y, field="y", length=length)
        for name in _NUMERIC_SERIES_FIELDS[1:]:
            values = getattr(self, name)
            if values is not None:
                _check_numbers(values, field=name, length=length)
        self._check_box_fields()
        if self.text is not None:
            _str_tuple(self.text, field="text")
            if len(self.text) != length:
                raise ValueError(f"text must have the length of x ({length})")

    def _check_box_fields(self) -> None:
        whiskers = (self.whisker_low, self.whisker_high)
        if self.kind is SeriesKind.BOXES:
            if any(values is None for values in (self.low, self.high, *whiskers)):
                raise ValueError("boxes need low, high, whisker_low and whisker_high")
        elif any(values is not None for values in whiskers):
            raise ValueError("whisker_low/whisker_high exist only in boxes")

    def as_mapping(self) -> dict[str, object]:
        return {
            "series_id": self.series_id,
            "kind": self.kind.value,
            "name": self.name,
            "model": self.model,
            "label": self.label.as_mapping(),
            "x": list(self.x),
            "y": list(self.y),
            "low": None if self.low is None else list(self.low),
            "high": None if self.high is None else list(self.high),
            "whisker_low": None if self.whisker_low is None else list(self.whisker_low),
            "whisker_high": None if self.whisker_high is None else list(self.whisker_high),
            "text": None if self.text is None else list(self.text),
        }


@dataclass(frozen=True, kw_only=True)
class PanelSpec:
    """Um painel: o eixo (horizonte, invariante ou comparação), os rótulos e as séries.

    Raises:
        ValueError: `horizon` ausente num painel `horizon` ou presente fora dele, série
            vazia ou id de série repetido, rótulo ausente.
    """

    panel_id: str
    scope: PanelScope
    horizon: int | None
    title: str
    x_label: str
    y_label: str
    series: tuple[SeriesSpec, ...]
    label: ElementLabel

    def __post_init__(self) -> None:
        _non_empty_str(self.panel_id, field="panel_id")
        for name in ("title", "x_label", "y_label"):
            _non_empty_str(getattr(self, name), field=f"PanelSpec.{name}")
        if not isinstance(self.scope, PanelScope):
            raise ValueError(f"scope must be a PanelScope, got {self.scope!r}")
        if self.scope is PanelScope.HORIZON:
            validate_int_at_least(self.horizon, minimum=1, field="PanelSpec.horizon")
        elif self.horizon is not None:
            raise ValueError(f"a {self.scope.value} panel has no horizon, got {self.horizon!r}")
        if not isinstance(self.label, ElementLabel):
            raise ValueError(f"panel {self.panel_id!r} must carry an ElementLabel")
        if not isinstance(self.series, tuple) or not self.series:
            raise ValueError(f"panel {self.panel_id!r} needs at least one series")
        if not all(isinstance(series, SeriesSpec) for series in self.series):
            raise ValueError("series must be SeriesSpec")
        ids = [series.series_id for series in self.series]
        if len(set(ids)) != len(ids):
            raise ValueError(f"panel {self.panel_id!r} repeats a series_id: {ids}")

    def as_mapping(self) -> dict[str, object]:
        return {
            "panel_id": self.panel_id,
            "scope": self.scope.value,
            "horizon": self.horizon,
            "title": self.title,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "label": self.label.as_mapping(),
            "series": [series.as_mapping() for series in self.series],
        }


# --------------------------------------------------------------------------------------
# O catálogo fechado (doc §6.2; D13; I11)
# --------------------------------------------------------------------------------------

SEED_PLACEHOLDER: Final = "{seed}"
EMPIRICAL_COVERAGE_NOTE: Final = "cobertura empírica (não garantida)"
FAN_CHART_SEED_NOTE: Final = "seed {seed}, ilustrativa; as métricas usam a média entre seeds"


def fan_chart_seed_note(seed: int) -> str:
    """A legenda do I6 com a seed resolvida."""
    validate_int_at_least(seed, minimum=0, field="seed")
    return FAN_CHART_SEED_NOTE.replace(SEED_PLACEHOLDER, str(seed))


@dataclass(frozen=True, kw_only=True)
class FigureCatalogEntry:
    """Uma linha do catálogo: omissões declaradas, frases obrigatórias e nota de painel.

    `required_notes` pode conter `{seed}` (a legenda do fan chart), que casa um inteiro.
    `panel_note`, quando presente, é a nota exigida no rótulo de **todo** painel.

    Raises:
        ValueError: texto vazio ou não-`tuple`.
    """

    title: str
    omissions: tuple[str, ...]
    required_notes: tuple[str, ...]
    panel_note: str | None = None

    def __post_init__(self) -> None:
        _non_empty_str(self.title, field="FigureCatalogEntry.title")
        _str_tuple(self.omissions, field="omissions")
        _str_tuple(self.required_notes, field="required_notes")
        _optional_note(self.panel_note, field="panel_note")

    def missing_notes(self, notes: tuple[str, ...]) -> tuple[str, ...]:
        """As frases obrigatórias ausentes de `notes` (`{seed}` casa um inteiro)."""
        missing: list[str] = []
        for required in self.required_notes:
            if SEED_PLACEHOLDER in required:
                before, after = required.split(SEED_PLACEHOLDER, 1)
                pattern = re.compile(rf"{re.escape(before)}\d+{re.escape(after)}")
                if not any(pattern.fullmatch(note) for note in notes):
                    missing.append(required)
            elif required not in notes:
                missing.append(required)
        return tuple(missing)


FIGURE_CATALOG: Final[Mapping[str, FigureCatalogEntry]] = MappingProxyType(
    {
        "reliability_diagram": FigureCatalogEntry(
            title="Reliability diagram por τ",
            omissions=(
                "τ = 0,5 (sem linha de calibração)",
                "banda de Wilson do candidato nos níveis fora do gate e da média entre seeds "
                "(o gold só a tem por seed; a dispersão por seed é desenhada no lugar)",
            ),
            required_notes=("banda binomial anti-conservadora em h+7 e sob agrupamento",),
        ),
        "quantile_score_plot": FigureCatalogEntry(
            title="Quantile score plot", omissions=(), required_notes=()
        ),
        "sharpness_diagram": FigureCatalogEntry(
            title="Sharpness diagram",
            omissions=(),
            required_notes=("sharpness só tem sentido sujeito à calibração",),
        ),
        "picp_mpiw_plot": FigureCatalogEntry(
            title="PICP × MPIW",  # noqa: RUF001
            omissions=(),
            required_notes=(
                "o gráfico não ordena modelos — mais estreito só é melhor com cobertura igual",
            ),
        ),
        "dm_candidate_vs_comparators": FigureCatalogEntry(
            title="DM: candidato × comparadores",  # noqa: RUF001
            omissions=(),
            required_notes=(),
        ),
        "oos_fan_chart": FigureCatalogEntry(
            title="Série OOS / fan chart", omissions=(), required_notes=(FAN_CHART_SEED_NOTE,)
        ),
        "loss_differential_acf": FigureCatalogEntry(
            title="Diferencial de perda d_t e ACF",
            omissions=("faixa de confiança da ACF (±1,96/√n não persistida)",),
            required_notes=(),
        ),
        "h3_family_importance": FigureCatalogEntry(
            title="Importância por família / H3",
            omissions=("intervalo bootstrap de I_f(h) e de s_f(h) (o gold só tem o de Δ_f)",),
            required_notes=(
                "linguagem estritamente descritiva: a família f responde por uma parcela "
                'maior da perda evitada em h+7 do que em h+1; nunca "f causa"',
            ),
        ),
        "vsn_weights": FigureCatalogEntry(
            title="Pesos da VSN", omissions=(), required_notes=("horizonte-invariante",)
        ),
        "native_vs_conformal": FigureCatalogEntry(
            title="Nativo × conformal",  # noqa: RUF001
            omissions=(
                "referência de dispersão Beta agregada (o gold só tem beta_mean/beta_sd por "
                "fold × seed × cauda; agregar ou tirar quantis seria cálculo novo)",  # noqa: RUF001
                "banda de Wilson do nativo na média entre seeds (só por seed no gold; os "
                "pontos por seed ficam como dispersão)",
            ),
            required_notes=(EMPIRICAL_COVERAGE_NOTE,),
            panel_note=EMPIRICAL_COVERAGE_NOTE,
        ),
    }
)
FIGURE_IDS: Final[tuple[str, ...]] = tuple(FIGURE_CATALOG)


@dataclass(frozen=True, kw_only=True)
class FigureSpec:
    """O dado plotado de uma figura do catálogo (concept 8.3 §4).

    Raises:
        ValueError: id fora do catálogo, título vazio, painel ausente ou repetido,
            omissões diferentes das do catálogo (A16), frase obrigatória ausente (I11) ou
            painel sem a nota exigida pelo catálogo.
    """

    figure_id: str
    title: str
    panels: tuple[PanelSpec, ...]
    notes: tuple[str, ...]
    omissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.figure_id not in FIGURE_CATALOG:
            raise ValueError(f"figure_id {self.figure_id!r} is not in FIGURE_CATALOG")
        entry = FIGURE_CATALOG[self.figure_id]
        _non_empty_str(self.title, field="FigureSpec.title")
        if not isinstance(self.panels, tuple) or not self.panels:
            raise ValueError(f"figure {self.figure_id!r} needs at least one panel")
        if not all(isinstance(panel, PanelSpec) for panel in self.panels):
            raise ValueError("panels must be PanelSpec")
        ids = [panel.panel_id for panel in self.panels]
        if len(set(ids)) != len(ids):
            raise ValueError(f"figure {self.figure_id!r} repeats a panel_id: {ids}")
        _str_tuple(self.notes, field="notes")
        _str_tuple(self.omissions, field="omissions")
        if self.omissions != entry.omissions:
            raise ValueError(
                f"figure {self.figure_id!r} omissions must be exactly the catalog's "
                f"{list(entry.omissions)}, got {list(self.omissions)}"
            )
        missing = entry.missing_notes(self.notes)
        if missing:
            raise ValueError(f"figure {self.figure_id!r} lacks required notes {list(missing)}")
        if entry.panel_note is not None:
            unlabelled = [p.panel_id for p in self.panels if p.label.note != entry.panel_note]
            if unlabelled:
                raise ValueError(
                    f"figure {self.figure_id!r} panels {unlabelled} lack {entry.panel_note!r}"
                )

    def as_mapping(self) -> dict[str, object]:
        return {
            "figure_id": self.figure_id,
            "title": self.title,
            "panels": [panel.as_mapping() for panel in self.panels],
            "notes": list(self.notes),
            "omissions": list(self.omissions),
        }

    def canonical_bytes(self) -> bytes:
        """A serialização canônica do dado plotado (dono único do `data_digest`)."""
        return canonical_json_bytes(self.as_mapping())

    @property
    def data_digest(self) -> str:
        """sha256 hex de `canonical_bytes()` (A11)."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


# --------------------------------------------------------------------------------------
# O registro por figura (A11; I7; I8)
# --------------------------------------------------------------------------------------


class SourceKind(StrEnum):
    """De onde uma série sai: tabela gold, documento da cópia, silver ou realizado."""

    GOLD_TABLE = "gold_table"
    DOCUMENT = "document"
    SILVER_TABLE = "silver_table"
    REALIZED = "realized"


_FORBIDDEN_KEY_PARTS: Final = ("commit", "time")
_ABSOLUTE_PATH = re.compile(r"^(?:/|[A-Za-z]:[\\/]|\\\\)")


def _check_key(key: object, *, field: str) -> None:
    """Chave estrutural de registro: sem commit, instante (`time`, `*_at`) — I8."""
    text = _non_empty_str(key, field=f"{field} key")
    lowered = text.lower()
    if any(part in lowered for part in _FORBIDDEN_KEY_PARTS) or lowered == "at":
        raise ValueError(f"{field} key {text!r} names a commit or an instant (I8)")
    if lowered.endswith("_at") or lowered.endswith(".at"):
        raise ValueError(f"{field} key {text!r} names an instant (I8)")


def _check_value(value: object, *, field: str) -> None:
    """Valor de registro: texto nunca é caminho absoluto (I8)."""
    if isinstance(value, str) and _ABSOLUTE_PATH.match(value):
        raise ValueError(f"{field} holds an absolute path {value!r} (I8)")


def _frozen_str_map(value: object, *, field: str, structural: bool) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a Mapping, got {type(value).__name__}")
    out: dict[str, str] = {}
    for key, item in sorted(value.items()):
        if structural:
            _check_key(key, field=field)
        else:
            _non_empty_str(key, field=f"{field} key")
        _non_empty_str(item, field=f"{field}[{key!r}]")
        _check_value(item, field=f"{field}[{key!r}]")
        out[key] = item
    return MappingProxyType(out)


FilterValue = str | int | float | bool | None


@dataclass(frozen=True, kw_only=True)
class SourceRef:
    """Uma fonte lida por uma figura: tipo, nome, filtro (coluna → valor) e campos lidos.

    Raises:
        ValueError: `kind` fora de `SourceKind`, nome vazio, filtro com chave proibida
            (commit/instante), valor não escalar/não finito ou caminho absoluto, campos
            vazios ou repetidos.
    """

    kind: SourceKind
    name: str
    filter: Mapping[str, FilterValue]
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SourceKind):
            raise ValueError(f"kind must be a SourceKind, got {self.kind!r}")
        _non_empty_str(self.name, field="SourceRef.name")
        if not isinstance(self.filter, Mapping):
            raise ValueError("SourceRef.filter must be a Mapping")
        frozen: dict[str, FilterValue] = {}
        for key, value in sorted(self.filter.items()):
            _check_key(key, field="SourceRef.filter")
            if isinstance(value, float) and not is_finite_number(value):
                raise ValueError(f"filter value of {key!r} must be finite, got {value!r}")
            if value is not None and not isinstance(value, str | int | float):
                raise ValueError(f"filter value of {key!r} must be a scalar, got {value!r}")
            _check_value(value, field=f"SourceRef.filter[{key!r}]")
            frozen[key] = value
        object.__setattr__(self, "filter", MappingProxyType(frozen))
        _str_tuple(self.fields, field="SourceRef.fields")
        if not self.fields or len(set(self.fields)) != len(self.fields):
            raise ValueError(f"SourceRef.fields must be non-empty and unique, got {self.fields}")

    def as_mapping(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "name": self.name,
            "filter": dict(self.filter),
            "fields": list(self.fields),
        }


CODE_RECORD_KEYS: Final = frozenset({"code.src", "code.uv_lock"})


@dataclass(frozen=True, kw_only=True)
class FigureRecord:
    """O registro `<id>.json` de uma figura (A11): a prova de origem é o dado (I7).

    Sem commit HEAD, instante, host, caminho absoluto e sem sha256 do PDF (I8).

    Raises:
        ValueError: id fora do catálogo, digest inválido, revisão negativa, fonte ausente,
            unidade do silver com digest inválido, contagem de degenerados negativa,
            omissões diferentes das do catálogo, `code` sem exatamente `code.src` e
            `code.uv_lock`, chave de commit/instante ou caminho absoluto.
    """

    figure_id: str
    data_digest: str
    generation_digest: str
    preregistration_ref: str
    revision: int
    partition: GoldPartition
    sources: tuple[SourceRef, ...]
    silver_units: Mapping[str, str]
    excluded_degenerate: Mapping[str, int]
    omissions: tuple[str, ...]
    code: Mapping[str, str]
    renderer: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.figure_id not in FIGURE_CATALOG:
            raise ValueError(f"figure_id {self.figure_id!r} is not in FIGURE_CATALOG")
        validate_sha256_hex(self.data_digest, field="data_digest")
        validate_sha256_hex(self.generation_digest, field="generation_digest")
        _non_empty_str(self.preregistration_ref, field="preregistration_ref")
        _check_value(self.preregistration_ref, field="preregistration_ref")
        validate_int_at_least(self.revision, minimum=0, field="revision")
        if not isinstance(self.partition, GoldPartition):
            raise ValueError("partition must be a GoldPartition")
        if not isinstance(self.sources, tuple) or not self.sources:
            raise ValueError("sources must be a non-empty tuple")
        if not all(isinstance(source, SourceRef) for source in self.sources):
            raise ValueError("sources must be SourceRef")
        units = _frozen_str_map(self.silver_units, field="silver_units", structural=False)
        for key, digest in units.items():
            validate_sha256_hex(digest, field=f"silver_units[{key!r}]")
        object.__setattr__(self, "silver_units", units)
        if not isinstance(self.excluded_degenerate, Mapping):
            raise ValueError("excluded_degenerate must be a Mapping")
        counts: dict[str, int] = {}
        for key, count in sorted(self.excluded_degenerate.items()):
            _non_empty_str(key, field="excluded_degenerate key")
            validate_int_at_least(count, minimum=0, field=f"excluded_degenerate[{key!r}]")
            counts[key] = count
        object.__setattr__(self, "excluded_degenerate", MappingProxyType(counts))
        _str_tuple(self.omissions, field="omissions")
        if self.omissions != FIGURE_CATALOG[self.figure_id].omissions:
            raise ValueError(f"record {self.figure_id!r} omissions differ from the catalog")
        code = _frozen_str_map(self.code, field="code", structural=True)
        if set(code) != CODE_RECORD_KEYS:
            raise ValueError(
                f"code must hold exactly {sorted(CODE_RECORD_KEYS)}, got {sorted(code)}"
            )
        object.__setattr__(self, "code", code)
        renderer = _frozen_str_map(self.renderer, field="renderer", structural=True)
        if not renderer:
            raise ValueError("renderer identity must not be empty")
        object.__setattr__(self, "renderer", renderer)

    def as_mapping(self) -> dict[str, object]:
        return {
            "figure_id": self.figure_id,
            "data_digest": self.data_digest,
            "generation_digest": self.generation_digest,
            "preregistration_ref": self.preregistration_ref,
            "revision": self.revision,
            "partition": {
                "asset": self.partition.asset,
                "parent_sweep_id": self.partition.parent_sweep_id,
            },
            "sources": [source.as_mapping() for source in self.sources],
            "silver_units": dict(self.silver_units),
            "excluded_degenerate": dict(self.excluded_degenerate),
            "omissions": list(self.omissions),
            "code": dict(self.code),
            "renderer": dict(self.renderer),
        }


# --------------------------------------------------------------------------------------
# O registro curado e a primeira barreira do A17
# --------------------------------------------------------------------------------------


class DossierEntryKind(StrEnum):
    """Os kinds do `dossier_register.toml` (concept 8.3 §4). `internal` vai só ao interno."""

    DEVIATION = "deviation"
    FINDING = "finding"
    PRE_ANCHOR = "pre_anchor"
    ENVIRONMENT = "environment"
    REPRODUCTION = "reproduction"
    INTERNAL = "internal"


OPEN_STATUS: Final = "open"

_TECHNICAL_82: Final = "docs/stages/8.2-equivalence-audit/technical.md"

CITABLE_82_ANCHORS: Final[frozenset[str]] = frozenset(
    {
        # [deviation] E2 item 7 — redação do A7 para o `parquet_gold_store.py`
        f"{_TECHNICAL_82}#2026-10-23--deviation-e2-item-7--redação-do-a7-para-o-"
        "parquet_gold_storepy--claude-executor-das-etapas",
        # [deviation] `env-equal` com `--preregistration-ref` obrigatória
        f"{_TECHNICAL_82}#2026-10-23--deviation-env-equal-com---preregistration-ref-"
        "obrigatória-emenda-do-runbook-e2e3--claude-executor",
        # [measurement] E2 — pré-voo da reprodução em `060537fc`
        f"{_TECHNICAL_82}#2026-10-23--measurement-e2--pré-voo-da-reprodução-em-060537fc--"
        "claude-executor-das-etapas",
        # [measurement] E3 — reprodução real e auditoria
        f"{_TECHNICAL_82}#2026-10-23--measurement-e3--reprodução-real-e-auditoria--"
        "claude-executor-das-etapas",
    }
)
"""As âncoras citáveis da 8.2 (A17): ponteiros exatos (caminho + âncora no estilo GitHub)."""

FORBIDDEN_CITABLE_POINTER_PREFIXES: Final[tuple[str, ...]] = (
    "docs/stages/8.2-",
    "docs/reports/equivalence_audit.md",
    "docs/reports/prior_evidence_registry.toml",
    "docs/adr/8_2_0003",
    "docs/adr/8_2_0004",
    "tests/equivalence/",
)
"""Fontes que nunca entram no citável (A17, 1ª barreira)."""


def _fold(text: str) -> str:
    """Sem caixa e com `_` ≡ `-` (a comparação do A17)."""
    return text.lower().replace("_", "-")


_FOLDED_ANCHORS: Final = frozenset(_fold(anchor) for anchor in CITABLE_82_ANCHORS)
_FOLDED_PREFIXES: Final = tuple(_fold(prefix) for prefix in FORBIDDEN_CITABLE_POINTER_PREFIXES)


def is_forbidden_citable_pointer(pointer: str) -> bool:
    """`True` se o ponteiro aponta para a evidência anterior (fora das âncoras citáveis)."""
    folded = _fold(pointer)
    if folded in _FOLDED_ANCHORS:
        return False
    return folded.startswith(_FOLDED_PREFIXES)


def _check_pointer(pointer: object, *, field: str) -> str:
    """Caminho relativo ao repo, **normalizado**, com âncora opcional `#…`.

    Segmento `.`/`..` ou vazio (`./docs`, `docs//x`, `docs/./x`) é recusado: um ponteiro
    não normalizado contornaria a comparação por prefixo da 1ª barreira do A17 (CC1-1).
    A barra final (diretório) é a única forma de segmento vazio aceita.
    """
    text = _non_empty_str(pointer, field=field)
    path = text.split("#", 1)[0]
    segments = path.split("/")
    if (
        not path
        or _ABSOLUTE_PATH.match(text)
        or "\\" in text
        or any(char.isspace() for char in text)
        or any(segment in {".", ".."} for segment in segments)
        or "" in segments[:-1]
    ):
        raise ValueError(
            f"{field} must be a repo-relative path with optional #anchor, got {text!r}"
        )
    return text


@dataclass(frozen=True, kw_only=True)
class DossierEntry:
    """Uma entrada do registro curado (concept 8.3 §4; D8).

    Primeira barreira do A17 (dono único, vale para todo produtor, inclusive o parser):
    entrada não-`internal` cujo `pointer` cai em `FORBIDDEN_CITABLE_POINTER_PREFIXES`
    (fora de `CITABLE_82_ANCHORS`) não constrói.

    Raises:
        ValueError: kind fora de `DossierEntryKind`, texto vazio, ponteiro inválido,
            `finding` sem `status = "open"`, `status` em outro kind ou ponteiro proibido
            numa entrada citável.
    """

    kind: DossierEntryKind
    title: str
    summary: str
    pointer: str
    status: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DossierEntryKind):
            raise ValueError(f"kind must be a DossierEntryKind, got {self.kind!r}")
        _non_empty_str(self.title, field="DossierEntry.title")
        _non_empty_str(self.summary, field="DossierEntry.summary")
        _check_pointer(self.pointer, field="DossierEntry.pointer")
        if self.kind is DossierEntryKind.FINDING:
            if self.status != OPEN_STATUS:
                raise ValueError(
                    f"a finding entry needs status {OPEN_STATUS!r}, got {self.status!r}"
                )
        elif self.status is not None:
            raise ValueError(f"status exists only in finding entries, got {self.status!r}")
        if self.kind is not DossierEntryKind.INTERNAL and is_forbidden_citable_pointer(
            self.pointer
        ):
            raise ValueError(
                f"a {self.kind.value} entry is citable and cannot point to {self.pointer!r} "
                "(prior evidence goes to an internal entry — A17)"
            )

    @property
    def visibility(self) -> Visibility:
        return Visibility.INTERNAL if self.kind is DossierEntryKind.INTERNAL else Visibility.CITABLE

    def as_mapping(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "title": self.title,
            "summary": self.summary,
            "pointer": self.pointer,
            "status": self.status,
        }


# --------------------------------------------------------------------------------------
# A segunda barreira do A17 (texto do citável)
# --------------------------------------------------------------------------------------

CITABLE_FORBIDDEN_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # o relatório de equivalência; só o diretório `8.2-equivalence-audit/` (com a
        # barra) das âncoras citáveis é poupado (refinamento CB-2 do technical 8.3 §1;
        # CC1-1: sem a barra, o termo casa)
        r"equivalence[_-]audit\.md",
        r"(?<!8\.2[_-])equivalence[_-]audit",
        r"equivalence[_-]audit(?!/)",
        r"prior[_-]evidence",
        r"tests/equivalence",
        r"8[._-]2[._-]000[34]",
        r"prior[_-]candidate[_-]labels",
        r"evid[êe]ncia\s+anterior",
        r"projeto\s+anterior",
        # a §5 do `reproduction_audit.md` (o citável só aponta as §1 a §4)
        r"reproduction[_-]audit(?:\.md)?\s*(?:#|§\s*)5",
        r"§\s*5\s+(?:do|of\s+the)\s+\W?reproduction[_-]audit",
    )
)
"""Os termos do A17 que nunca aparecem no texto do dossiê citável (2ª barreira)."""


def find_forbidden(text: str) -> tuple[str, ...]:
    """Os trechos de `text` que casam `CITABLE_FORBIDDEN_PATTERNS`, na ordem dos padrões."""
    return tuple(
        match.group(0) for pattern in CITABLE_FORBIDDEN_PATTERNS for match in pattern.finditer(text)
    )


# --------------------------------------------------------------------------------------
# O dossiê
# --------------------------------------------------------------------------------------


class Visibility(StrEnum):
    """Arquivo de destino de uma seção: o citável ou o interno (I12)."""

    CITABLE = "citable"
    INTERNAL = "internal"


CITABLE_SECTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("claim_pointers", "Ponteiros das afirmações do texto"),
    ("declared_power", "Poder declarado do gate H1"),
    ("identity", "Identidade da entrada"),
    ("preregistration_chain", "Cadeia do pré-registro"),
    ("pre_anchor_computation", "Computação pré-âncora já registrada"),
    ("blinding_statement", "Declaração de cegamento"),
    ("judged_generation", "Geração julgada preservada"),
    ("environment", "Ambiente"),
    ("code_commits", "Commits do código e árvore limpa"),
    ("seeds", "Seeds de cada etapa aleatória"),
    ("figures", "Figuras: fonte e reconstrução"),
    ("reproduction", "Resultado da reprodução"),
    ("deviations", "Registro de desvios do plano"),
)
"""As seções citáveis (id, título): uma por linha da tabela do doc §7 menos a última, na
ordem das camadas do D8 (do veredito para os detalhes — Sandve Rule 8)."""

INTERNAL_SECTION: Final = ("internal", "Interno, fora do texto do TCC")
_ROW_ARITY: Final = 2


@dataclass(frozen=True, kw_only=True)
class DossierBlock:
    """Um bloco de uma seção: título, linhas (campo → valor) e o ponteiro da fonte.

    Raises:
        ValueError: título vazio, linha que não é par de textos (campo não vazio) ou
            ponteiro inválido.
    """

    heading: str
    rows: tuple[tuple[str, str], ...]
    pointer: str | None = None

    def __post_init__(self) -> None:
        _non_empty_str(self.heading, field="DossierBlock.heading")
        if not isinstance(self.rows, tuple):
            raise ValueError("DossierBlock.rows must be a tuple")
        for row in self.rows:
            if not isinstance(row, tuple) or len(row) != _ROW_ARITY:
                raise ValueError(f"a dossier row is a (field, value) pair, got {row!r}")
            _non_empty_str(row[0], field="row field")
            if not isinstance(row[1], str):
                raise ValueError(f"row value must be str, got {row[1]!r}")
        if self.pointer is not None:
            _check_pointer(self.pointer, field="DossierBlock.pointer")


@dataclass(frozen=True, kw_only=True)
class DossierSection:
    """Uma seção do dossiê, com a visibilidade que decide o arquivo.

    Raises:
        ValueError: id/título vazios, visibilidade fora de `Visibility` ou bloco inválido.
    """

    section_id: str
    title: str
    visibility: Visibility
    blocks: tuple[DossierBlock, ...]

    def __post_init__(self) -> None:
        _non_empty_str(self.section_id, field="section_id")
        _non_empty_str(self.title, field="DossierSection.title")
        if not isinstance(self.visibility, Visibility):
            raise ValueError(f"visibility must be a Visibility, got {self.visibility!r}")
        if not isinstance(self.blocks, tuple) or not all(
            isinstance(block, DossierBlock) for block in self.blocks
        ):
            raise ValueError("blocks must be a tuple of DossierBlock")


@dataclass(frozen=True, kw_only=True)
class TraceabilityDossier:
    """O dossiê: exatamente as `CITABLE_SECTIONS` (citáveis, na ordem) e a seção interna.

    A 1ª barreira do A17 vale também para o ponteiro de cada bloco de seção citável (não só
    para a `DossierEntry`): bloco montado de outra fonte não leva a evidência anterior ao
    citável (Checkpoint C do bloco 1, CC1-1).

    Raises:
        ValueError: seção fora da lista fechada, fora de ordem, com título ou visibilidade
            diferentes, seção interna ausente/repetida ou ponteiro proibido em seção
            citável.
    """

    sections: tuple[DossierSection, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.sections, tuple) or not all(
            isinstance(section, DossierSection) for section in self.sections
        ):
            raise ValueError("sections must be a tuple of DossierSection")
        expected = (
            *((sid, title, Visibility.CITABLE) for sid, title in CITABLE_SECTIONS),
            (*INTERNAL_SECTION, Visibility.INTERNAL),
        )
        got = tuple((s.section_id, s.title, s.visibility) for s in self.sections)
        if got != expected:
            raise ValueError(
                "dossier sections must be exactly CITABLE_SECTIONS followed by the internal "
                f"one, got {[(sid, vis.value) for sid, _, vis in got]}"
            )
        forbidden = [
            block.pointer
            for section in self.sections_of(Visibility.CITABLE)
            for block in section.blocks
            if block.pointer is not None and is_forbidden_citable_pointer(block.pointer)
        ]
        if forbidden:
            raise ValueError(
                f"citable sections cannot point to {forbidden} (prior evidence goes to the "
                "internal section — A17, 1st barrier)"
            )

    def sections_of(self, visibility: Visibility) -> tuple[DossierSection, ...]:
        """As seções de um arquivo, na ordem."""
        return tuple(s for s in self.sections if s.visibility is visibility)


# --------------------------------------------------------------------------------------
# Validação da escrita (dono único do fake e do sink real — CB-4)
# --------------------------------------------------------------------------------------

PDF_MAGIC: Final = b"%PDF"


def check_artifacts(
    figures: Sequence[tuple[str, bytes, FigureRecord]], dossier: TraceabilityDossier
) -> None:
    """Valida tudo antes de qualquer escrita: dez ids do catálogo, `%PDF`, registro do id.

    Raises:
        ValueError: id repetido, ausente ou fora do catálogo; bytes que não começam com
            `%PDF`; registro de outro id; dossiê que não é `TraceabilityDossier`.
    """
    if not isinstance(dossier, TraceabilityDossier):
        raise ValueError("dossier must be a TraceabilityDossier")
    ids = [figure_id for figure_id, _, _ in figures]
    if len(set(ids)) != len(ids):
        raise ValueError(f"figure ids repeat: {ids}")
    if set(ids) != set(FIGURE_IDS):
        missing = sorted(set(FIGURE_IDS) - set(ids))
        unknown = sorted(set(ids) - set(FIGURE_IDS))
        raise ValueError(f"figures must be the catalog's ten: missing {missing}, unknown {unknown}")
    for figure_id, content, record in figures:
        if not isinstance(content, bytes) or not content.startswith(PDF_MAGIC):
            raise ValueError(f"figure {figure_id!r} bytes are not a PDF")
        if not isinstance(record, FigureRecord) or record.figure_id != figure_id:
            raise ValueError(f"figure {figure_id!r} carries the record of another figure")


# --------------------------------------------------------------------------------------
# Comando e resultado do use case
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GenerateReportArtifactsCommand:
    """O pedido do `GenerateReportArtifacts` (technical 8.3 §1 "Comando e resultado").

    A partição não vem aqui: sai do plano resolvido (`refresh_command_from`).
    `cohort_seeds` é a lista `seeds` do arquivo de cohort, lida no CLI (I6).

    Raises:
        ValueError: `name`/`preregistration_ref` vazios, `revision` negativa, seeds vazias,
            repetidas ou não-`int`, registro com item que não é `DossierEntry`.
    """

    name: str
    revision: int
    preregistration_ref: str
    cohort_seeds: tuple[int, ...]
    register: tuple[DossierEntry, ...]

    def __post_init__(self) -> None:
        _non_empty_str(self.name, field="name")
        _non_empty_str(self.preregistration_ref, field="preregistration_ref")
        validate_int_at_least(self.revision, minimum=0, field="revision")
        if not isinstance(self.cohort_seeds, tuple) or not self.cohort_seeds:
            raise ValueError("cohort_seeds must be a non-empty tuple")
        for seed in self.cohort_seeds:
            validate_int_at_least(seed, minimum=0, field="cohort_seeds item")
        if len(set(self.cohort_seeds)) != len(self.cohort_seeds):
            raise ValueError(f"cohort_seeds repeat a seed: {self.cohort_seeds}")
        if not isinstance(self.register, tuple) or not all(
            isinstance(entry, DossierEntry) for entry in self.register
        ):
            raise ValueError("register must be a tuple of DossierEntry")


@dataclass(frozen=True, kw_only=True)
class ReportArtifactsResult:
    """O que a geração produziu: a ref, a geração, (id, `data_digest`) por figura.

    Raises:
        ValueError: ref vazia, digest inválido, figuras fora da ordem do catálogo ou
            contagem do registro negativa.
    """

    preregistration_ref: str
    generation_digest: str
    figures: tuple[tuple[str, str], ...]
    register_entries: int

    def __post_init__(self) -> None:
        _non_empty_str(self.preregistration_ref, field="preregistration_ref")
        validate_sha256_hex(self.generation_digest, field="generation_digest")
        if (
            not isinstance(self.figures, tuple)
            or tuple(figure[0] if isinstance(figure, tuple) else None for figure in self.figures)
            != FIGURE_IDS
        ):
            raise ValueError("figures must be (id, data_digest) in the catalog order")
        for figure_id, digest in self.figures:
            validate_sha256_hex(digest, field=f"data_digest of {figure_id}")
        validate_int_at_least(self.register_entries, minimum=0, field="register_entries")
