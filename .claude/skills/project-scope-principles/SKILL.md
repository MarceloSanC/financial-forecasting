---
name: project-scope-principles
description: >
  Scope guardrail for THIS project — steers technical decisions toward the ratified v0 objectives
  with anti-overengineering, reproducibility, and academic defensibility. Use when deciding whether
  a task/feature/metric/plot belongs to current scope, when weighing a simple robust path vs complex
  automation, or when defining what evidence a confirmatory analysis must persist. Triggers (PT/EN):
  "isso é escopo?", "precisa pra v0?", "vale a pena implementar", "tá complicando demais",
  "overengineering", "o que persistir", "dá pra simplificar", scope creep, is this in scope.
  Defers the actual scope contract to docs/overview.md and docs/roadmap.md.
metadata:
  status: accepted
  applies_when:
    step: [any]
    camada_alvo: [any]
---

# Project Scope Principles

Keep decisions pointed at the **ratified v0** of this project: characterize probabilistic
**calibration** (primary object) and **relative skill** of a TFT quantílico on daily AAPL returns,
under **clean, tool-enforced architecture and full traceability**. The project prioritizes
**modularity, clean architecture, and auditability above sophistication** — refutation is a valid
result, and the previous implementation died of architectural debt, not of missing features.

## Source of truth (do not duplicate it here)

The binding scope contract is in [`docs/overview.md`](../../../docs/overview.md) §3 (Dentro/Fora do
escopo, Premissas) and §4 (Objetivos, Hipóteses, Critérios de sucesso), and the inherited-constraints
block of [`docs/roadmap.md`](../../../docs/roadmap.md). When in doubt, **read those, not this skill.**
This skill is the *decision lens*; the docs are the *contract*. If they disagree, the docs win.

## Decision lens

When a request arrives, classify and filter before implementing:

1. **Classify by scope level.** v0-essential / recommended / post-v0. Anything matching
   `overview.md §3 "Fora do escopo"` (other assets, trading/backtesting, intraday, causal claims,
   reusing derived data/checkpoints) is **out** — name it and defer, don't quietly build it.
2. **Anti-overengineering filter.** Prefer the simple, robust, auditable path. Data completeness +
   reproducibility beat sophisticated orchestration. Don't add a layer/abstraction/automation that
   no current Stage DoD requires. Complexity must be paid for by a stated v0 need.
3. **Fairness for comparison.** Statistical comparison only on **aligned OOS intersection** (exact
   `target_timestamp`), consistent splits, same cohort, **per horizon** — never aggregated across
   horizons. (Enforcement detail lives in `model-performance-and-research-advisor`.)
4. **Prefer persisted, reconstructible evidence.** Decision artifacts must be rebuildable from
   persisted data **without retrain** (silver Parquet = source of truth; gold reconstructible). If a
   choice risks needing a retrain later because data wasn't persisted now, persist now.
5. **Interpretability minimum (when in scope).** Feature-family contribution via the declared methods
   (VSN / permutation / ablation), descriptive only — no causal claim.
6. **Escalate ambiguity, don't assume.** If a policy/scope-defining decision is genuinely unresolved,
   ask Marcelo with **2–4 concrete options, the recommended one first, each with a one-line
   trade-off** — instead of silently picking. (Reuse `AskUserQuestion`.) This applies only to real
   forks; for choices with an obvious default, pick it and say so.

## What this guards against

- Building post-v0 features (extra assets, trading, intraday, microstructure) because they're "easy".
- Adding orchestration/automation before the core persisted evidence path exists.
- Mixing heterogeneous cohorts or aggregating across horizons in a final comparison.
- Drawing conclusions without the statistical validity gates (calibration gate, DM/Holm, MCS).
- Ephemeral analysis that can't be reproduced from persisted artifacts.

## Done / well-scoped when

- The decision maps to a stated v0 objective or checklist priority (or is explicitly deferred with a
  reason and a pointer to where it belongs later).
- No architectural complexity was added that a current Stage DoD doesn't require.
- Required evidence for a reproducible, defensible analysis is persisted.
- Trade-offs are explicit and auditable.

## When NOT to use

- Pure coding tasks whose scope and acceptance criteria are already fixed by the Stage `technical.md`.
- Local refactors with no project-level trade-off.
