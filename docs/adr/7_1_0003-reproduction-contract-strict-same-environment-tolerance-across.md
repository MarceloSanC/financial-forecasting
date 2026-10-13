---
title: ADR 7.1.0003 — Inference reproduction is checked against the test predictions already in silver, in memory, bit for bit when the runtime environment equals the reference one and within torch's float32 assert_close tolerance in the normalized space otherwise; threads and the deterministic flag are pinned to the trainer's; a run that fails emits no calib
description: Architecture Decision Record
when-use: Reference when deciding whether a re-inference "reproduces", which environment keys switch the criterion, what tolerance applies across environments and in which units, why the test block is not re-persisted, or what to do when strict equality fails on an apparently identical machine
keywords: [adr, inference, reproducibility, bitwise, tolerance, assert-close, float32, normalized-space, normalizer-scale, environment, torch-threads, deterministic-algorithms, cpu-capability, batch-size, num-workers, dropout, mc-dropout, sandve]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
adr_id: 7.1.0003
decision: For every (fold, seed) run, the use case re-predicts the test block from the checkpoint with the trainer's batch size, `num_workers=0`, CPU, the cohort's recorded thread count and `use_deterministic_algorithms(False)`, and compares it in memory with the run's `value_raw` test rows over the identical key set, in float64 over float32-representable values; the criterion is exact equality when the reference environment equals the current one on every non-code key (reference = the cohort's recorded environment for test, the environment of the first calib write for existing calib rows) and no justified `--cross-environment` was given, and otherwise |Δ|/s ≤ 1e-5 + 1.3e-6·|(ref − c)/s| with c, s the checkpoint's target-normalizer center and scale (torch.testing.assert_close float32 defaults applied where the network computes); any failure raises before the run's calib is written; a strict failure with equal non-code keys is a stop for diagnosis, never a reason to switch to tolerance.
context_stage: 7.1-inference-engine
bounded_context: inference
---

# ADR 7.1.0003 — Reproduction contract: strict in the same environment, declared tolerance across

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The DoD of 7.1 (as corrected by the Step 7 domain gate) is: bit for bit in the
same pinned environment (torch build, OS/CPU, fixed and recorded inference
batch, no workers) and within a declared tolerance across environments; dropout
off, no MC dropout. The domain doc settles the theory (inference §3.1, A1
evidence and A1-TOL convention; §3.2, A2) and leaves to 7.1 the concrete batch,
threads and tolerance, and the reference. Facts:

- The trainer emitted each run's test grid **from the checkpoint reloaded**,
  `batch_size = params.batch_size` (111 in the cohort), `num_workers=0`, CPU,
  the process-default thread count (recorded as `torch_threads = 6`) and
  `use_deterministic_algorithms` back to its process default `False` after
  `fit` (`pf_tft_trainer.py`). Those predictions are in silver as `value_raw`
  (float64 from float32 — exact round trip).
- The cohort recorded its runtime environment at its first run
  (`progress.json`). The current image reports the same library versions,
  6 threads and `x86_64/12` (read 2026-10-06, versions only).
- Re-writing `split = "test"` for the same `run_id` collides with the PK.
- The network computes in float32 on the **normalized** target: the target
  normalizer is a linear `GroupNormalizer` (ADR 5.4.0006; `transformation=None`,
  checked on the pinned image), so `y = center + scale·z`, with `scale` ≈ the
  standard deviation of daily returns (O(1e-2)). An absolute tolerance of 1e-5
  in return units would be ~1e-3 of a standard deviation — two to three orders
  above float32 rounding at that scale (Checkpoint A round 1, A-D3).
- The probe's `cpu` key is `machine/cpu_count`, not the CPU model or the ISA
  level torch dispatches to; `torch.backends.cpu.get_cpu_capability()` reports
  the latter (`AVX2` on the current image).
- Domain doc §3.1 records two open gaps: determinism across processes on the
  same machine and the effect of intra-op threads.

## Decision

1. **Reference = the run's test rows in silver**, compared in memory on the key
   `(decision_idx, horizon, quantile_level)` over `value_raw`, in float64 over
   values that are float32-representable. Key sets must be identical.
