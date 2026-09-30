---
title: ADR 6.5.0003 — Each preregistration revision is anchored like the cohort (published tag + issue comment whose server timestamp is the record); the anchor is kept in a separate file outside the hash; the scorecard refuses an unanchored plan and marks as not decision-ready any gold generated before the anchor
description: Architecture Decision Record
when-use: Reference when anchoring a preregistration, when asking how the Stage proves that the plan preceded every confirmatory metric, where the anchor record lives, or what the scorecard checks about order
keywords: [adr, evaluation, preregistration, anchor, tag, issue-comment, server-timestamp, blinding, order, b-ordem, anteriority]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-30
adr_id: 6.5.0003
decision: After the revision file is committed, push the tag preregistration/<preregistration_ref> to that commit and post a comment on the Stage issue with the preregistration_ref, the full hash, the tag, the commit and the referenced cohort_id and cohort hash — the comment's server created_at is the anchor time; record tag, commit, comment URL and anchored_at in config/preregistration/<name>-r<rev>.anchor.toml (written after the hash, so outside it); BuildConfirmatoryScorecard loads the anchor of every revision in the chain and raises if one is missing, and sets academic_decision_ready to false when the gold manifest's started_at precedes the judged revision's anchored_at; what the Stage proves is its own part of the order — the referenced cohort's anchor precedes the preregistration anchor (two server timestamps), the Stage computes nothing on the cohort, and the gold a scorecard reads must postdate the anchor; the first confirmatory refresh is the first one after the anchor (8.1's), and no statement is made about computations before it.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0003 — Anchor and order check

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-09-30 after Checkpoint A round 1 (C-A2: scope of the
order proof; B9: rebase)

## Context

A hash proves integrity, not when the content existed; git dates and the local
`Clock` are client-asserted and backdatable (ADR 5.5.0001, Context item 2,
Haber & Stornetta 1991). The roadmap DoD asks the Stage to prove that no metric
on the cohort's `parent_sweep_id` is computed before the preregistration hash is
published, "with a server-stamped anchor (ADR 5.5.0001)". Issue #127 (fork C2)
sources: Mertens & Krypotos (2019): "without timestamping, researchers can
easily antedate their data-analysis plans"; Cramer et al. (2022, US COVID-19
Forecast Hub) accept "publicly available evidence (e.g., GitHub commit
history)". No primary source compares a git tag with a server comment; the issue
comment is the project's server clock (5.5 precedent).

## Decision

`[decision:C] 6.5-C2 — anchor mechanism and how the use case enforces it`
`Escolha: tag + issue comment (5.5 pattern), anchor record in a separate file, scorecard refuses a missing anchor and flags gold older than the anchor · Alternativas: git commit date; OSF registration; anchor inside the hashed file; no code check (runbook only) · Degrau (C): 1 (ADR 5.5.0001 "Anchor")`
`Base: ADR 5.5.0001 Decision "Anchor"; ICH E9 §5.1 "Formal records should be kept of when the statistical analysis plan was finalised"; Mertens & Krypotos 2019 (issue #127)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim (o registro é aditivo)`

1. **Anchor steps** (runbook step of the freeze Task, per revision): commit the
   revision file → push tag `preregistration/<preregistration_ref>` to that
   commit (tags survive the feature-branch rebase; ADR 5.5.0001) → comment on the
   Stage issue with the `preregistration_ref`, the full hash, the tag, the
   commit, the `cohort_id` and the cohort hash it references. The comment's
   `created_at` (GitHub server) is `anchored_at`. The freeze commit is rebased
   later with the branch; the tag keeps the original commit reachable and the
   anchor record names it. What the scorecard and the consistency test compare is
   **content** (the hash of the revision file at HEAD equals the anchored
   hash), not commit identity, so the rebase does not break the anchor.
