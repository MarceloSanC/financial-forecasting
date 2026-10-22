---
title: ADR 8.1.0003 — The judged generation is preserved as a sealed copy under `judged/<preregistration_ref>/` (byte-for-byte copy of `current/`, scorecard, run record, `CONTENTS.json` with per-file sha256 written last), attested by a versioned record, a tag and one issue comment
description: Architecture Decision Record
when-use: Reference before writing, moving or reading the judged generation; when the 8.2 reproduction or the 8.3 dossier needs the judged copy, its digest, the run environment or the attestation; before adding a code path that posts to GitHub
keywords: [adr, evaluation, judged-generation, preservation, immutability, content-addressed, sha256, seal, manifest, scorecard, run-record, environment, commit, seeds, attestation, tag, issue-comment, anchor]
status: accepted
created_at: 2026-10-22
updated_at: 2026-10-22
adr_id: 8.1.0003
decision: After the confirmatory refresh and the scorecard, a port-out `JudgedGenerationStore` (filesystem adapter next to `ParquetGoldStore`) copies the partition's `current/` byte for byte into `gold/asset=<a>/parent_sweep_id=<p>/judged/<preregistration_ref>/generation/`, checks the copied manifest equals the published one, writes `gold_model_comparison_confirmatory_scorecard.json` (absent if BLOCKED) and `run_record.json` (commit, clean tree, environment keys, gold-path library versions, inference summary; seeds by reference to the manifest), writes `CONTENTS.json` (sha256 of every file and a generation digest over the sorted list) last and renames staging into place; the copy is never overwritten and every read re-checks the digest; the run is attested, by runbook, with a committed `<name>-r<rev>.judged.toml`, a `confirmatory-run/<ref>` tag and one comment on the Stage issue.
context_stage: 8.1-confirmatory-run
bounded_context: evaluation
---

# ADR 8.1.0003 — Judged generation: preserved copy, run record, attestation

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The generation produced by the confirmatory run — tables, manifest and
scorecard — is the **judged result**: what the dossier identifies, what the
plots draw and what the 8.2 reproduction compares against (domain doc
reproduction §2.1). A new refresh replaces `current/` and deletes the previous
generation (ADR 6.4.0005 items 4–5), so the judged one must be preserved before
any other refresh (R-PRESERVA, §4.5 item 1), with commit, environment and seeds
recorded (§4.5 items 3–5). The roadmap had the scorecard written as
`gold_model_comparison_confirmatory_scorecard` under
`gold/asset=<a>/parent_sweep_id=<p>/scorecard/<preregistration_ref>/`, and the
first confirmatory refresh posting a comment on the Stage issue to close the
order cohort anchor < preregistration anchor < first confirmatory refresh
(ADR 6.5.0003 item 4).

Facts:

- `ParquetGoldStore.publish` writes `.staging/`, `MANIFEST.json` last, and
  swaps by two directory renames; siblings of `current/` are not touched.
- `data/` is git-ignored: anything stored only in the data root cannot attest
  itself.
- The checkpoint integrity precedent streams the sha256 of the file bytes in an
  adapter (ADR 7.1.0004 item 1).
- The 5.5 runtime probe records `code.src`, `code.uv_lock`, `code_dirty`,
  library versions (torch stack, numpy, pandas, pyarrow…) and `cpu`; the 7.1
  inference compares its snapshot with the cohort's recorded environment to
  choose `strict` (ADR 7.1.0003 item 3), so adding keys to that probe would
  move `infer` to `tolerance`. It does not record `arch`, `statsmodels`,
  `scipy`, `scikit-learn`, `scoringrules` or `duckdb`, nor the commit id.
- Seeds of every random step of the gold path (MCS, Monte Carlo, permutation
  and bootstrap of H3) are in `RefreshParameters`, which the manifest records;
  training seeds are in the cohort spec.
- Preregistration anchors are runbook steps (tag + comment + `.anchor.toml`,
  ADR 6.5.0003 items 1–2); commits are rebased at closing, tags keep them
  reachable (ADR 5.5.0001).

## Decision

