---
title: ADR 6.5.0007 — The per-horizon verdict is an ordered H2 outcome on the candidate, reached only when the H1 gate passes; the primary winner is the candidate that passes H1, beats both naive baselines by DM + Holm and beats or ties the strong comparators (statistical and ML); academic_decision_ready is the conjunction of validity gates and never depends on whether the candidate won
description: Architecture Decision Record
when-use: Reference when reading the scorecard's verdict, when asking what "primary winner" means, which comparators are naive or strong, why GBM counts as strong, why H2 is "not applicable", what academic_decision_ready requires, or why a refuted hypothesis can still be decision-ready
keywords: [adr, evaluation, scorecard, verdict, h1, h2, primary-winner, naive, strong, ml, tiers, mcs, holm, dm, academic-decision-ready, profile, decision-tree]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-30
adr_id: 6.5.0007
decision: Per horizon, H1 = the gate of ADR 6.5.0006; if it fails, H2 is NOT_APPLICABLE; if it passes, (i) beats_naive = Holm rejects against both naive comparators (baseline_zero_return, baseline_historical_mean), (ii) beats_or_ties_strong = the candidate is in the primary MCS or Holm rejects against every strong comparator (the strong-statistical tier baseline_ar1, baseline_ewma_vol, baseline_historical_quantiles and the ML tier gbm_quantile), (iii) in_mcs is reported as complementary; the H2 outcome is one of NO_SKILL_OVER_NAIVE, BEATS_NAIVE_ONLY, BEATS_NAIVE_TIES_STRONG, BEATS_NAIVE_AND_STRONG; the primary winner of the horizon is the candidate iff H1 passes, (i) and (ii) hold (rule confirmed by the human, ADR 6.5.0010 P4), otherwise none; whether the candidate has the lowest mean pinball P̄_G is reported as information, never as a condition; the profile shows the outcome per tier (naive, strong statistical, ML); the Holm family stays the six comparators and the MCS set the seven models; the study success criterion is ≥ 1 horizon with H1 passed; nothing aggregates horizons; academic_decision_ready is true iff the gold generation is COMPLETED with no blocking or skipped required check, the gold started after the preregistration anchor, and no revision in the chain was amended unblinded — each false conjunct carries a reason.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0007 — Verdict form and decision readiness

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-09-30 after Checkpoint A round 1: the winner rule
was confirmed by the human (P4, ADR 6.5.0010); the anchor for placing GBM in the
strong class was corrected (C-M1); lowest P̄_G and the per-tier reading added.

## Context

