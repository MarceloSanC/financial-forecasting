---
title: ADR 3.5.0002 — Regime/flag derived features (volatility_regime, trend_regime, stress_tail_return_flag) are persisted as float64 with NaN during warmup, matching the regression oracle, even though the FeatureRegistry declares int64
description: Architecture Decision Record
when-use: Reference before changing the dataset dtype of regime/flag features, before reconciling the registry int64 declaration with the parquet float64 reality, or before tightening the pandera dataset schema dtypes
keywords: [adr, dtype, regime, flag, volatility-regime, trend-regime, stress-tail, nan, warmup, float64, int64, oracle, regression, pandera, feature-engineering, technical-debt]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "3.5.0002"
decision: volatility_regime / trend_regime / stress_tail_return_flag are persisted (and validated by the pandera dataset schema) as float64 carrying NaN on warmup rows — matching the regression oracle — rather than as Int64 nullable, even though the FeatureRegistry declares their dtype as int64; the registry/parquet mismatch inherited from the old project is recorded as conscious technical debt
context_stage: 3.5-dataset-builder-and-contracts
---

# ADR 3.5.0002 — Regime/flag features are float64 with NaN on warmup

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Three derived features encode discrete states:
`volatility_regime` (0/1/2 from trailing terciles), `trend_regime`
(-1/0/1 from an EMA spread deadband) and `stress_tail_return_flag` (tail-return
flag). All three are **shifted, window-based** derivations, so their first
`warmup` rows are undefined.

The `FeatureRegistry` (3.4) declares `dtype="int64"` for these specs
(`feature_registry.py:482/494/504`). But the **regression oracle** —
`data/processed/dataset_tft/AAPL/dataset_tft_AAPL.parquet` (4023 rows × 62
columns, column order confirmed) — stores them as **float64**. The reason is
mechanical: the warmup rows hold `NaN`, and `NaN` is a float; a plain int64 array
cannot represent missing, so the column gets promoted to float64 on write. The
old project is therefore **internally inconsistent**: its registry says `int64`
while the parquet it produced is `float64`.

This Stage's contract (I7) is **column/dtype parity with the oracle**, not
bit-identity. The pandera dataset schema must declare a dtype for these columns;
whatever it declares must match what the assembler produces and what the oracle
holds, or regression comparison breaks.

Forces:
- Oracle parity (4023×62, dtypes included) is a hard acceptance criterion (A5/A6).
- The discrete semantics (0/1/2; -1/0/1; 0/1) suggest an integer type.
- The warmup rows are genuinely missing and must be representable.

## Decision

Persist and validate `volatility_regime`, `trend_regime` and
`stress_tail_return_flag` as **float64**, carrying `NaN` on the warmup rows —
matching the regression oracle exactly. The pandera dataset schema declares these
three columns as `float64` (nullable on the warmup prefix), not as `int64` /
`Int64`.

The `FeatureRegistry`'s `int64` declaration for these specs is **kept as-is** (it
documents the *logical* type and the spec hash must not churn), and the
registry-vs-parquet dtype mismatch is recorded here as **conscious technical
debt**: the registry expresses intent (discrete), the dataset expresses reality
(float64 because warmup is NaN). Reconciliation (e.g. a `null_policy`-driven
"logical dtype vs storage dtype" split, or pandas nullable `Int64`) is deferred —
it is simple-and-replaceable and not worth inflating this integration Stage.

## Alternatives considered

### Alternative A — pandas nullable `Int64` (capital-I)
- **Description:** use the masked nullable integer type so warmup rows are `<NA>`
  while values stay integral.
- **Pros:** keeps the discrete semantics; honors the registry `int64`.
- **Cons:** the oracle parquet is plain `float64`, so this **breaks regression
  parity** (dtype mismatch on read-back); `Int64` round-trips through parquet/
  pyarrow with extension-type metadata that the old artifact does not carry;
  more moving parts in the schema. **Why rejected:** fails the oracle-parity
  acceptance criterion for a cosmetic dtype gain.

### Alternative B — int64 with a sentinel for warmup (e.g. -1 or a magic value)
- **Description:** avoid NaN by encoding "missing" as a reserved integer.
- **Pros:** stays integral; no float promotion.
- **Cons:** invents a sentinel the model would have to learn to ignore; collides
  with the legitimate `-1` of `trend_regime`; diverges from the oracle. **Why
  rejected:** semantically wrong (sentinel ≠ missing) and breaks parity.

### Alternative C — fix the registry to say float64 now
- **Description:** change the three specs' `dtype` to `float64` to remove the
  mismatch.
- **Pros:** registry and parquet agree.
- **Cons:** the registry `dtype` field feeds `feature_set_hash`; changing it
  churns the hash and the 3.4 contract for a non-load-bearing reason; loses the
  *intent* that these are discrete. **Why rejected:** out of scope (3.4 is `done`),
  changes a hashed contract, and the intent vs storage split is real — better
  recorded as debt than papered over by editing a closed Stage.

### Alternative D — Do nothing
Not acceptable: the schema must declare *some* dtype; leaving it implicit means
the regression comparison would fail unpredictably.

## Consequences

### Positive
- Exact dtype parity with the regression oracle (4023×62); A5/A6 pass.
- Missing warmup is represented honestly (NaN), no sentinel hacks.

### Negative
- Registry (`int64`) and dataset (`float64`) disagree — a documented inconsistency
  a reader must not be surprised by.
- Discrete features ride as floats; any consumer wanting integer codes must cast
  after dropping warmup.

### Neutral / trade-offs accepted
- Reconciling the logical-vs-storage dtype split is deferred (debt), tracked here
  and as a `[finding]` in the technical §7.

## Implementation notes

- pandera dataset schema (`adapters/out/parquet/schemas/dataset_schema.py`):
  declare the three columns `float64`, nullable.
- The assembler must **not** cast these to int; leave NaN on warmup so the float
  promotion happens naturally, matching the oracle.
- Record the registry/parquet mismatch as a `[finding]` in the technical §7 for a
  future reconciliation Stage.

## References

- Related ADRs: `3.4.0002` (FeatureSpec dtype field), `0.0.0021` (regression by
  unit + oracle).
- Oracle: `data/processed/dataset_tft/AAPL/dataset_tft_AAPL.parquet`.
- Registry specs: `feature_registry.py:482` (volatility_regime), `:494`
  (trend_regime), `:504` (stress_tail_return_flag).
- Old inconsistency: old `FEATURE_REGISTRY` (int64) vs produced parquet (float64).
