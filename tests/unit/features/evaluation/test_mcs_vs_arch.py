"""Unit test do `ModelConfidenceSet` ('R') e da regra de bloco (A9, A10, C6, C7, C8, I1, I9).

Desvio de caminho declarado (concept 6.2 D7; ADR 6.2.0004 item 6): o nome do arquivo é o
do roadmap (`test_mcs_vs_arch.py`), mas o conteúdo é **só analítico** — índices de
bootstrap montados à mão (linhas identidade, reamostras fixas, conjuntos fechados por
troca de posições) ou por `random.Random(<seed>)` da stdlib, com
`generator = "manual (teste)"`, e perdas inteiras/diádicas. A paridade com
`arch.MCS(method="R")` (mesma ordem de eliminação, p-valores idênticos) vive na
integração da Task 12 (`tests/integration/features/evaluation/test_mcs_vs_arch.py`) —
unit não importa biblioteca. A pertença na fronteira p̂ = alpha, o empate exato e o caso
"todos incluídos" só existem aqui (o `arch` usa ">" na pertença).
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import random
from collections.abc import Callable

import pytest

from financial_forecasting.features.evaluation.domain.services.model_confidence_set import (
    MIN_MCS_REPS,
    McsElimination,
    McsReport,
    ModelConfidenceSet,
)
from financial_forecasting.features.evaluation.domain.value_objects.bootstrap_indices import (
    BootstrapIndices,
    BootstrapScheme,
)
from financial_forecasting.features.evaluation.domain.value_objects.paired_loss_series import (
    PairedLossSeries,
)

_GENERATOR = "manual (teste)"
_ALPHA = 0.10
_REPS = MIN_MCS_REPS


def _timestamps(n_points: int) -> tuple[str, ...]:
    return tuple(f"2024-04-{day:02d}T00:00:00+00:00" for day in range(1, n_points + 1))


def _series(
    models: tuple[str, ...], losses: tuple[tuple[float, ...], ...], horizon: int = 1
) -> PairedLossSeries:
    return PairedLossSeries(
        horizon=horizon,
        models=models,
        target_timestamps=_timestamps(len(losses[0])),
        losses=losses,
    )


def _indices(
    rows: tuple[tuple[int, ...], ...],
    *,
    scheme: BootstrapScheme = BootstrapScheme.STATIONARY,
    block_size: int = 1,
    seed: int = 11,
) -> BootstrapIndices:
    return BootstrapIndices(
        scheme=scheme,
        block_size=block_size,
        seed=seed,
        n_obs=len(rows[0]),
        generator=_GENERATOR,
        indices=rows,
    )


def _iid_rows(n_obs: int, reps: int, seed: int) -> tuple[tuple[int, ...], ...]:
    rng = random.Random(seed)
    return tuple(tuple(rng.randrange(n_obs) for _ in range(n_obs)) for _ in range(reps))


# Dominado: C = A + 2 + eps, eps em {0, 1} não constante (senão o diferencial A-C seria
# constante e o MCS ergueria).
_A = (1.0, 3.0, 2.0, 4.0, 1.0, 3.0, 2.0, 4.0)
_B = (2.0, 2.0, 3.0, 3.0, 2.0, 2.0, 3.0, 3.0)
_EPS = (0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0)
_C = tuple(a + 2.0 + e for a, e in zip(_A, _EPS, strict=True))


def _dominated_report(horizon: int = 1) -> McsReport:
    series = _series(("A", "B", "C"), (_A, _B, _C), horizon=horizon)
    bootstrap = _indices(_iid_rows(len(_A), _REPS, seed=3), block_size=2, seed=3)
    return ModelConfidenceSet.evaluate(series, bootstrap=bootstrap, alpha=_ALPHA)


# Três modelos de perdas diádicas sem diferença sistemática (random.Random(5)): a
# eliminação sai fora da ordem dos modelos (m2, m1, m3), o p do 2º passo é menor que o do
# 1º (o máximo acumulado age) e todos ficam no MCS a alpha = 0,10.
_NOISY_SEED = 5
_NOISY_POINTS = 20


def _noisy_series() -> PairedLossSeries:
    rng = random.Random(_NOISY_SEED)
    columns = tuple(
        tuple(round(rng.uniform(0.0, 4.0) * 8) / 8 for _ in range(_NOISY_POINTS)) for _ in range(3)
    )
    return _series(("m1", "m2", "m3"), columns)


def _noisy_bootstrap() -> BootstrapIndices:
    return _indices(_iid_rows(_NOISY_POINTS, _REPS, _NOISY_SEED), seed=_NOISY_SEED)


def _noisy_report() -> McsReport:
    return ModelConfidenceSet.evaluate(_noisy_series(), bootstrap=_noisy_bootstrap(), alpha=_ALPHA)


@pytest.mark.unit
def test_mcs_dominated_first() -> None:
    report = _dominated_report()
    assert report.eliminations[0].model == "C"
    assert report.eliminations[-1].mcs_p_value == 1.0


@pytest.mark.unit
def test_mcs_cumulative_max() -> None:
    report = _noisy_report()
    steps = [entry.step_p_value for entry in report.eliminations]
    assert steps[1] < steps[0]  # o 2º passo é menos significativo que o 1º...
    mcs = [entry.mcs_p_value for entry in report.eliminations]
    assert mcs == [steps[0], steps[0], 1.0]  # ... e herda o p do 1º (Def. 4)
    assert steps[-1] == 1.0


@pytest.mark.unit
def test_mcs_boundary_included_at_alpha() -> None:
    """900 linhas identidade (t* = 0) + 100 da reamostra (3, 3, 3, 3) → p do passo = 0,1."""
    series = _series(("A", "B"), ((1.0, 1.0, 1.0, 5.0), (1.0, 1.0, 1.0, 1.0)))
    rows = ((0, 1, 2, 3),) * 900 + ((3, 3, 3, 3),) * 100
    bootstrap = _indices(rows)
    at_alpha = ModelConfidenceSet.evaluate(series, bootstrap=bootstrap, alpha=0.1)
    assert at_alpha.eliminations[0] == McsElimination(model="A", step_p_value=0.1, mcs_p_value=0.1)
    assert at_alpha.included == ("A", "B")  # p̂ = alpha pertence (p̂ >= alpha)
    above = ModelConfidenceSet.evaluate(series, bootstrap=bootstrap, alpha=0.101)
    assert above.included == ("B",)


@pytest.mark.unit
def test_mcs_boundary_included_counts_only_strict_exceedance() -> None:
    """Réplica com T*_R = T_R exato não conta (p = #{T_R < T*_R}/B, convenção do `arch`).

    d = (0, 0, 0, 4), d̄ = 1: (3, 3, 0, 0) dá d̄* = 2, logo d̄* - d̄ = d̄ e t* = t exatos.
    """
    series = _series(("A", "B"), ((1.0, 1.0, 1.0, 5.0), (1.0, 1.0, 1.0, 1.0)))
    rows = ((0, 1, 2, 3),) * 850 + ((3, 3, 3, 3),) * 100 + ((3, 3, 0, 0),) * 50
    report = ModelConfidenceSet.evaluate(series, bootstrap=_indices(rows), alpha=_ALPHA)
    assert report.eliminations[0].step_p_value == 0.1  # noqa: PLR2004 — 100/1000, não 150/1000


@pytest.mark.unit
def test_mcs_variance_recentred_by_hand() -> None:
    """var̂_ij usa d*_ij,b - d̄_ij (recentrado), não o 2º momento bruto de d* (I8).

    A = (1, 1, 1, 5), B = (1, 1, 1, 1), C = (0, 0, 1, 2); 900 linhas identidade, 50 da
    reamostra (3, 3, 3, 3) e 50 de (0, 0, 0, 0). d̄: AB = 1, AC = 1,25, BC = 0,25.
    d* - d̄ (identidade / (3,...) / (0,...)): AB 0 / 3 / -1; AC 0 / 1,75 / -0,25;
    BC 0 / -1,25 / 0,75 → var̂ = 50·Σ²/1000: AB 0,5; AC 0,15625; BC 0,10625.
    t: AB √2 ≈ 1,414; AC 1,25/√0,15625 ≈ 3,162 (máx. → sai A); BC ≈ 0,767.
    Passo 1: T*_R da (3,...) = 1,75/√0,15625 ≈ 4,427 > 3,162 (conta); da (0,...) =
    0,75/√0,10625 ≈ 2,301 < 3,162 (não conta) → p = 50/1000. Passo 2 (B, C): T_R = t_BC
    ≈ 0,767, as duas reamostras passam (3,83 e 2,30) → p = 100/1000.
    Com o 2º momento bruto (var̂ AB 1,7; AC 1,90625; BC 0,15625) as duas reamostras
    passariam já no passo 1 (p = 0,1).
    """
    series = _series(
        ("A", "B", "C"), ((1.0, 1.0, 1.0, 5.0), (1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 1.0, 2.0))
    )
    rows = ((0, 1, 2, 3),) * 900 + ((3, 3, 3, 3),) * 50 + ((0, 0, 0, 0),) * 50
    report = ModelConfidenceSet.evaluate(series, bootstrap=_indices(rows), alpha=_ALPHA)
    assert report.eliminations == (
        McsElimination(model="A", step_p_value=0.05, mcs_p_value=0.05),
        McsElimination(model="B", step_p_value=0.1, mcs_p_value=0.1),
        McsElimination(model="C", step_p_value=1.0, mcs_p_value=1.0),
    )


@pytest.mark.unit
def test_mcs_exact_tie_one_model() -> None:
    """t_AC = t_BC exatos: B é A com as posições 0 e 1 trocadas, C[0] = C[1] e o conjunto
    de linhas é fechado pela troca 0 ↔ 1. A 1ª eliminação é só A (1º modelo-linha)."""
    a = (3.0, 5.0, 4.0, 6.0, 3.0, 5.0)
    b = (5.0, 3.0, 4.0, 6.0, 3.0, 5.0)
    c = (1.0, 1.0, 2.0, 1.0, 2.0, 1.0)
    half = _iid_rows(len(a), _REPS // 2, seed=17)
    swap = {0: 1, 1: 0}
    rows = half + tuple(tuple(swap.get(i, i) for i in row) for row in half)
    report = ModelConfidenceSet.evaluate(
        _series(("A", "B", "C"), (a, b, c)), bootstrap=_indices(rows), alpha=_ALPHA
    )
    assert [entry.model for entry in report.eliminations] == ["A", "B", "C"]


@pytest.mark.unit
def test_mcs_all_included_is_not_an_error() -> None:
    report = _noisy_report()
    assert report.included == ("m1", "m2", "m3")


@pytest.mark.unit
def test_mcs_copies_bootstrap() -> None:
    bootstrap = _noisy_bootstrap()
    report = ModelConfidenceSet.evaluate(_noisy_series(), bootstrap=bootstrap, alpha=_ALPHA)
    assert (report.scheme, report.block_size, report.reps, report.seed, report.generator) == (
        bootstrap.scheme,
        bootstrap.block_size,
        bootstrap.reps,
        bootstrap.seed,
        bootstrap.generator,
    )
    assert (report.statistic, report.alpha) == ("R", _ALPHA)


@pytest.mark.unit
def test_mcs_elimination_names() -> None:
    report = _noisy_report()
    names = [entry.model for entry in report.eliminations]
    assert len(names) == 3  # noqa: PLR2004 — k entradas
    assert set(names) == {"m1", "m2", "m3"}


@pytest.mark.unit
def test_mcs_included_order_follows_series() -> None:
    report = _noisy_report()
    assert [entry.model for entry in report.eliminations] == ["m2", "m1", "m3"]
    assert report.included == ("m1", "m2", "m3")


@pytest.mark.unit
def test_mcs_horizon_propagated() -> None:
    report = _dominated_report(horizon=2)
    assert (report.horizon, report.n_points) == (2, len(_A))


@pytest.mark.unit
def test_mcs_alpha_signature() -> None:
    parameter = inspect.signature(ModelConfidenceSet.evaluate).parameters["alpha"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def _c6_cases() -> list[object]:
    series = _series(("A", "B", "C"), (_A, _B, _C))
    good = _indices(_iid_rows(len(_A), _REPS, seed=3))
    return [
        pytest.param(series, good, 0.0, "alpha must be", id="alpha-zero"),
        pytest.param(series, good, 1.0, "alpha must be", id="alpha-one"),
        pytest.param(series, good, math.nan, "alpha must be", id="alpha-nan"),
        pytest.param(
            series,
            _indices(_iid_rows(len(_A), _REPS - 1, seed=3)),
            _ALPHA,
            "reps >= 1000",
            id="reps-999",
        ),
        pytest.param(
            series, _indices(_iid_rows(len(_A) + 1, _REPS, seed=3)), _ALPHA, "n_obs", id="n-obs"
        ),
        pytest.param(
            _series(("A", "B", "C"), (_A, tuple(a + 1.0 for a in _A), _C)),
            good,
            _ALPHA,
            "constant loss differential",
            id="constant-pair",
        ),
        pytest.param(
            series,
            _indices((tuple(range(len(_A))),) * _REPS),
            _ALPHA,
            "variance",
            id="identity-rows",
        ),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(("series", "bootstrap", "alpha", "message"), _c6_cases())
def test_mcs_c6_invalid_raises(
    series: PairedLossSeries, bootstrap: BootstrapIndices, alpha: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ModelConfidenceSet.evaluate(series, bootstrap=bootstrap, alpha=alpha)


@pytest.mark.unit
def test_mcs_c6_invalid_moving_block_full_length_barred_by_indices() -> None:
    with pytest.raises(ValueError, match="block_size < n_obs"):
        _indices(
            (tuple(range(len(_A))),) * _REPS,
            scheme=BootstrapScheme.MOVING_BLOCK,
            block_size=len(_A),
        )


def _elims(*entries: tuple[str, float, float]) -> tuple[McsElimination, ...]:
    return tuple(McsElimination(model=m, step_p_value=s, mcs_p_value=c) for m, s, c in entries)


_VALID_REPORT = McsReport(
    horizon=1,
    n_points=8,
    alpha=_ALPHA,
    statistic="R",
    scheme=BootstrapScheme.STATIONARY,
    block_size=2,
    reps=_REPS,
    seed=3,
    generator=_GENERATOR,
    eliminations=_elims(("C", 0.25, 0.25), ("A", 0.125, 0.25), ("B", 1.0, 1.0)),
    included=("A", "B", "C"),
)

_INCOHERENT: list[tuple[str, dict[str, object], str]] = [
    ("statistic", {"statistic": "max"}, "statistic"),
    ("alpha", {"alpha": 1.0}, "alpha must be"),
    ("horizon", {"horizon": 0}, "horizon must be"),
    ("n-points-le-horizon", {"horizon": 8}, "T > h"),
    ("block-size", {"block_size": 0}, "block_size must be"),
    ("seed", {"seed": -1}, "seed must be"),
    ("scheme", {"scheme": "stationary"}, "BootstrapScheme"),
    ("reps", {"reps": 999}, "reps must be >= 1000"),
    ("generator", {"generator": ""}, "generator"),
    ("one-elimination", {"eliminations": _elims(("B", 1.0, 1.0)), "included": ("B",)}, "k >= 2"),
    (
        "eliminations-list",
        {"eliminations": list(_VALID_REPORT.eliminations)},
        "tuple",
    ),
    (
        "empty-name",
        {"eliminations": _elims(("", 0.25, 0.25), ("B", 1.0, 1.0)), "included": ("", "B")},
        "non-empty",
    ),
    (
        "repeated-name",
        {"eliminations": _elims(("B", 0.25, 0.25), ("B", 1.0, 1.0)), "included": ("B",)},
        "unique",
    ),
    (
        "step-negative-stepneg",
        {"eliminations": _elims(("A", -0.25, -0.25), ("B", 1.0, 1.0))},
        r"\[0, 1\]",
    ),
    (
        "step-bool-stepbool",
        {"eliminations": _elims(("A", True, True), ("B", 1.0, 1.0))},
        r"\[0, 1\]",
    ),
    (
        "step-out-of-range",
        {"eliminations": _elims(("A", 1.5, 1.5), ("B", 1.0, 1.5))},
        r"\[0, 1\]",
    ),
    (
        "not-cumulative-max",
        {"eliminations": _elims(("C", 0.25, 0.25), ("A", 0.125, 0.125), ("B", 1.0, 1.0))},
        "cumulative max",
    ),
    (
        "last-not-one",
        {"eliminations": _elims(("A", 0.25, 0.25), ("B", 0.5, 0.5)), "included": ("A", "B")},
        "p = 1.0",
    ),
    ("included-missing", {"included": ("A", "B")}, "included must be"),
    ("included-extra", {"alpha": 0.5, "included": ("A", "B", "C")}, "included must be"),
    ("included-repeated", {"included": ("A", "B", "C", "C")}, "without repeats"),
    ("included-list", {"included": ["A", "B", "C"]}, "without repeats"),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "message"), [pytest.param(c, m, id=i) for i, c, m in _INCOHERENT]
)
def test_mcs_report_incoherent_raises(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dataclasses.replace(_VALID_REPORT, **changes)  # type: ignore[arg-type]


def _pair_series(horizon: int) -> PairedLossSeries:
    return _series(("A", "B", "C"), (_A, _B, _C), horizon=horizon)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("horizon", "estimates", "expected"),
    [
        pytest.param(7, (9.2, 3.0, 1.5), 10, id="h7-max-9.2"),
        pytest.param(7, (3.4, 0.5, 2.0), 7, id="h7-max-3.4"),
        pytest.param(1, (0.0, 0.0, 0.0), 1, id="h1-zero"),
        pytest.param(2, (3.0, 1.0, 1.0), 3, id="integer-estimate"),
    ],
)
def test_block_length_ceiling(horizon: int, estimates: tuple[float, ...], expected: int) -> None:
    series = _pair_series(horizon)
    block = ModelConfidenceSet.block_length(
        series, block_estimates=dict(zip(series.model_pairs(), estimates, strict=True))
    )
    assert block == expected
    assert type(block) is int


def _c7_cases() -> list[object]:
    pairs = (("A", "B"), ("A", "C"), ("B", "C"))
    good = dict.fromkeys(pairs, 1.0)
    return [
        pytest.param({("A", "B"): 1.0, ("A", "C"): 1.0}, "misses", id="missing-pair"),
        pytest.param({**good, ("A", "Z"): 1.0}, "unknown", id="unknown-pair"),
        pytest.param(
            {("B", "A"): 1.0, ("A", "C"): 1.0, ("B", "C"): 1.0}, "unknown", id="reversed-pair"
        ),
        pytest.param({**good, ("A", "C"): -0.1}, "finite number >= 0", id="negative"),
        pytest.param({**good, ("A", "C"): math.nan}, "finite number >= 0", id="nan"),
        pytest.param({**good, ("A", "C"): math.inf}, "finite number >= 0", id="inf"),
        pytest.param({**good, ("A", "C"): True}, "finite number >= 0", id="bool"),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(("estimates", "message"), _c7_cases())
def test_block_length_c7_invalid_raises(
    estimates: dict[tuple[str, str], float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ModelConfidenceSet.block_length(_pair_series(1), block_estimates=estimates)


_REPORT_BUILDERS: list[Callable[[], McsReport]] = [_dominated_report, _noisy_report]


@pytest.mark.unit
@pytest.mark.parametrize("build", _REPORT_BUILDERS)
def test_mcs_report_from_evaluate_is_coherent(build: Callable[[], McsReport]) -> None:
    """O relatório do `evaluate` passa pelo próprio I9 (reconstrução sem erro)."""
    report = build()
    assert dataclasses.replace(report) == report
