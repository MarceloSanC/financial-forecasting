---
title: ADR 5.5.0001 — The confirmatory cohort is a versioned TOML spec, frozen and hashed through a shared VO, anchored by a published tag and issue comment, and kept blind until the Step 6 pre-registration
description: Architecture Decision Record
when-use: Reference before changing what the cohort file declares, how the cohort hash or cohort_id is computed, how the freeze is anchored in time, or the rule that no metric is computed on the cohort before the 6.5 pre-registration
keywords: [adr, cohort, preregistration, freeze, hash, toml, parent_sweep_id, cohort_id, revision, anteriority, blinding, forking-paths]
status: accepted
created_at: 2026-09-26
updated_at: 2026-09-27
adr_id: "5.5.0001"
decision: Declare the cohort in config/cohorts/aapl_confirmatory.toml parsed at the CLI boundary into a CohortSpec; hash its canonical payload through a CohortHash VO in shared/domain/value_objects; derive cohort_id = name-r<revision>-<hash12> as parent_sweep_id; declare device cpu inside the hash; before the run, push a cohort/<cohort_id> tag and post the hash on the Stage issue; compute no metric on the cohort until the 6.5 pre-registration hash is published
context_stage: 5.5-confirmatory-retrain
bounded_context: modeling
---

# ADR 5.5.0001 — Frozen, hashed, anchored and blind cohort spec

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The confirmatory design (domain doc `quantile-model-training.md` §6.3) requires
the cohort — candidate, comparators, seeds, folds, configuration — to be frozen
before running and hashed; the Stage 5.2 finding adds `quantile_levels` to the
hash. The roadmap planned `config/cohorts/aapl_confirmatory.yaml` without a
schema. Forces:

1. **Integrity:** any change to the declaration must be detectable.
2. **Anteriority:** a hash proves integrity, not *when* the content existed. Git
   author/committer dates and the silver `created_at_utc` (local `Clock`) are
   client-asserted and backdatable (Haber & Stornetta 1991). The freeze commit
   lives on a feature branch that the Git workflow rebases before the PR, which
   rewrites its hash.
3. **Layer rule:** `check_layout` rule 6 allows `hash_mapping` calls only inside
   `shared/domain/value_objects/` (identity only through shared VOs; precedent
   ADR 5.2.0004).
4. **Remediation:** a partially persisted unit cannot be completed in the
   append-only silver (ADR 5.5.0003); a new `cohort_id` must be obtainable
   without editing substantive content.
5. **Forking paths:** the run happens in Stage 5.5, before the Step 6
   pre-registration (6.5) freezes the seed aggregation rule and the primary tail
   pair. With predictions in silver, a metric computed before 6.5 would let the
   analysis plan be chosen after seeing results (Gelman & Loken 2014).

## Decision

- **File and boundary:** `config/cohorts/aapl_confirmatory.toml`, parsed with
  `tomllib` by the modeling CLI adapter into a `CohortSpec` DTO. The spec
  carries: name, `revision`, asset, feature set name **and** `feature_set_hash`,
  `pipeline_version`, horizons, quantile levels, geometry, device, TFT seeds
  (ordered), sweep plan for TFT and GBM (spaces, base params, `n_trials`,
  sampler seed), frozen TFT and GBM params, baseline specs, sweep provenance
  (study ids, best trials and objectives, dataset fingerprint of the sweeps) and
  the dataset content fingerprint of the run.
- **Hash:** `CohortHash.compute(hasher, payload)` in
  `shared/domain/value_objects/cohort_hash.py` over the canonical payload; the
  TFT seed inside `tft_params` is excluded (seeds are per unit).
  `cohort_id = f"{name}-r{revision}-{hash[:12]}"` is `ScopeSpec.cohort_id` for
  every unit, so every `dim_run` row carries it. The sweeps run under
  `f"{name}-r{revision}-sweep-{draft_hash[:12]}"`, computed on the unfrozen spec.
