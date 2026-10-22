---
title: ADR 8.1.0004 — One judgment per cohort partition enforced against unsealed attempts and a lost data root — write-ahead attempt log, live-generation check, the committed `.judged.toml` as cross truth, and re-execution only with the same code, environment and input or a registered deviation
description: Architecture Decision Record
when-use: Reference before re-running `evaluate` after an interrupted or failed run, before restoring or deleting a data root that holds gold, before anchoring a new revision of a plan already evaluated, or when asking what counts as "numbers already exist"
keywords: [adr, evaluation, confirmatory-run, re-judgment, forking-paths, attempt-log, write-ahead, deviation, judged-record, data-root, git-ignored, cross-check, replay]
status: accepted
created_at: 2026-10-22
updated_at: 2026-10-22
adr_id: 8.1.0004
decision: Numbers exist from the moment `RefreshGold` starts, not from the seal; so before E1 the use case appends an attempt entry (ref, commit, code.src, code.uv_lock, R-BIT environment keys, started_at, deviation text if any, silver_content of a prior live generation; after E1 a second line with the silver_content read) to a write-ahead attempt log of the partition, and G4 refuses — before any effect — when the partition has a sealed copy, an attempt or a live `current/` generation of another revision, when a committed `<name>-r*.judged.toml` names another revision or names this one without a sealed copy of the same digest, or when an earlier unsealed attempt of the same revision ran other code or another R-BIT environment and no `[deviation]` justification is given; after E1 a different input (silver_content, dataset fingerprint) than the earlier attempt's, or a result different from the earlier live generation with code, environment and input equal, stops with a `[finding]` and nothing is sealed; the durable source is git — the runbook commits each real attempt's intention in the technical §7 before running.
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
   the `silver_content` of the live generation of this revision if one exists
   (read through the existing `GoldGenerationReader.read_generation`; no new
   store method) — **after G1–G3 and before E1**; after E1 it appends a second
   line with the `silver_content` the refresh read. The run record lists every
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
   e. attempts of this revision with `code.src` or `code.uv_lock` different
      from the current snapshot → `PriorAttemptCodeChangedError`, or with
      another image id, platform, CPU capability or library versions →
      `PriorAttemptEnvironmentChangedError` — both unless `command.deviation`
      is given; a `deviation` must contain `[deviation]` (checked) and is
      recorded.
2b. **After E1, before E2.** (i) The `silver_content` and
   `dataset_fingerprint` of the new manifest differ from the last recorded
   input of an earlier attempt of this revision and no deviation →
   `PriorAttemptInputChangedError`; (ii) a live generation of this revision
   existed before E1 and the new one differs from it in the result layer
   (table rows by value; manifest without `started_at`/`finished_at`) while
   code, environment and input are equal → `PriorAttemptDivergenceError`: an
   R-BIT failure, which the domain doc §4.2 makes a stop for diagnosis
   (`[finding]`), never a switch. In both, nothing is sealed.
2c. **Recovery of a tampered or lost judged copy** has no code path: a
   `[deviation]` is committed, the sealed backup of `judged/<ref>/` (ADR
   8.1.0003 item 6c) is restored and checked by `sha256sum -c`, and G4 then
   passes because the digest matches the committed record.
3. **Durable source = git; residual (declared).** Before **each** real
   `evaluate`, the runbook commits in the technical §7 the attempt's intention
   (commit, `code.src`, image id, platform, CPU capability, time); no new code
   mechanism. Residual: deleting `gold/` or restoring the data-root backup
   erases the local attempt log, but not the committed intentions, so an
   attempt is never invisible to a reviewer of the repository.
4. **No code path deletes** the attempt log, a sealed copy or a `.judged.toml`.

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