2. **Record:** `config/preregistration/<name>-r<rev>.anchor.toml` with `tag`,
   `commit`, `comment_url`, `anchored_at` (UTC ISO-8601), committed after the
   comment. It is outside the hash by construction (it cannot exist before the
   hash). The mirror (ADR 6.5.0001 item 5) quotes it too.
3. **Enforcement in code:** the preregistration source port returns the anchor
   of each revision; `BuildConfirmatoryScorecard` raises
   `PreregistrationNotAnchoredError` when a revision of the chain has none. If
   the gold manifest's `started_at` is earlier than the judged revision's
   `anchored_at`, the scorecard is still produced but `academic_decision_ready`
   is false with the reason "gold generated before the preregistration anchor".
   The manifest time is the refresh's local clock — the check catches the honest
   mistake, not a forged clock; the public proof is item 4.
4. **What the order proof covers.** The roadmap DoD ("nenhuma métrica sobre o
   `parent_sweep_id` … é calculada antes de o hash do pré-registro estar
   publicado, e a Stage prova essa ordem") is rewritten by this Stage (concept
   D10) to what the Stage can prove and does prove:
   - the **referenced cohort's anchor** (for r0: the issue #102 comment, 5.5)
     precedes the preregistration anchor (issue #127 comment) — two server
     timestamps recorded by the anchoring Task in the technical §7;
   - Stage 6.5 itself computes no metric on the cohort (every test and the e2e
     use synthetic silver);
   - the gold that a scorecard reads must be generated after the anchor (item 3
     in code), and the **first confirmatory refresh** is, by definition, the
     first refresh of the cohort's gold after the anchor with parameters derived
     from the plan — the 8.1 run, which posts its own comment, closing the chain
     cohort anchor < preregistration anchor < first confirmatory refresh on the
     server.
   It makes **no** claim that no metric was ever computed on the cohort before
   the anchor: Stage 6.4 recorded one such computation (technical 6.4 §7), which
   the human decided to leave as recorded, with the cohort unchanged
   (ADR 6.5.0010, P1).

## Alternatives considered

### Alternative A — Git commit date as the record

- **Why rejected:** client-asserted and rewritten by the rebase (ADR 5.5.0001,
  Alternative B).

### Alternative B — OSF registration

- **Pros:** the discipline's reference registry.
- **Cons:** external account and manual upload per revision; the project's
  existing anchor already gives a third-party timestamp.
- **Why rejected:** degree 1 (5.5 pattern); can be added later without change.

### Alternative C — Anchor fields inside the hashed file

- **Why rejected:** circular: the anchor needs the hash.

### Alternative D — Runbook only, no check in code

- **Why rejected:** the 5.5 left the anchor "a manual runbook step, not enforced
  by code" (ADR 5.5.0001, Negative); here the consumer of the plan exists, so the
  cheap checks (anchor present, gold not older than it) belong to it.

## Consequences

### Positive

- The scorecard cannot run on a plan that was never published; a gold built
  before the plan cannot be read as confirmatory.

### Negative

- Anchoring stays a manual step (tag push, comment); the local-clock check is
  weak by nature and declared so.

## References

- Related ADRs: [6.5.0010](./6_5_0010-human-decisions-blinding-threshold-deviation-winner.md), [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md), [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md), [6.5.0001](./6_5_0001-preregistration-canonical-toml-hashed-value-object.md), [6.5.0002](./6_5_0002-amendment-as-new-revision-file.md).
- Haber, S.; Stornetta, W. S. (1991), J. Cryptology 3(2), doi:10.1007/BF00196791.
- Mertens, G.; Krypotos, A.-M. (2019), Psychologica Belgica, doi:10.5334/pb.493.
- Cramer, E. Y. et al. (2022), Scientific Data, doi:10.1038/s41597-022-01517-w.
- ICH E9 (1998) §5.1.
- Issues [#102](https://github.com/MarceloSanC/financial-forecasting/issues/102) (cohort anchor), [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (fork C2).
