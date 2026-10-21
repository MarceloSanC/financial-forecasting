---
title: ADR 7.3.0004 — Training device as a property of the trainer instance (cpu unchanged), torch build declared in the ablation spec and checked, ROCm torch installed by an environment override on Linux
description: Architecture Decision Record
when-use: Reference when asking how a cohort runs on GPU, why the confirmatory and 7.1 paths stay CPU, where the device and torch build are declared and checked, or how the ROCm torch is installed without changing uv.lock
keywords: [adr, device, gpu, rocm, accelerator, lightning, torch-build, probe, composition-root, reproduction, uv, index, modeling]
status: accepted
created_at: 2026-10-18
updated_at: 2026-10-18
adr_id: 7.3.0004
decision: The device becomes a constructor parameter of PfTftTrainer (accelerator used by fit, emission and checkpoint prediction; default "cpu"); the composition root maps a declared device to an accelerator ({"cpu": "cpu", "rocm": "gpu"}) and builds one trainer per device, keeping the confirmatory cohort, the 7.1 inference and the attribution on "cpu"; the ablation spec declares device and torch_build, both in its hash, and RunAblationCohort refuses a probe whose torch version or device differs; on Linux the ROCm torch is installed over the locked environment (uv sync --frozen, then the ROCm wheel, then uv run --no-sync), without touching pyproject.toml or uv.lock.
context_stage: 7.3-explainability
bounded_context: inference
---

