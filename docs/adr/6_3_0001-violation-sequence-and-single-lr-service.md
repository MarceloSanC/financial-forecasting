---
title: ADR 6.3.0001 — One violation-sequence primitive and one likelihood-ratio service; Kupiec POF and descriptive VaR are readings of it, not separate implementations
description: Architecture Decision Record
when-use: Reference when asking why Stage 6.3 has a HitSequence value object, why Kupiec POF is a kernel reused by the Christoffersen test instead of its own service, why the VaR backtest adds no math, or which files deviate from the roadmap list
keywords: [adr, evaluation, christoffersen, kupiec, pof, var, hit-sequence, likelihood-ratio, backtest, roadmap-deviation]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.3.0001
decision: Stage 6.3 builds every coverage backtest on one value object (HitSequence — violation indicators with the nominal violation rate, masked rows kept as None) and one binomial likelihood-ratio kernel (kupiec_pof, which is Kupiec's POF and Christoffersen's LR_uc at once); ChristoffersenTest, the Wilson band and the descriptive VaR backtest consume that primitive, so no statistic is implemented twice.
context_stage: 6.3-calibration-risk-backtests
bounded_context: evaluation
---

# ADR 6.3.0001 — One violation-sequence primitive, one LR service

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The roadmap lists three domain services for Stage 6.3 —
`christoffersen_test.py`, `kupiec_pof.py`, `var_descriptive.py` — as if they
were three statistics. The ratified domain doc
(`docs/domain/evaluation/probabilistic-forecast-evaluation.md`) says they are
one:

- **Kupiec POF ≡ LR_uc** by algebra: "Trocando x ↔ n_1, p* ↔ 1−p, é
  **exatamente o LR_uc** de Christoffersen (a equivalência é algébrica;
  Christoffersen fn. 6 confirma)" (doc §7.3; Kupiec 1995 expression (6)).
- **The VaR backtest is re-labelling**: "Isto **é** a cobertura marginal por
  quantil de §4.1 lida com o nome da gestão de risco — não há cálculo novo,
  há re-rotulação de pontos da grade" (doc §7.5); "LR_uc/ind/cc aplicam-se
  sem alteração (Christoffersen pp. 843–844)".
- **Relabelling hits ↔ violations** maps p ↔ 1−p and leaves the three LR
  statistics identical (doc §7.1).
- **The Wilson band and LR_uc share the binomial null** (doc §4.4); the gate
  sensitivities use "só contagens por cauda" (doc §6.9).

Three copies of the same binomial likelihood would drift (different
0·log 0 handling, different count conventions), and each would need its own
oracle check. The concept's "teste da solução mais direta" asks for the
general mechanism instead of three local ones.

## Decision

1. **One primitive: `HitSequence`** (value object,
   `evaluation/domain/value_objects/hit_sequence.py`). It carries, for one
   (model, horizon) series, a **violation** indicator per aligned row
   (`True` = violation, `False` = no violation, `None` = row masked by the
   degeneracy gate — ADR 6.3.0004), the nominal **violation rate**
   `p_viol ∈ (0, 1)`, the series' `target_timestamps`, the horizon, a
   provenance label (kind + grid levels) and the self-description needed
   when persisted (ADR 6.1.0004 pattern): the degeneracy `tolerance`, the
   gate's degeneracy rate, `includes_degenerate` and, for a DGT sub-series,
   its offset and step. The violation orientation (Kupiec
   and `rugarch` vocabulary) is used everywhere; Christoffersen's "hit =
   inside" is the same statistic with p ↔ 1−p (doc §7.1). Nominal rates come
   from the grid, never from code constants (6.1 I7): `pair_miscoverage(τ_l)
   = 2·τ_l` for a nested interval, `τ` for a lower tail, `1 − τ` for an upper
   tail.
