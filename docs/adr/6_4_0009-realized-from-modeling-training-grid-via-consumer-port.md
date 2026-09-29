---
title: ADR 6.4.0009 — RefreshGold reads the realized return from the modeling slice's single training grid through a consumer-owned TrainingGridReader port satisfied by a new ReadTrainingGrid use case, identifies it by DatasetContentFingerprint and refuses a grid whose fingerprint differs from the cohort's frozen value
description: Architecture Decision Record
when-use: Reference when asking why the gold's realized series starts after the warm-up prefix, why evaluation depends on a modeling use case for the dataset, how decision_idx and the realized index are guaranteed to share an origin, why the gold manifest carries a DatasetContentFingerprint and grid_trimmed_prefix instead of a DatasetFingerprint, or what a refresh does when the dataset changed after the cohort ran
keywords: [adr, evaluation, modeling, training-grid, warmup, trim, realized, target-return, decision-idx, dataset-content-fingerprint, consumer-owned-port, bc-independence, type-checking, cohort-freeze]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.4.0009
decision: The realized series of RefreshGold is the modeling slice's single training grid (build_training_grid via load_training_grid, ADR 5.5.0004), read once through a TrainingGridReader Protocol declared in evaluation/application/ports/out (`__call__(*, asset_id) -> TrainingGrid`, the supplier's type annotated under TYPE_CHECKING) and satisfied by duck typing by a new additive ReadTrainingGrid use case in modeling/application/use_cases that delegates to load_training_grid with the modeling columns computed once in the composition root; RealizedReturns is built from the grid's ISO timestamps and target_return, so I5 compares decision_idx with an index of the same trimmed grid by exact equality; the grid is identified by DatasetContentFingerprint.compute over its timestamps and columns, which must equal the frozen fingerprint carried by RefreshGoldCommand (else GridFingerprintMismatchError before any effect); the manifest and realized_provenance record that fingerprint and grid_trimmed_prefix. This amends items 3–4 of ADR 6.4.0004 and supersedes its decision 6.4-C4c.
context_stage: 6.4-gold-builders-and-quality-gates
bounded_context: evaluation
---

# ADR 6.4.0009 — Realized return from the modeling training grid

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — amends [ADR 6.4.0004](./6_4_0004-evaluation-inputs-silver-reader-port-and-medallion-dataset.md)
items 3 (realized read) and 4 (fingerprint), and supersedes its decision
record `6.4-C4c`. Items 1, 2 and 5 of ADR 6.4.0004 (silver port, cohort read,
data edge) stand.

## Context

Execution finding (Stage 6.4 Checkpoint C block 4, ALTA-1, 2026-09-29):

