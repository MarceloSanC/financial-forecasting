"""Unit test do p-valor Monte Carlo do `ChristoffersenTest` (ADR 6.3.0006).

Prova (concept 6.3 A8, I7, I8, C4, C5, C6, C9):

- o kernel `mc_p_value` (desempate de Dufour 2006 Eq. 2.30) numa fixture à mão com
  empates;
- determinismo e uma regressão congelada (guarda a ordem de consumo do RNG);
- a referência de LR_ind/LR_cc condicionada ao evento de aplicabilidade, por um
  **replay independente** escrito neste teste (e diferente da não condicionada);
- teto de 100·N, "só LR_uc" e "sem LR_uc";
- envelopes binomiais exatos sem e com lacunas;
- C4/C5 e a coerência do `MonteCarloPValues` (C9).

Custos: N ≤ 2 000 e T ≤ 40 (technical §5).
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import random
from collections.abc import Callable, Sequence

import pytest

from financial_forecasting.features.evaluation.domain.services.christoffersen_test import (
    ChristoffersenTest,
    MonteCarloPValues,
    MonteCarloStatus,
    christoffersen_statistics,
    mc_p_value,
)
from financial_forecasting.features.evaluation.domain.services.kupiec_pof import kupiec_pof
from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import (
    HitSequence,
)

HitSequenceFactory = Callable[..., HitSequence]

T, F = True, False
_P = 0.05
_LEVELS = (_P,)
# Fixture da referência condicionada e da regressão: T = 40, 3 violações (duas
# seguidas), min_violations = 3, observado APPLICABLE (transições (34, 2, 2, 1)).
_COND_POSITIONS = (10, 11, 25)
_COND = tuple(i in _COND_POSITIONS for i in range(40))
_COND_MIN = 3
_COND_DRAWS = 199
_COND_SEED = 1
# Regressão congelada: (sequência _COND, seed = 20260928, N = 199) — valores medidos na
# execução da Task 08; guardam a ordem de consumo do RNG (ADR 6.3.0006 item 5).
_REGRESSION_SEED = 20260928
_REGRESSION = {"p_uc": 0.655, "p_ind": 0.095, "p_cc": 0.435, "attempts": 581}
# Teto: T = 20, 10 violações alternadas (matriz não degenerada), p = 0.01.
_CAP_SEQUENCE = (T, F) * 10
_CAP_RATE = 0.01
_CAP_MIN = 10
_CAP_DRAWS = 5
_H7 = 7


def _cond_sequence(make_hit_sequence: HitSequenceFactory) -> HitSequence:
    return make_hit_sequence(_COND, levels=_LEVELS)


# --- I7 — kernel de Dufour ------------------------------------------------------------------


@pytest.mark.unit
def test_dufour_ties_hand_fixture() -> None:
    """A8: S_0 = 2, S = [1, 2, 2, 3], U = [0.3, 0.9, 0.1, 0.5], U_0 = 0.5 →
    G̃_N = 1 - 3/4 + 1/4 = 0.5 e p̃ = 0.6; o não-aleatorizado p̂ = (N·Ĝ_N + 1)/(N + 1)
    com Ĝ_N = #(S_i ≥ S_0)/N = 3/4 dá 0.8 ≥ p̃ (Dufour Eq. 2.33)."""
    simulated, uniforms = [1.0, 2.0, 2.0, 3.0], [0.3, 0.9, 0.1, 0.5]

    observed = 2.0
    p_tilde = mc_p_value(
        observed=observed, simulated=simulated, uniforms=uniforms, observed_uniform=0.5
    )

    n = len(simulated)
    p_hat = (n * (sum(1 for s in simulated if s >= observed) / n) + 1) / (n + 1)
    assert p_tilde == 0.6  # noqa: PLR2004
    assert p_hat == 0.8  # noqa: PLR2004
    assert p_hat >= p_tilde


