# DMLS Ch. 6 — Deployment and Inference Decisions (Task Reference)

Task-oriented notes from Chip Huyen's *Designing Machine Learning Systems*, Chapter 6. Organized around the decisions you make when taking a trained model to production users.

<!--
METADATA (for hybrid spine-skill assembly)
source: DMLS Ch. 6 — Model Deployment
tasks_supported:
  - task-1-choose-a-serving-paradigm
  - task-2-decide-where-to-run-inference
  - task-3-compress-a-model-for-fast-or-small-inference
  - task-4-compile-and-optimize-for-production-hardware
spine_topics_likely_to_pull_from_this_chapter:
  - deploying-and-serving (primary)
  - operating-in-production (online prediction connects to monitoring)
  - infrastructure-and-scaling (compilation, edge hardware, cost optimization)
-->

**Four tasks this reference supports:**
1. **Choose a Serving Paradigm** — pick online (synchronous), batch (asynchronous), or hybrid; decide whether streaming features are needed
2. **Decide Where to Run Inference** — cloud, edge, or in-browser; weigh latency, cost, privacy, and connectivity
3. **Compress a Model for Fast/Small Inference** — apply low-rank factorization, knowledge distillation, pruning, or quantization
4. **Compile and Optimize for Production Hardware** — understand the IR/compiler stack, decide when ML-based optimization or browser deployment is worth it

Each task is self-contained. Background and dated points are in Appendix A.

**Dependency note:** This chapter assumes you have a trained model (Ch. 5), features computed via batch or stream pipelines (Ch. 2), and a production-readiness evaluation completed (Ch. 5 Task 5). It feeds into Ch. 7 (monitoring) and Ch. 8 (continual learning).

---

## Task 1: Choose a Serving Paradigm

**Use when:** Designing the serving layer for a new model, or revisiting an existing one because latency, cost, or freshness has become a problem. This is the most consequential deployment decision — it shapes infrastructure, cost, user experience, and what the model can do.

### Step 1.1 — Understand the three options

| Paradigm | How it works | Optimized for | Typical use |
|---------|-------------|--------------|------------|
| **Batch (asynchronous)** | Predictions generated periodically (every N hours, daily); stored in DB/files; retrieved on demand | Throughput | Recommendations, churn predictions, lead scoring — anything where freshness in minutes/seconds isn't required |
| **Online (synchronous)** | Predictions generated on-demand when a request arrives | Latency | Translation, search ranking, fraud detection, voice assistants, autonomous systems |
| **Hybrid** | Precompute predictions for popular/predictable queries; generate the long tail online | Both, by use case | E-commerce (popular items batched, niche ones online); content platforms |

**Online prediction has two sub-flavors:**
- *Online with batch features only:* prediction service queries pre-computed features from a warehouse. Simpler infrastructure.
- *Online with streaming features* (sometimes called "streaming prediction"): real-time pipeline computes features as events happen, feeds them into the model. Requires Apache Flink, Kafka Streams, or similar. Necessary for use cases needing right-now state (current driver count, last-N-minutes activity).

### Step 1.2 — Decide based on application requirements

Walk these questions in order. The first "yes" usually settles the paradigm.

