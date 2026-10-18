---
title: ADR 7.3.0005 — H3 preregistration as one blind amendment r3 of r2 with an [h3] block, anchored after the ablation freeze, and the values it freezes
description: Architecture Decision Record
when-use: Reference when writing, filling or anchoring revision r3 of aapl_confirmatory; when asking which interval, level, block, B, seed, K_p, permutation generator, pairing key, seed aggregation or non-positive-total rule H3 uses; or why the volatility subgroup profile is not computed
keywords: [adr, preregistration, amendment, r3, blinded, anchor, h3, bonferroni, basic-interval, block-bootstrap, block-rule, permutation-plan, common-random-numbers, k_p, pairing, decision-point, vsn, volatility]
status: accepted
created_at: 2026-10-18
updated_at: 2026-10-18
adr_id: 7.3.0005
decision: H3 is frozen by a single blinded revision r3 of aapl_confirmatory (r2 verbatim + amendment fields + an optional [h3] block parsed by an H3Parameters VO, forbidden in r0), written as a draft in the Stage folder on Windows and filled with the ablation cohort id, hash and seeds, committed and anchored on Linux right after the ablation freeze and before any H3 metric; it freezes the registry partition by feature lists + feature_set_hash, whole-window permutation with K_p = 10 permutations per fold shared by all seeds and families (Fisher–Yates over Random(int).random()), permutation_seed = 130, the grid-average pinball difference, pairing by decision point on the intersection of h+1 and h+7, pointwise seed means, one stationary block bootstrap for both methods with block = max(7, ⌈max b̂⌉) over the 16 series, B = 1000, seed = 129, the basic interval with linear percentiles at level 1 − 0.05/4, the undefined rule for non-positive totals, the sign-agreement reading and the VSN summary; the volatility subgroup profile is out.
context_stage: 7.3-explainability
bounded_context: inference
---

# ADR 7.3.0005 — H3 preregistration details (blind amendment r3)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.3 concept (issue #186), 2026-10-18. Closes item 8 of the
research findings and the five open points of inference domain doc §5.7; the
four forks triaged in the issue (r3 single, Bonferroni, volatility out, block
as a rule) are recorded here with their rung. Every choice is made before any
H3 number exists (8.1 has not run; no permuted prediction or ablation model has
been scored), so the triage class is C, not P (skill `evidence-resolution` §1).

## Context

- Doc §7 / ADR 0.0.0007 item 9: partition, permutation scheme, K_p, measure,
  bootstrap block/B/seed, the reading rule and the ablation cohort hash are
  preregistered with the 6.5 machinery before any metric on the real cohort;
  the form is the Stage's.
- ADR 7.2.0001 item 5: 8.1 judges by the latest anchored revision of the
  chain; r2 adds `[conformal]`; "every later amendment (H3 in 7.3) must copy r2
  verbatim". r2 exists only once Stage 7.2 is merged.
- The ablation cohort hash exists only after its freeze on Linux (seeds are a
  human decision after the pilot; ADR 7.3.0003).
- The block b̂ needs d_t, hence the realized series — computing it before the
  anchor would break blinding (doc §7; precedent `block_rule` of r0/r1).

## Decision

### Form