- Stage 5.5 (merged in `develop`, PR #121) made every modeling writer read the
  TFT dataset through one reader that **trims the warm-up prefix**
  ([ADR 5.5.0004](./5_5_0004-single-training-grid-warmup-trim.md); concept 5.5
  I9 "Mesmo grid para todos os modelos", D11). The rule is the pure domain
  service `build_training_grid(rows, *, columns) -> TrainingGrid(timestamps,
  columns, trimmed_prefix)` in `modeling/domain/services/training_grid.py`; the
  store read is `load_training_grid(*, store, asset_id, columns)`
  (`run_confirmatory_cohort.py:260-265`); the columns are
  `modeling_columns()` (`train_gbm_quantile.py:215`: enabled registry
  features, calendar features, `target_return`).
- The writers persist `decision_idx` as an index into the **trimmed** grid and
  `target_timestamp_utc = grid.timestamps_iso()[decision_idx + h]`. The start
  of the grid (`trimmed_prefix`) is not persisted anywhere; the grid is
  identified only by its `DatasetContentFingerprint` (`grid_fingerprint`,
  `train_gbm_quantile.py:225`), frozen in the cohort spec
  (`config/cohorts/aapl_confirmatory.toml`, `dataset_fingerprint`) and
  re-checked by the run (`DatasetMismatchError`,
  `run_confirmatory_cohort.py:330-340`). `dim_run` carries no fingerprint.
- `RefreshGold._read_realized` (as built by Task 11) read the **whole**
  dataset through the shared `MedallionStore`. Its session index is shifted by
  the trimmed prefix, so the I5 rule of `SeriesAssembly`
  (`index(decision_timestamp) == decision_idx`) fails on every series. A
  read-only probe on a copy of cohort `aapl_confirmatory-r0-665f45d9169a`
  (96 runs) measured an offset of 251 sessions and 32
  `decision_index_mismatch` findings: every real refresh would be `BLOCKED`.
- `evaluation` may not import modeling behaviour
  ([ADR 0.0.0053](./0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md)
  item 2: behaviour crosses through a port owned by the consumer; item 3: data
  crosses declared). `check_port_coverage` accepts as the real of a consumer
  port a public class of another slice's `application/use_cases` with the same
  annotations, imported by the `[fake, real]` contract (#93; precedents
  `PredictionPersister` ← `PersistPredictions`, #68).

## Decision

`[decision:C] 6.4-C4d — source and identity of the realized input after the 5.5 grid`
`Escolha: consumer-owned TrainingGridReader satisfied by a new modeling use case ReadTrainingGrid (delegates to load_training_grid); RealizedReturns = the trimmed grid; DatasetContentFingerprint checked against the cohort's frozen value · Alternativas: A move the grid to shared; B′ local copy of the trim in evaluation; C persist a grid descriptor in silver/spec; D infer the offset from the data · Degrau (C): 1`
`Base: ADR 5.5.0004 Decision ("One training-dataset reader in the modeling slice"); concept 5.5 I9/D11; ADR 0.0.0053 items 2–3; LAYOUT §4 ("Um segundo consumidor não é motivo para mover"); LAYOUT §7 (type-only perimeter); check_port_coverage #93; run_confirmatory_cohort.py:330-340 (DatasetMismatchError precedent)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. **Port** `TrainingGridReader` (port-out,
   `evaluation/application/ports/out/training_grid_reader.py`):
   `__call__(self, *, asset_id: str) -> TrainingGrid`. `TrainingGrid` is the
   supplier's value (`modeling/domain/services/training_grid.py`) and is
   imported **only under `if TYPE_CHECKING:`** — a type-only cross-slice edge,
   invisible to `bc-independence` (`exclude_type_checking_imports = True`) and
   therefore declared by name in the perimeter of LAYOUT §7 and in the comment
   of the contract in `.importlinter` (precedent: the `PredictionPersister`/
   `RunRecordPersister` annotations, #68). `RefreshGold` only reads attributes
   of the returned value (`timestamps_iso()`, `column("target_return")`,
   `columns`, `trimmed_prefix`); if the implementation ever needs a runtime
   import, it enters `bc-independence` as a named exception (22 → 23), never
   silently.
2. **Real**: a new use case `ReadTrainingGrid(*, store: MedallionStore,
   columns: Sequence[str])` in `modeling/application/use_cases/
   read_training_grid.py`, `__call__(*, asset_id) -> TrainingGrid`, which only
   delegates to `load_training_grid` — additive, no new rule, no change to the
   5.5 writers. Fake `FakeTrainingGridReader` (rows per asset, delegating to
   the same domain service `build_training_grid`) and a `[fake, real]`
   contract suite (trimmed prefix reported, chronological rows, interior
   missing value and no usable row raise in both legs).
3. **Wiring**: the composition root builds
   `ReadTrainingGrid(store=store, columns=columns)` with the same
   `columns = modeling_columns()` it already computes for the confirmatory
   cohort, and injects it into `RefreshGold` in place of the `MedallionStore`.
4. **Realized**: `RealizedReturns(timestamps=grid.timestamps_iso(),
   returns=grid.column("target_return"))`. Index 0 is the first session of the
   trimmed grid — the same origin as the writers' `decision_idx`. I5 stays an
   **exact** equality (same grid, same function, same columns).
5. **Identity**: `DatasetContentFingerprint.compute(hasher=…, asset_id=asset,
   timestamps=grid.timestamps_iso(), columns=grid.columns)` — the same VO and
   inputs as the 5.5 `grid_fingerprint`. `RefreshGoldCommand` gains a required
   `dataset_fingerprint: str` (the value frozen in the cohort spec). A
   mismatch raises `GridFingerprintMismatchError` (`ApplicationError`, in the
   use case module) right after the grid read, before the assembly and before
   any effect — it mirrors `DatasetMismatchError` of the confirmatory run:
   the data is not the one the cohort trained on, so there is no series to
   judge.
6. **Record**: `GoldManifest.dataset_fingerprint` and
   `QualityCheckContext.dataset_fingerprint` become
   `DatasetContentFingerprint`; both carry `grid_trimmed_prefix` (the start of
   the grid, which 5.5 does not persist), and the `realized_provenance` detail
   (WARN/REPORTED) prints it. `DatasetFingerprint`, the `close`/`volume` sums,
   the `PARQUET_FILE_HASH` literal and the use-case helpers `_timestamp`/
   `_number` leave `RefreshGold`.

## Alternatives considered

### Alternative A — Move `TrainingGrid`/`build_training_grid` to `shared`

- **Pros:** `evaluation` would import it directly, no port.
- **Cons:** the grid has an owner (ADR 5.5.0004 places the reader in the
  modeling slice); LAYOUT §4: "Um segundo consumidor não é motivo para mover:
  é uma aresta de dados a declarar"; the column set comes from the
  `feature_engineering` registry, which `shared` may not import.
- **Why rejected:** ownership, not consumer count, decides placement.

### Alternative B′ — Local copy of the trim in `evaluation`

- **Pros:** no dependency on modeling at all.
- **Cons:** a second owner of the rule (`usable_start` + columns); any change
  in 5.5 (columns, rule) would silently desynchronise the realized index from
  `decision_idx` — the exact defect this ADR fixes.
- **Why rejected:** ADR 5.5.0004 replaced four copies with one reader; a fifth
  copy reintroduces what it removed.

### Alternative C — Persist a grid descriptor (start, fingerprint) in silver or in the cohort spec

- **Pros:** the refresh would not need to rebuild the grid.
- **Cons:** 5.5 does not persist it; adding a field to the spec changes the
  hashed payload and invalidates the `CohortHash` of the cohort already run
  (ADR 5.5.0001); a silver schema change to a closed Stage for a value the
  grid read already recomputes.
- **Why rejected:** changes closed contracts for information that is
  derivable from the owner's read.

### Alternative D — Infer the offset from the data (align on the first matching timestamp)

- **Pros:** no new port.
- **Cons:** I5 becomes circular — the index that the rule verifies becomes the
  one that is adjusted until it passes; a shifted or rebuilt dataset would be
  "aligned" instead of detected.
- **Why rejected:** removes the check it is meant to satisfy.

## Consequences

### Positive

- Realized index and `decision_idx` share the origin by construction; on the
  real cohort the 32 `decision_index_mismatch` findings disappear (measured in
  the Stage technical §7 on a copy of `aapl_confirmatory-r0-665f45d9169a`).
- The gold is tied to the frozen cohort data: a rebuilt dataset stops the
  refresh before anything is written, like the confirmatory run.
- The identity no longer depends on the file hash (#120 is no longer an input
  of 6.4) and covers `target_return` directly.

### Negative

- `evaluation` knows the name of a modeling type (type-only) and depends on a
  modeling use case at wiring time — declared, not hidden.
- The composition "fingerprint of a grid = `DatasetContentFingerprint` over
  `timestamps_iso()` and `columns`" is written in two call sites (5.5
  `grid_fingerprint`, which `evaluation` may not import, and `RefreshGold`).
  The hash rule itself lives only in the VO; the e2e asserts that both values
  are equal on the same grid, so drift fails the build.
- ADR 6.4.0002 item 6 and ADR 6.4.0005 item 8 still name `DatasetFingerprint`
  as the recorded identity; read them as `DatasetContentFingerprint` +
  `grid_trimmed_prefix` per this ADR.

## References

- ADR 5.5.0004; concept 5.5 I9, D11; ADR 5.5.0001 (cohort hash).
- ADR 0.0.0053 items 2–3; LAYOUT §4, §7; `scripts/check_port_coverage.py`
  (#93); issue #68 precedent.
- ADR 6.4.0004 (amended), 6.4.0002, 6.4.0003 (I5 rule), 6.4.0005 (manifest).
- Issues #117, #99 (closed by 5.5), #120.
