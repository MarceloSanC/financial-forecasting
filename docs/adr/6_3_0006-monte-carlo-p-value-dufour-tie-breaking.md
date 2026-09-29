---
title: ADR 6.3.0006 — The Monte Carlo p-value of the Christoffersen tests uses Dufour's randomized tie-breaking, a reference conditioned on the same applicability event as the observed statistic, a mandatory seed and draw count, and is defined for h = 1 only
description: Architecture Decision Record
when-use: Reference when asking how the h+1 Monte Carlo sensitivity p-value is computed, how ties of the discrete LR statistic are broken, why null draws that would be "não aplicável" are redrawn, in what order the RNG is consumed, or why the function refuses h > 1
keywords: [adr, evaluation, christoffersen, monte-carlo, dufour, p-value, ties, seed, applicability, conditioning, sensitivity]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.3.0006
decision: The Monte Carlo p-value (sensitivity at h+1, domain doc §7.6 FC6) simulates iid Bernoulli(p) on the observed positions of the HitSequence with a seeded stdlib random.Random consumed in a fixed order, computes p̃ = (N·G̃_N + 1)/(N + 1) with Dufour's randomized tie-breaking, uses the first N draws as the LR_uc reference and the first N draws that satisfy the same applicability rule as the observed LR_ind (redrawing up to a declared cap) as the LR_ind/LR_cc reference, takes seed and N as mandatory arguments, and raises for horizon > 1.
context_stage: 6.3-calibration-risk-backtests
bounded_context: evaluation
---

# ADR 6.3.0006 — Monte Carlo p-value with Dufour tie-breaking

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Domain doc §7.6 (FC6): the reported p-value is the asymptotic χ²; "Como
**sensibilidade em h+1**, o p-valor **Monte Carlo exato sob iid Bern(p)** de
Christoffersen & Pelletier (2004, §4.3 …; técnica de Dufour) … p̂_N(LR_0) =
(N·Ĝ_N(LR_0) + 1)/(N + 1). Só h+1 admite o MC sem parâmetro de incômodo
(§7.4)." The doc does not say how Ĝ_N handles ties, nor what to do with null
draws on which LR_ind is not defined. The LR statistics of a binary sequence
are discrete, so ties are frequent (LR_uc takes one value per violation
count).

Evidence (triage `evidence-resolution`, 2026-09-28; researcher report and
verifier; class **E**):

- Christoffersen & Pelletier (2004), CIRANO WP 2003s-05, §4.3 p. 9: "When
  working with binary sequences the test values can only take a countable
  number of distinct values. Therefore, we need a rule to break ties", with
  uniforms U_i, i = 0..N. The WP prints the first term with "<", which counts
  ties twice (G̃ can reach 2). §5 p. 11: "we do not use Monte Carlo samples
  with zero or one VaR violations".
- Dufour (2006), J. Econometrics, DOI 10.1016/j.jeconom.2005.06.007 (CIRANO
  WP 2005s-02): Eqs. (2.30)–(2.31) p. 8, G̃_N = 1 − F̂_N[x] + T̄_N with
  F̂_N = (1/N)Σ1(S_i ≤ x) (Eq. 2.8, p. 4) and T̄_N = (1/N)Σ δ(S_i − x)·1(U_i ≥ U_0);
  Eq. (2.33) p. 8 orders the two p-values (the randomized one is never
  larger); Eq. (2.37) p. 9, "P[p̂_N(S_0) ≤ α] ≤ P[p̃_N(S_0) ≤ α] =
  I[α(N+1)]/(N+1)": **under exchangeable S_0, …, S_N** and independent U,
  the randomized test has exact size α when α(N+1) is an integer; the
  non-randomized Ĝ_N = (1/N)Σ1(S_i ≥ x) (Eq. 2.10, p. 5) only guarantees
  size ≤ α (Dufour calls it valid).
- Berkowitz, Christoffersen & Pelletier (2011), Management Science, DOI
  10.1287/mnsc.1080.0964 (preliminary version, p. 16) print the rule with
  "≤", confirming the WP's "<" as a typo.
- Checkpoint A probe (p = 0.01, T = 250, `min_violations = 2`): 28.3 % of
  unconditioned null draws are "não aplicável" for LR_ind; the p-value of
  one observed case was 0.0080 with an unconditioned reference versus 0.0112
  with the reference conditioned on applicability — about 30 %
  anti-conservative. The observed statistic is only computed on the event
  A = {LR_ind applicable}; an unconditioned reference is not exchangeable
  with it, so Eq. (2.37) does not apply.
