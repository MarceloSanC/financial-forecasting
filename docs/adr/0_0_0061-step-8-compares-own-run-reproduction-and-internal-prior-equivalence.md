---
title: ADR 0.0.0061 — Stage 8.2 makes two comparisons — reproduction of the own confirmatory run from persisted artifacts (the citable claim) and an internal equivalence audit of the official pipeline against the prior confirmatory evidence on the common intersection
description: Architecture Decision Record
when-use: Reference when questioning what Stage 8.2 compares, why the TCC cites the reproduction of the own run and not the agreement with the prior project, which quantities the prior-evidence audit covers, or why that audit stays in the repository
keywords: [adr, step-8, stage-8.2, reproduction, equivalence-audit, prior-evidence, regression-oracle, common-intersection, pinball, picp, mpiw, diebold-mariano, verdict, editorial-policy, assum-4, r-repro-1, human-decision]
status: accepted
created_at: 2026-10-22
updated_at: 2026-10-22
adr_id: 0.0.0061
decision: Stage 8.2 makes both comparisons — (i) it re-executes the silver → gold → scorecard chain of 8.1 from the persisted cohort and compares it with the judged generation (bit for bit in the same pinned environment, per class across environments), which is the reproduction claim cited in the TCC; and (ii) it audits the official pipeline against the prior confirmatory evidence restricted to the common intersection (pinball at τ ∈ {0.1, 0.5, 0.9}, PICP/MPIW of the 80 % pair, DM against the common baselines as each side reported it, direction of the verdict), with the prior evidence frozen by content hash before it serves as oracle, as an internal audit recorded only in the repository; the TCC text does not mention the prior project.
context_stage: 0.0-global
bounded_context: evaluation
---

# ADR 0.0.0061 — Stage 8.2 compares the own-run reproduction and, internally, the prior evidence

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — decided by the human (Marcelo) on 2026-10-22 (issue #208, fork
P "B1" of the Step 8 domain gate).

## Context

The roadmap text of Stage 8.2 says: "comparar a pipeline oficial corrigida com
a evidência anterior (oráculo de regressão) dentro da tolerância declarada",
and its DoD asks for deltas within the declared tolerance (ASSUM-4) and
divergences explained by theory. Three facts pull against reading that
literally as the whole of 8.2:

- The overview fixes the prior evidence as an "oráculo de
  equivalência/regressão … nunca como autoridade de decisão" (§2) and the
  success criterion "Reprodutibilidade: artefatos de decisão reconstruíveis a
  partir de dados persistidos sem re-treino" (§4). The second is about **this**
  project's run, not about the prior one.
- The TCC editorial policy (human decision) forbids mentioning the prior
  project in the text: a claim built on agreement with the prior evidence
  cannot be stated in the TCC.
- The prior evidence is a different retraining on a different numerical stack
  (ASSUM-4); its grid, folds, baselines and statistical code may differ, so
  only a part of it is comparable at all.

What should 8.2 compare? This is a preference/scope question (it changes what
the Step delivers and what the TCC claims), so it went to the human
(`evidence-resolution` §1, class P).

## Decision

**Option C — both comparisons, with different roles.**

1. **(i) Reproduction of the own run — the citable claim.** Re-execute the
   silver → gold → scorecard chain of 8.1 from the persisted artifacts, without
   retraining, in a separate destination, and compare it with the judged
   generation preserved by 8.1: bit for bit in the same pinned environment
   (random steps included, seeds recorded); per class of quantity across
   environments. Theory: domain doc §4.
2. **(ii) Official × prior confirmatory evidence — an internal audit.**
   Restricted to the **common intersection**: pinball per level at
   τ ∈ {0.1, 0.5, 0.9}; PICP and MPIW of the 80 % pair (0.1, 0.9); DM against
   the common baselines, compared as each side reported it (never recomputed);
   the direction of the verdict (sign of the loss differential and DM
   rejection per common comparator and horizon). The prior evidence is
   **frozen by content hash** before it serves as oracle. How the declared
   tolerance of ASSUM-4 applies (numeric on the realized target and the metric
   code, direction on the model numbers) is a separate human decision, B2 —
   [ADR 0.0.0062](./0_0_0062-equivalence-tolerance-numeric-where-equality-expected-direction-for-model-numbers.md),
   not part of B1. The audit satisfies ASSUM-4 /
   R-REPRO-1 and is recorded only in the repository. Theory (alignment,
   tolerance, explanation, scaffolding): domain doc §5.
