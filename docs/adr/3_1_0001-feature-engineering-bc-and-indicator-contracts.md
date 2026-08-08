---
title: ADR 3.1.0001 — Introduce the feature_engineering bounded context as a layered container with a minimal domain IndicatorSpec value-object and a pandas-free IndicatorCalculator port, deferring rich registry and processed persistence
description: Architecture Decision Record
when-use: Reference before changing the shape of IndicatorSpec or IndicatorCalculator, before adding feature_engineering layers to import-linter, or when deciding what belongs to Stage 3.1 vs 3.4 (rich registry) vs 3.5 (dataset builder / processed persistence)
keywords: [adr, feature-engineering, bounded-context, layered-container, import-linter, indicator-spec, value-object, indicator-calculator, port-out, protocol, processed-layer, scope-boundary, hexagonal, float32]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "3.1.0001"
decision: feature_engineering is added as a layered import-linter container; IndicatorSpec is a minimal stdlib-only domain value-object (not the rich FeatureSpec, deferred to 3.4); IndicatorCalculator is a pandas-free Protocol port returning Sequence[Mapping] of float32; and processed-layer persistence is deferred to the dataset builder (3.5)
context_stage: 3.1-technical-indicators
bounded_context: feature_engineering
---

# ADR 3.1.0001 — `feature_engineering` BC and indicator contracts

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.1 introduces `feature_engineering`, the **second bounded context under
`features/`** (after `market_data`, 2.2), and the first to compute features. It
must deliver three production artifacts — a value-object describing each
indicator, a port to compute indicators, and an adapter over `pandas-ta-classic`
(ADR [0.0.0024](./0_0_0024-pandas-ta-classic-over-pandas-ta.md)) — while staying
inside an atomic Stage. Several shaping decisions share one context and are
recorded together here to avoid four near-identical ADRs:

- **Architecture must be mechanically enforced.** The prior repo rotted because
  the domain boundary was unenforced (23/36 domain files imported pandas/numpy/
  torch — ADR 1.3.0001). `.importlinter` line 42 already declares *"cada feature
  vira container ao ganhar layers"*, and the `store-no-storage-leak` block
  (lines 157-175) says *"cada NOVA feature ... entra aqui"*. The pattern was set
  by `market_data` (ADR 2.2.0001).
- **Scope creep is a named, high-impact risk** (`overview.md` §10). The roadmap
  splits the feature layer deliberately: Stage **3.4** owns the rich
  `FeatureSpec`/`FeatureRegistry` (known/unknown typing, derived features), and
  Stage **3.5** owns `build_dataset` + the dataset schema + persistence. Stage
  3.1's `arquivos_a_criar` lists **no** use case and **no** `processed` schema.
- **The old `FeatureSpec`** (`feature_registry.py:7-17`) carried per-indicator
  `warmup`/`anti_leakage_tag` — a direct mold for an indicator spec — but also
  `null_policy`/`enabled_by_default`/`group`/`formula_desc` that belong to the
  rich 3.4 registry. The old `TechnicalIndicatorCalculatorPort` was an **ABC**
  returning `list[TechnicalIndicatorSet]` (entity).
- **The port-as-Protocol posture is consolidated** across three prior ports
  (`MedallionStore` 2.1.0002, `ExperimentTracker` 1.5.0002, `CandleFetcher` 2.2):
  ports are structural `Protocol`s that never leak third-party types across the
  boundary.
- **The `MedallionStore` schema registry covers only `bronze`** today
  (`bronze_schemas.py`); there is no `processed` schema. The DoD phrase
  "bronze→processed" must be interpreted against that fact.

## Decision

Four coupled decisions, one BC:

1. **Layered container.** Add `financial_forecasting.features.feature_engineering`
   to the `containers` of the `hexagonal-layers` contract,
   `...feature_engineering.domain` to `domain-purity`, and
   `...feature_engineering.{application,domain}` to `store-no-storage-leak`. No
   per-feature `layers` contract and no feature-vs-feature `independence` contract
   (only two features exist; ADR 1.3.0001 defers `independence` until it means
   something). Inward-only is proven by an intentional `import pandas` in the
   domain that turns `lint-imports` red, then reverted.

