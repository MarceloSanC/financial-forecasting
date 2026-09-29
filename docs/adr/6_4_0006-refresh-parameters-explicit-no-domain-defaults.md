---
title: ADR 6.4.0006 — Every parameter of the gold refresh is an explicit field of a frozen RefreshParameters DTO with no default, including the preregistration reference and both Wilson band levels; validated at construction by public owner validators; one MCS seed serves every horizon and scheme
description: Architecture Decision Record
when-use: Reference when asking where α, reps, seed, tolerance, band levels, min_violations, the candidate or the preregistration reference of the gold refresh come from, why the domain has no default for them, or how the MCS seed is used across horizons
keywords: [adr, evaluation, parameters, preregistration, mcs, seed, bootstrap, reps, alpha, tolerance, min-violations, wilson, band-level, no-default]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.4.0006
decision: RefreshGold takes a frozen RefreshParameters DTO (application/dtos) whose fields — preregistration reference, degeneracy tolerance, Wilson band levels, min_violations, Holm candidate and α, DM variance estimators, MCS α, reps, seed and bootstrap schemes — have no default; the DTO checks presence and structure (non-empty, unique tuples; non-empty strings) and all are validated at construction by public owner validators (validate_tolerance, validate_rate, validate_min_violations, validate_alpha, the new public validate_bootstrap_parameters split out of validate_bootstrap_request, and MIN_MCS_REPS), so no manifest — BLOCKED included — ever carries an invalid value; the values belong to the 6.5 preregistration, which supplies the reference; a single int MCS seed is used for every horizon and every scheme and is persisted with each MCS report.
context_stage: 6.4-gold-builders-and-quality-gates
bounded_context: evaluation
---

# ADR 6.4.0006 — Explicit refresh parameters

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The services of 6.1–6.3 take their statistical parameters as mandatory
arguments with no domain default: tolerance (ADR 6.1.0003), `min_violations`
(concept 6.3 C4), α (6.2 C4), the bootstrap request (ADR 6.2.0004: `seed ≥ 0`,
`reps ≥ 1`; the MCS needs `reps ≥ MIN_MCS_REPS`). Concept 6.2 §1/§11 and
concept 6.3 §Fora do escopo put the **values** in the 6.5 preregistration.
Issue #117 (P5, fork C6) asked whether the MCS seed is one per horizon or
derived.

The domain doc §8.2 (B-ORDEM) requires the preregistration to be frozen and
hashed **before** any confirmatory metric is computed; the Wilson band has two
roles with two levels (95 % for the isolated test, 97.5 % per tail in the H1
gate — doc §4.4, §10; concept 6.3 §Fora do escopo). The domain doc §2.7 forbids
aggregating across horizons: each horizon's MCS is a separate procedure whose
validity depends only on its own resampling distribution.

