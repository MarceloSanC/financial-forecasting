---
title: ADR 8.3.0001 — Stage 8.3 renders the full ten-figure catalog of the reproduction domain doc §6.2 (not the five files listed by the roadmap), and the Diebold–Mariano figure is a candidate × comparators grid (raw p-value with the primary estimator plus the Holm decision), never a comparator × comparator matrix
description: Architecture Decision Record
when-use: Reference when asking why Stage 8.3 draws ten figures instead of the five of the roadmap, why there is no dm_matrix_plot, or before adding a figure that compares two comparators
keywords: [adr, evaluation, plots, catalog, diebold-mariano, holm, p8-rot, roadmap-amendment]
status: accepted
created_at: 2026-10-24
updated_at: 2026-10-24
adr_id: 8.3.0001
decision: The figure set of Stage 8.3 is the ten-row catalog of the reproduction domain doc §6.2 (reliability by τ, quantile score, sharpness, PICP × MPIW, DM candidate × comparators, OOS fan chart, loss differential with ACF, family importance / H3, VSN weights, native × conformal); the DM figure is a horizon × family-comparator grid coloured by the raw one-sided p-value of the primary (rectangular) estimator and annotated with that p-value and the Holm decision; comparator × comparator cells do not exist; the roadmap block is amended accordingly.
context_stage: 8.3-plots-and-final-report
bounded_context: evaluation
---

# ADR 8.3.0001 — Full figure catalog; DM as candidate × comparators

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The roadmap block of 8.3 (written at roadmap creation, 2026-06-22) lists five
plot files: `calibration_plot`, `dm_matrix_plot`, `picp_mpiw_plot`,
`oos_series_plot`, `contribution_plot`. The domain doc
`reproduction-equivalence-and-reporting.md`, accepted later at the Step 8 domain
gate (issue #208, 2026-10-22), fixes a ten-row catalog in §6.2, each row with a
primary source and a status label (P8-ROT, §9 items 14–17). The five extra
figures (quantile score, sharpness diagram, loss differential + ACF, VSN weights,
native × conformal) show quantities the preregistration declares (profile, H3,
conformal benchmark). The name `dm_matrix_plot` suggests the usual "p-value
matrix" over all model pairs; the doc §6.2 says "Células comparador × comparador
não existem: o gold não persiste esses DMs, e calculá-los seria teste novo"
(§6.1 item 5: a figure never requires a test the gold did not persist).

## Decision

1. Stage 8.3 renders the ten figures of doc §6.2, one panel per horizon (VSN:
   one "horizon-invariant" panel; H3: h+1 and h+7 side by side for comparison).
2. The DM figure is a grid with one row per horizon and one cell per comparator
   of the family; colour = raw one-sided DM p-value "candidate has lower loss"
   with the primary estimator (rectangular, ADR 6.5.0006) on a sequential
   colour-blind-safe map; annotation = raw p-value and Holm decision; row label
   confirmatory only where H1 passes in the scorecard, otherwise "descriptive
   (profile) — H2 not applicable".
3. The roadmap block of 8.3 is amended (files, contracts, layer) in the same
   change set as the concept.

## Alternatives considered

### Alternative A — Only the five roadmap plots
- **Pros:** fewer files and tests.
- **Cons:** leaves declared profile/H3/conformal quantities without the figure the
  domain doc fixed for them; the TCC text would cite numbers whose figure was
  never produced from persisted data.
- **Why rejected:** the domain doc is the higher, later source for the Step 8 gate.

### Alternative B — Comparator × comparator DM matrix
- **Pros:** familiar visual.
- **Cons:** the gold has no such DMs; computing them is a new test (doc §6.1
  item 5) outside the preregistered family and Holm correction.
- **Why rejected:** forbidden by doc §6.2 / §9 item 15.

## Consequences

### Positive
- Every figure of the text maps to a catalog row with a fixed status.

### Negative
- Ten figure assemblers instead of five (more unit tests).

### Neutral / trade-offs accepted
- Exploratory extra figures remain allowed by the doc but none is created here.

## References

- Domain doc reproduction-equivalence-and-reporting §2.3, §6.1, §6.2, §9 items 14–17
- ADR 6.5.0006 (primary estimator), 6.5.0007 (verdict tree)
- Concept 8.3 D1, D2
