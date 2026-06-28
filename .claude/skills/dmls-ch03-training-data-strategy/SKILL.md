---
name: dmls-ch03-training-data-strategy
description: Use this skill whenever the user is making decisions about how to build training data for a production ML model — specifically when they are (a) choosing a sampling strategy for training/evaluation/monitoring (simple random, stratified, weighted, importance, or reservoir sampling for streams), (b) designing a labeling strategy when hand labels are limited (weak supervision, semi-supervision, transfer learning, active learning, or combinations), (c) running an annotation operation (handling label multiplicity, annotator disagreement, data lineage, quality control), (d) handling class imbalance (picking metrics that work for imbalance, then data-level or algorithm-level interventions), or (e) applying data augmentation (label-preserving transformations, perturbation/adversarial augmentation, or data synthesis). Also trigger on direct questions about Snorkel, labeling functions, SMOTE, focal loss, cost-sensitive learning, mixup, reservoir sampling, F1 vs. accuracy for imbalanced data, or any mention of Chip Huyen's *Designing Machine Learning Systems* book. Lean toward triggering — this skill adds structure to most conversations about preparing training data for production ML.
metadata:
  status: draft
---

# DMLS Ch. 3 — Training Data Strategy

This skill supports **five decisions** when building training data for a production ML model. It is not a summary to read — it is a job aid for making training-data decisions.

## Reference doc

Full content: `references/chapter-content.md`

Always read the reference before answering. It is organized task-by-task, with decision tables, checklists, and questions to surface to the user.

## Role in the skill library (hybrid architecture)

This is a **per-chapter skill** — it owns Chapter 3's content. After all 12 chapters are processed, **topic-scope "spine" skills** will sit on top (e.g., *designing the data strategy*, *model development and evaluation*). Those spine skills will deep-link into this chapter's tasks when relevant.

Implications for this skill:
- Stay chapter-scoped. Defer to other chapters' skills for data infrastructure (Ch. 2 — where data comes from), feature engineering (Ch. 4), model selection and training (Ch. 5), deployment (Ch. 6/7), continual learning (Ch. 8).
- Task anchors (e.g., `Task 4: Handle Class Imbalance`) are stable and may be deep-linked. Preserve them if editing.
- Appendix B (cross-chapter connections) is the integration point — update it as later chapters reveal refinements.

## The five tasks this skill supports

Route to the reference task that matches the work the user is doing:

| If the user is… | Go to reference task | Use it to… |
|-----------------|---------------------|-----------|
| Selecting samples from a population for training, evaluation, or monitoring; sampling from a stream | **Task 1: Choose a Sampling Strategy** | Walk through probability-based methods (simple random, stratified, weighted, importance, reservoir). Flag non-probability sampling bias risks. |
| Starting a supervised ML project with limited labels; planning the labeling approach; deciding between weak/semi/transfer/active | **Task 2: Design a Labeling Strategy When Hand Labels Are Limited** | Audit what's available, pick among the four approaches (often in combination). Apply the decision shortcut in order: natural labels → transfer learning → weak supervision → semi-supervision → active learning. |
| Running annotators; handling disagreements; setting up quality processes | **Task 3: Manage Labeling Quality and Multiplicity** | Write clear problem definitions, train annotators, measure inter-annotator agreement, track data lineage, resolve label multiplicity, handle privacy constraints. |
| Dealing with imbalanced classes (fraud, churn, disease, rare-event detection) | **Task 4: Handle Class Imbalance** | Fix metrics first (per-class accuracy, F1, precision-recall), then pick algorithm-level (focal loss, class-balanced loss, cost-sensitive) or data-level (resampling, SMOTE, two-phase) interventions. |
| Expanding training data or adding robustness via augmentation | **Task 5: Apply Data Augmentation** | Pick among label-preserving transformations (cheap expansion), perturbation (robustness to noise/adversarial), or data synthesis (templates, mixup, generative). |

Multiple tasks may apply. A user building a supervised classifier from scratch will usually hit Task 1 (sampling) → Task 2 (labeling strategy) → Task 3 (labeling operations) → Task 4 (imbalance) in sequence, with Task 5 (augmentation) added if data is limited or robustness is needed.

## How to use the reference

1. **Identify the task** from the table above. Name it before answering.
2. **Read the relevant task section.** Decision tables and checklists are the value — use them directly.
3. **Apply the decision procedures literally.** Each task has a decision order (e.g., Task 4: diagnose → metrics → consider no intervention → algorithm-level → data-level). Follow it rather than listing options.
4. **Surface questions-to-answer** to the user rather than guessing. The user has domain context you don't.
5. **Cite benchmarks as illustrative.** The 8-hour-LFs-vs-1-year-hand-labeling result is directional; don't treat the exact numbers as current.

## Style of advice

- **Task-first, technique-second.** Name what the user is doing, then introduce techniques. "You're handling class imbalance — first we fix metrics, then we pick interventions" rather than "Let me describe SMOTE and focal loss."
- **Tables and checklists over prose.** This chapter has many tables; preserve them when answering.
- **Push back on overall accuracy for imbalanced data.** This is the chapter's sharpest point and most common real-world mistake. Flag it proactively whenever imbalance comes up.
- **Don't skip the diagnostic step.** For imbalance especially: ask why the imbalance exists before fixing it. Sampling pipeline issues and labeling errors get "fixed" with resampling when they should be fixed at the source.
- **Combine approaches in Task 2.** The four labeling approaches aren't exclusive. Most real projects combine them (transfer learning base + weak supervision labels + active learning refinement).
- **LLM-era context for weak supervision.** Appendix A notes that using LLMs to generate/verify labels is now common and complements Snorkel-style LFs. Bring it up when someone's planning weak supervision from scratch in 2026.

## Caveats on dated content

Several data points are from 2017–2021 (Snorkel study, credit card fraud rate, GPT-3 training cost, one-pixel attack results). Directional claims hold; specific numbers may have moved. Appendix A flags every dated point. The most substantive post-book development is LLM-based labeling, noted in Appendix A.

## What this skill is NOT for

- Where data comes from; data infrastructure decisions → Chapter 2
- Feature engineering from training data → Chapter 4
- Model selection, training, and evaluation → Chapter 5
- Deployment patterns → Chapter 6
- Monitoring and distribution shift → Chapter 7
- Continual learning and online updates → Chapter 8
- Infrastructure and resource management → Chapter 9

If the user's question is clearly in one of those domains, say so and suggest the relevant chapter's skill.
