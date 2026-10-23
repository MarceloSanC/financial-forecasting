---
title: ADR 8.1.0004 — One judgment per cohort partition enforced against unsealed attempts and a lost data root — write-ahead attempt log, live-generation check, the committed `.judged.toml` as cross truth, and re-execution only with the same code, environment and input or a registered deviation
description: Architecture Decision Record
when-use: Reference before re-running `evaluate` after an interrupted or failed run, before restoring or deleting a data root that holds gold, before anchoring a new revision of a plan already evaluated, or when asking what counts as "numbers already exist"
keywords: [adr, evaluation, confirmatory-run, re-judgment, forking-paths, attempt-log, write-ahead, deviation, judged-record, data-root, git-ignored, cross-check, replay]
status: accepted
created_at: 2026-10-22
updated_at: 2026-10-23
adr_id: 8.1.0004
decision: Numbers exist from the moment `RefreshGold` starts, not from the seal; so before E1 the use case appends a `started` line (ref, commit, code.src, code.uv_lock, R-BIT environment keys, started_at, deviation text if any, and the silver_content and `prior_live_result_digest` of the live generation of this revision if one exists) to a write-ahead attempt log of the partition, and after E1 an `input_read` line with the input read and the `result_digest` of the result layer published; G4 refuses — before any effect — when the partition has a sealed copy, an attempt or a live `current/` generation of another revision, when a committed `<name>-r*.judged.toml` names another revision or names this one without a sealed copy of the same digest, when an attempt of the current segment (since the last deviation that reached its input) ran other code or another R-BIT environment, or when the references of the segment (its `input_read` lines, the `prior_live_result_digest` of its `started` lines but the first, and the live generation) already disagree — unless a `[deviation]` justification is given; after E1 a different input or result than any reference stops with a `[finding]` and nothing is sealed; the durable source is git — the runbook commits each real attempt's intention in the technical §7 before running.
context_stage: 8.1-confirmatory-run
bounded_context: evaluation
---

# ADR 8.1.0004 — One judgment per partition: attempt log, committed record, deviation

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — amends ADR 8.1.0001 items 3 and 5 (G4) and ADR 8.1.0003 item 4 (`find`).

## Context

ADR 8.1.0001 keyed "already judged" on the sealed copy only. Checkpoint A
(round 1, findings DT-1/CA-1, DT-2/CA-3, CA-2) showed two holes:

1. **Unsealed attempts.** `RefreshGold` publishes `current/` at E1, before
   the seal at E3. A crash or abort between E1 and E3 leaves numbers on disk
   (and possibly read) with nothing in `judged/`. A later revision (r4) would
   pass G1–G4, and a re-run "before the seal" after changing code would
   produce a different judgment without any record — the forking-paths
   problem, and a correction after the hash without a deviation record
   (domain doc reproduction §4.6; ADR 6.5.0003 item 4: the 8.1 refresh *is*
   the first confirmatory refresh).
2. **The data root is git-ignored.** Deleting `judged/<ref>/` (or restoring an
   older backup) erases the evidence of a judgment; a `CONTENTS.sha256`
   rewritten consistently passes a digest check against itself.

Facts: `current/MANIFEST.json` carries `preregistration_ref` and `started_at`
(`GoldManifest.as_mapping`); the anchor records live in
`config/preregistration/` and are read by the `PreregistrationSource`; ADR
7.1.0003 item 3 already requires a justification citing a `[finding]` to
force a mode — the same pattern serves a deviation.

## Decision

