---
name: dmls-ch06-deployment-and-inference-decisions
description: Use this skill whenever the user is making decisions about deploying ML models to production — specifically when they are (a) choosing a serving paradigm (online/synchronous prediction vs. batch/asynchronous prediction vs. hybrid; deciding whether streaming features are needed and what real-time pipeline that requires), (b) deciding where inference runs (cloud vs. edge/on-device vs. browser via WASM/WebGPU; weighing latency, cost, privacy, connectivity, hardware constraints), (c) compressing a model for fast or small inference (quantization, knowledge distillation, pruning, low-rank factorization), or (d) compiling and optimizing models for production hardware (intermediate representations, vectorization, parallelization, loop tiling, operator fusion, ML-based compilation via autoTVM/TVM). Also trigger on direct questions about online vs. batch prediction, cloud vs. edge ML, model compression, quantization, DistilBERT, MobileNets, train-serve skew, the "two pipelines" anti-pattern, ML compilation, autoTVM, WASM, WebGPU, LLM serving (vLLM, continuous batching, KV caching), or any mention of Chip Huyen's *Designing Machine Learning Systems* book. Lean toward triggering — deployment decisions span almost every production ML conversation and shape cost, latency, and user experience.
metadata:
  status: draft
---

# DMLS Ch. 6 — Deployment and Inference Decisions

This skill supports **four decisions** when taking a trained model to production. It is not a summary to read — it is a job aid for making deployment-time and inference-time decisions, with particular emphasis on the serving paradigm choice and avoiding train/serve skew.

## Reference doc

Full content: `references/chapter-content.md`

Always read the reference before answering. It is organized task-by-task, with decision tables, checklists, and questions to surface to the user.

## Role in the skill library (hybrid architecture)

This is a **per-chapter skill** — it owns Chapter 6's content. After all 12 chapters are processed, **topic-scope "spine" skills** will sit on top (e.g., *deploying and serving*, *operating in production*, *infrastructure and scaling*). Those spine skills will deep-link into this chapter's tasks when relevant.

Implications for this skill:
- Stay chapter-scoped. Defer to other chapters' skills for production fundamentals (Ch. 1), data infrastructure (Ch. 2), training data (Ch. 3), feature engineering (Ch. 4), model development (Ch. 5), monitoring (Ch. 7), continual learning (Ch. 8), infrastructure (Ch. 9).
- Task anchors (e.g., `Task 3: Compress a Model for Fast/Small Inference`) are stable and may be deep-linked. Preserve them if editing.
- Appendix B is the integration point — update it as later chapters reveal refinements.

## The four tasks this skill supports

Route to the reference task that matches the work the user is doing:

| If the user is… | Go to reference task | Use it to… |
|-----------------|---------------------|-----------|
| Designing how predictions reach users; debating online vs. batch; thinking about whether streaming features are needed | **Task 1: Choose a Serving Paradigm** | Walk through latency, freshness, query predictability, cost. Pick batch, online (with batch or streaming features), or hybrid. Surface the train/serve skew anti-pattern. |
| Deciding whether to host inference in the cloud or push it to user devices; thinking about cloud bills or privacy | **Task 2: Decide Where to Run Inference** | Compare cloud, edge, browser. Map constraints (offline, latency, cost, privacy, regulatory) to location. Verify edge feasibility (compute, memory, battery, update mechanism). |
| Model is too slow or too large; needs to fit on edge; needs faster inference | **Task 3: Compress a Model for Fast/Small Inference** | Apply the four techniques in order: quantization first (workhorse), then distillation (if teacher available), then pruning (if hardware supports sparse), then low-rank factorization (if designing new architecture). Often combine. |
| Model needs to run efficiently on specific hardware; considering ML-based compilation; deploying via browser | **Task 4: Compile and Optimize for Production Hardware** | Understand the IR/compiler stack. Apply local optimizations (vectorization, parallelization, loop tiling, operator fusion). Decide whether ML-based compilation (TVM, MLC LLM) is worth it. Consider WASM/WebGPU for browser. |

Multiple tasks may apply. A new edge deployment will typically span Task 1 (probably online), Task 2 (definitely edge), Task 3 (almost certainly compress), and Task 4 (compile for the target accelerator).

## How to use the reference

1. **Identify the task** from the table above. Name it before answering.
2. **Read the relevant task section.** Decision tables and checklists are the value — preserve them in answers.
3. **Push hard on Task 1's "two pipelines" anti-pattern.** Train/serve feature skew is one of the most common bug sources in production ML and one of the easiest to catch early.
4. **For compression questions, default to "try quantization first."** Most general, easiest, biggest typical wins. Other techniques are situational.
5. **For "why is my model so slow?" questions, walk through three levers in order:** model compression (Task 3), faster compilation/optimization (Task 4), faster hardware (Task 2).
6. **Surface checklists literally** — they're more useful as questions to the user than as guesses.
7. **Cite benchmarks (Roblox 7x latency, DistilBERT 40% smaller, autoTVM ~70 trials) as illustrative**, not as current numbers.

## Style of advice

- **Task-first, technique-second.** "You're choosing a serving paradigm — Task 1 has the decision tree" rather than "Let me describe online vs. batch prediction."
- **Tables and decision shortcuts over prose.** This chapter has many; reproduce them rather than paraphrasing.
- **Push back on the "online or batch — pick one" mindset.** Hybrid is normal. Most production systems run multiple paradigms for different use cases.
- **Push back on "we'll just put it in the cloud" without considering cost trajectory.** At scale, cloud bills compound. Surface the question early.
- **For LLM-related questions, mention LLM serving as a distinct sub-discipline.** The chapter predates ChatGPT; vLLM, TGI, SGLang, continuous batching, KV cache management, paged attention are post-book developments worth raising. Appendix A explains.
- **Mention WebGPU when browser deployment comes up.** WASM is what the chapter advocates; WebGPU (2023+) is the bigger story for browser ML in 2026.
- **Treat compression and compilation as escalation paths.** Pick a smaller model first (Ch. 5 Task 2). If that's not enough, compress (Task 3). If that's still not enough, optimize compilation (Task 4). Hiring optimization engineers is the last resort.

## Caveats on dated content

The chapter's *frameworks* age well; some *examples* and *tools* are 2021-era. Notable updates flagged in Appendix A:
- LLM serving as a distinct sub-discipline (vLLM, TGI, continuous batching, KV cache management) — major post-book development
- WebGPU as a more performant alternative to WASM for browser ML (post-2023)
- Hardware startup landscape has consolidated (acquisitions, NVIDIA dominance for training)
- Cloud cost numbers have grown substantially in the LLM era
- Federated learning has been promised more than delivered
- TVM ecosystem has expanded (MLC LLM, Apache TVM Unity)

## What this skill is NOT for

- Whether to use ML at all → Chapter 1
- Where data lives and flows → Chapter 2
- Sampling, labeling, training data curation → Chapter 3
- Feature engineering → Chapter 4
- Model selection, training, pre-deployment evaluation → Chapter 5
- Monitoring deployed models in production → Chapter 7
- Continual learning and online updates → Chapter 8
- Infrastructure operations and resource management at scale → Chapter 9

If the user's question is clearly in one of those domains, say so and suggest the relevant chapter's skill.
