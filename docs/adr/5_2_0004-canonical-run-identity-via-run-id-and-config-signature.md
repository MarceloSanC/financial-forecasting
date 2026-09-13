---
title: ADR 5.2.0004 — Canonical run identity via RunId/ConfigSignature; schema_version out of the key; cohort_id, max_horizon and the registry hash placement
description: Architecture Decision Record
when-use: Reference before changing what makes two runs "the same run" — adding or removing a field from the run identity, moving a field between config_signature and a RunId slot, bumping pipeline_version, or designing the cohort/replay semantics of Stage 5.5
keywords: [adr, run-id, config-signature, identity, reproducibility, schema-version, cohort, parent-sweep-id, max-horizon, feature-set-hash, pipeline-version, modeling, hashing]
status: accepted
created_at: 2026-09-12
updated_at: 2026-09-12
adr_id: "5.2.0004"
decision: The three training use cases compute run identity ONLY through the shared RunId.compute (9 fixed slots) and ConfigSignature.compute; schema_version leaves the key and stays a dim_run column; config_signature carries everything the other 8 slots do not (scope minus asset, params minus seed, features, typing, grid) including cohort_id and max_horizon; feature_set_hash is the FeatureRegistry content hash; PIPELINE_VERSION bumps to "2" in the same change
context_stage: 5.2-baselines-naive-statistical
bounded_context: modeling
---

# ADR 5.2.0004 — Canonical run identity via `RunId`/`ConfigSignature`

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

> **Numbering note.** This decision was taken in issue #65, after Stages 5.2–5.4 had shipped. It is filed under `5.2` because concept 5.2 §D5 is where the hand-rolled `run_id` payload (scope + spec + fingerprint + grid + `schema_version`) was first designed; Stages 5.3 and 5.4 copied that design. This ADR supersedes that detail of D5 for all three use cases.

## Status

`accepted`

## Context

Reproducibility in this project is declared as "traceable by `run_id` + `config_signature` + `split_fingerprint`" (`docs/overview.md`). Stage 1.4 delivered the identity value objects `RunId` (a sha256 over **9 fixed slots**: `asset, feature_set_hash, trial_number, fold, seed, model_version, config_signature, split_signature, pipeline_version`) and `ConfigSignature` (a sha256 over an arbitrary mapping minus volatile keys). Verified before this change: **neither VO was called anywhere in `src/`**. What ran instead were three private `_run_payload` / `_config_payload` / `_params_payload` / `_spec_payload` helpers — one set per use case (`run_baselines.py`, `train_gbm_quantile.py`, `train_tft.py`) — each with a different payload, all three including `schema_version`, the Parquet schema version of the destination table.

Two defects follow:

1. **Identity contaminated by persistence detail.** Bumping a column of the silver Parquet changes the `run_id` of every model ever trained, and old runs stop pairing with new ones. Evans (ENTITIES): identity must be defined "regardless of its form or history"; `schema_version` is form.
2. **Three concurrent definitions of "the same run".** Three payloads, hand-listed fields (a new hyperparameter silently stays out of the identity), and the canonical VOs left as an anemic model (Fowler): built, tested, never called.

Honest note on sources: Evans, Fowler and Cockburn do not treat *identity of a computation* (a run happens and ends; it is not an Entity with continuity). "Identity contains no persistence detail" is an extrapolation of ENTITIES, well founded but not a citation about this case. That gap is precisely why this ADR exists: the project has to declare what "the same run" means, because no canonical source does it for us.

Mapping the current payloads onto the 9 slots is mechanical except for three fields that have **no obvious slot**: `cohort_id`, `max_horizon` (both from `ScopeSpec`) and the choice of what `feature_set_hash` should be. Each was resolved with a measurement, not an assumption.

## Decision

### D1 — Single path: `RunId.compute` + `ConfigSignature.compute`

Each use case has one private method `_identity(...)` that builds the config mapping, calls `ConfigSignature.compute`, then calls `RunId.compute` with the 9 slots spelled out at the call site. The private payload helpers are deleted. A gate in `scripts/check_layout.py` forbids any call to `hasher.hash_mapping` / `hasher.hash_text` outside `shared/domain/value_objects/` (proved to fail in `tests/architecture/test_layout_rules.py`), so the duplication cannot come back.

### D2 — `schema_version` leaves the key, stays a column

`schema_version` is provenance of the row (`RunRecord.schema_version`, `dim_run` column). It enters neither `config_signature` nor `run_id`. Test that *is* the issue: `test_run_id_invariant_under_schema_version_change` in each use case's identity test module.

### D3 — Uniform rule for `config_signature`

`config_signature` = **the complete configuration of the run minus what the other 8 slots already carry explicitly.** Therefore:

