# DMLS Ch. 1 — Production ML Fundamentals (Task Reference)

Task-oriented notes from Chip Huyen's *Designing Machine Learning Systems*, Chapter 1. Organized around the real work this chapter supports, not the book's narrative order.

<!--
METADATA (for hybrid spine-skill assembly)
source: DMLS Ch. 1 — ML Systems in Production
tasks_supported:
  - task-1-ml-go-no-go-gate
  - task-2-scoping-a-production-ml-project
  - task-3-planning-for-the-iterative-lifecycle
  - task-4-translating-research-ml-to-production-ml
  - task-5-communicating-ml-tradeoffs-to-non-ml-stakeholders
spine_topics_likely_to_pull_from_this_chapter:
  - scoping-and-planning-an-ml-project
  - building-the-ml-org
  - operating-in-production (for the silent-failure framing)
  - communicating-with-stakeholders
-->

**Five tasks this reference supports:**
1. **ML Go/No-Go Gate** — deciding whether a problem should use ML
2. **Scoping a Production ML Project** — turning business goals into concrete requirements
3. **Planning for the Iterative Lifecycle** — designing a project plan that expects loops
4. **Translating Research ML to Production ML** — catching assumptions that won't survive deployment
5. **Communicating ML Tradeoffs to Non-ML Stakeholders** — explaining latency, silent failures, fairness, interpretability

Jump to the task you're doing. Each task is self-contained. Background context and historical debates are in the Appendix.

---

## Task 1: ML Go/No-Go Gate

**Use when:** Someone is proposing to use ML for a problem. Before committing data, infra, and team time, walk the problem through this gate.

### Step 1.1 — Six-part definition check

ML is an approach to **(1) learn (2) complex (3) patterns from (4) existing data** and use these patterns to make **(5) predictions on (6) unseen data**. The problem must satisfy *all six*.

| # | Condition | Ask yourself | If fails, do this instead |
|---|-----------|--------------|---------------------------|
| 1 | **Learn** — system can learn | Is there something concrete to learn from? Not just "we have a database." | Use deterministic logic, rules, or a lookup table |
| 2 | **Complex** — pattern is complex | Could you hand-write this as a rule without it ballooning? | Write rules / use a lookup table |
| 3 | **Patterns** — patterns actually exist | Is there a reason to believe signal exists in the data? | Don't waste time; the problem may be genuinely random or the wrong data |
| 4 | **Existing data** — data is available or collectable | Do you have (or can you obtain) labeled data representative of the task? | Bootstrap with humans-in-the-loop ("fake it till you make it") and collect data to train later, or consider zero-shot (requires data on a related task) |
| 5 | **Predictions** — problem is predictive | Can you rephrase the problem as "what's the answer to this question?" | Reframe the problem, or use exact computation if feasible |
| 6 | **Unseen ≈ training distribution** — serving data will resemble training data | Is the environment stable enough that yesterday's patterns hold tomorrow? | Plan for continual learning, or don't use ML if shifts are too fast/extreme |

### Step 1.2 — Amplifier check (does ML *shine* here?)

ML's upfront cost (data, compute, talent, infra) is high. It pays off best when:

- [ ] **Repetitive task** — pattern occurs many times, so the model has enough examples to learn from
- [ ] **Wrong predictions are cheap** — bad recommendation = user ignores it. If mistakes are catastrophic, the benefit of correct predictions must clearly outweigh the cost (e.g., self-driving: statistically safer than humans justifies mistakes)
- [ ] **At scale** — many predictions per unit time (millions of emails/year, thousands of tickets/day). A "single" prediction that updates hourly also counts
- [ ] **Patterns change constantly** — hand-written rules would go stale; ML retrains from new data

A problem can still justify ML without all four, but each missing amplifier weakens the business case.

### Step 1.3 — Hard stops (don't use ML if)

- [ ] **Unethical.** Full stop.
- [ ] **Simpler solutions do the trick.** Rules, heuristics, or lookup tables should be tried first. If they work, ship them.
- [ ] **Not cost-effective.** Factor in labeling, compute, infra, ongoing monitoring, retraining — not just training cost.

### Step 1.4 — Partial-ML fallback

If the full problem fails the gate, decompose it. ML often solves a *component* of a problem:

