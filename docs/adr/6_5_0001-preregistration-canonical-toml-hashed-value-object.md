---
title: ADR 6.5.0001 — The preregistration is a versioned TOML file, one per revision, parsed into a frozen Preregistration value object with typed values and enumerated rule identifiers, and hashed without float rounding through a shared PreregistrationHash VO; the markdown document is a human mirror that quotes the hash
description: Architecture Decision Record
when-use: Reference before changing where the preregistration lives, what its hash covers, how floats and rule identifiers enter the hash, how preregistration_ref is formed, how the markdown mirror relates to the canonical file, or why the Preregistration is a value object and not a domain service
keywords: [adr, evaluation, preregistration, hash, toml, value-object, canonical, mirror, preregistration-ref, immutability, identity, float, rule-identifier]
status: accepted
created_at: 2026-09-29
updated_at: 2026-09-30
adr_id: 6.5.0001
decision: The preregistration of a confirmatory study is declared in config/preregistration/<name>-r<revision>.toml (one immutable file per revision), read by an out adapter into a mapping, turned into a frozen Preregistration value object in the evaluation domain (unknown or missing keys are errors; numbers coerced to their declared type; every rule the domain applies named by an enumerated identifier that the domain accepts only if it implements it; every value validated by the public owner validators), and hashed over its canonical payload through a PreregistrationHash VO in shared/domain/value_objects — the only place hash_mapping may be called — which first replaces every float by its exact shortest repr, so the hasher's 10-decimal rounding never merges two plans; preregistration_ref = "<name>-r<revision>-<hash[:12]>" is the value carried by RefreshParameters and every confirmatory gold row; docs/preregistration/<name>.md is the human-readable mirror, which quotes each revision's full hash and whose consistency with the canonical file is checked by a test.
context_stage: 6.5-preregistration-and-scorecard
bounded_context: evaluation
---

# ADR 6.5.0001 — Canonical TOML, hashed value object, markdown mirror

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — revised on 2026-09-30 after Checkpoint A round 1 (float encoding,
type coercion, rule identifiers).

## Context

The domain doc §8.1 lists what the preregistration freezes ("como se julga")
and §8.2 (B-ORDEM, ADR 0.0.0011) requires it to be **hashed before any
confirmatory metric**. The roadmap planned `domain/services/preregistration.py`
and a document `docs/preregistration/aapl_confirmatory.md` "with the same
values", without saying which of the two is canonical (issue #127, fork C1).

Forces:

1. **Integrity:** any change to how the study is judged must change the hash
   (roadmap DoD: "alteração quebra o hash").
2. **One owner of identity:** `check_layout` rule 6 allows `hash_mapping` calls
   only inside `shared/domain/value_objects/`; the cohort uses a `CohortHash` VO
   for the same reason (ADR 5.5.0001, precedent ADR 5.2.0004).
3. **The hasher rounds floats.** `CanonicalJsonHasher` rounds every float to 10
   decimals before serializing (`shared/adapters/out/hashing/canonical_json_hasher.py`,
   `_FLOAT_PRECISION = 10`, ADR 1.4.0001). A tolerance of 1e-12, 1e-11 or 0.0
   would hash equal: the plan could change without changing the hash
   (Checkpoint A round 1, A-A1).
4. **Numbers from TOML:** `tomllib` returns `0` (int) and `0.0` (float) as
   different types, which serialize differently; a plan must not change hash
   because an integer-valued float was written without a decimal point.
5. **Rules, not only numbers:** §8.1 also freezes the primary metric and the
   role of the secondary ones, the DM direction/kernel/lag/fallback, the MCS
   block rule, "no exclusions", the logical form of the verdict and the success
   criterion (C-A1). These are rules implemented in code; if the plan only
   described them in prose, a change to the code would change the judgment
   without changing the hash.
6. **Two artifacts, one truth:** a markdown text with "the same values" as a
   machine file drifts silently unless one of them is canonical and the other is
   checked against it.
7. **Tactical shape:** the preregistration has no identity or lifecycle beyond
   its content (skill `ddd-tactical-patterns`: value object).
8. **Precedent:** the cohort is a versioned TOML parsed with `tomllib`
   (ADR 5.5.0001, Alternative A rejected YAML).

## Decision