2. **Inference parameters fixed by construction:** batch size = the frozen
   cohort's `tft_params.batch_size`; `num_workers = 0`; `accelerator = "cpu"`,
   one device; eval mode (Lightning's predict loop); no stochastic passes;
   `torch.set_num_threads(<cohort torch_threads>)` and
   `torch.use_deterministic_algorithms(False)` for the duration of the
   prediction, both restored afterwards. Recorded per run (ADR 7.1.0004): those
   values, `get_cpu_capability()`, the platform string, the scikit-learn version
   and the checkpoint's `normalizer_center`/`normalizer_scale`.
3. **Mode selection:** `strict` iff the reference environment exists and equals
   the current snapshot on every key except the code keys and no
   `--cross-environment` was given. The code keys are **imported, never
   redeclared**: `CODE_KEYS` and `DIRTY_KEY` (and the new `THREADS_KEY`) of
   `modeling/application/ports/out/runtime_environment_probe.py`, a data edge
   declared in `bc-independence` (today `code.src`, `code.uv_lock`,
   `code.cohort_file`, `code_dirty`). Reference for the test check = the cohort's
   recorded environment; reference for existing calib rows = the environment of
   that run's first calib write (manifest). Otherwise `tolerance`.
   `--cross-environment` only changes anything when the non-code keys are
   equal (with a differing key the mode is already `tolerance`). Its **only
   legitimate use** is a numeric difference that was diagnosed and that the
   keys do not capture (e.g., CPU capability): the justification must cite the
   `[finding]` of that diagnosis (checked: contains `[finding]`), the manifest
   records `forced = true` and the justification, and it applies to both
   checks.
4. **Criteria:** `strict` → `new == ref` for every value. `tolerance` →
   `|new − ref| / s ≤ atol + rtol·|ref − c| / s`, with `c`, `s` the
   `normalizer_center`/`normalizer_scale` of the run's checkpoint (i.e. the
   `assert_close` rule applied to `z = (y − c)/s`), `rtol = 1.3e-6`, `atol = 1e-5` (float32 defaults of
   `torch.testing.assert_close`, torch 2.13.0 `torch/testing/_comparison.py`
   L82–86, L1373–1377, L1465). Dividing by `s` maps the comparison back to the
   space where the float32 arithmetic happens, where the defaults have the
   scale they were set for. Non-finite values cannot occur (C5 of 5.4).
5. **Failure is blocking:** `ReproductionError` (run_id, mode, offending count,
   max |Δ|, max |Δ|/s) before any calib row of the run. Max |Δ| and max |Δ|/s
   are recorded for passing runs too (0.0 in strict).
6. **Strict failure with equal non-code keys is a stop, not a switch.** It
   means something the keys do not capture (CPU capability, a kernel, a code
   path) changed the numbers; it is recorded as a `[finding]` and diagnosed
   before any calib is written. Only after that diagnosis may
   `--cross-environment` be used, citing the `[finding]` (item 3); the Stage
   7.1 real run's acceptance requires strict with max |Δ| = 0 on all 60 runs.
7. **Determinism of the predictor is tested where the artifact is born:** at the
   adapter level, `predict_from_checkpoint` reproduces the `train_and_predict`
   test grid exactly in the same process, in a separate subprocess (closes the
   "across processes" gap before the real run), and under two different global
   RNG states (A2: the seed is irrelevant and dropout is off — a dropout-on
   mutation breaks it). MC dropout has no code path.

## Alternatives considered

### Alternative A — Tolerance always (no strict mode)
- **Why rejected:** contradicts the DoD and A1; a tolerance hides a
  reconstruction bug (e.g., a re-fitted scaler) whose effect is below it.

### Alternative B — Strict always
- **Why rejected:** "Completely reproducible results are not guaranteed across
  PyTorch releases, individual commits, or different platforms" (PyTorch notes,
  randomness); contradicts A1-TOL.

### Alternative C — Re-execute the artifact twice and compare runs (no silver)
- **Cons:** proves only self-consistency of today's code; a deterministic but
  wrong reconstruction passes.
- **Why rejected as the operational check:** kept as an adapter test (item 7).

### Alternative D — Re-persist the test block under a new label
- **Why rejected:** PK collision under `split = "test"`; a second copy of the
  same predictions with no consumer.

### Alternative E — The float32 defaults in return units (first draft)
- **Cons:** at `s` ≈ 1e-2 the `atol` 1e-5 accepts differences ~1e-3 of a
  standard deviation, far above float32 rounding of the network's outputs.
- **Why rejected:** wrong scale (A-D3).