2. **Minimal domain `IndicatorSpec`.** A frozen, **stdlib-only** value-object with
   `name`, `family`, `source_cols`, `warmup`, `anti_leakage_tag`,
   `dtype="float32"` + a static `INDICATOR_SPECS` registry of the 11 indicators
   (H-2) + a deterministic `indicator_registry_hash()`. It does **not** replicate
   the old `null_policy`/`enabled_by_default`/`group`/`formula_desc`. The spec is
   born in `domain`, not infrastructure.

3. **Pandas-free `IndicatorCalculator` port.** A structural `Protocol` in
   `application/ports/out` with
   `calculate(asset, candles: Sequence[Candle]) -> Sequence[Mapping[str, float]]`
   (one row per bar, `float32`, NaN tolerated in warmup). It imports the
   `market_data` `Candle` entity (application may import domain) and **never**
   exposes `pandas`/`DataFrame`; pandas-ta column names
   (`MACD_12_26_9`/`MACDs_12_26_9`) stay internal to the adapter.

4. **Defer `processed` persistence.** Stage 3.1 delivers the **`float32` output
   contract** of the calculator only. No `processed` schema, no `build_dataset`
   use case, no `MedallionStore` wiring — those belong to Stage 3.5. "bronze→
   processed" is read as the **direction of data flow**, not wiring to build here.

## Alternatives considered

### Alternative A — Replicate the full `FeatureSpec` (rich registry) now

- **Description:** Bring the old `FeatureSpec` with `null_policy`, `group`,
  `enabled_by_default`, `formula_desc`, and known/unknown typing into 3.1.
- **Pros:** One registry; no later absorption step.
- **Cons:** Pulls Stage 3.4 scope (`3.4-feature-registry-and-derived`) into 3.1,
  inflating an atomic Stage and pre-committing to a registry shape before derived
  features exist to inform it.
- **Why rejected:** Scope creep against a named risk; the minimal `IndicatorSpec`
  is simple-and-replaceable and can be absorbed by the 3.4 `FeatureSpec` without
  rework.

### Alternative B — Port the old ABC returning `list[TechnicalIndicatorSet]`

- **Description:** Keep an ABC port and return the rich entity set, as the old
  repo did.
- **Pros:** Direct port of the old contract.
- **Cons:** ABCs couple adapters to `application` (adapters inherit it); returning
  an entity across the port pushes a richer type than the dataset builder needs
  and pre-empts the 3.4/3.5 entity shape.
- **Why rejected:** Violates the consolidated port-as-Protocol posture; a
  `Sequence[Mapping[str, float]]` is the minimal pandas-free crossing and keeps
  the entity decision for the Stage that owns the dataset.

### Alternative C — Return a `DataFrame` (or pandas types) from the port

- **Description:** Let `calculate` return a `pandas.DataFrame`.
- **Pros:** Less conversion code in the adapter; pandas all the way to the
  consumer.
- **Cons:** Leaks `pandas` into `application`, breaking `store-no-storage-leak`
  and making the BC untestable without pandas; couples every consumer to the
  library choice this very Stage is trying to confine (ADR 0.0.0024).
- **Why rejected:** Directly contradicts the hexagonal posture and the
  supply-chain confinement; no real benefit for a primitive `Mapping` crossing.

### Alternative D — Implement `processed` persistence (schema + use case) in 3.1

- **Description:** Add a `processed` schema to the `MedallionStore` registry and a
  `build_dataset`-like use case here, satisfying a literal "bronze→processed".
- **Pros:** A literal reading of the DoD phrase; end-to-end write in one Stage.
- **Cons:** Pulls Stage 3.5 scope into 3.1 and requires extending the 2.1 schema
  registry without mandate; `arquivos_a_criar` lists neither artifact.
- **Why rejected:** Scope creep crossing two Stage boundaries; the calculator's
  `float32` output is the in-scope contract, and 3.5 owns the dataset/persistence.

### Alternative E — Do nothing / defer the BC

