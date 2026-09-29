"""VOs da montagem das séries do gold: achados, relatório de alinhamento e amostras (6.4).

Value objects de domínio **frozen, stdlib-only** (concept 6.4 §4 `SeriesAssembly`, D1;
ADR `6_4_0003`, `6_4_0007`). São a saída do `SeriesAssembly.assemble`:

- `AlignmentKind` — os 19 tipos de achado das regras I3-I10 (um por violação);
- `AlignmentFinding` — um achado com o seu escopo (`horizon`/`model`/`seed`, cada um
  opcional conforme a regra) e um `detail` legível;
- `AlignmentReport` — todos os achados e, por horizonte, o T da amostra comum
  (`common_points`);
- `HorizonSamples` — as duas amostras de um horizonte (D5; ADR `6_4_0007`): `full`
  (toda a série de cada (modelo, seed)) e `common` (a fatia da interseção comum), S
  séries por modelo alinhadas às seeds;
- `AssembledCohort` — o relatório e, **só quando não há achado**, as amostras por
  horizonte (D1: achado bloqueia a montagem, nunca vira exceção).

A coerência é verificada na construção (ADR `0_0_0020`); o conteúdo das séries
(grade, finitude, ordem) já é garantido pela `CoverageSeries`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    CoverageSeries,
)
from financial_forecasting.features.evaluation.domain.value_objects.forecast_record import (
    check_non_empty_str,
    check_optional_seed,
)


class AlignmentKind(StrEnum):
    """Tipo de achado da montagem (concept 6.4 I3-I10); a ordem é a ordem de relato."""

    MULTIPLE_FEATURE_SETS = "multiple_feature_sets"
    MULTIPLE_CONFIG_SIGNATURES = "multiple_config_signatures"
    ORPHAN_RUN = "orphan_run"
    MODEL_VERSION_MISMATCH = "model_version_mismatch"
    DUPLICATE_POINT = "duplicate_point"
    DECISION_INDEX_MISMATCH = "decision_index_mismatch"
    HORIZON_LABEL_MISMATCH = "horizon_label_mismatch"
    GRID_INCOMPLETE = "grid_incomplete"
    GRID_DIVERGENT = "grid_divergent"
    GUARDRAIL_FLAG_MISMATCH = "guardrail_flag_mismatch"
    REALIZED_MISSING = "realized_missing"
    INTERIOR_GAP = "interior_gap"
    TRUNCATED_SUFFIX = "truncated_suffix"
    PREFIX_OVER_DEFICIT = "prefix_over_deficit"
    FOLD_COVERAGE = "fold_coverage"
    SEED_HORIZON_COVERAGE = "seed_horizon_coverage"
    HORIZON_MISSING = "horizon_missing"
    REQUIRED_MODEL_MISSING = "required_model_missing"
    COMMON_SAMPLE_TOO_SHORT = "common_sample_too_short"


def _seed_order(seed: int | None) -> tuple[int, int]:
    # `None` antes de qualquer int (convenção de ordem do technical 6.4 §1)
    return (0, 0) if seed is None else (1, seed)


@dataclass(frozen=True)
class AlignmentFinding:
    """Um achado da montagem.

    Campos:
        kind: tipo (`AlignmentKind`).
        horizon: horizonte do achado, ou `None` (regra de cohort, ex. `orphan_run`).
        model: modelo do achado, ou `None`.
        seed: seed do achado (`int` não-`bool`), ou `None`.
        detail: descrição legível (`str` não-vazia).

    Raises:
        ValueError: campo fora da forma acima, na construção.
    """

    kind: AlignmentKind
    horizon: int | None
    model: str | None
    seed: int | None
    detail: str

    def __post_init__(self) -> None:
        """Forma de cada campo."""
        if not isinstance(self.kind, AlignmentKind):
            raise ValueError(f"kind must be an AlignmentKind, got {self.kind!r}")
        if self.horizon is not None:
            validate_horizon(self.horizon, field="horizon")
        if self.model is not None:
            check_non_empty_str(self.model, field="model")
        check_optional_seed(self.seed)
        check_non_empty_str(self.detail, field="detail")


@dataclass(frozen=True)
class AlignmentReport:
    """Achados da montagem e o T da amostra comum por horizonte.

    Campos:
        findings: todos os achados (`tuple` de `AlignmentFinding`).
        common_points: `(horizonte, T)` por horizonte, horizontes estritamente
            crescentes, T `int` não-`bool` ≥ 1.

    Raises:
        ValueError: contêiner não-`tuple`, elemento de tipo errado, horizonte inválido
            ou fora de ordem, T < 1, na construção.
    """

    findings: tuple[AlignmentFinding, ...]
    common_points: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        """Forma dos achados e dos pares (horizonte, T)."""
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, AlignmentFinding) for finding in self.findings
        ):
            raise ValueError(f"findings must be a tuple of AlignmentFinding, got {self.findings!r}")
        if not isinstance(self.common_points, tuple):
            raise ValueError(f"common_points must be a tuple, got {self.common_points!r}")
        previous = 0
        for entry in self.common_points:
            if not isinstance(entry, tuple) or len(entry) != 2:  # noqa: PLR2004 — par (h, T)
                raise ValueError(f"common_points entries must be (horizon, T) pairs, got {entry!r}")
            horizon, n_points = entry
            validate_horizon(horizon, field="common_points horizon")
            if horizon <= previous:
                raise ValueError(
                    f"common_points horizons must be strictly increasing, got {self.common_points}"
                )
            if isinstance(n_points, bool) or not isinstance(n_points, int) or n_points < 1:
                raise ValueError(f"common_points T must be an int >= 1, got {n_points!r}")
            previous = horizon


@dataclass(frozen=True)
class HorizonSamples:
    """As duas amostras de um horizonte, S séries por modelo alinhadas às seeds.

    Campos:
        horizon: rótulo do horizonte (≥ 1) — de toda série.
        models: modelos, ordenados e únicos (≥ 1).
        levels: grade comum de níveis — de toda série.
        seeds: modelo → seeds (ordenadas, `None` antes de int, únicas, ≥ 1).
        full: modelo → uma `CoverageSeries` por seed com todos os pontos da série.
        common: modelo → uma `CoverageSeries` por seed na interseção comum.
        n_common: T da amostra comum (≥ 1) — `n_points` de toda série `common`.
        common_first_target_timestamp, common_last_target_timestamp: primeiro e
            último `target_timestamp` de toda série `common`.

    Raises:
        ValueError: qualquer incoerência entre os campos, na construção.
    """

    horizon: int
    models: tuple[str, ...]
    levels: tuple[float, ...]
    seeds: Mapping[str, tuple[int | None, ...]]
    full: Mapping[str, tuple[CoverageSeries, ...]]
    common: Mapping[str, tuple[CoverageSeries, ...]]
    n_common: int
    common_first_target_timestamp: str
    common_last_target_timestamp: str

    def __post_init__(self) -> None:
        """Modelos, chaves, seeds, séries e amostra comum coerentes."""
        validate_horizon(self.horizon, field="horizon")
        self._check_models()
        n_common = self.n_common
        if isinstance(n_common, bool) or not isinstance(n_common, int) or n_common < 1:
            raise ValueError(f"n_common must be an int >= 1, got {n_common!r}")
        check_non_empty_str(
            self.common_first_target_timestamp, field="common_first_target_timestamp"
        )
        check_non_empty_str(self.common_last_target_timestamp, field="common_last_target_timestamp")
        for name in ("seeds", "full", "common"):
            keys = tuple(sorted(getattr(self, name)))
            if keys != self.models:
                raise ValueError(f"{name} keys must be the models {self.models}, got {keys}")
        for model in self.models:
            self._check_model(model)

    def _check_models(self) -> None:
        models = self.models
        if not isinstance(models, tuple) or not models:
            raise ValueError(f"models must be a non-empty tuple, got {models!r}")
        for model in models:
            check_non_empty_str(model, field="model")
        if list(models) != sorted(set(models)):
            raise ValueError(f"models must be sorted and unique, got {models}")

    def _check_model(self, model: str) -> None:
        seeds = self.seeds[model]
        if not isinstance(seeds, tuple) or not seeds:
            raise ValueError(f"model {model!r}: seeds must be a non-empty tuple, got {seeds!r}")
        for seed in seeds:
            check_optional_seed(seed)
        if list(seeds) != sorted(set(seeds), key=_seed_order):
            raise ValueError(f"model {model!r}: seeds must be sorted and unique, got {seeds}")
        for name in ("full", "common"):
            series = getattr(self, name)[model]
            if not isinstance(series, tuple) or len(series) != len(seeds):
                raise ValueError(
                    f"model {model!r}: {name} must hold one series per seed ({len(seeds)}), "
                    f"got {series!r}"
                )
            for item in series:
                self._check_series(item, model=model, sample=name)

    def _check_series(self, series: object, *, model: str, sample: str) -> None:
        where = f"model {model!r}, {sample}"
        if not isinstance(series, CoverageSeries):
            raise ValueError(f"{where}: expected a CoverageSeries, got {series!r}")
        if series.horizon != self.horizon:
            raise ValueError(f"{where}: series horizon {series.horizon} != {self.horizon}")
        if series.levels != self.levels:
            raise ValueError(f"{where}: series levels {series.levels} != {self.levels}")
        if sample == "common" and (
            series.n_points != self.n_common
            or series.target_timestamps[0] != self.common_first_target_timestamp
            or series.target_timestamps[-1] != self.common_last_target_timestamp
        ):
            raise ValueError(
                f"{where}: series must have T={self.n_common} points from "
                f"{self.common_first_target_timestamp!r} to "
                f"{self.common_last_target_timestamp!r}, got T={series.n_points} from "
                f"{series.target_timestamps[0]!r} to {series.target_timestamps[-1]!r}"
            )


@dataclass(frozen=True)
class AssembledCohort:
    """Resultado da montagem: o relatório e, sem achado, as amostras por horizonte.

    Campos:
        alignment: o `AlignmentReport`.
        horizons: `HorizonSamples` por horizonte, estritamente crescentes — vazio **se e
            somente se** `alignment.findings` não é vazio; sem achado, os pares
            `(horizon, n_common)` são os `alignment.common_points`.

    Raises:
        ValueError: achado com horizontes, nenhum achado sem horizontes, horizontes fora
            de ordem ou T divergente do relatório, na construção.
    """

    alignment: AlignmentReport
    horizons: tuple[HorizonSamples, ...]

    def __post_init__(self) -> None:
        """Achados xor horizontes; ordem e T coerentes com o relatório."""
        if not isinstance(self.alignment, AlignmentReport):
            raise ValueError(f"alignment must be an AlignmentReport, got {self.alignment!r}")
        if not isinstance(self.horizons, tuple) or not all(
            isinstance(samples, HorizonSamples) for samples in self.horizons
        ):
            raise ValueError(f"horizons must be a tuple of HorizonSamples, got {self.horizons!r}")
        if bool(self.alignment.findings) == bool(self.horizons):
            raise ValueError(
                "horizons must be empty if and only if the alignment has findings: "
                f"{len(self.alignment.findings)} findings and {len(self.horizons)} horizons"
            )
        labels = [samples.horizon for samples in self.horizons]
        if labels != sorted(set(labels)):
            raise ValueError(f"horizons must be strictly increasing, got {labels}")
        points = tuple((samples.horizon, samples.n_common) for samples in self.horizons)
        if self.horizons and points != self.alignment.common_points:
            raise ValueError(
                f"horizons (h, T) {points} must equal alignment.common_points "
                f"{self.alignment.common_points}"
            )
