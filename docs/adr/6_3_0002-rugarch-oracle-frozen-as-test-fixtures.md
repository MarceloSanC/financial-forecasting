---
title: ADR 6.3.0002 — The rugarch::VaRTest oracle is frozen as versioned test fixtures read directly by the golden tests; no port and no adapter in src/
description: Architecture Decision Record
when-use: Reference when asking how Stage 6.3 proves Christoffersen/Kupiec against R without R at runtime or in CI, why the roadmap file r_backtest_oracle_fixtures.py was dropped, or how to regenerate the R fixtures
keywords: [adr, evaluation, rugarch, vartest, oracle, r, fixtures, golden-test, roadmap-deviation, provenance, sessioninfo]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.3.0002
decision: The R oracle rugarch::VaRTest is frozen offline as the R-fixture unit var_test_cases under tests/fixtures/r_oracle/, in the Step's R-fixture format owned by ADR 6.2.0006, with T ≤ 500 recorded in its provenance; integration tests read that file and compare it with the stdlib domain implementation; no port and no adapter are created, and the roadmap file adapters/out/inference/r_backtest_oracle_fixtures.py is dropped.
context_stage: 6.3-calibration-risk-backtests
bounded_context: evaluation
---

# ADR 6.3.0002 — rugarch oracle frozen as test fixtures

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The DoD of Stage 6.3 says Christoffersen (LR_uc/ind/cc) and Kupiec POF
"batem com R `rugarch::VaRTest`/fixtures". Sources and constraints:

- **ADR 0.0.0020**, both bullets of its Decision:
  - "**Domain (stdlib-only, pure):** value objects such as `PairedLossSeries`,
    `QuantileForecast`, `CoverageSeries` carry their invariants … The
    statistical operations expressed as pure functions/services over these
    VOs — pinball, CRPS, the DM statistic, MCS bookkeeping, Christoffersen —
    depend only on the standard library."
  - "**Adapters (out):** libraries that compute or accelerate these
    quantities (`arch` for MCS/bootstrap/VaR, `statsmodels` for Holm/HAC,
    `sklearn`/`scoringrules` for pinball/Winkler/CRPS, …) live behind ports.
    Where no canonical Python library exists (Diebold–Mariano,
    Christoffersen, Kupiec), a thin own-implementation sits behind a port and
    is validated against an R oracle."
- **Overview §7/§8** carried the same "atrás de porta" wording for DM,
  Christoffersen and Kupiec (and R-LIBS-1 "Wrapper próprio atrás de porta +
  oráculo R + pin de versão + ADR de proveniência").
- **Human decision.** The tension between the two bullets was escalated and
  the human chose option A — formula of record in the domain; a port only
  where a Python library exists to wrap; the R oracle as versioned fixtures
  read by golden tests. It is recorded as the transversal ADR 0.0.0056
  (decisão humana de 2026-09-28, criada no PR da 6.2), which also amends the
  overview §7/§8 wording.
- **ADR 0.0.0021:** per-unit oracle checks; "R-oracle harnesses are
  version-pinned and documented per unit when introduced"; it accepts
  "an R dependency for some oracles" as authoring work. The CI and the dev
  image have no R.
- **Roadmap 6.3** lists `adapters/out/inference/r_backtest_oracle_fixtures.py`
  but no port; an adapter implements a port by definition (LAYOUT §7) and an
  adapter without one fails the `port-coverage` gate.
- **ADR 6.2.0006** (created in the Stage 6.2 PR; cited by id) is the single
  owner of the Step's R-fixture format — files per unit, number encoding,
  provenance keys, the shared `Dockerfile` and the integration test that
  walks every fixture under `tests/fixtures/r_oracle/`. This ADR does not
  restate it.
- **Test layer.** The project's pytest marker `unit` means "no I/O"; a test
  that reads a fixture file is an integration test (same orchestration
  decision for Stage 6.2).
- `rugarch` has its own mechanics limits: `VaRTest` errors when a symbol is
  missing in `head`/`tail` of the indicator (domain doc §11.3), and its
  product likelihoods underflow **silently** for large T at high violation
  rates (Checkpoint A probe, p = 0.5: T = 1 050 error ≈ 7e-9, T = 1 070 error
  ≈ 1.4e-2, T = 1 100 `NaN`, no R error).

## Decision

1. **Implementation of record = domain** (ADR 6.3.0001): `kupiec_pof` and
   `ChristoffersenTest` are stdlib-only and are the only code path that
   produces the project's numbers. No port, no adapter, no fake (ADR
   0.0.0056 option A: no Python library exists to wrap).
2. **One R-fixture unit, `var_test_cases`**, in `tests/fixtures/r_oracle/`,
   in the Step's R-fixture format (ADR 6.2.0006). What is specific to 6.3:
   the cases — seeded iid and clustered violation sequences for several
   violation rates, cases with I_1 = 1, and boundary cases — each with its
   0/1 violations and violation rate and, for two feeds (whole sequence;
   sequence from t = 2 — ADR 6.3.0003), `uc.LRstat` and `cc.LRstat` or the
   expected R error message; and the T bound of item 3, recorded in the
   provenance.
