---
name: dmls-ch05-model-development-and-evaluation
description: Use this skill whenever the user is making decisions about model development or pre-deployment evaluation — specifically when they are (a) framing an ML problem (translating a business request into inputs/outputs/objective function, picking task type, deciding multiclass vs. multilabel, or decoupling multiple objectives), (b) selecting models or comparing architectures (the simple-first principle, avoiding the SOTA trap, fair comparisons, learning curves, model assumptions, deciding whether to ensemble and which type — bagging, boosting, or stacking), (c) establishing model development practices (experiment tracking, versioning code/data/artifacts, debugging discipline, distributed training when scale demands it), (d) tuning hyperparameters or considering AutoML approaches (random search, Bayesian optimization, Keras Tuner, Optuna, NAS, learned optimizers), or (e) evaluating a model before deployment (setting baselines, perturbation tests, invariance tests, directional expectation tests, calibration, confidence measurement, slice-based evaluation including Simpson's paradox awareness). Also trigger on direct questions about ensembles, F1 vs. accuracy, hyperparameter tuning, model debugging, "overfit a single batch", random seeds, learning curves, model fairness testing, calibration curves, or any mention of Chip Huyen's *Designing Machine Learning Systems* book. Lean toward triggering — model development and evaluation decisions span almost every ML conversation.
metadata:
  status: draft
---

# DMLS Ch. 5 — Model Development and Evaluation

This skill supports **five decisions** when developing, training, and evaluating ML models before deployment. It is not a summary to read — it is a job aid for making model-development decisions, with particular emphasis on framing problems correctly and evaluating models thoroughly before shipping.

## Reference doc

Full content: `references/chapter-content.md`

Always read the reference before answering. It is organized task-by-task, with decision tables, checklists, and questions to surface to the user.

## Role in the skill library (hybrid architecture)

This is a **per-chapter skill** — it owns Chapter 5's content. After all 12 chapters are processed, **topic-scope "spine" skills** will sit on top (e.g., *model development and evaluation*, *scoping and planning an ML project*, *operating in production*). Those spine skills will deep-link into this chapter's tasks when relevant.

Implications for this skill:
- Stay chapter-scoped. Defer to other chapters' skills for production fundamentals (Ch. 1), data infrastructure (Ch. 2), training data (Ch. 3), feature engineering (Ch. 4), deployment (Ch. 6/7), monitoring (Ch. 7), continual learning (Ch. 8), infrastructure (Ch. 9).
- Task anchors (e.g., `Task 5: Evaluate a Model Before Deployment`) are stable and may be deep-linked. Preserve them if editing.
- Appendix B is the integration point — update it as later chapters reveal refinements.

## The five tasks this skill supports

Route to the reference task that matches the work the user is doing:

| If the user is… | Go to reference task | Use it to… |
|-----------------|---------------------|-----------|
| Translating a business problem into ML; picking task type; struggling with multiple competing objectives | **Task 1: Frame an ML Problem** | Specify inputs/outputs/objective. Pick task type (binary, multiclass, multilabel). Reframe to avoid built-in failure modes. Decouple objectives when stakeholders conflict. |
| Comparing architectures; deciding whether to ensemble; debating SOTA vs. simple baselines | **Task 2: Select and Evaluate Models** | Apply the six tips for model selection. Compare under equivalent budgets. Use learning curves. Check assumptions. Decide on ensembling and pick the right type (bagging, boosting, stacking). |
| Setting up experiment tracking; debugging a model; making training reproducible; thinking about distributed training | **Task 3: Establish Model Development Practices** | Set up tracking and versioning. Apply the three debugging techniques (start simple, overfit a batch, set random seed). Walk the failure-cause checklist. Consider distributed training only when scale demands it. |
| Searching for the best hyperparameters; considering AutoML | **Task 4: Tune Models with AutoML** | Use soft AutoML (random search, Bayesian optimization) for hyperparameters. Don't tune on the test split. Reach for hard AutoML (NAS, learned optimizers) only with massive compute budgets — usually use pre-trained NAS outputs (EfficientNets) instead. |
| Validating a candidate model is ready for production; running fairness or robustness tests | **Task 5: Evaluate a Model Before Deployment** | Set baselines (random, heuristic, zero rule, human, existing solution). Run perturbation, invariance, directional expectation tests. Measure calibration. Set confidence thresholds. Slice the data and check per-subgroup performance. |

Multiple tasks may apply. A new ML project will typically hit Task 1 → Task 2 → Task 3 → Task 4 → Task 5 in sequence over the development lifecycle.

## How to use the reference

1. **Identify the task** from the table above. Name it before answering.
2. **Read the relevant task section.** Decision tables and checklists are the value — preserve them in answers.
3. **For Task 1, push hard on framing before solutions.** A poorly-framed ML problem is unsolvable regardless of architecture. Spend real time here.
4. **For Task 2, default to simple-first.** When the user wants to start with SOTA, ask whether they've tried logistic regression / XGBoost first.
5. **For Task 5, treat it as a gauntlet, not a checkbox.** Each evaluation type catches different failures. Don't deploy until all the relevant ones pass.
6. **Surface checklists literally** — they're more useful as questions to the user than as guesses.
7. **Cite benchmarks (Kaggle ensemble stats, GPT-3 batch size, Berkeley admissions) as illustrative**, not as current numbers.

## Style of advice

- **Task-first, technique-second.** "You're framing a multi-objective problem — Task 1 Step 1.5 has the decoupling pattern" rather than "Let me describe Pareto optimization."
- **Tables and checklists over prose.** This chapter has many decision tables; reproduce them rather than paraphrasing.
- **Push back on the SOTA trap.** When the user wants to use a fancy new model, ask what simpler solutions have been tried. SOTA on benchmarks ≠ best for the user's problem.
- **Push back on overall metrics without baselines.** If someone reports "F1 = 0.90," ask what random performance is. Without that comparison, the metric is decoration.
- **Push back on overall metrics without slicing.** Aggregate numbers can hide critical subgroup failures (Simpson's paradox is real, not theoretical).
- **For multi-objective problems, advocate for decoupling.** Combined-loss approaches require retraining to rebalance; decoupled models tune at serving time.
- **Mention foundation models when relevant.** The chapter doesn't address foundation models / LLMs as a model selection option, but by 2026 they're often the right starting point for NLP/vision/multimodal problems. Appendix A explains.
- **Treat distributed training as escalation.** Single-GPU first. Multi-GPU only when needed. Multi-machine only when single-node is exhausted. Pipeline parallelism only when model parallelism alone is too slow.

## Caveats on dated content

The chapter's *frameworks* age well; some *examples* and *tools* are 2021-era. Notable updates flagged in Appendix A:
- Foundation models / LLMs as a model selection option (post-book development)
- AutoML ecosystem matured (AutoGluon, cloud AutoML services, Optuna)
- Experiment tracking ecosystem expanded (MLflow, Neptune, Comet, ClearML beyond DVC and Weights & Biases)
- GPT-3 batch size of 3.2M is no longer the frontier
- Kaggle and SQuAD leaderboard specifics are dated; the broader patterns hold

## What this skill is NOT for

- Whether to use ML at all → Chapter 1
- Where data lives and flows → Chapter 2
- Sampling, labeling, class imbalance interventions → Chapter 3
- Feature transformations and leakage → Chapter 4
- Deployment patterns (online, batch, edge) → Chapter 6
- Monitoring and distribution shift → Chapter 7
- Continual learning → Chapter 8
- Infrastructure and resource management → Chapter 9

If the user's question is clearly in one of those domains, say so and suggest the relevant chapter's skill.
