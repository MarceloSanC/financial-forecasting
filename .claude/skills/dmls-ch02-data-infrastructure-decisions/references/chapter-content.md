# DMLS Ch. 2 — Data Infrastructure Decisions (Task Reference)

Task-oriented notes from Chip Huyen's *Designing Machine Learning Systems*, Chapter 2. Organized around the architectural decisions this chapter supports, not the book's narrative order.

<!--
METADATA (for hybrid spine-skill assembly)
source: DMLS Ch. 2 — Data Engineering Fundamentals
tasks_supported:
  - task-1-map-data-sources-for-an-ml-project
  - task-2-choose-storage-format-and-data-model
  - task-3-design-inter-service-dataflow
  - task-4-write-data-system-reliability-and-workload-requirements
spine_topics_likely_to_pull_from_this_chapter:
  - designing-the-data-strategy (primary)
  - deploying-and-serving
  - scoping-and-planning-an-ml-project
  - operating-in-production
-->

**Four tasks this reference supports:**
1. **Map Data Sources for an ML Project** — inventory where data comes from, what it behaves like, what constraints each type imposes
2. **Choose Storage Format and Data Model** — pick CSV/Parquet/JSON/etc. and relational/document/graph for a given dataset
3. **Design Inter-Service Dataflow** — decide how data moves between services (database / request-driven / event-driven) and the batch vs. stream consequence
4. **Write Data System Reliability and Workload Requirements** — ACID/BASE, OLTP/OLAP, storage-compute coupling — produce scoping requirements, not implementation

Jump to the task you're doing. Each task is self-contained. Background and dated data points are in Appendix A.

---

## Task 1: Map Data Sources for an ML Project

**Use when:** Scoping a new ML project, auditing an existing one, or designing the data ingestion layer. This task runs *before* Task 2 — format and storage choices depend on what kind of data you're handling.

### Step 1.1 — Inventory data by source category

Every ML project's data traces back to one or more of these five sources. Each has different characteristics that drive downstream decisions.

| Source | Characteristics | Processing implications |
|--------|----------------|------------------------|
| **User input** — data users explicitly type/upload (text, images, files, numbers) | Malformed often; users put wrong data in wrong fields. Users expect fast feedback. | Heavy validation required. Low-latency processing. Clear error messaging. |
| **System-generated — logs** | State records, events, job results, memory/service metrics. Rarely malformed. Grows very quickly. | Periodic (hourly/daily) processing usually fine, but alerting paths need fast access. Plan for log search tooling and tiered retention. |
| **System-generated — user behavior** | Clicks, scrolls, time-on-page, dismissals, zooms. Subject to privacy regulations *even though* it's system-generated. | Treat as personal data. Useful both as model input and as training signal. |
| **Internal databases** | Company-owned business data: inventory, CRM, users, orders. Usually well-structured. | Often needs to be joined into features or checked at inference time (e.g., filter recommendations by current stock). |
| **Third-party** | Data purchased from vendors about users who aren't your customers. Usually arrives cleaned and structured. | Privacy scrutiny is high. Coverage shrinks over time as platforms add privacy controls (e.g., Apple's IDFA opt-in in 2021). Don't build a core strategy on it unless you've accepted the regulatory risk. |

**First-party / second-party / third-party distinction:**
- First-party: data your company collects on its own users.
- Second-party: another company's first-party data, sold to you.
- Third-party: data collected by a vendor on the general public (not their customers).

### Step 1.2 — Questions to answer for each source

For every source on your inventory, answer:

- [ ] What latency does this source's data *need* to be processed at? (User input → seconds. Logs → hours is often OK. User behavior → varies.)
- [ ] How malformed is it? What validation will it need?
- [ ] Is it subject to privacy regulations? (User input and behavior data almost always are; third-party always.)
- [ ] How fast is it growing? What's the retention policy?
- [ ] What's our storage tier strategy for it? (Hot/warm/cold — latency vs. cost tradeoff.)
- [ ] What happens if this source becomes unavailable? Is the ML system still functional?

### Step 1.3 — Flag privacy and dependency risks early

Third-party data is the most common place where plans fail after deployment. Platforms restrict tracking (Apple IDFA opt-in, browser cookie deprecation, regional regulation) and entire data feeds disappear.

