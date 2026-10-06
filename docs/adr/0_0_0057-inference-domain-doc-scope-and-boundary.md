---
title: ADR 0.0.0057 — Single inference domain doc covering Step 7, with boundaries to modeling (Step 5) and evaluation (Step 6)
description: Architecture Decision Record
when-use: Reference when questioning why the Step 7 domain gate is satisfied by one doc (conformal-benchmark-and-feature-attribution.md), why it does not re-derive coverage metrics, the bootstrap or the preregistration machinery, or why the roadmap's orphan vocabulary ("contrato P2", "≥2/3", "N+1") is abandoned or defined there
keywords: [adr, domain-doc, inference, conformal-benchmark-and-feature-attribution, scope, boundary, step-7, cqr, h3, explainability, api, doc-category]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 0.0.0057
decision: The Step 7 domain gate is satisfied by a single doc, docs/domain/inference/conformal-benchmark-and-feature-attribution.md, covering deterministic inference (7.1), the CQR coverage benchmark (7.2), family attribution for H3 (7.3) and the API payload concept (7.4); it consumes the modeling and evaluation docs by pointer only, defers implementation to the Stages' technical.md, and abandons or defines the roadmap's orphan vocabulary.
context_stage: 0.0-global
bounded_context: inference
---

# ADR 0.0.0057 — Single inference domain doc covering Step 7

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — ratified on 2026-10-06 by delegation of the human (Marcelo),
together with the inference domain doc (issue #150); the Step 7 gate is
closed.

## Context

No Stage of Step 7 may start without an `accepted` domain doc for the
`inference` bounded context (ADR 0.0.0003; `PROMPT-step-single-session.md`
§1). ADR 0.0.0054 excluded conformal/CQR from the evaluation doc and promised
that the Step 7 doc would reuse the coverage definitions without re-derivation.
The four Stages of Step 7 (7.1–7.4) share one object — the candidate TFT's
7-quantile grid per horizon — and one discipline: per horizon, seeds as means,
descriptive (never causal) language, preregistered reading rules.

Forces:

- 7.1 (reproduce the grid), 7.2 (recalibrate pairs of it) and 7.3 (attribute
  its loss to feature families) all rest on the same object and the same seed
  and per-horizon rules; three docs would copy them.
- The coverage metrics (ĉ(τ), PICP/MPIW, Wilson, hits), the stationary
  bootstrap and the preregistration machinery already live in the evaluation
  doc; re-deriving them would create two sources that drift.
- The API (7.4) has no theory of its own, only a labelling contract.
- The roadmap text of Step 7 carries vocabulary defined nowhere in the repo
  ("contrato P2", "ablação explanatória (N+1)", "triangulação ≥2/3") and some
  claims that the research contradicts (unqualified "bit-a-bit"; a new
  guardrail service; "pré-registrada em ADR").

## Decision

Write **one** domain document,
[`docs/domain/inference/conformal-benchmark-and-feature-attribution.md`](../domain/inference/conformal-benchmark-and-feature-attribution.md),
to satisfy the Step 7 gate. Its scope:

- **four blocks** — deterministic inference (§3), CQR as coverage benchmark
  (§4), family attribution for H3 (§5), the API payload concept (§6) — plus
  shared fundamentals (§2), preregistration and blinding (§7), a per-Stage
  consumption map (§1);
- a **boundary section** (§8) that consumes the modeling doc (rearrangement,
  TFT typing, early-stop ≠ calib, cohort) and the evaluation doc (L_t, coverage
  definitions, bootstrap, seeds, preregistration) **by pointer only**;
- **excluded:** implementation specs (where calib predictions are persisted,
  numeric tolerances, MAPIE's exact role, preregistration file form, payload
  schema) — `technical.md` of each Stage;
- the orphan roadmap vocabulary is **abandoned** ("contrato P2", "≥2/3") or
  **defined** ("N+1" = 4 ablated families + the full reference model; VSN,
  NexCP, ACI, EnbPI, split-CQR) in doc §9; the roadmap text of Step 7 and the
  8.1 dependency on 7.3 are corrected in the same PR.

Methodological forks were triaged with the `evidence-resolution` skill
(2026-10-05/06): E/C forks closed by the agent and recorded in doc §10.1; the
two P forks (role of the VSN in H3; ablation design) were decided by the human
on 2026-10-06. The load-bearing ones are recorded in
[ADR 0.0.0007](./0_0_0007-h3-family-contribution-across-horizons.md) (H3) and
[ADR 0.0.0008](./0_0_0008-native-quantiles-with-conformal-benchmark.md)
(native quantiles + CQR benchmark).

## Alternatives considered

### Alternative A — One doc per Stage (7.1–7.4)
- **Pros:** local to each `concept.md`.
- **Cons:** the object, the seed rule and the per-horizon rule are the same in
  7.1–7.3; 7.4 has no theory; four docs would copy the core.
- **Why rejected:** same reasoning as ADR 0.0.0051 Alternative B and ADR
  0.0.0054 Alternative A.

### Alternative B — Two docs (conformal; explainability)
- **Pros:** each topic has a distinct literature.
- **Cons:** both reuse the same seed/per-horizon/preregistration core and the
  same 7.1 object; the boundary to evaluation would be stated twice.
- **Why rejected:** the shared core outweighs the topical split; splitting
  later is cheap (supersede this ADR).

### Alternative C — Keep the roadmap's vocabulary
- **Pros:** no roadmap edits.
- **Cons:** "contrato P2" and "N+1" are undefined; "≥2/3" promises a
  triangulation that the VSN cannot provide here (ADR 0.0.0007).
- **Why rejected:** undefined vocabulary cannot be audited (ADR 0.0.0054
  Alternative C).

## Consequences

### Positive
- Step 7 has a single citable theory source with a Stage → section map.
- The coverage and preregistration theory keeps one home (evaluation doc).

### Negative
- A long doc; mitigated by the consumption map.
- Five items are flagged in the doc (§5.7) as still open for Stage 7.3's
  preregistration (interval level; multiplicity; negative importances;
  pairing key between horizons; joint bootstrap block), and one as an
  out-of-scope issue to be opened (the volatility features' family).

### Neutral / trade-offs accepted
- The doc was ratified (`accepted`) on 2026-10-06 by delegation of the human;
  the Step 7 gate is closed.

## References

- [ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md),
  [ADR 0.0.0051](./0_0_0051-modeling-domain-doc-scope-and-boundary.md),
  [ADR 0.0.0054](./0_0_0054-evaluation-domain-doc-scope-and-boundary.md),
  [ADR 0.0.0007](./0_0_0007-h3-family-contribution-across-horizons.md),
  [ADR 0.0.0008](./0_0_0008-native-quantiles-with-conformal-benchmark.md),
  [ADR 6.5.0008](./6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md).
- Originating issue: [#150](https://github.com/MarceloSanC/financial-forecasting/issues/150).