- **Why not acceptable:** Stage 3.1 *is* the creation of `feature_engineering`;
  there is no smaller increment that delivers indicators. Deferring blocks Step 3
  and 3.5.

## Consequences

### Positive

- The second feature BC carries the same mechanical inward-only + purity proof as
  `market_data` and `shared`; `import pandas` in its domain turns the build red.
- The indicator contracts are minimal, pure, and replaceable: `IndicatorSpec` can
  grow into the 3.4 `FeatureSpec`; the `Protocol` keeps the adapter (and the
  library) swappable; the `Mapping` crossing keeps consumers pandas-free.
- Stage boundaries stay crisp: 3.1 (indicators) / 3.4 (rich registry) / 3.5
  (dataset + persistence) do not bleed into each other.

### Negative

- A future absorption of `IndicatorSpec` into the 3.4 `FeatureSpec` is extra work
  (accepted: cheaper than over-designing 3.4's registry now under uncertainty).
- `.importlinter` gains one more container line and two more `source_modules`
  entries (the cheap, known maintenance cost ADR 1.3.0001 accepted).

### Neutral / trade-offs accepted

- Feature-vs-feature `independence` remains deferred until it adds value (two
  features today).
- The DoD phrase "bronze→processed" is interpreted as flow direction, not wiring;
  recorded as a `[decision]` in `technical.md` §7 so the interpretation is
  auditable.

## Implementation notes

- `.importlinter`: append `feature_engineering` to `hexagonal-layers` containers;
  add `...feature_engineering.domain` to `domain-purity` and
  `...feature_engineering.{application,domain}` to `store-no-storage-leak`, with a
  comment citing concept 2.2 D1 / LAYOUT §3 on the changed lines. Keep
  `exhaustive = False` (no `adapters/in`/`ports/in` this Stage).
- `IndicatorSpec` imports only `dataclasses`/`hashlib`/`typing`/`collections.abc`;
  `indicator_registry_hash()` mirrors the old `feature_registry_hash`
  (`feature_registry.py:471-491`) over specs sorted by name.
- The port imports `Candle` from `features.market_data.domain.entities.candle`;
  `pandas`/`pandas_ta_classic` live only in
  `adapters/out/pandas_ta/pandas_ta_indicator_calculator.py`, which validates the
  full set of 11 against `INDICATOR_SPECS` before returning (hardening the old
  `RuntimeError("Missing technical indicators")` to set equality).
- Correctness of the indicators is guarded by the oracle fixture
  (`test_indicator_canonical_formulas.py`) and the leakage test
  (`test_indicator_leakage.py`), per ADR 0.0.0021.

## References

- Related ADRs:
  [2.2.0001](./2_2_0001-market-data-feature-as-layered-container.md) (the layered-
  container pattern for the first feature, replicated here),
  [1.3.0001](./1_3_0001-import-linter-as-architecture-fitness-function.md)
  (import-linter as fitness function; per-container layers; `independence`
  deferred),
  [2.1.0002](./2_1_0002-medallion-store-port-shape.md) /
  [1.5.0002](./1_5_0002-experiment-tracker-port-shape.md) (port-as-Protocol
  posture),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md) (oracle fixtures),
  [0.0.0024](./0_0_0024-pandas-ta-classic-over-pandas-ta.md) (the indicator
  library this BC confines).
- `docs/stages/3.1-technical-indicators/concept.md` §7 D1/D2/D3/D5.
- `docs/roadmap.md` §Stage 3.1 (`arquivos_a_criar`, DoD), §Stage 3.4 (rich
  registry), §Stage 3.5 (dataset builder / persistence).
- `docs/autonomous-run-decision-ledger.md` H-2 (the 11 indicators, no expansion).
- `.importlinter` line 42 and `store-no-storage-leak` block (lines 157-175).
- Old: `src/infrastructure/schemas/feature_registry.py:7-17` (FeatureSpec mold),
  `:471-491` (hash); `src/interfaces/technical_indicator_calculator.py` (ABC →
  Protocol); `src/adapters/technical_indicator_calculator.py:46-63`.