- Python `random` documentation: for a given seed, `Random.random()` keeps
  producing the same sequence across Python versions (the other methods,
  e.g. `randint`, `choice`, are not covered by that guarantee).

## Decision

```
[decision:E] 6.3-MC-TIES — tie handling in the Monte Carlo p-value of the discrete LR statistics
Escolha: Dufour randomized tie-breaking (Eq. 2.30, with ≤) · Alternativas: non-randomized Ĝ_N with ≥ (valid, size ≤ α); strict ">" (continuous-case rule); the WP's literal "<"
Base: C&P 2004 §4.3 p. 9 "we need a rule to break ties" [doi ok; verificado]; Dufour 2006 Eqs. (2.30)–(2.31), (2.33) p. 8, (2.37) p. 9 [doi ok; verificado]; BCP 2011 prelim. p. 16 [doi ok; verificado]
Sensibilidade pré-registrada: nenhuma (o MC já é sensibilidade de perfil) · Reversível: sim

[decision:E] 6.3-MC-COND — reference distribution when LR_ind is not defined on some null draws
Escolha: condition the LR_ind/LR_cc reference on the same applicability event A as the observed statistic (first N draws in A, redrawing up to a declared cap); LR_uc reference = first N draws (its applicability is structural) · Alternativas: unconditioned reference with inapplicable draws counted as LR_ind = 0; drop inapplicable draws and report fewer than N
Base: Dufour 2006 Eq. (2.37) "exchangeable" premise [doi ok; verificado]; C&P 2004 §5 p. 11 "we do not use Monte Carlo samples with zero or one VaR violations" [doi ok]; Checkpoint A probe (0.0080 vs 0.0112)
Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

1. `ChristoffersenTest.monte_carlo_p_values(sequence, *, min_violations,
   draws, seed)` — `draws` (N ≥ 1, `int`, not `bool`) and `seed` (`int`, not
   `bool`) are mandatory, with no default (values preregistered in 6.5; N
   should make α(N+1) an integer for the α used, e.g. N = 9 999 — recorded
   for 6.5 in the concept §8).
2. **Null draws:** iid Bernoulli(`violation_rate`) on the **observed**
   positions of the sequence; masked positions stay `None` (same gaps —
   ADR 6.3.0004). Each draw is scored with the same primitive
   (`christoffersen_statistics`) and the same `min_violations`.
3. **Applicability gates (the same for the observed and the drawn
   sequences):**
   - `p_uc` exists iff the observed LR_uc exists (≥ 1 observed consecutive
     pair). Every draw has the same observed positions, hence the same
     number of pairs, so LR_uc is defined on every draw; the reference is
     the first N draws.
   - `p_ind` and `p_cc` exist iff the observed `independence_status` is
     `APPLICABLE`. Their reference is the first N draws that are also
     `APPLICABLE` (event A: violations ≥ `min_violations` and a
     non-degenerate transition matrix — ADR 6.3.0001 item 7, empty row and
     empty column treated alike). Draws are continued until N such draws are
     found or the cap of `100·N` attempts is reached; at the cap, `p_ind` and
     `p_cc` are `None` with the reason `MC_CAP_REACHED`, and the number of
     attempts is always reported.
   - `p_uc` exists even when `p_ind` does not. When the observed LR_uc is
     not applicable, nothing is drawn: every p-value is `None`, both
     statuses are `NOT_APPLICABLE` and `attempts = 0`.
   - The result (`MonteCarloPValues`) is self-describing for persistence:
     it carries `min_violations` (which defines event A), `draws`, `seed`,
     `attempts`, the statuses and the sequence identity (horizon, kind,
     levels, tolerance, variant).
4. **Tie-breaking and p-value (pure kernel).**
   `mc_p_value(*, observed, simulated, uniforms, observed_uniform) -> float`
   computes G̃_N = 1 − (1/N)Σ1(S_i ≤ S_0) + (1/N)Σ1(S_i = S_0)·1(U_i ≥ U_0) and
   p̃ = (N·G̃_N + 1)/(N + 1). "=" and "≤" are **exact** float comparisons,
   with no tolerance: every statistic is computed by the same primitive, in
   the same operation order, from integer counts, so equal counts give
   identical floats.
   **Test envelope (acceptance criterion A8):** for LR_uc with small T and
   large N, p̃ ∈ [P(S > s₀) − ε, P(S ≥ s₀) + ε], with the exact binomial
   probabilities computed in the test and ε = 4·√(v/N) + 1/(N + 1), where
   v = max(P(S > s₀)(1 − P(S > s₀)), P(S ≥ s₀)(1 − P(S ≥ s₀))) (or v = 1/4).
5. **RNG consumption order (fixed, part of the contract):** one
   `random.Random(seed)` per call; only `random()` is used. First U_0; then,
   for each attempt, one `random()` per observed position in position order
   (violation ⇔ value < `violation_rate`), then one `random()` for that
   draw's U_i. The same U_i serves every statistic of that draw. A frozen
   regression value for a fixed (sequence, seed, N) guards the order.
6. **Exactness, stated precisely.** Under H0 at h = 1, conditionally on A,
   the observed and the conditioned draws are exchangeable, so p̃ has exact
   conditional size α when α(N+1) is an integer (Dufour Eq. (2.37)); for
   LR_uc the conditioning event is structural and the statement is
   unconditional.
7. **`horizon > 1` raises `ValueError`**: the (h−1)-dependence under H0 is a
   nuisance parameter the null does not fix (doc §7.4, §7.6).

## Alternatives considered

### Alternative A — Non-randomized Ĝ_N with ≥ (Dufour Eq. 2.10)

- **Pros:** no auxiliary uniforms; still a valid test.
- **Cons:** its p-value is never smaller than the randomized one (Dufour
  Eq. 2.33), so its size can fall below α for a discrete statistic
  (Eq. 2.37); not what C&P prescribe for binary sequences.
- **Why rejected:** the evidence names the randomized rule for binary
  sequences.

### Alternative B — Strict ">" (C&P's continuous-case formula)

- **Why rejected:** drops ties entirely; no validity guarantee for a
  discrete statistic.

### Alternative C — The WP's literal "<"

- **Why rejected:** counts ties twice (G̃ up to 2); the same authors print
  "≤" in 2011.

### Alternative D — Unconditioned reference (inapplicable draws as LR_ind = 0)

- **Why rejected:** not exchangeable with the observed statistic; the probe
  shows it anti-conservative by about 30 %.

### Alternative E — Drop inapplicable draws, report the p-value on fewer than N

- **Why rejected:** N becomes data-dependent and α(N+1) no longer an
  integer by design; redrawing to N keeps the preregistered N.

### Alternative F — Do nothing (asymptotic p-value only)

- **Why rejected:** the doc preregisters the MC p-value as the h+1
  sensitivity.

## Consequences

### Positive

- The sensitivity p-value is exact (conditionally on A for LR_ind/LR_cc)
  at h+1 and reproducible from (seed, N) across Python versions.

### Negative

- Rare-violation series can need many redraws; the cap makes the cost
  bounded and visible. The run time at the pilot scale (T ≈ 10³, N ≈ 10⁴)
  is measured in the technical phase, not assumed.

### Neutral / trade-offs accepted

- The p-value depends on the seed through the tie-breaking uniforms, by
  design (Dufour); the seed is preregistered.

## References

- Domain doc §7.4, §7.6, §10 convention 22.
- Christoffersen, P.; Pelletier, D. (2004), JFEc 2(1), 84–108, DOI
  10.1093/jjfinec/nbh004 — CIRANO WP 2003s-05 §4.3 p. 9, §5 p. 11.
- Dufour, J.-M. (2006), "Monte Carlo tests with nuisance parameters: A
  general approach to finite-sample inference and nonstandard asymptotics",
  J. Econometrics 133(2), 443–477, DOI 10.1016/j.jeconom.2005.06.007 —
  CIRANO WP 2005s-02 Eqs. (2.8) p. 4, (2.10) p. 5, (2.30)–(2.31) and (2.33)
  p. 8, (2.37) p. 9.
- Berkowitz, J.; Christoffersen, P.; Pelletier, D. (2011), "Evaluating
  Value-at-Risk Models with Desk-Level Data", Management Science 57(12),
  2213–2227, DOI 10.1287/mnsc.1080.0964 — preliminary version (2005) p. 16.
- Python standard library, `random` module documentation ("Notes on
  Reproducibility").
- Related ADRs: 6.3.0001, 6.3.0004.