3. **Editorial boundary:** the TCC text uses (i); (ii) is not mentioned.

## Alternatives considered

### Alternative A — Only (i), reproduction of the own run
- **Characteristics:** 8.2 proves that the judged result is reconstructible
  from persisted data; the prior evidence is not used.
- **Pros:** the strongest and simplest claim; independent of artifacts outside
  version control; nothing to explain about a pipeline the text cannot name.
- **Cons:** leaves ASSUM-4 and R-REPRO-1 of the overview unanswered and drops
  the roadmap's regression-oracle role, which is the only external check that
  the rebuilt pipeline did not silently change what was being measured.
- **Reversibility:** easy (adding (ii) later is additive).

### Alternative B — Only (ii), the literal roadmap reading
- **Characteristics:** 8.2 compares the official pipeline with the prior
  evidence within a declared tolerance.
- **Pros:** matches the roadmap text word for word.
- **Cons:** the TCC could not cite it (editorial policy), so the Step would
  end without a citable reproducibility claim; it would make the prior
  evidence the reference of "correct", against overview §2; the
  reproducibility criterion of overview §4 would stay unproved.
- **Reversibility:** easy.

### Alternative C — Both (chosen)
- **Pros:** the citable claim rests on this project's artifacts only; the
  prior evidence keeps its role as regression oracle; the audit is restricted
  to what is comparable.
- **Cons:** more work in 8.2 (two comparisons); the audit depends on files
  outside version control, hence the hash freeze.
- **Reversibility:** easy; dropping (ii) later would only need this ADR
  superseded.

### Trade-offs across the options
- **Implementation cost:** A < B < C, but (i) reuses the existing refresh and
  scorecard; (ii) needs only readers of the prior files and the comparison.
- **Risk:** B carries the highest risk of "matching the old" being read as
  validation; A carries the risk of an undetected definitional drift; C covers
  both.
- **Who pays:** C's cost is paid once in 8.2; the TCC benefits from (i).

## Consequences

### Positive
- The reproducibility claim of the TCC is about the judged result itself,
  exact in the recorded environment (Sandve et al. 2013, Rule 6).
- The prior evidence is used for what overview §2 allows it to do, and no
  more.

### Negative
- The audit cannot become a continuous regression test (its oracle is not
  version-controlled); its durable record is the report with the hashes
  (domain doc §5.7); the equivalence test is skipped without the hashed oracle
  and is not a CI gate.
- 8.1 gains two obligations: preserve the judged generation (copy + hash)
  before any other refresh, and record a content hash of the silver it read
  (domain doc §4.5).

### Neutral / trade-offs accepted
- **Roadmap amended** in the same PR, anchored on this decision (roadmap >
  domain, so the domain doc could not contradict it): the 8.2 description and
  DoD now name (i) the reproduction of the 8.1 run from persisted artifacts and
  (ii) the internal equivalence audit; `non_goals` reads "bit-identical vs
  evidência anterior" (the own-run reproduction is bit for bit in the recorded
  environment); a reproduction report joins `arquivos_a_criar`; ROADMAP-5 is
  restated accordingly; a line in the roadmap history records it.

## References

- Domain doc [reproduction-equivalence-and-reporting](../domain/evaluation/reproduction-equivalence-and-reporting.md)
  §4, §5, §9.1 (B1, P-EDIT).
- [ADR 0.0.0060](./0_0_0060-reproduction-equivalence-reporting-domain-doc-scope-and-boundary.md),
  [ADR 7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md).
- Overview §2 (Estado atual), §4 (Critérios de sucesso), ASSUM-4, R-REPRO-1;
  roadmap Stage 8.2.
- Sandve, G. K.; Nekrutenko, A.; Taylor, J.; Hovig, E. (2013). "Ten Simple
  Rules for Reproducible Computational Research". *PLOS Computational
  Biology*, 9(10), e1003285. DOI: 10.1371/journal.pcbi.1003285. (Rule 6.)
- Decision: issue [#208](https://github.com/MarceloSanC/financial-forecasting/issues/208), 2026-10-22.
