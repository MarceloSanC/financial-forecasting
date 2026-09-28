"""VO `CoverageSeries` — a entrada alinhada, por horizonte, de toda métrica do Step 6.

Value object de domínio **frozen, stdlib-only** (concept 6.1 §4, I1/I2/I3, C1/C2;
ADR `6_1_0002`). Carrega, para **um** modelo x **um** horizonte, a tripla por ponto
que toda métrica da 6.1 consome — a grade de quantis do fornecedor
(`QuantileForecast` do 4.3), o retorno realizado e o `target_timestamp` —, alinhada
1:1 e com as invariantes da série verificadas **uma vez**, na construção (ADR
`0_0_0020`):

- um único rótulo `horizon` (≥ 1): não existe contêiner multi-horizonte, logo nenhum
  serviço agrega entre horizontes (I1). Que cada ponto seja mesmo desse horizonte é
  garantia do builder (6.4) — `QuantileForecast` não carrega horizonte;
- `target_timestamps` estritamente crescentes (únicos e ordenados);
- grade comum `levels` em (0, 1), estritamente crescente e **simétrica**
  (``|τ_k + τ_{K+1-k} - 1| ≤ 1e-12``), com ao menos um par (τ_1 < 0.5);
- em todo ponto, `forecast.levels == levels` e `guardrail_values` finito e
  não-decrescente — `QuantileForecast` é dataclass pública sem `__post_init__` (só o
  `from_raw` ordena), então a série revalida em vez de confiar;
- todo `realized` finito.

Valor não-finito **ergue**, nunca descarta a linha (ADR `6_1_0002` item 5; ADR
`0_0_0011`): excluir linha é grau de liberdade do pesquisador e quebra a contiguidade
de que HAC e bootstrap em blocos dependem.

Pontua-se o vetor **pós-guardrail** (I3): `scored_values` devolve `guardrail_values`;
nenhum caminho expõe `raw_values` para pontuação. `guardrail_applied_rate` é só
diagnóstico de cruzamento (doc de domínio §2.2).

A aresta de runtime `evaluation.domain → analytics_store.domain.value_objects.
quantile_forecast` é de DADOS (VO do fornecedor, sem tradução) e está declarada no
contrato `bc-independence` (ADR `0_0_0053` item 3; ADR `6_1_0002` item 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)

# Tolerância da simetria da grade: representação float64 (ADR 6.1.0002 item 2). Aceita
# (0.02, …, 0.98) apesar de `1 - 0.98 != 0.02` em float.
_SYMMETRY_TOLERANCE = 1e-12
_MEDIAN_LEVEL = 0.5


@dataclass(frozen=True)
class CoverageSeries:
    """Série alinhada de um modelo x horizonte sobre o `QuantileForecast` do 4.3.

    Campos:
        horizon: rótulo do horizonte (≥ 1) — um só por série.
        levels: grade comum de níveis, em (0, 1), estritamente crescente e simétrica.
        target_timestamps: timestamps ISO UTC do alvo, estritamente crescentes (formato
            único do silver; a comparação é de string).
        forecasts: um `QuantileForecast` por ponto, com `levels` iguais aos da série.
        realized: retorno realizado persistido por ponto, finito (lido, nunca
            recomputado).

    Raises:
        ValueError: em qualquer violação de C1/C2 (concept 6.1 §6), na construção.
    """

    horizon: int
    levels: tuple[float, ...]
    target_timestamps: tuple[str, ...]
    forecasts: tuple[QuantileForecast, ...]
    realized: tuple[float, ...]

    def __post_init__(self) -> None:
        """Valida as invariantes na ordem do technical 6.1 Task 02."""
        self._check_lengths()
        self._check_horizon()
        self._check_levels()
        self._check_timestamps()
        self._check_points()

    @property
    def n_points(self) -> int:
        """T — número de pontos alinhados da série."""
        return len(self.realized)

    @property
    def symmetric_pairs(self) -> tuple[tuple[float, float], ...]:
        """Pares `(τ_l, τ_u)` = `(levels[k], levels[K-1-k])` com τ_l < 0.5.

        O nível central 0.5 (K ímpar) não forma par. Os valores são os da grade da
        série (não `1 - τ_l` recalculado), de modo que o casamento por igualdade
        exata de float com um par da grade funciona.
        """
        return tuple(
            (self.levels[k_low], self.levels[k_high])
            for k_low, k_high in self.symmetric_pair_indices
        )

    @property
    def symmetric_pair_indices(self) -> tuple[tuple[int, int], ...]:
        """Colunas `(k, K-1-k)` de cada par, alinhadas 1:1 com `symmetric_pairs`.

        Fonte única da regra par → colunas do vetor pontuado: os serviços (IS, gate,
        cobertura) indexam `scored_values(i)` por aqui, sem remontar a regra.
        """
        size = len(self.levels)
        return tuple((k, size - 1 - k) for k in range(size) if self.levels[k] < _MEDIAN_LEVEL)

    @property
    def guardrail_applied_rate(self) -> float:
        """Fração de pontos cujo guardrail de monotonicidade reordenou a grade (§2.2)."""
        applied = sum(1 for forecast in self.forecasts if forecast.guardrail_applied)
        return applied / self.n_points

    def scored_values(self, index: int) -> tuple[float, ...]:
        """Vetor pontuado do ponto `index`: o `guardrail_values` (I3), nunca o bruto."""
        return self.forecasts[index].guardrail_values

    def _check_lengths(self) -> None:
        sizes = (len(self.target_timestamps), len(self.forecasts), len(self.realized))
        if len(set(sizes)) != 1:
            raise ValueError(
                "target_timestamps, forecasts and realized must align 1:1, got lengths "
                f"{sizes[0]}, {sizes[1]} and {sizes[2]}"
            )
        if sizes[0] == 0:
            raise ValueError("a CoverageSeries needs at least one point (T >= 1)")

    def _check_horizon(self) -> None:
        if self.horizon < 1:
            raise ValueError(f"horizon must be >= 1, got {self.horizon}")

    def _check_levels(self) -> None:
        levels = self.levels
        if any(not 0.0 < level < 1.0 for level in levels):
            raise ValueError(f"levels must all be in (0, 1), got {levels}")
        if any(b <= a for a, b in pairwise(levels)):
            raise ValueError(f"levels must be strictly increasing and unique, got {levels}")
        size = len(levels)
        for k in range(size):
            if abs(levels[k] + levels[size - 1 - k] - 1.0) > _SYMMETRY_TOLERANCE:
                raise ValueError(
                    f"levels must be symmetric (tau_k + tau_(K+1-k) == 1 within "
                    f"{_SYMMETRY_TOLERANCE}), got {levels}"
                )
        # Vazia ou só {0.5}: nenhum par simétrico — IS, PICP e nominal indefinidos.
        if not levels or levels[0] >= _MEDIAN_LEVEL:
            raise ValueError(
                f"levels must hold at least one symmetric pair (tau_1 < 0.5), got {levels}"
            )

    def _check_timestamps(self) -> None:
        for index, (previous, current) in enumerate(pairwise(self.target_timestamps), 1):
            if current <= previous:
                raise ValueError(
                    "target_timestamps must be strictly increasing (unique and ordered): "
                    f"point {index} has {current!r} after {previous!r}"
                )

    def _check_points(self) -> None:
        for index, (forecast, realized) in enumerate(
            zip(self.forecasts, self.realized, strict=True)
        ):
            if forecast.levels != self.levels:
                raise ValueError(
                    f"point {index}: forecast levels {forecast.levels} differ from the "
                    f"series levels {self.levels}"
                )
            values = forecast.guardrail_values
            # Alinhamento valor↔nível: o VO do 4.3 construído direto não o garante.
            if len(values) != len(self.levels):
                raise ValueError(
                    f"point {index}: {len(values)} guardrail values for {len(self.levels)} levels"
                )
            if any(not is_finite_number(value) for value in values):
                raise ValueError(
                    f"point {index}: guardrail values must all be finite, got {values}"
                )
            if any(b < a for a, b in pairwise(values)):
                raise ValueError(
                    f"point {index}: guardrail values must be non-decreasing, got {values}"
                )
            if not is_finite_number(realized):
                raise ValueError(f"point {index}: realized value must be finite, got {realized}")


def pair_miscoverage(lower_level: float) -> float:
    """Miscobertura do par simétrico (τ_l, 1 - τ_l): alpha = 2·τ_l — fórmula única (I5).

    A forma `1 - (τ_u - τ_l)` é igual em aritmética exata mas não em float64 (daria
    0.10000000000000009 em (0.05, 0.95)); todo serviço usa esta função.
    """
    return 2.0 * lower_level


def pair_nominal(lower_level: float) -> float:
    """Cobertura nominal do par simétrico: 1 - 2·τ_l = 1 - `pair_miscoverage` (I7)."""
    return 1.0 - pair_miscoverage(lower_level)


def is_at_or_below(realized: float, quantile: float) -> bool:
    """Indicador 1{y ≤ q̂} — regra única de empate FA7 da cauda (doc §4.5; concept 6.3 I3).

    Empate `y == q̂` **conta** como "abaixo ou no quantil". Consumidores: o
    `CoverageMetrics` (ĉ(τ)) e o `HitSequences` (violação da cauda inferior); a
    violação da cauda superior é `not is_at_or_below(y, q̂_τ)` — no empate, não é
    violação. Sem validação própria: recebe valores já validados pela
    `CoverageSeries` (C2 da 6.1).
    """
    return realized <= quantile


def is_inside_closed(realized: float, lower: float, upper: float) -> bool:
    """Indicador [l ≤ y ≤ u] do intervalo **fechado** — regra única FA7 (doc §4.5; I3).

    As duas bordas contam como dentro (`y == l` ou `y == u` não é violação).
    Consumidores: o `CoverageMetrics` (PICP) e o `HitSequences` (violação do intervalo
    = `not is_inside_closed(...)`). Sem validação própria (valores já validados pela
    `CoverageSeries`).
    """
    return lower <= realized <= upper