The "int non-bool ≥ minimum" rule has several writings in the slice
(issue #118); the DTO must not add another.

## Decision

`[decision:E] 6.4-C6a — defaults for the refresh parameters`
`Escolha: none; explicit frozen DTO validated at construction by public owner validators · Alternativas: domain defaults; a validation copy in the DTO; validation at first use · Degrau (C): —`
`Base: ADR 6.1.0003 "the caller must pass (no default in the domain; the value is preregistered in 6.5)"; ADR 6.2.0004 (seed/reps validated by validate_bootstrap_request); issue #118`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

`[decision:C] 6.4-C6b — MCS seed across horizons and schemes`
`Escolha: one int seed for every horizon and scheme, persisted per report · Alternativas: one seed per horizon; seeds derived by hashing (seed, horizon) · Degrau (C): 5`
`Base: domain doc §2.7 "nada é agregado entre horizontes"; ADR 6.2.0004 (BootstrapIndices carries the seed)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. `RefreshParameters` (frozen application DTO — it calls validators that
   live in domain services, and the domain direction is service → VO), all
   keyword, no defaults:
   - `preregistration_ref: str` — the hash of the frozen preregistration,
     supplied by 6.5 (and by the tests with a declared literal until then);
   - `degeneracy_tolerance: float`;
   - `band_levels: tuple[float, ...]` — every level to compute (the
     preregistration names 95 % and 97.5 %), each persisted with its level;
   - `min_violations: int`;
   - `candidate: str`, `dm_alpha: float`,
     `dm_variance_estimators: tuple[DmVarianceEstimator, ...]`;
   - `mcs_alpha: float`, `mcs_reps: int`, `mcs_seed: int`,
     `mcs_schemes: tuple[BootstrapScheme, ...]`.
2. `__post_init__` checks presence and structure (non-empty strings; tuples
   non-empty and without repeats) and calls only **public** owner validators,
   so every value is valid before anything is read — including on the
   `BLOCKED` path, whose manifest records the parameters although the
   services that would use them never run:
   - `validate_tolerance(value, field=...)` (`value_objects/_tolerance.py`,
     the single owner shared by `DegeneracyGate` and `HitSequence`);
   - `validate_rate` for each band level (the validator `WilsonBand` uses);
   - `validate_min_violations`; `validate_alpha` for both α;
   - `validate_bootstrap_parameters(*, reps, seed)` — a public function split
     out of `validate_bootstrap_request` in `bootstrap_indices.py` (which
     then calls it, with the same messages; a small declared change to a 6.2
     file) — and `reps ≥ MIN_MCS_REPS`.

   No rule is re-written in the DTO (issue #118 keeps the unification of the
   integer rule).
3. The same `mcs_seed` feeds `McsBackend.bootstrap_indices` for every horizon
   and every scheme; `McsReport` already carries seed, reps, scheme, block and
   generator, and `gold_mcs_results` persists them.
4. `preregistration_ref` is written to the manifest (ADR 6.4.0005) and on
   every row of the confirmatory tables (`gold_dm_results`,
   `gold_mcs_results`, `gold_calibration_table`, `gold_metrics_by_run`).
5. Not computed by 6.4 (their values or series are not among these
   parameters): the Monte Carlo p-values (ADR 6.3.0006), the MCS block
   sensitivities l = h and l = √T (B-MCS, doc §6.5), the DM per τ — see the
   concept §Fora do escopo.

## Alternatives considered

### Alternative A — Seed derived per horizon

- **Why rejected:** no statistic combines horizons, so independence between
  horizons' bootstrap streams buys nothing; a derivation rule would be an
  identity scheme with no source (and hashing belongs to the shared identity
  VOs, LAYOUT §7).

### Alternative B — Defaults in the use case until 6.5

- **Why rejected:** a default is a preregistration value chosen before the
  preregistration exists (forking paths).

### Alternative C — Validate reps and seed in the DTO

- **Why rejected:** would add another writing of the integer rule that issue
  #118 exists to unify; the owner exposes it instead.

### Alternative D — Validate tolerance, reps and seed at first use

- **Why rejected:** on the `BLOCKED` path the services never run, so the
  manifest would publish unvalidated parameters (Checkpoint A round 2).

## Consequences

### Positive

- The 6.5 preregistration becomes the single source of every value; the
  gold records which values, and which preregistration, produced it.

### Negative

- Callers before 6.5 (tests, e2e) must spell every parameter, including a
  literal preregistration reference.
- Two small public-surface changes in 6.2 files (`MIN_MODELS`,
  `validate_bootstrap_parameters`), declared in the concept's
  `arquivos_a_modificar`.

## References

- Concept 6.2 §1, §11; concept 6.3 §Fora do escopo, C4; domain doc §2.7,
  §4.4, §8.2, §10.
- Issue #118 (single integer rule of the slice).
- Related ADRs: 6.1.0003, 6.2.0004, 6.2.0005, 6.3.0006, 6.4.0001, 6.4.0005.
