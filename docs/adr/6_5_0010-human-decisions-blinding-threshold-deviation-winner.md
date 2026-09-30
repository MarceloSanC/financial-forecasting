---
title: ADR 6.5.0010 — Human decisions of Stage 6.5 — the 6.4 computation on cohort r0 is left as recorded and r0 stays the judged cohort, with an optional blinding statement whose content is still open; degeneracy threshold 1 %; power scenarios ±5 p.p. + 0.2σ (primary) and ±3 p.p. + 0.1σ (secondary); the primary-winner rule is kept
description: Architecture Decision Record
when-use: Reference when asking why cohort r0 is still the judged cohort after the Stage 6.4 measurement, what the preregistration may and may not say about blinding, where the 1 % degeneracy threshold and the power scenarios come from, or who decided the primary-winner rule
keywords: [adr, evaluation, preregistration, human-decision, blinding, exposure, degeneracy-threshold, power, minimum-relevant-deviation, primary-winner, class-p]
status: accepted
created_at: 2026-09-30
updated_at: 2026-09-30
adr_id: 6.5.0010
decision: P1 — the Stage 6.4 measurement that computed the confirmatory tables of cohort aapl_confirmatory-r0-665f45d9169a in a discarded container, with no value read, is left as recorded (technical 6.4 §7, PR #126, issue #127 are not edited) and r0 remains the judged cohort (no new revision, no retraining); the preregistration must not state that no metric was ever computed on r0; its schema has an optional blinding_statement text whose content (or absence) the human has not decided yet. P2 — the degeneracy threshold of the H1 gate is 1 %. P3 — the power of the gate is reported against a primary scenario of ±5 p.p. width and 0.2σ location and a secondary scenario of ±3 p.p. width and 0.1σ location. P4 — the primary winner is the candidate that passes H1, beats both naive and beats or ties the strong comparators (tie = in the MCS); lowest P̄_G is information only; GBM stays in the strong class; the profile shows the outcome per tier.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0010 — Human decisions (class P) of Stage 6.5

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — decided by the human (Marcelo) at Checkpoint A round 1,
2026-09-30. P1 has one part still open (content of the blinding statement).

## Context

Skill `evidence-resolution` routes to the human only the forks whose answer is a
preference or project policy (class P). The concept draft left three open (P1
blinding, P2 threshold, P3 deviation); the Checkpoint A round 1 review raised a
fourth (P4 winner rule), because the domain doc says the exact logical form of
the verdict "é conteúdo do pré-registro" and gives only an example.

- **P1.** The domain doc §8.2 (B-ORDEM, ADR 0.0.0011): "ver predições OOS brutas
  antes do hash não é violação; computar métricas confirmatórias é". Stage 6.4
  (technical §7, `[finding]` "Exposição de cegamento") ran the refresh on a copy
  of cohort r0 before this preregistration: the confirmatory tables were computed
  inside an ephemeral container and discarded; only status, durations, counts,
  the grid prefix, the fingerprint equality, the realized summary and grouped
  check counts were printed — no metric, p-value or rate was read.
- **P2.** Doc §5.3 item 4: a degeneracy rate above a preregistered threshold fails
  H1 for distributional models; no source fixes the value (§5.2: the gate is
  project policy).
- **P3.** Doc §8.5 (B1): the claim "calibration not rejected" is always stated
  with the gate's power against a preregistered minimum relevant deviation, in a
  width and a location form; the doc gives "±5 p.p." and 0.2σ as examples.
- **P4.** Doc §8.6 example ("menor P̄_G com DM+Holm significativo vs todos os
  naive e não eliminado do MCS") versus overview §4 ("superar ou empatar com os
  fortes").

## Decision

`[decision:P] 6.5-P1 — treatment of the Stage 6.4 computation on cohort r0`
`Escolha: leave it as recorded; keep r0 as the judged cohort; no statement that no metric was ever computed on r0; optional blinding_statement field, content undecided · Alternativas: declare it as a null exposure in the plan; new cohort r1 with new TFT seeds; new revision with the same seeds · Decisor: humano (Checkpoint A r1, 2026-09-30)`
`Base: technical 6.4 §7 [finding] (nothing was read); Nosek et al. 2018 "Challenge 3" (account for loss of blinding) — weighed by the human`
`Sensibilidade pré-registrada: nenhuma · Reversível: o conteúdo da declaração, até a âncora`

1. r0 (`aapl_confirmatory-r0-665f45d9169a`) stays the judged cohort; no r1, no
   retraining. The existing records (technical 6.4 §7, PR #126, issue #127
   comments) are not edited or removed.
2. No artifact of this Stage — preregistration, mirror, ADR, concept — may state
   or imply that no metric was ever computed on r0.
3. The preregistration schema has an **optional** key `blinding_statement`
   (non-empty text when present; hashed like every other field). Whether r0's
   file carries it, and its wording, is still the human's decision; the freeze
   Task waits for it. The scorecard echoes the statement when present and never
   conjoins it in `academic_decision_ready` (ADR 6.5.0007).
4. The order this Stage proves is the one of ADR 6.5.0003 item 4 (anchors,
   nothing computed by 6.5, gold after the anchor), not a claim about the past.

`[decision:P] 6.5-P2 — degeneracy threshold of the H1 gate`
`Escolha: 1 % (mean degeneracy rate of the candidate across seeds) · Alternativas: 0 %; 5 %; 10 % · Decisor: humano (Checkpoint A r1, 2026-09-30)`
`Base: doc §5.3 item 4; a synthetic benchmark run by the orchestration (not versioned) showed that at 1 % the collapse hardly hides miscalibration and a calibrated model is not penalized`
`Sensibilidade pré-registrada: nenhuma · Reversível: não depois do hash`

`[decision:P] 6.5-P3 — minimum relevant deviation for the declared power`
`Escolha: primary = ±5 p.p. width of the 80 % pair and 0.2σ location; secondary = ±3 p.p. width and 0.1σ location · Alternativas: ±3 p.p. + 0.1σ only; ±10 p.p. + 0.3σ · Decisor: humano (Checkpoint A r1, 2026-09-30)`
`Base: doc §8.5 (examples ±5 p.p., 0.2σ; power table); in-session exact power at n ≈ 1,512 (from the geometry): ±5 p.p. → 0.975/0.989, 0.2σ → 1.000, ±3 p.p. → 0.637/0.647, 0.1σ → 0.750`
`Sensibilidade pré-registrada: the secondary scenario · Reversível: não depois do hash`

The tail rates of each scenario are written explicitly in the file (ADR 6.5.0006,
6.5-SIGMA): width ±5 p.p. → (0.125, 0.125) and (0.075, 0.075); ±3 p.p. →
(0.115, 0.115) and (0.085, 0.085); location 0.2σ → (Φ(−z₀.₉ − 0.2),
1 − Φ(z₀.₉ − 0.2)) ≈ (0.0692, 0.1397); 0.1σ → ≈ (0.0836, 0.1187).

`[decision:P] 6.5-P4 — the primary-winner rule`
`Escolha: keep: winner = candidate iff H1 ∧ beats both naive ∧ (in the MCS ∨ beats every strong); lowest P̄_G shown as information; GBM in the strong class; outcome per tier in the profile · Alternativas: add lowest P̄_G as a condition; require beating every strong; ML tier as a third condition · Decisor: humano (Checkpoint A r1, 2026-09-30)`
`Base: overview §4 ("superar ou empatar com os fortes"); doc §6.10 (tie = MCS); ADR 6.5.0007`
`Sensibilidade pré-registrada: nenhuma · Reversível: não depois do hash`

## Alternatives considered

The alternatives of each decision are those listed in its record; the options,
examples and trade-offs were presented to the human in the format of
`docs/PROMPT-step-single-session.md` §2.

## Consequences

### Positive

- Every value of the plan now has an owner; the only open item is the wording
  (or absence) of the blinding statement, which changes no rule.

### Negative

- The freeze and anchoring Task of r0 cannot run until the blinding statement is
  decided.

## References

- Domain doc §5.2, §5.3, §8.2, §8.5, §8.6; overview §4.
- Technical 6.4 §7 `[finding]` "Exposição de cegamento (B-ORDEM) na medição real da Task 15".
- Related ADRs: [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md), [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md), [6.5.0006](./6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md), [6.5.0007](./6_5_0007-verdict-logical-form-and-decision-readiness.md), [6.5.0009](./6_5_0009-preregistered-conventional-values.md).
- Nosek et al. (2018), PNAS, doi:10.1073/pnas.1708274114.
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127).
