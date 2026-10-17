---
title: ADR 7.2.0001 — CQR preregistration details as a blind amendment r2 with a [conformal] block, anchored on the Stage issue
description: Architecture Decision Record
when-use: Reference when writing or reading revision r2 of aapl_confirmatory, when asking which revision 8.1 judges by, why the conformal benchmark is not a scorecard profile, or which conformal rules are frozen and how
keywords: [adr, preregistration, amendment, r2, blinded, anchor, conformal, cqr, nexcp, rule-catalog, scorecard, 8.1]
status: accepted
created_at: 2026-10-17
updated_at: 2026-10-17
adr_id: 7.2.0001
decision: The CQR details listed in inference domain doc §4.13 are frozen by a blinded revision r2 of aapl_confirmatory (r1 + amendment fields + an optional [conformal] block of catalog identifiers parsed by a new ConformalParameters VO, forbidden in r0), not in profiles.declared, anchored by tag + comment on issue #158 + .anchor.toml as the Stage's last Task, before any metric on the real cohort; 8.1 judges by the most recent anchored revision of the chain.
context_stage: 7.2-conformal-cqr
bounded_context: inference
---

# ADR 7.2.0001 — CQR preregistration details (blind amendment r2)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.2 concept (issue #158), 2026-10-17. Named by ADR
0.0.0008 ("Stage 7.2 keeps the implementation and preregistration details
(`7_2_0001`)") and by the roadmap.

## Context

ADR 0.0.0008 item 12 and inference domain doc §4.13/§7 require the CQR
details (variant of record, NexCP ρ, pairs and primary pair, asymmetry, seed
treatment, per-horizon rule, comparison metrics, no rearrangement of the
conformal output) to be preregistered with the 6.5 machinery before any metric
on the real cohort; doc §7 leaves the *form* to Stage 7.2. ADR 6.5.0008 item 6:
the CQR rules "are not frozen here" and "belong to the Stages that own them".
The anchored chain today is r0 → r1 (`aapl_confirmatory-r1-bfa8028498ca`,
Stage 6.6, ADR 6.6.0001). No conformal number has been computed on the cohort
(the 7.1 run wrote predictions only — technical 7.1 §7, Etapa E).

## Decision

`[decision:C] 7.2-PREREG — form of the CQR preregistration`
`Escolha: revision r2 of aapl_confirmatory, blind_status = "blinded" · Alternativas: own plan file (aapl_conformal-r0); ADR only · Degrau: 1 (ADR 6.5.0002 and the r1 precedent of 6.6)`
`Base: ADR 6.5.0001/6.5.0002/6.5.0003; ADR 6.6.0001; doc §7 "Mecanismo"`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim, até a âncora`

1. **File.** `config/preregistration/aapl_confirmatory-r2.toml` = r1 verbatim
   except `revision = 2`, the amendment fields (`amends` = the r1
   `preregistration_ref`, a non-empty `justification`, `blind_status =
   "blinded"`) and a new optional block `[conformal]`. Nothing that judges H1,
   H2 or H3 changes; r0 and r1 hashes are unchanged (the block is absent there).
2. **Block content** — one catalog identifier per rule (accepted only if the
   code implements it, ADR 6.5.0004 item 2 pattern, through a new
   `ConformalParameters` VO in `evaluation/domain/value_objects`, forbidden in
   r0, optional for r ≥ 1):
   - variant of record: asymmetric split-CQR, unweighted, one-sided scores on
     the rearranged (`value_guardrail`) pair, rank ⌈(n+1)(1−α_tail)⌉ in exact
     rational arithmetic over the decimal of each level, α_lo = τ_lo,
     α_hi = 1 − τ_hi, rank > n ⇒ +∞ (ADR 7.2.0002);
   - sensitivity: NexCP with fixed weights ρ^(n+1−i), i in increasing target
     time, `rho = 0.99`, normalized with the test point's weight 1, threshold =
     smallest score whose cumulative normalized weight is ≥ 1 − α_tail, +∞ when
     the finite mass never reaches it (Barber et al. 2023 Eqs. (10)–(11) and
     footnote 1; authors' code, ADR 7.2.0002);
   - unit of calibration: (fold, seed, horizon, pair, tail, variant), nothing
     reused across units nor aggregated across horizons;
   - pairs: the three symmetric pairs of the grid; primary comparison pair =
     the H1 gate pair (`h1_gate.lower_level/upper_level`, cross-checked);
   - output: not rearranged; ±∞ limits allowed and flagged;
   - comparison: descriptive, on the candidate's full series per seed
     (`model_full`), with the native series' degeneracy mask and the plan's
     `degeneracy_tolerance` (same n as the native coverage), ĉ per conformal
     tail, PICP/MPIW per pair, Wilson at the plan's two band levels, two seed means
     over complete seeds only — c̄/n̄ (ADR 6.5.0006 item 2) and the mean of
     per-seed coverages (ADR 0.0.0008 item 9) —, label "cobertura empírica (não
     garantida)", no hypothesis test (ADR 0.0.0008 item 11);
   - profile quantities: nesting-violation rate across conformalized pairs,
     per-seed dispersion, Beta(n+1−l, l) reference **per tail only** and only
     for the unweighted variant (parameters, mean, sd; none when l = 0). No
     per-pair Beta: under asymmetric CQR the pair's conditional coverage
     depends on both tails and is not Beta-distributed (Checkpoint A, A-D5).
3. **Not a scorecard profile.** `[profiles].declared` is not extended: the
   conformal benchmark is a comparative axis beside the scorecard (ADR 0.0.0008
   item 1; doc §4.11), never a profile of H1/H2; `ScorecardProfile` and the
   verdict ignore the block, so `BuildConfirmatoryScorecard(revision=2)` yields
   the same `ScorecardVerdict` as revision 1 (tested).
4. **Anchor (ADR 6.5.0003).** After the r2 file is committed: tag
   `preregistration/<r2 ref>`, a comment on **issue #158** (ref, full hash, tag,
   commit, cohort_id and cohort hash), and
   `config/preregistration/aapl_confirmatory-r2.anchor.toml` with tag, commit,
   comment URL and server `anchored_at`; this is the Stage's last Task before
   the PR, so r2 is anchored before any metric on the real cohort (8.1). The
   mirror `docs/preregistration/aapl_confirmatory.md` gains the r2 section with
   the full hash.
5. **8.1 judges by the latest anchored revision of the chain** (r2 after this
   Stage; r3 if Stage 7.3 amends for H3): `refresh_command_from(rN, ref)` and
   `BuildConfirmatoryScorecard(revision=N)`. The roadmap sentence "a 8.1 julga
   pela r1" is replaced.

## Alternatives considered

### Alternative A — Own plan file (`aapl_conformal-r0.toml`)
- **Pros:** CQR edits never touch the confirmatory chain.
- **Cons:** two chains and two anchors for one study; 8.1 would load two plans
  and cross-check cohort and grid between them; the scorecard's revision chain
  would no longer describe the whole protocol.
- **Why rejected:** rung 1 — the 6.5 machinery and the 6.6 precedent make an
  amendment the way to add rules to the same study.

### Alternative B — Freeze the details in this ADR only
- **Why rejected:** doc §7: "o ADR registra a decisão; o pré-registro é o
  artefato hasheado". An ADR is not hashed nor anchored.

### Alternative C — Declare conformal quantities as scorecard profiles
- **Pros:** the scorecard would list their state.
- **Cons:** needs new `PROFILE_CATALOG` entries and `ScorecardProfile` states
  for something that is not a profile of the verdict's metrics.
- **Why rejected:** rung 5 (simplest) and ADR 0.0.0008 item 1 (conformal never
  enters the verdict path).

### Alternative D — Do nothing until 8.1
- **Why rejected:** ADR 0.0.0008 item 12 and the 7.2 DoD require the rules to be
  frozen before any metric on the real cohort; leaving them to 8.1 would freeze
  them in the Stage that computes them.

## Consequences

### Positive
- One chain r0 → r1 → r2 describes the whole confirmatory protocol.
- The CQR rules are hashed before the code that measures them ever sees the
  real test partition.

### Negative
- Every later amendment (H3 in 7.3) must copy r2 verbatim.
- The Preregistration VO gains an optional block and a cross-rule (primary pair
  = gate pair).

### Neutral / trade-offs accepted
- The conformal gold tables are built by `RefreshGold` in this Stage (ADR
  7.2.0003) and filled for the first time on the real cohort by 8.1; r2
  freezes what they contain.

## References

- Related ADRs: [0.0.0008](./0_0_0008-native-quantiles-with-conformal-benchmark.md),
  [6.5.0001](./6_5_0001-preregistration-canonical-toml-hashed-value-object.md),
  [6.5.0002](./6_5_0002-amendment-as-new-revision-file.md),
  [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md),
  [6.5.0004](./6_5_0004-judging-values-in-preregistration-cohort-by-reference.md),
  [6.5.0006](./6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md),
  [6.5.0008](./6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md),
  [6.6.0001](./6_6_0001-stationarity-diagnostic-acf-and-dm-variance-cusum-frozen-by-blinded-r1.md),
  [7.2.0002](./7_2_0002-own-cqr-in-domain-mapie-oracle-nexcp-fixture.md),
  [7.2.0003](./7_2_0003-conformal-intervals-on-demand-gold-via-refresh-gold.md).
- Inference domain doc §4.13, §7.
- Issue: [#158](https://github.com/MarceloSanC/financial-forecasting/issues/158).
