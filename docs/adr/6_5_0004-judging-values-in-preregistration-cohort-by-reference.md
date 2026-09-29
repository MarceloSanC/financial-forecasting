---
title: ADR 6.5.0004 — Every value that judges lives in the preregistration — including the realized source (dataset fingerprint) and the window deficits — while the cohort is only referenced by id and hash; RefreshParameters and the refresh command are derived from the preregistration by one function, and the scorecard refuses a gold whose manifest disagrees with it
description: Architecture Decision Record
when-use: Reference when asking where a refresh or scorecard parameter comes from (preregistration or cohort spec), why the dataset fingerprint appears in both, how RefreshParameters is built for the confirmatory run, or what the scorecard checks in the gold manifest
keywords: [adr, evaluation, preregistration, cohort, refresh-parameters, window-deficits, dataset-fingerprint, manifest, consistency, identity]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.5.0004
decision: The preregistration carries the asset, the cohort reference (cohort_id and full cohort hash), the realized source (the frozen dataset content fingerprint, equal to the cohort spec's), the evaluated horizons and quantile grid (equal to the cohort's), the explicit per-model window deficits and every RefreshParameters value; a single application function refresh_inputs_from(preregistration) returns the RefreshParameters and every other field of RefreshGoldCommand — asset, parent_sweep_id (= the referenced cohort_id, ADR 5.5.0001), horizons, window_deficits and dataset_fingerprint; a versioned-config test checks that the preregistration's cohort reference, fingerprint, horizons and grid match config/cohorts/<cohort>.toml and its hash; BuildConfirmatoryScorecard takes no partition of its own — it reads the partition derived from the plan — and raises PreregistrationMismatchError when the gold manifest's partition, preregistration_ref, parameters, horizons, window_deficits or dataset_fingerprint differ from those derived from the preregistration, or when the seeds or quantile levels present in the gold rows differ from the preregistered ones.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0004 — Judging values in the preregistration; cohort by reference

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Issue #127 (fork C5) asks whether `window_deficits`, `dataset_fingerprint` and
the MCS parameters come from the preregistration or from the cohort spec. The
domain doc §8.2 gives the criterion: the cohort freezes **what** is trained, the
preregistration freezes **how it is judged**, "two hashes with distinct roles".
§8.1 lists, as preregistration content, the grid and horizons, the "fonte do
realizado (§2.1)", the exclusion rules and "a referência ao hash do cohort".

Facts:

- `RefreshParameters` (ADR 6.4.0006) has no default; `RefreshGoldCommand` also
  takes `horizons`, `window_deficits` (I8 of 6.4: the maximum late start per
  model; 0 if undeclared) and the mandatory `dataset_fingerprint` (ADR 6.4.0009).
- The cohort spec (`config/cohorts/aapl_confirmatory.toml`, ADR 5.5.0001)
  carries `horizons = [1, 7]`, the grid, the seeds and `dataset_fingerprint`; it
  is a `modeling` DTO read by a `modeling` CLI adapter. `evaluation` may not
  import `modeling` at runtime (ADR 0.0.0053, LAYOUT §7).
- `window_deficits` is a tolerance on the start of each model's series: a larger
  declared deficit shortens the common sample T that DM and MCS use. Chosen after
  seeing results it would be an exclusion rule picked post hoc (domain doc §5.3
  item 5; Simmons et al. 2011).

## Decision

`[decision:C] 6.5-C5 — where the refresh and scorecard inputs come from`
`Escolha: all judging inputs in the preregistration (cohort by id + hash; fingerprint, horizons, grid copied and checked against the cohort); one derivation function; manifest checked by the scorecard · Alternativas: read horizons/fingerprint from the cohort spec at run time; split (MCS in the preregistration, deficits and fingerprint in the cohort) · Degrau (C): 1 (domain doc §8.1 lists grid, horizons, realized source and exclusion rules as preregistration content; §8.2 roles of the two hashes)`
`Base: domain doc §8.1, §8.2; ADR 6.4.0006; ADR 6.4.0009; ADR 0.0.0053`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o hash`

1. **Preregistration content** (beyond the §8.1 statistical rules):
   `asset`, `cohort.cohort_id`, `cohort.cohort_hash` (full), `realized.dataset_fingerprint`
   (the `DatasetContentFingerprint` of the training grid, ADR 6.4.0009),
   `horizons`, `quantile_levels`, `candidate`, the comparator list by class
   (ADR 6.5.0007), and `window_deficits` as an explicit mapping with one entry
   per model of the cohort (no implicit 0).
2. **Derivation:** `refresh_inputs_from(preregistration) -> RefreshInputs`
   (application, `evaluation/application/dtos/`), the only place that maps the
   plan to `RefreshParameters` and to **every** other field of
   `RefreshGoldCommand`: `asset` (the plan's asset), `parent_sweep_id` (the
   referenced `cohort_id`, which *is* the cohort's `parent_sweep_id` —
   ADR 5.5.0001), `horizons`, `window_deficits`, `dataset_fingerprint`. The 8.1
   orchestrator calls it; nobody spells these values twice, and the gold can
   only be built on the partition of the cohort the plan names.
3. **Cohort consistency** is a versioned-config test (it reads the two TOML
   files and hashes the cohort through the cohort's own loader and `CohortHash`
   — the test, not `src/`, crosses to `modeling`), run in the normal suite: the
   preregistration's `asset`, `cohort_id`, `cohort_hash`, `dataset_fingerprint`,
   `horizons`, `quantile_levels` and seeds equal the cohort's. The production code of `evaluation`
   never reads the cohort file.
4. **Manifest consistency:** `BuildConfirmatoryScorecard` takes no asset or
   partition in its command: it reads the partition derived from the plan.
   Before any verdict it compares the gold manifest (`partition`,
   `preregistration_ref`, `parameters`, `horizons`, `window_deficits`,
   `dataset_fingerprint`) with `refresh_inputs_from(prereg)`, and the **seed
   set** and **quantile levels** found in the gold rows with the preregistered
   seeds and grid (neither is in the manifest: `RefreshParameters` carries no
   seed list or grid). Any difference — a missing **or an extra** seed
   included — raises `PreregistrationMismatchError`: the gold was not produced
   from the cohort and plan named here.

## Alternatives considered

### Alternative A — Horizons and fingerprint read from the cohort spec at run time

- **Pros:** no copied value.
- **Cons:** `evaluation` would need the cohort spec (a `modeling` DTO, a
  consumer port for a config file); the plan would no longer state by itself
  what it judges.
- **Why rejected:** the copy is checked (item 3), so it cannot drift; the plan
  is self-contained, as §8.1 asks.

### Alternative B — Window deficits in the cohort spec

- **Why rejected:** the cohort hash of r0 is anchored; adding a field changes it
  (ADR 6.4.0009, Alternatives); and a deficit is a judging tolerance (it moves
  T), so it is "how", not "what".

## Consequences

### Positive

- One derivation from plan to refresh; a gold made with other values cannot be
  scored against this plan.

### Negative

- The fingerprint, horizons and grid are written in two files; the test of item
  3 is what keeps them equal.

## References

- Domain doc §2.1, §5.3, §6.7, §8.1, §8.2.
- Related ADRs: [0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md), [5.4.0001](./5_4_0001-encoder-context-across-partitions.md), [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md), [6.4.0006](./6_4_0006-refresh-parameters-explicit-no-domain-defaults.md), [6.4.0009](./6_4_0009-realized-from-modeling-training-grid-via-consumer-port.md), [6.5.0001](./6_5_0001-preregistration-canonical-toml-hashed-value-object.md).
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (fork C5).