```
[decision:E] 8.1-R1 — when "numbers exist"
Escolha: from the start of E1 (write-ahead attempt entry before RefreshGold) · Alternativas: from the seal (ADR 8.1.0001 as first written)
Base: ADR 6.5.0003 item 4 ("the first confirmatory refresh is, by definition, the first refresh of the cohort's gold after the anchor") — the refresh, not the seal; domain doc reproduction §4.6 ("qualquer correção que mude um número confirmatório depois do hash é um desvio do plano"); RefreshGold publishes current/ at E1 (refresh_gold.py `publish` step)
Verificado: não verificado (§4.2) — internal sources
Sensibilidade pré-registrada: nenhuma · Reversível: sim (before the 8.1 run)

[decision:C] 8.1-R2 — re-execution after an unsealed attempt
Escolha: allowed with the same code (code.src and code.uv_lock), the same R-BIT environment (image id, platform, CPU capability, library versions) and the same input (silver_content, dataset fingerprint) as every earlier attempt of the revision, the result checked against the earlier live generation; otherwise only with `--deviation "<justification containing [deviation]>"`, recorded in the attempt log, the run record and the technical §7 · Alternativas: never re-run after E1 started; re-run freely before the seal · Degrau (C): 1 (ADR 7.1.0003 item 3: forcing needs a justification citing the diagnosis record) and 4 (most conservative that still lets an infrastructure crash be retried)
Base: domain doc reproduction §4.2 R-BIT (same code + same environment ⇒ same result, so a re-run with the same code, environment and input cannot choose a different result) and R-BIT-COMMIT (the code diff, not the commit id, decides); §4.6 (deviation reported)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] 8.1-R3 — cross truth outside the data root
Escolha: the committed `config/preregistration/<name>-r<rev>.judged.toml` is authoritative: G4 refuses if a record names another revision of the plan, or names this one and the sealed copy is missing or its generation_digest differs · Alternativas: data root only; sign the copy · Degrau (C): 1 (ADR 6.5.0003 items 1–2: anchors by committed record + tag + comment) and 5
Base: ADR 6.5.0003; git history is outside the git-ignored data root
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

1. **Attempt log (write-ahead).** The `JudgedGenerationStore` gains
   `record_attempt(partition, attempt)` and `attempts(partition)` and
   `judged_refs(partition)`. The log lives in the partition
   (`judged/ATTEMPTS.jsonl`, append-only, one JSON object per line, written by
   temporary file + `os.replace` of the whole file). The use case appends an
   entry — `preregistration_ref`, `commit`, `code.src`, `code.uv_lock`, the
   R-BIT environment keys (image id, platform, CPU capability, library
   versions), `started_at` (from the `Clock`), `deviation` (text or null), and
   the `silver_content` and `prior_live_result_digest` of the live generation
   of this revision if one exists (read through the existing
   `GoldGenerationReader.read_generation`; no new store method; both null
   otherwise) — **after G1–G3 and before E1**; after E1 it appends a second
   line, `input_read`, with the `silver_content` and `dataset_fingerprint` the
   refresh read and the `result_digest` of the generation it published. The
   **result layer** is every table by value plus `manifest.as_mapping()`
   **without** the `started_at`/`finished_at` keys (dropped, never replaced by
   another instant); its sha256 is integrity for comparing attempts, like the
   copy's sha256 (ADR 7.1.0004), not a call to the `Hasher` port. The run record lists every
   entry of the partition. One port: splitting the attempt log from the judged
   store would not change behavior (same adapter, same layout owner).
2. **G4, in this order, all before any effect:**
   a. committed records (`PreregistrationSource.judged_records(name)`, a new
      read of `config/preregistration/<name>-r*.judged.toml`): another
      revision named → `JudgedGenerationExistsError`; this revision named and
      no sealed copy, or a different `generation_digest` →
      `JudgedGenerationTamperedError`;
   b. sealed copies (`judged_refs`): another revision → `JudgedGenerationExistsError`;
      this revision → `find` (digest check) → `ALREADY_JUDGED` or
      `JudgedGenerationTamperedError`;
   c. attempts of another revision → `JudgedGenerationExistsError`;
   d. live generation: `current/MANIFEST.json` with another
      `preregistration_ref` → `JudgedGenerationExistsError`; with this ref and
      no attempt entry of this ref → `JudgedGenerationTamperedError` (an
      unrecorded refresh);
   e. the **segment** of this revision's log starts at the last `started`
      line with a deviation whose attempt reached its `input_read` line (the
      whole log if there is none). Without `command.deviation`: a `started`
      line of the segment with other `code.*` → `PriorAttemptCodeChangedError`,
      or other `env.*` (image id, platform, CPU capability, library versions) →
      `PriorAttemptEnvironmentChangedError`; and the **references** already
      disagree → `PriorAttemptInputChangedError` (two inputs) or
      `PriorAttemptDivergenceError` (two result digests: a recorded
      divergence, after which only `--deviation` re-runs). A `deviation` must
      contain `[deviation]` (checked) and is recorded in the attempt line.
2b. **References and the check after E1, before E2.** The references of the
   segment are (1) every `input_read` line (input and result digest); (2)
   every non-null `prior_live_result_digest` of its `started` lines **except
   the first** — the witness of what an earlier attempt published, also when
   it died between the publish and its `input_read` line (the first line,
   opening the segment with a deviation, holds the generation before the
   deviation); and (3) the live generation at G4 (its result digest and its
   manifest's input). The result digest covers the input, since the manifest
   without its instants holds `silver_content` and `dataset_fingerprint`. The
   `input_read` line of the new attempt is written first, so a refusal still
   records it. Then, without `command.deviation`, a new input different from
   any reference's input → `PriorAttemptInputChangedError`, and a new result
   digest different from any reference's → `PriorAttemptDivergenceError`: an
   R-BIT failure, which the domain doc §4.2 makes a stop for diagnosis
   (`[finding]`), never a switch. In both, nothing is sealed. The run record
   of the run that seals keeps `deviation = null` when that run carries no
   `--deviation`, even if its segment opened with one; the deviation stays
   in the attempt lines the run record lists.
2c. **Recovery of a tampered or lost judged copy** has no code path: a
   `[deviation]` is committed, the sealed backup of `judged/<ref>/` (ADR
   8.1.0003 item 6c) is restored and checked by `sha256sum -c`, and G4 then
   passes because the digest matches the committed record.
3. **Durable source = git; residual (declared).** Before **each** real
   `evaluate`, the runbook commits in the technical §7 the attempt's intention
   (commit, `code.src`, image id, platform, CPU capability, time); no new code
   mechanism. Residual: deleting `gold/` or restoring the data-root backup
   erases the local attempt log; editing `current/` by hand without deleting
   `gold/` can make the live reference and the log agree on a result no
   attempt produced (when the edit also rewrites the log, or when no
   `input_read` of the segment exists to contradict it). Neither erases the
   committed intentions, so an attempt is never invisible to a reviewer of the
   repository; the code does not harden against a hand edit of the data root
   (decision C, Checkpoint C 8.1 re-verification round 2).
4. **No code path deletes** the attempt log, a sealed copy or a `.judged.toml`.

### Amendment history

- **2026-10-23, Checkpoint C 8.1 block 5 (CC5-1..3).** The first version compared the
  new generation with the live one, neutralizing the instants by copying the
  generation's own `started_at`. Every legitimate re-run then diverged, and after one
  divergence the replaced `current/` became the reference. Replaced by the result
  digest in the `input_read` line and the segment since the last deviation.
- **2026-10-23, Checkpoint C 8.1 final block (CC6-1, CC6-2).** A crash between the
  publish and the `input_read` line left no reference, and a deviation attempt that died
  before its input reset the segment. Fixed by the `prior_live_result_digest` witness
  and the segment rule of item 2e.
- **2026-10-23, re-verification round 2.** Items 1, 2e, 2b and 3 rewritten in one text.
  The references are the `input_read` lines, the witnesses of the `started` lines but the
  first, and the live generation. A hand edit of `current/` is declared in the residual
  of item 3.

## Alternatives considered

### Alternative A — "Judged" starts at the seal (ADR 8.1.0001 as first written)
- **Cons:** the window E1→E3 allows re-judging with numbers on disk.
- **Why rejected:** numbers exist from E1 (8.1-R1).

### Alternative B — Never re-run after E1 started
- **Pros:** strongest.
- **Cons:** an out-of-memory or power loss during the refresh would end the
  study with no judgment although a same-code, same-environment, same-input re-run reproduces the result
  bit for bit (R-BIT).
- **Why rejected:** R-BIT makes same-code, same-environment, same-input re-runs result-neutral (and the result is checked); code, environment or input
  changes still need a deviation.

### Alternative C — Data root as the only truth
- **Cons:** git-ignored; deletable or restorable without trace.
- **Why rejected:** the committed record exists anyway (ADR 8.1.0003) and
  costs one read.

### Alternative D — Cryptographic signature of the copy
- **Cons:** key management for a single-operator study; the committed digest
  plus the issue comment already give an external reference.
- **Why rejected:** disproportionate.

### Alternative E — Do nothing
Leaves DT-1/DT-2: re-judgment without trace.

## Consequences

### Positive
- "One judgment per partition" holds against crashes, new revisions, code
  changes and a lost or restored data root, up to the declared residual.

### Negative
- One more port method family and one more source read; a `--deviation`
  path in the CLI.

### Neutral / trade-offs accepted
- A re-run after a crash with the same code, environment and input is allowed and leaves its attempts on
  record; the dossier lists them.

## References

- Related ADRs: [6.5.0003](./6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md),
  [7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md),
  [8.1.0001](./8_1_0001-confirmatory-run-orchestration-guards-status-replay.md),
  [8.1.0003](./8_1_0003-judged-generation-preserved-copy-run-record-attestation.md)
- Domain: `docs/domain/evaluation/reproduction-equivalence-and-reporting.md` §4.2, §4.6
- Issue: #211; Checkpoint A round 1 (DT-1, DT-2, CA-1, CA-2, CA-3)
