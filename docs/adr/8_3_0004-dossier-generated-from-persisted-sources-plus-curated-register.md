---
title: ADR 8.3.0004 — The final traceability dossier is rendered by GenerateReportArtifacts from persisted sources (judged copy, preregistration chain, .judged.toml, attempt log, dim_run, figure records) in layers from verdict to detail, and the items that are not persisted data (deviations, findings, pre-anchor computation, training/ablation environments, reproduction result, internal equivalence pointer) come from a versioned hand-edited register docs/reports/dossier_register.toml parsed at the CLI boundary
description: Architecture Decision Record
when-use: Reference before editing the final dossier, adding a deviation or finding to it, or asking why hashes in the dossier are not typed by hand
keywords: [adr, evaluation, dossier, traceability, sandve, deviations, findings, blinding-statement, register, report]
status: accepted
created_at: 2026-10-24
updated_at: 2026-10-24
adr_id: 8.3.0004
decision: docs/reports/final_traceability_dossier.md (citable) and docs/reports/final_traceability_dossier_internal.md (internal: everything touching the prior evidence) are generated, never hand-edited, by the same use case that renders the figures, with sections for every row of domain doc §7 organised in layers (verdict and claims with pointers, input identity, preregistration chain and blinding, judged generation, environment/commits/seeds, figures, reproduction with R1/R2/R3 counts and max |Δ|, deviations and findings) in the citable file and the internal layer in a separate file; hashes and ids come from persisted sources; curated items come from docs/reports/dossier_register.toml (entries with kind in deviation, finding, pre_anchor, environment, reproduction, internal; title; summary; pointer), parsed by the CLI into DossierEntry DTOs, kind internal going only to the internal file; the blinding statement is transcribed verbatim from the judged revision.
context_stage: 8.3-plots-and-final-report
bounded_context: evaluation
---

# ADR 8.3.0004 — Dossier generated from persisted sources plus a curated register

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Doc §7 (DOSSIE, class C, Sandve et al. 2013 Rules 1, 3–9) lists the minimum
content: identities per claim, the preregistration chain, the pre-anchor
computation, the blinding statement, the judged generation, the declared power,
environments, commits, seeds, a deviation register, per-figure sources,
per-claim pointers, the reproduction result and an internal pointer to the
equivalence audit. Most of it is persisted (judged copy, scorecard,
`run_record.json`, `ATTEMPTS.jsonl`, preregistration TOMLs and anchors,
`.judged.toml`, `dim_run`). Some is not: deviations and findings live in the
technical §7 of 8.1/8.2 and in ADRs (e.g. B3, ADR 8.2.0004; the 8.2 PICP finding;
errata O1/O2 and F2–F5; the formatting-only `code.src` diff), and the training
(CPU) and ablation (Linux/GPU) environments are recorded in earlier stages'
technical §7. The 8.2 `reproduction_audit.md` was written by hand from command
output. The blinding statement content was decided by the human and anchored in
the revisions (ADR 6.5.0010, note of 2026-09-30).

## Decision

1. The dossier is rendered by `GenerateReportArtifacts` through the
   `ReportArtifactSink`; it is regenerated, never edited.
2. Layers (Sandve Rule 8): verdict and claims with a pointer (table/document,
   key, field) each — H1 per horizon with declared power, H2 per horizon,
   primary winner, "≥ 1 horizon", H3 reading, conformal benchmark; input
   identity; preregistration chain with `blind_status`, the verbatim
   `blinding_statement` and the ADR 6.5.0003 item 4 caveat; judged generation;
   environment, commits, seeds; figures (record per figure); reproduction;
   deviations and findings of the citable chain.
3. **Separate internal file** (domain doc §7 last row, "Interno, fora do texto
   do TCC"; P-EDIT, doc §9 item 2): the prior-evidence hash registry, the
   equivalence report, B3/ADR 8.2.0004, the 8.2 PICP finding, errata F2–F5, the
   E4 scaffold finding and the limit that `reproduction_audit.md` §5 lists the
   blob of `tests/equivalence/prior_evidence.py`. The citable file cites none of
   these (tested) and points only to §1–§4 of `reproduction_audit.md`, repeating
   the claim numbers (R1/R2/R3 compared/different/max |Δ|, image, commit
   `060537fc`, `generation_digest`, `result_digest`). A file, not a section,
   because the TCC must be able to point to the citable dossier as a whole; the
   8.2 artifact is not edited.
4. Curated items come from `docs/reports/dossier_register.toml`, parsed by the
   CLI (adapter in) into `DossierEntry` DTOs passed in the command; a malformed
   register is an error before the use case runs.
5. The dossier carries no timestamp of the generation run (byte determinism,
   ADR 8.3.0003); recorded server timestamps of anchors are data.

## Alternatives considered

### Alternative A — Hand-written dossier (as reproduction_audit.md)
- **Pros:** no generator code.
- **Cons:** dozens of hashes and ids transcribed by hand; no test that every §7
  row is present.
- **Why rejected:** Sandve Rules 1 and 9 favour recorded over transcribed values.

### Alternative B — Fully generated, deviations hard-coded in source
- **Cons:** project history embedded in code; every new finding needs a code change.
- **Why rejected:** data belongs in a versioned data file.

### Alternative C — A dedicated out port to read the register
- **Cons:** port + fake + contract test for one static file read once.
- **Why rejected:** the CLI is already the boundary that reads user input.

## Consequences

### Positive
- A test can assert that every §7 row and the inherited deviations are present.

### Negative
- The register must be kept up to date by hand (acceptance A12 checks a closed
  list of inherited items).

## References

- Domain doc §7, §9 item 18; Sandve et al. 2013 Rules 1, 3–9
- ADRs 6.5.0003, 6.5.0010, 8.1.0004, 8.2.0004
- Concept 8.3 D8, D9
