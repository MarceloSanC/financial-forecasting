---
title: ADR 0.0.0007 — H3 as heterogeneity of family contribution between h+1 and h+7, read by agreement of grouped permutation importance and LOCO ablation; VSN descriptive
description: Architecture Decision Record
when-use: Reference when questioning how H3 is worded and read, why the VSN does not vote on H3, why the ablation retrains (LOCO) in its own cohort, what "heterogeneous" and "agreement" mean operationally, or why H3's conclusion is descriptive and separate from the H1→H2 verdict
keywords: [adr, h3, feature-attribution, feature-families, vsn, permutation-importance, grouped-importance, loco, ablation, block-bootstrap, per-horizon, descriptive, inference, step-7]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 0.0.0007
decision: H3 holds when, for at least one feature family, the change of its normalized share between h+1 and h+7 has the same sign under grouped permutation importance and under LOCO ablation with retraining, with a paired block-bootstrap interval excluding zero in both; VSN weights are reported as horizon-invariant description only; the ablation is LOCO with 10 seeds in its own frozen, hashed cohort that also retrains the full reference model; the reading is a preregistered mechanical rule yielding a descriptive conclusion separate from the H1→H2 verdict.
context_stage: 0.0-global
bounded_context: inference
---

# ADR 0.0.0007 — H3: family contribution across horizons

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — ratified on 2026-10-06 by delegation of the human (Marcelo),
together with the inference domain doc (issue #150); the Step 7 gate is
closed. The two P forks — the role of the VSN in H3 (P-H3-VSN) and the
ablation design (P-ABLACAO) — were decided by the human on 2026-10-06.

## Context

Overview §4 stated H3 as "heterogeneous between horizons, detectable
consistently in ≥ 2 of 3 methods (VSN, permutation, ablation)", and overview
§11 promised this ADR. No document defined "heterogeneous", "consistent" or
the ablation, and the gate's research found a structural problem:

- **The VSN has no horizon axis here.** TFT variable selection weights are a
  softmax over variables per time step (Lim et al. 2021, §4.2 Eq. (6)). All 55
  registry features are observed inputs (encoder only); the decoder VSN sees
  only known calendar inputs; one multi-horizon decoder serves h+1 and h+7
  (ADR 5.4.0002). So the encoder VSN weights are identical for both horizons by
  construction (pytorch-forecasting 1.8.0 applies the encoder VSN only to
  encoder positions; verified by a fresh-context verifier). The VSN cannot vote
  on heterogeneity between horizons; "≥ 2 of 3" would promise a triangulation
  that does not exist.
- **Ablation needs models that are not in the confirmatory cohort.** Dropping
  a family and retraining produces models absent from the frozen cohort (ADR
  5.5.0001).
- **Only h+1 and h+7 are evaluated**, so "heterogeneous" is a two-point
  comparison and needs an operational definition with uncertainty under serial
  dependence.

## Decision

1. **Wording (P, human, 2026-10-06).** H3: the relative contribution of the
   families (price, technical, sentiment, fundamental) is heterogeneous between
   h+1 and h+7 — for at least one family, the change of its share between the
   horizons has the same sign under permutation importance and under family
   ablation (LOCO with retraining), with a paired block-bootstrap interval
   excluding zero in both. VSN weights are reported as a general,
   horizon-invariant description of how much the model uses each family. No
   causal claim.
2. **Permutation (E).** Per family, permute across test samples the whole
   encoder window of all the family's features jointly (grouped importance;
   Fisher, Rudin & Dominici 2019 §2); the model is fixed. Grouped rather than
   summed individual importances because, "in general, the grouped variable
   importance is not comparable with the sum of the individual importances" —
   the exception being an additive f with independent variables in the group
   (Gregorutti, Michel & Saint-Pierre 2015, arXiv:1411.4170 §2.1; published
   version CSDA 90). Within-time shuffling is rejected (Hooker, Mentch & Zhou
   2021).
3. **Measure (C).** Per horizon, the difference in grid-average pinball,
   L_perm − L_orig, averaged over K_p permutations; additive per observation, so
   the d_t series admits the same block bootstrap as the DM differential.
   Horizons are compared through the normalized share s_f(h) = I_f(h) / Σ_g
   I_g(h) (Gu, Kelly & Xiu 2020 §1.9).
4. **Ablation (P, human, 2026-10-06).** LOCO with retraining (Lei et al. 2018
   §6; Hooker et al. 2021 §5; Covert, Lundberg & Lee 2021 §8.2): 4 families ×
   6 folds × **10 seeds**, plus the **full reference model retrained in the
   same environment** — the "N+1" = 5 configurations of the roadmap. They form
   an **ablation cohort of their own, frozen and hashed**, separate from the
   confirmatory one; each configuration uses the candidate's frozen training
   procedure. Device and torch build are a Stage 7.3 decision and enter the
   hash. Ablation share uses L_{−f} − L_full, with the same bootstrap.