- out of the config payload: `asset_id` (slot `asset`), `seed` (slot `seed`), `model_version` (slot), the fold and its fingerprint (slots `fold`/`split_signature`), `schema_version` (column, D2);
- in the config payload: `scope.{feature_set_name, max_horizon, cohort_id}`, hyperparameters as `dataclasses.asdict(params)` minus `seed` (a new hyperparameter enters the identity by itself — fixes the hand-listed omission), `feature_names` (ordered), `known_feature_names` (TFT typing, I10), `horizons`, `quantile_levels`; for baselines the spec via `asdict(spec)`.

### D4 — Slot mapping per use case

| `RunId` slot | `RunBaselines` | `TrainGbmQuantile` | `TrainTft` |
|---|---|---|---|
| `asset` | `scope.asset_id` | same | same |
| `feature_set_hash` | `feature_registry.feature_set_hash()` (D7) | same | same |
| `trial_number` | `None` | `None` | `None` |
| `fold` | `str(fold.fold_index)` | same | same |
| `seed` | `None` | `params.seed` | `params.seed` |
| `model_version` | `spec.model_version` | `"gbm_quantile"` | `"tft_quantile"` |
| `config_signature` | `{scope*, spec, horizons, quantile_levels}` | `{scope*, params−seed, feature_names, horizons, quantile_levels}` | `{scope*, params−seed, feature_names, known_feature_names, horizons, quantile_levels}` |
| `split_signature` | `fold.fingerprint.value` | same | same |
| `pipeline_version` | `PIPELINE_VERSION` | same | same |

`scope*` = `{feature_set_name, max_horizon, cohort_id}`. `trial_number` is `None` in all three because the only producer of trials (`RunTftSweep`) is exploratory by design and does not persist `dim_run` rows (ADR 5.4.0005).

### D5 — `cohort_id` stays in the identity, inside `config_signature`

Measured in the Parquet adapter (`parquet_analytics_repository.py::_write_partition`): logical-PK collisions are detected **per partition file**. If `cohort_id` left the key, two cohorts training the same config/fold/seed would produce the same `run_id`, and then:

- `fact_oos_predictions` (append-only, PK starts with `run_id`, partitioned by `(asset, feature_set_name, year)`, no `parent_sweep_id` column) raises `DuplicateKeyError` for the second cohort — its predictions cannot be persisted at all;
- `dim_run` (upsert, PK `(run_id,)`, partitioned by `(asset, parent_sweep_id)`) writes two rows with the same `run_id` into two partition files — the logical PK is violated without any error.

The Evans-pure reading ("the cohort is history, not identity") is right in principle and wrong in timing: it requires a store PK/replay redesign, which is the Stage 5.5 concept's job (the 5.2 finding already routes replay semantics there). Until then the identity keeps today's semantics (distinct cohorts ⇒ distinct `run_id`), expressed in the one slot that admits it. Accepted cost: `config_signature` no longer answers "same config across cohorts" by itself.

### D6 — `max_horizon` stays in the identity, inside `config_signature`, in all three use cases

Measured with a control (120 synthetic sessions, 2 folds): the splitter computes `gap = max_horizon + embargo`, so `split_fingerprint` sees only the **sum**. Control `(max_horizon=2, embargo=1)` twice → identical; treatment A `(2,1)` vs `(3,1)` → different; treatment B **`(2,2)` vs `(3,1)` → identical fingerprints**. `split_signature` therefore does **not** represent `max_horizon` transitively. In the TFT it is also the decoder length (ADR 5.4.0002) — a model parameter. It goes into `config_signature` uniformly (GBM/baselines too): uniformity is worth more than the marginal over-discrimination, and over-discrimination is the safe failure direction. Pinned by `test_max_horizon_enters_identity_even_when_split_fingerprint_is_unchanged` in each identity test module.

### D7 — `feature_set_hash` = `feature_registry.feature_set_hash()`

Concept 1.4 D5 defined the slot as `hasher.hash_text("|".join(features_ordered))` computed by the caller. That literal reading would call `hash_text` outside the VOs — exactly what D1's gate forbids — and would duplicate `feature_names`, which already lives in `config_signature`. The slot carries instead the content hash of the `FeatureRegistry` (definitions: formula, warmup, dtype, typing…), a pure function that already exists and is **the same value `BuildDataset` returns in its result DTO** (`BuildDatasetResult.feature_set_hash`; nothing persists it today — the pairing holds by construction, both call `feature_set_hash()` over the same `FEATURE_SPECS`, not by a stored key). Persisting it as dataset metadata is a separate, speculative follow-up. The consumed subset, its order and its typing are discriminated by `config_signature`. This is a recorded deviation from concept 1.4 D5. For baselines, which consume no feature, the hash states which registry built the dataset they read.

