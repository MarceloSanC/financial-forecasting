# DMLS Ch. 4 — Feature Engineering Decisions (Task Reference)

Task-oriented notes from Chip Huyen's *Designing Machine Learning Systems*, Chapter 4. Organized around the decisions you make when turning raw data into model-ready features.

<!--
METADATA (for hybrid spine-skill assembly)
source: DMLS Ch. 4 — Feature Engineering
tasks_supported:
  - task-1-handle-missing-values
  - task-2-transform-raw-features-into-model-ready-features
  - task-3-detect-and-prevent-data-leakage
  - task-4-evaluate-whether-a-feature-should-stay-in-the-model
spine_topics_likely_to_pull_from_this_chapter:
  - designing-the-data-strategy (primary, pairs with Ch. 2 and Ch. 3)
  - model-development-and-evaluation (feature evaluation connects to model evaluation)
  - operating-in-production (leakage detection is also a production debugging skill)
-->

**Four tasks this reference supports:**
1. **Handle Missing Values** — diagnose the type of missingness, then choose deletion, imputation, or treating missingness as signal
2. **Transform Raw Features Into Model-Ready Features** — apply scaling, discretization, encoding (including the hashing trick for evolving categories), feature crossing, and positional embeddings
3. **Detect and Prevent Data Leakage** — recognize the six common causes and apply detection techniques throughout the project lifecycle
4. **Evaluate Whether a Feature Should Stay in the Model** — measure importance and generalization; decide whether to keep, prune, or rework

Each task is self-contained. Background and dated points are in Appendix A.

**Dependency note:** This chapter assumes you have training data. Chapter 2 covers where data comes from; Chapter 3 covers turning data into training data. This chapter is about the operations applied to columns of training data to make them useful to a model.

---

## Task 1: Handle Missing Values

**Use when:** You have a feature with missing values and need to decide what to do. This is the most common feature engineering problem and one of the most consequential — getting it wrong can introduce bias or leak information about the label.

### Step 1.1 — Diagnose the type of missingness first

Don't pick a strategy before identifying *why* values are missing. The right response depends on the type.

| Type | Definition | Example | Implication |
|------|-----------|---------|-------------|
| **MNAR** (Missing Not At Random) | The value is missing because of the value itself | High earners refuse to disclose income; sick patients drop out of studies | Missingness is informative; treat it as a signal, not noise |
| **MAR** (Missing At Random) | The value is missing because of *another* observed variable | Older respondents skip the income question; women skip a particular survey item | Can impute conditioned on the related variable; deletion may bias the data |
| **MCAR** (Missing Completely At Random) | No pattern; truly random | Annotator forgot to fill a field | Rare in real data — investigate before assuming MCAR |

**Diagnostic questions:**
- Is the rate of missingness correlated with any observed feature? (→ MAR)
- Is the rate of missingness correlated with the *target variable*? (→ MNAR — high risk)
- Have I actually checked, or am I assuming MCAR by default?

**Default assumption:** real-world missingness is rarely MCAR. Investigate before treating it as such.

### Step 1.2 — Choose deletion, imputation, or signal-preservation

Three strategies, each with conditions where it fits and conditions where it bites.