Domain doc §8.6 fixes the tree: H1 gate (candidate only) → if it fails, H2 "não
aplicável"; if it passes, (i) beats the naive? (DM unilateral + Holm, family = the
B comparators of the horizon), (ii) beats/ties the strong? (DM + Holm for
"beats"; "ties" = not eliminated from the MCS at α_MCS, §6.10), (iii) belongs to
the MCS? (complementary evidence, not a condition). "The primary winner is defined
by the preregistered rule over (i)–(iii) (the exact logical form — e.g., 'lowest
P̄_G with DM + Holm significant against every naive and not eliminated from the
MCS' — is preregistration content)". "The profile never changes the verdict".
"`academic_decision_ready` … is the conjunction of gates — engineering, no
source".

Overview §4 H2: the candidate is compared with a declared hierarchy {naive,
strong statistical, ML quantile model}; "expected to beat the naive; the
scientific interest is to beat **or tie** the strong; MCS complementary;
non-dominance is a valid result". Overview §1: refutation is a valid result.

The doc's example includes "lowest P̄_G". Among the seven models only the
candidate is tested against every other one (the family is candidate ×
comparators); a lowest-P̄_G condition would add a point comparison with no test
behind it.

The FDA guidance on multiple endpoints (2022; issue #127) supports a success
defined by a conjunction ("only one path … no concern with Type I error rate
inflation") and a prospectively specified sequence. Its gatekeeping opens on a
**rejection**; H1 opens on a **non-rejection** (a validity precondition), so its
error guarantee does not transfer literally (issue #127, caveat to P3).

## Decision

`[decision:C] 6.5-VERDICT — exact logical form of the per-horizon verdict`
`Escolha: ordered H2 outcome on the candidate; (ii) = in the primary MCS ∨ beats every strong; strong = strong-statistical ∪ ML tiers · Alternativas: winner = lowest P̄_G model; winner requires beating every strong; winner = (i) only; ML tier as a third condition · Degrau (C): 1 (domain doc §8.6 and §6.10; overview §4 H2 "superar ou empatar com os fortes")`
`Base: domain doc §8.6, §6.10, §8.8; overview §1, §4; FDA Multiple Endpoints (2022), conjunction and fixed sequence (issue #127)`
`Sensibilidade pré-registrada: nenhuma no veredito; o perfil mostra o desfecho por nível, DM Bartlett e MCS moving-block · Reversível: não depois do hash`

The primary-winner rule itself was put to the human and confirmed (ADR 6.5.0010,
`[decision:P] 6.5-P4`).

`[decision:C] 6.5-READY — what academic_decision_ready conjoins`
`Escolha: validity gates only (gold COMPLETED without blocking or skipped required checks; gold after the anchor; no unblinded amendment); never the H1/H2 outcome · Alternativas: also require H1 passed in ≥ 1 horizon; also require a blinding statement · Degrau (C): 1 (overview §1 "refutação é resultado válido"; §8.8: a horizon failing H1 is reported with its profile)`
`Base: domain doc §8.6 "conjunção de gates — engenharia, sem fonte"; overview §1`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. **Tiers** (declared in the preregistration, ADR 6.5.0004): naive =
   {`baseline_zero_return`, `baseline_historical_mean`}; strong statistical =
   {`baseline_ar1`, `baseline_ewma_vol`, `baseline_historical_quantiles`}; ML =
   {`gbm_quantile`}. The verdict reads **naive** against **strong = strong
   statistical ∪ ML**. Putting the ML tier with the strong comparators follows
   overview §4 (the scientific interest is to "superar ou empatar com os fortes",
   and the ML quantile model is the hierarchy's strongest rung) and is the more
   demanding reading: condition (ii) can be met by beating every strong or by
   staying in the MCS with all of them, the GBM included. The Holm family is
   unchanged — the six comparators (B-FAMILIA, ADR 0.0.0010); the tiers only group
   the reading. The MCS set M0 is the seven models (candidate + six).
2. **Per horizon:** `H1Result` (pass/fail, the two bands, mean degeneracy, power,
   sensitivities); if fail, `H2Outcome.NOT_APPLICABLE`; else `beats_naive`,
   `beats_or_ties_strong`, `in_mcs` and the outcome:
   - `NO_SKILL_OVER_NAIVE` — not (i);
   - `BEATS_NAIVE_ONLY` — (i), not (ii);
   - `BEATS_NAIVE_TIES_STRONG` — (i), (ii), and some strong comparator not
     beaten;
   - `BEATS_NAIVE_AND_STRONG` — (i) and Holm rejects against every strong
     comparator.
3. **Primary winner** of horizon h: the candidate iff H1 passes, (i) and (ii);
   else `None`. There is no winner across horizons (§8.7).
4. **Information, not condition:** `candidate_has_lowest_mean_pinball` (P̄_G on
   the common sample, candidate as seed mean) is reported next to the verdict.
5. **Per-tier profile:** for each tier, whether Holm rejects against every member
   and whether the candidate is in the MCS with them, so the three rungs of the
   overview stay readable.
6. **Study success** (conv. #28): true iff H1 passes in ≥ 1 preregistered
   horizon; reported apart from the per-horizon winners.
7. **Profile** is a separate VO; the verdict VOs have no field computed from it
   (tested: the verdict is built before and without the profile).
8. **`academic_decision_ready`** = the manifest is `COMPLETED` (a `BLOCKED` gold
   raises before, ADR 6.5.0005) ∧ `gold_quality_checks` has no `ERROR`+`FAIL`
   and no `SKIPPED` among the checks the verdict needs (`degeneracy_check`,
   `alignment_check`, `statistical_preconditions`) ∧ manifest `started_at` ≥ the
   judged revision's `anchored_at` (ADR 6.5.0003) ∧ no `unblinded` amendment in
   the chain (ADR 6.5.0002). Each false conjunct adds a named reason. Integrity
   failures (hash, manifest or gold vs plan) are exceptions, not a false flag
   (ADR 6.5.0004). The roadmap wording "exige todos os gates" is rewritten to this
   meaning in the Stage's PR (concept D10).

## Alternatives considered

### Alternative A — Winner = the model with lowest P̄_G, or lowest P̄_G as a condition

- **Why rejected:** the family tests only the candidate against each comparator;
  a lowest-P̄_G condition adds a point comparison without a test (White 2000 §2:
  the claim must match the comparisons made). Kept as information (item 4).

### Alternative B — Winner requires beating every strong comparator

- **Why rejected:** contradicts overview §4 ("superar **ou empatar**") and §6.10
  (tie = in the MCS); it is the top outcome level instead.

### Alternative C — Winner = beats the naive only

- **Why rejected:** "expected" per overview §4, not the scientific interest; kept
  as `BEATS_NAIVE_ONLY`.

### Alternative D — The ML tier as a separate third condition

- **Pros:** mirrors the three rungs literally.
- **Cons:** a third condition over the same Holm family and MCS adds no test;
  "beats or ties the strong" already includes the GBM.
- **Why rejected:** the per-tier profile (item 5) shows the three rungs without a
  third gate.

### Alternative E — Readiness also requires H1 passed somewhere

- **Why rejected:** would make a refutation "not ready", the opposite of
  overview §1.

## Consequences

### Positive

- The verdict is a finite table of outcomes per horizon, readable without
  interpretation; readiness says whether the reading is valid, not whether the
  hypothesis won.

### Negative

- The type I error property of an H1 gate that opens on non-rejection has no
  primary source (issue #127 caveat); by event logic P(declare H2 ∧ pass H1) ≤ α,
  but the size conditional on passing H1 is not guaranteed — declared in the
  preregistration mirror.

## References

- Domain doc §6.4, §6.10, §8.5–§8.8; overview §1, §4.
- White, H. (2000), Econometrica 68(5), §2.
- FDA (2022), *Multiple Endpoints in Clinical Trials — Guidance for Industry*.
- Related ADRs: [0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md), [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md), [6.5.0002](./6_5_0002-amendment-as-new-revision-file.md), [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md), [6.5.0004](./6_5_0004-judging-values-in-preregistration-cohort-by-reference.md), [6.5.0005](./6_5_0005-gold-generation-reader-port-manifest-first.md), [6.5.0006](./6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md), [6.5.0010](./6_5_0010-human-decisions-blinding-threshold-deviation-winner.md).
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127); Checkpoint A round 1.
