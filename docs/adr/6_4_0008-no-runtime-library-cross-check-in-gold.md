---
title: ADR 6.4.0008 — The gold refresh does not re-run ScoringBackend or InferenceBackend at runtime as a domain-versus-library quality check; the contract suites remain the oracle
description: Architecture Decision Record
when-use: Reference when proposing a runtime comparison of domain statistics against sklearn/scoringrules/statsmodels inside the gold pipeline, or when asking why RefreshGold consumes only McsBackend among the library ports
keywords: [adr, evaluation, scoring-backend, inference-backend, oracle, contract-tests, quality-checks, runtime]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.4.0008
decision: The option left open by ADR 6.1.0001 item 5 — using ScoringBackend (and, by extension, InferenceBackend) at runtime as a quality check that compares domain results with the libraries — is not adopted in 6.4; per-unit contract suites and the R fixtures stay the oracle (ADR 0.0.0021), and McsBackend is the only library port RefreshGold consumes, because it produces an input (bootstrap indices and b̂_sb) rather than a second opinion.
context_stage: 6.4-gold-builders-and-quality-gates
bounded_context: evaluation
---

# ADR 6.4.0008 — No runtime library cross-check

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

ADR 6.1.0001 item 5 left to 6.4 the option of calling `ScoringBackend` at
runtime as a "domain vs library" quality check. ADR 0.0.0021 fixes that
correctness is asserted per unit against an oracle; the `[fake, sklearn,
scoringrules]` and `[fake, statsmodels, arch]` suites, plus the versioned R
fixtures (ADR 6.2.0006, 6.3.0002), already prove agreement on the domains the
statistics run on. Issue #117 (reflection point 1c) noted the runtime cost
(statsmodels' Holm path runs `gc.collect()`, ≈ 0.25 s per call).

## Decision

`[decision:C] 6.4-C8 — runtime domain-vs-library check`
`Escolha: not adopted · Alternativas: WARN check comparing every report with the backends · Degrau (C): 1`
`Base: ADR 0.0.0021 "Correctness is asserted per unit against an oracle"; ADR 6.1.0001 item 5 (option, not requirement)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim (one more check in the registry)`

1. `RefreshGold` consumes `McsBackend` (production role fixed by ADR
   6.2.0004 item 7) and no other library port.
2. Reopening trigger: a disagreement found on real data that the contract
   domains do not cover (e.g. an input shape the suites never generate) — then
   a WARN check is one registry entry (ADR 6.4.0002).

## Alternatives considered

### Alternative A — WARN check comparing domain and library on every series

- **Why rejected:** repeats in production what the per-unit oracle already
  proves, adds library runtime to every refresh, and a disagreement would be
  a unit bug to fix, not a data-quality result to persist.

## Consequences

### Positive

- The refresh depends on one library port only.

### Negative

- A library/domain drift that appears only on shapes outside the contract
  domains would not be seen at runtime.

## References

- ADR 0.0.0021, 6.1.0001, 6.2.0003, 6.2.0004, 6.4.0002.