Consequence of D7: `run_baselines.py` now imports `feature_registry`, a new `modeling → feature_engineering` runtime edge. It is declared as the 12th named exception of the `bc-independence` contract (same debt class and same exit condition as the GBM/TFT registry edges). Computing it in-process, rather than receiving it through the command DTO, keeps identity from depending on a caller-supplied string.

### D8 — `PIPELINE_VERSION = "2"`, bumped in the same commit as the first break

`features/modeling/application/pipeline_version.py`. `"1"` is assigned retroactively to the hand-rolled generation (never emitted); `"2"` is this ADR. It does not become a `dim_run` column (Stage 4.1 dropped it); it lives only inside the hash. The bump is what makes the discontinuity explicit: hashes that do not pair, never different data under an unchanged id.

## Alternatives considered

### `cohort_id`
- **(i) inside `config_signature` — chosen.** Keeps today's semantics; no store change.
- **(ii) out of the identity, column only.** Evans-pure, but unpersistable today (D5 defects). Belongs to the 5.5 concept together with PK/replay.
- **(iii) slot `trial_number`.** Wrong type (`int`) and wrong meaning. Rejected.

### `max_horizon`
- **(A) inside `config_signature` in all three — chosen.**
- **(B) only in the TFT.** GBM/baselines would tolerate the aliasing because their computation is invariant to `max_horizon` given the fold; rejected for non-uniformity.
- **(C) out of the identity everywhere.** Rejected by the measurement: a TFT with a different decoder length would share a `run_id`.

### `feature_set_hash`
- **(A) registry content hash — chosen.**
- **(B) a new `FeatureSetHash` VO hashing the ordered consumed names (faithful to concept 1.4 D5).** Adds a VO outside the issue's scope and is redundant with `feature_names` in the config.

### Where `feature_set_hash` is computed
- **In-process via the registry import — chosen** (12th declared edge).
- **Received through the command DTO.** Zero new edge, but identity would depend on a caller-supplied string, and the edge would only move to the 5.5 runner.

## Consequences

### Positive
- One definition of "the same run", visible at one call site per use case, with the 9 slots spelled out.
- `schema_version` bumps no longer break pairing between runs.
- A new hyperparameter enters the identity automatically (`asdict`).
- Run ↔ dataset share the registry hash.
- The discontinuity is explicit (`pipeline_version`), golden-pinned before/after (`test_identity_golden.py` keeps the pre-#65 values frozen as `PRE_65_*`).

### Negative
- **Every `run_id` and `config_signature` persisted before this change stops pairing with new ones.** Executed before the confirmatory freeze, as the issue requires.
- `config_signature` alone no longer identifies "same config across cohorts" (D5 cost).
- One more declared cross-BC edge (D7).

### Neutral / trade-offs accepted
- Baselines carry a registry hash although they consume no feature (D7 rationale).
- Slight over-discrimination for GBM/baselines on `max_horizon` (D6).

## Implementation notes

- Identity tests per use case: `tests/unit/features/modeling/application/test_{run_baselines,train_gbm_quantile,train_tft}_identity.py` — invariance under `schema_version`, column preserved, an oracle that recomputes `RunId.compute` from the persisted `dim_run` row, one perturbation per variable slot, the `max_horizon`/`embargo` aliasing case.
- Golden: `tests/unit/features/modeling/application/test_identity_golden.py` (`PRE_65_*` frozen, `GOLDEN_*` current, `*_broke_from_pre_65` proves the break is total and intentional).
- Gate: `scripts/check_layout.py` rule "no `hash_mapping`/`hash_text` outside `shared/domain/value_objects/`", proved failing in `tests/architecture/test_layout_rules.py`.
- Finding routed to Stage 5.5 (issue #65 comment): if the cohort design wants "run = computation", change the store PK/replay first, then drop `cohort_id` from the config payload with a new `pipeline_version` bump.

## References

- Issue #65; issue #11 (Stage 1.4, the VOs); issue #60 (`bc-independence` contract).
- `docs/overview.md` — reproducibility traceable by `run_id` + `config_signature` + `split_fingerprint`.
- Concept 1.4 (§4 `RunId` 9 slots, D5 `feature_set_hash`); concept 5.2 §D5 (superseded detail).
- ADR 1.4.0001 (canonical hashing), ADR 4.1.0001 (silver schema; `dim_run` without `pipeline_version`), ADR 4.2.0001 (repository port and partitioning), ADR 5.1.0003 (four-way split fingerprint), ADR 5.4.0002 (single multi-horizon decoder), ADR 5.4.0005 (exploratory sweep does not persist runs).
- Evans, *DDD Reference* (2015): ENTITIES, DOMAIN EVENTS, LAYERED ARCHITECTURE. Fowler, *AnemicDomainModel*.
