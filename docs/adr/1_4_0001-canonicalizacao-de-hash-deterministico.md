---
title: ADR 1.4.0001 — Deterministic canonical hashing scheme with hardened float canonicalization and NaN/inf rejection
description: Architecture Decision Record
when-use: Reference before changing the canonical JSON hashing scheme, the float rounding precision, the volatile-key strip list, or the NaN/inf policy used by the Hasher adapter and the identity value objects
keywords: [adr, hashing, sha256, canonical-json, determinism, float, rounding, ulp, nan, infinity, fingerprint, run-id]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "1.4.0001"
decision: Replicate the old repo's canonical sha256-over-sorted-compact-JSON scheme, but harden it by rounding floats to a declared fixed precision before serialization and rejecting NaN/±inf with ValueError; strip volatile keys from config signatures
context_stage: 1.4-identity-and-fingerprints
---

# ADR 1.4.0001 — Deterministic canonical hashing scheme with hardened float canonicalization and NaN/inf rejection

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 1.4 rebuilds the project's deterministic identity layer: the value objects
`RunId`, `DatasetFingerprint`, `ConfigSignature` and `SplitFingerprint`, each a
sha256 hex string over a canonical payload, produced by a `Hasher` port-out
implemented by a `CanonicalJsonHasher` adapter. Identity must be **reproducible
across processes and platforms** — the whole reproducibility/audit story of the
project rests on "the same canonical inputs always yield the same `run_id` /
fingerprint" (Overview §3, §4 "Reprodutibilidade").

Forces at play:

- **A proven scheme already exists in the prior repo.** In
  `/home/marcelo/Code/financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py`
  the canonical form is `json.dumps(payload, sort_keys=True,
  separators=(",", ":"), ensure_ascii=False)` then `sha256(text.encode("utf-8")).hexdigest()`
  (lines 17-22). Config signatures `pop` the volatile keys
  `created_at/started_at/ended_at/timestamp` (lines 37-41). Split fingerprints
  `sorted()` each split before hashing (lines 44-55). Run ids hash 9 fields with
  `trial_number/fold/seed` nullable as part of the key (lines 101-124). This is a
  working contract; the silver layer it feeds is the source of truth. Replicating
  it faithfully preserves continuity and lets old results act as a regression
  oracle (Overview ASSUM-4).

- **The old scheme has a determinism hole on floats.** `compute_dataset_fingerprint`
  serializes `float(close_sum)` / `float(volume_sum)` **raw** (lines 73-74).
  CPython's `float.__repr__` is the shortest round-tripping decimal and is stable
  *within a CPython version on a given platform*, but `close_sum`/`volume_sum` are
  **sums produced by the new numeric stack** (pandas/numpy/pyarrow over re-derived
  data). Floating-point summation is not associative; the result can differ in the
  last ULP across library versions, BLAS backends, chunking, or platforms (notably
  the AMD ROCm target, ASSUM-2). A last-ULP difference flips the `repr`, flips the
  JSON, flips the hash — silently producing two different fingerprints for the
  "same" dataset. The pre-declared finding (ledger §B, Stage 1.4) explicitly
  requires hardening float canonicalization against exactly this.

- **The old scheme has no NaN/inf guard.** `json.dumps` with default
  `allow_nan=True` emits the bare tokens `NaN`, `Infinity`, `-Infinity` — which are
  **not valid JSON** and have no stable cross-tool meaning. A NaN/inf reaching a
  `close_sum`/`volume_sum` signals corrupted upstream data, not a legitimate state
  to fingerprint. The old test suite
  (`tests/unit/infrastructure/schemas/test_analytics_store_schema.py`) covers key
  order, volatile-key ignore, split order-invariance and run_id determinism, but
  has **no** coverage for float canonicalization or NaN/inf — a gap this Stage must
  close.

- **The domain must stay pure.** The value objects live in `shared/domain` and may
  only use the standard library (import-linter `domain-purity`, Stage 1.3). The
  canonicalization logic (rounding, NaN/inf rejection) therefore cannot leak into
  the domain VOs as bespoke code; it belongs **behind the `Hasher` port**, in the
  adapter, where it is centralized and contract-tested.

## Decision

The `CanonicalJsonHasher` adapter replicates the old canonical scheme **and**
hardens it, with the policy centralized in the adapter (the domain VOs only build
the payload dict and delegate):