`[decision:C] 6.5-C1 — canonical source of the preregistration hash`
`Escolha: TOML file per revision → frozen Preregistration VO (typed, with rule identifiers) → PreregistrationHash (shared VO, exact floats); markdown is a mirror that quotes the hash · Alternativas: markdown canonical (hash of the text); VO literal in Python code; one TOML edited in place per revision; change the hasher's precision · Degrau (C): 1 (ADR 5.5.0001: cohort as TOML + shared hash VO + name-r<rev>-<hash12>)`
`Base: ADR 5.5.0001 (Decision, "File and boundary", "Hash"); check_layout rule 6; canonical_json_hasher.py _FLOAT_PRECISION = 10`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o primeiro hash ancorado`

1. **File:** `config/preregistration/<name>-r<revision>.toml`. Revision 0 is the
   original; an amendment is a new file with a new revision (ADR 6.5.0002). A
   file, once its hash is anchored (ADR 6.5.0003), is never edited.
2. **Value object:** `Preregistration` (frozen, `evaluation/domain/value_objects/`)
   with nested frozen VOs per block of §8.1 (content: ADR 6.5.0004).
   `Preregistration.from_mapping(mapping)`:
   - rejects unknown and missing keys (the only optional key is the blinding
     statement, ADR 6.5.0010);
   - **coerces numbers to the declared type** — `float` for rates, α,
     thresholds, tolerance and deviation rates (so `0` and `0.0` are the same
     plan), `int` for reps, seeds, draws, deficits and horizons (a non-integral
     float or a `bool` there is an error);
   - accepts, for each **rule identifier** (ADR 6.5.0004 item 2), only the value
     the domain implements — changing a rule therefore needs a new identifier,
     which needs new code and gives a new hash;
   - validates every value with the **public owner validators** already used by
     `RefreshParameters` (`validate_alpha`, `validate_rate`, `validate_tolerance`,
     `validate_min_violations`, `validate_mcs_reps`, `validate_bootstrap_parameters`)
     — no second writing of a rule.
   `as_payload()` is its single canonical serialization (text fields as `str`;
   no date objects); `from_mapping(as_payload())` round-trips.
3. **Hash:** `PreregistrationHash.compute(hasher=…, payload=prereg.as_payload())`
   in `shared/domain/value_objects/preregistration_hash.py`. Before delegating
   to `hash_mapping`, the VO walks the payload and replaces every `float` `x` by
   the string `f"float:{x!r}"` (shortest exact round-trip repr), so the hasher's
   rounding never applies to a preregistration value. Tests: every leaf changes
   the hash; `1e-12` vs `1e-11` differ; `0` vs `0.0` in a float field give the
   same hash (coercion happens before).
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

- **Why rejected:** whitespace edits change the hash; values must be parsed back
  out of prose — a second parser of the same rules.

### Alternative B — The preregistration as a Python literal in code

- **Why rejected:** a reformatting refactor is indistinguishable from a change of
  plan in review; the cohort precedent is a config file (degree 1).

### Alternative C — One TOML edited in place, the tag preserves history

- **Why rejected:** an amendment must not overwrite the original (ICH E9 §5.1;
  OSF "Update" — issue #127 sources); ADR 6.5.0002.

### Alternative D — A domain service `preregistration.py` (roadmap wording)

- **Why rejected:** no behaviour beyond validation and serialization; the
  roadmap line is updated in this Stage's PR.

### Alternative E — Change the hasher's precision

- **Why rejected:** would change every existing fingerprint and the anchored
  cohort hash (ADR 1.4.0001 golden values); the exact encoding is local to the
  one identity that needs it.

### Alternative F — Rules described only as prose in the mirror

- **Why rejected:** the code could change the rule without changing the hash
  (force 5).

## Consequences

### Positive

- One truth for the values and the rules, one hash rule, one reference string
  end to end (TOML → VO → hash → `RefreshParameters` → gold → scorecard).
- No two different plans share a hash through float rounding or int/float
  spelling.

### Negative

- A second identity VO in `shared/domain/value_objects` close to `CohortHash`,
  with a float-encoding step that `CohortHash` does not have.
- A new rule needs a new identifier and code before it can be preregistered —
  intended.

## References

- Domain doc [`probabilistic-forecast-evaluation.md`](../domain/evaluation/probabilistic-forecast-evaluation.md) §8.1, §8.2, §10 conv. #25.
- Related ADRs: [0.0.0011](./0_0_0011-preregistration-invariants-and-h1-gate.md), [1.4.0001](./1_4_0001-canonicalizacao-de-hash-deterministico.md), [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md), [6.4.0006](./6_4_0006-refresh-parameters-explicit-no-domain-defaults.md), [6.5.0002](./6_5_0002-amendment-as-new-revision-file.md), [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md), [6.5.0004](./6_5_0004-judging-values-in-preregistration-cohort-by-reference.md), [6.5.0010](./6_5_0010-human-decisions-blinding-threshold-deviation-winner.md).
- ICH E9 (1998) §5.1; Nosek et al. (2018), PNAS, doi:10.1073/pnas.1708274114.
- Issue [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127) (fork C1); Checkpoint A round 1 (A-A1, C-A1, B1).