3. **Numeric safety of the oracle.** The generator rejects (does not write)
   any case whose R output is non-finite, and keeps T within a declared safe
   bound — T ≤ 500 for every violation rate, below the underflow onset
   measured above (≈ 1 050 at p = 0.5, later for smaller p); each case is
   re-checked for finite `uc`/`cc` and the bound is stated in `provenance`.
   Optionally the generator also calls `rugarch:::.LR.uc(p, TN, N)` directly
   to record a Kupiec / pure-LR_uc value where `VaRTest` errors (zero
   violations, a single violation only at t = 1 or t = 2); if used, the case
   records `source: ".LR.uc"`.
4. **Integration tests read the fixture**:
   `tests/integration/features/evaluation/test_christoffersen_vs_rugarch.py`
   (pure triple vs the two-feed composition) and
   `tests/integration/features/evaluation/test_kupiec_vs_oracle.py` (Kupiec
   POF vs `uc.LRstat` of the whole feed) — the roadmap's file names, moved
   from `tests/unit/` because they read a file — with a declared rounding
   tolerance, never an O(1/T) one (domain doc §7.7). Recorded R errors are
   asserted as domain policy ("não aplicável" or a domain-defined value),
   not as oracle values. The Step's fixture integration test (ADR 6.2.0006)
   also covers this unit. Unit tests use analytic fixtures only.
5. **Roadmap deviation (declared):** `adapters/out/inference/r_backtest_oracle_fixtures.py`
   leaves `arquivos_a_criar`; the two oracle tests change path to
   `tests/integration/features/evaluation/`; `camada_alvo` becomes `domain`;
   the Stage PR rewrites the 6.3 line. No `.importlinter`, `pyproject.toml` or `uv.lock`
   change.

## Alternatives considered

### Alternative A — Port + fixture-replay adapter + fake + contract suite

- **Description:** a `CoverageBacktestBackend` port whose "real" adapter
  answers by looking up the frozen R outputs (ADR 6.1.0001 pattern).
- **Pros:** a literal reading of "atrás de porta"; `port-coverage`-gated.
- **Cons:** a port whose only implementation is a lookup table of test data,
  with no computation and no production consumer.
- **Why rejected:** ADR 0.0.0056 (human decision): a port only where a
  Python library exists to wrap.

### Alternative B — Adapter that runs R at call time (`Rscript` subprocess)

- **Pros:** answers any input.
- **Cons:** ADR 0.0.0021 accepts an R dependency as authoring work for some
  oracles; turning it into a runtime/CI dependency would put R in the dev
  image and in CI, which have none.
- **Why rejected:** the R dependency stays offline, in the pinned image.

### Alternative C — Adapter file without a port (the roadmap text)

- **Why rejected:** breaks LAYOUT §7 and `port-coverage`.

### Alternative D — Do nothing (analytic fixtures only)

- **Why rejected:** the DoD requires an R oracle; analytic fixtures alone
  cannot catch a shared misreading of the paper.

## Consequences

### Positive

- Reproducible from one command in a pinned image, provenance tested; no R
  in `src/`; one format for R oracles in the Step, with one owner.

### Negative

- The oracle check is a plain integration test, not a `port-coverage`-gated
  contract; the Step's fixture test partly compensates.
- The oracle only covers T ≤ 500; larger T is covered by analytic fixtures
  (the domain works in log-sums, no product likelihoods).

### Neutral / trade-offs accepted

- The integration test composes the pure-convention numbers from two R
  feeds (ADR 6.3.0003).

## Implementation notes

- Regeneration command and encoding: as in ADR 6.2.0006, with the
  generator `var_test_cases.R`.
- The R side receives `actual = ±1`, `VaR = 0` built from the violation
  indicators, so there is no tie (`actual < VaR` is strict in `rugarch`).
  The FA7 tie conventions (closed interval vs `≤` lower tail — ratified in
  domain doc §4.5) are therefore not exercised by the oracle; they are
  measure-zero for continuous returns and are covered by analytic fixtures.

## References

- ADR 0.0.0020 (Decision, both bullets); ADR 0.0.0021 (Consequences,
  Implementation notes); ADR 0.0.0056 (decisão humana de 2026-09-28, criada
  no PR da 6.2); ADR 6.2.0006 (Stage 6.2 PR); ADRs 6.1.0001, 6.3.0001,
  6.3.0003.
- Overview §7, §8 R-LIBS-1; LAYOUT §3, §7.
- Domain doc §4.5, §7.7, §11.3 (`rugarch::VaRTest` mechanics).
- `rugarch` 1.5.3 — `VaRTest`, `LR.cc.test`, `rugarch:::.LR.cc`,
  `rugarch:::.LR.uc`, printed from the installed namespace in
  `ff-r-oracle:4.4.1` (R 4.4.1) on 2026-09-28.