# ADR 7.3.0004 — Device per trainer instance, torch build declared

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.3 concept (issue #186), 2026-10-18. Closes item 4 of the
research findings of the issue; settles the ROCm install path that ADR
5.4.0003 left open ("override the index in that environment or ... Alternative
B").

## Context

- `composition_root.py` L342–344: `_TRAINERS_DEVICE = "cpu"`, passed as
  `supported_device` to the cohort runner, the checkpoint resolver and the
  predictor; `check_cohort_declarations` refuses a spec whose `device` differs.
- `pf_tft_trainer.py` fixes `accelerator="cpu"` in `fit` (L707–711) and in the
  `trainer_kwargs` of `_emit` (L512–518); `predict_from_checkpoint` reports
  `"accelerator": "cpu"` in its settings.
- The 7.1 reproduction (ADR 7.1.0003) is strict on CPU; 60 runs reproduced with
  max |Δ| = 0. Nothing in it may change.
- P-ABLACAO: the ablation runs on GPU (RX 7700 XT, ROCm, Linux); device and
  torch build enter the ablation cohort hash; the full model is retrained in
  the same environment.
- The probe (`git_runtime_environment_probe.py`) records library versions
  (the torch version string carries the local build tag, e.g. `+cpu`), the
  declared device and the code identity; a dirty `uv.lock` is refused.
- `TftTrainingParams` is inside the confirmatory cohort hash and the
  `config_signature`; a new field there would change both.

## Decision

`[decision:C] 7.3-DEVICE — how the device is parametrized`
`Escolha: accelerator as a PfTftTrainer constructor parameter, one trainer per declared device built in the composition root; torch_build declared and checked; ROCm wheel installed over the frozen environment · Alternativas: device inside TftTrainingParams; a per-call device argument on the ports; uv conflicting extras cpu/rocm (ADR 5.4.0003 Alt. B) · Degrau: 1 (7.1 reproduction untouched; ADR 5.5.0001 hash of the declaration) e 5`
`Sensibilidade pré-registrada: nenhuma · Reversível: sim`

1. `PfTftTrainer(accelerator: str = "cpu")`; `fit`, `_emit` and both checkpoint
   prediction methods use the instance's accelerator, and the settings report
   it. The CPU instance behaves exactly as today (all 5.4/7.1 tests unchanged).
2. Composition root: `_SUPPORTED_DEVICES = {"cpu": "cpu", "rocm": "gpu"}`
   (declared device → Lightning accelerator) and a lazy trainer per device.
   `confirmatory_cohort_for`, `run_inference_for` and
   `permutation_inference_for` always use `"cpu"` (the confirmatory checkpoints
   are CPU artifacts and the identity is checked against the 7.1 silver);
   `ablation_cohort_for(path)` reads the device **from the ablation spec**
   itself — no device argument that could disagree with the hashed one. A device outside the map is refused before any
   import of torch.
3. `AblationCohortSpec.device` and `.torch_build` are in its hash.
   The probe's `device` key echoes the declared device (it is a constructor
   argument), so it proves nothing about the hardware. For `device ≠ "cpu"`
   the snapshot therefore gains **observed** keys — `torch.cuda.is_available()`,
   the GPU name and `torch.version.hip` — and `RunAblationCohort` refuses,
   before training, a snapshot where the GPU is not available, the HIP version
   is absent, or the `torch` version differs from `torch_build`. The base
   declarations go through `check_cohort_declarations` with the **base**
   device (`"cpu"`, so the base check is unchanged), and the ablation device is
   checked by this observed-hardware guard, which replaces, for the ablation,
   the guard of `run_confirmatory_cohort.py` L305–309 (a spec declaring
   "rocm" that runs on CPU). For `"cpu"` the snapshot is byte-identical to
   today's (the confirmatory ledger and the 7.1 manifests keep comparing).
4. **ROCm install on Linux (handoff):** `uv sync --frozen` (lock unchanged),
   then the ROCm wheel of torch from the PyTorch ROCm index into the same
   environment, then every command with `uv run --no-sync` (a plain `uv run`
   would resync to the CPU wheel). The installed version string is the
   `torch_build` written at freeze. `pyproject.toml` and `uv.lock` do not change,
   so `code.uv_lock` stays the committed one and CI is unaffected.
5. GPU training keeps `deterministic=True`. If an operation has no
   deterministic ROCm kernel, the pilot shows it; the fix is a `[decision]` in
   the technical §7 on Linux, before the freeze (never after training starts).

## Alternatives considered

### Alternative A — Device inside `TftTrainingParams`
- **Why rejected:** changes the confirmatory cohort hash and every
  `config_signature`/`run_id` (asdict of the params) — breaks 7.1.

### Alternative B — Device argument on each port call
- **Cons:** every caller (training, sweep, 7.1, attribution) must pass and
  validate it; the device is a property of the environment, not of a request.
- **Why rejected:** rung 5.

### Alternative C — uv conflicting extras `cpu`/`rocm` (ADR 5.4.0003 Alt. B)
- **Cons:** every install entry point (Dockerfile, devcontainer, CI, `make
  setup`) must choose an extra; a forgotten flag yields no torch (ADR 5.4.0003
  cons); the lock changes for a one-off environment.
- **Why rejected:** rung 5; the ablation environment is declared and checked
  through `torch_build`, which is what reproducibility needs.

### Alternative D — Keep CPU only
- **Why rejected:** ~95 h of CPU (measured, ADR 0.0.0007); the human decided GPU.

## Consequences

### Positive
- CPU paths byte-identical; the GPU path is a declared, hashed, checked
  environment.

### Negative
- The ROCm path is only exercised on Linux (the Windows Stage tests the
  mapping, the refusals and the CPU instance); a GPU smoke test is skipped
  without a GPU.

### Neutral / trade-offs accepted
- The Linux environment is reproduced by the handoff steps and the recorded
  `torch_build`, not by the lock.

## References

- Related ADRs: [5.4.0003](./5_4_0003-torch-core-dependency-cpu-index.md),
  [5.5.0001](./5_5_0001-frozen-hashed-cohort-spec.md),
  [7.1.0003](./7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md),
  [7.3.0003](./7_3_0003-ablation-cohort-spec-by-reference-identity-per-configuration.md).
- Issue: [#186](https://github.com/MarceloSanC/financial-forecasting/issues/186).