1. **Canonical form (replicated verbatim):** `json.dumps(payload, sort_keys=True,
   separators=(",", ":"), ensure_ascii=False)`, then sha256 of the UTF-8 bytes,
   hex digest. `hash_text(text)` hashes the UTF-8 bytes of the string directly
   (used for `feature_set_hash` via `"|".join(features_ordered)`, order-sensitive).

2. **Float canonicalization by declared rounding:** every `float` in the payload is
   rounded to a **declared fixed precision of 10 decimal places** (`round(x, 10)`)
   before serialization. `int` values stay `int`. Ten decimals is far below the
   noise floor of a last-ULP summation difference yet far above any precision a
   dataset fingerprint needs to discriminate distinct datasets (`close_sum` /
   `volume_sum` are large aggregates; a 1e-10 absolute difference is not a
   meaningful distinction). The precision is a single documented constant in the
   adapter, trivially changeable later. Booleans are left to JSON's native
   `true`/`false` (Python `bool` is not rounded).

3. **NaN/±inf rejection (fail-fast):** before serializing, the adapter checks each
   float with `math.isnan` / `math.isinf` and raises `ValueError` on any NaN or
   ±inf. `json.dumps` is additionally called with `allow_nan=False` as a
   belt-and-suspenders guard (it raises `ValueError` on non-finite floats), so even
   a non-finite value reaching `json.dumps` cannot silently produce invalid JSON.

4. **Volatile-key strip (replicated):** `ConfigSignature` removes
   `created_at/started_at/ended_at/timestamp` from a defensive copy of the config
   dict before hashing, exactly as `compute_config_signature` does. `None` maps to
   JSON `null` natively (no special handling).

The `Hasher` **port** declares this semantics in its docstring (sort_keys, floats
canonicalized, NaN/±inf rejected, None→null, key order irrelevant) so that any
adapter — including the in-memory `FakeHasher` used in tests — must honor the same
contract. A single parametrized contract test pins fake and real to identical
behavior.

## Alternatives considered

### Alternative A — Serialize floats raw (status quo of the old repo)
- **Description:** Keep `float(x)` straight into `json.dumps`, relying on CPython's
  `repr` stability.
- **Pros:** Zero code; bit-identical to the old fingerprints when the sums match.
- **Cons:** Reintroduces the last-ULP determinism hole the new numeric stack makes
  realistic (pandas/numpy/ROCm); two runs over the "same" data could fingerprint
  differently, silently breaking the reproducibility/audit invariant.
- **Why rejected:** Directly contradicts the pre-declared hardening finding
  (ledger §B) and the project's reproducibility critério de sucesso (Overview §4).
  The cost of a rounding call is negligible; the risk it removes is the core value
  of a fingerprint.

### Alternative B — Map NaN/±inf to `null` (or a sentinel string)
- **Description:** Instead of failing, replace non-finite floats with `null` or a
  sentinel before hashing.
- **Pros:** Never raises; pipeline keeps running.
- **Cons:** Masks corrupted upstream data; two genuinely different corruption modes
  could collapse to the same fingerprint; a "valid-looking" hash gives false
  confidence in a dataset that is actually broken.
- **Why rejected:** A fingerprint exists to detect divergence honestly. Hiding
  corruption behind a sentinel defeats the purpose. Fail-fast surfaces the bug at
  the boundary where it is cheapest to diagnose.

### Alternative C — Quantize floats to integers (e.g. cents / fixed scale)
- **Description:** Multiply by a fixed scale and cast to `int` (decimal-fixed-point)
  instead of rounding to N decimals as float.
- **Pros:** Fully integer payload, no float repr in the JSON at all.
- **Cons:** Requires a per-field scale choice (price vs volume differ by orders of
  magnitude), overflows for very large `volume_sum`, and adds modeling decisions
  (which scale?) that buy nothing over `round(x, 10)` for a *fingerprint*.
- **Why rejected:** More machinery, more knobs, same determinism guarantee.
  `round(x, 10)` is the simpler-and-swappable choice; fixed-point can be revisited
  if a future need (e.g. money arithmetic) actually demands it.

### Alternative D — Hash a stable binary encoding (e.g. `struct`/`pickle`) instead of JSON
- **Description:** Serialize the payload to a binary form and hash the bytes.
- **Pros:** No JSON formatting concerns.
- **Cons:** Loses the human-auditable, grep-friendly canonical JSON the old scheme
  and the silver store rely on; pickle is version-fragile and unsafe; the old
  contract is JSON-based, so a binary scheme breaks regression-oracle continuity.
