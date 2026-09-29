---
title: ADR 6.2.0006 — R-oracle fixture format of Step 6 (JSON with exact inputs and provenance, <unit>.R generator, <unit>.sessionInfo.txt, two-line Dockerfile, provenance test over every fixture); Stage 6.2 has R fixtures for DM only
description: Architecture Decision Record
when-use: Reference when generating or regenerating any R-oracle fixture of the project (DM in 6.2, rugarch backtests in 6.3, …), when asking what must be committed next to a fixture JSON, how numbers round-trip exactly between R and Python, or why there is no mcs_cases.json under tests/fixtures/r_oracle/
keywords: [adr, evaluation, r-oracle, fixtures, provenance, rocker, r-ver, sessioninfo, dm-test, forecast, rugarch, mcs, reproducibility, ci, round-trip]
status: accepted
created_at: 2026-09-28
updated_at: 2026-09-28
adr_id: 6.2.0006
decision: Every R-oracle unit commits under tests/fixtures/r_oracle/ a `<unit>.json` (provenance block + cases with exact inputs — decimal "%.17g" plus C99 hex "%a" — and expected outputs or errors), its `<unit>.R` generator and `<unit>.sessionInfo.txt`, plus one shared two-line `Dockerfile` (FROM rocker/r-ver:4.4.1 / RUN install2.r --error --ncpus 4 forecast rugarch jsonlite); every floating-point input is a {"dec", "hex"} object (scalar or equal-length lists), integers and strings stay plain, outputs are plain %.17g numbers; an integration test checks every tests/fixtures/r_oracle/*.json for the provenance fields and their agreement with the sessionInfo, and the exact decimal↔hex round-trip of the inputs; CI never runs R. In Stage 6.2 only DM gets R fixtures; the MCS oracle is arch (integration test) plus analytic fixtures, so mcs_cases.json is not created.
context_stage: 6.2-paired-inference-dm-mcs-holm
bounded_context: evaluation
---

# ADR 6.2.0006 — R-oracle fixtures: format of the Step, provenance and scope

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` (revised after Checkpoint A rounds 1–2: this ADR owns the R-fixture format for
all of Step 6 — Stage 6.3 conforms; exact number round-trip; integration location;
JSON schema of a double fixed by the master session in round 2).

## Context

- ADR 0.0.0021: correctness per unit against an oracle; "R-oracle harnesses are
  version-pinned and documented per unit when introduced"; a global snapshot is
  rejected. ADR 0.0.0056 (human decision): the R oracle is consumed as versioned
  fixtures read by golden tests.
- CI and the dev image have no R. A local image built from `rocker/r-ver:4.4.1` with
  `forecast`, `rugarch` and `jsonlite` runs the generators once (forecast 8.23.0,
  rugarch 1.5.3). Rocker: "Non-latest R version images installs all R packages from a
  fixed snapshot of CRAN mirror at a given date. This setting ensures that the same
  version of the R package is installed no matter when the installation is performed."
  (r-ver page) — 4.4.1 is non-latest, so the tag pins R and the package snapshot.
- Stages 6.2 (DM) and 6.3 (rugarch `VaRTest`) write fixtures to the same directory in
  parallel; the master session assigned the format to this ADR.
- Numbers must reach Python as the **same doubles** R used: 17 significant digits are
  enough for a correctly-rounded parser, and the C99 hex form is exact by construction.
- Unit tests are "sem I/O" (pyproject marker); reading a fixture file is integration.
- The R `MCS` package (0.2.0) uses a moving block with an `ar()`-order block and
  α = 0.15, and derives `included` from the step p-value, not HLN Definition 4 — not a
  membership oracle (issue #114; Bernardi & Catania 2018); it is not in the image.

## Decision

1. **Files per R-oracle unit** in `tests/fixtures/r_oracle/`:
   - `<unit>.json` with
     - `provenance`: `generator` (repo-relative path of `<unit>.R`), `image`
       (`rocker/r-ver:4.4.1`), `r_version`, `packages` (name → version, e.g.
       `forecast`, `jsonlite`), `cran_snapshot` (the `repos` URL reported inside the
       container), `generated_at` (ISO date), `session_info` (path of
       `<unit>.sessionInfo.txt`), `command` (exact `docker run … Rscript <unit>.R`);
     - `cases`: each with an `id`, a description, its **inputs** (every double written
       twice: decimal `sprintf("%.17g")` and hex `sprintf("%a")`) and either the
       **expected output** (decimal `%.17g`) or the **expected error** (message);
   - `<unit>.R` — the deterministic generator (it asserts in R that
     `as.numeric(sprintf("%.17g", x)) == x` before writing);
   - `<unit>.sessionInfo.txt` — `sessionInfo()` of the generating run.

   **JSON schema of a number** (master decision, Checkpoint A round 2), so the
   provenance/round-trip test walks any unit generically:
   - every **floating-point input**, scalar or vector, is an object
     `{"dec": <number | [numbers]>, "hex": <string | [strings]>}` — `dec` written with
     `%.17g`, `hex` with `%a`, same shape (scalar ↔ scalar; list ↔ list of equal
     length);
   - **integers** (h, counts, 0/1 hit sequences) and **strings** stay plain JSON;
   - **outputs** (expected values) are plain JSON numbers written with `%.17g`;
   - the generic test recognises **exactly** the objects whose key set is
     `{"dec", "hex"}`;
   - required `provenance` keys: `generator`, `image`, `r_version`, `packages`,
     `cran_snapshot`, `generated_at`, `session_info`, `command` (`session_info` = path
     of `<unit>.sessionInfo.txt` relative to the JSON).
2. **One shared `Dockerfile`** in the same directory, exactly these two lines
   (byte-identical in every Stage that uses it):
   ```
   FROM rocker/r-ver:4.4.1
   RUN install2.r --error --ncpus 4 forecast rugarch jsonlite
   ```
3. **Provenance is tested, not trusted** — integration test over **every**
   `tests/fixtures/r_oracle/*.json`: fails if a required provenance key is missing, if
   `r_version`/`packages` disagree with the named sessionInfo file, if the generator or
   sessionInfo file does not exist, or if any `{"dec", "hex"}` object has mismatched
   shapes or a decimal and hex form that parse to different doubles
   (`float(dec) != float.fromhex(hex)`). Golden tests use the hex inputs.
4. **Scope in 6.2:** `dm_test_cases.{json,R,sessionInfo.txt}` with `alternative =
   "less"`, `power = 1`, non-negative losses: h = 1 and h = 7, rectangular and
   Bartlett, candidate better and worse, small T (T > h always — no h = T case, ADR
   6.2.0001), the h > 1 negative-variance fallback, a constant differential with h = 2
   (fallback, then the h = 1 zero-variance error), and the errors h > T and zero
   variance with h = 1. The MCS is checked against `arch` (ADR 6.2.0004) and analytic
   fixtures; **no `mcs_cases.json`**. The roadmap's `arquivos_a_criar` is corrected in
   the PR, and Bernardi & Catania (2018) is registered as consulted and discarded.

## Decision record

```
[decision:C] 6.2-R4 — what is recorded with the R fixtures (format of the Step)
Escolha: JSON with provenance + exact inputs (%.17g and %a) + outputs/errors, <unit>.R, <unit>.sessionInfo.txt, shared two-line Dockerfile; provenance and round-trip checked by an integration test over every fixture · Alternativas: JSON only; JSON + generator without pins; decimal-only inputs · Degrau (C): 1 (ADR 0.0.0021 "version-pinned and documented per unit"; ADR 0.0.0056)
Base: rocker-project.org/images/versioned/r-ver.html "Non-latest R version images installs all R packages from a fixed snapshot of CRAN mirror at a given date" [verificado; 4.4.1 é non-latest]
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] 6.2-R6 — R fixtures for the MCS (mcs_cases.json)
Escolha: not produced; MCS oracle = arch (integration) + analytic fixtures · Alternativas: R MCS package on clear cases (elimination order only); arch outputs frozen as JSON · Degrau (C): 1 (doc §6.5/§11.3 and issue #114: R MCS is not a membership oracle) e 5 (arch already runs in CI; a frozen copy would be a snapshot of a live oracle)
Base: issue #114 §Projetos comparáveis "Na 0.2.0, included vem do p-valor do passo, não do p-valor MCS cumulativo" [pesquisa da issue; a decisão não depende dela: o oráculo adotado é o arch]
Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

## Alternatives considered

### Alternative A — JSON only
- **Why rejected:** cannot be regenerated or audited; indistinguishable from a snapshot.

### Alternative B — JSON + generator, no pins
- **Why rejected:** ADR 0.0.0021 is stricter; `dm.test` semantics changed across
  forecast versions (`varestimator` since 8.17.0).

### Alternative C — Decimal-only inputs (≤ 10 decimals or `%.17g`)
- **Why rejected:** exactness would rest on both parsers rounding identically; the hex
  form removes the question and the test proves the decimal agrees.

### Alternative D — R MCS package fixtures on clear cases
- **Why rejected:** partial check with a different bootstrap and block rule, and an
  image change, for little verification; arch is an exact oracle already.

### Alternative E — Do nothing (commit only the JSON)
- **Why rejected:** see A.

## Consequences

### Positive
- Any reviewer can rebuild the image and regenerate the numbers; CI stays R-free.
- One format for every R fixture of the Step.

### Negative
- Three files per R unit plus the shared Dockerfile; regeneration is a manual Docker
  step.

### Neutral / trade-offs accepted
- Stage 6.3 conforms to this format (its fixtures fall under the same provenance test).

## References

- Related ADRs: [0.0.0021](./0_0_0021-per-unit-contract-tests-with-oracle.md),
  [0.0.0056](./0_0_0056-own-statistics-in-domain-r-oracle-as-fixtures.md),
  [6.2.0001](./6_2_0001-paired-loss-series-single-aligned-matrix-vo.md),
  [6.2.0003](./6_2_0003-dm-holm-of-record-statsmodels-oracle-no-dm-wrapper.md),
  [6.2.0004](./6_2_0004-mcs-procedure-in-domain-over-backend-bootstrap-indices.md).
- Rocker versioned images, https://rocker-project.org/images/versioned/r-ver.html.
- Bernardi, M.; Catania, L. (2018). "The model confidence set package for R".
  *International Journal of Computational Economics and Econometrics*, 8(2), 144–158.
  DOI: 10.1504/IJCEE.2018.091037.
- Domain doc §6.5, §11.3; issue [#114](https://github.com/MarceloSanC/financial-forecasting/issues/114) (fork R4).
