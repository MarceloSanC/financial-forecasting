---
title: ADR 6.2.0002 — The t_{T−1} p-value of the DM test is computed in the domain with a stdlib regularized incomplete beta (student_t.py), not by scipy behind a port nor by the normal approximation
description: Architecture Decision Record
when-use: Reference when asking where the Student-t CDF of the DM/HLN test lives, why the evaluation domain carries its own special function, how it is verified, why the normal approximation is not used, or why t and χ² live in separate modules
keywords: [adr, evaluation, student-t, incomplete-beta, p-value, diebold-mariano, hln, stdlib, domain-purity, dlmf, oracle, lentz]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.2.0002
decision: The one-sided DM p-value P(t_{T−1} ≤ S1*) is computed in `evaluation/domain/services/student_t.py` through the regularized incomplete beta with the same two branches as R's `pt` (for n > x², I_{x²/(n+x²)}(½, n/2) with x²/(n+x²) computed directly; otherwise I_{n/(n+x²)}(n/2, ½); equivalent through DLMF 8.17.4), evaluated by the DLMF 8.17.22 continued fraction with the modified Lentz method under an iteration cap (non-convergence raises); the module holds only the t distribution (Stage 6.3's χ² lives in its own module, reversing issue #114's "one distributions module" by orchestration decision), and it is verified against analytic values, the R `dm.test` fixtures and scipy through the statsmodels adapter.
context_stage: 6.2-paired-inference-dm-mcs-holm
bounded_context: evaluation
---

# ADR 6.2.0002 — Student-t p-value in the domain (stdlib)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` (revised after Checkpoint A round 1: exact `pt.c` branches, direct
complement argument, iteration cap, measured accuracy range, module split recorded as
a reversal).

## Context

HLN 1997 (Eq. (9), pp. 283–284) compare the modified statistic S1* with the Student
t with T − 1 degrees of freedom; the domain doc fixes it (§6.1, §6.3, convention
#14) and the R oracle does the same (`pt(STATISTIC, df = n − 1)` for
`alternative = "less"`, doc §11.3). The DM statistic lives in the domain, stdlib-only
(ADR 0.0.0020; ADR 0.0.0056; contract `evaluation-no-scoring-lib-leak` forbids
`scipy` in `evaluation.{application,domain}`). Python's stdlib has `math.erf` and
`math.lgamma` but no t CDF.

Accuracy evidence so far: issue #114 measured a stdlib Lentz continued fraction
against `scipy.stats.t` at a maximum relative error of 8.4e−12 (df 19–1999,
|t| ≤ 10); the Checkpoint A domain reviewer measured ≤ 2.1e−12 (df 59–2499,
|x| from 1e−9 to 31.6). Neither covers df 1–18 nor the far tails. The normal
approximation is anti-conservative (−1.2 % / −3.9 % / −10 % at p ≈ 0.05 / 0.01 /
0.001 with df = 249; −2 % to −4 % at the Holm threshold α/6).

Issue #114 ("Entendimento validado" §1(b)) proposed a single distributions module in
`evaluation/domain` shared by the t (6.2) and the χ² (6.3). The master session then
decided, to avoid a merge conflict between the two Stages running in parallel, that
each distribution lives in its own file (`student_t.py` here; `chi_square.py` in 6.3,
which uses closed forms for df 1 and 2, not an incomplete gamma).

## Decision

1. `evaluation/domain/services/student_t.py` exposes a pure function
   `student_t_cdf(x: float, df: float) -> float` (lower tail), stdlib-only.
2. **Same branches as the oracle.** R's `src/nmath/pt.c` computes, with
   `nx = 1 + x²/n`, `pbeta(x²/(n + x²), 0.5, n/2, upper tail)` when n > x² and
   `pbeta(1/nx, n/2, 0.5, lower tail)` otherwise, halves it, and takes the complement
   for x > 0. Both branches are the same quantity ½·I_{n/(n+x²)}(n/2, ½) = ½·[1 −
   I_{x²/(n+x²)}(½, n/2)] by DLMF 8.17.4; the implementation follows the branch
   split and computes the complementary argument x²/(n + x²) **directly** (never as
   1 − n/(n + x²), which cancels for small |x|).
3. **Special function:** I_z(a, b) by the continued fraction DLMF 8.17.22
   (coefficients 8.17.23), evaluated with the modified Lentz method, using the
   8.17.4 symmetry when z > (a + 1)/(a + b + 2) (where the DLMF says the direct
   expansion converges slowly); prefactor z^a(1 − z)^b/(a·B(a, b)) with
   `math.lgamma`. An **iteration cap** bounds the loop; not converging within it
   raises (`ArithmeticError`), never returns a partial value. Non-finite x or df < 1
   → `ValueError`.