2. **One builder service: `HitSequences`**
   (`evaluation/domain/services/hit_sequences.py`) turns a `CoverageSeries`
   into a `HitSequence` for a symmetric pair (violation = `not (l ≤ y ≤ u)`,
   FA7), a lower tail (violation = `y ≤ q̂_τ`) or an upper tail (violation =
   `y > q̂_τ`), running `DegeneracyGate.evaluate` on that same series
   (ADR 6.1.0004 pattern — the mask is never passed in).
   **The FA7 indicator rule has one owner.** Today it is written inline in
   `CoverageMetrics` (6.1: `coverage_metrics.py` ĉ(τ) `realized ≤ q` and
   PICP `low ≤ realized ≤ high`); a second copy in `HitSequences` would be
   the drift Alternative C rejects. Two predicates move next to
   `pair_miscoverage` in `value_objects/coverage_series.py` —
   `is_at_or_below(realized, quantile)` (1{y ≤ q̂}) and
   `is_inside_closed(realized, lower, upper)` ([l ≤ y ≤ u]) — and both
   `CoverageMetrics` (a fix to the 6.1 file, no behaviour change) and
   `HitSequences` consume them; the upper-tail violation is
   `not is_at_or_below`. Proven by count identities: lower tail
   `n_violations/n_observed = ĉ(τ)`, upper tail `= 1 − ĉ(τ)`, interval
   `= 1 − PICP`, on the same series and tolerance.
3. **One likelihood kernel: `kupiec_pof`**
   (`evaluation/domain/services/kupiec_pof.py`) —
   `−2 log[(1−p)^{n−x} p^x] + 2 log[(1−x/n)^{n−x} (x/n)^x]` with
   `0·log 0 = 0`. It **is** Kupiec's POF and Christoffersen's LR_uc; the
   module keeps the roadmap file name and the Kupiec citation.
4. **One LR service: `ChristoffersenTest`**
   (`evaluation/domain/services/christoffersen_test.py`) computes, on a
   `HitSequence`, the pure-convention triple (LR_uc via `kupiec_pof` on the
   conditioned counts, LR_ind, LR_cc := LR_uc + LR_ind) and, as the Kupiec
   reading, `kupiec_pof` on **all** observed rows (the same (x, n) as the
   Wilson band). It also holds the 3-state LR_uc kernel (doc §7.2 FC4) and
   the Monte Carlo p-value (ADR 6.3.0006).
5. **`VarDescriptive`** (`var_descriptive.py`) owns only the relabelling
   of grid levels as VaR levels — τ < 0.5 → lower tail, `var_level = 1 − τ`
   (VaR_α(r) = −q_{1−α}(r), long position); τ > 0.5 → upper tail,
   `var_level = τ` (short position) — the per-tail loop over τ ≠ 0.5 and the
   label "descritivo — sem claim de gestão de risco"; every number in its
   report is a `ChristoffersenReport` of a one-sided `HitSequence`. No
   library is wrapped: `arch` (listed for "VaR" in ADR 0.0.0020) computes
   VaR forecasts of its own models, not Kupiec/Christoffersen backtests of an
   external quantile grid (to be confirmed against the installed `arch` in
   the technical phase, once Stage 6.2 lands the dependency); the oracle is
   `rugarch` (ADR 6.3.0002).
6. **Roadmap deviation (declared).** The three roadmap service files are
   kept; the Stage **adds** `value_objects/hit_sequence.py`,
   `services/hit_sequences.py`, `services/wilson_band.py` and
   `services/chi_square.py` (closed-form χ² survival for df ∈ {1, 2}, kept in
   its own module so Stage 6.2's Student-t module never shares a file with
   it). `KupiecPof` stops being a service class: the roadmap contract becomes
   the `kupiec_pof` kernel plus the `kupiec_pof` field of
   `ChristoffersenStatistics` (carried by `ChristoffersenReport.statistics`). The roadmap adapter file is dropped (ADR
   6.3.0002). The roadmap line of 6.3 is rewritten in this Stage's PR
   (convention 30 of the domain doc).
7. **Applicability is a result, never an exception.** A statistic whose
   likelihood is undefined or empty for the observed data yields a report
   marked "não aplicável" with the reason, as the domain doc §7.7 requires
   ("são casos de domínio com política própria"). Status of LR_ind/LR_cc,
   checked in this order (the first that holds is reported):
   `NO_TRANSITIONS` (no observed consecutive pair) →
   `BELOW_MIN_VIOLATIONS` (observed violations < the mandatory
   `min_violations`) → `DEGENERATE_TRANSITION_MATRIX` (an empty row,
   n00 + n01 = 0 or n10 + n11 = 0, **or** an empty column, n00 + n10 = 0 or
   n01 + n11 = 0 — treated alike; this is also exactly where the oracle's
   `table(head, tail)` loses a symbol). `n_11 = 0` alone is **not** such a
   case: it is computed with the Christoffersen & Pelletier (2004) §4.1
   likelihood (numerically `0^0 = 1`). The same rule decides applicability
   of the Monte Carlo draws (ADR 6.3.0006).