### Alternative F — `atol = 0` and `rtol = k·eps(float32)` in return units
- **Pros:** scale-free.
- **Cons:** relative error is unbounded for quantiles near zero (the median of
  daily returns is ≈ 0), where a harmless difference of a few ulps of `s` would
  fail; choosing `k` has no source.
- **Why rejected:** the normalized space gives a documented pair and a stable
  denominator.

### Alternative G — Record threads and the deterministic flag without pinning (first draft)
- **Cons:** a process whose defaults differ from the trainer's would run a
  different reduction order while every key looks equal.
- **Why rejected:** pinning to the trainer's values costs two calls and removes
  the gap (A-C10/A-D10).

### Alternative H — Allow `--cross-environment` to rescue an undiagnosed strict failure
- **Why rejected:** it would turn an unexplained numeric difference into
  accepted evidence; item 6. Allowed only after a recorded diagnosis (item 3).

## Consequences

### Positive
- The calib rows are certified to come from the same numerical function that
  produced the test rows the confirmatory evaluation reads.
- The criterion is objective, scale-aware and decided before any run; the
  record makes it auditable (Sandve et al. 2013, Rule 1).

### Negative
- A host with an equal key set but a different CPU capability may fail strict
  and stop the Stage until diagnosed.
- A scikit-learn change is not an environment key, so it stays in strict and
  fails loudly if it alters the unpickled scalers (its version is recorded).

### Neutral / trade-offs accepted
- The reproduction reads predictions only (no realized target, no score): it is
  not a confirmatory metric (evaluation §8.2; domain doc inference §7).

## References

- Domain doc [inference](../domain/inference/conformal-benchmark-and-feature-attribution.md)
  §3.1–§3.2, §10.1 (A1, A1-TOL, A2).
- Related ADRs: [7.1.0001](./7_1_0001-checkpoint-prediction-supplied-by-modeling-through-consumer-port.md),
  [7.1.0002](./7_1_0002-calib-predictions-in-fact-oos-predictions-idempotent-completion.md),
  [7.1.0004](./7_1_0004-checkpoint-resolution-before-load-and-write-ahead-inference-manifest.md),
  [5.4.0006](./5_4_0006-explicit-train-fitted-target-normalizer.md),
  [5.5.0003](./5_5_0003-resumable-cohort-units-atomic-ledger.md).
- External: PyTorch v2.13.0 `notes/randomness.md`, `notes/numerical_accuracy.md`;
  `torch.testing.assert_close` (torch 2.13.0, verified by a zero-context
  verifier on 2026-10-06: sustains); Sandve, Nekrutenko, Taylor & Hovig (2013),
  PLoS Comput Biol 9(10):e1003285, Rule 1.
- Conversation/issue: [#153](https://github.com/MarceloSanC/financial-forecasting/issues/153);
  Checkpoint A round 1 (A-D3, A-D4, A-C10/A-D10).

## Decision record (evidence-resolution)

```
[decision:E] R1 — bit for bit in the same environment, against the trainer's test rows
Escolha: strict when environment keys (non-code) are equal; threads and deterministic flag pinned to the trainer's · Alternativas: tolerance always; self-consistency only
Base: domain doc inference §3.1 A1 (PyTorch notes v2.13.0 randomness/numerical_accuracy; torch.use_deterministic_algorithms docstring "same software and hardware"); pf_tft_trainer.py (trainer predicts from the reloaded checkpoint, batch = params.batch_size, num_workers=0, CPU)
Verificado: não verificado (§4.2) — inherited from the domain gate; the code fact was read in this session
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] R2 — tolerance across environments, in the normalized space
Escolha: |Δ|/s ≤ 1e-5 + 1.3e-6·|(ref − c)/s|, c, s = target-normalizer center and scale · Alternativas: same pair in return units; atol 0 with rtol k·eps; numpy allclose defaults · Degrau: 2
Base: torch 2.13.0 torch/testing/_comparison.py L82–86 "torch.float32: (1.3e-6, 1e-5)"; L1373–1377 "considered close if |actual − expected| ≤ atol + rtol · |expected|"; GroupNormalizer(transformation=None) is affine, so the network's float32 output lives in z = (y − center)/scale
Verificado: sustenta (zero-context verifier, 2026-10-06; notes: formula for finite real values; max of both pairs on dtype mismatch)
Sensibilidade pré-registrada: nenhuma · Reversível: sim
```
