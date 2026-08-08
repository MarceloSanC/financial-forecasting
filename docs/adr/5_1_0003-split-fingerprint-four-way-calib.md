---
title: ADR 5.1.0003 — Extend SplitFingerprint to a four-way split with an optional calibration partition
description: Architecture Decision Record
when-use: Reference when fingerprinting a train/early-stop/calib/test fold, or before adding a modeling-local fingerprint that duplicates the shared canonical primitive
keywords: [adr, split-fingerprint, calibration, reproducibility, hashing, dry, walk-forward, modeling, identity]
status: accepted
created_at: 2026-07-04
updated_at: 2026-07-04
adr_id: "5.1.0003"
decision: The shared SplitFingerprint value object (Stage 1.4) is extended with an optional, backward-compatible calib partition so the split identity attests the dedicated calibration boundary; a modeling-local fingerprint is rejected as duplication
context_stage: 5.1-walk-forward-harness
bounded_context: modeling
---

# ADR 5.1.0003 — SplitFingerprint extended to a four-way split (optional calib)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

`SplitFingerprint` (Stage 1.4) is the project's single canonical primitive for
the reproducible identity of a data split: a sha256 over the canonical JSON of
`{train, val, test}`, each list sorted before hashing, delegated to the `Hasher`
port. Stage 5.1 introduces a **four-way** split — `train`, `early_stop`, `calib`,
`test` — where the `calib` block is a methodologically first-class partition whose
*dedication* is load-bearing for the conformal coverage claim (ADR 5.1.0002).

The 1.4 `compute` classmethod accepts only `train`/`val`/`test`. So the fold's
identity has to be expressed through a 3-slot primitive that does not know about
`calib`. Forces:

- **Calibration is not a mere sub-slice of validation.** If `calib` is folded into
  `val` for the fingerprint, two folds with identical `train`/`val`/`test` but
  different `calib` boundaries would produce the **same** fingerprint — a
  collision that hides the very boundary whose dedication we must attest and
  reproduce.
- **Single canonical primitive (DRY).** The project deliberately keeps one place
  where split canonicalization lives (1.4 / ADR 1.4.0001); a second, parallel
  fingerprint would duplicate the canonicalization semantics and risk drift.
- **Backward compatibility.** Stage 1.4 and any existing 3-way caller must keep
  producing the exact same fingerprint they do today — a done, shared contract
  must not silently change value.
- **Scope.** `split_fingerprint.py` lives in `shared/domain` (Stage 1.4), outside
  the `modeling` bounded context whose files Stage 5.1 nominally creates; touching
  it is a cross-stage, additive change that must be explicit.

## Decision

**Extend the shared `SplitFingerprint.compute` with an optional keyword-only
`calib: Sequence[str] | None = None`.** When `calib` is provided, the canonical
payload becomes `{"train": sorted(train), "val": sorted(val), "calib":
sorted(calib), "test": sorted(test)}`; when omitted, the payload is byte-for-byte
what it is today, so every existing 3-way caller yields an identical fingerprint.
Stage 5.1 passes `early_stop` as `val` and the dedicated `calib` block as `calib`,
so each `FoldSplit` fingerprint attests all four boundaries.

This keeps one canonical split-identity primitive project-wide (honoring the
roadmap's `contratos_consumidos: SplitFingerprint (1.4)`), extends it additively,
and makes the calibration boundary a first-class part of the fold's identity.

## Alternatives considered

### Alternative A — Reuse SplitFingerprint as-is, folding calib into val

- **Description:** fingerprint `{train, val = early_stop ∪ calib, test}`.
- **Pros:** zero change to the shared 1.4 VO; least code.
- **Cons:** the calib boundary disappears from the split identity; two folds
  differing only in the early-stop/calib partition collide; reproducibility cannot
  attest that calib was dedicated.
- **Why rejected:** ADR 5.1.0002 makes calib dedication load-bearing; an identity
  that cannot distinguish it is unsafe for a confirmatory, pre-registered protocol.

### Alternative B — New modeling-local `FoldFingerprint`

- **Description:** a fresh fingerprint VO in `modeling.domain` hashing all four
  lists, leaving 1.4 untouched.
- **Pros:** keeps 1.4 frozen; stays within the `modeling` BC.
- **Cons:** duplicates the canonical-hash concern in a second place (drift risk
  against ADR 1.4.0001); contradicts the roadmap's declaration that 5.1 *consumes*
  `SplitFingerprint (1.4)`.
- **Why rejected:** duplication of a deliberately-singular primitive is a worse
  long-term cost than an additive, backward-compatible extension.

### Alternative C — Do nothing / status quo

- Leaving the fingerprint 3-way means the fold identity is blind to calib. Not
  acceptable given ADR 5.1.0002.

## Consequences

### Positive

- One canonical split-identity primitive covers both 3-way (Steps 1–4) and 4-way
  (Step 5+) splits.
- Fold reproducibility attests the dedicated calibration boundary — no collisions.
- Existing 3-way callers are provably unchanged (optional param, default `None`).

### Negative

- A Stage-1.4 shared artifact is modified during Stage 5.1 (cross-stage, additive).
  Mitigated by the backward-compatibility test (3-way cases keep their exact
  fingerprints) and by this ADR recording the change.

### Neutral / trade-offs accepted

- The parameter name stays `val` (not renamed to `early_stop`) to preserve the
  1.4 signature; Stage 5.1 maps `early_stop → val` at the call site.

## Implementation notes

- Add the optional `calib` keyword to `SplitFingerprint.compute`; include it in the
  payload only when not `None` (so the omitted-case payload is unchanged).
- Extend `tests/unit/shared/domain/value_objects/test_split_fingerprint.py` with a
  4-way case and a case proving a 3-way call is identical to the pre-change value.

## References

- Related ADRs: [1.4.0001](./1_4_0001-canonicalizacao-de-hash-deterministico.md)
  (canonical deterministic hashing), [5.1.0002](./5_1_0002-dedicated-calibration-partition.md)
  (why calib is first-class).
- Source: `src/financial_forecasting/shared/domain/value_objects/split_fingerprint.py`
  (Stage 1.4); roadmap `docs/roadmap.md` Stage 5.1 (`contratos_consumidos`).
- Conversation: session decision 2026-07-04 (question answered after the
  conformal-calibration literature review; see ADR 5.1.0002 references).
