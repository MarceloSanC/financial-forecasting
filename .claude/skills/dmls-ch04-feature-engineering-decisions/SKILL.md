---
name: dmls-ch04-feature-engineering-decisions
description: Use this skill whenever the user is making feature engineering decisions for a production ML model — specifically when they are (a) handling missing values in features (deletion vs. imputation, diagnosing MNAR/MAR/MCAR, deciding whether missingness itself is signal), (b) transforming raw features for a model (scaling, normalization, log transforms, discretization, categorical encoding including the hashing trick for unbounded categories, feature crossing for non-linear interactions, or positional embeddings), (c) detecting or preventing data leakage (random splits on time-correlated data, scaling before splitting, group leakage, leakage from data collection processes), or (d) evaluating whether a feature should stay in the model (feature importance via SHAP or ablation, generalization via coverage and value-distribution overlap, pruning decisions). Also trigger on direct questions about SHAP, feature importance, the hashing trick, feature crossing, train-test split timing, RoPE / position embeddings, feature stores, or any mention of Chip Huyen's *Designing Machine Learning Systems* book. Lean toward triggering — feature engineering decisions come up in almost every production ML conversation, and getting them wrong (especially around leakage) causes some of the most expensive failures.
metadata:
  status: draft
---

# DMLS Ch. 4 — Feature Engineering Decisions

This skill supports **four decisions** when turning raw data into features for a production ML model. It is not a summary to read — it is a job aid for making feature engineering decisions, with a particular focus on data leakage prevention.

## Reference doc

Full content: `references/chapter-content.md`

Always read the reference before answering. It is organized task-by-task, with decision tables, checklists, and questions to surface to the user.

## Role in the skill library (hybrid architecture)

This is a **per-chapter skill** — it owns Chapter 4's content. After all 12 chapters are processed, **topic-scope "spine" skills** will sit on top (e.g., *designing the data strategy*, *model development and evaluation*). Those spine skills will deep-link into this chapter's tasks when relevant.

Implications for this skill:
- Stay chapter-scoped. Defer to other chapters' skills for data infrastructure (Ch. 2), training data strategy (Ch. 3), model selection and training (Ch. 5), deployment (Ch. 6/7), monitoring (Ch. 7), continual learning (Ch. 8), infrastructure including feature stores (Ch. 9).
- Task anchors (e.g., `Task 3: Detect and Prevent Data Leakage`) are stable and may be deep-linked. Preserve them if editing.
- Appendix B is the integration point — update it as later chapters reveal refinements.

## The four tasks this skill supports

Route to the reference task that matches the work the user is doing:

| If the user is… | Go to reference task | Use it to… |
|-----------------|---------------------|-----------|
| Dealing with missing values; deciding deletion vs. imputation; figuring out whether missingness itself is signal | **Task 1: Handle Missing Values** | Diagnose MNAR/MAR/MCAR first, then choose deletion, imputation, or signal-preservation. Watch for valid-value-collision and imputation-then-leakage pitfalls. |
| Choosing a transformation for a raw feature (scaling, log transform, discretization, encoding, crossing, position embeddings) | **Task 2: Transform Raw Features Into Model-Ready Features** | Walk the operation catalog. Especially: use the hashing trick for unbounded/evolving categories rather than UNKNOWN buckets. |
| Worried about leakage; saw suspiciously good test performance; debugging a model that worked in dev but failed in prod | **Task 3: Detect and Prevent Data Leakage** | Walk the six causes (time-correlated random splits, scaling before splitting, missing-value imputation across full data, duplicates, group leakage, collection-process leakage). Apply detection (correlation analysis, ablation, new-feature scrutiny). |
| Reviewing a model's feature set; deciding which features to add or remove; doing a feature audit | **Task 4: Evaluate Whether a Feature Should Stay in the Model** | Measure importance (SHAP, ablation), check generalization (coverage, value-distribution overlap), apply the keep-or-prune decision procedure. Remember the Pareto pattern — top features carry most of the weight. |

Multiple tasks may apply to one conversation. Adding a new feature usually spans Task 2 (transformation) → Task 3 (leakage check) → Task 4 (importance/generalization evaluation).

## How to use the reference

1. **Identify the task** from the table above. Name it before answering.
2. **Read the relevant task section.** Decision tables and checklists are the value — preserve their structure in answers.
3. **For Task 1, always ask about missingness type before recommending a fix.** Don't default to mean imputation without diagnosing.
4. **For Task 3, treat leakage with high suspicion by default.** A user mentioning "test performance dropped in production" should immediately route here.
5. **Surface checklists literally** — they're more useful as questions to the user than as guesses.
6. **Cite benchmarks (Booking.com 50% collision, Facebook top-10 importance, CIFAR duplicates) as illustrative**, not as current numbers.

## Style of advice

- **Task-first, technique-second.** "You're doing a feature audit — Task 4's decision procedure walks importance + generalization + cost" rather than "Let me describe SHAP."
- **Tables and checklists over prose.** This chapter has many decision tables; reproduce them rather than paraphrasing.
- **Push back on the "more features is better" instinct.** This is the chapter's sharpest practical point and a common real-world mistake. Bring up the costs (leakage risk, overfitting, latency, technical debt) when someone wants to add features without auditing existing ones.
- **Push back on assuming MCAR.** When a user describes missing values, ask why they're missing before recommending mean imputation. MCAR is rare in real data.
- **Push back on random splits for time-correlated data.** This is the most common leakage cause and it's almost always preventable.
- **Mention feature stores when relevant.** The chapter doesn't cover them but they're important post-book context for production feature engineering. Appendix A explains.
- **Mention the LLM-era position embedding update (RoPE, ALiBi) when the user is choosing position embeddings.** The chapter's BERT-era guidance is dated for current LLM work.

## Caveats on dated content

The chapter's *techniques* age well; some *examples* and *tools* are 2021-era. Notable updates flagged in Appendix A:
- Position embeddings: BERT-era is dated; modern LLMs use RoPE/ALiBi
- "Most ML isn't deep learning" — partially true in 2026; depends on domain
- Vowpal Wabbit — less prominent in 2026; technique is more widespread than ever
- Feature stores — not covered in the chapter but central to modern production feature engineering

## What this skill is NOT for

- Where data comes from; data infrastructure → Chapter 2
- Sampling, labeling, or class imbalance → Chapter 3
- Model selection, training, evaluation → Chapter 5
- Deployment patterns → Chapter 6
- Monitoring and distribution shift → Chapter 7
- Continual learning → Chapter 8
- Feature stores as infrastructure (vs. feature engineering as practice) → Chapter 9

If the user's question is clearly in one of those domains, say so and suggest the relevant chapter's skill.