| Strategy | When it fits | Don't use when |
|----------|-------------|----------------|
| **Column deletion** | Feature has so many missing values it's mostly noise; the feature isn't predictive when present | The feature is highly predictive of the target (you'd lose information that matters) |
| **Row deletion** | MCAR + small fraction of rows affected (<0.1% rule of thumb) | MNAR (drops biased samples); MAR (drops a subgroup entirely); large fractions affected |
| **Imputation with default** | The missing value has a clear semantic default (empty string for missing job description) | The default is a *valid value in the domain* — collisions with real data points |
| **Imputation with mean/median/mode** | MCAR or MAR with stable distribution; feature is unlikely to be MNAR | MNAR (imputing hides the signal); the imputed value collides with valid domain values |
| **Treat missingness as signal** | MNAR; missingness itself is predictive | Almost never wrong to consider; always evaluate this option for MNAR |

**The "valid value collision" trap.** Don't impute with a value that exists in the domain.
- ❌ Impute missing `number_of_children` with 0 — model can't distinguish "no children" from "unknown."
- ❌ Impute missing `age` with 0 — model treats unknown-age users as infants.
- ✅ Add a separate `is_missing` indicator column and impute the original column with mean/median, OR use a sentinel value clearly outside the domain (-1 if domain is positive integers).

### Step 1.3 — When in doubt, add a missingness indicator

A simple, robust pattern: add a binary feature `feature_X_was_missing` alongside whatever imputation you do for `feature_X`. The model can use both. This handles MNAR cases gracefully without forcing you to commit to one interpretation.

### Step 1.4 — Watch for the imputation-then-leakage pitfall

If you compute the imputation value (mean, median, mode) using the *full* dataset before splitting, you've leaked test-set statistics into training. Always:
1. Split first.
2. Compute imputation values from the *training* split only.
3. Apply those values to validation, test, and production.

This connects to Task 3 (Data Leakage) — same fix, different angle.

### Step 1.5 — Questions to answer before settling on a missing-value strategy

- [ ] What's the missingness rate per feature?
- [ ] Have I tested whether missingness correlates with the target? (Quick correlation check; if yes, treat as signal.)
- [ ] What does my chosen imputation value look like — is it a real domain value that could collide with valid data?
- [ ] Am I computing imputation values from the train split only?
- [ ] Could a separate `is_missing` indicator be cheaper than getting the imputation right?

---

## Task 2: Transform Raw Features Into Model-Ready Features

**Use when:** You have raw features and need to turn them into something a model can use effectively. This task covers a catalog of transformations — pick the ones that fit your data and model type.

### Step 2.1 — Scaling

ML models that aren't naturally scale-invariant (gradient-boosted trees, logistic regression, neural networks, distance-based methods) benefit substantially from scaling. Tree models like random forests are largely scale-invariant. Know which family you're using.

**Why it matters:** if `age` ranges 20–40 and `income` ranges 10,000–150,000, models will weight income more simply because the numbers are bigger. Scaling forces the model to weight features based on predictive value, not magnitude.

**Three scaling methods:**

| Method | Formula | Use when |
|--------|---------|----------|
| **Min-max to [0, 1]** | `(x - min) / (max - min)` | No assumptions about distribution; bounded output desired |
| **Min-max to [a, b]** (often [-1, 1]) | `a + (x - min)(b - a) / (max - min)` | Same as above; [-1, 1] often empirically better than [0, 1] |
| **Standardization** | `(x - mean) / std` | Variable approximately normal; centered around 0 with unit variance is helpful |
| **Log transform** | `log(x)` | Variable is positively skewed; reduces skew |

**Hard rules:**
- Compute min/max/mean/std from the **training split only**, not the full dataset. Reuse those values at inference.
- If incoming production data drifts away from the training distribution, the scaling becomes meaningless. Plan to retrain.
- Log transform changes the *interpretation* of analyses done on the feature — be aware when reporting effect sizes.

**Order of operations gotcha:** scaling can yield a 10%+ performance boost on classical models. Don't skip it because it feels mechanical.

### Step 2.2 — Discretization

Turn a continuous feature into a discrete (bucketed) feature.

| Use when | Don't use when |
|----------|----------------|
| The model only needs to learn coarse distinctions (lower / middle / upper income) | Fine-grained variation is predictive |
| Continuous values are noisy and bucketing reduces noise | You don't have justification for the bucket boundaries |
| You suspect the relationship is non-linear and steps would help | A monotonic transformation (log, sqrt) would do the job better |

**Choosing bucket boundaries:**
- Plot a histogram and look for natural breaks
- Use quantiles (deciles, quartiles) for distribution-aware bucketing
- Use domain expertise (legal age cutoffs, tax brackets, rush-hour vs. off-peak)

**Reminder:** discretization can apply to discrete features too (collapsing 100 age values into 6 age brackets). Reduces cardinality and helps the model focus.

### Step 2.3 — Encoding categorical features

Two regimes, very different problems.

**Regime A: Static categories with known cardinality.**
- Examples: age brackets, income brackets, country codes, day of week
- Approach: assign each category an integer; one-hot encode if the model needs it
- Straightforward; no special handling needed

**Regime B: Dynamic categories that grow over time.**
- Examples: brands on a marketplace (Amazon had 2M+ in 2019), user accounts, product types, website domains, IP addresses, restaurants, companies
- The naive approach fails badly:

**The naive-encoding trap (Chip's Amazon example):**
1. Encode each brand 0..N-1. Model trained, looks great on test.
2. Production hits a new brand → crash. Add `UNKNOWN` category.
3. Model never saw `UNKNOWN` during training → recommends nothing for new brands → seller complaints.
4. Train on top 99% brands, encode bottom 1% as `UNKNOWN`. Now the model has *learned* that `UNKNOWN` means "unpopular brand."
5. New luxury and knockoff brands all get hashed to `UNKNOWN` → treated as low-quality → click rate plummets.

**The hashing trick (the fix):**
- Use a hash function to map each category to an index in a fixed hash space (e.g., 18-bit space → 262,144 possible values).
- New categories are hashed automatically — no special-casing needed.
- Collisions happen but are *random* — a new luxury brand might collide with any existing brand, not consistently with low-performing ones.
- Booking.com found 50% collision rate causes <0.5% log loss increase. Worst-case acceptable.
- Locality-sensitive hashing variants put similar categories near each other in the hash space when that's useful.

**When to use the hashing trick:**
- [ ] The category space is unbounded or grows over time
- [ ] You're doing continual learning (new categories arrive in production)
- [ ] You'd rather have random collisions than systematic UNKNOWN-bucket bias
- [ ] You've sized the hash space large enough for your expected cardinality

Available in scikit-learn, TensorFlow, gensim, Vowpal Wabbit (the original popularizer).

### Step 2.4 — Feature crossing

Combine two or more features to create a new one that captures non-linear relationships.

**Example:** `marriage_status × number_of_children` → `("Married", 2)`, `("Single", 0)`, etc. Captures the joint signal that linear models can't decompose into separate marriage and children effects.

| When to use | When to skip |
|-------------|--------------|
| Linear models (logistic regression), tree models that don't natively learn deep interactions | Deep neural networks usually learn interactions implicitly (still occasionally helpful for faster convergence) |
| You have specific domain hypotheses about feature interactions | You're throwing crosses at the wall to see what sticks (feature space blows up; overfitting risk) |
| Recommendation / CTR tasks (DeepFM, xDeepFM family explicitly use crosses) | Memory-constrained serving (crosses balloon parameter counts) |

**Cardinality warning:** crossing two features with 100 values each yields 10,000 possible values. You need much more data, and overfitting risk grows.

### Step 2.5 — Positional embeddings (when relevant)

Most feature engineering doesn't touch this. It applies when:
- You're using a transformer or attention-based architecture (most modern NLP / multimodal work).
- You're using a coordinate-based network (Fourier features for 3D representation, NeRF-style models).
- You're working with sequence data where order matters but the architecture processes elements in parallel.

**Two flavors:**

| Type | How | Use when |
|------|-----|----------|
| **Learned position embeddings** | Treat positions like vocabulary; embedding matrix with one column per position; sums with token embeddings | Discrete positions, fixed maximum length |
| **Fixed position embeddings** (sine/cosine) | Predefined functions of position; even index → sin, odd index → cos | Discrete or continuous positions; no max length constraint |
| **Fourier features** (continuous) | Generalization of sin/cosine to continuous coordinates | 3D shapes, signed distance fields, coordinate-based learning |

**2026 update worth knowing:** modern LLMs typically use rotary position embeddings (RoPE) or ALiBi rather than the original Transformer's learned absolute embeddings or sin/cosine positions. The chapter's framing is correct but BERT-era; if the user is choosing position embeddings for an LLM in 2026, suggest looking up RoPE / ALiBi.

### Step 2.6 — Decision summary table

For each raw feature, walk through:

| If the feature is... | Apply... |
|---------------------|----------|
| Continuous, large numerical range, model isn't tree-based | Scaling (min-max or standardization) |
| Continuous, skewed distribution | Log transform |
| Continuous, model only needs coarse distinctions | Discretization |
| Categorical with stable, known categories | Integer encoding / one-hot |
| Categorical with unbounded or evolving categories | Hashing trick |
| Two features with suspected non-linear interaction (linear/tree model) | Feature crossing |
| Sequence / coordinate input to attention model | Positional embeddings |
| Missing values present | → Task 1 first |

---

## Task 3: Detect and Prevent Data Leakage

**Use when:** Building any supervised model, evaluating a model that performs suspiciously well on test data, or debugging a model that worked in development but fails in production. Leakage is one of the most common production-failure modes and one of the hardest to detect after the fact.

**Definition.** Data leakage = information about the label "leaks" into the features at training time, but isn't available at inference time. Result: model looks great on test, fails in production.

### Step 3.1 — Recognize the six common causes

| # | Cause | Example | Fix |
|---|-------|---------|-----|
| 1 | **Random splitting of time-correlated data** | Stock prices, music trends, news topics — random split mixes future and past in training data | Always split by time when data has any temporal structure. Train on weeks 1–4, validate/test on week 5. |
| 2 | **Scaling before splitting** | Computing mean/std on full dataset to scale features → test mean leaks into training | Split first; compute statistics from train split only. |
| 3 | **Filling missing values with full-data statistics** | Median imputation using all data, including test | Same fix: compute imputation value from train only. |
| 4 | **Duplicates across splits** | Same example in train and test (CIFAR-10 has 3.3% test-set duplicates in training; CIFAR-100 has 10%) | Always deduplicate. Check before *and* after splitting. If oversampling, do it after splitting. |
| 5 | **Group leakage** | Two CT scans of the same patient one week apart, both labeled cancerous; one in train, one in test | Split at the group level, not the example level. Patient-level split, not scan-level. |
| 6 | **Data collection process leakage** | Hospital A sends suspected-cancer patients to a different scan machine; model learns the machine type, not the cancer | Hardest to detect. Requires understanding *how* data was collected. Normalize across sources to remove the spurious signal. |

### Step 3.2 — Detection techniques

Run these throughout the project, not just once.

**Correlation analysis.**
- For each feature, measure correlation with the target.
- Flag features with unusually high correlation (especially anything near 1.0).
- Two features may be individually fine but jointly leaky (start_date and end_date individually don't reveal tenure; together they do). Check feature combinations too.

**Ablation studies.**
- Remove each feature (or feature group) and measure the model's performance hit.
- A feature whose removal causes a *very* large performance drop deserves scrutiny — is it that good, or is it leaking?
- For 1000+ feature models, focus ablation on the most-suspicious features rather than all combinations.

**Watch new features carefully.**
- A new feature that gives a big jump in test performance is either (a) an excellent feature or (b) a leak. Default to suspicion until you've verified it's the former.

**Minimize test-set interaction.**
- The test split is for *final reporting*, not for ideation, hyperparameter tuning, or feature exploration.
- Every time you look at the test split for any other purpose, you risk leaking that information into your decisions, which leaks into the model indirectly.

**Cross-distribution evaluation.**
- If feature coverage or distribution differs significantly between train and test splits (e.g., 90% coverage in train, 20% in test), that's a red flag — either a sampling issue or a leakage issue.

### Step 3.3 — Prevention checklist

Build these into your pipeline, not as one-time audits.

- [ ] Split by time whenever data has temporal structure
- [ ] Split before any other processing (scaling, imputation, EDA)
- [ ] Compute all global statistics (mean, std, min, max, median, mode, vocab) from the train split only
- [ ] Deduplicate before splitting; verify after splitting
- [ ] If oversampling or augmenting, do it after splitting
- [ ] Identify the natural "group" in your data (patient, user, session) and split at that level
- [ ] Document how data was collected, including any process differences across sources
- [ ] Establish a habit of suspicion when a new feature massively boosts test performance
- [ ] Treat the test split as read-only except for final reporting

### Step 3.4 — When you discover leakage in production

This is mostly damage control:
1. Identify the leaky feature(s) — usually the one you most recently added or the one with anomalously high importance.
2. Retrain without it, expecting performance to drop. The drop is the cost of the leak being real.
3. If a feature was *also* used in feature crosses, derived features, or downstream models, those need rework too.
4. Update your leakage prevention checklist with the cause you missed.

---

## Task 4: Evaluate Whether a Feature Should Stay in the Model

**Use when:** Reviewing the feature set of an existing model, deciding which features to add or remove, or doing a periodic feature audit. More features is not always better — overfitting, latency, memory, technical debt, and leakage risk all grow with feature count.

### Step 4.1 — Why bigger feature sets aren't always better

Common belief: more features → better model. Reality (production constraints):

- More features → more opportunities for leakage
- More features → more overfitting risk
- More features → more memory at serving time → larger / more expensive instances
- More features → higher inference latency for online prediction
- More features → more technical debt (every pipeline change ripples through every dependent feature)
- Useless features that L1 regularization could in theory zero out are still cheaper to just remove

**Practical heuristic:** if a feature isn't pulling weight, remove it. You can always add it back; you can't easily debug a regression caused by an unused feature interacting with new data.

### Step 4.2 — Evaluate feature *importance*

How much does the model actually rely on this feature?

| Method | When to use |
|--------|------------|
| **Built-in importance** (XGBoost `get_score`, sklearn `feature_importances_`) | Tree-based models; quick first pass |
| **SHAP** (SHapley Additive exPlanations) | Any model; gives both global feature importance *and* per-prediction contribution. Standard for production ML interpretability. |
| **Ablation** | Any model; remove the feature, retrain, measure performance drop. Most rigorous but expensive |
| **Permutation importance** | Any model; shuffle the feature's values and measure performance drop. Cheaper than ablation |

**The Pareto pattern.** Facebook's ad CTR work found that the top 10 features account for ~50% of total feature importance, and the bottom 300 features contribute <1%. Most production models follow some version of this — a small number of features carry most of the predictive weight.

**Implication:** identify your top-importance features and protect them; the long tail is often safe to prune.

### Step 4.3 — Evaluate feature *generalization*

Importance tells you the feature works on the training-time data. Generalization tells you whether it'll keep working on data the model hasn't seen. These are different.

**Two dimensions of generalization:**

**Coverage** — what fraction of examples have a value for this feature?

| Coverage pattern | Implication |
|-----------------|-------------|
| Very low coverage (e.g., 1%) | Probably not useful — *unless* the missing-vs-present distinction itself carries strong signal |
| Coverage differs significantly between train and test (e.g., 90% vs 20%) | Red flag: either bad splitting or leakage. Investigate before relying on this feature |
| Coverage shifts over time | Plan for retraining; the feature's value may degrade |

**Value distribution overlap** — do the values seen in production look like the values seen during training?

| Pattern | Implication |
|---------|-------------|
| Train and test value sets fully overlap | Feature generalizes; safe to use |
| Train and test value sets disjoint | Feature does not generalize and may *harm* the model |
| Train values are a strict subset of test values | Some test cases will see novel values; depends on encoding |

**Example (Chip's taxi ETA model):** `DAY_OF_THE_WEEK` has 100% coverage but if train has Mon–Sat and test has Sun, the feature won't generalize at all and may hurt performance. `HOUR_OF_THE_DAY` has 100% coverage *and* 100% value overlap, so it's safe.

### Step 4.4 — Generalization vs. specificity tradeoff

A more general feature (`IS_RUSH_HOUR`) generalizes better but loses information. A more specific feature (`HOUR_OF_THE_DAY`) carries more signal but generalizes worse.

The right answer is usually "include both" rather than picking one — the model can learn from both granularities. Where to draw the line is task-specific:

- [ ] Does the specific feature have full value-distribution overlap between train and prod?
- [ ] Does the general feature lose meaningful signal that isn't recoverable from other features?
- [ ] Can we afford the cardinality of the specific feature in our serving infrastructure?

### Step 4.5 — Decision procedure

Walk this for each feature in the model (or each feature group, for thousand-feature models):

1. **Importance check.** Is this feature in the top 10 by SHAP / built-in importance? If yes, protect it.
2. **Generalization check.** Does it have decent coverage and good value overlap between train and current production data?
3. **Leakage check.** Does its importance seem suspicious given the task? Has its importance grown sharply since the last audit?
4. **Cost check.** What's the cost of keeping it? (Latency, memory, pipeline complexity, expertise to maintain.)
5. **Decide.**
   - High importance + good generalization + no leakage signs → keep
   - Low importance + low cost → keep (cheap insurance) or remove (cleaner pipeline) — judgment call
   - Low importance + high cost → remove
   - Suspiciously high importance → investigate before deciding
   - Poor generalization regardless of importance → remove or rework

**Versioning recommendation.** Removed features shouldn't be deleted from the codebase — store the feature definitions so they can be re-added later if needed, and so other teams can reuse them. Feature stores (Feast, Tecton, or homegrown) are the modern infrastructure for this; the chapter mentions them only briefly.

---

## Appendix A: Background Context (not task-critical)

### Learned features vs. engineered features (chapter framing)

Deep learning automates many feature engineering steps for text and images. Classical NLP required lemmatization, contraction expansion, punctuation removal, lowercasing, n-gram extraction. Modern NLP often skips most of this — tokenize, embed, let the model learn. Same trend in computer vision.

But **most production ML still has plenty of engineered features** because:
- Tabular and structured data still dominates enterprise ML (fraud, churn, pricing, forecasting)
- Even deep learning models benefit from explicit features for non-text/non-image inputs (user metadata, comment metadata, thread metadata)
- A spam detector needs features about the post (text, votes), the user (account age, post frequency, vote history), the thread (views, comment count) — most of these don't auto-learn from raw input

The chapter's framing — "deep learning has reduced feature engineering but not eliminated it" — is correct as of 2026. The boundary keeps shifting toward auto-learned, but engineered features remain core to most production systems.

### Feature stores (post-book context worth knowing)

The chapter gestures at "feature definition management" but doesn't develop it. By 2026, **feature stores** (Feast, Tecton, Vertex AI Feature Store, Databricks Feature Store, Hopsworks) are a major piece of production ML infrastructure. They solve:
- Sharing feature definitions across training and serving (avoids train-serve skew)
- Reusing features across teams and models
- Versioning feature transformations
- Materializing computed features for low-latency serving
- Handling the static vs. dynamic feature distinction from Ch. 2 Task 3

When a user is doing serious feature engineering work in production, the question "do we have a feature store?" is usually relevant. The chapter doesn't cover this; Ch. 9 (infrastructure) likely does.

### Position embedding evolution (post-book context)

The chapter describes BERT-era position embeddings (learned absolute) and the original Transformer's sin/cosine. Modern LLMs (2024+) use:
- **RoPE (Rotary Position Embeddings)** — encodes relative positions through rotation in embedding space; widely adopted
- **ALiBi** — adds linear bias based on distance; simpler than RoPE in some respects
- **No position embeddings at all** in some experimental architectures

If the user is choosing position embeddings for a new transformer in 2026, point them at RoPE/ALiBi rather than the chapter's recommendations.

### Dated content (treat as illustrative, not current)

- **"Most ML applications in production aren't deep learning"** (~2021) — partially true in 2026. False for consumer NLP/CV/multimodal at scale; still mostly true for enterprise tabular ML.
- **Vowpal Wabbit as the popularizer of feature hashing** — historically true; VW is much less prominent in 2026, but the technique is more widespread than ever.
- **HuggingFace BERT position embedding (August 2021)** — BERT is still used but no longer the canonical example for transformers. Modern LLMs use RoPE/ALiBi.
- **Amazon brand count: >2M (2019)** — still illustrates the unbounded-category problem, definitely larger now.
- **Booking.com 50% hash collision study (~0.5% log loss impact)** — directional finding, still cited as supporting evidence for the hashing trick.
- **Facebook 2014 paper on feature importance distribution** — the Pareto pattern (top features dominate) holds across most production ML; specific numbers vary by task.
- **CIFAR-10 / CIFAR-100 duplicate rates (3.3%, 10%)** — the deduplication-before-split lesson still applies broadly.
- **DeepFM / xDeepFM** — still in production for recommendations; transformer-based recsys has grown but doesn't fully replace this family.

### Things we didn't save (and why)

- **Long n-gram tokenization walkthrough** — well-known background; no actionable feature engineering content beyond "this is what classical NLP required."
- **Kaggle Ion Switching cautionary tale** — interesting story but the lesson ("random splits leak time-correlated data") is already in Task 3 cause #1.
- **Full Fourier features formula** — the equation is in the source for anyone who needs it; the *use case* matters more than the math.
- **Theoretical argument that L1 regularization handles useless features** — Chip himself notes that in practice you should remove them anyway.

---

## Appendix B: Cross-chapter connections

Populated as later chapter skills are built.

### From Ch. 2 — Data Infrastructure Decisions

**Refinements:**
- **Ch. 2 Task 3's static vs. dynamic features** is the infrastructure reality behind Ch. 4's feature engineering. Static features (driver rating) go through batch processing; dynamic features (current driver count) go through stream processing. Ch. 4 doesn't address *how* features are computed at serving time — that's Ch. 2's domain.
- **Ch. 2 Task 1's source taxonomy** maps to feature provenance. Features derived from user input vs. system-generated vs. third-party have different latency, freshness, and reliability profiles. Track which source each feature comes from.

**Cross-links:**
- *Designing the data strategy* (spine) will pull Ch. 2 Tasks 1–4 + Ch. 3 + Ch. 4 as one integrated workflow.

### From Ch. 3 — Training Data Strategy

**Refinements:**
- **Ch. 3 Task 1's sampling decisions** interact with Ch. 4 Task 3's leakage prevention. Both involve correct splitting. Ch. 3 is about *what* to sample; Ch. 4 is about *how* to split without leaking. Treat them as joined decisions.
- **Ch. 3 Task 4's class imbalance** and Ch. 4 Task 1's missing values share a meta-principle: diagnose before intervening. Class imbalance can be inherent, sampling-caused, or labeling-caused; missingness can be MNAR, MAR, or MCAR. Same diagnostic discipline applies.
- **Ch. 3's data lineage practice** (track origin and annotator of every sample) extends to feature lineage — track how each feature was computed, what version of the transformation produced it, and which data it was derived from.

**Cross-links:**
- *Designing the data strategy* (spine) will tie sampling, labeling, and feature engineering together as the "preparing data for the model" workflow.

### From Ch. 5 — Model Development and Evaluation

**Refinements:**
- **Ch. 4 Task 4's feature evaluation** (importance via SHAP, generalization via coverage and distribution overlap) is feature-level. **Ch. 5 Task 5's evaluation methods** (perturbation, invariance, calibration, slice-based) are model-level. Both run before deployment; both contribute to the deployment-readiness decision.
- **Ch. 4 Task 3's leakage prevention** has a Ch. 5 echo: "don't tune hyperparameters on test split" (Ch. 5 Task 4) is leakage prevention applied to AutoML. Same discipline at a different layer.
- **Ch. 4's "more features isn't always better" framing** has a model-level analogue in Ch. 5's Tip 2 ("start with the simplest models"). Same Occam's razor principle, applied at different layers of the system.

**New concepts from Ch. 5 worth remembering when using Ch. 4:**
- **Pre-deployment evaluation gauntlet (Ch. 5 Task 5)** runs *after* Ch. 4's feature engineering work and folds it in. Slice-based evaluation, for example, can reveal that a feature with good aggregate generalization fails on a specific subgroup — sending you back to Ch. 4 Task 4 to revisit.
- **Six tips for model selection (Ch. 5 Task 2)** include "understand your model's assumptions." Many feature engineering decisions in Ch. 4 (scaling for non-tree models, encoding for high-cardinality categories) are downstream of which assumptions the chosen model makes. Cross-link tightly: when picking a model, list its assumptions; check Ch. 4 features against them.

### From Ch. 6 — Deployment and Inference Decisions

**Refinements:**
- **Ch. 4 Task 3's leakage prevention** has its deployment-time analogue in **Ch. 6 Task 1's "two pipelines anti-pattern"** (train/serve feature skew). Both are about consistent feature computation across stages — Ch. 4 within training, Ch. 6 between training and serving.
- **Ch. 4 Appendix A's note on feature stores** (a post-book development not in Ch. 4 itself) is the operational answer to **Ch. 6 Task 1's pipeline unification problem**. Feature stores enforce that the same feature definitions run in both training and serving paths, eliminating one major class of deployment-time bugs.

**New concepts from Ch. 6 worth remembering when using Ch. 4:**
- **Streaming features at serving time (Ch. 6 Task 1)** changes what feature engineering work can look like. If your serving pipeline is online with streaming features, your Ch. 4 transformations need to run with sub-millisecond latency — which constrains the techniques (no expensive feature crossings; quantizable scalings; hash-based encoding for unbounded categories).
- **Edge deployment constraints (Ch. 6 Task 2)** force feature engineering simplifications. Memory-constrained devices can't load large embedding tables, hash-space sizes need to fit, and feature transformations need to run with limited compute.

*Chapters 7–12 pending.*