**Questions to raise with the project team:**
- Are we depending on any data source we don't control?
- If that source is cut off or restricted, what's our fallback?
- Do we have written consent / regulatory clearance for the user behavior data we're collecting?

---

## Task 2: Choose Storage Format and Data Model

**Use when:** Designing the storage layer for a new dataset, migrating between formats, or debugging unexpectedly slow data access. Usually done after Task 1 (you need to know what kind of data first).

Two decisions, typically made together: **format** (how bytes are laid out on disk) and **data model** (how records are structured conceptually).

### Step 2.1 — Format decision

Two axes, decide each:

**Axis A: Row-major vs. column-major**

| Property | Row-major (CSV) | Column-major (Parquet) |
|----------|-----------------|------------------------|
| Fast at | Writing individual records; reading whole records | Reading a subset of columns across many records |
| Use when | Appending rows constantly (transactional logs, event streams written to files) | Analytics on a few features out of many; ML feature extraction |
| File size | Larger | Smaller |

**Rule of thumb:** if your workload is "keep adding examples one at a time," go row-major. If it's "pull 4 features out of 1000 for training," go column-major.

**Pandas gotcha worth knowing:** DataFrames are column-major (inherited from R's data frame). Iterating a DataFrame by row is roughly 30x slower than by column in Chip's example (~2.4s vs ~0.07s on the same data). Converting to a NumPy `ndarray` makes row iteration fast again. If your code feels slow iterating pandas rows, this is probably why.

**Axis B: Text vs. binary**

| Property | Text (CSV, JSON) | Binary (Parquet, Avro, Protobuf, Pickle) |
|----------|-----------------|------------------------------------------|
| Human-readable | Yes | No (hex bytes when opened in a text editor) |
| File size | Larger | Smaller |
| Use when | Small data, debugging, interchange between systems with no shared schema | Scale, performance, compact storage |

**Illustrative size difference** (treat as directional, not exact): Chip's CSV → Parquet conversion took a file from 14 MB to 6 MB. AWS documentation (circa 2021) claimed Parquet is "up to 2x faster to unload and uses up to 6x less storage in S3" vs. text formats.

**Common format pairings to remember:**

| Format | Binary/Text | Typical use |
|--------|-------------|-------------|
| JSON | Text | Everywhere — configs, web APIs, flexible data |
| CSV | Text | Ad-hoc data interchange; *avoid for float-heavy data* (precision loss) |
| Parquet | Binary | Analytics, ML feature stores, data lakes (Hadoop, Redshift) |
| Avro | Binary | Hadoop ecosystem, schema evolution |
| Protobuf | Binary | Google services, TensorFlow (TFRecord) |
| Pickle | Binary | Python/PyTorch serialization; *avoid for anything security-sensitive or cross-language* |

**CSV warning:** CSV silently loses float precision (e.g., `0.12345678901232323` may round to `0.12345678901`). For any numeric data where precision matters, use Parquet or another binary format.

### Step 2.2 — Data model decision

Three models. Pick based on your query pattern, not tradition.

| Model | Structure | Pick when | Avoid when |
|-------|-----------|-----------|------------|
| **Relational** | Tables with fixed schema; joins across tables | Data is uniform and relationships are stable; strong analytics need; need SQL tooling | Schema changes often; you need to join 5+ tables for basic queries |
| **Document** | Self-contained JSON/BSON blobs; one record = one document | Each record is self-contained (user profile, product, order); schemas vary across records; reads are "fetch the whole thing" | Cross-document queries are common; data has lots of relationships |
| **Graph** | Nodes + edges; relationships are first-class | Relationships *are* the query ("find everyone born in X," multi-hop connection finding, recommendation via graph traversal) | Primary queries are tabular aggregations |

**Decision shortcut:** ask what your dominant query looks like.
- "Give me all rows where X and Y join on Z" → relational
- "Fetch this user's full profile" → document
- "Who is connected to whom through N hops?" → graph

**Mixing is normal.** PostgreSQL and MySQL both support relational + document in the same database. You don't have to pick one model for your whole system.

### Step 2.3 — Structured vs. unstructured / warehouse vs. lake / ETL vs. ELT

These are the same decision cluster, viewed from three angles. Decide them together.

**Where does schema responsibility live?**

| Approach | Schema enforced at... | Storage | Pipeline |
|----------|----------------------|---------|----------|
| Structured / warehouse / ETL | Write time | Data warehouse | Extract → **Transform** → Load |
| Unstructured / lake / ELT | Read time (by whichever app reads it) | Data lake | Extract → Load → **Transform later** |

**Questions to decide:**

- [ ] Is our data schema stable, or changing constantly?
- [ ] Do we have multiple downstream apps with different needs? (More apps → favor lake; they each transform as needed.)
- [ ] How much discipline do we have around writing good transform code? (Lakes rot fast without it — "dump everything and figure it out later" becomes "nobody can find anything.")
- [ ] Can we afford the storage cost of keeping raw + transformed copies?

**Hybrid: data lakehouse.** Databricks and Snowflake both offer this — combine lake's flexibility with warehouse's management. Worth evaluating instead of picking pure lake or pure warehouse.

### Step 2.4 — Sanity checks before committing

Before locking in format + model + storage choice:

- [ ] Have I matched format to the *dominant* access pattern, not a hypothetical one?
- [ ] Have I considered whether my data is likely to change schema? (If yes, don't go pure relational-warehouse-ETL.)
- [ ] Have I checked the precision / encoding behavior of my chosen format for my actual data types? (CSV + floats = pain.)
- [ ] For any binary format: does my team have the tooling to inspect it when debugging? (A `.parquet` file is useless in `cat`; make sure people have `parquet-tools` or pandas handy.)

---

## Task 3: Design Inter-Service Dataflow

**Use when:** Designing how services in an ML system communicate — feature engineering service sending to prediction service, monitoring pulling from both, etc. Usually done once the service boundaries are drawn.

### Step 3.1 — Pick the dataflow mode for each service-to-service link

Three options. These aren't exclusive; a real system will use all three for different links.

| Mode | How it works | Latency | Best for | Failure mode |
|------|--------------|---------|----------|--------------|
| **Through database** | Producer writes; consumer reads | Slow (DB I/O) | Batch handoffs, non-latency-critical pipelines, simple case | Requires both services to access same DB (infeasible across org boundaries) |
| **Through services (request-driven)** | Consumer sends request to producer; producer returns data. Typically REST (public APIs) or RPC (internal, same datacenter) | Network-bound | Logic-heavy systems; clear consumer-producer relationships | Synchronous: if target is down, caller fails. Doesn't scale well with many services — n services → O(n²) request paths |
| **Through real-time transport (event-driven)** | Producer publishes event to broker; consumers subscribe. Kafka, Kinesis (pubsub); RabbitMQ (message queue) | Low (in-memory) | Data-heavy systems; many consumers of the same data; asynchronous decoupling | Requires operating a broker; retention policy must be decided |

### Step 3.2 — Decision rule: request-driven vs. event-driven

Chip's rule of thumb:
- **Logic-heavy system** (few services, each doing complex transformations, clear caller-callee) → request-driven.
- **Data-heavy system** (many services all consuming overlapping data, fan-out patterns) → event-driven.

**Warning sign that you need event-driven:** you're drawing the service graph and every service is calling every other service. With 3 services and fan-out needs, you already have 6 request paths. At 10 services, it's unmanageable. Introducing a broker collapses this to 10 producer-to-broker edges.

### Step 3.3 — Consequence: batch vs. stream processing

Your dataflow choice largely determines your feature-computation mode.

| Dataflow | Typical feature mode | Feature type |
|----------|---------------------|--------------|
| Database-based | Batch processing (MapReduce, Spark) | **Static features** — slow-changing (driver rating, user tenure, historical averages) |
| Real-time transport | Stream processing (Flink, KSQL, Spark Streaming) | **Dynamic features** — fast-changing (current availability, last-N-minutes counts, right-now state) |

**Most production ML systems need both.** Driver rating (batch/static) + current driver count in area (stream/dynamic) both feed the price model. You need infrastructure that computes both *and joins them* at inference time. That joining is where a lot of real-world pain lives.

**Stream processing gotchas:**
- Stream compute engines are harder to operate than batch engines. Consider that when staffing.
- Simple stream compute can use Kafka's built-in capabilities; anything complex (many joins, aggregations across dimensions) needs Flink / KSQL / Spark Streaming.
- Stream has one real advantage over batch: **stateful computation**. A 30-day user engagement metric recomputed daily in batch = 30 days of data every day. Stream = compute new data + join with yesterday's result. Much cheaper at scale.

### Step 3.4 — Pubsub vs. message queue

If you go event-driven, pick one:

| Property | Pubsub (Kafka, Kinesis) | Message queue (RabbitMQ, RocketMQ) |
|----------|------------------------|-----------------------------------|
| Producer knows consumer? | No — publishes to topic | Sometimes — message has intended consumer |
| Retention | Usually retained N days then discarded or archived | Usually consumed and removed |
| Pattern | Broadcast / fan-out | Point-to-point work distribution |

**Decision shortcut:** if many services want the same data independently, pubsub. If one message needs exactly one consumer (task distribution), message queue.

### Step 3.5 — Questions to answer in dataflow design

- [ ] For each service-to-service link: what's the latency budget? (Drives mode.)
- [ ] Are any consumers outside our organization? (Rules out shared-database mode.)
- [ ] What's the blast radius if the producer goes down? (Request-driven couples availability; event-driven decouples it.)
- [ ] Which features are static (batch) vs. dynamic (stream)? Where do we join them?
- [ ] If we need a broker: pubsub or message queue? What retention policy?
- [ ] Who operates the broker? (This is not zero-op infrastructure.)

---

## Task 4: Write Data System Reliability and Workload Requirements

**Use when:** Producing scoping documents, writing RFCs, or defining acceptance criteria for the data layer of an ML system. This is requirements-level, not implementation — use it in conjunction with Ch. 1 Task 2 (Scoping a Production ML Project).

### Step 4.1 — Specify the reliability posture per system component

Use ACID or BASE as your vocabulary. Write which one each component needs.

**ACID** — strong guarantees, typical for transactional components:
- **Atomicity** — all steps in a transaction succeed together or all fail together. (Payment + driver assignment: if payment fails, don't assign driver.)
- **Consistency** — all transactions follow predefined rules. (Transaction must come from a valid user.)
- **Isolation** — concurrent transactions behave as if they ran one at a time. (Two users can't book the same driver simultaneously.)
- **Durability** — committed transactions survive system failure. (User orders ride, phone dies — ride still comes.)

**BASE** — weaker guarantees, typical for analytics / large-scale reads:
- **Basically Available** — system available most of the time.
- **Soft state** — state may be stale.
- **Eventual consistency** — data converges over time, but reads may be temporarily inconsistent.

**Decision rule:** if the component handles money, user accounts, bookings, or anything where a lost or inconsistent write is a real-world problem → ACID. If the component serves analytics, dashboards, or ML features where stale-by-seconds is fine → BASE.

### Step 4.2 — Classify workload: OLTP, OLAP, or both

**OLTP — OnLine Transaction Processing.** High-volume, low-latency, individual-record reads/writes. Typically row-major databases. User-facing actions go here.

**OLAP — OnLine Analytical Processing.** Aggregations across many rows for analytics. Typically column-major databases. Dashboards, feature computation, reporting go here.

**Modern reframing (important):** the strict OLTP/OLAP split is outdated. As of ~2021:
- Transactional databases can handle analytical queries (CockroachDB).
- Analytical databases can handle transactional queries (Iceberg, DuckDB).
- Storage and compute are being decoupled (BigQuery, Snowflake) — data lives in one place, different engines on top query it differently.

**Implication for requirements:** don't over-specify. Don't demand "we need an OLTP database and a separate OLAP database" if a modern HTAP or decoupled-storage system fits. Specify the workload properties (latency, consistency, query types) and let the implementation team pick the engine.

### Step 4.3 — Requirements checklist

For each data-storing component in the system, answer:

- [ ] What's the workload: transactional, analytical, or both?
- [ ] What's the reliability posture required: ACID, BASE, or somewhere specific in between?
- [ ] What's the read latency target (p95/p99)? The write latency target?
- [ ] What's the consistency requirement? (Strong / eventual / session?)
- [ ] What's the durability requirement? (Zero data loss / some loss acceptable / RPO in minutes?)
- [ ] What's the availability SLO?
- [ ] Are we coupling storage to a specific compute engine, or keeping them decoupled?

### Step 4.4 — The "online" term is overloaded — be specific

"Online" in the data world can mean three different things:
- **Online processing** — data immediately available for I/O.
- **Nearline** — data retrievable quickly without human intervention.
- **Offline** — data needs human intervention to become available.

And separately, "online" sometimes means "deployed in production" (e.g., "this feature is online now"), and sometimes means "connected to the internet."

**When writing requirements, say the specific latency or availability tier you mean.** Don't say "online features." Say "features available with p99 latency < 50ms from the feature store."

---

## Appendix A: Background Context (not task-critical)

### The declarative ML sidebar

Chip mentions Ludwig (Uber) and H2O AutoML as declarative ML frameworks that let you specify schema + task and have the system find a model. The sidebar concludes that declarative ML abstracts away model development, but model development isn't the hard part — feature engineering, data processing, evaluation, shift detection, and continual learning are. *As of 2026:* this take still holds; AutoML hasn't displaced custom ML development in production at meaningful scale. Skip this topic unless someone specifically proposes AutoML as a solution.

### Relational model history

Edgar F. Codd invented the relational model in 1970. Relations are sets of tuples. Relations are unordered (shuffling rows/columns preserves the relation). SQL is a declarative query language that works on top of this model but deviates from pure relational algebra (SQL tables allow duplicates, true relations don't). Normal forms (1NF, 2NF, etc.) formalize how to structure relations to reduce redundancy. Practitioners rarely apply normal forms by name — the concept that matters is "separate repeated data into its own table and reference it."

### Dated data points (treat as illustrative, not current)

All circa 2019–2021 unless noted. Trends hold; specific numbers have moved.

- **AWS S3 Standard vs. Glacier pricing:** ~5x difference in per-GB cost (2021). Still roughly directionally correct but the exact ratio has shifted.
- **Parquet vs. text size:** "up to 6x less storage" per AWS's claim. Chip's concrete example: 14 MB CSV → 6 MB Parquet.
- **Pandas row iteration speed:** 0.07s by column vs. 2.41s by row on Chip's example data. The *ratio* (~30x) is the lesson; exact numbers depend on hardware and data.
- **Apple IDFA opt-in:** took effect early 2021, significantly reduced third-party mobile tracking. This one actually happened as predicted and reshaped the ads industry.
- **CAID (China's tracking workaround):** 2021-era example; probably superseded by now. The general point — privacy arms races happen — still applies.
- **Stackshare company lists for Kafka / RabbitMQ:** skip; visual-only and stale. Both tools are still widely used in 2026.

### Things we didn't save (and why)

- **Full Wikipedia-style walkthrough of normal forms (1NF, 2NF).** Pointer to the concept is enough.
- **REST vs. RPC detailed comparison.** The decision rule ("REST for public APIs, RPC for internal same-datacenter") is the takeaway. Details of HTTP methods, Idempotence, etc., are not this chapter's contribution.
- **Detailed history of declarative ML.** Tangent, self-undercut by Chip, and dated.

---

## Appendix B: Cross-chapter connections

Populated as later chapter skills are built.

### From Ch. 3 — Training Data Strategy

**Refinements to Ch. 2 concepts:**
- **Ch. 2 Task 1's source taxonomy** feeds directly into Ch. 3 Task 1's sampling decisions. Streaming user input (Ch. 2) → reservoir sampling (Ch. 3). Internal DB (Ch. 2) → any probability method (Ch. 3). Third-party data (Ch. 2) → inherit whatever sampling the vendor did; may need re-sampling.
- **Ch. 2 Task 3's batch vs. stream processing** ties to Ch. 3 Task 2's active learning. Real-time/stream data is where active learning shines — you can query the model on fresh data and choose what to label.

**New concepts from Ch. 3 that extend Ch. 2:**
- **Data lineage** (Ch. 3 Task 3) extends Ch. 2 Task 2's versioning concern. Versioning data isn't just about schema — it's about origin and annotator too. When picking storage format (Ch. 2 Task 2), think about whether it supports lineage metadata per record.
- **Natural labels** (Ch. 3 Task 2) are usually user-behavior data (Ch. 2 Task 1 category 3). Same data, different use: Ch. 2 treats it as a source to manage; Ch. 3 treats it as free labels. Both framings apply.

**Cross-links for spine skills:**
- *Designing the data strategy* (spine) will pull Ch. 2's infrastructure decisions + Ch. 3's training-data decisions as one integrated workflow.

### From Ch. 4 — Feature Engineering Decisions

**Refinements to Ch. 2 concepts:**
- **Ch. 2 Task 3's static vs. dynamic feature distinction** is the infrastructure layer beneath Ch. 4's feature engineering. Static features (driver rating, user tenure) are batch-computed; dynamic features (current driver count, last-N-minutes activity) are stream-computed. When picking between batch and stream in Ch. 2 Task 3, the deciding factor is often *what features you'll need engineered*, which is a Ch. 4 question.
- **Ch. 2 Task 1's source classification** maps to feature provenance in Ch. 4. User-input features are noisy and need heavy validation; system-generated features are reliable but voluminous; third-party features have hidden sampling biases.

**New concepts from Ch. 4 that extend Ch. 2:**
- **Feature stores** (post-book context noted in Ch. 4 Appendix A) are the operational glue between Ch. 2's data infrastructure and Ch. 4's feature engineering. They handle the train-serve consistency problem, materialize features for low-latency serving, and version feature definitions across teams. Ch. 9 likely covers this.
- **The hashing trick** (Ch. 4 Task 2) is especially useful for streaming/dynamic features with unbounded categories. Pairs naturally with Ch. 2's stream processing (Apache Flink, KSQL).
- **Train-serve skew prevention** (a side effect of Ch. 4 Task 3's leakage prevention) requires Ch. 2's storage infrastructure to support it — same scaling stats applied at training and serving.

**Cross-links for spine skills:**
- *Designing the data strategy* (spine) will tie Ch. 2 + Ch. 3 + Ch. 4 together. Ch. 2 = *where* data lives and flows; Ch. 3 = *what* training data we curate; Ch. 4 = *how* we transform features for the model.

### From Ch. 5 — Model Development and Evaluation

**Refinements to Ch. 2 concepts:**
- **Ch. 2 Task 3's batch vs. stream processing decision** is what produces the static and dynamic features that feed Ch. 5 Task 1's model framing. The infrastructure choice (batch / stream) determines what kinds of features the model will see at serving time.
- **Ch. 2 Task 4's reliability and workload requirements** inform Ch. 5 Task 3's distributed training. SSGD requires reliable inter-machine communication and synchronization (closer to ACID); ASGD relaxes that (closer to BASE). Pipeline parallelism requires careful coordination of data flow between stages.

**New concepts from Ch. 5 that extend Ch. 2:**
- **Distributed training infrastructure (Ch. 5 Task 3)** is a heavy consumer of Ch. 2's data infrastructure. Data parallelism requires fast distributed I/O. Model parallelism requires reliable inter-node networking. Both interact with the storage and dataflow choices made in Ch. 2.

### From Ch. 6 — Deployment and Inference Decisions

**Refinements to Ch. 2 concepts:**
- **Ch. 2 Task 3's static vs. dynamic features** maps directly to **Ch. 6 Task 1's "online with batch features only" vs. "online with streaming features"** decision. The Ch. 2 infrastructure decision determines what Ch. 6 serving paradigms are even feasible — without a stream computation engine in Ch. 2, you can't do streaming-feature online prediction in Ch. 6.
- **Ch. 2 Task 3's batch vs. stream processing** is the upstream architecture that makes **Ch. 6 Task 1's "two pipelines anti-pattern"** possible. If you maintain separate batch (training) and streaming (serving) pipelines for the same features, train/serve skew is inevitable. The fix lives in Ch. 2's infrastructure: unify on Flink/Beam/feature store so the same code runs in both paths.
- **Ch. 2 Task 4's OLTP vs. OLAP framing** loosely maps to Ch. 6's online vs. batch serving. Online serving wants OLTP-like properties (low latency, high availability per request). Batch serving has OLAP-like properties (throughput-oriented, periodic).

**New concepts from Ch. 6 that extend Ch. 2:**
- **Train/serve skew as a deployment-time concern** sharpens Ch. 2's concern about pipeline consistency. Ch. 2 talks about avoiding bugs from divergent data pipelines; Ch. 6 names the specific deployment failure mode this causes and the practical fix (unified pipelines, feature stores).

*Chapters 7–12 pending.*
