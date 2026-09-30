---
title: ADR 6.5.0002 — An amendment to the preregistration is a new revision file that names the revision it amends, states why, and declares whether it was written blind; the original is never edited, and an amendment written after unblinding makes the verdict exploratory
description: Architecture Decision Record
when-use: Reference before changing a preregistration after it was anchored, when asking what happens to the original, or how the scorecard treats a plan changed after the confirmatory gold existed
keywords: [adr, evaluation, preregistration, amendment, revision, blinding, exploratory, confirmatory, ich-e9, osf]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-30
adr_id: 6.5.0002
decision: Revision r+1 of a preregistration is a new file config/preregistration/<name>-r<r+1>.toml whose payload carries amends (the preregistration_ref of revision r), a non-empty justification and blind_status ∈ {blinded, unblinded}; revision 0 carries none of them; files of anchored revisions are never edited; each revision is anchored on its own; the scorecard reports the revision chain, and an amendment declared unblinded sets academic_decision_ready to false with the reason "amended after unblinding" (its verdict is exploratory).
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0002 — Amendment as a new revision

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-09-30 after Checkpoint A round 1 (C-A2: definition
of the first confirmatory refresh)

## Context

Issue #127 (fork C3) asks how the preregistration changes after it is
registered. The sources already verified for the issue say: ICH E9 §5.1 —
"Formal records should be kept of when the statistical analysis plan was
finalised as well as when the blind was subsequently broken", with changes after
the blind review going to "a protocol amendment", and §4.5 — an unplanned
analysis needs an amendment "completed prior to unblinded access"; OSF — a
registration is a "time-stamped, read-only version … that can never be edited or
deleted", updated by a separate "Update" with a mandatory justification; ICH E9
§5.1 — "Only results from analyses envisaged in the protocol (including
amendments) can be regarded as confirmatory" (domain doc §8.1).

## Decision

`[decision:E] 6.5-C3 — how the preregistration is amended`
`Escolha: new revision file with amends + justification + blind_status; original never edited; unblinded amendment ⇒ exploratory · Alternativas: edit in place and rely on git/tag history; free-text changelog in the markdown only; forbid amendments · Degrau (C): —`
`Base: ICH E9 §5.1 "Formal records should be kept of when the statistical analysis plan was finalised as well as when the blind was subsequently broken"; §4.5 amendment "completed prior to unblinded access"; OSF Registrations "time-stamped, read-only version" + "Update" with justification (issue #127, fontes verificadas)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. Revision `r ≥ 1` carries `amends = "<preregistration_ref of r−1>"`,
   `justification` (non-empty text) and `blind_status ∈ {"blinded",
   "unblinded"}`; `Preregistration.from_mapping` refuses these keys on revision
   0 and requires them on `r ≥ 1`.
2. Anchored revision files are immutable: the consistency test of ADR 6.5.0001
   item 5 recomputes every revision's hash against the full hash quoted in the
   mirror, so an edit to an anchored file fails the build.
3. Each revision gets its own anchor (ADR 6.5.0003).
4. The scorecard receives the revision it judges by and lists the chain
   (`r0 → … → r`). If any revision in the chain is `unblinded`,
   `academic_decision_ready` is false with the reason "amended after
   unblinding": the result is reported, labelled exploratory (Wagenmakers et al.
   2012, domain doc §8.3: other analyses "should be labeled 'exploratory'").
5. `blind_status` is the author's declaration; its truth is checked by the
   order of server timestamps — the amendment's anchor versus the **first
   confirmatory refresh**, defined as the first refresh of the cohort's gold
   run **after the revision-0 anchor** with parameters derived from this plan
   (the 8.1 run, which posts its own comment; ADR 6.5.0003 item 4) — not by
   code. Nothing here asserts anything about computations made on the cohort
   before the revision-0 anchor (ADR 6.5.0010, P1).

## Alternatives considered

### Alternative A — Edit in place; tags keep history

- **Why rejected:** the original is not readable without git archaeology; OSF
  and ICH E9 treat the original as a frozen record next to the amendment.

### Alternative B — Changelog only in the markdown mirror

- **Why rejected:** the machine values would change without a new hash chain;
  the scorecard could not tell which plan judged the gold.

### Alternative C — Forbid amendments

- **Why rejected:** Nosek et al. (2018) "Challenge 1": deviations are
  documented, not prohibited; forbidding them pushes changes off the record.

## Consequences

### Positive

- The plan that judged a gold is always one anchored revision; changes are
  visible and justified; a change after unblinding cannot produce a
  confirmatory claim.

### Negative

- `blind_status` is self-declared; the protection is the public anchor order.

## References

- ICH E9 (1998) §4.5, §5.1; Nosek et al. (2018), doi:10.1073/pnas.1708274114; Wagenmakers et al. (2012) p. 632.
- Related ADRs: [6.5.0001](./6_5_0001-preregistration-canonical-toml-hashed-value-object.md), [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md), [6.5.0007](./6_5_0007-verdict-logical-form-and-decision-readiness.md).
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (fork C3).
