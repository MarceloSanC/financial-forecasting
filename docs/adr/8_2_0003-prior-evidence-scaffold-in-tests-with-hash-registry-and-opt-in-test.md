---
title: ADR 8.2.0003 — The prior evidence is read only by a scaffold under tests/equivalence/, gated by a committed hash registry (docs/reports/prior_evidence_registry.toml) written before any value is read, through an opt-in test that skips without the oracle, fails on any hash mismatch, asserts the declared classification of every comparison and never regenerates anything
description: Architecture Decision Record
when-use: Reference before reading any file of the prior evidence, before changing the equivalence test, or when asking why the test skips in CI and where the hashes live
keywords: [adr, evaluation, equivalence, prior-evidence, oracle, scaffold, eq-hash, eq-andaime, registry, opt-in-test, skip, regression-oracle]
status: accepted
created_at: 2026-10-23
updated_at: 2026-10-23
adr_id: 8.2.0003
decision: The prior confirmatory evidence (git-ignored data/analytics/) is frozen by docs/reports/prior_evidence_registry.toml — per file the path, content sha256, row count and physical column types from the Parquet footer — committed in its own commit before any value is read; readers, intersection, A1/A2 and the sense table live only under tests/equivalence/ (never in src/); tests/equivalence/test_official_vs_prior_evidence.py is opt-in by environment variables pointing at the oracle and official data roots, skips with a reason naming the registry when they are absent (so make check and CI skip it), fails when any hash differs from the registry, asserts that the recomputed classification of every comparison equals the one declared in the test and mirrored in the report, and never writes the registry or the report.
context_stage: 8.2-equivalence-audit
bounded_context: evaluation
---

# ADR 8.2.0003 — Prior-evidence scaffold in tests, hash registry, opt-in test

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Domain doc §5.1: the prior evidence is a regression/equivalence oracle, never
authority and never input of the official path (item 3). §5.2 (EQ-HASH): before
any value is read, the file set is fixed by content hash, versioned, with the
storage precision from the schema "registered alongside". §5.7 (EQ-ANDAIME): the
equivalence test has an oracle outside version control, cannot be a CI gate,
skips with reason when the oracle is absent, fails on hash mismatch; the durable
record is the report with the hashes. The prior files sit in the git-ignored
`data/analytics/` of the main checkout; `tests/` is the pytest `testpaths`, so
`make check` and CI collect `tests/equivalence/`.

## Decision

1. **Registry.** `docs/reports/prior_evidence_registry.toml`: per file, the path
   relative to `data/analytics/`, sha256 of the content, row count and physical
   type of every column (Parquet footer only). Committed alone, before any value
   read. It lives outside `tests/` so it survives the scaffold's retirement.
2. **Scaffold location.** Readers, alignment by `target_timestamp` and horizon,
   A1, A2 and the sense table: only under `tests/equivalence/`. No `src/` module
   reads `data/analytics/` or imports the scaffold.
3. **Opt-in.** The test reads the oracle root and the official data root from
   environment variables; absent → `pytest.skip` with a reason naming the
   registry. It never searches a default path.
4. **Fail on identity.** With the roots present, every registered file is
   hashed; any mismatch or missing file fails (never skips).
5. **Regression oracle.** The test declares, per comparison, the expected
   classification (within tolerance / explained with category / not explained)
   and asserts the recomputed one equals it, and that the declared table equals
   the table parsed from `docs/reports/equivalence_audit.md` (editing one
   without the other fails, with a visible diff). The documented command uses
   `-rs` so the skip reason is shown.
6. **Never regenerates.** The test writes neither the registry nor the report.
   The hash-check function has an always-on unit test (`tmp_path`, runs in CI).
7. **What "before any value" means.** No metric, loss, p-value, sign, verdict or
   realized-target value of the prior evidence is read before the registry
   commit; shape metadata (schema, counts, dates, ids, definition labels) is
   allowed — doc §5.2 protects the comparison set against the *new* numbers
   (concept 8.2 D11). What defines the comparison set (common baselines and
   their source, variants, sign convention, seed aggregation, u_q, the A1
   point-wise rule) is fixed in the concept (D12, D13) or in the registry
   commit, before values are read.

## Alternatives considered

### Alternative A — Version the prior files
- **Cons:** turns a git-ignored oracle into repository data; invites using it as
  input.
- **Why rejected:** §5.1 item 3; the hash is enough to identify it.

### Alternative B — Script outside the test suite
- **Cons:** the roadmap names the test file; a script has no skip/fail contract.
- **Why rejected:** roadmap 8.2 `arquivos_a_criar` and §5.7.

### Alternative C — Always-on test, or one that asserts A1/A2 only
- **Cons:** always-on breaks CI without the oracle; asserting raw A1/A2 fails on a
  legitimately explained divergence (e.g. a factor-2 pinball scale).
- **Why rejected:** §5.7 (skip without oracle) and §5.6 (explained divergences
  are legitimate outcomes).

### Alternative D — Registry inside `tests/equivalence/`
- **Cons:** retired together with the scaffold.
- **Why rejected:** §5.7 makes the report with the hashes the durable record.

## Consequences

### Positive
- Order hash → value is visible in `git log`; the oracle cannot be swapped silently.
- The official path stays free of the prior evidence.

### Negative
- The test only runs on a machine holding `data/analytics/`.

### Neutral / trade-offs accepted
- The scaffold stays in the repository as an opt-in regression oracle; its
  "retirement" (§5.7) is recorded in the report, not a deletion.

## References

- Related ADRs: 0.0.0060, 0.0.0061, 0.0.0062, 8.2.0001
- Domain doc reproduction-equivalence-and-reporting §5.1–§5.7
- pytest documentation, "How to use skip and xfail"
- Issue #232