8. **Numerical floor.** The LR statistics are differences of log-sums and
   can come out slightly negative (Checkpoint A: down to −2.84e-14 for
   LR_ind and −1.42e-14 for `kupiec_pof`), which would make `erfc(√(x/2))`
   fail. Every LR value in `[−1e-9, 0)` is set to `0.0` before it is stored
   or summed (LR_cc is composed after the clamp); anything below `−1e-9`
   raises `ValueError` (a bug, not noise).

## Alternatives considered

### Alternative A — Three independent services, as the roadmap lists them

- **Description:** `ChristoffersenTest`, `KupiecPof` and `VarDescriptive`
  each implement their likelihood.
- **Pros:** literal match with the roadmap file list and contract names.
- **Cons:** the same binomial likelihood written two or three times; each
  copy needs its own oracle check; the identity POF ≡ LR_uc becomes a test
  between copies instead of a fact of the code.
- **Why rejected:** contradicts the domain doc (§7.3, §7.5 "não há cálculo
  novo") and the directness test; drift between copies is exactly
  R-METRIC-1 (overview §8).

### Alternative B — Christoffersen's orientation (hit = inside) as the primitive

- **Description:** store `1{l ≤ y ≤ u}` with coverage p, and flip for tails.
- **Pros:** literal Definition 1 of Christoffersen (1998).
- **Cons:** the one-sided (VaR/Kupiec) reading, the oracle (`rugarch`
  counts `actual < VaR`) and the minimum-violations rule (C&P 2004 §5) are
  all stated in violations; every tail would carry a flip.
- **Why rejected:** equivalent statistics (doc §7.1), more flips; the
  violation orientation needs none.

### Alternative C — No primitive; services take the `CoverageSeries` directly

- **Description:** each service extracts its own indicators from the series.
- **Why rejected:** the indicator rule (FA7 ties, the mask, the nominal rate
  from the grid) would be re-derived per service — the drift 6.1 removed
  with `symmetric_pair_indices`/`pair_miscoverage`. For the same reason the
  FA7 predicates are extracted from `CoverageMetrics` (item 2) instead of
  being copied into `HitSequences`.

### Alternative D — Do nothing (follow the roadmap text literally, no ADR)

- **Why rejected:** Alternative A without a record of why.

## Consequences

### Positive

- Every coverage statistic has one code path and one oracle check.
- POF ≡ LR_uc is enforced by reuse, and a test still proves it against
  Kupiec's printed expression (6) and Table 2.
- 6.4/6.5 consume one report type per sequence (`ChristoffersenReport`),
  whatever the reading (interval, tail, VaR).

### Negative

- `KupiecPof` no longer exists as a class; the roadmap contract text changes.
- `HitSequence` is one more value object in the slice.

### Neutral / trade-offs accepted

- Two LR_uc numbers exist by design: the pure-convention one inside the
  triple (conditioned on the first observation, so LR_cc = LR_uc + LR_ind is
  exact — doc §7.2/§7.7) and the Kupiec reading on all observed rows (the
  one paired with the Wilson band — doc §4.4). Both come from the same
  kernel; the report names them apart.

## Implementation notes

- `min_violations` is a mandatory `int` (not `bool`) with no default (value
  preregistered in 6.5, doc §7.6); it counts violations over all observed
  rows.
- `ChristoffersenReport.independence_descriptive` is `True` when
  `horizon > 1` (doc §7.4, B-H7), except on a DGT sub-series, which is iid
  under the DGT null (doc §7.4); a sub-series cannot be re-partitioned.
- The report's coherence check on transitions uses exact inequalities that
  hold with gaps: Σn_ij ≤ max(n_observed − 1, 0), n01 + n11 ≤ n_violations,
  n10 + n11 ≤ n_violations, n_violations − (n01 + n11) ≤ n_observed − Σn_ij.

## References

- Domain doc §4.4, §6.9, §7.1–§7.7, §10 conventions 9, 10, 20–24, 30.
- Christoffersen, P. F. (1998), IER 39(4), 841–862 — Definitions 1–3,
  §3.1–§3.3, fn. 6. Kupiec, P. H. (1995), FEDS WP 95-24 — expression (6),
  Table 2. Christoffersen & Pelletier (2004), JFEc 2(1) — §4.1, §5.
- Related ADRs: 0.0.0020, 0.0.0021, 0.0.0054, 6.1.0002, 6.1.0004,
  6.3.0002, 6.3.0004, 6.3.0005, 6.3.0006.