@pytest.mark.unit
@pytest.mark.parametrize(
    ("simulated", "uniforms"), [([1.0, 2.0], [0.5]), ([], [])], ids=["sizes-differ", "empty"]
)
def test_dufour_ties_kernel_rejects_bad_sizes(
    simulated: list[float], uniforms: list[float]
) -> None:
    with pytest.raises(ValueError, match="must have the same length >= 1"):
        mc_p_value(observed=1.0, simulated=simulated, uniforms=uniforms, observed_uniform=0.5)


# --- Determinismo e regressão ---------------------------------------------------------------


@pytest.mark.unit
def test_mc_determinism_same_inputs_same_result(make_hit_sequence: HitSequenceFactory) -> None:
    sequence = _cond_sequence(make_hit_sequence)
    kwargs = {"min_violations": _COND_MIN, "draws": _COND_DRAWS, "seed": _COND_SEED}

    first = ChristoffersenTest.monte_carlo_p_values(sequence, **kwargs)
    second = ChristoffersenTest.monte_carlo_p_values(sequence, **kwargs)

    assert first == second


@pytest.mark.unit
def test_mc_regression_frozen_values(make_hit_sequence: HitSequenceFactory) -> None:
    """A8: valores literais congelados — qualquer mudança na ordem do RNG os altera."""
    result = ChristoffersenTest.monte_carlo_p_values(
        _cond_sequence(make_hit_sequence),
        min_violations=_COND_MIN,
        draws=_COND_DRAWS,
        seed=_REGRESSION_SEED,
    )

    assert result.p_uc == _REGRESSION["p_uc"]
    assert result.p_ind == _REGRESSION["p_ind"]
    assert result.p_cc == _REGRESSION["p_cc"]
    assert result.attempts == _REGRESSION["attempts"]


# --- ADR 6.3.0006 item 3 — referência condicionada, replay independente ---------------------


def _replay(
    violations: Sequence[bool | None], *, rate: float, min_violations: int, draws: int, seed: int
) -> dict[str, float | int]:
    """Reimplementação NESTE teste da ordem do ADR 6.3.0006 item 5 e das referências."""
    observed = christoffersen_statistics(
        violations=violations, violation_rate=rate, min_violations=min_violations
    )
    assert observed.lr_uc is not None and observed.lr_ind is not None
    assert observed.lr_cc is not None
    rng = random.Random(seed)
    u0 = rng.random()
    uc: list[tuple[float, float]] = []
    ind: list[tuple[float, float, float]] = []
    unconditioned: list[tuple[float, float]] = []
    attempts = 0
    while len(uc) < draws or len(ind) < draws:
        drawn = [None if v is None else rng.random() < rate for v in violations]
        u = rng.random()
        attempts += 1
        stats = christoffersen_statistics(
            violations=drawn, violation_rate=rate, min_violations=min_violations
        )
        if len(uc) < draws:
            assert stats.lr_uc is not None
            uc.append((stats.lr_uc, u))
            # Alternativa D do ADR: inaplicável contado como LR_ind = 0, sem redraw.
            unconditioned.append((stats.lr_ind if stats.lr_ind is not None else 0.0, u))
        if len(ind) < draws and stats.lr_ind is not None and stats.lr_cc is not None:
            ind.append((stats.lr_ind, stats.lr_cc, u))

    def p_of(obs: float, pairs: Sequence[tuple[float, float]]) -> float:
        return mc_p_value(
            observed=obs,
            simulated=[s for s, _ in pairs],
            uniforms=[u for _, u in pairs],
            observed_uniform=u0,
        )

    return {
        "p_uc": p_of(observed.lr_uc, uc),
        "p_ind": p_of(observed.lr_ind, [(a, u) for a, _, u in ind]),
        "p_cc": p_of(observed.lr_cc, [(c, u) for _, c, u in ind]),
        "p_ind_unconditioned": p_of(observed.lr_ind, unconditioned),
        "attempts": attempts,
    }