- **Why rejected:** Throws away the proven, auditable JSON contract for no
  determinism gain (JSON + rounding is already deterministic).

### Alternative E — Do nothing / status quo
- **Description:** Reuse the old functions unchanged.
- **Why not acceptable:** Same as A plus the NaN/inf hole of B's absence; the old
  code couples hashing to infrastructure and has no float/NaN tests. The Stage's
  whole point is to move identity into a pure, tested, hardened domain+adapter pair.

## Consequences

### Positive
- The reproducibility invariant ("same canonical inputs → same hash, across
  processes/platforms") holds even when float sums differ in the last ULP between
  library versions or hardware (notably ROCm) — the failure mode the rebuild was
  meant to eliminate.
- Corrupted data (NaN/inf) is caught at the fingerprint boundary with a clear
  `ValueError`, not silently absorbed into a misleading hash.
- The canonicalization policy lives in exactly one place (the adapter), is
  contract-tested against the fake, and is a single documented constant to tune.
- The JSON/sha256 scheme stays byte-compatible with the old repo for non-float
  payloads (config/split/run_id), preserving the regression-oracle relationship.

### Negative
- Fingerprints are **not** bit-identical to the old repo for dataset payloads whose
  float sums carried >10 significant decimals of "noise" — but this is intended
  (ASSUM-4: equivalence by declared tolerance, not bit-identity), and dataset
  fingerprints are re-derived from re-ingested bronze anyway.
- A legitimate-but-extreme value rounding to the same 10-decimal bucket as another
  could in principle collide; for `close_sum`/`volume_sum` aggregates this is not a
  practical concern, but it is a (documented) limit of the chosen precision.

### Neutral / trade-offs accepted
- We accept fixing the rounding precision now (10 decimals) and treating it as a
  swappable constant rather than searching for a "perfect" precision — simple and
  reversible beats over-engineered.
- We accept rejecting (not coercing) non-finite floats, trading "always runs" for
  "never lies".

## Implementation notes

- Policy lives in `src/financial_forecasting/shared/adapters/out/hashing/canonical_json_hasher.py`
  (rounding constant + `_canonicalize` helper applied recursively to the payload
  before `json.dumps(..., allow_nan=False)`).
- The `Hasher` port docstring
  (`shared/application/ports/out/hasher.py`) states the canonical semantics so the
  `FakeHasher` (`tests/fakes/shared/hasher.py`) implements the *same* rounding and
  NaN/inf rejection; the contract test
  (`tests/contract/shared/test_hasher_contract.py`) parametrizes over both.
- The value objects (`shared/domain/value_objects/*.py`) stay stdlib-only: they
  build the payload dict (and strip volatile keys / `sorted()` splits as
  appropriate) and call `hasher.hash_mapping` / `hasher.hash_text`. The
  NaN/inf `ValueError` is raised by the hasher, surfaced through the VO factory.

## References

- Related ADRs: [0.0.0019](./0_0_0019-hexagonal-enforced.md) (domain purity enforced
  by tooling — why the canonicalization lives in the adapter, not the VO);
  [1.3.0001](./1_3_0001-import-linter-as-architecture-fitness-function.md) (the
  domain-purity contract this Stage keeps green).
- Overview: §3/§4 (traceability by `run_id`/`config_signature`/`split_fingerprint`,
  reproducibility critério de sucesso), ASSUM-2 (ROCm), ASSUM-4 (equivalence by
  declared tolerance).
- Reference repo (scheme replicated + holes hardened):
  `/home/marcelo/Code/financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py`
  (`_canonical_json`/`_sha256_text` 17-22; `compute_config_signature` 37-41;
  `compute_split_fingerprint` 44-55; `compute_dataset_fingerprint` 58-77 incl. raw
  float at 73-74; `compute_run_id` 101-124; `compute_feature_set_hash` 33-34);
  the ad-hoc divergent fingerprint discarded (`run_baselines_use_case.py:365-389`).
- Decision ledger: `docs/autonomous-run-decision-ledger.md` §B (pre-declared
  decision for Stage 1.4).
- External: IEEE 754 floating-point non-associativity of summation; `json` module
  `allow_nan` parameter (emits invalid `NaN`/`Infinity` tokens when true).
