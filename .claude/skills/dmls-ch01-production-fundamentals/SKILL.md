---
name: dmls-ch01-production-fundamentals
description: Use this skill whenever the user is doing work that needs grounding in production ML fundamentals — specifically when they are (a) deciding whether to use ML for a problem at all, (b) scoping an ML project or writing requirements for one, (c) planning an ML project roadmap or timeline, (d) evaluating whether a research approach or paper will survive production, or (e) explaining ML tradeoffs to non-ML stakeholders (executives, product, legal, engineers). Also trigger on direct questions about the 4 production ML requirements (reliability, scalability, maintainability, adaptability), latency vs. throughput, why ML systems fail silently, how the ML development lifecycle actually loops, fairness and interpretability as production requirements, or any mention of Chip Huyen's *Designing Machine Learning Systems* book. Lean toward triggering — this skill adds high-value structure to almost any strategic ML systems conversation, not just reactive Q&A.
metadata:
  status: draft
---

# DMLS Ch. 1 — Production ML Fundamentals

This skill supports **five concrete tasks** where Chapter 1 of *Designing Machine Learning Systems* provides directly useful structure. It is not a summary to read — it is a job aid to work from.

## Reference doc

Full content: `references/chapter-content.md`

Always read the reference before answering. It is organized task-by-task, not chapter-order. Each task in the reference is a self-contained workflow with checklists, decision tables, and concrete questions to ask.

## Role in the skill library (hybrid architecture)

This is a **per-chapter skill** — it owns Chapter 1's content. After all 12 chapters of the book are processed, **topic-scope "spine" skills** will be added on top (e.g., *scoping an ML project*, *designing a data strategy*, *deploying ML*, *operating in production*). Those spine skills will deep-link into this chapter's tasks when relevant.

Implications for this skill:
- Stay chapter-scoped. Don't try to answer questions that clearly belong to later chapters — defer and flag.
- Task anchors (e.g., `Task 2: Scoping a Production ML Project`) are stable and may be deep-linked by spine skills. Preserve them if editing.
- The reference's Appendix B (cross-chapter connections) is the integration point — update it as later chapters reveal refinements or contradictions.

## The five tasks this skill supports

Route to the reference task that matches the work the user is doing:

| If the user is… | Go to reference task | Use it to… |
|-----------------|---------------------|-----------|
| Proposing ML for a problem, or asking "should we use ML for this" | **Task 1: ML Go/No-Go Gate** | Walk the 6-part definition check, amplifier check, and hard stops. Suggest partial-ML fallback if the full problem fails. |
| Starting a new ML project, writing requirements, building a project charter | **Task 2: Scoping a Production ML Project** | Map stakeholders, translate the 4 requirements into acceptance criteria, lock down latency/throughput targets, decide fairness/interpretability posture. |
| Building a roadmap, timeline, or project plan | **Task 3: Planning for the Iterative Lifecycle** | Plan the six phases with what-to-do-in-each; anticipate the common loopbacks; budget for 3–5 iterations, not one pass. |
| Evaluating a paper, research approach, or SOTA model for production use | **Task 4: Translating Research ML to Production ML** | Walk the five-axis gap, identify which research patterns rarely ship, flag data-transfer risks. |
| Preparing a presentation or conversation for non-ML stakeholders | **Task 5: Communicating ML Tradeoffs to Non-ML Stakeholders** | Pull talking points on silent failures, latency percentiles, accuracy-in-context, fairness/interpretability, ML vs. traditional software, cycle vs. pipeline. |

Multiple tasks may apply to one conversation. A user scoping a project (Task 2) will usually also need Task 3 (planning the lifecycle) and sometimes Task 5 (convincing leadership). Load both reference sections.

## How to use the reference

1. **Identify the task** from the table above. Don't skip to trying to answer — name the task first.
2. **Read the relevant task section** in the reference doc. Each task has concrete steps, checklists, and questions. Use them directly; don't paraphrase from memory.
3. **If the user's situation spans multiple tasks**, walk them in order (Task 1 → 2 → 3 is the natural project-start flow).
4. **Apply the checklists literally.** When the reference says "answer these questions," surface those questions to the user rather than assuming answers.
5. **Cite the data points only where they sharpen the point** — e.g., when defending latency percentile SLAs to a skeptical stakeholder, the Akamai/Booking.com numbers help. When planning a project, they don't.

## Style of advice

- **Task-first, framework-second.** Name what the user is doing before invoking concepts. "You're scoping a project — let's walk Task 2's stakeholder map" not "The book says there are four production requirements."
- **Checklists over prose.** Surface the reference's checklists and tables directly in the response. They're more useful than a restatement.
- **Be realistic about what this chapter doesn't cover.** Chapter 1 is scoping and framing — it doesn't teach you how to actually do data engineering, pick an algorithm, or build monitoring. Defer to later-chapter skills when they exist, or flag that deeper work is needed.
- **Don't default to recommending ML.** The chapter's repeated point is that ML isn't always the right tool. Task 1 is a gate, not a formality.
- **Think in cycles, not lines.** When advising on planning, assume the project will loop through phases multiple times. The 13-step walkthrough in Task 3 exists for this reason.

## Caveats on dated data points

Some numbers in the reference are from 2017–2021 (Akamai latency study, Lyft CAC, McKinsey fairness stats, dataset sizes). The trends they illustrate still hold, but cite them as *illustrative*, not current. The reference flags which data is dated in Appendix A.

## What this skill is NOT for

- Choosing a specific algorithm or model architecture → Chapter 5 territory
- Data engineering details (sources, pipelines, formats) → Chapter 2
- Labeling and training data curation → Chapter 3
- Feature engineering → Chapter 4
- Deployment mechanics → Chapter 6
- Monitoring, drift detection, debugging in production → Chapter 7
- Continual learning → Chapter 8

If the user's question is clearly in one of those domains, say so and suggest the relevant chapter's skill (which may not exist yet).
