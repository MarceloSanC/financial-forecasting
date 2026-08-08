---
title: ADR 0.0.0024 — Use pandas-ta-classic instead of the unmaintained pandas-ta beta, confined to a single adapter and validated against canonical formulas
description: Architecture Decision Record
when-use: Reference before adding or changing a technical-indicator library, before pinning an indicator dependency, or when auditing the supply-chain provenance of feature_engineering indicators
keywords: [adr, pandas-ta, pandas-ta-classic, technical-indicators, supply-chain, rsi, macd, ema, wilder, feature-engineering, oracle, canonical-formula, dependency-pin]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "0.0.0024"
decision: Technical indicators are computed with pandas-ta-classic (a maintained fork) instead of the unmaintained pandas-ta 0.4.71b0 beta, with the import confined to a single out adapter and every indicator validated against its canonical formula by an analytic oracle fixture
context_stage: 3.1-technical-indicators
bounded_context: transversal
---

# ADR 0.0.0024 — `pandas-ta-classic` over the unmaintained `pandas-ta` beta

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

This ADR formalizes a decision already recorded in `overview.md` (§11 decision
table, `adr_id 0.0.0024`, and §10 supply-chain risk row) for which **no ADR file
existed**. Stage 3.1 (`feature_engineering`) is the first Stage to actually
consume an indicator library, so the file is authored here, in that Stage's
context, to close the traceability `overview.md` already cited.

## Context

The technical indicators (RSI, MACD, EMAs, rolling volatility, candle
range/body) are computed by a library behind an out port. The prior repo
(`financial-time-series-forecasting`) pinned **`pandas-ta==0.4.71b0`**
(`pyproject.toml:21`) — a **beta** release of a project whose upstream source has
been taken down / is effectively **unmaintained**. Forces at play:

- **Supply-chain risk is explicitly flagged.** `overview.md` §10 lists
  *"`pandas-ta` com fonte apagada / sem manutenção"* as a **high-impact** risk,
  with the mitigation *"migrar para `pandas-ta-classic`/TA-Lib + validar cada
  indicador contra o paper + teste de leakage"*. `overview.md` §11 already names
  the decision and assigns it `adr_id 0.0.0024`; the dependency list (§7) names
  `pandas-ta-classic`/TA-Lib as the indicator library.
- **The rebuild's thesis is auditability and reproducibility.** A pinned,
  installable, maintained dependency is a precondition for a reproducible
  `uv.lock` and SBOM. A beta whose source vanished cannot be re-resolved or
  audited reliably.
- **Correctness must not depend on trusting the library blindly.** Decision H-2
  (decision ledger) requires replicating the exact set of 11 indicators **and
  validating each formula** against its canonical definition — the library is an
  implementation detail behind the validation, not an authority.
- **The pilot runs in CI without native build friction.** TA-Lib ships a native
  C library that complicates the build/CI image; `pandas-ta-classic` is a
  pure-Python pip-installable fork that drops in where `pandas-ta` was.

## Decision

Depend on **`pandas-ta-classic`** (a maintained, installable fork of the original
`pandas-ta`) for RSI/MACD/EMA computation, pinned in `pyproject.toml` with a
synchronized `uv.lock`. Confine the `import pandas_ta_classic` (and `pandas`) to
the **single out adapter** `features/feature_engineering/adapters/out/pandas_ta/`;
the `domain` and `application` layers never import it (enforced by the
`domain-purity` and `store-no-storage-leak` import-linter contracts extended to
the BC in Stage 3.1).

The library is treated as an **untrusted implementation detail**: every indicator
it produces is validated against its **canonical formula** by an analytic oracle
fixture (RSI by Wilder smoothing — not SMA; MACD = EMA12 − EMA26 and signal =
EMA9(MACD); EMA recursive with `alpha = 2/(N+1)`; volatility = rolling std of
`close.pct_change()`), within a declared numeric tolerance, plus a mandatory
leakage test. If `pandas-ta-classic` ever diverges in semantics, the oracle
fixture fails the build — the migration is safe precisely because correctness is
pinned to the formula, not to the library.

## Alternatives considered

### Alternative A — Keep `pandas-ta==0.4.71b0` (status quo of the old repo)

- **Description:** Reuse the exact beta dependency the prior repo used.
- **Pros:** Zero migration; byte-for-byte parity with the old computation path.
- **Cons:** Beta release of an **unmaintained / source-deleted** project; not a
  defensible foundation for a reproducible lock/SBOM; the documented high-impact
  supply-chain risk is left unmitigated.
- **Why rejected:** Contradicts `overview.md` §10 risk mitigation and the
  reproducibility/auditability thesis of the rebuild; a vanished upstream cannot
  be re-resolved or audited.