`[decision:C] 7.3-PREREG — form of the H3 preregistration`
`Escolha: one revision r3 (r2 + [h3]), anchored on Linux after the ablation freeze · Alternativas: r3 now (Windows, without the ablation hash) + r4 with the hash; own plan file · Degrau: 5 (one anchor, one amendment; the hash is part of what r3 freezes — triaged in issue #186)`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim até a âncora`

1. **File.** `config/preregistration/aapl_confirmatory-r3.toml` = r2 verbatim
   except `revision = 3`, the amendment fields (`amends` = r2's
   `preregistration_ref`, `justification`, `blind_status = "blinded"`) and an
   optional block `[h3]`, parsed by a new VO `H3Parameters`
   (`evaluation/domain/value_objects/h3_parameters.py`, one catalog identifier
   per rule, accepted only if the code implements it — ADR 6.5.0004 item 2
   pattern). `[h3]` is forbidden in r0 and optional for r ≥ 1. Nothing that
   judges H1 or H2 changes; r0–r2 hashes are unchanged.
2. **Draft on Windows.** `docs/stages/7.3-explainability/aapl_confirmatory-r3.draft.toml`
   holds the whole r3 with three sentinel values in `[h3.ablation]`
   (`cohort_id`, `cohort_hash`, `seeds`); a unit test fills them with synthetic
   values and parses the result through `Preregistration.from_mapping`, and
   checks "draft = r2 + amendment + [h3]". No file named
   `aapl_confirmatory-r3.toml` exists before Linux. A second test (run again
   in L7) compares the filled r3 with the draft and accepts differences **only**
   in `[h3.ablation]` (`cohort_id`, `cohort_hash`, `seeds`); any other
   change must be a `[decision]` in technical §7 that **first updates the
   draft** (so the comparison stays "only `[h3.ablation]`"), committed before
   L5.
3. **Linux (handoff).** After `ablation-freeze`: fill the three values from the
   frozen spec, copy to `config/preregistration/aapl_confirmatory-r3.toml`,
   commit, anchor (after the ablation cohort's own anchor, ADR 7.3.0006 L4; tag `preregistration/<r3 ref>`, comment on issue #186 with
   ref, full hash, tag, commit, both cohort ids and hashes, `.anchor.toml` with
   the server `anchored_at`), mirror section in
   `docs/preregistration/aapl_confirmatory.md`. The anchor precedes any H3
   metric (the first is 8.1's refresh).

### Values frozen by `[h3]`

```
[decision:C] H3-PARTITION — what the family partition is
Escolha: the registry partition (C8), frozen as family → feature list + feature_set_hash 7df0e1b4… + a literal `[h3.partition].partition_hash` (the shared `FamilyPartitionHash` computed when the draft is written; a consistency test recomputes it); the refresh compares the rows' column with that literal, without a Hasher; calendar, past target and relative time index outside (C6) · Alternativas: by family name only; a Hasher injected into RefreshGold to recompute the hash (rejected: the Hasher left RefreshGold in #128 — the grid fingerprint comes computed by its owner; a literal checked by a test keeps that) · Degrau: 1 (doc §5.2 (i); ADR 0.0.0007 errata; #128)
Base: doc §5.2; registry measured 2026-10-18 (17/17/11/10 features)
Sensibilidade pré-registrada: nenhuma · Reversível: não sem nova revisão do cohort

[decision:C] H3-VOL — descriptive permutation profile of the volatility subgroup
Escolha: out of scope · Alternativas: a fifth permuted group, outside the verdict (doc §5.2 (iii)) · Degrau: 5 (triaged in issue #186)
Base: the reading caveat of doc §5.2 (ii) stays in the report text; no table
Sensibilidade pré-registrada: nenhuma · Reversível: sim (a later amendment before 8.1)

[decision:C] H3-KP — number of permutations
Escolha: K_p = 10 per fold · Alternativas: 1 (Breiman 2001), 5 (sklearn permutation_importance default n_repeats), 30 · Degrau: 5
Base: [SEM-FONTE-PRIMÁRIA] for a number; K_p only reduces Monte Carlo error (doc §5.4, §5.6 item 1), and with one donor per decision the permutation noise enters d_t and is resampled by the block bootstrap over t; cost reference: ~20 s per run to re-predict the test *including the silver read* (technical 7.1 §7, E5) — the per-pass time is not measured, so 60 × (2 + 40) × 20 s ≈ 14 h is a ceiling, not a measurement; the dispersion across k is reported (gold_h3_importance)
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a âncora

[decision:C] H3-FOLD — the set the permutation draws from
Escolha: the test decisions of the run's own fold (each fold has its own model and its own per-column scalers fitted on that fold's training frame) · Alternativas: the whole test set across folds; the batch (captum FeaturePermutation) · Degrau: 1 (doc §5.4 C1 "entre as amostras do teste" of the model being explained; ADR 5.4.0001 — the fitted dataset state is per fold; swapping normalized blocks is a raw swap only under one scaler, ADR 7.3.0002 Context)
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a primeira gravação real

