---
title: ADR 6.1.0003 — Degeneracy is judged by an absolute tolerance on the grid spread, in units of y, supplied by the caller
description: Architecture Decision Record
when-use: Reference when implementing or questioning how the degeneracy gate decides that a grid (or a symmetric pair) collapsed, why the tolerance is absolute and not relative, or why the gate has no default tolerance
keywords: [adr, evaluation, degeneracy-gate, tolerance, dirac, collapse, absolute-tolerance, preregistration]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.1.0003
decision: A row is degenerate when the spread of its post-guardrail grid, max − min (= q_{τ_K} − q_{τ_1} on the monotone vector), is ≤ a finite, non-negative absolute tolerance in units of y that the caller must pass (no default in the domain; the value is preregistered in 6.5); a symmetric pair is partially collapsed under the same rule applied to q_u − q_l.
context_stage: 6.1-scoring-and-calibration-metrics
bounded_context: evaluation
---

# ADR 6.1.0003 — Absolute spread tolerance for the degeneracy gate

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The domain doc fixes the **semantics** of the degeneracy gate (§5.1, §5.3;
ADR 0.0.0011): total collapse of the grid (a Dirac); partial collapse of a
pair is a diagnostic; proper scores on all rows; calibration metrics only on
non-degenerate rows; the rate is always reported. It also says that "the
numeric tolerance of 'equal' is content of the preregistration" (§5.1) — the
**value** belongs to 6.5. What no document fixes is the **form** of the
comparison, which is part of the 6.1 contract (the gate's parameter).

Facts that constrain the form:

- The values are daily log-returns, which straddle zero; quantile grids of a
  near-collapsed forecast sit around 0 as often as around ±0.01.
- Python's `math.isclose` documents the two families: `rel_tol` is the
  "maximum difference for being considered 'close', relative to the magnitude
  of the input values"; `abs_tol` is the "maximum difference … regardless of
  the magnitude of the input values" (CPython 3.13 docstring, read on
  2026-09-28). A relative criterion shrinks to exact equality as the values
  approach 0, so the same physical spread (e.g. 1e-9) would be "degenerate"
  around 0.01 and "not degenerate" around 0 — the verdict would depend on the
  forecast's location, not on its spread.
- The declared degenerate baselines (`zero_return`, `historical_mean`) emit
  the same float at every level (`degenerate_grid`, ADR 5.2.0001), so their
  spread is exactly 0; the tolerance only matters for distributional models.
- On the post-guardrail (non-decreasing) vector, max − min = q_{τ_K} − q_{τ_1};
  the roadmap's "q_low == q_high" on the extreme pair is therefore the same
  event as total collapse.

Triage (`evidence-resolution`): class **C** — more than one defensible form;
decided by the ladder.

## Decision

- **Row:** degenerate ⇔ `max(guardrail_values) − min(guardrail_values) ≤ tolerance`.
- **Pair (diagnostic):** collapsed ⇔ `q_u − q_l ≤ tolerance`, reported per pair
  over the non-degenerate rows only (a degenerate row is trivially collapsed
  in every pair).
- `tolerance` is a required keyword argument, finite and ≥ 0, in units of y
  (the same unit as MPIW and IS_α — doc §4.3, FA5). No default in the domain:
  the value is preregistered in 6.5; tests pass it explicitly (0.0 reproduces
  exact equality).

Decision record:

```
[decision:C] 6.1-D-TOL — form of the "equal" test in the degeneracy gate
Escolha: absolute tolerance on the grid spread (max − min), caller-supplied, no default · Alternativas: relative tolerance (math.isclose rel_tol); exact equality only; tolerance as a fraction of the series' median spread · Degrau (C): 1 (doc §5.1: tolerance is preregistration content ⇒ a parameter; doc §4.3/FA5: units of y) e 5 (simplest well-defined near zero)
Base: CPython 3.13 `math.isclose.__doc__` "rel_tol … relative to the magnitude of the input values"; "abs_tol … regardless of the magnitude of the input values" [lido localmente]
Sensibilidade pré-registrada: nenhuma nesta Stage (6.5 pode pré-registrar mais de um valor de tolerância) · Reversível: sim
```

## Alternatives considered

### Alternative A — Relative tolerance (`math.isclose(a, b, rel_tol=…)`)

- **Cons:** degenerates to exact equality near zero, where returns live; the
  verdict depends on location.
- **Why rejected:** ill-posed for a variable that straddles 0.

### Alternative B — Exact equality only (`len(set(values)) == 1`)

- **Pros:** zero parameters.
- **Cons:** a model emitting a grid collapsed up to float noise (e.g. a
  booster whose leaves differ in the 15th digit) would never be caught, and
  the preregistration could not choose a value — contradicting doc §5.1.
- **Why rejected:** it is the special case `tolerance = 0.0` of the decision,
  which remains available.

### Alternative C — Tolerance relative to the series (e.g. fraction of the median spread)

- **Cons:** the threshold moves with the model being judged; a model that
  collapses often lowers its own bar.
- **Why rejected:** self-referential criterion, no source.

### Alternative D — Do nothing (hard-code a constant in the domain)

- **Why rejected:** would silently preregister a value the doc assigns to
  6.5.

## Consequences

### Positive

- The gate's verdict depends only on the spread, in the same unit as the
  sharpness metrics.
- 6.5 can preregister the value (and sensitivities) without touching code.

### Negative

- Every caller must choose a tolerance; tests must state it.

### Neutral / trade-offs accepted

- A tolerance too large would mark genuinely sharp forecasts as degenerate;
  choosing it is 6.5's job, with the rate always reported (ADR 0.0.0011).

## References

- Related ADRs: [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md),
  [4.3.0002](./4_3_0002-quantile-forecast-dense-grid-guardrail.md),
  [5.2.0001](./5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md),
  [6.1.0002](./6_1_0002-coverage-series-aligned-input-vo.md).
- Domain doc: [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md)
  §4.3, §5.1–§5.4.
- CPython 3.13 `math.isclose` (docstring); PEP 485.