@pytest.mark.unit
def test_conditioned_reference_matches_independent_replay(
    make_hit_sequence: HitSequenceFactory,
) -> None:
    """A8/I7 (Checkpoint B T1): p_uc, p_ind, p_cc e attempts == replay independente;
    a referência não condicionada daria outro p_ind; houve redraw (attempts > N)."""
    sequence = _cond_sequence(make_hit_sequence)

    result = ChristoffersenTest.monte_carlo_p_values(
        sequence, min_violations=_COND_MIN, draws=_COND_DRAWS, seed=_COND_SEED
    )
    replay = _replay(_COND, rate=_P, min_violations=_COND_MIN, draws=_COND_DRAWS, seed=_COND_SEED)

    assert result.ind_status is MonteCarloStatus.APPLICABLE
    assert result.p_uc == replay["p_uc"]
    assert result.p_ind == replay["p_ind"]
    assert result.p_cc == replay["p_cc"]
    assert result.attempts == replay["attempts"]
    assert result.attempts > _COND_DRAWS
    assert replay["p_ind_unconditioned"] != result.p_ind


# --- Teto, "só LR_uc", "sem LR_uc" ----------------------------------------------------------


@pytest.mark.unit
def test_mc_cap_reached_keeps_p_uc(make_hit_sequence: HitSequenceFactory) -> None:
    """A8: T = 20, 10 violações, p = 0.01, mínimo 10, N = 5 — nenhum sorteio aplicável
    em 100·N tentativas: MC_CAP_REACHED, p_ind/p_cc None, p_uc presente, attempts = 500."""
    sequence = make_hit_sequence(_CAP_SEQUENCE, levels=(_CAP_RATE,))

    result = ChristoffersenTest.monte_carlo_p_values(
        sequence, min_violations=_CAP_MIN, draws=_CAP_DRAWS, seed=1
    )

    assert result.ind_status is MonteCarloStatus.MC_CAP_REACHED
    assert (result.p_ind, result.p_cc) == (None, None)
    assert result.p_uc is not None
    assert result.uc_status is MonteCarloStatus.APPLICABLE
    assert result.attempts == 100 * _CAP_DRAWS


@pytest.mark.unit
def test_uc_only_when_independence_not_applicable(make_hit_sequence: HitSequenceFactory) -> None:
    """A8 (Checkpoint B T9): `[F]*10`, mínimo 1 — LR_uc aplicável, LR_ind não; sem redraw."""
    result = ChristoffersenTest.monte_carlo_p_values(
        make_hit_sequence((F,) * 10), min_violations=1, draws=50, seed=3
    )

    assert result.uc_status is MonteCarloStatus.APPLICABLE
    assert result.p_uc is not None
    assert result.ind_status is MonteCarloStatus.NOT_APPLICABLE
    assert (result.p_ind, result.p_cc) == (None, None)
    assert result.attempts == 50  # noqa: PLR2004


@pytest.mark.unit
def test_uc_not_applicable_draws_nothing(make_hit_sequence: HitSequenceFactory) -> None:
    """A8/C6: `[T]` (nenhum par) → nada é sorteado: attempts = 0 e tudo None."""
    result = ChristoffersenTest.monte_carlo_p_values(
        make_hit_sequence((T,)), min_violations=0, draws=10, seed=3
    )

    assert result.attempts == 0
    assert (result.p_uc, result.p_ind, result.p_cc) == (None, None, None)
    assert result.uc_status is MonteCarloStatus.NOT_APPLICABLE
    assert result.ind_status is MonteCarloStatus.NOT_APPLICABLE


@pytest.mark.unit
def test_mc_carries_identity_and_parameters(make_hit_sequence: HitSequenceFactory) -> None:
    """A8/I1/D8: o resultado carrega min_violations, draws, seed e a identidade."""
    sequence = make_hit_sequence(_COND, levels=_LEVELS, tolerance=0.001)

    result = ChristoffersenTest.monte_carlo_p_values(
        sequence, min_violations=_COND_MIN, draws=20, seed=11
    )

    assert (result.min_violations, result.draws, result.seed) == (_COND_MIN, 20, 11)
    assert (result.horizon, result.kind, result.levels) == (
        sequence.horizon,
        sequence.kind,
        sequence.levels,
    )
    assert (result.tolerance, result.includes_degenerate) == (
        sequence.tolerance,
        sequence.includes_degenerate,
    )