5. **Uncertainty (C, rung 1: coherence with the MCS of ADR 0.0.0010).** Stationary block bootstrap (Politis & Romano 1994;
   block per Politis & White 2004, the MCS machinery of evaluation §6.5),
   paired: the same resampled indices for h+1, h+7 and all families, with a
   **single block length** for the joint h+1/h+7 resampling, floored at the
   largest horizon (7) — coherent with the MCS block rule of ADR 0.0.0010
   (block = max(h, ⌈max b̂_sb⌉), the floor covering the MA(h−1) dependence;
   r0 `block_rule = "max_h_ceil_max_bsb"`), with b̂ the maximum Politis–White
   estimate over the series involved; numbers go to the preregistration.
   Seeds enter as pointwise means; seed dispersion goes to the profile.
   Molnar et al. (2023) compute the Monte Carlo variance of the PFI estimators
   across the n2 test instances and justify the model-PFI t-interval by
   independent samples; model variance requires refits (§7), and for
   learner-PFI they correct the shared-data case (Nadeau–Bengio). Our test
   instances are serially dependent, so the block bootstrap over d_t is a
   transposition, declared as such — no primary source gives a
   permutation-importance interval under serial dependence, which is why
   this item is a convention closed by rung 1, not evidence.
   **Pairing key between horizons (open, fixed in Stage 7.3's
   preregistration).** Evaluation aligns per horizon by `target_timestamp`
   (evaluation §2.1, §6.7): the same t at h+1 and h+7 comes from different
   decisions (t−1 vs t−7), and T differs (1511 vs 1505 in the cohort; concept
   5.5 D6). Recommended convention (no primary source): pair by **decision
   point**, restricted to the intersection — coherent with the VSN argument and
   with attribution acting on the same input.
6. **Reading rule (C).** Heterogeneous (per method): Δ_f = s_f(h+7) − s_f(h+1)
   has an interval excluding 0 for ≥ 1 family (no primary source — project
   convention). H3 sustained: both methods agree on the sign of Δ_f and both
   intervals exclude 0 for the same family (sign agreement — one of the six
   disagreement metrics *proposed* by Krishna et al. 2024 §3.2, not an
   established general practice). The VSN is outside the rule.
7. **Features without family (C).** Calendar inputs, past target and relative
   time index are neither permuted nor ablated; shares are computed over the 4
   families only; cross-family interactions follow the registry label.
   **Premise, verifiable before Stage 7.3:** no family feature is `known`
   (the TFT use case automatically routes any `known` registry spec to the
   decoder). If that changes, the decoder VSN gains a horizon axis and
   P-H3-VSN must be reopened.
8. **Language (C).** Strictly descriptive; the "mechanical H3 verdict" of the
   roadmap 8.1 is this preregistered reading rule producing a descriptive
   conclusion, separate from the H1→H2 verdict, never altering it.
9. **Preregistration.** Partition, permutation scheme, K_p, measure,
   bootstrap block/B/seed, the reading rule and the ablation cohort hash are
   preregistered with the 6.5 machinery before any metric on the real cohort
   (ADR 6.5.0008 item 6). Open items for Stage 7.3's preregistration (single
   list in the domain doc §5.7): interval level; multiplicity for "≥ 1 of 4
   families"; negative importances / Σ I_g ≈ 0; pairing key between horizons;
   block length of the joint bootstrap.