### Alternative B — TA-Lib

- **Description:** Use the TA-Lib bindings (industry-standard C library).
- **Pros:** Mature, widely trusted, comprehensive indicator coverage.
- **Cons:** Ships a **native C dependency** that complicates the Docker/CI build
  (system package + headers); heavier than needed for an 11-indicator pilot;
  larger surface than the problem warrants.
- **Why rejected:** Build/CI friction not justified by a single-asset pilot
  computing 11 indicators. `pandas-ta-classic` is pure-Python and drop-in. TA-Lib
  remains a future option (it is named alongside `pandas-ta-classic` in
  `overview.md` §7) if coverage or performance ever demands it.

### Alternative C — Hand-implement all indicators in the adapter (no library)

- **Description:** Compute RSI/MACD/EMA manually with `pandas`/`numpy`, no TA lib.
- **Pros:** No third-party indicator dependency at all; full control of formulas.
- **Cons:** Re-implements well-known, easy-to-subtly-break formulas (Wilder RSI
  recursion, MACD signal chaining) that a maintained library already gets right;
  more code to own and test for no architectural gain.
- **Why rejected:** The oracle fixture already validates the library's output;
  owning the full implementation adds maintenance cost without reducing the
  validation burden. (`volatility_20d`/`candle_range`/`candle_body` *are* computed
  manually — they have no library primitive and the formula is trivial.)

### Alternative D — Do nothing / defer

- **Description:** Postpone the indicator library choice.
- **Why not acceptable:** Stage 3.1 cannot compute indicators without a library;
  deferring blocks the entire feature layer (Step 3) and the dataset builder
  (3.5). The decision is already pre-declared in `overview.md`; only the ADR file
  was missing.

## Consequences

### Positive

- The supply-chain risk flagged in `overview.md` §10 is mitigated: a maintained,
  installable, lockable dependency replaces an unmaintained beta.
- Correctness is pinned to the **canonical formula** via the oracle fixture, not
  to the library — the library can be swapped (e.g. to TA-Lib) later with the
  same tests guarding the result.
- The import is confined to one adapter; the rest of the BC stays pure
  (`domain-purity`/`store-no-storage-leak`), so a future library swap touches one
  file.

### Negative

- `pandas-ta-classic` is itself a community fork (lower bus-factor than a vendor
  library); accepted because the oracle fixture detects any semantic drift and
  the dependency is pinned + locked.

### Neutral / trade-offs accepted

- We accept a community fork over TA-Lib's native binary for the pilot, trading
  some ecosystem maturity for zero native-build friction; revisitable if coverage
  or performance needs grow.
- Output is coerced to `float32` (Stage 3.1 contract), an intentional divergence
  from the old `float64`; the tolerance in the oracle fixture accounts for it.

## Implementation notes

- Pin `pandas-ta-classic` in `[project].dependencies` of `pyproject.toml`;
  regenerate `uv.lock` in the **same commit** (CONVENTIONS §5, no lock-only PRs).
- The **only** import site is
  `features/feature_engineering/adapters/out/pandas_ta/pandas_ta_indicator_calculator.py`.
  `import pandas`/`pandas_ta_classic` anywhere in `domain`/`application` must fail
  `lint-imports` (intentional-break verification recorded in `technical.md` §7).
- Smoke check: `uv run python -c 'import pandas_ta_classic'`.
- The oracle fixture (`test_indicator_canonical_formulas.py`) is the correctness
  gate for the library choice — it asserts Wilder RSI (not SMA), MACD 12/26/9, EMA
  `alpha=2/(N+1)`, and rolling-std volatility within a declared `atol`/`rtol`.

## References

- Related ADRs:
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md) (per-unit oracle
  fixtures, not global byte-identical snapshots — the validation posture this ADR
  relies on),
  [3.1.0001](./3_1_0001-feature-engineering-bc-and-indicator-contracts.md)
  (the BC and indicator contracts that consume this library).
- `docs/overview.md` §7 (dependency list naming `pandas-ta-classic`/TA-Lib), §10
  (supply-chain risk row), §11 (decision table, `adr_id 0.0.0024`).
- `docs/autonomous-run-decision-ledger.md` H-2 (replicate the 11 indicators +
  validate formulas).
- Old: `financial-time-series-forecasting/pyproject.toml:21`
  (`pandas-ta==0.4.71b0`); `src/adapters/technical_indicator_calculator.py:46-57`
  (the computation being ported).
- External: `pandas-ta-classic` (maintained fork of `pandas-ta`); TA-Lib (native
  alternative).