[decision:C] H3-PI — how the permutations are generated and shared
Escolha: π_{fold,k} depends only on (permutation_seed, fold, k) — the same for every seed and every family (common random numbers); algorithm `fisher_yates_random_random_v1`: one random.Random(permutation_seed * 1000 + fold_index) per fold, the K_p permutations drawn in sequence j = 0..K_p − 1 and stored with permutation_index = j + 1, each a Fisher–Yates of range(n) with i from n − 1 down to 1, r = floor(random() · (i + 1)), swap i and r; permutation_seed = 130; uniform permutations (fixed points allowed) · Alternativas: π per (seed, family); random.shuffle; derangements · Degrau: 1 (seeds are replicas of the same aligned point, doc §2.3 / ADR 0.0.0010 item 5 — the treatment applied to the replicas must be identical, so seed dispersion stays pure model variance; same pairing logic as the bootstrap of doc §5.6) e 5
Base: Python 3.12 Doc/library/random.rst "Notes on Reproducibility" — "The generator's random() method will continue to produce the same sequence when the compatible seeder is given the same seed" (other algorithms "are subject to change across Python versions")
Verificado: sustenta (evidence-verifier, 2026-10-18)
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a primeira gravação real

[decision:C] H3-PAIR — pairing key between horizons
Escolha: decision point, restricted to the decisions with both h+1 and h+7 (T measured by the refresh; of the order of 1505 — that number is the h+7 target-aligned T of concept 5.5 D6, not this intersection) · Alternativas: target_timestamp · Degrau: 1 (doc §5.7 item 4 recommendation; ADR 0.0.0007 item 5)
Base: [SEM-FONTE-PRIMÁRIA] — permuting a decision's encoder window acts on h+1 and h+7 together
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a âncora

