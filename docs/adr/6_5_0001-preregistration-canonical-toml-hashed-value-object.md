---
title: ADR 6.5.0001 — The preregistration is a versioned TOML file, one per revision, parsed into a frozen Preregistration value object and hashed through a shared PreregistrationHash VO; the markdown document is a human mirror that quotes the hash
description: Architecture Decision Record
when-use: Reference before changing where the preregistration lives, what its hash covers, how preregistration_ref is formed, how the markdown mirror relates to the canonical file, or why the Preregistration is a value object and not a domain service
keywords: [adr, evaluation, preregistration, hash, toml, value-object, canonical, mirror, preregistration-ref, immutability, identity]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-29
adr_id: 6.5.0001
decision: The preregistration of a confirmatory study is declared in config/preregistration/<name>-r<revision>.toml (one immutable file per revision), read by an out adapter into a mapping, turned into a frozen Preregistration value object in the evaluation domain (unknown or missing keys are errors; every value validated by the public owner validators), and hashed over its canonical payload through a PreregistrationHash VO in shared/domain/value_objects (the only place hash_mapping may be called); preregistration_ref = "<name>-r<revision>-<hash[:12]>" is the value carried by RefreshParameters and every confirmatory gold row; docs/preregistration/<name>.md is the human-readable mirror, which quotes each revision's full hash and whose consistency with the canonical file is checked by a test.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0001 — Canonical TOML, hashed value object, markdown mirror

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The domain doc §8.1 lists what the preregistration freezes ("como se julga") and
§8.2 (B-ORDEM, ADR 0.0.0011) requires it to be **hashed before any confirmatory
metric**. The roadmap planned `domain/services/preregistration.py` and a document
`docs/preregistration/aapl_confirmatory.md` "with the same values", without
saying which of the two is canonical (issue #127, fork C1).

Forces:

1. **Integrity:** any change to how the study is judged must change the hash
   (roadmap DoD: "alteração quebra o hash").
2. **One owner of identity:** `check_layout` rule 6 allows `hash_mapping` calls
   only inside `shared/domain/value_objects/`; the cohort uses a `CohortHash` VO
   for the same reason (ADR 5.5.0001, precedent ADR 5.2.0004). The hasher rounds
   floats to a declared precision and rejects NaN/±inf (ADR 1.4.0001).
3. **Two artifacts, one truth:** a markdown text with "the same values" as a
   machine file drifts silently unless one of them is canonical and the other is
   checked against it.
4. **Tactical shape:** the preregistration has no identity or lifecycle beyond
   its content; it is defined entirely by its values (skill `ddd-tactical-patterns`:
   value object).
5. **Precedent:** the cohort is a versioned TOML parsed with `tomllib`
   (ADR 5.5.0001, Alternative A rejected YAML).

## Decision

`[decision:C] 6.5-C1 — canonical source of the preregistration hash`
`Escolha: TOML file per revision → frozen Preregistration VO → PreregistrationHash (shared VO); markdown is a mirror that quotes the hash · Alternativas: markdown canonical (hash of the text); VO literal in Python code; one TOML edited in place per revision · Degrau (C): 1 (ADR 5.5.0001: cohort as TOML + shared hash VO + name-r<rev>-<hash12>)`
`Base: ADR 5.5.0001 (Decision, "File and boundary", "Hash"); check_layout rule 6; ADR 1.4.0001`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o primeiro hash ancorado`

1. **File:** `config/preregistration/<name>-r<revision>.toml`. Revision 0 is the
   original; an amendment is a new file with a new revision (ADR 6.5.0002). A
   file, once its hash is anchored (ADR 6.5.0003), is never edited.
2. **Value object:** `Preregistration` (frozen, `evaluation/domain/value_objects/`)
   with nested frozen VOs per block of §8.1 (cohort reference, realized source,
   horizons and grid, primary metric and profile roles, H2 family and DM, MCS, H1
   gate, seeds, exclusions, verdict form, profiles, blinding exposures,
   amendment). `Preregistration.from_mapping(mapping)` rejects unknown and
   missing keys and validates every value with the **public owner validators**
   already used by `RefreshParameters` (`validate_alpha`, `validate_rate`,
   `validate_tolerance`, `validate_min_violations`, `validate_mcs_reps`,
   `validate_bootstrap_parameters`) — no second writing of a rule.
   `as_payload()` is its single canonical serialization;
   `from_mapping(as_payload())` round-trips.
3. **Hash:** `PreregistrationHash.compute(hasher=…, payload=prereg.as_payload())`
   in `shared/domain/value_objects/preregistration_hash.py`, mirroring
   `CohortHash` (the whole payload, no key removed).
4. **Reference:** `preregistration_ref = f"{name}-r{revision}-{hash[:12]}"`,
   formed by one function next to the VO; this string is what
   `RefreshParameters.preregistration_ref` and the confirmatory gold rows carry
   (ADR 6.4.0006 item 4). The full hash is in the anchor (ADR 6.5.0003).
5. **Mirror:** `docs/preregistration/<name>.md` explains each value in plain
   language, declares that the TOML is canonical, and quotes, per revision, the
   full hash and the `preregistration_ref`. A test recomputes the hash of every
   revision file and requires the mirror to quote it: an edit to the TOML that is
   not reflected in the mirror fails the build. The mirror's value tables are
   narrative; the numbers that judge are only the TOML's.
6. **Doc category:** `docs/preregistration/` holds only preregistration mirrors
   (one file per study, sections appended per revision, never rewritten). It is
   the roadmap's path; no other category changes.

## Alternatives considered

### Alternative A — Markdown canonical (hash of the text)

- **Pros:** one artifact; what the human reads is what is hashed.
- **Cons:** whitespace and wording edits change the hash; values must be parsed
  back out of prose to parameterize the refresh — a second parser of the same
  rules.
- **Why rejected:** the machine values would not have one owner.

### Alternative B — The preregistration as a Python literal in code

- **Pros:** type-checked.
- **Cons:** mixes a study artifact with code; a refactor that reformats the
  literal is indistinguishable from a change of the plan in review; the cohort
  precedent is a config file.
- **Why rejected:** degree 1 (cohort precedent).

### Alternative C — One TOML edited in place, the tag preserves history

- **Pros:** the cohort does this with `revision` (ADR 5.5.0001).
- **Cons:** an amendment must **not** overwrite the original (ICH E9 §5.1:
  changes after review go to "a protocol amendment"; OSF registrations are
  "read-only" and updated by a separate "Update" — issue #127 sources); with one
  file the original survives only in git history.
- **Why rejected:** the original stays readable in the working tree
  (ADR 6.5.0002).

### Alternative D — A domain service `preregistration.py` (roadmap wording)

- **Why rejected:** no behaviour beyond validation and serialization; a value
  object states the immutability the DoD asks for. The roadmap line is updated
  in this Stage's PR.

## Consequences

### Positive

- One truth for the values, one hash rule, one reference string end to end
  (TOML → VO → hash → `RefreshParameters` → gold → scorecard).
- The mirror cannot drift from the anchored hash without a red build.

### Negative

- A second identity VO in `shared/domain/value_objects` with the same body as
  `CohortHash`; a generic "payload hash" VO would remove the duplication but
  blur which identity is which (the per-identity VOs are the project's pattern).
- The hasher's float rounding (ADR 1.4.0001) means two values that differ below
  the declared precision hash equal; every preregistered float is far above it.

## References

- Domain doc [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md) §8.1, §8.2, §10 conv. #25.
- Related ADRs: [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md), [1.4.0001](./1_4_0001-canonicalizacao-de-hash-deterministico.md), [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md), [6.4.0006](./6_4_0006-refresh-parameters-explicit-no-domain-defaults.md), [6.5.0002](./6_5_0002-amendment-as-new-revision-file.md), [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md).
- ICH E9 (1998) §5.1; Nosek et al. (2018), PNAS, doi:10.1073/pnas.1708274114.
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (fork C1).
