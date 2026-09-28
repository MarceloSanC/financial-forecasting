---
title: ADR 6.3.0005 — Count-based kernels (Wilson band, Kupiec POF, 3-state LR_uc) accept real-valued counts so the H1 gate can run on counts averaged across seeds
description: Architecture Decision Record
when-use: Reference when asking why wilson_band/kupiec_pof/the 3-state LR_uc take floats instead of integer counts, which counts the 3-state LR_uc uses, or where the averaging across seeds happens
keywords: [adr, evaluation, wilson, kupiec, pof, three-state, seeds, counts, h1-gate, b-seeds]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.3.0005
decision: The count-based kernels take a real count 0 ≤ x ≤ n and a real n > 0 (0·log 0 = 0), so 6.5 can feed them the per-tail counts averaged across seeds with the averaged number of non-degenerate points; the 3-state LR_uc takes the two one-sided tail counts (y ≤ q̂_τl, y > q̂_τu) on all non-degenerate rows, the same counts as the per-tail Wilson gate; sequence-based statistics (the Christoffersen triple, the Monte Carlo p-value) stay integer and per seed.
context_stage: 6.3-calibration-risk-backtests
bounded_context: evaluation
---

# ADR 6.3.0005 — Count kernels accept mean counts

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

B-SEEDS (domain doc §6.9, ADR 0.0.0010) fixes how the candidate with S seeds
enters H1:

- "Cobertura e degeneração do candidato são a **média entre seeds** …; a
  banda de Wilson usa como n os pontos alinhados não-degenerados (≈ T),
  **nunca S·T**";
- "**Gate H1 e suas sensibilidades** (§8.5: bandas por cauda, LR_uc de 3
  estados, partição de DGT em h+7) usam **só contagens** por cauda, sem
  transições; entram com as contagens médias entre seeds e o mesmo n";
- "**Backtests com transições** (LR_ind, LR_cc) exigem uma sequência
  binária; são computados **por seed**".

Doc §4.4 adds that n is the number of non-degenerate points and, "com S
seeds, a média entre seeds desse número". A mean of integer counts is in
general not an integer, and so is a mean of n when degeneracy differs by
seed. The averaging itself belongs to the consumer (6.5; the issue keeps
6.3 "por série").

Convention 21 of the domain doc (FC5, "todas as contagens sobre t = 2..T,
n_1 = n_01 + n_11") is the conditioning of the **2-state Christoffersen
triple**, needed for the exact identity LR_cc = LR_uc + LR_ind. It does not
govern the count-only statistics: the doc's own worked regions for the
formal test associated with the Wilson band (§4.4, "Wilson aceita c ∈ [4,
16], LR_uc a 5 % aceita c ∈ [5, 16]" at T = 500) and the gate sensitivities
(§6.9, §8.5) use the counts over all observed points. This ADR delimits that
scope explicitly; the Stage PR writes the delimitation into convention 21.

## Decision

1. `wilson_interval`/`WilsonBand.evaluate`, `kupiec_pof` and the 3-state
   LR_uc kernel take `count`/`n` as **real numbers** with `0 ≤ count ≤ n`,
   `n > 0`, finite; the likelihoods use `0·log 0 = 0`. BCD 2001 Eq. (4) and
   Kupiec's expression (6) are smooth in (x, n), so the value at a mean count
   is well defined; for integer inputs nothing changes.
2. The **3-state LR_uc** (Christoffersen 1998 §4.2, χ²(2), doc §7.2 FC4)
   takes `lower_count = #{y ≤ q̂_{τ_l}}`, `upper_count = #{y > q̂_{τ_u}}` and
   `n` over all non-degenerate rows, with nominal rates `τ_l` and `1 − τ_u`
   — the **same counts** the per-tail Wilson gate uses (doc §8.5 condition 1),
   because it is that gate's sensitivity. It is not conditioned on the first
   observation (it has no transitions; convention 21 scopes only the 2-state
   triple). The Kupiec POF reading and the Wilson band likewise use all
   observed rows.
3. Sequence-based statistics stay integer and per series: the Christoffersen
   triple (transitions need a binary sequence) and the Monte Carlo p-value.
4. Averaging across seeds is **not** done in 6.3: no service here receives S
   series. 6.5 averages and calls the kernels.

## Alternatives considered

### Alternative A — Integer-only kernels; the consumer rounds the mean count

- **Cons:** rounding is an unregistered researcher choice that can flip the
  verdict at the band edge (the Wilson and LR_uc regions differ by one count
  at the boundary — doc §4.4).
- **Why rejected:** introduces a rule the doc does not have.

### Alternative B — Kernels receive the S per-seed sequences and average inside

- **Cons:** moves B-SEEDS aggregation into 6.3, which belongs to the
  consumer (6.5); couples the kernel to a seed container.
- **Why rejected:** out of the Stage's frontier.

### Alternative C — 3-state LR_uc on pure-convention counts (t = 2..T)

- **Cons:** the gate's Wilson bands use all non-degenerate rows; a
  sensitivity on different counts would disagree for a reason unrelated to
  the test.
- **Why rejected:** doc §6.9 ties the gate and its sensitivities to the same
  counts and n.

### Alternative D — Do nothing (leave the signature to the technical)

- **Why rejected:** the signature is a contract 6.5 depends on.

## Consequences

### Positive

- 6.5 applies the gate and its sensitivities with one rule and no rounding.

### Negative

- The oracle (`rugarch`) only exercises integer counts; real-valued counts
  are verified by analytic fixtures (smoothness and agreement with the
  integer case).

### Neutral / trade-offs accepted

- A "count" can be fractional in a report; the reports say so in their
  docstrings.

## References

- Domain doc §4.4, §6.9, §7.2 (FC4), §8.5; convention 19 (B-SEEDS), 20, 26.
- Brown, Cai & DasGupta (2001), Stat. Sci. 16(2) — §3.1.1 Eq. (4).
- Kupiec (1995), FEDS WP 95-24 — expression (6).
- Christoffersen (1998), IER 39(4) — §4.2.
- Related ADRs: 0.0.0010, 0.0.0011, 6.3.0001.
