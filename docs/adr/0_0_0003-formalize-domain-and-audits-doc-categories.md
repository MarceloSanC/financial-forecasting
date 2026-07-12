---
title: ADR 0.0.0003 — Formalize the `domain/` and `audits/` documentation categories, nested by bounded context
description: Architecture Decision Record
when-use: Reference before creating a domain-knowledge doc or an audit report, when deciding where canonical subdomain theory (the what/why) or a read-only implementation-vs-reality diagnosis belongs, or when questioning the `docs/domain/` and `docs/audits/` structure and frontmatter
keywords: [adr, documentation, domain, audits, doc-category, bounded-context, ddd, ubiquitous-language, subdomain, step-gate]
status: accepted
created_at: 2026-07-11
updated_at: 2026-07-11
adr_id: 0.0.0003
decision: Formalize `docs/domain/` (canonical, cross-Stage subdomain theory) and `docs/audits/` (read-only implementation-vs-reality diagnoses) as first-class local documentation categories extending ADR 0.0.0000, in a single ADR, both nested by bounded context (`docs/<category>/<bc>/<slug>.md`) mirroring `features/<bc>/`.
context_stage: 0.0-global
---

# ADR 0.0.0003 — Formalize the `domain/` and `audits/` documentation categories

> ADRs are written and consumed in **English**, even when the rest of the project
> docs (including the domain and audit documents this ADR governs) are in
> Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The documentation standard ([ADR 0.0.0000](./0_0_0000-adopt-documentation-standard.md))
enumerates three kinds of docs: **project-level** (`overview.md`, `roadmap.md`),
**per-Stage** (`docs/stages/N.M-<slug>/`), and **auxiliary** (ADRs in `docs/adr/`,
runbooks in `docs/runbooks/`). It also states that ADRs are "mandatory for
non-obvious decisions".

Two further kinds of document are now needed, and neither has a home in that
standard.