# --- Envelopes binomiais exatos -------------------------------------------------------------


def _envelope(observed_lr_uc: float, n_pairs: int, rate: float, draws: int) -> tuple[float, float]:
    """[P(S > s0) - ε, P(S ≥ s0) + ε], com S = LR_uc(k) e k ~ Binomial(n_pairs, p)."""
    above = at_or_above = 0.0
    for k in range(n_pairs + 1):
        mass = math.comb(n_pairs, k) * rate**k * (1 - rate) ** (n_pairs - k)
        statistic = kupiec_pof(violations=k, observations=n_pairs, violation_rate=rate)
        if statistic > observed_lr_uc:
            above += mass
        if statistic >= observed_lr_uc:
            at_or_above += mass
    variance = max(above * (1 - above), at_or_above * (1 - at_or_above))
    epsilon = 4 * math.sqrt(variance / draws) + 1 / (draws + 1)
    return above - epsilon, at_or_above + epsilon


@pytest.mark.unit
def test_iid_envelope_without_gaps(make_hit_sequence: HitSequenceFactory) -> None:
    """A8: T = 30, p = 0.1, N = 2 000 — p̃ de LR_uc dentro do envelope binomial exato
    (n_1 puro ~ Binomial(29, p)); ε do ADR 6.3.0006 item 4."""
    rate, draws = 0.1, 2000
    violations = tuple(i in (3, 4, 9, 15, 16, 22) for i in range(30))
    sequence = make_hit_sequence(violations, levels=(rate,))
    observed = christoffersen_statistics(
        violations=violations, violation_rate=rate, min_violations=0
    )
    assert observed.lr_uc is not None

    result = ChristoffersenTest.monte_carlo_p_values(
        sequence, min_violations=0, draws=draws, seed=5
    )

    low, high = _envelope(observed.lr_uc, 29, rate, draws)
    assert result.p_uc is not None
    assert low <= result.p_uc <= high


@pytest.mark.unit
def test_gaps_envelope_with_masked_positions(make_hit_sequence: HitSequenceFactory) -> None:
    """A8 (Checkpoint B T4): 34 posições com 4 None espalhados — n_1 puro ~
    Binomial(nº de pares observados, p) e as mesmas lacunas nos sorteios."""
    rate, draws = 0.1, 2000
    gaps = {5, 12, 13, 27}
    marks = {2, 3, 8, 17, 18, 30}
    violations = tuple(None if i in gaps else i in marks for i in range(34))
    sequence = make_hit_sequence(violations, levels=(rate,))
    observed = christoffersen_statistics(
        violations=violations, violation_rate=rate, min_violations=0
    )
    n_pairs = sum(observed.transitions)
    # 7 pares tocam as 4 lacunas (12 e 13 adjacentes)
    assert n_pairs == 34 - 1 - 7
    assert observed.lr_uc is not None

    result = ChristoffersenTest.monte_carlo_p_values(
        sequence, min_violations=0, draws=draws, seed=6
    )

    low, high = _envelope(observed.lr_uc, n_pairs, rate, draws)
    assert result.p_uc is not None
    assert low <= result.p_uc <= high


# --- C5 / C4 --------------------------------------------------------------------------------


@pytest.mark.unit
def test_dgt_subseries_raises(make_hit_sequence: HitSequenceFactory) -> None:
    """A8/C5: sub-série DGT (h = 7) ergue com a mensagem de sub-série."""
    sub = make_hit_sequence(_COND, horizon=_H7).dgt_partition()[0]

    with pytest.raises(ValueError, match="not defined on a DGT sub-series"):
        ChristoffersenTest.monte_carlo_p_values(sub, min_violations=0, draws=10, seed=1)