```
[decision:C] 8.1-J1 — what the judged copy's hash is
Escolha: sha256 of the stored bytes of every file of the copy + generation digest over the sorted (path, sha256) list, in `CONTENTS.json` · Alternativas: canonical-row content hash of the gold tables; no hash (trust the filesystem) · Degrau (C): 1 (ADR 7.1.0004 item 1, byte hash for integrity of a stored artifact) and 5
Base: Sandve et al. 2013 Rule 5 "archive any intermediate result files"; the copy's role is integrity of an archive — field-by-field comparison is the 8.2's job (domain doc §4.6); Chacon & Straub, Pro Git 2nd ed. §10.2 "Git Objects" (content-addressable storage: an object is checked by its hash)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] 8.1-J2 — where the copy lives and what names it
Escolha: `gold/asset=<a>/parent_sweep_id=<p>/judged/<preregistration_ref>/` (one per cohort partition, ADR 8.1.0001), outside `current/`, with the digest inside · Alternativas: directory named by the digest (git-object style); `scorecard/<preregistration_ref>/` holding only the scorecard (roadmap text); outside `gold/` · Degrau (C): 1 (ADR 8.1.0001: one judged generation per partition) and 5
Base: ADR 6.4.0005 items 4–5 (current/ is replaced); naming by digest would admit several judged copies per revision; the roadmap path held only the scorecard, the domain gate requires the whole generation
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim (before the 8.1 run)

[decision:C] 8.1-J3 — run record
Escolha: `run_record.json` in the copy: commit, code_dirty (false), whether `config/preregistration/` is clean, the 5.5 probe keys (reused, unchanged), the CPU capability (the quantity ADR 7.1.0003 item 2 records — the probe's `cpu` is only machine/count, and R-BIT needs the capability), versions of the gold-path libraries the probe lacks, platform and CPU count, image id when available, inference summary; seeds by reference to the manifest's parameters and the cohort spec · Alternativas: extend the 5.5 probe keys; rely on uv.lock hash only; duplicate seeds · Degrau (C): 1 (domain doc §4.5 items 3–5; ADR 7.1.0003) and 5
Base: Sandve et al. 2013 Rules 3 "note the exact names and versions of the main programs", 4, 6 "the random seed should be recorded" (verified in the Step 8 domain gate); ADR 7.1.0003 item 3 (extra probe keys would break `strict`)
Verificado: herdado · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] 8.1-J4 — attestation
Escolha: runbook step after the seal: push tag `confirmatory-run/<preregistration_ref>` on the run commit; post one comment on the Stage issue with the body printed by the CLI (searching first for the digest to avoid duplicates); commit `config/preregistration/<name>-r<rev>.judged.toml` with digest, status, commit, tag, comment_url, commented_at (server created_at) · Alternativas: post from code through a GitHub port; no attestation outside the data root · Degrau (C): 1 (ADR 6.5.0003 items 1–2, 4: anchors by tag + comment + record file) and 5
Base: ADR 6.5.0003 item 4 (the 8.1 comment closes the chain); Haber & Stornetta 1991 (time-stamping by an external party, via ADR 6.5.0003). Strength stated honestly: the server timestamp of a comment posted after the seal is an upper bound of the refresh; the lower bound (refresh after the anchor) rests on G1 in code plus the manifest's local `started_at`, which "catches the honest mistake, not a forged clock" (ADR 6.5.0003 item 3) — the same strength 6.5 declared. A second, pre-refresh comment was not added: it would only move the forged-clock residual, not remove it, and doubles the runbook effects.
Verificado: herdado · Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

1. **Port.** `JudgedGenerationStore` in
   `evaluation/application/ports/out/judged_generation_store.py`:
   `find(partition, preregistration_ref) -> JudgedGeneration | None` and
   `preserve(partition, preregistration_ref, expected_manifest, documents) -> JudgedGeneration`.
   Real: a filesystem adapter in `evaluation/adapters/out/` next to
   `ParquetGoldStore` (same data root, `validate_path_identifier` on every
   path segment); fake in `tests/fakes/features/evaluation/`; contract suite
   `[fake, real]`.
2. **Layout.** `judged/<preregistration_ref>/generation/` (byte copy of
   `current/`: tables and `MANIFEST.json`),
   `gold_model_comparison_confirmatory_scorecard.json`
   (`ScorecardResult.as_mapping()`, written with sorted keys; absent when
   `BLOCKED`), `run_record.json`, `CONTENTS.json`.
3. **Protocol of `preserve`.** Remove a leftover staging directory → copy
   `current/` into staging → parse the copied manifest and compare it with
   `expected_manifest` (the manifest the refresh returned; and, by the use
   case, the scorecard's `manifest_read`) — different →
   `JudgedGenerationMismatchError`, staging removed → write the documents →
   compute the sha256 of every file and the generation digest → write
   `CONTENTS.json` **last** → rename staging to `judged/<ref>/`. An existing
   `judged/<ref>/` → `JudgedGenerationExistsError` before anything is written.
4. **Protocol of `find`.** No directory → `None`. Otherwise read
   `CONTENTS.json`, recompute every file's sha256 and the digest; any
   mismatch, missing or extra file → `JudgedGenerationTamperedError`.
5. **Immutability.** No code path overwrites, moves or deletes a judged copy.
   File permissions are not relied on (Windows bind mount); integrity is the
   digest checked on every read, and the external attestation (item 7).
6. **Run record.** The keys of decision 8.1-J3, from the consumer port
   `EvaluationEnvironment` (real composed in the composition root from the 5.5
   probe — whose keys are not changed — plus `importlib.metadata` versions of
   the gold-path libraries and `git rev-parse HEAD`). The exact library list
   and how the image id reaches the container are fixed in the technical.
7. **Attestation.** Runbook step after the seal (decision 8.1-J4). The CLI
   prints a deterministic comment body: preregistration ref, generation
   digest, status, commit, tag, manifest `started_at`/`finished_at`,
   `academic_decision_ready` with its reasons and the per-horizon verdict. The
   record file mirrors `.anchor.toml` and is committed.

## Alternatives considered

### Alternative A — Canonical-row content hash of the gold (8.1-J1)
- **Pros:** comparable across environments.
- **Cons:** the copy's question is "is this archive unchanged?", which a byte
  hash answers exactly; cross-run comparison is field by field in the 8.2.
- **Why rejected:** wrong tool for integrity; adds a second canonicalization.

### Alternative B — No hash (8.1-J1)
- **Cons:** an edited or truncated copy is indistinguishable from the judged
  one.
- **Why rejected:** R-PRESERVA asks for the hash.

### Alternative C — Directory named by the digest (8.1-J2)
- **Pros:** content-addressed in the git sense.
- **Cons:** a re-run would create a second judged copy for the same revision
  (the manifest timestamps differ), which ADR 8.1.0001 forbids.
- **Why rejected:** the natural key of a judgment is the revision.

### Alternative D — `scorecard/<preregistration_ref>/` with only the scorecard (8.1-J2)
- **Cons:** the tables and manifest stay only in `current/`, replaced by the
  next refresh.
- **Why rejected:** the domain gate requires the whole generation; the roadmap
  is refined (the file keeps the roadmap's scorecard name).

### Alternative E — Extend the 5.5 probe keys (8.1-J3)
- **Cons:** the 7.1 `infer` compares the snapshot with the cohort's recorded
  environment; new keys would make every run `tolerance`.
- **Why rejected:** breaks the strict reproduction of 7.1.

### Alternative F — uv.lock hash only (8.1-J3)
- **Pros:** the lock pins every version transitively.
- **Cons:** a reader of the record cannot see the versions without the
  repository at that commit; the domain gate asks for the versions.
- **Why rejected:** cheap to record both.

### Alternative G — Post the comment from code (8.1-J4)
- **Cons:** a GitHub port, adapter, fake and contract test for a single
  effect; network in the run path.
- **Why rejected:** the anchors are already a runbook step with the same
  guarantees.

### Alternative H — Do nothing
The judged generation disappears on the next refresh, and the 8.2 has nothing
to reproduce against.

## Consequences

### Positive
- The judged generation survives any later refresh and is self-describing
  (tables, manifest with silver identity, scorecard, environment, commit).
- Integrity is checkable by anyone with `sha256sum` against `CONTENTS.json`
  and the committed digest.

### Negative
- Doubles the gold storage of the partition (one copy).
- The attestation depends on a correctly executed runbook step.

### Neutral / trade-offs accepted
- The generation digest covers provenance fields (manifest timestamps); it is
  an integrity digest, not a reproduction criterion.
- Durability after a power loss is not attempted (as ADR 6.4.0005); an
  unsealed staging is discarded and the run repeated.

## Implementation notes

- Share the copy/rename helpers with `ParquetGoldStore` only through a
  domain-free module of the same adapter package (no adapter-to-adapter import
  across slices).
- `CONTENTS.json` lists paths relative to `judged/<ref>/`, POSIX separators,
  sorted.

## References

- Related ADRs: [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md),
  [6.4.0005](./6_4_0005-gold-full-refresh-per-cohort-partition.md),
  [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md),
  [7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md),
  [7.1.0004](./7_1_0004-checkpoint-resolution-before-load-and-write-ahead-inference-manifest.md),
  [8.1.0001](./8_1_0001-confirmatory-run-orchestration-guards-status-replay.md),
  [8.1.0002](./8_1_0002-silver-content-hash-exact-rows-consumed-by-refresh.md)
- Domain: `docs/domain/evaluation/reproduction-equivalence-and-reporting.md` §2.1, §4.5, §4.6, §7, §9 (R-PRESERVA, DOSSIE)
- External: Sandve et al. 2013, Rules 3–6; Chacon & Straub, *Pro Git* 2nd ed.
  §10.2 "Git Objects"; Haber & Stornetta 1991 (via ADR 6.5.0003)
- Issue: #211; concept 8.1 D5–D7