| Question | If yes → | Reasoning |
|---------|---------|----------|
| Are predictions needed in real-time (sub-second to seconds)? | Online | Batch can't meet latency budgets |
| Are queries unpredictable (can't enumerate inputs in advance)? | Online | Translation, search, anything user-generated |
| Does the model need right-now state (current activity, fresh signals)? | Online with streaming features | Streaming features require real-time pipeline |
| Are predictions for a known finite set of users/items, computed periodically? | Batch | Recommendations are the canonical case |
| Is the model too slow/expensive to run online for all queries? | Batch (or hybrid) | Batch is a workaround for inference cost |
| Do most users not interact with the system on any given day? | Online (or hybrid) | Generating predictions for inactive users wastes compute |
| Are some queries popular (predictable) and others rare (unpredictable)? | Hybrid | Cache the popular ones; serve the long tail online |

**Concrete failure modes when paradigms mismatch use cases:**
- *Batch when online is needed:* Netflix can't update recommendations mid-session if next batch is hours away. User searches "comedy" → still gets horror recommendations until tomorrow.
- *Batch when no one queries:* generating predictions for 31M users when only 622K order daily wastes 98% of compute.
- *Online when batch would do:* paying for synchronous inference infrastructure when predictions could be precomputed cheaply.

### Step 1.3 — If choosing online, plan for fast inference + real-time pipeline

Online prediction with acceptable latency requires both:

1. **A model fast enough to meet latency targets.** Most consumer apps mean sub-100ms p95 (Ch. 1 Task 5 has the latency framing). If your model can't hit this, see Tasks 3 and 4.
2. **A pipeline that delivers features in time.** If you need streaming features, you need real-time transport (Kafka, Kinesis) and stream computation (Flink, KSQL). See Ch. 2 Task 3.

**The "two pipelines" anti-pattern.** A common bug source — separate batch pipeline for training, separate streaming pipeline for inference, often maintained by different teams (ML team owns training; deployment team owns serving). Changes in one pipeline don't replicate to the other → train/serve feature skew → silent prediction failures.

**Fix:** unify the pipelines. Apache Flink, Beam, or modern feature stores (Tecton, Feast) can run the same feature transformations in both training and serving paths. This connects to Ch. 4 Task 3's leakage prevention — train/serve skew is a leakage cousin.

### Step 1.4 — Don't lock in a paradigm prematurely

Online and batch aren't mutually exclusive. Common patterns that work well:

- **Start batch, move to online as latency requirements emerge.** Often easier than the reverse.
- **Hybrid by query type.** Popular queries → cache. Long tail → online.
- **Hybrid by user segment.** Active users → online (worth the cost). Inactive users → no predictions, or batch.
- **Online prediction with cached predictions as a fallback.** If the online pipeline fails or times out, return a recent cached prediction.

### Step 1.5 — Questions to answer before committing

- [ ] What's the p95/p99 latency budget at the product layer? (Cascades down to inference budget.)
- [ ] How fresh do predictions need to be? (Seconds, minutes, hours, days?)
- [ ] Can we enumerate the universe of queries in advance, or are they user-generated?
- [ ] What fraction of our user base actually triggers predictions on a given day?
- [ ] Do we need streaming features, or can we get by with batch features?
- [ ] If online, can our current model meet the latency budget? If not, do we compress (Task 3), optimize (Task 4), or pick a smaller model (Ch. 5 Task 2)?
- [ ] Are training and serving feature pipelines the same code, or are we maintaining two?

---

## Task 2: Decide Where to Run Inference

**Use when:** You've picked a serving paradigm and now need to choose where the compute happens — cloud, on-device (edge), or in the browser. This decision drives cost, privacy posture, latency profile, and what hardware you can target.

### Step 2.1 — Compare the three locations

| Location | What it means | Strengths | Weaknesses |
|---------|--------------|----------|------------|
| **Cloud** | Inference runs on managed cloud servers (AWS, GCP, Azure, or self-hosted) | Easy to set up; scalable; no client-side constraints; centralized monitoring | Expensive at scale; requires reliable network; data must leave the device (privacy); subject to network latency |
| **Edge / on-device** | Inference runs on the user's device (phone, laptop, smartwatch, vehicle, embedded device) | Works offline; no network latency; data stays local (privacy); no per-inference cloud cost | Constrained compute, memory, battery; need to support diverse hardware; harder to push model updates |
| **Browser (WASM/WebGPU)** | Inference runs in the user's browser, no app install required | Hardware-agnostic (works wherever browsers run); no native app needed; some privacy benefits | Slower than native (~45–55% slower than native via WASM, per 2021 study); model size limits; cold start |

### Step 2.2 — Decide based on constraint priorities

Walk these questions. The strongest constraint usually determines the location.

| Constraint | Forces you toward |
|-----------|-------------------|
| Need to work offline or in poor connectivity | Edge |
| Strict data residency or regulatory privacy (GDPR, EU AI Act, healthcare) | Edge (or private cloud) |
| Cloud bill is becoming unsustainable | Edge (push compute to users) |
| Network latency is the bottleneck (already, or will be) | Edge — network can be seconds; edge inference is bounded |
| Model is too large/expensive to run on user devices | Cloud |
| Need to update the model frequently | Cloud (edge updates require app updates) |
| Need to centrally monitor and debug predictions | Cloud (edge monitoring is a harder problem) |
| Need to ship cross-platform without per-OS native apps | Browser (WASM/WebGPU) |

**Cost reality check (illustrative, circa 2018–2021):** Pinterest, Infor, Intuit each spent hundreds of millions annually on cloud bills. Small/medium companies typically $50K–$2M/year. With LLM serving in 2024–2026, these numbers have grown substantially. If you're at scale and ML compute is a major cost line, edge or hybrid is worth serious evaluation.

**Privacy reality check:** ~80% of companies experienced a cloud data breach in an 18-month period (Security magazine survey, circa 2021). Edge reduces but doesn't eliminate privacy risk — physical device theft becomes a vector instead.

### Step 2.3 — If edge, verify the device can actually run the model

- [ ] Does the device have enough compute (CPU/GPU/NPU) to run inference within latency target?
- [ ] Does the device have enough memory to load the model into RAM?
- [ ] Will inference drain the battery faster than acceptable?
- [ ] Can we ship updates to the model? (App store review cycles, force-update flows.)
- [ ] What hardware fragmentation do we need to support? (Different phone chips, different OS versions.)

If the answers force the model to be smaller, fewer parameters, or different architecture: see Task 3 (compression) and possibly Ch. 5 Task 2 (revisit model selection).

### Step 2.4 — Browser deployment specifics

If you choose browser deployment:

| Tool | Use for |
|------|--------|
| **JavaScript-based** (TensorFlow.js, Synaptic, brain.js) | Simple models; quick prototypes |
| **WebAssembly (WASM)** | Compiled, performant code in browser; supported on ~93%+ devices. Faster than JS, slower than native. |
| **WebGPU** *(post-book; 2023+)* | Modern alternative for browser ML; significantly faster than WASM for large models. transformers.js, MLC Web-LLM use this. |

**The pitch for browser deployment:** if it runs in a browser, it runs anywhere. No platform-specific apps. No worrying about Apple switching from Intel to ARM. The cost is performance — even WASM is ~45–55% slower than native (Jangda et al., circa 2021).

### Step 2.5 — Questions to answer before committing

- [ ] What's our latency budget, and does the network add unacceptable overhead in our use case?
- [ ] What's our cloud cost trajectory, and at what scale does it become unsustainable?
- [ ] What are our regulatory and privacy constraints around user data?
- [ ] How often do we need to update the model? (Frequent updates favor cloud.)
- [ ] What hardware constraints do our target users have? (Old phones, low-end devices?)
- [ ] Is browser deployment a viable cross-platform shortcut, or do we need native performance?

### Step 2.6 — Hybrid deployment is common

Few production systems run purely cloud or purely edge. Common patterns:

- **On-device for speed, cloud for fallback.** Edge handles common queries; cloud handles edge cases or high-confidence-required ones.
- **Cloud for training, edge for inference.** Standard for any production-grade edge ML.
- **Cloud for heavy models, edge for lightweight personalization.** Big foundation model in cloud; lightweight personalization model on device.

---

## Task 3: Compress a Model for Fast/Small Inference

**Use when:** Your model is too slow for online serving, too large for edge devices, too expensive to run, or all of the above. Compression is one of three levers for faster inference (the others: faster hardware, optimized compilation — see Task 4).

### Step 3.1 — Pick a compression technique

Four main techniques. They're often combined.

| Technique | What it does | Best for | Tradeoffs |
|-----------|-------------|---------|-----------|
| **Quantization** | Reduce bits per parameter (32→16→8→1) | The default. Most general, most widely used. Standard for edge inference. | Rounding errors, range limits; usually small accuracy loss with proper calibration |
| **Knowledge distillation** | Train smaller "student" to mimic larger "teacher" model | When you have a strong teacher model and want a much smaller deployment artifact | Requires a teacher; sensitive to architecture and task; not always universally applicable |
| **Pruning** | Remove unimportant weights (set to 0) or whole nodes | When the model is over-parameterized; can reduce non-zero parameters >90% | Active debate about whether the value is in retained weights or in the discovered architecture; sparse-architecture inference may need specialized hardware |
| **Low-rank factorization** | Replace high-dim tensors with lower-dim ones | When you control model architecture and can use specialized blocks (depthwise/pointwise convolutions) | Architecture-specific (mainly CNNs); requires architectural expertise to design |

### Step 3.2 — Quantization — the workhorse

Most practical compression technique. Mix-and-match by training stage and target precision.

**Precision levels:**

| Precision | Bits | Use |
|-----------|------|----|
| Single (FP32) | 32 | Default training; standard |
| Half (FP16) | 16 | Mixed-precision training; ~2x memory savings |
| Bfloat16 | 16 | Google TPU's preferred format; better numerical range than FP16 |
| Int8 | 8 | Common for inference on edge; ~4x memory savings vs FP32 |
| Binary (1-bit) | 1 | Extreme compression (BinaryConnect, Xnor-Net); accuracy tradeoffs |

**Quantization timing:**
- *Quantization-aware training (QAT):* train with low-precision representation. Best accuracy but more setup work.
- *Post-training quantization:* train in FP32; quantize after for inference. Easier; sometimes sufficient.

**Tools (for free in major frameworks):**
- TensorFlow Lite (post-training and QAT for mobile)
- PyTorch Mobile
- NVIDIA TensorRT (server-side inference quantization)

**Concrete benchmark (Roblox case, circa 2021):** for a BERT NLP service handling 25K+ inferences/sec at <20ms latency, quantization from FP32 to INT8 delivered **7x latency reduction and 8x throughput increase**. Bigger gains than distillation or input-shape changes alone.

### Step 3.3 — Knowledge distillation — when you have a strong teacher

Train a small "student" model to mimic the predictions of a large "teacher" model.

**Concrete benchmark:** DistilBERT — 40% smaller than BERT, retains 97% of language understanding capability, runs 60% faster.

**When distillation works well:**
- [ ] You have a strong, accurate teacher model already trained
- [ ] You can afford to train (or have access to) the smaller student
- [ ] The student architecture can plausibly capture the teacher's behavior
- [ ] You don't need explicit guarantees on accuracy — distillation loses some quality

**When to skip:**
- No strong teacher model exists for your task
- Teacher and student architectures are too different (sometimes works — random forest student, transformer teacher — but often not)
- You need exact reproduction of the teacher's outputs

### Step 3.4 — Pruning — for over-parameterized models

Remove parameters or nodes that contribute little to predictions.

**Two flavors:**
- *Weight pruning:* set unimportant weights to 0; architecture unchanged but sparse
- *Structural pruning:* remove entire nodes/layers; changes architecture, reduces parameter count

**Effectiveness:** can reduce non-zero parameter counts >90% without accuracy loss in well-designed setups.

**Open question (Liu et al. vs. Zhu et al.):** is pruning's value in the retained "important" weights, or in discovering a better architecture that should be retrained from scratch as a dense model? Practical answer: try both for your case.

**Practical caveat:** sparse weights need hardware/library support to actually run faster. Many platforms still treat sparse weights like dense ones — you save storage but not compute time. Check your inference target's sparse-matrix support.

### Step 3.5 — Low-rank factorization — architecture-specific

Replace high-dimensional tensors with lower-dimensional ones in a structured way.

**MobileNets example:** standard convolution `K × K × C` decomposed into depthwise (`K × K × 1`) and pointwise (`1 × 1 × C`). Reduces parameters from `K² · C` to `K² + C`. With K=3, that's an 8–9x reduction.

**SqueezeNet example:** AlexNet-level accuracy with 50x fewer parameters via 1×1 convolutions and other architecture tricks.

**When to use:**
- You're designing a new model architecture for edge constraints
- The use case is CNN-based (most low-rank work is CNN-specific)
- You have architectural expertise on the team

**When to skip:**
- You're using a pre-trained foundation model
- Your bottleneck isn't really parameter count

### Step 3.6 — Decision shortcut

Apply in roughly this order:

1. **Try quantization first.** Most general, easiest to apply, biggest typical wins.
2. **If model is still too large/slow, look at distillation** — especially for transformer / NLP / vision models with well-known teachers (DistilBERT, MobileBERT, etc.). Often pre-distilled smaller models exist; use those.
3. **If still constrained, consider pruning** — but verify your inference target supports sparse computation.
4. **Use low-rank factorization** when designing new architectures for edge from the start, not as a retrofit.

Often you'll combine: quantize a distilled model. Or prune then quantize.

### Step 3.7 — Questions to answer before compressing

- [ ] What's our latency target, and how far is the current model from it?
- [ ] What's our accuracy floor — how much accuracy can we afford to lose?
- [ ] Is there an existing compressed version (DistilBERT, MobileBERT, etc.) for our base model?
- [ ] Does our deployment target (edge device, server inference engine) actually support quantized/sparse inference?
- [ ] Can we benchmark each compression technique on representative production traffic?

---

## Task 4: Compile and Optimize for Production Hardware

**Use when:** You've trained a model in one framework (PyTorch, TensorFlow, JAX) and need to run it efficiently on specific hardware (server GPU, edge accelerator, browser, mobile CPU). Compilation is often invisible — handled by the framework — until edge deployment or performance-critical serving forces you to confront it.

### Step 4.1 — Understand the framework × hardware problem

You have:
- M frameworks (PyTorch, TensorFlow, JAX, scikit-learn, LightGBM, etc.)
- N hardware backends (CPU, GPU, TPU, edge accelerators, FPGAs, ASICs)

Without intermediate representations (IRs), you'd need M×N pairs of optimized code. Adding a new framework or hardware backend would explode the matrix.

**Each backend has different compute primitives and memory layouts:**
- CPUs: scalar primitives (one number at a time, historically)
- GPUs: vector primitives (one-dimensional vectors)
- TPUs: tensor primitives (two-dimensional tensors)
- Different L1/L2/L3 cache layouts and buffer sizes

A convolution operator runs very differently on these backends. Generic code won't be efficient.

### Step 4.2 — The compiler stack — IRs as the middle layer

| Layer | Examples | Purpose |
|------|---------|--------|
| **High-level IR** | XLA HLO, TensorFlow Lite, TensorRT, ONNX | Hardware-agnostic; represents the computation graph |
| **Low-level IR** | LLVM, NVCC | Hardware-specific; closer to machine code |
| **Machine code** | x86, ARM, CUDA, PTX | Native to the target hardware |

The translation from high-level (your model code) → machine code is called **lowering**, not "translating," because there's no one-to-one mapping. The compiler progressively transforms the representation through multiple IRs.

### Step 4.3 — Pick local optimization techniques to apply

Even after lowering, the generated code may not be efficient. Standard local optimizations:

| Technique | What it does |
|-----------|-------------|
| **Vectorization** | Use hardware SIMD instructions to operate on multiple contiguous elements simultaneously |
| **Parallelization** | Split work across threads/cores |
| **Loop tiling** | Reorder data accesses to leverage cache layout (hardware-dependent — what's good on CPU isn't good on GPU) |
| **Operator fusion** | Combine multiple operators into one to avoid redundant memory access (vertical: sequential ops; horizontal: parallel ops on the same input) |

These are typically applied automatically by compilers like XLA, TensorRT, or TVM.

### Step 4.4 — Decide whether ML-based optimization is worth it

For complex models on specific hardware, hand-tuned heuristics may not be optimal. **ML-based compilation** (autoTVM, MLIR ML passes) treats compilation as a search problem.

**How autoTVM-style optimization works:**
1. Break the computation graph into subgraphs
2. Predict execution time for each subgraph (cost model trained on real measurements)
3. Allocate search budget per subgraph
4. Stitch the best subgraph executions together

**Concrete benchmark:** autoTVM beats cuDNN on ResNet-50 (NVIDIA TITAN X) after ~70 trials. Once optimized, the result can be cached and reused for that model + hardware pair.

**When ML-based optimization is worth it:**
- [ ] Model is going to production at scale (one-time optimization cost amortizes)
- [ ] Target hardware is specific and stable (you'll deploy on this hardware for a while)
- [ ] Model architecture isn't already heavily hand-optimized by the hardware vendor (which is the case for ResNet-50, BERT, GPT — but not for novel architectures)
- [ ] Search time (hours to days) is acceptable

**When to skip:**
- Quick prototypes where iteration speed matters
- Models that change frequently
- Standard architectures the framework already handles well

### Step 4.5 — Browser deployment via WASM / WebGPU

If you need hardware-agnostic deployment without app installs:

| Approach | Performance | When to use |
|---------|------------|-------------|
| **JavaScript** (TensorFlow.js, brain.js) | Slowest | Quick demos, simple models |
| **WASM** | ~45–55% slower than native (Jangda et al., circa 2021) | Want broad compatibility; can tolerate the perf cost |
| **WebGPU** *(post-book, 2023+)* | Closer to native for GPU-friendly ops | Modern browsers; large models in-browser (transformers.js, MLC Web-LLM) |

**The pitch:** if it runs in a browser, it runs on any device with a modern browser. You don't care if Apple switches from Intel to ARM, or whether the user is on Chrome/Firefox/Safari, or what GPU they have. You just compile to WASM/WebGPU and ship a static asset.

**The cost:** performance is slower than native. For latency-critical applications, native still wins.

### Step 4.6 — Decide whether to bring in optimization engineers

Optimization engineers are hard to hire (need both ML and hardware expertise) and expensive. Most teams won't have one. Compilers (especially ML-based ones) automate much of what optimization engineers used to do manually.

**Default approach for most teams:**
1. Use the framework's default compilation (TensorRT, XLA, TF Lite, Core ML, etc.)
2. If perf is insufficient, try ML-based compilation (TVM, MLC LLM)
3. If still insufficient, evaluate whether the gap justifies hiring optimization expertise

**When you genuinely need optimization engineers:**
- Your scale is large enough that 10–20% perf gains save millions
- Your model is novel and hardware vendors haven't optimized it
- You're deploying to specialized hardware with limited tooling

### Step 4.7 — Don't over-trust benchmarks

Benchmarks like MLPerf measure popular models on standard hardware. **A popular model running fast on a hardware target doesn't mean an arbitrary model will run fast** — the popular model may simply be over-optimized for that benchmark.

When evaluating hardware or compilation options, benchmark *your* model on *your* representative workload, not just published numbers.

### Step 4.8 — Questions to answer before committing to an optimization approach

- [ ] What's the framework's default optimization, and does it meet our perf target?
- [ ] Is our target hardware specific and stable enough to justify ML-based compilation?
- [ ] How often will we update this model? (Frequent updates make optimization investment less valuable.)
- [ ] Do we need browser deployment, or is native acceptable?
- [ ] Have we benchmarked on our actual workload, not just published numbers?

---

## Appendix A: Background Context (not task-critical)

### Six myths Chip debunks at the start of the chapter

Useful framing for stakeholders who haven't deployed ML before. These set expectations:

1. **You only deploy one or two models at a time.** False. Uber has thousands; Google has thousands training concurrently; Booking.com has 150+; Algorithmia (2021) found 41% of 25K+ employee orgs have 100+ models in production.
2. **Model performance stays the same if you don't touch it.** False. ML models age via "concept drift" (data distribution shifts) and software rot.
3. **You won't need to update models often.** False. The right question is "how often *can* I update?" — Etsy 50/day, Netflix 1000s/day, Weibo 10-minute iteration cycles, Alibaba/ByteDance similar.
4. **Most ML engineers don't worry about scale.** False. Most ML engineers work at companies large enough to hit scale challenges (StackOverflow Survey 2019: >50% of devs at companies of 100+ employees).
5. **ML deployment is a single-team activity.** False. Often spans data science, ML engineering, DevOps, infra, with hand-offs that cause communication overhead and debugging difficulty.
6. **Deployment is easy.** True if you ignore all the hard parts. Available-via-cloud-endpoint deployment is easy; production-grade with millisecond latency, 99% uptime, alerting, debugging, and update pipelines is hard engineering.

### LLM serving — major post-book development

Chip wrote the chapter before ChatGPT's release. By 2026, **LLM serving is a distinct sub-discipline** with its own engineering challenges:

- **KV cache management** — autoregressive models accumulate per-request state; memory management is a primary concern
- **Continuous batching** — replacement for static batching; allows new requests to join an in-flight batch
- **Speculative decoding** — small "draft" model proposes tokens; large model verifies; can give 2–3x speedups
- **Paged attention** — virtual memory-style management of attention KV blocks (vLLM)
- **Multi-tenancy with QoS** — many requests, mixed priorities, per-tenant guarantees
- **Long-context engineering** — context windows of 100K–1M+ tokens require specialized handling

Tools that emerged: **vLLM, TGI (Text Generation Inference), SGLang, llama.cpp** (CPU/edge), **MLC LLM** (cross-platform).

The chapter's online vs. batch framing still applies, but LLM serving has added a whole layer of engineering specific to autoregressive transformers. When the conversation is about LLMs specifically, add this context.

### Federated learning

Chapter mentions federated learning as a future direction. Reality check (2026): **promised more than delivered.** Still niche outside specific privacy-critical use cases (mobile keyboard suggestion, some healthcare scenarios). The framing in Task 2 (edge computing for privacy) is more practical than federated learning for most production teams.

### WASM and WebGPU

Chapter advocates WASM as a future direction. Reality check (2026):
- WASM is widely supported (>95% of devices) and used for various non-ML workloads
- For ML specifically, **WebGPU** (released 2023) has emerged as a more performant alternative
- Tools like **transformers.js** and **MLC Web-LLM** run real LLMs in-browser via WebGPU
- WASM is still relevant for CPU-bound inference; WebGPU is the story for GPU-bound model inference in browsers

### Hardware vendor fragmentation

Chapter highlights startups (SambaNova, Graphcore, Cerebras, Habana Labs, etc.) competing for the AI chip market. By 2026, the picture is mixed — some have stalled, some have been acquired, NVIDIA has consolidated dominance for training, and edge inference is fragmented across phone NPUs, Apple Silicon, AMD, Qualcomm, etc. The principle (hardware diversity makes IR/compiler stacks important) holds; specific company names are dated.

### Dated content (treat as illustrative, not current)

- **Cloud bills (Pinterest, Infor, Intuit hundreds of millions/year, ~2018)** — directionally still true; LLM-era costs have grown substantially.
- **Roblox BERT case study** — still illustrative of compression patterns; specific numbers are tied to BERT-era architectures.
- **DistilBERT 40% smaller / 97% capability** — still cited; foundation-model-era distillations have similar tradeoffs but at different scales.
- **Cloud breach statistic (~80%, ~2021)** — directionally true; specific number varies by survey.
- **WASM 93% device support (Sept 2021)** — even higher now; WebGPU emerged after the book.
- **Hardware startup list (Sept 2021)** — heavily dated. Skip the list; keep the meta-point.
- **autoTVM ~70 trials to beat cuDNN** — still illustrative; TVM ecosystem has expanded into MLC LLM and Apache TVM Unity.
- **2025 prediction of 30+ billion edge devices** — already a 2026 reality.
- **TPU/PyTorch support arriving Sept 2020** — historical; the lesson is about framework/hardware support lag.

### Things we didn't save (and why)

- **Detailed history of TensorFlow 1.0 computation graphs** — background context, no decision payoff
- **Specific dollar amounts of hardware startup funding** — ages quickly, illustrative only
- **cuDNN autotune internal mechanics** — curiosity, not action
- **Long discussion of computation graph optimization examples** — the principle (operator fusion, vectorization) is what matters; the specific graphs are visual only

---

## Appendix B: Cross-chapter connections

Populated as later chapter skills are built.

### From Ch. 1 — Production Fundamentals

**Refinements:**
- **Ch. 1 Task 2's latency targets (p95/p99 SLAs)** cascade directly into Ch. 6 Task 1's serving paradigm choice. Sub-100ms latency forces online; multi-second tolerance allows batch.
- **Ch. 1 Task 5's stakeholder talking points on ML systems failing silently** apply doubly to deployment — the train/serve skew bug from Ch. 6 Task 1 is a silent-failure pattern Ch. 1 warns about.

### From Ch. 2 — Data Infrastructure Decisions

**Refinements:**
- **Ch. 2 Task 3's static vs. dynamic features** maps directly to Ch. 6 Task 1's "online with batch features only" vs. "online with streaming features." The Ch. 2 infrastructure decision determines what Ch. 6 serving paradigms are feasible.
- **Ch. 2 Task 3's batch vs. stream processing** is the upstream decision that makes Ch. 6 Task 1's "two pipelines anti-pattern" possible. If your Ch. 2 design uses one unified pipeline (Flink/Beam), Ch. 6's anti-pattern doesn't arise.

### From Ch. 3 — Training Data Strategy

No direct cross-references. (Ch. 3 is upstream of training; Ch. 6 is downstream of training.)

### From Ch. 4 — Feature Engineering Decisions

**Refinements:**
- **Ch. 4 Task 3's leakage prevention** has a deployment-time analogue: train/serve feature skew (Ch. 6 Task 1's "two pipelines anti-pattern"). Same principle (consistent feature computation) at a different layer.
- **Ch. 4 Appendix A's note on feature stores** ties to Ch. 6 Task 1's pipeline unification. Feature stores are the operational answer to train/serve skew — they enforce that the same feature definitions run in both training and serving paths.

### From Ch. 5 — Model Development and Evaluation

**Refinements:**
- **Ch. 5 Task 2's tradeoff evaluation** (compute vs. accuracy, interpretability vs. performance) feeds directly into Ch. 6 Task 1 (online vs. batch — latency tolerance is the tradeoff) and Task 2 (cloud vs. edge — compute availability is the tradeoff).
- **Ch. 5 Task 5's pre-deployment evaluation gauntlet** (baselines, perturbation, invariance, calibration, slicing) is the gate that should run *before* Ch. 6's deployment work. Don't deploy a model that hasn't passed Ch. 5 Task 5.
- **Ch. 5 Task 2's "start with simplest models"** is a strong Ch. 6 input. The simplest model that solves the problem is also the easiest to compress, deploy, and serve at low latency. Compression (Ch. 6 Task 3) is sometimes a substitute for picking a smaller architecture upfront — but picking smaller upfront is usually cleaner.

*Chapters 7–12 pending.*