**1. The theory layer of a subdomain (`domain/`).** The Step-level orchestration
prompt ([`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §1)
makes a `docs/domain/<bc>/<subdomain>.md` with `status: accepted` a **blocking
gate**: no Stage of a Step may start until the theory the Stage's `concept.md`
consumes is written down and sourced. Step 5 (modeling — naive/statistical
baselines, quantile training, the confirmatory cohort) is the first Step to hit
this gate, and it cannot start without it. Today that theory (how a random-walk
baseline emits quantiles, what the pinball loss is and why quantile crossing
matters, known/unknown typing in the TFT, the seeds × folds discipline of the
confirmatory cohort) is scattered across roadmap prose, the `5_1_*` ADRs and the
`dmls-*` skills — re-derived per Stage and free to drift.

**2. A read-only diagnosis of the implementation against the reality of the data
(`audits/`).** Issue [#32](https://github.com/MarceloSanC/financial-forecasting/issues/32)
(reinforcing the anti-leakage cross-check of the dataset-builder) has exactly
this shape: a durable finding, with evidence, that a later Stage will consume as
its spec. Today it lives in an issue body and dies with the ticket.

Both categories were **imported from the sibling project's template** as two
separate ADRs (`0.0.0003` for `audits/`, `0.0.0004` for `domain/`). The imported
text records **that** project's history (accounting subdomains, ERP
reconciliation, its bounded contexts and its issue numbers) and was never a
decision of this project. This ADR **replaces both imported drafts** with a
single decision taken here, for this project's reasons.

Forces at play:

- Neither category is an existing artifact: a domain doc is not a *decision*
  (that is an ADR), not Stage *planning/execution* (that is `stages/`), and not
  the *how* of implementation (that is code + `technical.md`). An audit is not a
  decision either, nor canonical theory — it is a diagnosis with evidence.
- The two are being adopted **in the same act, for the same structural reason**
  (extend ADR 0.0.0000; nest by bounded context, mirroring `features/<bc>/` from
  [LAYOUT.md §2](../LAYOUT.md)). Splitting them into two ADRs would duplicate the
  shared rationale and make each one carry a cross-reference to the other.
- The bounded contexts of this project are the ones under
  `src/financial_forecasting/features/`: **`market_data`**,
  **`feature_engineering`**, **`modeling`**, **`analytics_store`**.

## Decision

Recognize **`docs/domain/`** and **`docs/audits/`** as first-class local
documentation categories that extend ADR 0.0.0000, with the contracts below.

### `docs/domain/` — the theory layer of a subdomain

The conceptual **what** and **why**: fundamentals, canonical metrics and their
formulas, invariants, business/statistical rules, and the ubiquitous language
(DDD) of the subdomain. It is **transversal to Stages**: the base each Stage's
`concept.md` consumes, so the same knowledge is stated once and reused instead of
being re-derived (and drifting) in every Stage that touches the subdomain.

A domain doc is explicitly **not an implementation spec**: it does not define
schemas, file layouts, recompute cadences or edge cases — those belong to the
Stage `technical.md` + code, which hold the system context.

Every formula and rule that is *load-bearing* (i.e. that changes a number the
project reports) carries a **traceable citation to a primary source**. The
sourcing bar and its **fixed search order** live in
[`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §1 — this ADR
does not restate them. In short: the sources this project has **already
ratified** come first ([`overview.md`](../overview.md) §Referências, the
`## References` of the relevant ADRs, the `concept.md` of Stages already `done`
in the same BC); a new source is sought **only** for what they do not cover, must
be primary and tied to this project's context, and is registered back in
`overview.md` §Referências in the same PR.

**Structure — nested by bounded context, no root tier:**

```
docs/domain/<bc>/<english-kebab-subdomain>.md
```

`<bc>` is named exactly like `features/<bc>/` (`market_data`,
`feature_engineering`, `modeling`, `analytics_store`). Canonical knowledge always
belongs to a subdomain inside a BC, so — unlike `audits/` — there is **no
cross-cutting root tier**.

**Frontmatter** — common fields from [CONVENTIONS.md §2](../CONVENTIONS.md) plus:

```yaml
bounded_context: string          # the BC, named like features/<bc>/ (e.g. modeling)
subdomain: string                # the subdomain inside the BC (e.g. quantile-forecasting)
# optional:
superseded_by: path/to/newer.md  # only if status=superseded
references: [other-doc.md, ...]
```

**Lifecycle:** `draft` → `accepted` (→ `superseded`).

- `draft` — being authored or under review; **not** yet a reliable base for a
  Stage `concept.md`, and **does not satisfy** the Step gate.
- `accepted` — reviewed and canonical; the project commits to this as the shared
  theory of the subdomain. (`accepted`, not `done`, deliberately mirrors the ADR
  vocabulary: a curated, reviewed statement, not a one-shot deliverable that is
  "finished".)
- `superseded` — replaced by a rewritten domain doc; point `superseded_by` at the
  replacement, as an ADR does.

A domain doc does **not** archive when a Stage closes — it is cross-Stage by
definition and stays `accepted` as living reference, revised in place (bumping
`updated_at`) as the understanding of the subdomain grows.

### `docs/audits/` — read-only diagnosis with evidence

A **read-only diagnosis** that cross-checks a concrete implementation against the
reality of the data (a leakage cross-check, a reconciliation of a built dataset
against its source, a metric that disagrees with its oracle), **quantifies the
gap with evidence**, and **proposes a remediation** that a later Stage or ADR will
execute. It is the durable record of "we found X, here is the proof, here is how
to fix it" — independent of any single PR or issue thread.

An audit is **not** a decision (→ `adr/`), not Stage planning (→ `stages/`), not
canonical theory (→ `domain/`), and not a throwaway PR finding (→ the PR thread;
promote to an audit only when the diagnosis is durable and worth a Stage).

**Structure — nested by bounded context, with a root tier for cross-cutting:**

```
docs/audits/<bc>/<english-kebab-slug>.md     # owned by a single BC
docs/audits/<english-kebab-slug>.md          # cross-cutting (no single BC owner)
```

**Frontmatter** — common fields from [CONVENTIONS.md §2](../CONVENTIONS.md) plus:

```yaml
audit_id: kebab-slug             # stable id, independent of the filename
scope: [paths/or/modules]        # exact area audited (BC-relative or repo-relative)
# optional:
supersedes: [audit_id, ...]
references: [other-audit.md, ...]
```

`scope` is kept even when the folder already names the BC: the folder records
**ownership** (one BC), while `scope` records the **exact modules/paths audited**
(finer than the BC, and the only discriminator for root-level cross-cutting
audits).

**Lifecycle:** `open` → `closed`.

- `open` — the gap is diagnosed but not yet remediated.
- `closed` — the remediation landed; the closed audit **must link to the Stage
  and/or ADR that fixed it**. Closing an audit does **not** require resolving
  every secondary `[finding]` inside it; those may live on as separate issues,
  noted in the audit body.

### Boundaries (both categories)

| Artifact | Home |
|---|---|
| A decision with alternatives | `docs/adr/` |
| Stage planning / execution | `docs/stages/<N.M-slug>/` |
| Canonical subdomain theory (what/why) | `docs/domain/<bc>/` |
| Read-only implementation-vs-reality diagnosis | `docs/audits/[<bc>/]` |
| The *how* of implementation (schemas, cadence, edge cases) | code + `technical.md` |
| Recurring operational procedure | `docs/runbooks/` |

### Naming and language

Filename **slug in English kebab-case** (consistent with stages/ADRs); document
**body in Portuguese** (human-facing narrative artifact, same rule as the other
narrative docs — [CONVENTIONS.md §1](../CONVENTIONS.md)).

## Alternatives considered

### Alternative A — One ADR per category (the shape of the imported drafts)
- **Description:** keep two ADRs, one for `domain/` and one for `audits/`, each
  rewritten for this project.
- **Pros:** each ADR stays focused; superseding one category later touches only
  its own ADR; it is the shape the origin project chose.
- **Cons:** the two categories are being adopted **in the same act** and share the
  same rationale (extend 0.0.0000) and the same structural rule (BC nesting) —
  two ADRs duplicate that rationale and force a mutual cross-reference, which is
  exactly the "eco divergente" that [CONVENTIONS.md §0](../CONVENTIONS.md) warns
  against. The "one ADR per category" call recorded in the imported drafts was a
  **user decision in the origin project**, made when the two categories already
  existed there for different historical reasons; it does not bind this project.
- **Why rejected:** user decision (2026-07-11) — synthesize into one ADR. Cheaply
  reversible: if the two categories' rules diverge materially later, split this
  ADR in two and supersede it.

### Alternative B — No `domain/`; keep subdomain theory inside each `concept.md`
- **Description:** no separate category; the what/why of a subdomain lives in the
  `concept.md` of the Stage that first needs it.
- **Pros:** zero new categories; theory sits next to the plan that uses it.
- **Cons:** the modeling theory of Step 5 spans Stages 5.2–5.5 **and** feeds Step
  6 (the confirmatory statistics); pinning it to one `concept.md` forces every
  later Stage to re-derive or copy it, and the copies drift. It also **does not
  satisfy** the blocking gate of `PROMPT-step-single-session.md` §1, which
  requires the theory to exist, sourced and `accepted`, *before* the first Stage
  of the Step.
- **Why rejected:** domain theory is transversal to Stages, and the Step gate
  requires a home that outlives any single `concept.md`.

### Alternative C — No `audits/`; leave diagnoses in issues and PR threads
- **Description:** adopt only `domain/` (the category that blocks Step 5) and let
  implementation-vs-reality findings live as GitHub issues.
- **Pros:** no category without an instance; strictly less ceremony now (the
  anti-overengineering default of the `project-scope-principles` skill).
- **Cons:** an issue is a *ticket*, not a diagnosis: it has no contract for
  evidence, no lifecycle tying it to the Stage that remediated it, and it dies
  when closed. Issue #32 is already the spec of a future Stage and would be lost
  as durable reference.
- **Why rejected:** the diagnosis outlives the ticket. **Trade-off accepted
  explicitly:** `audits/` is adopted with **zero instances today** — unlike
  `domain/`, this ADR *invents* the category rather than ratifying an existing
  practice. It is justified by the imminent first instance (issue #32) and costs
  nothing until a file is written; if no audit is ever written, the cost is one
  unused section of this ADR.

### Alternative D — Flat categories (no BC nesting)
- **Description:** every file at `docs/domain/<subdomain>.md` /
  `docs/audits/<slug>.md`.
- **Pros:** one less directory level for categories that have zero or one file
  today.
- **Cons:** loses BC-at-a-glance grouping and stops mirroring `features/<bc>/`
  ([LAYOUT.md §2](../LAYOUT.md)). As subdomains accumulate (modeling alone will
  hold baselines, quantile training and the confirmatory cohort), the root
  degrades into an undifferentiated list.
- **Why rejected:** BC nesting mirrors the code layout and pays for itself as the
  categories grow; the extra level is free today.

## Consequences

### Positive
- `docs/domain/` and `docs/audits/` are documented, first-class categories with
  explicit purpose, frontmatter contract and lifecycle — new docs have a clear
  home and a stable shape.
- The blocking Step gate (`PROMPT-step-single-session.md` §1) now has a formal
  target: Step 5 can proceed as soon as `docs/domain/modeling/<subdomain>.md` is
  `accepted`.
- BC ownership is visible from the path, and both categories share one mental
  model — the same nesting as `features/<bc>/`.
- The boundary against `adr/`, `stages/`, `runbooks/` and implementation code is
  written down, including the rule that a domain doc is theory, **never** an
  implementation spec.

### Negative
- Two more categories for contributors to learn (mitigated by the symmetry
  between them and the boundary table above).
- `audits/` is formalized before its first instance exists (see Alternative C) —
  a category that could stay empty.
- The domain status vocabulary borrows the ADR term `accepted` (instead of the
  concept/technical `done`); a reader could expect the ADR state machine.
  Mitigated by spelling out the three-state lifecycle above.

### Neutral / trade-offs accepted
- `bounded_context`/`subdomain` (domain) and `scope` (audits) partially overlap
  the path; kept on purpose so they are greppable from the frontmatter and
  survive a file move.
- **No machine validation enforces these categories.** `make docs-check` covers
  only `check_technical_postexec.py` + `check_stage_issue.py`; conformance is a
  code-review concern, like the rest of CONVENTIONS.

## Implementation notes

- Create `docs/domain/<bc>/` and `docs/audits/<bc>/` **lazily**, named exactly
  like `features/<bc>/`. Cross-cutting audits stay at the `docs/audits/` root;
  `domain/` has no root tier.
- **First `domain/` instance:** the modeling theory that unblocks Step 5
  (`docs/domain/modeling/<subdomain>.md`), to be written under the domain gate of
  `PROMPT-step-single-session.md` §1 — not part of this ADR's PR.
- **First `audits/` candidate:** issue
  [#32](https://github.com/MarceloSanC/financial-forecasting/issues/32)
  (anti-leakage cross-check of the dataset-builder), when it is executed.
- This ADR **replaces the two drafts imported from the template**
  (`0_0_0003-formalize-audits-doc-category.md` and
  `0_0_0004-formalize-domain-doc-category.md`), removed in the same PR. They were
  never accepted decisions of this project: their Context, bounded contexts,
  examples and issue links belonged to the origin project. ADR id `0.0.0003` is
  reused because those drafts never landed on `develop`.

## References

- Extends: [ADR 0.0.0000](./0_0_0000-adopt-documentation-standard.md)
  (documentation standard — project-level, per-Stage and auxiliary docs).
- Gate that requires `domain/`:
  [`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §1 (domain
  gate, blocking, with the sourcing bar).
- Conventions: [CONVENTIONS.md §1–§3](../CONVENTIONS.md) (naming, frontmatter,
  status); [LAYOUT.md §2](../LAYOUT.md) (`features/<bc>/`, mirrored by the
  nesting).
- Originating issue:
  [#45](https://github.com/MarceloSanC/financial-forecasting/issues/45).
- First `audits/` candidate:
  [#32](https://github.com/MarceloSanC/financial-forecasting/issues/32).
