---
title: ADR 8.2.0004 — The A1 (realized target) tolerance of the 8.2 equivalence audit is half an ulp of float32 at each point — the prior evidence's effective storage precision — under the verified precondition that every prior value is exactly representable in float32; declared as a deviation before any model number of the prior evidence is computed
description: Architecture Decision Record
when-use: Reference when reading the A1 result of the 8.2 equivalence report, before changing the A1 tolerance, or when asking why the model comparison after A1 is labelled a post-hoc deviation
keywords: [adr, evaluation, equivalence, eq-must, a1, storage-precision, float32, ulp, deviation, prior-evidence]
status: accepted
created_at: 2026-10-23
updated_at: 2026-10-23
adr_id: 8.2.0004
decision: A1 passes at a point when |y_new − y_prior| ≤ half an ulp of float32 at that point, provided every y_prior of the intersection is exactly representable in float32 (checked; if any is not, the double rule of concept D13 applies unchanged); human decision B3 (option 2) on issue #232, taken after the A1 diagnosis and before any model number of the prior evidence was computed; the model comparison (A10/A11) that A1 now unblocks is labelled in the internal report as a post-hoc deviation.
context_stage: 8.2-equivalence-audit
bounded_context: evaluation
---

# ADR 8.2.0004 — A1 tolerance by the effective float32 storage precision

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — amends concept 8.2 D13 and A9 (deviation, human decision B3).

## Context

Domain doc §5.4 (A1): on the intersection, the realized y of both evidences
must coincide "within the storage precision of the prior: half an ulp of the
stored type at the value's magnitude", the precision read from the schema
(§5.2). The prior column `y_true` is physically `double`, so concept 8.2 D13
fixed |Δ| ≤ 2⁻⁵³·|y_prior|.

In the real E4 run, the pre-declared D13 diagnosis (item 4, float32 path)
showed that the prior target was stored rounded to float32 inside a double
column: y_prior = float32(y_new) at 937/937 points on both horizons; max
relative |Δ| = 0.978·2⁻²⁴. A1 under the double rule failed at 934/937 points,
explained as category "alvo"; by D13 the model comparison (A10/A11) was marked
`not_compared:A1`. No model number of the prior evidence had been computed.

## Decision

Human decision B3, option 2 ("emendar A1 já"), registered on issue #232
(comment of 2026-10-23):

1. **Tolerance.** A1 passes at a point when |y_new − y_prior| ≤ ½ ulp of
   float32 at that point — the prior's **effective** storage precision, which
   is what doc §5.4 asks for ("dentro da precisão de armazenamento do anterior").
2. **Precondition (checked).** Every y_prior in T∩ is exactly representable in
   float32 (`float(np.float32(y)) == y`). If any point fails it, the double
   rule of D13 applies unchanged for that horizon.
3. **Order.** The amendment is committed before any model number of the prior
   evidence is computed; E4/E5 are re-run under it.
4. **Labelling.** The internal report labels the model comparison (A10/A11)
   that A1 now unblocks as a **post-hoc deviation** (rule changed after seeing
   the A1 diagnosis), with this ADR as the reference.

## Alternatives considered

### Option 1 — Keep A1 under the double rule
- **Pros:** no rule change after execution.
- **Cons:** A1 fails by storage artifact, not by a different target; the model
  comparison stays `not_compared` on both horizons.
- **Why rejected (by the human):** the doc's rule is the storage precision of the
  prior, and the effective one is float32.

### Option 2 — Amend A1 to the effective float32 precision now (chosen)
- See Decision.

### Option 3 — Keep A1 failed and defer the amendment to a later issue
- **Pros:** the 8.2 closes without a deviation.
- **Cons:** postpones the comparison the Stage exists for; same deviation later.
- **Why rejected (by the human):** no gain in rigor, only delay.

## Consequences

### Positive
- A1 measures the target definition, not a storage artifact; A10/A11 can run.

### Negative
- A rule changed after execution: the model comparison is a post-hoc deviation
  in the internal report (not used in the TCC text — P-EDIT).

### Neutral / trade-offs accepted
- Reversible: dropping the amendment restores D13's double rule and
  `not_compared:A1`.

## References

- Domain doc reproduction-equivalence-and-reporting §5.2, §5.4, §5.6
- Concept 8.2 D9 (D-M6), D13, A9; ADR 8.2.0003
- Issue #232, decision B3 (2026-10-23)