@pytest.mark.unit
def test_horizon_raises_outside_dgt(make_hit_sequence: HitSequenceFactory) -> None:
    """A8/C5/I8: h = 7 fora de sub-série ergue com a mensagem de horizonte."""
    sequence = make_hit_sequence(_COND, horizon=_H7)

    with pytest.raises(ValueError, match="require horizon == 1"):
        ChristoffersenTest.monte_carlo_p_values(sequence, min_violations=0, draws=10, seed=1)


@pytest.mark.unit
@pytest.mark.parametrize("draws", [0, 1.5, True], ids=["zero", "float", "bool"])
def test_invalid_draws_raise(make_hit_sequence: HitSequenceFactory, draws: int) -> None:
    with pytest.raises(ValueError, match="draws must be an int >= 1"):
        ChristoffersenTest.monte_carlo_p_values(
            _cond_sequence(make_hit_sequence), min_violations=0, draws=draws, seed=1
        )


@pytest.mark.unit
@pytest.mark.parametrize("seed", [1.5, True], ids=["float", "bool"])
def test_invalid_seed_raises(make_hit_sequence: HitSequenceFactory, seed: int) -> None:
    with pytest.raises(ValueError, match="seed must be an int"):
        ChristoffersenTest.monte_carlo_p_values(
            _cond_sequence(make_hit_sequence), min_violations=0, draws=5, seed=seed
        )


@pytest.mark.unit
def test_invalid_min_violations_in_mc_raises(make_hit_sequence: HitSequenceFactory) -> None:
    with pytest.raises(ValueError, match="min_violations must be an int >= 0"):
        ChristoffersenTest.monte_carlo_p_values(
            _cond_sequence(make_hit_sequence), min_violations=True, draws=5, seed=1
        )


@pytest.mark.unit
@pytest.mark.parametrize("name", ["min_violations", "draws", "seed"])
def test_mc_signature_mandatory_keyword_only(name: str) -> None:
    """ADR 6.3.0006 item 1: `min_violations`, `draws` e `seed` obrigatórios, sem default."""
    parameter = inspect.signature(ChristoffersenTest.monte_carlo_p_values).parameters[name]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


# --- C9 — MonteCarloPValues incoerente ------------------------------------------------------


def _applicable(make_hit_sequence: HitSequenceFactory) -> MonteCarloPValues:
    return ChristoffersenTest.monte_carlo_p_values(
        _cond_sequence(make_hit_sequence), min_violations=_COND_MIN, draws=20, seed=2
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"horizon": 2}, "exist only for horizon == 1"),
        ({"horizon": 0}, "horizon must be an int >= 1"),
        ({"min_violations": -1}, "min_violations must be an int >= 0"),
        ({"draws": 0}, "draws must be an int >= 1"),
        ({"seed": True}, "seed must be an int"),
        ({"p_uc": 1.5}, r"p_uc must be in \[0, 1\]"),
        ({"uc_status": MonteCarloStatus.MC_CAP_REACHED}, "uc_status is never MC_CAP_REACHED"),
        ({"p_uc": None}, "p_uc must be set exactly when uc_status is APPLICABLE"),
        ({"p_ind": None}, "p_ind must be set exactly when ind_status is APPLICABLE"),
        ({"p_cc": None}, "p_cc must be set exactly when ind_status is APPLICABLE"),
        ({"attempts": 5.0}, "attempts must be an int"),
        ({"attempts": 19}, r"attempts must be in \[draws, 100\*draws\]"),
        ({"attempts": 2001}, r"attempts must be in \[draws, 100\*draws\]"),
    ],
    ids=[
        "horizon-two",
        "horizon-zero",
        "min-violations-negative",
        "draws-zero",
        "seed-bool",
        "p-value-above-one",
        "uc-cap-reached",
        "p-uc-missing",
        "p-ind-missing",
        "p-cc-missing",
        "attempts-float",
        "attempts-below-draws",
        "attempts-above-cap",
    ],
)
def test_mc_incoherent_applicable_result_raises(
    make_hit_sequence: HitSequenceFactory, overrides: dict[str, object], match: str
) -> None:
    """C9: cada ramo do `MonteCarloPValues.__post_init__` sobre o resultado aplicável."""
    result = _applicable(make_hit_sequence)
    assert result.attempts > result.draws  # premissa: houve redraw

    with pytest.raises(ValueError, match=match):
        dataclasses.replace(result, **overrides)  # type: ignore[arg-type]