- **Anchor:** after committing the frozen file and before `run`, push the tag
  `cohort/<cohort_id>` pointing to the freeze commit (tags survive branch
  rebases) and post `cohort_id` + full hash as a comment on the Stage issue
  (server-side timestamp). `run` records the code identity (git content hash of
  `src/`, `uv.lock` and the cohort file) and refuses tracked uncommitted changes
  in those paths (ADR 5.5.0003).
- **Device:** the declared device is `cpu` and enters the hash (Alternative E).
- **Blinding:** no metric is computed on the cohort's `parent_sweep_id` until the
  6.5 pre-registration hash is published; Stage 5.5 reports row counts and
  `target_timestamp` sets only. The rule enters the 6.5 DoD and the runbook.

## Alternatives considered

### Alternative A — YAML file, as the roadmap planned
- **Why rejected:** PyYAML is only transitive (`uv.lock`); the project already
  reads versioned TOML with `tomllib` (`scripts/arch_baseline.toml`).

### Alternative B — Compare the TOML commit date with the first `dim_run.created_at`
- **Why rejected:** both timestamps are local and backdatable; the comparison
  proves nothing (Checkpoint A).

### Alternative C — Wait for 6.5 before running the cohort
- **Pros:** strongest ordering.
- **Cons:** blocks Step 5 on Step 6 for no gain: what the pre-registration must
  precede is the first *result*, and blinding guarantees that.
- **Why rejected:** decided by the human (issue #102, B2).

### Alternative D — Environment inside the hash
- **Why rejected (partially):** the hash must exist before the run, and the
  library versions and code identity are observed at run time. The declared
  `device` is in the hash; observed versions and code identity go to the ledger
  and a resume with any
  difference aborts (ADR 5.5.0003).

### Alternative E — ROCm as the confirmatory device (overview ASSUM-2, ADR 5.4.0003)
- **Pros:** the environment the overview assumed; faster TFT training.
- **Cons:** the TFT adapter hardcodes `accelerator="cpu"`
  (`pf_tft_trainer.py:325,523`) and torch comes from the CPU index; enabling
  ROCm means changing a closed adapter and the dependency index before knowing
  whether CPU cost is acceptable. ROCm on a Windows Docker host is fragile.
- **Why rejected (for now):** the declared device is `cpu` and enters the hash;
  CPU cost is measured before the human's budget decisions, and the Stage stops
  for a human decision if the measured cost makes the cohort infeasible.
  Overview ASSUM-2 and ADR 5.4.0003 are annotated with this deviation.

### Alternative F — Do nothing (freeze by discipline)
- **Why rejected:** §6.3 and Nosek et al. (2018) require a checkable freeze.

## Consequences

### Positive
- Any edit to the declaration yields a new `cohort_id`; `revision` gives a
  content-neutral remediation path.
- Step 6.5 can cite one hash, and its own anchor proves order against metrics.

### Negative
- Anchoring is a manual runbook step (tag push, issue comment), not enforced by
  code.
- Re-materializing on another machine may change the dataset fingerprint and
  require a new revision.

## References

- Related ADRs: [1.4.0001](./1_4_0001-canonicalizacao-de-hash-deterministico.md), [5.2.0004](./5_2_0004-canonical-run-identity-via-run-id-and-config-signature.md), [5.5.0002](./5_5_0002-exploratory-sweep-on-fold-zero-geometry.md), [5.5.0003](./5_5_0003-resumable-cohort-units-atomic-ledger.md)
- Nosek, B. A. et al. (2018). The preregistration revolution. PNAS. doi:10.1073/pnas.1708274114
- Gelman, A.; Loken, E. (2014). The statistical crisis in science. American Scientist 102(6).
- NIST (2015). FIPS 180-4 Secure Hash Standard, §1. doi:10.6028/NIST.FIPS.180-4
- Haber, S.; Stornetta, W. S. (1991). How to time-stamp a digital document. J. Cryptology 3(2). doi:10.1007/BF00196791
- Issue #102 (decisions B2, 2026-09-27); Stage 5.2 technical §7 (finding 2026-07-18)
