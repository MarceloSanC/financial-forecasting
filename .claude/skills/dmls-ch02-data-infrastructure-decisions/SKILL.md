---
name: dmls-ch02-data-infrastructure-decisions
description: Use this skill whenever the user is making architectural decisions about the data layer of an ML system — specifically when they are (a) mapping or auditing the data sources an ML project will use, (b) choosing a storage format (CSV, Parquet, JSON, Avro, Protobuf, Pickle) or data model (relational, document, graph) for a dataset, (c) deciding between structured vs. unstructured, data warehouse vs. data lake, or ETL vs. ELT, (d) designing how services in an ML system pass data to each other (database, request-driven REST/RPC, event-driven Kafka/Kinesis/RabbitMQ), (e) deciding batch vs. stream processing for feature computation, or (f) writing reliability and workload requirements (ACID vs. BASE, OLTP vs. OLAP) for the data layer. Also trigger on direct questions about row-major vs. column-major formats, pandas DataFrame performance issues, CSV precision loss, static vs. dynamic features, pubsub vs. message queue, or any mention of Chip Huyen's *Designing Machine Learning Systems* book. Lean toward triggering — this skill adds structure to most data infrastructure conversations in ML work.
metadata:
  status: draft
---

# DMLS Ch. 2 — Data Infrastructure Decisions

This skill supports **four architectural decisions** where Chapter 2 of *Designing Machine Learning Systems* provides directly useful structure. It is not a summary to read — it is a job aid for making data-layer decisions in production ML systems.

## Reference doc

Full content: `references/chapter-content.md`

Always read the reference before answering. It is organized task-by-task, not chapter-order. Each task has decision tables, checklists, and questions to surface to the user.

## Role in the skill library (hybrid architecture)

This is a **per-chapter skill** — it owns Chapter 2's content. After all 12 chapters of the book are processed, **topic-scope "spine" skills** will sit on top (e.g., *designing the data strategy*, *deploying and serving*). Those spine skills will deep-link into this chapter's tasks when relevant.

Implications for this skill:
- Stay chapter-scoped. Defer to other chapters' skills for training data curation (Ch. 3), feature engineering (Ch. 4), deployment mechanics (Ch. 6/7), and infrastructure operations (Ch. 9).
- Task anchors (e.g., `Task 2: Choose Storage Format and Data Model`) are stable and may be deep-linked. Preserve them if editing.
- Appendix B (cross-chapter connections) is the integration point — update it as later chapters reveal refinements.

## The four tasks this skill supports

Route to the reference task that matches the work the user is doing:

| If the user is… | Go to reference task | Use it to… |
|-----------------|---------------------|-----------|
| Inventorying where data comes from for an ML project; auditing data sources; raising privacy/dependency concerns | **Task 1: Map Data Sources for an ML Project** | Walk the 5-category taxonomy, surface per-source questions, flag privacy and third-party risks. |
| Choosing a file format, data model, warehouse vs. lake, or ETL vs. ELT | **Task 2: Choose Storage Format and Data Model** | Walk row/column, text/binary, relational/document/graph decisions as decision tables. Surface format gotchas (CSV floats, pandas rows). |
| Designing how services communicate; drawing service graphs; deciding batch vs. stream | **Task 3: Design Inter-Service Dataflow** | Pick between database / request-driven / event-driven per link. Decide pubsub vs. message queue. Plan static vs. dynamic feature computation. |
| Writing data-layer reliability and workload requirements (ACID, BASE, OLTP, OLAP) | **Task 4: Write Data System Reliability and Workload Requirements** | Classify workload, specify reliability posture per component, avoid over-specifying legacy OLTP/OLAP splits. |

Multiple tasks may apply to one conversation. A user scoping a new ML project's data layer will likely need Task 1 → Task 2 → Task 4 in that order, then Task 3 once services are defined.

## How to use the reference

1. **Identify the task** from the table above. Name it before answering.
2. **Read the relevant task section.** Each has concrete decision tables and questions — use them directly.
3. **Surface decision tables as tables** in the response, not as prose. The tables are the value.
4. **Apply the questions-to-answer literally** — surface them to the user rather than guessing answers.
5. **Cite dated data points only when they sharpen a decision.** (Parquet's 2x-6x size/speed claim helps justify picking a binary format; it doesn't help an abstract "why columnar is better" conversation.)

## Style of advice

- **Task-first, concept-second.** Name what the user is doing before invoking vocabulary. "You're choosing between REST and pubsub — that's Task 3's decision rule" not "The book covers request-driven vs. event-driven architectures."
- **Tables and checklists over prose.** This chapter is decision-dense. Flattening tables into paragraphs destroys their value.
- **Don't skip the decision rule.** Each task has a shortcut rule (e.g., "logic-heavy → request-driven; data-heavy → event-driven"). Use those to help the user decide, don't just list options.
- **Flag gotchas proactively.** CSV + floats = precision loss. Pandas rows = slow. Lakes without discipline = data swamps. These come up often enough to mention without being asked.
- **Resist over-specifying.** The chapter's modern-reframing point applies broadly: don't demand a specific implementation when requirements would do. A component needs "low-latency transactional writes with strong consistency" — the team picks the engine.

## Caveats on dated content

Several numbers are circa 2019–2021 (AWS S3 pricing ratios, Parquet size claims, Stackshare company lists, CAID workaround). The *directional* claims hold — binary is smaller than text, column-major is faster for column scans, privacy arms races continue. Cite specifics as illustrative. Appendix A flags every dated data point explicitly.

## What this skill is NOT for

- Sampling, labeling, or training data curation → Chapter 3
- Feature engineering specifics → Chapter 4
- Model selection and training → Chapter 5
- Deployment patterns → Chapter 6
- Monitoring and data drift detection → Chapter 7
- Continual learning → Chapter 8
- Infrastructure operations and resource management → Chapter 9

If the user's question is clearly in one of those domains, say so and suggest the relevant chapter's skill (which may not exist yet).
