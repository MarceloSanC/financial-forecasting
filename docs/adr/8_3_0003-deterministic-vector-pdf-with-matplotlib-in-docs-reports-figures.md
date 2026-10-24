---
title: ADR 8.3.0003 — Figures are vector PDFs rendered by matplotlib (direct dependency pinned by minor, object-oriented API, confined to evaluation/adapters/out/plots by an import-linter contract) with the creation date removed so the bytes are equal across generations in the same environment, colour-blind-safe palettes, Portuguese labels, versioned under docs/reports/figures/
description: Architecture Decision Record
when-use: Reference before adding a plotting library, changing the figure format or location, or when a regenerated figure differs byte-wise
keywords: [adr, evaluation, plots, matplotlib, pdf, determinism, source-date-epoch, cividis, colour-blind, import-linter, docs-reports]
status: accepted
created_at: 2026-10-24
updated_at: 2026-10-24
adr_id: 8.3.0003
decision: matplotlib>=3.11,<3.12 becomes a direct dependency (lock keeps 3.11.0) confined to features/evaluation/adapters/out/plots by a new import-linter forbidden contract whose sources are every other module of the package (indirect imports allowed, so the composition root may wire the adapter), plus an AST test forbidding matplotlib.pyplot anywhere in src/; the renderer uses matplotlib.figure.Figure with the PDF backend inside rc_context (no pyplot, no global state) with pdf.fonttype 42 and savefig(format="pdf", metadata={"CreationDate": None}); only PDF is produced; sequential scales use cividis, series use a fixed model-to-colour colour-blind-safe cycle validated by the dataviz palette validator, with identity never by colour alone; labels are in Portuguese; outputs are versioned in docs/reports/figures/ and text/ is not touched.
context_stage: 8.3-plots-and-final-report
bounded_context: evaluation
---

# ADR 8.3.0003 — Deterministic vector PDF with matplotlib, in docs/reports/figures/

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

No code imports matplotlib today; it reaches the lock (3.11.0) only through
mlflow. The TCC (`text/Main.tex`) uses `graphicx`, which takes PDF natively.
matplotlib's PDF backend writes a `CreationDate` unless the metadata sets it to
`None` or `SOURCE_DATE_EPOCH` is set (matplotlib 3.11.0 source; SOURCE_DATE_EPOCH
spec rev. 1.1); SVG adds a date and random ids (`svg.hashsalt`) and PNG a
`Software` key. Colour guidance: matplotlib "Choosing Colormaps" and Nuñez,
Anderton & Renslow 2018 (cividis). The 8.2 reports live in `docs/reports/`; the
TCC template keeps images next to chapters, but writing the TCC is out of scope.

## Decision

1. `matplotlib>=3.11,<3.12` in `[project] dependencies` (minor pin, the lock
   pins the patch); import-linter `forbidden` contract
   `evaluation-no-matplotlib-leak` whose `source_modules` list every module of
   `financial_forecasting` except `features.evaluation.adapters.out.plots`
   (including `adapters.out.reports`, `adapters.in`, other slices, `shared`,
   `cli`, `composition_root`), with `allow_indirect_imports = true`, and a break
   proof; an AST architecture test rejects `matplotlib.pyplot` in every `src/`
   file, the plots adapter included.
2. Renderer: `Figure` objects, PDF backend, `rc_context` with fixed fonts,
   sizes and `pdf.fonttype = 42`; `identity()` reports the matplotlib and
   FreeType versions; the contract test compares bytes across two subprocesses
   with different `PYTHONHASHSEED`; `savefig(format="pdf", metadata={"CreationDate": None})`; no
   environment variable.
3. PDF only (vector). No SVG/PNG.
4. Colour: cividis for sequential scales and the heatmap (viridis allowed); a
   fixed model → colour map from a colour-blind-safe cycle, validated in the
   technical with `validate_palette.js` (dataviz skill); legend plus marker or
   line style so identity is never colour-only; one y axis per panel.
5. Labels and captions in Portuguese.
6. Outputs in `docs/reports/figures/<id>.pdf` (+ record), committed; the TCC
   references this path later.

## Alternatives considered

### Alternative A — plotly + kaleido / interactive HTML
- **Cons:** extra heavy dependency; interactive dashboards are a non-goal.
- **Why rejected:** scope and LaTeX target.

### Alternative B — PNG (raster) or SVG
- **Cons:** raster scales badly in print; SVG needs conversion for pdflatex and
  carries random ids and dates.
- **Why rejected:** PDF is native to graphicx and the simplest to make deterministic.

### Alternative C — SOURCE_DATE_EPOCH environment variable
- **Cons:** process-global state, easy to forget in a run.
- **Why rejected:** explicit metadata in the adapter is local and testable.

### Alternative D — Write figures into text/5_Resultados/
- **Cons:** the 8.3 would edit the TCC tree (redaction is out of scope); two
  copies when the dossier also points to them.
- **Why rejected:** one location next to the dossier; reversible by moving files.

### Alternative E — Do not version figures (regenerate on TCC build)
- **Cons:** the TCC build would need the git-ignored data; regenerated bytes are
  only guaranteed equal in the same environment.
- **Why rejected:** the committed figures plus records are the archived output
  (Sandve Rule 5).

## Consequences

### Positive
- Two generations in the same environment yield identical bytes (acceptance A14).

### Negative
- A future matplotlib upgrade changes PDF bytes; the records (data digest) still
  prove the data.

### Neutral / trade-offs accepted
- Byte equality across environments is not claimed.

## References

- matplotlib 3.11.0 source (backend_pdf metadata); SOURCE_DATE_EPOCH spec rev. 1.1
- Nuñez, Anderton & Renslow 2018, PLOS ONE 13(7): e0199239; matplotlib "Choosing Colormaps"
- Issue #234 §Referências; concept 8.3 D6, D7
