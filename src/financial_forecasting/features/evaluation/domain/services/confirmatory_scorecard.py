"""Serviço de domínio `ConfirmatoryScorecard` — árvore H1 → H2 por horizonte (Stage 6.5).

stdlib-only (concept 6.5 §4, D7, I9, I10, I12, C9, C11; ADR `6_5_0007` itens
1-7; ADR `6_5_0010` P4). `decide(prereg, evidence)`, por horizonte pré-registrado:

- `h1` = `H1Gate.evaluate(prereg.h1_gate, evidence)`;
- linhas DM do estimador **primário** (Holm já aplicado no gold ao alpha do plano);
  (i) `beats_naive` = Holm rejeita contra **todo** naive;
  `beats_every_strong` = rejeita contra todo forte (estatístico forte + ML — P4:
  o GBM é forte); `in_mcs` = candidato incluído no MCS do esquema primário;
  (ii) `beats_or_ties_strong` = `in_mcs or beats_every_strong`;
- `h2`: `NOT_APPLICABLE` se H1 reprova; senão `NO_SKILL_OVER_NAIVE` (não (i)),
  `BEATS_NAIVE_ONLY` ((i), não (ii)), `BEATS_NAIVE_AND_STRONG` ((i) e Holm rejeita
  contra todo forte) ou `BEATS_NAIVE_TIES_STRONG` ((i), (ii), algum forte não
  superado);
- `primary_winner` = candidato ⇔ H1 ∧ (i) ∧ (ii); senão `None`;
- `candidate_has_lowest_mean_pinball` — P̄_G da amostra comum, **informação**, não
  condição (empate conta como menor).

`beats_naive`, `beats_or_ties_strong` e `in_mcs` são fatos do gold e vêm
preenchidos mesmo com H1 reprovado. A família de Holm são os seis comparadores e o
MCS os sete modelos (I10): um comparador mal calibrado continua neles — o gate só
decide a elegibilidade do candidato. Horizontes são independentes (I9); o sucesso
do estudo é "H1 em ≥ 1 horizonte" (doc §8.8). O veredito não tem campo do perfil
(I12): é construído antes e sem ele.

`tier_readings` (perfil, ADR 6.5.0007 item 5) é função separada: por horizonte e
nível, se Holm rejeita contra todos os membros, se o candidato está no MCS
primário, a condição (ii) lida contra o nível (`beats_or_ties`) e se o candidato
está no MCS **junto com** todos eles (empate com o nível). `decide` não a chama.

Na entrada, `decide` confere `rules.h1_gate.form`, `rules.verdict.form` e
`rules.success_criterion` contra o catálogo (defesa: o VO do plano já garante).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from financial_forecasting.features.evaluation.domain.services.h1_gate import H1Gate, H1Result
from financial_forecasting.features.evaluation.domain.value_objects.preregistration import (
    Preregistration,
    require_implemented_rule,
)
from financial_forecasting.features.evaluation.domain.value_objects.scorecard_evidence import (
    DmEvidence,
    HorizonEvidence,
)

_CHECKED_RULES = ("h1_gate.form", "verdict.form", "success_criterion")


class H2Outcome(StrEnum):
    """Desfecho ordenado de H2 no candidato (ADR 6.5.0007 item 2)."""

    NOT_APPLICABLE = "not_applicable"
    NO_SKILL_OVER_NAIVE = "no_skill_over_naive"
    BEATS_NAIVE_ONLY = "beats_naive_only"
    BEATS_NAIVE_TIES_STRONG = "beats_naive_ties_strong"
    BEATS_NAIVE_AND_STRONG = "beats_naive_and_strong"


@dataclass(frozen=True, kw_only=True)
class HorizonVerdict:
    """Veredito de um horizonte (sem campo do perfil — I12)."""

    horizon: int
    h1: H1Result
    beats_naive: bool
    beats_or_ties_strong: bool
    in_mcs: bool
    h2: H2Outcome
    primary_winner: str | None
    candidate_has_lowest_mean_pinball: bool


@dataclass(frozen=True)
class ScorecardVerdict:
    """Vereditos por horizonte e o sucesso do estudo (H1 em ≥ 1 horizonte)."""

    horizons: tuple[HorizonVerdict, ...]
    study_success_h1: bool


@dataclass(frozen=True)
class TierReading:
    """Leitura de um nível de comparadores num horizonte (perfil, ADR 6.5.0007 item 5).

    Campos:
        holm_rejects_all: Holm rejeita contra todo membro do nível.
        candidate_in_mcs: o candidato está no MCS primário (o mesmo fato de
            `HorizonVerdict.in_mcs`).
        beats_or_ties: `candidate_in_mcs or holm_rejects_all` — a condição (ii) do
            veredito lida só contra este nível.
        ties_in_mcs: o candidato **e todos** os membros do nível estão no MCS
            primário (empate com o nível inteiro) — descritivo, mais estrito que (ii).
    """

    horizon: int
    tier: str
    members: tuple[str, ...]
    holm_rejects_all: bool
    candidate_in_mcs: bool
    beats_or_ties: bool
    ties_in_mcs: bool


def _evidence_by_horizon(
    prereg: Preregistration, evidence: Sequence[HorizonEvidence]
) -> tuple[HorizonEvidence, ...]:
    horizons = [item.horizon for item in evidence]
    if sorted(horizons) != list(prereg.horizons) or len(set(horizons)) != len(horizons):
        raise ValueError(
            f"evidence horizons {horizons} must be the preregistered horizons "
            f"{list(prereg.horizons)}"
        )
    return tuple(sorted(evidence, key=lambda item: item.horizon))


def _primary_rows(prereg: Preregistration, evidence: HorizonEvidence) -> Mapping[str, DmEvidence]:
    rows = {
        row.comparator: row for row in evidence.dm if row.estimator is prereg.dm.primary_estimator
    }
    missing = [model for model in prereg.comparators if model not in rows]
    if missing:
        raise ValueError(
            f"horizon {evidence.horizon}: no primary DM row for the comparators {missing}"
        )
    return rows


def _included(prereg: Preregistration, evidence: HorizonEvidence) -> frozenset[str]:
    scheme = prereg.mcs.primary_scheme
    rows = [row for row in evidence.mcs if row.scheme is scheme]
    missing = [model for model in prereg.models if model not in {row.model for row in rows}]
    if missing:
        raise ValueError(f"horizon {evidence.horizon}: no primary MCS row for the models {missing}")
    return frozenset(row.model for row in rows if row.included)


def _lowest_mean_pinball(prereg: Preregistration, evidence: HorizonEvidence) -> bool:
    missing = [model for model in prereg.models if model not in evidence.mean_pinball]
    if missing:
        raise ValueError(f"horizon {evidence.horizon}: no mean pinball for the models {missing}")
    values = [evidence.mean_pinball[model] for model in prereg.models]
    return evidence.mean_pinball[prereg.candidate] <= min(values)


def _outcome(*, passed: bool, beats_naive: bool, ties: bool, beats_every_strong: bool) -> H2Outcome:
    if not passed:
        return H2Outcome.NOT_APPLICABLE
    if not beats_naive:
        return H2Outcome.NO_SKILL_OVER_NAIVE
    if not ties:
        return H2Outcome.BEATS_NAIVE_ONLY
    if beats_every_strong:
        return H2Outcome.BEATS_NAIVE_AND_STRONG
    return H2Outcome.BEATS_NAIVE_TIES_STRONG


class ConfirmatoryScorecard:
    """A regra mecânica H1 → H2 por horizonte (ver docstring do módulo)."""

    @staticmethod
    def decide(prereg: Preregistration, evidence: Sequence[HorizonEvidence]) -> ScorecardVerdict:
        """Vereditos por horizonte e o sucesso do estudo.

        Raises:
            ValueError: identificador de regra fora do catálogo; horizontes da
                evidência ≠ os do plano; linha DM/MCS ou P̄_G faltando (C11).
        """
        for key in _CHECKED_RULES:
            require_implemented_rule(key, prereg.rules.value_of(key))
        verdicts = tuple(
            ConfirmatoryScorecard._horizon(prereg, item)
            for item in _evidence_by_horizon(prereg, evidence)
        )
        return ScorecardVerdict(
            horizons=verdicts,
            study_success_h1=any(verdict.h1.passed for verdict in verdicts),
        )

    @staticmethod
    def _horizon(prereg: Preregistration, evidence: HorizonEvidence) -> HorizonVerdict:
        h1 = H1Gate.evaluate(prereg.h1_gate, evidence)
        rows = _primary_rows(prereg, evidence)
        beats_naive = all(rows[model].rejected for model in prereg.comparator_tiers.naive)
        beats_every_strong = all(rows[model].rejected for model in prereg.strong)
        in_mcs = prereg.candidate in _included(prereg, evidence)
        ties = in_mcs or beats_every_strong
        winner = prereg.candidate if h1.passed and beats_naive and ties else None
        return HorizonVerdict(
            horizon=evidence.horizon,
            h1=h1,
            beats_naive=beats_naive,
            beats_or_ties_strong=ties,
            in_mcs=in_mcs,
            h2=_outcome(
                passed=h1.passed,
                beats_naive=beats_naive,
                ties=ties,
                beats_every_strong=beats_every_strong,
            ),
            primary_winner=winner,
            candidate_has_lowest_mean_pinball=_lowest_mean_pinball(prereg, evidence),
        )

    @staticmethod
    def tier_readings(
        prereg: Preregistration, evidence: Sequence[HorizonEvidence]
    ) -> tuple[TierReading, ...]:
        """Por horizonte e nível: Holm contra todos? candidato no MCS com todos eles?"""
        tiers = prereg.comparator_tiers
        readings: list[TierReading] = []
        for item in _evidence_by_horizon(prereg, evidence):
            rows = _primary_rows(prereg, item)
            included = _included(prereg, item)
            candidate_in_mcs = prereg.candidate in included
            for name, members in (
                ("naive", tiers.naive),
                ("strong_statistical", tiers.strong_statistical),
                ("ml", tiers.ml),
            ):
                readings.append(
                    TierReading(
                        horizon=item.horizon,
                        tier=name,
                        members=members,
                        holm_rejects_all=(rejects_all := all(rows[m].rejected for m in members)),
                        candidate_in_mcs=candidate_in_mcs,
                        beats_or_ties=candidate_in_mcs or rejects_all,
                        ties_in_mcs=candidate_in_mcs and all(m in included for m in members),
                    )
                )
        return tuple(readings)