- A chatbot that can't answer everything can classify whether a query matches an FAQ and route to it; hand off the rest to humans.
- A full legal document reviewer is too risky for ML, but classifying which clauses need human review is tractable.

Ask: **what is the smallest predictive slice of this problem that could deliver value?**

### Step 1.5 — Forward-looking caveat

Don't reject ML because it isn't cost-effective *today* at your scale. If the data and use case will grow, and the tech is improving, waiting for proof can leave you years behind competitors. But this is an argument for *piloting*, not *committing*.

---

## Task 2: Scoping a Production ML Project

**Use when:** You've passed the Go/No-Go gate and need to turn "we're going to use ML for X" into concrete requirements, stakeholders, and acceptance criteria.

### Step 2.1 — Map stakeholders and their requirements

Production ML always involves multiple groups with conflicting priorities. Identify each and capture their requirement explicitly.

**Default stakeholder list to start from:**

| Stakeholder | Typical priority | Typical requirement to surface |
|-------------|------------------|--------------------------------|
| ML engineers | Model quality | Data access, training infra, evaluation framework |
| Product | User experience | Latency targets, error tolerance, UX for failure modes |
| Sales / revenue | Revenue impact | Which business metric is the model *actually* optimizing for? |
| Infra / platform | System stability | Deploy cadence, resource budget, rollback strategy |
| Leadership | Margin / ROI | Cost ceiling, timeline, success criteria |
| Legal / compliance | Risk | Privacy, fairness, auditability, regulated-data handling |
| End users | Outcome quality | Often unspoken; proxy with product |

**For each stakeholder, capture:**
- What do they want the system to do?
- What's their *must-have* vs. *nice-to-have*? (Critical — without this distinction you can't make tradeoffs later.)
- What would make them say the project failed?

**Watch for hidden objective conflicts.** The classic example: a restaurant recommender where ML engineers optimize "most likely to order," sales wants "most expensive restaurant" (higher fees), product wants "<100ms latency." These are three different models, not one.