4. **Verification (ADR 0.0.0021):** (i) analytic values (x = 0 → ½; df = 1 Cauchy
   ½ + arctan(x)/π; df = 2 closed form ½ + x/(2√(2 + x²))); (ii) the R `dm.test`
   p-values in the versioned fixtures (ADR 6.2.0006); (iii) the statsmodels adapter
   computes its DM p-value with `scipy.stats.t`, so the `InferenceBackend` contract
   suite compares the two t CDFs on every DM case (ADR 6.2.0003). The technical
   **measures** the accuracy over df 1–2500 and |x| up to the far tails before fixing
   the declared tolerance (absolute + relative).
5. **Module split, recorded as a reversal.** This file holds only the t distribution;
   it reverses issue #114 §1(b) by orchestration decision. When a **third**
   distribution is needed by the BC, the modules are unified — recorded as a
   `[finding]` candidate for that Stage.

## Decision record

```
[decision:C] 6.2-R1 — where the t_{T−1} p-value of the DM test is computed
Escolha: domain, stdlib incomplete beta (student_t.py) · Alternativas: scipy.stats.t behind the port; normal approximation · Degrau (C): 1 (ADR 0.0.0020/0.0.0056: DM statistic in the stdlib domain; doc §6.3: t_{T−1}) e 2 (same identity and branches as the oracle's pt)
Base: R src/nmath/pt.c "val = (n > x * x) ? pbeta (x * x / (n + x * x), 0.5, n / 2., /*lower_tail*/0, log_p) : pbeta (1. / nx, n / 2., 0.5, /*lower_tail*/1, log_p);" … "val /= 2." [verificado]; DLMF 8.17.4 "I_x(a,b)=1−I_{1−x}(b,a)", 8.17.22 continued fraction, "converges rapidly for x<(a+1)/(a+b+2)" [verificado]
Sensibilidade pré-registrada: nenhuma (the p-value is a function, not a convention) · Reversível: sim
```

## Alternatives considered

### Alternative A — scipy behind the port
- **Cons:** the domain cannot call an application port (LAYOUT §3): the p-value, hence
  the DM verdict, would be assembled in a use case — ADR 0.0.0020 Alternative B.
- **Why rejected:** splits one test across layers.

### Alternative B — Normal approximation Φ(S1*)
- **Why rejected:** contradicts HLN's t_{T−1} (doc §6.3) and the oracle;
  anti-conservative at the thresholds that matter (see Context).

### Alternative C — A shared `distributions` module for t and χ² (issue #114 §1(b))
- **Pros:** one place for special functions.
- **Cons:** 6.2 and 6.3 would create the same file in parallel (merge conflict); the
  χ² of 6.3 uses closed forms and shares nothing with the incomplete beta.
- **Why rejected:** orchestration constraint; unify at the third distribution.

### Alternative D — Do nothing (report the statistic without p-value)
- **Why rejected:** Holm needs p-values (doc §6.4).

## Consequences

### Positive
- The DM result is complete in the domain; the p-value follows the oracle's formula
  and branches.
- Two independent references for the t CDF (R `pt` via fixtures, scipy via adapter).

### Negative
- A hand-written special function to maintain (~40 lines), justified by the oracle
  tests.

### Neutral / trade-offs accepted
- Extreme tails where R switches to an asymptotic formula (x² > 1e100·n) are outside
  any realistic DM statistic and are not specially handled.

## References

- Harvey, Leybourne & Newbold (1997), IJF 13(2), Eq. (9), pp. 283–284.
- NIST DLMF §8.17, Eqs. 8.17.2, 8.17.4, 8.17.22–8.17.23, https://dlmf.nist.gov/8.17.
- R source `src/nmath/pt.c`; Didonato & Morris (1992), ACM TOMS 18(3), 360–373
  (`pbeta`, TOMS 708).
- Related ADRs: [0.0.0020](./0_0_0020-statistics-in-domain-over-value-objects.md),
  [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md),
  [0.0.0056](./0_0_0056-own-statistics-in-domain-r-oracle-as-fixtures.md),
  [6.2.0003](./6_2_0003-dm-holm-of-record-statsmodels-oracle-no-dm-wrapper.md),
  [6.2.0006](./6_2_0006-r-oracle-fixtures-provenance-and-scope.md).
- Domain doc §6.1, §6.3, §11.3; issue [#114](https://github.com/MarceloSanC/financial-forecasting/issues/114) (fork R1).