@pytest.mark.unit
def test_mc_incoherent_round_trips_when_valid(make_hit_sequence: HitSequenceFactory) -> None:
    result = _applicable(make_hit_sequence)

    assert dataclasses.replace(result) == result


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sequence_values", "min_violations", "overrides", "match"),
    [
        ((T,), 0, {"attempts": 3}, "nothing is drawn"),
        (
            (T,),
            0,
            {"ind_status": MonteCarloStatus.MC_CAP_REACHED},
            "nothing is drawn",
        ),
        ((F,) * 10, 1, {"attempts": 51}, "there is no redraw"),
        (_CAP_SEQUENCE, _CAP_MIN, {"attempts": 499}, "mc_cap_reached means the cap was used"),
    ],
    ids=[
        "not-applicable-with-attempts",
        "not-applicable-with-ind-status",
        "uc-only-with-redraw",
        "cap-without-cap-attempts",
    ],
)
def test_mc_incoherent_status_attempts_raise(
    make_hit_sequence: HitSequenceFactory,
    sequence_values: tuple[bool, ...],
    min_violations: int,
    overrides: dict[str, object],
    match: str,
) -> None:
    """C9: tentativas incoerentes com os status (sem LR_uc, só LR_uc, teto)."""
    rate = _CAP_RATE if sequence_values == _CAP_SEQUENCE else _P
    draws = _CAP_DRAWS if sequence_values == _CAP_SEQUENCE else 50
    result = ChristoffersenTest.monte_carlo_p_values(
        make_hit_sequence(sequence_values, levels=(rate,)),
        min_violations=min_violations,
        draws=draws,
        seed=1,
    )

    with pytest.raises(ValueError, match=match):
        dataclasses.replace(result, **overrides)  # type: ignore[arg-type]


# --- C9 — identidade copiada da sequência (D8; Checkpoint C bloco 3) ------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"kind": "x"}, "kind must be a HitKind"),
        ({"levels": (0.05, 0.95)}, r"levels must have 1 element\(s\) for kind=lower_tail"),
        ({"tolerance": -1.0}, r"MonteCarloPValues\.tolerance must be a finite number >= 0"),
        ({"includes_degenerate": 1}, "includes_degenerate must be a bool"),
    ],
    ids=["kind-not-hitkind", "levels-size", "tolerance-negative", "includes-degenerate-int"],
)
def test_mc_incoherent_identity_raises(
    make_hit_sequence: HitSequenceFactory, overrides: dict[str, object], match: str
) -> None:
    """C9/D8: o resultado persistido valida a identidade copiada pelas regras do VO."""
    result = _applicable(make_hit_sequence)

    with pytest.raises(ValueError, match=match):
        dataclasses.replace(result, **overrides)  # type: ignore[arg-type]


@pytest.mark.unit
def test_mc_incoherent_attempts_bool_raises(make_hit_sequence: HitSequenceFactory) -> None:
    """C9: `attempts` é `int` - `True` (== 1) não é contagem de tentativas."""
    result = ChristoffersenTest.monte_carlo_p_values(
        make_hit_sequence((True,)), min_violations=0, draws=1, seed=1
    )
    assert result.attempts == 0

    with pytest.raises(ValueError, match="attempts must be an int"):
        dataclasses.replace(result, attempts=True)
