"""VO `HitSequence` — a sequência de violações de uma série x horizonte (primitivo único).

Value object de domínio **frozen, stdlib-only** (concept 6.3 §4, I2, I4, I5, I8, C1;
ADR `6_3_0001` item 1; ADR `6_3_0004`). Carrega, para **um** (modelo, horizonte), o
indicador de **violação** por linha alinhada da `CoverageSeries`:

- `True` = violação, `False` = sem violação, `None` = linha mascarada pelo
  `DegeneracyGate` (lacuna — a sequência continua 1:1 com os timestamps, I4);
- a taxa nominal de violação sai da grade pela regra do `kind`
  (`violation_rate_for`, dono único): `pair_miscoverage(τ_l)` no intervalo, τ na
  cauda inferior, 1 - τ na superior — nunca de constante do código (I2);
- a autodescrição de quando for persistida (padrão ADR 6.1.0004): a `tolerance` do
  gate, a `degeneracy_rate` da série de origem, `includes_degenerate` e, numa
  sub-série DGT, `dgt_offset`/`dgt_step`.

Transições (n00, n01, n10, n11) só entre posições consecutivas **ambas observadas**
(ADR 6.3.0004 item 2): `count_transitions` é a única escrita da regra das lacunas,
consumida por `HitSequence.transition_counts` e pelo serviço de LR.

`dgt_partition` implementa a partição de Diebold, Gunther & Tay (1998, §6) para
h > 1: sub-séries {j, j+h, j+2h, …}, j = 0..min(h, T)-1, iid sob a nula de DGT (I8).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    is_multi_step,
    validate_horizon,
)
from financial_forecasting.features.evaluation.domain.value_objects._tolerance import (
    validate_tolerance,
)
from financial_forecasting.features.evaluation.domain.value_objects.coverage_series import (
    is_symmetric_pair,
    pair_miscoverage,
)


class HitKind(StrEnum):
    """O que conta como violação na linha (regra FA7 do `HitSequences`, doc §4.5).

    - `INTERVAL`: violação = `not is_inside_closed(y, l, u)`; taxa = `pair_miscoverage(τ_l)`;
    - `LOWER_TAIL`: violação = `is_at_or_below(y, q̂_τ)`; taxa = τ;
    - `UPPER_TAIL`: violação = `not is_at_or_below(y, q̂_τ)`; taxa = 1 - τ.
    """

    INTERVAL = "interval"
    LOWER_TAIL = "lower_tail"
    UPPER_TAIL = "upper_tail"


_LEVELS_SIZE = {HitKind.INTERVAL: 2, HitKind.LOWER_TAIL: 1, HitKind.UPPER_TAIL: 1}


def violation_rate_for(kind: HitKind, levels: Sequence[float]) -> float:
    """Taxa nominal de violação pela regra do `kind` (I2) — única escrita da regra.

    `pair_miscoverage(levels[0])` (= 2·τ_l) no intervalo, `levels[0]` na cauda
    inferior e `1.0 - levels[0]` na superior. Consumida pela validação do VO e pelo
    construtor `HitSequences`, para a taxa gravada e a conferida serem a mesma conta.
    """
    if kind is HitKind.INTERVAL:
        return pair_miscoverage(levels[0])
    if kind is HitKind.LOWER_TAIL:
        return levels[0]
    return 1.0 - levels[0]


def validate_kind_and_levels(kind: HitKind, levels: Sequence[float]) -> None:
    """`kind` é `HitKind`; `levels` tem 2 (intervalo, par simétrico τ_l < τ_u) ou 1 nível."""
    if not isinstance(kind, HitKind):
        raise ValueError(f"kind must be a HitKind, got {kind!r}")
    expected_size = _LEVELS_SIZE[kind]
    if len(levels) != expected_size:
        raise ValueError(
            f"levels must have {expected_size} element(s) for kind={kind.value}, got {levels}"
        )
    if kind is HitKind.INTERVAL and not (levels[0] < levels[1] and is_symmetric_pair(*levels)):
        raise ValueError(
            "levels of an interval must be a symmetric pair (tau_l, tau_u) of the grid "
            f"with tau_l < tau_u, got {levels}"
        )


def validate_violation_rate(kind: HitKind, levels: Sequence[float], violation_rate: float) -> None:
    """`violation_rate` igual (exato) à regra do `kind` (`violation_rate_for`) e em (0, 1)."""
    expected_rate = violation_rate_for(kind, levels)
    if violation_rate != expected_rate:
        raise ValueError(
            f"violation_rate must equal the {kind.value} rule of the grid = "
            f"{expected_rate!r}, got {violation_rate!r}"
        )
    if not 0.0 < violation_rate < 1.0:
        raise ValueError(f"violation_rate must be in (0, 1), got {violation_rate!r}")


def validate_includes_degenerate(includes_degenerate: bool) -> None:
    """A variante (`includes_degenerate`) é `bool` - `1`/`0` não são variante."""
    if type(includes_degenerate) is not bool:
        raise ValueError(f"includes_degenerate must be a bool, got {includes_degenerate!r}")


def validate_mask_description(
    *, tolerance: float, degeneracy_rate: float, includes_degenerate: bool, tolerance_field: str
) -> None:
    """Autodescrição da máscara: tolerância (regra única), taxa em [0, 1], variante `bool`."""
    validate_tolerance(tolerance, field=tolerance_field)
    if not is_finite_number(degeneracy_rate) or not (0.0 <= degeneracy_rate <= 1.0):
        raise ValueError(f"degeneracy_rate must be in [0, 1], got {degeneracy_rate!r}")
    validate_includes_degenerate(includes_degenerate)


def validate_dgt_fields(*, dgt_offset: int | None, dgt_step: int | None, horizon: int) -> None:
    """Sub-série DGT: ambos ou nenhum; `int` não-`bool`; `dgt_step == horizon ≥ 2`;
    `0 ≤ dgt_offset < dgt_step` (decisões de detalhe do technical §1)."""
    if (dgt_offset is None) != (dgt_step is None):
        raise ValueError(
            f"dgt_offset and dgt_step must be both set or both None, got "
            f"dgt_offset={dgt_offset!r}, dgt_step={dgt_step!r}"
        )
    if dgt_offset is None or dgt_step is None:
        return
    for name, value in (("dgt_offset", dgt_offset), ("dgt_step", dgt_step)):
        if type(value) is not int:
            raise ValueError(f"{name} must be an int (not bool), got {value!r}")
    if dgt_step != horizon:
        raise ValueError(f"dgt_step must equal horizon={horizon}, got {dgt_step}")
    if not is_multi_step(dgt_step):
        raise ValueError(
            f"dgt_step must be >= 2 (horizon = 1 has no DGT sub-series), got {dgt_step}"
        )
    if not 0 <= dgt_offset < dgt_step:
        raise ValueError(f"dgt_offset must be in [0, dgt_step={dgt_step}), got {dgt_offset}")


def belongs_to_dgt_partition(dgt_step: int | None) -> bool:
    """Predicado único de "sub-série DGT" (`dgt_step` preenchido; pares já validados)."""
    return dgt_step is not None


def validate_hit_identity(  # noqa: PLR0913 - um parâmetro por campo da identidade (keyword-only)
    *,
    horizon: int,
    kind: HitKind,
    levels: Sequence[float],
    violation_rate: float,
    tolerance: float,
    degeneracy_rate: float,
    includes_degenerate: bool,
    dgt_offset: int | None,
    dgt_step: int | None,
    tolerance_field: str,
) -> None:
    """Identidade autodescritiva de uma sequência de violações (D8) - regra única.

    Consumida pela `HitSequence` e pelos relatórios que a copiam
    (`ChristoffersenReport`), que são persistidos como autodescritivos.
    """
    validate_horizon(horizon, field="horizon")
    validate_kind_and_levels(kind, levels)
    validate_violation_rate(kind, levels, violation_rate)
    validate_mask_description(
        tolerance=tolerance,
        degeneracy_rate=degeneracy_rate,
        includes_degenerate=includes_degenerate,
        tolerance_field=tolerance_field,
    )
    validate_dgt_fields(dgt_offset=dgt_offset, dgt_step=dgt_step, horizon=horizon)


def validate_violation_elements(violations: Sequence[object]) -> None:
    """Todo elemento é `bool` ou `None` (`1`, `0`, `"x"` erguem) - regra única do slice.

    `type(v) is bool`: `int` não é violação. Consumida pela `HitSequence` e pelo
    primitivo `christoffersen_statistics` (chamado também fora de uma `HitSequence`).
    """
    for index, value in enumerate(violations):
        if value is not None and type(value) is not bool:
            raise ValueError(f"violations[{index}] must be a bool or None, got {value!r}")


def count_observed(violations: Sequence[bool | None]) -> int:
    """Posições não-`None` (o n da banda de Wilson e do Kupiec POF) - contagem única."""
    return sum(1 for value in violations if value is not None)


def count_violations(violations: Sequence[bool | None]) -> int:
    """Violações (`True`) entre as observadas (o x do Kupiec POF) - contagem única."""
    return sum(1 for value in violations if value is True)


def count_transitions(violations: Sequence[bool | None]) -> tuple[int, int, int, int]:
    """(n00, n01, n10, n11) sobre pares consecutivos **ambos** observados (ADR 6.3.0004).

    n_ij conta t com `violations[t-1] == i` e `violations[t] == j`; um par com `None`
    em qualquer ponta não conta (a lacuna quebra a transição). Sem lacunas, é a
    convenção pura t = 2..T. Dono único da regra: o VO e o serviço de LR a consomem.
    """
    n00 = n01 = n10 = n11 = 0
    for previous, current in pairwise(violations):
        if previous is None or current is None:
            continue
        if previous:
            if current:
                n11 += 1
            else:
                n10 += 1
        elif current:
            n01 += 1
        else:
            n00 += 1
    return n00, n01, n10, n11


@dataclass(frozen=True)
class HitSequence:
    """Sequência de violações de uma série x horizonte, com lacunas da máscara.

    Campos:
        horizon: rótulo da série de origem (≥ 1).
        kind: `HitKind` — intervalo, cauda inferior ou superior.
        levels: `(τ_l, τ_u)` no intervalo; `(τ,)` nas caudas.
        violation_rate: p_viol em (0, 1), igual (exato) a `violation_rate_for`.
        target_timestamps: os das posições desta sequência, estritamente crescentes.
        violations: 1:1 com as posições; `None` = linha mascarada.
        tolerance: a do gate que produziu a máscara (finita, ≥ 0).
        degeneracy_rate: taxa do gate na série de origem, em [0, 1].
        includes_degenerate: `True` ⇒ nenhum `None`, salvo série 100 % degenerada.
        dgt_offset: j da sub-série DGT; `None` fora da partição.
        dgt_step: h da partição; `None` fora da partição.

    Raises:
        ValueError: em qualquer caso de C1 (concept 6.3 §6), na construção.
    """

    horizon: int
    kind: HitKind
    levels: tuple[float, ...]
    violation_rate: float
    target_timestamps: tuple[str, ...]
    violations: tuple[bool | None, ...]
    tolerance: float
    degeneracy_rate: float
    includes_degenerate: bool
    dgt_offset: int | None = None
    dgt_step: int | None = None

    def __post_init__(self) -> None:
        """C1: um ramo por caso, mensagens nomeando o campo ou a posição."""
        self._check_lengths()
        self._check_timestamps()
        validate_hit_identity(
            horizon=self.horizon,
            kind=self.kind,
            levels=self.levels,
            violation_rate=self.violation_rate,
            tolerance=self.tolerance,
            degeneracy_rate=self.degeneracy_rate,
            includes_degenerate=self.includes_degenerate,
            dgt_offset=self.dgt_offset,
            dgt_step=self.dgt_step,
            tolerance_field="HitSequence.tolerance",
        )
        self._check_elements()
        self._check_gaps()

    @property
    def n_observed(self) -> int:
        """Posições não-`None` — o n da banda de Wilson e do Kupiec POF (I4)."""
        return count_observed(self.violations)

    @property
    def n_violations(self) -> int:
        """Violações (`True`) entre as observadas — o x do Kupiec POF."""
        return count_violations(self.violations)

    @property
    def transition_counts(self) -> tuple[int, int, int, int]:
        """(n00, n01, n10, n11) sobre pares consecutivos observados (`count_transitions`)."""
        return count_transitions(self.violations)

    @property
    def is_dgt_subseries(self) -> bool:
        """`True` numa sub-série da partição DGT (`belongs_to_dgt_partition`)."""
        return belongs_to_dgt_partition(self.dgt_step)

    def dgt_partition(self) -> tuple[HitSequence, ...]:
        """Sub-séries DGT {j, j+h, …}, j = 0..min(h, T)-1; `horizon == 1` → `(self,)`.

        Cada sub-série mantém `horizon`, `kind`, `levels`, `violation_rate`,
        `tolerance`, `includes_degenerate` e a `degeneracy_rate` da série de origem,
        com os timestamps e violações das suas posições (lacunas preservadas).

        Raises:
            ValueError: chamada numa sub-série DGT (sem re-partição, I8).
        """
        if self.is_dgt_subseries:
            raise ValueError(
                f"dgt_partition cannot be applied to a DGT sub-series "
                f"(dgt_offset={self.dgt_offset}, dgt_step={self.dgt_step})"
            )
        if not is_multi_step(self.horizon):
            return (self,)
        step = self.horizon
        return tuple(
            HitSequence(
                horizon=self.horizon,
                kind=self.kind,
                levels=self.levels,
                violation_rate=self.violation_rate,
                target_timestamps=self.target_timestamps[offset::step],
                violations=self.violations[offset::step],
                tolerance=self.tolerance,
                degeneracy_rate=self.degeneracy_rate,
                includes_degenerate=self.includes_degenerate,
                dgt_offset=offset,
                dgt_step=step,
            )
            for offset in range(min(step, len(self.violations)))
        )

    def _check_lengths(self) -> None:
        n_violations, n_timestamps = len(self.violations), len(self.target_timestamps)
        if n_violations != n_timestamps:
            raise ValueError(
                f"violations and target_timestamps must align 1:1, got lengths "
                f"{n_violations} and {n_timestamps}"
            )
        if n_violations == 0:
            raise ValueError("a HitSequence needs at least one position (T >= 1)")

    def _check_timestamps(self) -> None:
        for index, (previous, current) in enumerate(pairwise(self.target_timestamps), 1):
            if current <= previous:
                raise ValueError(
                    "target_timestamps must be strictly increasing: position "
                    f"{index} has {current!r} after {previous!r}"
                )

    def _check_elements(self) -> None:
        validate_violation_elements(self.violations)

    def _check_gaps(self) -> None:
        n_gaps = len(self.violations) - self.n_observed
        if self.includes_degenerate:
            self._check_without_gaps_variant(n_gaps)
        # Na sub-série DGT a taxa é a da série de origem, não a das posições da sub-série.
        if not self.includes_degenerate and not self.is_dgt_subseries:
            expected = n_gaps / len(self.violations)
            if self.degeneracy_rate != expected:
                raise ValueError(
                    f"degeneracy_rate must be n_None / T = {expected!r} in the masked "
                    f"variant, got {self.degeneracy_rate!r}"
                )

    def _check_without_gaps_variant(self, n_gaps: int) -> None:
        # Variante "sem lacunas": nenhuma lacuna, salvo série 100 % degenerada, e a taxa
        # do gate é 1.0 exatamente quando todas as posições são None (ADR 6.3.0004 item 4).
        size = len(self.violations)
        if 0 < n_gaps < size:
            raise ValueError(
                "includes_degenerate=True allows gaps only when every position is None "
                f"(fully degenerate series), got {n_gaps} of {size}"
            )
        if (n_gaps == size) != (self.degeneracy_rate == 1.0):
            raise ValueError(
                "includes_degenerate=True requires degeneracy_rate == 1.0 exactly when every "
                f"position is None, got degeneracy_rate={self.degeneracy_rate!r} with "
                f"{n_gaps} of {size} positions None"
            )