[decision:C] H3-SEEDS — seed aggregation
Escolha: d_{f,t}(h) = mean over seeds of mean over k of (L^{perm f,k}_{s,t} − L^{id}_{s,t}); LOCO: mean_s L^{−f}_{s,t} − mean_s L^{full}_{s,t}; per-seed I_f in the profile · Alternativas: pooling seeds as observations · Degrau: 1 (doc §2.3, §5.6 item 3)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] H3-BLOCK — block of the joint bootstrap
Escolha: rule, not number: block = block_length_rule(horizon = 7, max_estimate = max of the Politis–White b̂ of the 16 series d_{f,t}(h), 2 methods × 4 families × 2 horizons); one index draw for both methods · Alternativas: a number fixed now; a block per method · Degrau: 1 (ADR 0.0.0010 / r0 block_rule; doc §5.6; triaged in issue #186: b̂ needs the realized series)
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a âncora

[decision:C] H3-B — replicas and seed
Escolha: stationary scheme, B = 1000, bootstrap seed = 129 · Alternativas: B = 2000/5000 · Degrau: 1 (r0 [mcs] reps = 1000; seeds 127/128 already used by MCS and Monte Carlo)
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a âncora · Nota: at level 0.9875 each tail has ~6 replicas; accepted as the project's bootstrap size

[decision:C] H3-CI — interval type
Escolha: basic interval [2·Δ̂ − q_{1−a/2}, 2·Δ̂ − q_{a/2}] of the replicas, with q by linear interpolation (numpy/arch default, type 7) · Alternativas: percentile, BCa, studentized · Degrau: 2 (default of the reference implementation of the project's bootstrap backend: arch 8.0.0 IIDBootstrap.conf_int method="basic"; oracle test against it)
Base: arch v8.0.0 arch/bootstrap/base.py L579–581 `method ... = "basic"`; L789 `np.percentile(values[:, i], ...)`; L793–796 `lower = 2.0 * base - upper; upper = 2.0 * base - lower_copy`
Verificado: sustenta (evidence-verifier, 2026-10-18)
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a âncora

[decision:C] H3-LEVEL — level and multiplicity for "≥ 1 of 4 families"
Escolha: simultaneous Bonferroni over the 4 families: each Δ_f interval at 1 − 0.05/4 = 0.9875, in each method; no further adjustment for requiring both methods (the conjunction is more restrictive than either) · Alternativas: 0.95 unadjusted; Holm · Degrau: 4 (the most conservative for the claim; triaged in issue #186)
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a âncora

[decision:C] H3-NEG — negative importances and Σ_g I_g ≈ 0
Escolha (id `undefined_if_point_total_nonpositive_replicas_as_infinite_v1`): importances keep their sign (no clipping); a method is undefined (status undefined, H3 not sustained by it) only when Σ_g I_g(h) ≤ 0 at the point estimate, for h = 1 or 7; a bootstrap replica with Σ*_g I*_g(h) ≤ 0 at h = 1 or h = 7 (Δ* undefined) stays among the B replicas and, in replica space, enters as +∞ when computing q_{1−a/2} and as −∞ when computing q_{a/2}; since lower = 2Δ̂ − q_{1−a/2} and upper = 2Δ̂ − q_{a/2}, both bounds widen (B unchanged); infinite bounds are stored in gold_h3_shares as null + flag (lower_infinite/upper_infinite), the 7.2 pattern; many such replicas make a quantile infinite, and the interval then cannot exclude 0 — the bias goes only towards not excluding 0; their count per horizon is persisted in gold_h3_shares and gold_h3_reading · Alternativas: undefined if any replica has Σ* ≤ 0 (rejected: depends on B — P ≈ 0.74 of undefined at z = 3 with B = 1000, Checkpoint A round 1, A-D2); exclusion of the replicas when their fraction is ≤ a/2 (rejected in round 2: the exclusion is taken over the union of the horizons, up to a = 0.0125 of mass against ~6 replicas per tail, which shrinks the tails and biases towards excluding 0 — anti-conservative); clip at 0; normalize by Σ|I_g| · Degrau: 4 (the most conservative for the claim; no share is reported where it is not defined at the point)
Base: [SEM-FONTE-PRIMÁRIA] (lacuna listed in issue #186)
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a âncora

[decision:C] H3-READ — mechanical reading
Escolha: side of a family = sign of Δ̂_f; the family excludes 0 when its interval excludes 0 strictly on that side (Δ̂ > 0 and lower > 0, or Δ̂ < 0 and upper < 0); an interval excluding 0 on the side opposite to Δ̂ (possible for the basic interval under skewed replicas), or with a bound exactly 0, makes that family undefined with a reason; per method, heterogeneous ⇔ some ok family excludes 0; H3 sustained ⇔ some family excludes 0 in both methods with the same sign of Δ̂; with an undefined bootstrap (invalid b̂, ArithmeticError, H3-NEG) the method is undefined, heterogeneous = None, and the reading is sustained = False with status undefined and the reason; label "descritiva (sem claim causal)" · Alternativas: side of the interval instead of the sign of Δ̂ (first draft; contradicted the ratified wording — Checkpoint A, A-C2/A-D10) · Degrau: 1 (overview §4; ADR 0.0.0007 item 6; doc §5.7 C5 "mesmo sinal de Δ_f e IC excluindo 0")
Sensibilidade pré-registrada: nenhuma · Reversível: sim até a âncora

[decision:C] H3-VSN — VSN summary
Escolha: per decision, the per-sample encoder weights of interpret_output(reduction="none") (mean over encoder steps), averaged over seeds pointwise; per family the sum of its variables per decision; p10/p50/p90 over the test decisions (type 7); non-family variables reported apart; label "horizonte-invariante; descreve quanto o modelo usa cada família" · Alternativas: pool (seed, decision); sum of variable percentiles · Degrau: 2 (the library's own per-sample reduction) e 1 (doc §2.3, §5.3)
Base: pytorch-forecasting 1.8.0 _tft.py L811–848 (verified 2026-10-18); Lim et al. 2021 §7.1 (percentiles over the test set)
Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

Catalog identifiers (final names in the technical) cover: partition rule,
permutation scheme, permutation algorithm, measure, pairing, seed aggregation,
bootstrap scheme, block rule, interval, multiplicity, non-positive rule,
reading rule and VSN summary; numbers: `k_p = 10`, `permutation_seed = 130`,
`reps = 1000`, `seed = 129`, `family_alpha = 0.05`; references: the ablation
`cohort_id`, `cohort_hash`, `seeds` and the model versions of the five
configurations (ADR 7.3.0003).

## Alternatives considered

### Alternative A — r3 now on Windows + r4 with the ablation hash
- **Pros:** the analysis rules are anchored earlier.
- **Cons:** two anchors and two amendments for one hypothesis; r3 would freeze
  an H3 without the cohort that half of the reading depends on.
- **Why rejected:** triaged in issue #186 (rung 5).

### Alternative B — Own plan file (`aapl_h3-r0.toml`)
- **Why rejected:** ADR 7.2.0001 Alt. A — one chain describes the whole
  protocol; 8.1 loads one plan.

### Alternative C — Freeze the values in this ADR only
- **Why rejected:** doc §7 — the ADR records the decision; the preregistration
  is the hashed artifact.

## Consequences

### Positive
- One anchored chain r0 → r1 → r2 → r3; H3 rules hashed before any H3 number.
- Every open point of doc §5.7 is closed with its rung.

### Negative
- Stage 7.3's execution starts only after 7.2 is merged (r3 copies r2) and its
  last act happens on Linux.
- The `Preregistration` VO gains one more optional block and cross-rules
  (partition = the 4 families of ADR 0.0.0016, disjoint; ablation model
  versions distinct from the candidate and the comparators).

### Neutral / trade-offs accepted
- No volatility subgroup table; the caveat stays in the report text.

## References

- Related ADRs: [0.0.0007](./0_0_0007-h3-family-contribution-across-horizons.md),
  [0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md),
  [6.2.0004](./6_2_0004-mcs-procedure-in-domain-over-backend-bootstrap-indices.md),
  [6.2.0005](./6_2_0005-mcs-block-length-ceiling-integer.md),
  [6.5.0001](./6_5_0001-preregistration-canonical-toml-hashed-value-object.md),
  [6.5.0002](./6_5_0002-amendment-as-new-revision-file.md),
  [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md),
  [6.5.0004](./6_5_0004-judging-values-in-preregistration-cohort-by-reference.md),
  7.2.0001 (Stage 7.2),
  [7.3.0001](./7_3_0001-attribution-statistics-in-evaluation-gold-via-refresh-gold.md),
  [7.3.0003](./7_3_0003-ablation-cohort-spec-by-reference-identity-per-configuration.md).
- arch 8.0.0 `arch/bootstrap/base.py` (tag `v8.0.0`); Python 3.12
  `Doc/library/random.rst`; pytorch-forecasting 1.8.0 `_tft.py`.
- Breiman, L. (2001). *Machine Learning*, 45(1), 5–32. DOI: 10.1023/A:1010933404324.
- Lim, B. et al. (2021). *International Journal of Forecasting*, 37(4). DOI: 10.1016/j.ijforecast.2021.03.012.
- Inference domain doc §2.3, §5.2–§5.7, §7.
- Issue: [#186](https://github.com/MarceloSanC/financial-forecasting/issues/186).