**Pending outside this ADR:** ADR 0.0.0016 puts volatility features in the
price family while the registry labels six of them technical; this changes the
H3 partition and must be resolved (separate issue [#151](https://github.com/MarceloSanC/financial-forecasting/issues/151)) before H3 is
preregistered.

## Alternatives considered

### Alternative A — Replace the VSN by a third horizon-resolved method (integrated gradients per output)
- **Pros:** keeps a 3-method triangulation.
- **Cons:** a third method with its own baseline/path choices; more forks to
  preregister; gradient methods on the same fixed model are not independent of
  permutation.
- **Why rejected:** decided by the human (P); two methods with different
  estimands are a cleaner test than three correlated ones.

### Alternative B — Keep "≥ 2 of 3" with the VSN
- **Cons:** the VSN gives the same weights for both horizons; it can only ever
  vote "not heterogeneous", so the rule degenerates to "permutation and
  ablation agree" while claiming three methods.
- **Why rejected:** promises a triangulation that does not exist.

### Alternative C — Ablation without retraining (zero/mean substitution)
- **Pros:** no extra training; precedent in Gu, Kelly & Xiu (2020 §1.9).
- **Cons:** replacing by a fixed value "can be interpreted as an additional
  assumption of model linearity" (Covert et al. 2021 §8.2), and it evaluates
  the same fixed model off-support as permutation does — the two methods would
  no longer be independent.
- **Why rejected:** decided by the human (P).

### Alternative D — Ranking change as "heterogeneous"
- **Cons:** 4 families give 24 orders; coarse and without natural uncertainty.
- **Why rejected:** the share difference with a bootstrap interval is finer.

### Alternative E — Ratio instead of difference (Breiman 2001; Fisher MR)
- **Cons:** not additive per observation; no direct block-bootstrap series.
- **Why rejected:** the difference reuses the evaluation machinery.

## Consequences

### Positive
- H3 becomes falsifiable with two horizon-resolved methods of different
  estimands (model reliance vs information available to the learner).
- The reading is mechanical and preregistered; reconstructible from persisted
  predictions without retraining (the ablation cohort is trained once).

### Negative
- Ablation costs 5 configurations × 6 folds × 10 seeds = 300 TFT trainings
  outside the confirmatory cohort. Anchored on the measured cost (ADR 0.0.0010
  item 5; D8 of Stage 5.5): the real confirmatory cohort of 10 seeds × 6 folds
  took ~19 h on CPU (~1.5–2.9 h per seed; technical 5.5, Task 35), so the
  ablation is ≈ 95 h on CPU. The human decided 10 seeds, run on GPU under
  Linux (RX 7700 XT / ROCm), with a 1 seed × 1 fold pilot first; the number of
  seeds may be revisited in Stage 7.3 in the light of the pilot.
- Stage 7.3 needs new modeling code: training the TFT on a subset of families
  (today the use case takes the whole registry), run identity /
  `feature_set_hash` per configuration, an ablation cohort spec with 5
  configurations (the cohort runner refuses a `feature_set_hash` other than
  the registry's) and a device other than `cpu` (the composition root only
  accepts `cpu`).
- Five open items (interval level; multiplicity; negative importances;
  pairing key; joint block length) must be fixed in Stage 7.3's
  preregistration.
- The family partition depends on resolving the volatility finding.

### Neutral / trade-offs accepted
- The VSN is still reported (percentiles 10/50/90 per variable, sum per
  family), labelled horizon-invariant; attention/gating weights are not causal
  explanations (Jain & Wallace 2019; Wiegreffe & Pinter 2019).

## References

- Lim, B.; Arık, S. Ö.; Loeff, N.; Pfister, T. (2021). "Temporal Fusion Transformers for interpretable multi-horizon time series forecasting". *International Journal of Forecasting*, 37(4), 1748–1764. DOI: 10.1016/j.ijforecast.2021.03.012. (arXiv:1912.09363v3: §4.2 Eqs. (6), (8); §7.1 Eq. (27).)
- Fisher, A.; Rudin, C.; Dominici, F. (2019). *JMLR*, 20(177). arXiv:1801.01489. (§2; §3 Eq. (3.1).)
- Gregorutti, B.; Michel, B.; Saint-Pierre, P. (2015). *Computational Statistics & Data Analysis*, 90, 15–35. DOI: 10.1016/j.csda.2015.04.002. (arXiv:1411.4170 §2.1.)
- Hooker, G.; Mentch, L.; Zhou, S. (2021). *Statistics and Computing*, 31, 82. DOI: 10.1007/s11222-021-10057-z. (Abstract; §5.)
- Lei, J.; G'Sell, M.; Rinaldo, A.; Tibshirani, R. J.; Wasserman, L. (2018). *JASA*, 113(523), 1094–1111. DOI: 10.1080/01621459.2017.1307116. (§6 LOCO.)
- Covert, I.; Lundberg, S.; Lee, S.-I. (2021). *JMLR*, 22(209). arXiv:2011.14878. (§8.2.)
- Gu, S.; Kelly, B.; Xiu, D. (2020). *Review of Financial Studies*, 33(5), 2223–2273. DOI: 10.1093/rfs/hhaa009. (§1.9.)
- Molnar, C. et al. (2023). DOI: 10.1007/978-3-031-44064-9_24. (§5, §7.)
- Politis, D. N.; Romano, J. P. (1994). DOI: 10.1080/01621459.1994.10476870. Politis, D. N.; White, H. (2004). DOI: 10.1081/ETC-120028836.
- Krishna, S. et al. (2024). *TMLR*. arXiv:2202.01602. (§3.2.)
- Jain, S.; Wallace, B. C. (2019). DOI: 10.18653/v1/N19-1357. Wiegreffe, S.; Pinter, Y. (2019). DOI: 10.18653/v1/D19-1002.
- Full citations and locators: [inference domain doc §11](../domain/inference/conformal-benchmark-and-feature-attribution.md); decision records in its §10.1.
- [ADR 0.0.0002](./0_0_0002-probabilistic-calibration-framing.md),
  [ADR 0.0.0016](./0_0_0016-four-feature-families.md),
  [ADR 0.0.0010](./0_0_0010-paired-inference-dm-holm-mcs.md),
  [ADR 5.4.0002](./5_4_0002-single-multi-horizon-decoder.md),
  [ADR 5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md),
  [ADR 6.5.0008](./6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md),
  [ADR 0.0.0057](./0_0_0057-inference-domain-doc-scope-and-boundary.md).
- Originating issue: [#150](https://github.com/MarceloSanC/financial-forecasting/issues/150).
