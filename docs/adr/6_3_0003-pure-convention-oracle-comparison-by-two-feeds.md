---
title: ADR 6.3.0003 — The pure-convention Christoffersen triple is compared with rugarch through two feeds (whole series for LR_ind, series from t = 2 for LR_uc)
description: Architecture Decision Record
when-use: Reference when asking how the golden test compares the project's pure-convention LR_uc/LR_ind/LR_cc with rugarch::VaRTest exactly, or why the domain doc's "feed the oracle from t = 2" recipe was made precise
keywords: [adr, evaluation, christoffersen, rugarch, vartest, pure-convention, conditioning, oracle, golden-test]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.3.0003
decision: For each recorded case the oracle runs VaRTest twice — on the whole violation sequence and on the sequence from t = 2 — and the pure-convention triple is compared exactly (to rounding) as LR_uc = uc.LRstat(t≥2 feed), LR_ind = cc.LRstat − uc.LRstat (whole feed), LR_cc = their sum; the Kupiec POF reading is compared with uc.LRstat of the whole feed.
context_stage: 6.3-calibration-risk-backtests
bounded_context: evaluation
---

# ADR 6.3.0003 — Pure-convention oracle comparison by two feeds

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The project adopts Christoffersen's **pure** conditioning (domain doc §7.2,
§7.7, convention 21 / FC5): every count runs over t = 2..T, `n_1 = n_01 +
n_11`, so LR_cc = LR_uc + LR_ind is exact (Christoffersen 1998 p. 847). The
golden test must "compare convenções iguais … exigindo igualdade **exata** a
menos de arredondamento; **não** se usa tolerância O(1/T)". The doc's recipe
is "alimenta o oráculo com a série a partir de t = 2 (ou descarta I_1 da
própria implementação só para o teste)".

`rugarch` 1.5.3 (code printed from the pinned image, 2026-09-28):

```r
.LR.cc: VaR.ind = as.numeric(ifelse(actual < VaR, 1, 0)); N = sum(VaR.ind); TN = length(VaR.ind)
        n <- table(head(VaR.ind, -1), tail(VaR.ind, -1))      # transitions over the T−1 pairs
        ... stat.ind = -2 * log(l1/l2); stat.uc = .LR.uc(p, TN, N); stat.cc = stat.uc + stat.ind
.LR.uc: l1 = (1 - p)^(TN - N) * p^N; l2 = (1 - N/TN)^(TN - N) * (N/TN)^N; -2 * log(l1/l2)
VaRTest returns uc.LRstat and cc.LRstat only (no LR_ind).
```

So `rugarch`'s LR_ind is already the pure LR_ind (transitions over the T−1
pairs), while its LR_uc counts all T observations. Feeding the series **from
t = 2** fixes LR_uc but moves LR_ind to the T−2 pairs from t = 3 — the pure
LR_ind is lost. Probe on the pinned image (seeded iid Bern(0.05), T = 250,
I_1 = 1, p = 0.05):

```
pure (hand)  uc=0.184712376423590 ind=1.112014544823495 cc=1.296726921247085
whole feed   uc=0.021324025180584 ind=1.112014544823476 cc=1.133338570004059
t>=2 feed    uc=0.184712376423595 ind=1.021463972799997 cc=1.206176349223592
composed     uc=0.184712376423595 ind=1.112014544823476 cc=1.296726921247070
```

Neither single feed reproduces the whole pure triple; the composition does,
to ~2e-14. This is a question of **evidence** (the oracle's code), class E.

## Decision

Each recorded case stores the outputs of **two** `VaRTest` calls — whole
sequence and sequence from t = 2 — and the comparison is:

| Project number | Oracle expression |
|---|---|
| pure LR_uc (Christoffersen triple) | `uc.LRstat` of the t ≥ 2 feed |
| pure LR_ind | `cc.LRstat − uc.LRstat` of the whole feed |
| pure LR_cc | sum of the two lines above |
| Kupiec POF (all observed rows) | `uc.LRstat` of the whole feed |

Equality is asserted with a declared **rounding** tolerance (order 1e-10
absolute; the subtraction `cc − uc` in R costs ~1e-14), never an O(1/T) one.
A case where R fails on either feed is recorded with the R error message
and is not an oracle value (domain doc §7.7).

The domain doc's recipe (§7.7, §11.3 "Neutralizar", convention 21) is made
precise in this Stage's PR — mechanics only, no theory changes: "LR_uc
compared with the feed from t = 2; LR_ind with `cc − uc` of the whole feed".

## Alternatives considered

### Alternative A — Single feed from t = 2 (the doc's literal recipe)

- **Cons:** LR_ind and LR_cc differ by O(1) (probe: 1.021 vs 1.112).
- **Why rejected:** fails the doc's own requirement of exact equality.

### Alternative B — Drop I_1 from the project's implementation for the test

- **Cons:** the project's LR_uc then conditions on I_2, LR_ind loses the
  (I_1, I_2) transition — the numbers under test are no longer the ones the
  project reports.
- **Why rejected:** tests a variant, not the implementation of record.

### Alternative C — Whole feed with an O(1/T) tolerance

- **Why rejected:** the doc forbids it; with I_1 = 1 the gap is O(1)
  (probe: 0.021 vs 0.185).

### Alternative D — Do nothing (follow the literal recipe and let LR_ind fail)

- **Why rejected:** a red golden test, or a loosened tolerance, would follow.

## Consequences

### Positive

- The full pure triple and the Kupiec reading are each compared exactly with
  an R number.
- The I_1 = 1 cases show in the fixture why the convention matters.

### Negative

- Two R calls per case; the golden test composes them (ADR 6.3.0002).

### Neutral / trade-offs accepted

- The oracle's domain is narrower than the project's: R fails whenever a
  symbol is missing in `head` or `tail` of a feed (zero violations, all
  violations, or a single violation at the first or last position of that
  feed — for the t ≥ 2 feed, a violation only at t = 1 leaves it with none).
  Those inputs are covered by analytic fixtures.

## References

- Domain doc §7.2, §7.7, §10 convention 21, §11.3.
- Christoffersen, P. F. (1998), IER 39(4) — p. 845 fn. 8, p. 847.
- `rugarch` 1.5.3 in `ff-r-oracle:4.4.1` (R 4.4.1): `VaRTest`, `rugarch:::.LR.cc`,
  `rugarch:::.LR.uc`.
- Related ADRs: 0.0.0021, 6.3.0001, 6.3.0002.
