---
title: ADR 7.2.0005 — The 7.1 reproduction policy moves to inference/domain as pure functions over primitives; the silver-row plumbing of the calib verification stays in RunInference
description: Architecture Decision Record
when-use: Reference when touching reproduction_mode, within_mode, the float32 tolerances or the C7/C8 checks of RunInference, or when asking why the inference domain does not import the modeling probe keys nor QuantileForecast
keywords: [adr, inference, domain, reproduction, strict, tolerance, refactor, run-inference, bc-independence, code-keys]
status: accepted
created_at: 2026-10-17
updated_at: 2026-10-17
adr_id: 7.2.0005
decision: reproduction_mode, within_mode, the tolerance constants, the strict/tolerance names and the key-set comparison of the C7 test reproduction move from run_inference.py to inference/domain/services/reproduction_policy.py as pure functions over primitives, with the ignored environment keys passed by the caller (the use case still imports CODE_KEYS/DIRTY_KEY from the modeling probe port); the row-field checks of _verify_decision (identity columns, timestamps, guardrail_applied, QuantileForecast values) stay in the use case and call the domain criterion, so no new bc-independence edge is created and RunInference's behavior is unchanged.
context_stage: 7.2-conformal-cqr
bounded_context: inference
---

# ADR 7.2.0005 — Reproduction policy in the inference domain

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.2 concept (issue #158), 2026-10-17. Executes the
`[decision]` F3 of technical 7.1 §7 (2026-10-12: "adiar para a 7.2, que já cria
o domain do `inference`, e mover a política junto"), refining which symbols
move.

## Context

F3 (stage audit of 7.1, D-bis #10) listed `reproduction_mode`, `within_mode`,
`TOLERANCE_ATOL`/`TOLERANCE_RTOL` and `_verify_decision` as pure policy living
in the use case. Two facts limit a literal move:

- `reproduction_mode` ignores `CODE_KEYS`/`DIRTY_KEY`, imported from the
  modeling probe port — an `inference.domain → modeling.application` import
  is barred by `bc-independence` (no runtime edge from the inference domain is
  declared) and by LAYOUT §3 (the domain depends on nothing outside itself
  and `shared`); concept 7.1 I6 forbids redeclaring the keys.
- `_verify_decision` reads silver `Row` mappings and `QuantileForecast`
  (analytics_store VO); moving it would add an
  `inference.domain → analytics_store.domain` data edge for plumbing, not
  policy.

## Decision

`[decision:C] 7.2-F3 — what moves to inference/domain`
`Escolha: the pure criterion (mode, value comparison, key-set comparison) over primitives; ignored keys as a parameter; row plumbing stays · Alternativas: move everything incl. _verify_decision with a new data edge; keep all in the use case · Degrau: 1 (LAYOUT §3/§7 "Domain tem zero I/O", ADR 0.0.0053; technical 7.1 §7 F3) e 5`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. `inference/domain/services/reproduction_policy.py` (stdlib):
   `STRICT`, `TOLERANCE`, `TOLERANCE_ATOL = 1e-5`, `TOLERANCE_RTOL = 1.3e-6`,
   a frozen `ReproductionMode(name, reason, forced)`,
   `reproduction_mode(reference, current, justification, *, ignored_keys)`,
   `within_mode(*, new, ref, center, scale, mode)` and
   `compare_reproduction(reference, predicted, *, mode, center, scale)` (key
   sets equal, nothing-compared fail-closed, failures counted, max |Δ| and
   max |Δ|/s) returning a frozen `ReproductionComparison`.
2. `RunInference` imports them, passes `ignored_keys = {*CODE_KEYS,
   DIRTY_KEY}`, keeps its error types and messages (C7/C8), and keeps
   `_verify_decision`'s row checks, calling `within_mode`. The CLI adapter
   `inference/adapters/in/cli/inference_commands.py`, which imports `STRICT`
   from `run_inference`, switches to the domain module (listed in the files to
   modify; no re-export left in the use case).
3. Behavior is unchanged: every 7.1 test passes without changing an assertion;
   the policy gets its own unit tests in `tests/unit/features/inference/domain/`.

## Alternatives considered

### Alternative A — Move `_verify_decision` too
- **Why rejected:** new cross-slice data edge for silver plumbing; the domain
  would read persisted rows.

### Alternative B — Leave it in the use case
- **Why rejected:** contradicts F3; the domain of `inference` now exists.

## Consequences

### Positive
- The reproduction rule is testable without fakes of ports.

### Negative
- One more module and an explicit `ignored_keys` parameter.

### Neutral / trade-offs accepted
- C7/C8 error wording stays in the application layer.

## References

- Technical 7.1 §7, `[decision]` F3 (2026-10-12).
- Related ADRs: [7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md),
  [7.1.0001](./7_1_0001-checkpoint-prediction-supplied-by-modeling-through-consumer-port.md),
  [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md).
- Issue: [#158](https://github.com/MarceloSanC/financial-forecasting/issues/158).
