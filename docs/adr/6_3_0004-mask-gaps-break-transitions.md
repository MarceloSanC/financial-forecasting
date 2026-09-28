---
title: ADR 6.3.0004 — Rows masked by the degeneracy gate stay as gaps in the hit sequence; LR transitions are counted only between consecutive observed rows
description: Architecture Decision Record
when-use: Reference when asking how LR_ind/LR_cc treat rows removed by the degeneracy gate, what the "com/sem lacunas" profile pair of the domain doc means in code, or why the hit sequence stores None
keywords: [adr, evaluation, christoffersen, lr-ind, degeneracy-gate, mask, gaps, transitions, markov, sensitivity]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.3.0004
decision: A HitSequence keeps one slot per aligned row, with None for a row masked by the degeneracy gate; Markov transitions n_ij are counted only over pairs of consecutive rows that are both observed (each gap restarts the chain, conditioning on the first observation of each segment), and the "sem lacunas" profile variant is the same sequence built with the degenerate rows included.
context_stage: 6.3-calibration-risk-backtests
bounded_context: evaluation
---

# ADR 6.3.0004 — Mask gaps break transitions

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Calibration metrics and backtest hits use only the non-degenerate rows (ADR
0.0.0011; domain doc §5.3 item 2). For a distributional model with a low but
non-zero degeneracy rate, the doc declares the consequence (§5.3 "Limitação
declarada"): "retirar as linhas degeneradas do hit sequence (item 2) abre
lacunas nas **transições** de que o LR_ind depende (§7.2); … o pré-registro
deve declarar que, nesse caso, LR_ind/LR_cc são computados sobre a
sequência com lacunas, com a versão 'com/sem' as lacunas reportada lado a
lado **no perfil** (ICH E9 §5.3)". LR_ind/LR_cc never enter the H1 gate, so
the choice cannot change a verdict.

The doc does not say how transitions are counted across a gap. Options:
(A) compress — treat the remaining rows as consecutive, bridging the gap;
(B) count only pairs of consecutive rows that are both observed — each gap
restarts the chain.

Evidence (triage `evidence-resolution`, 2026-09-28, researcher report):
no primary source prescribes gap handling. Christoffersen (1998, p. 845
fn. 8): "as is standard, I condition on the first observation everywhere";
the chain is defined on (I_{t−1}, I_t) for adjacent t. Christoffersen &
Pelletier (2004, CIRANO WP §4.1, p. 7): "T_ij denotes the number of
observations with a j following an i". Implementations have no time index:
`rugarch` (`table(head, tail)`) and `GAS` (loop over `Hit[i-1]`, `Hit[i]`)
bridge removed rows (A) by omission; MATLAB `varbacktest` discards NaN rows
before testing (A, without discussing transitions). Under H0 (iid) both A
and B preserve the null for a selection independent of the hits; under the
first-order Markov alternative, a bridged pair across k missing rows follows
Π^{k+1}, not Π (derivation). Class **C**.

## Decision

`[decision:C] 6.3-GAPS — transitions of the LR test across rows masked by the degeneracy gate`
`Escolha: B (pairs of consecutive observed rows only; each segment conditions on its first observation) · Alternativas: A (compress) · Degrau (C): 1`
`Base: domain doc §5.3 "abre lacunas nas transições … computados sobre a sequência com lacunas"; Christoffersen 1998 p. 845 fn. 8 "I condition on the first observation everywhere" [doi ok]`
`Sensibilidade pré-registrada: "sem lacunas" = degenerate rows included (doc §5.3 "Limitação declarada" cites ICH E9 §5.3; doc §10.1 B-GATE record ties "com/sem as lacunas" to Simmons et al. 2011 req. 5) · Reversível: sim`

1. `HitSequence.violations` has one entry per row of the `CoverageSeries`,
   `None` where the gate masked the row. Counts for the Wilson band and the
   Kupiec reading use every non-`None` entry.
2. Transitions (n_00, n_01, n_10, n_11) are counted over t such that rows
   t−1 and t are both non-`None`; the pure-convention LR_uc uses n_1 = n_01 +
   n_11 and n = n_0 + n_1 over the same pairs, so LR_cc = LR_uc + LR_ind
   stays exact with gaps. Without gaps this is exactly the pure convention
   (t = 2..T).
3. The rung-1 reading: the ratified doc speaks of gaps **in the
   transitions** and of computing "sobre a sequência com lacunas" — under
   compression there would be no gap in the transitions. Rung 3 agrees
   (first-order transitions are between adjacent periods).
4. The doc's "com/sem as lacunas" profile pair is: **com** = the sequence
   above; **sem** = the same builder with the degenerate rows **included**
   (`include_degenerate=True`, no mask, no gaps). "Sem" follows the sources
   the doc attaches to this requirement — ICH E9 §5.3 in the §5.3
   "Limitação declarada" paragraph, and Simmons et al. (2011) req. 5 ("report
   what the statistical results are if those observations are included") in
   the B-GATE decision record of §10.1 (its "Sensibilidade pré-registrada":
   "LR_ind/LR_cc com/sem as lacunas reportados lado a lado no perfil") —
   both about re-including eliminated observations. Choosing which variant
   a report shows is the consumer's (6.5); 6.3 provides both. On a series
   whose degeneracy rate is 100 % (the point baselines, degenerate by
   specification) there is no "sem lacunas" variant: the builder returns
   the all-`None` sequence and every statistic is "não aplicável" — the
   point baselines do not enter the backtests (doc §5.3 item 2, §7.2).
5. The Monte Carlo null (ADR 6.3.0006) simulates on the observed positions
   only, keeping the same gaps, so its null matches the statistic.

## Alternatives considered

### Alternative A — Compress (bridge the gaps)

- **Pros:** what `rugarch`/`GAS`/`varbacktest` do by omission; the whole
  observed count enters LR_uc.
- **Cons:** mixes (k+1)-step pairs into a one-step transition matrix under
  the alternative; contradicts the doc's "lacunas nas transições".
- **Why rejected:** rung 1 discriminates for B. Not added as a further
  sensitivity: LR_ind never gates H1 and the doc's "sem lacunas" variant
  already shows the effect of the mask.

### Alternative B′ — "Sem lacunas" read as the compressed sequence

- **Why rejected:** both sources the doc cites for the side-by-side report
  are about including the eliminated observations, not about how to bridge
  them.

### Alternative C — Do nothing (refuse LR_ind when any row is masked)

- **Why rejected:** the doc requires LR_ind/LR_cc on the sequence with gaps.

## Consequences

### Positive

- One-step transitions keep their meaning; the identity LR_cc = LR_uc +
  LR_ind is exact in every case.
- The mask's effect on the profile is visible (with/without the degenerate
  rows).

### Negative

- Each gap drops one observation from the pure LR_uc count (the first row of
  each segment is conditioned on). That this is small at the rates the 6.5
  threshold allows is a **premise, not a measurement**: 6.5 confirms it on
  the cohort when it fixes the threshold (the transition counts are
  reported, so the loss is visible).

### Neutral / trade-offs accepted

- Differs from what the R oracle would do with rows removed; the oracle is
  fed contiguous sequences only (ADR 6.3.0002), so the comparison is
  unaffected.

## References

- Domain doc §5.3 (item 2, "Limitação declarada"), §7.2, §7.7, §10.1 B-GATE.
- Christoffersen, P. F. (1998), IER 39(4), 841–862, DOI 10.2307/2527341 —
  p. 845 fn. 8.
- Christoffersen, P.; Pelletier, D. (2004), JFEc 2(1), 84–108, DOI
  10.1093/jjfinec/nbh004 — CIRANO WP 2003s-05 §4.1 p. 7.
- Simmons, Nelson & Simonsohn (2011), Psych. Sci. 22(11) — req. 5 p. 1363.
- `rugarch` `R/rugarch-tests.R` `.LR.cc`; `GAS` `R/Testing.R`
  `Christoffersen`; MATLAB `varbacktest` documentation (implementation
  behaviour, not prescription).
- Related ADRs: 0.0.0011, 6.1.0004, 6.3.0001, 6.3.0006.