**When objectives truly conflict:** build one model per objective and combine predictions at serving time (covered more in the book's Ch. 5 on Decoupling Objectives). Don't try to cram all objectives into one loss function.

### Step 2.2 — Define the four production requirements as acceptance criteria

Every production ML system must satisfy reliability, scalability, maintainability, and adaptability. Translate each into concrete, testable requirements.

#### Reliability
**Concept:** System performs correctly under adverse conditions (hardware failure, software bugs, human error).

**The ML-specific wrinkle:** ML systems **fail silently**. A `predict()` call may succeed and return a wrong answer. Traditional reliability tooling (5xx errors, crashes, exceptions) won't catch it.

**Questions to answer when scoping:**
- How will we detect wrong predictions in production, given we often lack ground truth in real time?
- What's our proxy-for-correctness metric (e.g., downstream business metrics, user feedback, shadow evaluation)?
- What's our plan for monitoring distribution shift? (Ch. 7 depth — scope the hook now.)
- What's the rollback plan when a model degrades?

#### Scalability
**Concept:** Handle growth along three axes, not just traffic.

**The three growth axes to plan for:**
1. **Complexity growth** — small model now, larger model later. Does your infra tolerate a 16x RAM increase?
2. **Traffic growth** — 10K/day → 10M/day. Plan autoscaling, but know autoscaling can fail (Amazon Prime Day: autoscaling failure cost an estimated $72–99M/hour).
3. **Model count growth** — one model → one per customer. A startup in the book scaled to 8000 models for 8000 enterprise customers. Managing 100 models is fundamentally different from managing one.

**Two aspects of scaling to plan separately:**
- **Resource scaling** (up/down): GPUs, memory, replicas. Usually handled by cloud autoscaling.
- **Artifact management**: code, data, and model versioning; automated retraining; reproducibility. Often overlooked during scoping, then becomes the dominant source of operational pain.

**Questions to answer:**
- What's the expected model count in 1 year? 3 years?
- Who owns retraining automation?
- How do we reproduce a specific model version on demand?

#### Maintainability
**Concept:** Different people with different tools must be able to work on the system without friction.

**The ML-specific wrinkle:** ML projects span ML engineers, DevOps, data engineers, subject matter experts, and often product/analytics. Each brings their own tools and mental models.

**Questions to answer:**
- Who owns which component? (Write it down.)
- What's the on-call story — who gets paged when the model misbehaves?
- Are we forcing everyone onto one toolchain, or allowing each group to use what they're good at? (The book argues for the latter.)

#### Adaptability
**Concept:** System must evolve to handle shifting data and shifting business requirements, with updates possible without service interruption.

**Questions to answer:**
- What's the expected cadence of retraining? Daily? Weekly? On drift?
- Can we update the model without downtime? (Canary, shadow, blue/green — pick one and scope it.)
- How will we know when business requirements have shifted enough to warrant a model change vs. a retrain?

### Step 2.3 — Lock down latency and throughput targets early

These numbers drive architecture. Don't leave them vague.

**Distinguish latency from throughput:**
- **Latency** — time from request to response, as experienced by one user
- **Throughput** — queries processed per unit time across all users

They're not inversely related when batching is involved. Batching raises latency *and* throughput simultaneously — which can be a good or bad tradeoff depending on the product.

**Critical: specify latency as percentiles, not averages.**
Example: 10 requests at [100, 102, 100, 100, 99, 104, 110, 90, 3000, 95]ms → average is 390ms. That average is misleading; 9 requests were fine and 1 was pathological. Percentiles tell the real story:
- **p50 (median)** — typical user experience
- **p90 / p95 / p99** — tail experience; outliers and your worst-served users live here

**High percentiles are often your most valuable users.** On Amazon, the slowest requests come from accounts with the most purchase history — the most valuable customers.

**Default SLA practice:** specify p95 or p99, not average.

**Real-world latency sensitivity (illustrative — from 2017–2019, but the shape holds):**
- Akamai 2017: 100ms delay → 7% conversion drop
- Booking.com 2019: ~30% latency increase → 0.5% conversion drop (material at their scale)
- Google 2016: >3s mobile page load → >50% of users leave

**Questions to answer in scoping:**
- What's our p95 latency budget? p99?
- Can we batch online, or does the product require single-query processing?
- What's our throughput target at peak? At steady state?

### Step 2.4 — Decide fairness and interpretability posture upfront

Both are **production requirements, not research nice-to-haves**. Deciding posture upfront prevents retrofitting.

**Fairness:**
- ML at scale makes discriminatory judgments at scale. A model can reject creditworthy applicants based on zip code (encoded socioeconomic signal), downrank résumés based on name spelling, or charge higher interest rates based on biased credit scores.
- **Berkeley 2019:** lenders rejected ~1.3M creditworthy Black and Latino applicants (2008–2015); stripping race identifiers approved the same applications.
- **Misclassification of minorities often has minor effects on aggregate metrics** — so companies skip the fix when it's expensive. Plan explicitly against this default.

**Questions to answer:**
- Who is the model making decisions about? Are any groups disproportionately affected by errors?
- What's our fairness metric, and who owns monitoring it?
- Do we have a written policy for what we'll do when we detect bias?

**Interpretability:**
- Needed for user trust, regulatory defense, and developer debugging.
- Hinton's thought experiment: black-box AI surgeon with 90% cure rate vs. human surgeon with 80%. Half of surveyed tech executives still picked the human. Interpretability is a *human* requirement, not a technical one.

**Questions to answer:**
- Who needs to understand model decisions? (End users? Regulators? Internal debuggers?)
- What level of interpretability is required — feature attribution, counterfactuals, full rule extraction?
- Is our model architecture compatible with that level? (If not, decide *now*.)

---

## Task 3: Planning for the Iterative Lifecycle

**Use when:** Building the project plan, setting milestones, or resisting pressure to commit to a waterfall timeline.

### Step 3.1 — The six-phase lifecycle (with what you actually do in each)

Not a waterfall. A cycle. Each phase *can* loop back to an earlier phase at any time.

| Phase | What you do | What to plan for |
|-------|-------------|------------------|
| 1. **Project scoping** | Set goals, objectives, constraints. Identify stakeholders. Estimate resources. | Use Task 2 above. Explicit must-have vs. nice-to-have per stakeholder. |
| 2. **Data engineering** | Source data from different origins/formats. Sample. Label. Curate training data from raw data. | Data versioning strategy. Labeling workflow (who labels, how is quality assured). Privacy/regulatory constraints. |
| 3. **ML model development** | Feature engineering. Model selection, training, evaluation. | Experiment tracking. Reproducibility. Decide evaluation metrics that reflect *business* goals, not just model goals. |
| 4. **Deployment** | Make the model accessible to users. | Deployment pattern (online/batch/edge). Rollback plan. Shadow/canary strategy. |
| 5. **Monitoring & continual learning** | Monitor for decay. Retrain. Adapt to shifts. | Silent-failure detection. Drift metrics. Retraining automation. |
| 6. **Business analysis** | Evaluate against business goals. Generate insights. Decide to kill, pivot, or scale. | Agreed-upon success/kill criteria. Who owns this review, and how often. |

### Step 3.2 — Anticipate the common loopbacks

Chip's realistic 13-step walkthrough of an ad-display prediction project shows where projects *actually* loop:

1. Pick metric (impressions).
2. Collect data, label it.
3. Engineer features.
4. Train.
5. **Error analysis → relabeling needed.** *(Loops to step 2.)*
6. Retrain.
7. **Error analysis → class imbalance.** *(Loops to step 2 for more positive-class data.)*
8. Retrain.
9. **Model decays on recent data — stale test set.** *(Loops to step 2 for fresh data.)*
10. Retrain.
11. Deploy.
12. **Revenue drops — wrong metric.** *(Loops all the way to step 1 to change the objective.)*
13. Back to start.

**Planning implications:**
- Build time/budget for 3–5 loops, not one pass.
- The most expensive loop is changing the optimization metric (step 12 → step 1). Spend real time on metric selection *before* engineering starts.
- Error analysis is a scheduled activity, not a one-time checkpoint. Plan it in.
- Test sets go stale. Plan for refreshing them.

### Step 3.3 — Common scoping mistakes this phase catches

- Planning a linear Gantt chart for a cyclical process.
- Choosing an evaluation metric that doesn't match the business metric.
- Treating labels as final when relabeling will almost certainly happen.
- Not budgeting for retraining and monitoring infra *before* deploy.
- Treating deploy as the end, when it's the start of Phases 5 and 6.

---

## Task 4: Translating Research ML to Production ML

**Use when:** Evaluating whether a paper's approach will ship, onboarding a researcher to a production team, or defending why "we can't just use the SOTA model."

### The five-axis gap

Production ML and research ML differ across five dimensions. Any mismatch is a risk to surface explicitly.

| Axis | Research | Production | Translation risk |
|------|----------|------------|------------------|
| **Requirements** | Single objective, usually SOTA on a benchmark | Multiple stakeholders, often conflicting | SOTA model may not be best for your stakeholder mix |
| **Computational priority** | Fast training, high throughput (willing to pay latency cost) | Fast inference, low latency | Research-aggressive batching hurts user-facing latency |
| **Data** | Clean, static, well-understood, preprocessed | Messy, shifting, biased, streaming, privacy-constrained | Paper's data pipeline won't match yours; quirks won't transfer |
| **Fairness** | "Good to have" — no SOTA metric for it | Required | Research models are rarely evaluated for bias |
| **Interpretability** | "Good to have" | Required for trust, debugging, compliance | Black-box SOTA may be non-starter for regulated domains |

### Specific research patterns that often don't ship

- **Ensembling** — wins Kaggle and Netflix Prize, but typically too slow and hard to maintain in production. Small perf gains rarely justify the complexity cost.
- **Small accuracy gains on benchmarks** — 95% → 95.2% is invisible to users. For business metrics like CTR, 0.2% can be millions of dollars; for user-perceived quality, it's noise. Know which regime you're in.
- **Leaderboard-driven models** — easy steps are pre-done for you (data cleaning, labels, metric); multiple-hypothesis testing means top leaderboard models may win partly by chance; optimizes for the leaderboard metric only, ignoring compactness, fairness, efficiency.

### Training vs. inference bottleneck

- **Research:** model runs many training iterations, one inference pass on a test set. **Training is the bottleneck.**
- **Production:** model is trained relatively rarely, inferences continuously. **Inference is the bottleneck.**

This affects every architecture decision — model size, batching, quantization, hardware. A research team optimizing for training throughput will build a different system than a production team optimizing for inference latency.

### Data: the single biggest research → production failure mode

Research datasets are clean, static, well-known, often with public preprocessing scripts. Production data is:
- Noisy, possibly unstructured
- Constantly shifting (distribution drift)
- Biased in unknown ways
- Labels sparse, imbalanced, outdated, or wrong
- Class definitions may change after deployment
- Privacy and regulatory constraints
- Mix of historical + streaming + third-party sources

A model that achieves SOTA on a benchmark may perform terribly on your data. Always evaluate on *your* data, not the paper's.

---

## Task 5: Communicating ML Tradeoffs to Non-ML Stakeholders

**Use when:** Explaining ML decisions to executives, PMs, legal, or skeptical engineers. Quick talking points with the underlying reasoning.

### Talking point 1: "ML systems fail silently, unlike regular software."

Traditional software crashes, returns 500s, or throws exceptions. You know when it breaks. ML systems keep serving — just with wrong answers. End users may not notice; developers may not either.

**Implication:** reliability monitoring for ML systems is a different, harder problem than for traditional software. Budget for it.

### Talking point 2: "Latency is a distribution, not a number."

Averaging latency hides the experience of your worst-served users.
- Example: 10 requests, 9 fast (~100ms), 1 slow (3000ms). Average = 390ms. Median = 100ms.
- p95 and p99 tell the real story of the tail.
- **On Amazon, the slowest requests come from the most valuable customers** (largest purchase histories = most data to process). Tail latency is a business metric.

**Implication:** SLAs should be written in percentiles, not averages. A "p99 < 200ms" SLA is meaningfully different from "average < 200ms."

### Talking point 3: "Tiny accuracy gains are sometimes enormous, sometimes invisible."

Depends on what's downstream of the prediction.
- 0.2% CTR improvement in recommendations = millions in revenue for a large ecommerce site.
- 95% → 95.2% speech recognition = no user notices.

**Implication:** "better model" means nothing without context. Insist on a downstream metric tied to a business outcome.

### Talking point 4: "Fairness and interpretability aren't nice-to-haves in production."

- Fairness: ML at scale *discriminates at scale*. Known real-world cases include credit denial based on zip code, résumé downranking based on name, and mortgage rates tied to biased credit scores. Berkeley 2019 found ~1.3M creditworthy Black and Latino applicants were rejected (2008–2015); removing race identifiers approved them.
- Interpretability: users, regulators, and developers all need it. In Hinton's thought experiment, half of surveyed executives preferred the 80%-cure-rate human surgeon over the 90%-cure-rate black-box AI. Trust isn't about accuracy.

**Implication:** treat these as scoped, budgeted requirements, not add-ons.

### Talking point 5: "ML systems are code + data + artifacts — not just code."

Traditional software engineering separates code from data. ML systems can't — the *model itself* is derived from both. Consequences:
- You version *data* as well as code.
- Sample quality matters: 1000 cancerous lung scans are worth more than 1M normal scans to a cancer detector.
- New attack surfaces exist — e.g., data poisoning, where malicious training inputs can backdoor a face recognition system.
- Model size creates deployment challenges (edge devices, inference costs).
- Models are opaque — debugging and monitoring are harder than for traditional services.

**Implication:** "just ship it like regular software" is a category error. ML ops is a distinct discipline.

### Talking point 6: "ML development is a cycle, not a pipeline."

Deployments don't end projects; they start phases 5 (monitoring) and 6 (business review). Models decay. Metrics reveal wrong objectives. Labels need refreshing. Plan for 3–5 loops, not one pass.

**Implication:** resist waterfall Gantt charts for ML projects. Budget for error analysis, retraining, and metric revisions as first-class activities.

---

## Appendix A: Background Context (not task-critical)

Kept here for depth when needed; not part of the five task workflows.

### Mind vs. Data debate

A long-running argument in ML about whether intelligent algorithmic design or massive data + compute matters more.

- **"Mind" camp (Judea Pearl, Chris Manning):** data alone is dumb; inductive biases matter. Pearl (2020) predicted data-centric practitioners would be outdated in 3–5 years.
- **"Data" camp (Richard Sutton, Peter Norvig):** Sutton's "Bitter Lesson" — general methods leveraging computation win in the long run. Norvig: "We don't have better algorithms. We just have more data."

**How this has aged (as of 2026):** the data+compute camp has dominated frontier progress. GPT-4, Claude, Gemini all validated the Bitter Lesson at scale. Pearl's 3–5 year prediction did not pan out — data-centric approaches are more dominant than ever. However, **data quality and curation** have proven more important than pure quantity, which is a partial vindication of the "mind" camp's emphasis on thoughtfulness.

**Practical takeaway:** at application scale, focus on data quality and quantity first. Algorithmic cleverness rarely beats better data.

### Why "ML system" is more than the algorithm

The algorithm is a small piece. A production ML system also includes:
- Interface (user and developer)
- Data stack
- Hardware backend
- Infrastructure for development, deployment, monitoring, updating

When scoping, resist focusing only on the algorithm. The other components drive more risk and consume more time.

### Common ML use case categories (for recognition, not planning)

**Consumer:** search, recommendation (Amazon, Netflix), predictive typing, photo enhancement, face/fingerprint auth, machine translation, voice assistants, security cameras, health monitoring.

**Enterprise (majority of use cases):** fraud detection, price optimization, demand forecasting, customer acquisition, churn prediction, support ticket classification, brand monitoring, healthcare diagnostics.

**Enterprise vs. consumer posture:**
- Enterprise: stricter accuracy requirements, more forgiving on latency. A 0.1% efficiency gain at scale = millions.
- Consumer: easier to distribute, harder to monetize; users less tolerant of latency.

### Dated data points (treat as illustrative, not current)

All circa 2019–2021. Trends hold; specific numbers have moved.

- Akamai 2017: 100ms delay → 7% conversion drop
- Booking.com 2019: ~30% latency increase → ~0.5% conversion drop
- Google 2016: >3s page load → >50% mobile users leave
- Customer retention: 5–25x cheaper than acquisition
- Mobile app acquisition cost: ~$87/paying user (2019)
- Lyft rider CAC: ~$158 (2019)
- McKinsey 2019: 13% of large companies actively mitigating fairness; 19% working on interpretability
- Dataset size trajectory: 0.8B tokens (2013) → 10B (GPT-2) → 500B (GPT-3) → ~13T (GPT-4, 2023) → larger since

### Themes that recur in later chapters

Forward-pointers, updated as later chapter skills are built. Use these when the user's question spans multiple chapters.

- **Stakeholder alignment and decoupling objectives** → Ch. 5
- **Data-centric mindset (quality, labeling, versioning)** → Ch. 2, 3
- **Feature engineering and model selection** → Ch. 4, 5
- **Deployment patterns, edge devices, model optimization** → Ch. 6
- **Failures, monitoring, distribution shift** → Ch. 7
- **Continual learning** → Ch. 8
- **Infrastructure and resource management** → Ch. 9
- **Team structure and the human side of ML** → Ch. 10

---

## Appendix B: Cross-chapter connections

Populated as later chapter skills are built. This section captures:
- Concepts from Ch. 1 that later chapters **refine** (e.g., if Ch. 5 gives a more nuanced view of "decoupling objectives" than Ch. 1's two-models-combined approach, note it here)
- Concepts from Ch. 1 that later chapters **contradict or update**
- Concrete cross-links useful for the eventual hybrid spine skills (e.g., "Task 2's latency targets tie to Ch. 7's deployment patterns")

### From Ch. 2 — Data Infrastructure Decisions

**Refinements to Ch. 1 concepts:**
- **Ch. 1 Task 2's data-sourcing question** ("Do you have labeled data?") is sharpened by Ch. 2 Task 1's 5-category source taxonomy. When scoping a project, use Ch. 1 Task 2 to ask whether data is available; use Ch. 2 Task 1 to classify *what kind* and plan accordingly.
- **Ch. 1 Task 2's latency targets** (p95/p99 at the system level) cascade down to component-level choices in Ch. 2. A sub-100ms p99 at the product layer forces event-driven dataflow and in-memory brokers (Ch. 2 Task 3) rather than database handoffs.
- **Ch. 1's production requirement of "adaptability"** ties to Ch. 2's ETL vs. ELT and warehouse vs. lake decisions. Lake + ELT gives more adaptability at the cost of schema discipline; warehouse + ETL is rigid but predictable.

**New concepts from Ch. 2 worth remembering when using Ch. 1:**
- **Static vs. dynamic features** (Ch. 2 Task 3) — when Ch. 1 Task 2 has you defining "what the model optimizes for," that choice implicitly decides whether you need streaming infrastructure. Surface this early.
- **ACID vs. BASE** (Ch. 2 Task 4) — more precise vocabulary than Ch. 1's general "reliability" requirement. Use it when writing specific data-layer requirements.

**Cross-links for spine skills:**
- *Scoping & planning an ML project* (spine) will pull Ch. 1 Task 2 + Ch. 2 Task 1 + Ch. 2 Task 4 together.
- *Designing the data strategy* (spine) will pull primarily from Ch. 2 (all tasks) but refer back to Ch. 1 Task 2's stakeholder mapping when deciding who owns data decisions.

### From Ch. 3 — Training Data Strategy

**Refinements to Ch. 1 concepts:**
- **Ch. 1 Task 1's "existing data" gate-check** (is data available?) gets sharpened by Ch. 3's alternatives. The answer isn't just yes/no — even when explicit labeled data is missing, you often have *natural labels* (clicks, ratings, conversions), or can leverage *pretrained models* via transfer learning, or can use *weak supervision* with subject-matter expertise. Update Ch. 1 Task 1 gate-check: "existing data" is almost always yes in some form; the real question is whether you have the right labeling approach.
- **Ch. 1 Task 3's loopback points** (relabeling, class imbalance, metric changes) are directly what Ch. 3 gives you tools for. Ch. 1 says "expect to loop 3–5 times"; Ch. 3 says "here's what each loop actually does."

**New concepts from Ch. 3 worth remembering when using Ch. 1:**
- **Natural labels** — should be part of Ch. 1 Task 1's feasibility check, not discovered later.
- **Labeling strategy as a project-scoping concern** — belongs in Ch. 1 Task 2's stakeholder mapping (who owns labeling? what's the budget?). Without it surfacing at scoping time, projects often discover labeling is the bottleneck after committing.

**Cross-links for spine skills:**
- *Scoping & planning an ML project* (spine) will pull Ch. 1 Task 2 + Ch. 3 Task 2 when assessing labeling feasibility and cost.

### From Ch. 4 — Feature Engineering Decisions

**Refinements to Ch. 1 concepts:**
- **Ch. 1 Task 2's reliability requirement** ("how do we know predictions are wrong without ground truth?") now has a partial answer through Ch. 4 Task 3's leakage detection. Many "silent failures" trace back to leakage rather than model degradation — when a production-deployed model performs much worse than test, leakage is a leading suspect.
- **Ch. 1 Task 3's iterative lifecycle** (the 13-step walkthrough, where errors trace back to wrong labels, class imbalance, etc.) should add a step for "errors trace back to leakage discovered post-deployment." Ch. 4 Task 3 is the workflow for that step.

**New concepts from Ch. 4 worth remembering when using Ch. 1:**
- **Leakage as a primary production-failure mode** — alongside data drift and model decay, leakage is one of the top reasons production performance disagrees with test performance. Worth surfacing in Ch. 1 Task 5's talking points for non-ML stakeholders ("here's why we can't fully trust our test numbers").
- **Feature engineering as a continuous activity** — Ch. 4's closing point that feature engineering doesn't end at deployment is consistent with Ch. 1's iterative-lifecycle framing.

**Cross-links for spine skills:**
- *Operating in production* (spine) will pull Ch. 1 Task 4 (silent failures) + Ch. 4 Task 3 (leakage detection) as the diagnostic workflow when production metrics diverge from test metrics.

### From Ch. 5 — Model Development and Evaluation

**Refinements to Ch. 1 concepts:**
- **Ch. 1 Task 1's ML go/no-go gate** is followed naturally by **Ch. 5 Task 1's problem framing**. Ch. 1 asks "should we use ML?"; Ch. 5 asks "what *shape* of ML problem is this — inputs, outputs, objective?"
- **Ch. 1 Task 2's stakeholder mapping with conflicting objectives** has a technical answer in **Ch. 5 Task 1's decoupling pattern**. When sales wants engagement and policy wants quality, don't combine into one loss — train separate models and tune the combination at serving time without retraining.
- **Ch. 1 Task 5's stakeholder talking points on fairness and interpretability** are backed by **Ch. 5 Task 5's invariance tests, calibration, and slice-based evaluation**. Those are the technical methods supporting the strategic framing.
- **Ch. 1's iterative lifecycle (Task 3)** has the model-development phase fleshed out by **Ch. 5 Task 3's practices** (experiment tracking, versioning, debugging discipline, distributed training when needed) — these are the operational practices that keep the loop running.

**New concepts from Ch. 5 worth remembering when using Ch. 1:**
- **The four phases of ML adoption** (before ML → simplest ML → optimizing simple → complex systems) is a project-strategy framework that complements Ch. 1's six-step lifecycle. Ch. 1's lifecycle is iterative within a phase; Ch. 5's four phases describe the maturity progression across phases.
- **Pre-deployment evaluation gauntlet (Task 5)** is what completes the "Phase 4: Deployment" step in Ch. 1's lifecycle. Don't ship until baselines, perturbation, invariance, directional expectation, calibration, confidence, and slicing have all been checked.

**Cross-links for spine skills:**
- *Scoping & planning an ML project* (spine) will pull Ch. 1 Tasks 1–3 + Ch. 5 Task 1 as the project framing workflow.
- *Model development and evaluation* (spine) is essentially the Ch. 5 spine skill — pulling all five Ch. 5 tasks plus relevant Ch. 1 (problem definition) and Ch. 7 (post-deployment monitoring) connections.

### From Ch. 6 — Deployment and Inference Decisions

**Refinements to Ch. 1 concepts:**
- **Ch. 1 Task 2's latency targets (p95/p99 SLAs)** cascade directly into Ch. 6 Task 1's serving paradigm choice. Sub-100ms latency forces online prediction; multi-second tolerance allows batch. This is where Ch. 1's abstract latency requirement becomes a concrete deployment architecture.
- **Ch. 1 Task 4's "ML systems fail silently" framing** has a deployment-time analogue in Ch. 6 Task 1's "two pipelines anti-pattern" (train/serve feature skew). The serving pipeline silently uses different feature definitions than the training pipeline, and predictions degrade without crashes. This is the canonical example of silent failure Ch. 1 warns about.
- **Ch. 1 Task 5's stakeholder talking points on cost and privacy** connect to Ch. 6 Task 2's cloud-vs-edge decision. When non-ML stakeholders ask "why are our cloud bills so high?" or "why can't we use this model in healthcare?" — the answer involves the architectural choices in Ch. 6 Task 2.

**New concepts from Ch. 6 worth remembering when using Ch. 1:**
- **The "production is a spectrum" framing** sharpens Ch. 1 Task 2's stakeholder mapping. "Production" can mean anything from a notebook plot for the business team to millions-of-users-per-day serving. When scoping requirements, ask explicitly which point on the spectrum.
- **Online prediction as the default direction of travel** — as hardware gets faster and inference cheaper, more systems move from batch to online. When planning a new ML system in 2026, the question is increasingly "can we do this online?" rather than "should we?"

**Cross-links for spine skills:**
- *Deploying and serving* (spine) will pull Ch. 6's four tasks plus Ch. 1 Task 2's latency requirements and Ch. 2 Task 3's batch/stream decisions.

### From Ch. 7 — Production Failure Modes

**Refinements to Ch. 1 concepts:**
- **Ch. 1 Task 4's silent failure framing** is sharpened by **Ch. 7 Task 1's diagnostic procedure** — and quantitatively supported by Ch. 7's Google study finding that 60/96 ML pipeline failures over 15 years were not directly ML-related. This is the data behind Ch. 1's "ML production is mostly engineering" framing.
- **Ch. 1 Task 3's iterative lifecycle** has the post-deployment phase fleshed out by **Ch. 7's failure modes** (edge cases, distribution shifts, degenerate feedback loops). These are the things Ch. 1's loopbacks are about.
- **Ch. 1 Task 5's stakeholder talking points** gain a sharper claim from Ch. 7: when non-ML stakeholders ask "what could go wrong?", the answer isn't usually the model — it's the data pipeline, the deployment, or the feedback loop.

**New concepts from Ch. 7 worth remembering when using Ch. 1:**
- **"~80% of drifts are internal errors"** — sharpens Ch. 1's adaptability requirement (Task 2). Most "the world changed" is actually "our pipeline broke." Plan for both, but suspect the pipeline first.
- **Edge case tolerance varies by domain** — refines Ch. 1 Task 1's go/no-go gate. Some applications (autonomous vehicles, medical) cannot deploy until edge case handling is solved; others (recommendations) can.

**Cross-links for spine skills:**
- *Operating in production* (spine) will pull Ch. 7's diagnostic and failure-mode tasks plus Ch. 8's monitoring and continual learning, with Ch. 1 Task 4 (silent failures) and Ch. 6 Task 1 (train/serve skew) as the foundational concepts.
