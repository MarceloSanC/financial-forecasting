# DMLS Ch. 5 — Model Development and Evaluation (Task Reference)

Task-oriented notes from Chip Huyen's *Designing Machine Learning Systems*, Chapter 5. Organized around the decisions you make when developing, training, and evaluating ML models before deployment.

<!--
METADATA (for hybrid spine-skill assembly)
source: DMLS Ch. 5 — Model Development
tasks_supported:
  - task-1-frame-an-ml-problem
  - task-2-select-and-evaluate-models
  - task-3-establish-model-development-practices
  - task-4-tune-models-with-automl
  - task-5-evaluate-a-model-before-deployment
spine_topics_likely_to_pull_from_this_chapter:
  - model-development-and-evaluation (primary, the heart of this spine)
  - scoping-and-planning-an-ml-project (problem framing connects to project scoping)
  - operating-in-production (evaluation methods inform monitoring)
-->

**Five tasks this reference supports:**
1. **Frame an ML Problem** — translate a business request into inputs, outputs, and an objective function; pick task type; decouple multiple objectives
2. **Select and Evaluate Models** — apply the six tips for model selection, decide whether to ensemble, and pick the right ensemble strategy
3. **Establish Model Development Practices** — experiment tracking, versioning, debugging discipline, distributed training when needed
4. **Tune Models with AutoML** — hyperparameter tuning (practical) vs. NAS / learned optimizers (research-grade); pitfalls to avoid
5. **Evaluate a Model Before Deployment** — baselines, perturbation tests, invariance tests, directional expectation tests, calibration, confidence, slice-based evaluation

Each task is self-contained. Background and dated points are in Appendix A.

**Dependency note:** This chapter assumes you have features (Ch. 4), training data (Ch. 3), and data infrastructure (Ch. 2). It also picks up where Ch. 1 left off — Ch. 1 decides whether to use ML; Ch. 5 decides *how* to shape the ML problem and pick a model.

---

## Task 1: Frame an ML Problem

**Use when:** A business stakeholder asks you to "use ML for X" or you're scoping how to translate a real-world problem into something a model can solve. The framing decision determines everything downstream — bad framing makes the problem unnecessarily hard or impossible.

### Step 1.1 — Define the three components of any ML problem

Every ML problem must specify:

- **Inputs:** what features the model sees at inference time
- **Outputs:** what the model produces (a class, a number, a probability distribution)
- **Objective function:** what loss the training process minimizes

If any of these is missing or vague, the problem isn't yet an ML problem. Ch. 5's example: "speed up customer service" isn't an ML problem. "Predict which of 4 departments handles a request, minimize cross-entropy between predicted and actual department" is.

**Questions to surface to the stakeholder:**
- [ ] What does the model see at decision time? (Available features.)
- [ ] What decision should the model produce? (One of N classes? A continuous value? A ranking?)
- [ ] How will we measure success? (What's the loss function we're minimizing?)
- [ ] What's the action that follows from a prediction? (Routing, ranking, alerting, blocking — affects how wrong predictions cost.)

### Step 1.2 — Pick the task type

Output shape determines task type. Each subtype has different difficulties.

| Task type | Output | Common pitfalls |
|-----------|--------|----------------|
| **Regression** | Continuous value | Easy to convert to/from classification by thresholding or bucketing |
| **Binary classification** | One of two classes | Easiest case; metrics like F1 and confusion matrices are intuitive |
| **Multiclass, low cardinality** | One of N classes (small N, e.g., 4–20) | Manageable; same techniques as binary but more annotation work |
| **Multiclass, high cardinality** | One of many classes (e.g., 1000s) | Need ~100 examples per class as a rule of thumb. Some classes will be rare. Consider hierarchical classification (first classify into broad groups, then sub-classify) |
| **Multilabel** | Multiple classes can be true simultaneously | Most error-prone in production. Number of labels per example varies, breaking both annotation (multiplicity disagreements) and prediction extraction (how many top-k probabilities to pick?) |

**The convertibility trick.** Regression and classification can often be reframed as each other:
- Regression → classification: bucket the continuous value (house price → price band)
- Classification → regression: output a probability and threshold (spam classification → "spam score" between 0 and 1)

Use this to make a problem more tractable when the natural framing is hard.

### Step 1.3 — Reframe to avoid built-in failure modes

A bad framing can require frequent retraining or make the model fundamentally brittle. Reframe before committing.

**Chip's app-recommendation example:**
- *Bad framing:* multiclass classification — output a probability distribution over all N apps. New app added → retrain.
- *Good framing:* regression — input is (user, environment, app) → output is a single 0-1 score. New app added → just call the model with new app's features. No retrain.

The good framing makes the *number of options* a runtime input rather than a baked-in dimension of the model.

**Reframing checklist:**
- [ ] Does my framing require retraining when something simple changes (new class, new product, new user type)?
- [ ] Could I move that "something" from the model's structure to its inputs?
- [ ] Am I forcing a classification framing onto a problem that's actually a ranking or scoring problem?
- [ ] If multilabel, can I instead train N binary classifiers and combine outputs?

### Step 1.4 — Pick the objective function (usually straightforward)

Most production ML uses standard loss functions:
- **Regression:** RMSE or MAE
- **Binary classification:** Logistic Loss (Log Loss)
- **Multiclass classification:** Cross Entropy

Custom objectives are possible but rarely needed. Chapter 3 Task 4 covers loss-function modifications for class imbalance (focal loss, class-balanced loss, cost-sensitive learning) — defer to that for imbalance cases.

### Step 1.5 — Decouple multiple objectives

When a system needs to optimize multiple things (e.g., recommend posts that are both engaging *and* high-quality), don't combine the losses into one. Train separate models per objective and combine outputs at serving time.

**Combined-loss approach (avoid):**
```
loss = α · quality_loss + β · engagement_loss
```
Train one model. To rebalance α and β, retrain.

**Decoupled approach (preferred):**
- Train `quality_model` to minimize `quality_loss`
- Train `engagement_model` to minimize `engagement_loss`
- At serving time: `final_score = α · quality_score + β · engagement_score`
- Tune α and β without retraining

**Why decoupling wins:**
- No retrain when re-weighting objectives
- Different objectives have different update cadences (spam evolves fast; quality perception slow). Decoupled models can be retrained independently.
- Easier to debug: you can see which model is failing.
- Easier to add or remove objectives later.

**When to decouple:**
- [ ] Multiple stakeholders care about different things (engagement team vs. integrity team)
- [ ] Sub-objectives have different data sources or labeling pipelines
- [ ] You expect to rebalance the objectives over time
- [ ] Objectives evolve at different rates

This connects to Ch. 1 Task 2 on stakeholder mapping. When stakeholders have conflicting objectives, decoupling is the technical answer.

---

## Task 2: Select and Evaluate Models

**Use when:** Picking which model architecture(s) to try; comparing candidates; deciding whether to add complexity; deciding whether to ensemble.

### Step 2.1 — Six tips for model selection

These six tips are the most actionable framework in the chapter. Walk them in order.

**Tip 1: Avoid the SOTA trap.**
- SOTA on benchmarks ≠ best for your problem.
- SOTA models are often expensive, slow, complex, and tuned for academic datasets.
- Use the simplest solution that solves your problem.
- Stay aware of new techniques but don't default to them.

**Tip 2: Start with the simplest models.**
- Easier to deploy → validates your prediction pipeline early.
- Easier to debug and understand.
- Provides a baseline for more complex models.
- "Simplest" ≠ "least effort." A pretrained BERT model is complex but easy to use via HuggingFace. An off-the-shelf complex model with strong community support can be the right starting point.

**Tip 3: Avoid human biases in selecting models.**
- The team member who's excited about Architecture A will run more experiments on it. Their results aren't comparable to less-explored Architecture B.
- Compare under equivalent setups: same number of experiments, same hyperparameter search budget per architecture.
- A claim like "Architecture A is better than Architecture B" is almost never universally true; it depends on task, data, hyperparameters.

**Tip 4: Evaluate good performance now vs. good performance later.**
- The best model today isn't necessarily the best model two months from now.
- Use **learning curves** (model performance vs. training set size) to estimate whether more data will help.
- Models that improve with continual learning (simple neural networks) can outperform models that need full retraining (collaborative filtering) over time, even if they start behind.
- Take into account near-future improvements in your decision.

**Tip 5: Evaluate trade-offs.**
- False positives vs. false negatives (fingerprint unlocking vs. cancer screening lean opposite ways)
- Compute requirements vs. accuracy (more accurate model needing GPU vs. less accurate model on CPU)
- Interpretability vs. performance (linear models are interpretable; deep nets often aren't)
- Latency vs. accuracy (Ch. 1 Task 5 territory)

**Tip 6: Understand your model's assumptions.**
Common assumptions to check against your data:

| Assumption | Made by | Check |
|-----------|---------|-------|
| **Prediction** | All predictive models | Can Y be predicted from X at all? |
| **IID** | Most neural networks | Are examples independently drawn from same distribution? |
| **Smoothness** | Most supervised ML | Do similar inputs map to similar outputs? |
| **Tractability** | Generative models | Is P(Z\|X) computable? |
| **Linear boundaries** | Linear classifiers | Are decision boundaries linear in feature space? |
| **Conditional independence** | Naive Bayes | Are features independent given the class? |
| **Normality** | Many statistical methods | Is the data normally distributed? |

A model fails when its assumptions are violated. Match assumptions to data characteristics.

### Step 2.2 — Decide whether to ensemble

Ensembles consistently boost performance — 20 of 22 winning Kaggle solutions in 2021 used ensembles; top SQuAD 2.0 leaderboard solutions are all ensembles. But they're more complex to deploy and maintain.

**When ensembles are worth it:**
- Small performance gains translate to large business value (CTR prediction, ad ranking, fraud detection)
- You have the infrastructure to deploy and maintain multiple models
- The latency cost of running multiple models is acceptable

**When to skip ensembles:**
- Latency-critical online serving with tight budgets
- Simple problem where a single model already exceeds the threshold
- Limited engineering capacity for ongoing maintenance

**Why ensembles work — the math.** If you have 3 uncorrelated 70%-accurate classifiers and take a majority vote, the ensemble accuracy rises to 78.4%:

| 3-classifier outcome | Probability | Vote correct? |
|---------------------|-------------|---------------|
| All 3 correct | 0.7³ = 0.343 | Yes |
| Exactly 2 correct | 3 × 0.7² × 0.3 = 0.441 | Yes |
| Exactly 1 correct | 3 × 0.3² × 0.7 = 0.189 | No |
| None correct | 0.3³ = 0.027 | No |

Ensemble accuracy = 0.343 + 0.441 = **0.784**.

**Critical condition:** classifiers must be uncorrelated. Perfectly correlated classifiers give the same accuracy as a single one. Use diverse model families to maximize the gain (transformer + RNN + gradient-boosted tree, not three slightly-tuned versions of the same model).

### Step 2.3 — Pick the ensemble type

Three patterns, each addressing a different problem.

| Type | Reduces | How | Best for |
|------|---------|-----|---------|
| **Bagging** (Bootstrap Aggregating) | Variance | Train each base model on a different bootstrap sample of the data; majority vote (classification) or average (regression) | Unstable methods (neural networks, decision trees, linear regression with feature subset selection). Random forests are the canonical example. |
| **Boosting** | Bias | Train iteratively; later models focus on examples earlier models got wrong; final prediction is weighted combination | Weak learners that need to be combined into a strong one. Gradient Boosting Machines, XGBoost, LightGBM. |
| **Stacking** | Generalization error | Train base learners on training data; train a meta-learner that takes base-learner outputs as features and predicts the final answer | When base learners are diverse and you want to learn how to combine them rather than using a fixed rule |

**Decision shortcut:**
- Variance is the problem (overfitting on a single training set) → bagging
- Bias is the problem (models underfit) → boosting
- You want the model itself to learn the combining rule → stacking

**Note on bagging exceptions:** Bagging mildly *degrades* stable methods like k-nearest neighbors. Apply to unstable methods.

**XGBoost vs. LightGBM in practice:** XGBoost was the dominant competition winner; many teams have shifted to LightGBM for faster training on large datasets via parallel learning. Both remain widely used in production.

### Step 2.4 — Questions to answer before committing to a model

- [ ] What's our baseline (random, simple heuristic, existing solution)? See Task 5 for baseline framework.
- [ ] What's the simplest model that could plausibly work?
- [ ] Have I evaluated 2+ candidate architectures with comparable experiment budgets?
- [ ] What does the learning curve suggest about future performance?
- [ ] Which tradeoffs (FP/FN, latency/accuracy, interpretability) matter most for this problem?
- [ ] Do my data and task satisfy the model's assumptions?
- [ ] Is an ensemble worth the operational cost?

---

## Task 3: Establish Model Development Practices

**Use when:** Setting up a model development workflow, debugging a model that's not training well, or trying to make experiments reproducible. These are the operational practices that surround model selection.

### Step 3.1 — Track experiments and version artifacts

Many things go wrong during training (loss not decreasing, overfitting, fluctuating weights, dead neurons, OOM). You need to track enough to detect and diagnose.

**What to track per experiment (illustrative, not exhaustive):**

- [ ] Loss curves for train split and each eval split
- [ ] Performance metrics on non-test splits (accuracy, F1, perplexity, etc.)
- [ ] Speed metrics (steps/second; tokens/second for text)
- [ ] System metrics (memory, CPU/GPU utilization)
- [ ] Hyperparameters that change over time (learning rate schedule, gradient norms, weight norms)
- [ ] All artifacts needed to reproduce the run (code snapshot, data version, config, seeds)

**The tracking discipline:** track more than you think you need. When something goes wrong, you'll want the data. Tools like MLflow, Weights & Biases, Neptune, ClearML, Comet handle the boilerplate. (DVC is more versioning-focused, useful for the data side.)

**Versioning extends beyond code.** ML systems are part code, part data, part artifacts. You need to version:
- Code (standard tooling: Git)
- Data (harder — DVC and similar tools work, but with caveats)
- Trained models / artifacts
- Experiment configurations and seeds

**Why data versioning is hard:**
- Data is too large for line-by-line diffs
- Storing full copies of every dataset version is often infeasible
- Defining what counts as a "diff" is unclear (file changes? checksum changes?)
- Merge conflicts have no clean resolution (two devs trained different models on different data versions — there's no single correct merged data version)
- Privacy regulations (GDPR, EU AI Act) may forbid retaining old data versions

**Pragmatic approach:** version the data identifier and pipeline configuration that produces the data, not necessarily the raw bytes. Combined with reproducible pipelines, this often gets you reproducibility without the storage explosion.

**Reproducibility caveat:** even with full tracking, reproducibility isn't guaranteed. Hardware non-determinism (CUDA atomic operations, floating-point ordering), framework versions, and random sources can introduce variation between runs.

### Step 3.2 — Debug ML models with discipline

Debugging ML models is harder than debugging traditional software because:
1. **Models fail silently.** No crash, no exception — just wrong predictions.
2. **Validating a fix is slow.** May require retraining; can't see immediate feedback.
3. **Cross-functional complexity.** Bugs can be in data, labels, features, algorithms, code, or infrastructure — different teams own different pieces.

**Common failure causes (use as a checklist when debugging):**

- [ ] **Theoretical constraints** — model assumptions don't match data (linear model on non-linear data)
- [ ] **Implementation bugs** — gradient updates not stopped during eval, wrong loss function, wrong tensor shapes, etc.
- [ ] **Hyperparameter choices** — same model, wrong hyperparameters, won't converge
- [ ] **Data problems** — mislabeled samples, label/feature misalignment, outdated normalization stats
- [ ] **Feature problems** — too many features (overfitting), too few (under-capacity)

**Three debugging techniques to apply (Karpathy's "Recipe for Training Neural Networks"):**

1. **Start simple and add components.** Begin with the simplest version of your model. Add complexity (more layers, regularization, multi-loss objectives) one piece at a time. If you start by cloning a complex SOTA implementation and plugging in your data, you can't isolate which component is breaking.

2. **Overfit a single batch.** Train on a tiny dataset (10 images, 100 sentence pairs) and verify the model can drive loss to near-zero or accuracy to near-100%. If it can't, your implementation is broken — no point training on the full dataset.

3. **Set a random seed.** Otherwise you can't tell whether a performance change came from your code change or from random initialization. Set seeds for weight init, dropout, data shuffling, etc.

### Step 3.3 — Distributed training (when scale demands it)

Most teams won't need this. When you do, the choices are:

**Data parallelism** (most common): split data across machines; each machine has a full model copy; accumulate gradients.

| Approach | How it works | Tradeoff |
|----------|-------------|----------|
| **Synchronous SGD (SSGD)** | Wait for all machines before updating | Stragglers slow everything down |
| **Asynchronous SGD (ASGD)** | Update weights as gradients arrive | Gradient staleness — the model may have moved before a worker's gradient lands |

In practice, when gradient updates are sparse (most updates touch only a small fraction of parameters), ASGD converges similarly to SSGD. Modern algorithms address straggler issues effectively.

**Model parallelism:** split *the model itself* across machines (different layers on different machines). Often the layers can't run in parallel (layer 2 needs layer 1's output) — naive model parallelism is slower.

**Pipeline parallelism:** the trick for making model parallelism efficient. Break each machine's work into chunks; while machine 2 processes chunk 1, machine 1 processes chunk 2. Reduces idle time.

**Practical issues to plan for:**
- Effective batch size grows with machine count. GPT-3's 3.2M batch size (2020) is at the high end. Past a threshold, larger batches give diminishing returns.
- Master-worker imbalance — the master often does more work than other workers. Imbalance the batch sizes (smaller for master) if needed.
- Gradient checkpointing trades compute for memory: ~10x larger models on the same GPU at ~20% compute cost. Useful when memory is the bottleneck.

**Use the simpler option first.** Single-GPU training before multi-GPU, before multi-machine, before pipeline parallelism. Each step adds complexity that's hard to debug.

### Step 3.4 — Practices checklist

- [ ] Experiment tracking tool in place from day one (don't bolt it on later)
- [ ] Random seeds set everywhere
- [ ] "Overfit a batch" test passes before scaling up training
- [ ] Code starts simple; complexity added one component at a time
- [ ] Data version tracked alongside code version
- [ ] Distributed training only when single-machine training proves insufficient

---

## Task 4: Tune Models with AutoML

**Use when:** You have a candidate model and want to find its best hyperparameters; or you're considering automating parts of architecture design itself.

AutoML splits into two practical regimes.

### Step 4.1 — Soft AutoML: hyperparameter tuning (mainstream practice)

The same model with different hyperparameters can give dramatically different performance. Tuning them systematically beats manual ("Graduate Student Descent") tuning.

**Hyperparameters that matter:**
- Learning rate
- Batch size
- Number of layers / hidden units
- Dropout probability
- Optimizer-specific parameters (β₁, β₂ in Adam, momentum, etc.)
- Regularization strength
- Quantization level (mixed-precision, fixed-point)

**Search methods:**

| Method | How | When to use |
|--------|-----|-------------|
| **Grid search** | Try all combinations from a fixed grid | Small search space, low-dimensional |
| **Random search** | Sample randomly from the search space | Often beats grid in higher dimensions; cheap to parallelize |
| **Bayesian optimization** | Build a surrogate model of the objective; pick next points expected to be informative | When evaluating each configuration is expensive (long training runs) |

**Tools:** Keras Tuner (TensorFlow), Ray Tune (framework-agnostic), auto-sklearn (scikit-learn), Optuna (popular general-purpose). Most ML frameworks ship with built-in or first-party utilities.

**Sensitive vs. insensitive hyperparameters.** Some have huge impact (learning rate); some don't matter much. Prioritize tuning the sensitive ones — running 100 experiments on irrelevant hyperparameters wastes compute.

**Hard rule — don't tune on the test split.** Pick hyperparameters using the validation split. Report final performance on the test split. Tuning on the test split overfits the model to that split and inflates reported performance. (This is a special case of Ch. 4 Task 3's leakage prevention.)

### Step 4.2 — Hard AutoML: NAS and learned optimizers (research-grade)

Treats whole model components as hyperparameters.

**Neural Architecture Search (NAS).** Three components:
- **Search space:** building blocks (conv layers, activations, pooling, etc.) and constraints on how they combine
- **Performance estimation:** how to evaluate candidate architectures cheaply (without full retrain)
- **Search strategy:** how to explore (RL, evolution; random search is too expensive even for NAS)

**Learned optimizers.** Replace Adam/SGD with a neural network that learns how much to update model weights. Trained once on many tasks, then reused. Can recursively be used to train better learned optimizers.

**Reality check.** Hard AutoML is expensive — training a learned optimizer or running serious NAS requires the kind of compute only a handful of organizations have. For most teams:
- Use the *outputs* of hard AutoML (e.g., EfficientNets — produced by Google's NAS work and now widely used)
- Don't try to run hard AutoML yourself unless you have specific reasons and large compute budgets

### Step 4.3 — Decision guide

| Situation | Approach |
|-----------|----------|
| Need to find good hyperparameters for a chosen model | Soft AutoML — random search or Bayesian optimization |
| Want to compare a few architectures fairly | Run equal-budget hyperparameter search on each (Tip 3 from Task 2) |
| Considering NAS or learned optimizers from scratch | Almost certainly use a pre-trained NAS-derived model (EfficientNets, etc.) instead |
| Hyperparameter tuning is taking too long | Reduce search space to sensitive hyperparameters; use Bayesian optimization to be sample-efficient |

---

## Task 5: Evaluate a Model Before Deployment

**Use when:** You have a candidate model and need to decide whether it's good enough to deploy. Aggregate metrics alone aren't enough — production-readiness requires a fuller evaluation.

### Step 5.1 — Always set baselines first

Metrics alone are meaningless. "F1 = 0.90" sounds great until you realize random achieves nearly the same on a 90/10 imbalanced split.

**Five baselines to consider:**

| Baseline | What it measures | Example |
|----------|-----------------|---------|
| **Random** | Performance with no learning | Uniform random or sampling from label distribution. Set the floor. |
| **Simple heuristic** | Performance with rule-based logic, no ML | "Sort newsfeed reverse-chronological" — does ML beat this? |
| **Zero rule** | Predict the most common class always | If 70% accurate, your model must significantly beat 70% to justify itself |
| **Human** | Performance of human experts | Critical when ML is replacing or assisting humans |
| **Existing solution** | Current production system or third-party | A model only slightly worse than current can still be useful if cheaper/simpler |

**Rule:** report your model's metrics alongside at least one meaningful baseline. Without that comparison, the metric is decoration.

### Step 5.2 — Run perturbation tests (robustness)

Inputs in production are noisier than inputs during training. Test how your model handles that.

**How to run:**
- Take your test split
- Apply realistic perturbations: background noise, image cropping, typos, microphone-quality changes
- Measure performance on perturbed test data

**Decision rule:** prefer the model that performs best on *perturbed* data, not the one that wins on clean data.

**Why it matters:** sensitivity to noise = production fragility. Any change in user behavior (better cameras, different noise profiles) will degrade a noise-sensitive model. Also more vulnerable to adversarial attacks (Ch. 3 Task 5 covered adversarial augmentation as a defense).

### Step 5.3 — Run invariance tests (fairness)

Some input changes shouldn't affect outputs. If they do, you have bias.

**Examples of inputs that shouldn't change predictions:**
- Race, gender, sexual orientation, religion (in lending, hiring, screening)
- Names that signal demographics (résumés)
- Zip codes that proxy for socioeconomic class

**How to run:**
- Take a test example, change only the sensitive attribute, predict again
- If predictions differ, the model is biased on that attribute

**Best practice:** exclude sensitive attributes from features in the first place. Some legal frameworks (in lending, hiring) require this. Doesn't fully prevent bias (proxies still exist) but is a baseline.

This connects to Ch. 1's framing of fairness as a production requirement, not a nice-to-have.

### Step 5.4 — Run directional expectation tests (sanity)

Some input changes *should* produce predictable directional changes.

**Examples:**
- Increasing a house's lot size → predicted price should not decrease
- Decreasing square footage → predicted price should not increase
- Adding more spam keywords to an email → spam probability should not decrease

**How to run:**
- Identify monotonic or directional relationships you expect to hold
- Generate paired test inputs differing on the relevant axis
- Verify predictions move in the expected direction

If they don't, your model is learning something other than what you think. Investigate before deploying.

### Step 5.5 — Check model calibration

A calibrated model's predicted probabilities match empirical frequencies. If a model says "70% probability of X," then across many such predictions, X should happen ~70% of the time.

**When calibration matters:**
- You're using probabilities as actual probabilities (expected click count, expected revenue)
- You combine model outputs across systems (calibration mismatches compound)
- Users see and rely on confidence numbers

**When calibration matters less:**
- You only care about ranking (which item is most probable, regardless of absolute number)

**How to measure:**
- Bin predictions by predicted probability
- For each bin, measure the empirical frequency of the positive event
- Plot predicted probability vs. empirical frequency — diagonal = calibrated

`sklearn.calibration.calibration_curve` produces this for binary classifiers.

**How to fix miscalibration:** Platt scaling (`sklearn.calibration.CalibratedClassifierCV`). Logistic Regression is naturally calibrated because it directly optimizes log-loss; Naive Bayes and SVMs typically need scaling.

**Real example:** a recommender for a user who watches 80% romance / 20% comedy will recommend only romance if you pick top-ranked items. A calibrated recommender would output 80% romance / 20% comedy in its slate — matching the user's actual preferences.

### Step 5.6 — Confidence measurement (per-instance, not just aggregate)

Instead of "the model is 95% accurate on average," ask "how confident is the model on *this* prediction?"

**Use confidence to:**
- Show only high-confidence predictions to users; loop in humans or ask for more info on low-confidence ones
- Block a prediction from being shown if confidence is below a threshold
- Route low-confidence cases to an alternate system

**Why per-instance matters:** for high-stakes decisions (medical, legal, financial, predictive policing), a single confident-but-wrong prediction can cause serious harm. Aggregate accuracy doesn't tell you which cases the model is unsure about.

**Decisions to make:**
- [ ] What's our confidence threshold for showing predictions?
- [ ] What do we do with predictions below threshold (discard, escalate to human, defer)?
- [ ] How do we monitor confidence-distribution changes in production over time?

### Step 5.7 — Run slice-based evaluation

Aggregate metrics can hide critical performance differences across subgroups.

**Two failure modes that overall metrics miss:**

1. **Different performance on subgroups when it should be the same.** Model A: 98% on majority, 80% on minority → 96.2% overall. Model B: 95% on majority, 95% on minority → 95% overall. Aggregate metrics pick A; fairness picks B.

2. **Same performance on subgroups when it should be different.** Critical subsets (paid users, high-value customers) deserve more attention than aggregate.

**Simpson's paradox.** A model can be better than another *on every subgroup* yet worse overall (or vice versa). This actually happens — the 1973 Berkeley admissions data showed apparent gender bias overall but admission rates *favored women in 4 of 6 departments* when sliced. Aggregation can reverse the apparent direction of an effect.

**Three approaches to find slices:**

| Approach | How | Best for |
|---------|-----|----------|
| **Heuristics-based** | Slice by known dimensions (mobile vs. desktop, geographic region, browser, account age) | When you have domain expertise about meaningful slices |
| **Error analysis** | Examine misclassified examples; look for common patterns | When errors cluster around something you didn't expect |
| **Slice finder algorithms** | Automated search for slices where performance differs | Large feature spaces; when you suspect slices but don't know where |

**Slicing checklist before deployment:**
- [ ] What demographic / behavioral slices exist in our data?
- [ ] What slices are *critical* (paid users, regulated populations, high-stakes cases)?
- [ ] Have we measured per-slice performance for each one?
- [ ] Do any slices have substantially worse performance than overall?
- [ ] Is the difference acceptable or does it require intervention?

### Step 5.8 — Pre-deployment evaluation checklist

Walk this before signing off on deployment:

- [ ] Multiple meaningful baselines reported alongside model metrics
- [ ] Perturbation tests passed (acceptable robustness to realistic noise)
- [ ] Invariance tests passed (no bias on sensitive attributes)
- [ ] Directional expectation tests passed (model behaves sensibly on monotonic relationships)
- [ ] Calibration measured (and corrected if needed for the use case)
- [ ] Confidence thresholds defined for production filtering
- [ ] Slice-based evaluation done on critical subgroups
- [ ] Model performance on each slice documented and reviewed

---

## Appendix A: Background Context (not task-critical)

### Four phases of ML adoption

A useful project-strategy framework, separate from model-selection:

1. **Before ML** — heuristics. Facebook's chronological newsfeed (2006) ran for years before ML was added. Often heuristics are good enough.
2. **Simplest ML models** — logistic regression, XGBoost, KNN. Easier to deploy and iterate. Validates the framework end-to-end.
3. **Optimizing simple models** — better objectives, hyperparameter search, feature engineering, more data, ensembles.
4. **Complex systems** — only after exhausting simpler options.

Use a phase's solutions as the baseline for the next phase. Each phase teaches you something about the problem, the data, and the operational realities.

### Foundation models / LLMs as a model selection option (post-book context)

Chapter 5 was written before foundation models reshaped model selection. By 2026:
- Many problems start with "can we fine-tune or prompt an existing foundation model?" before "what custom architecture?"
- For NLP, computer vision, and increasingly multimodal tasks, the default starting point is often a pretrained foundation model rather than a from-scratch architecture
- The build-vs-buy/adapt decision now precedes the architecture decision
- The chapter's *framework* (six tips, simple-first, evaluate trade-offs) still applies — foundation models just shift what "simplest" looks like

Worth raising in Task 2 conversations: before picking between architectures from scratch, has the user considered fine-tuning or prompting a foundation model?

### Cross-functional debugging complexity

Different parts of an ML system are owned by different teams (data, labeling, ML algorithms, DevOps). Bugs cross team boundaries. When debugging, surface the question: "which component might be broken, and who owns it?" — and budget time for cross-team investigation, not just engineering work.

### Dated content (treat as illustrative, not current)

- **GPT-3 batch size of 3.2M (2020)** — current frontier models are larger. The point (diminishing returns past a threshold) holds.
- **20/22 winning Kaggle solutions in 2021 used ensembles** — directionally still true.
- **Top SQuAD 2.0 solutions all ensembles (Jan 2022)** — leaderboard has moved; the lesson generalizes.
- **Jeff Dean's "Solution = data + 100x computation" (2018)** — the Bitter Lesson has been validated. Hyperparameter AutoML is mainstream; NAS less so. Foundation models extended the trend further.
- **DVC, Weights & Biases as canonical experiment-tracking tools** — both still major. The ecosystem has expanded (MLflow, Comet, Neptune, ClearML).
- **GDPR and data versioning** — still applies; EU AI Act and similar regulations have added layers in 2024–2026.
- **"BERT vs. gradient boosted trees" anecdote** — still illustrative of the human-bias point even though the specific architectures have evolved.
- **"Most progress in last decade due to neural networks getting bigger"** (2021 framing) — even more true in 2026.
- **Berkeley 1973 admission data** — historical, valid example of Simpson's paradox.

### Things we didn't save (and why)

- **The Jeff Dean / TensorFlow DevSummit AutoML reveal anecdote** — color, no task content.
- **Detailed Python cross-entropy implementation** — well-known.
- **Long Facebook newsfeed history** — illustrates "before ML"; the four-phases framework already captures the lesson.
- **Detailed bagging probability calculation** — the table is the takeaway; the multiplication is trivial.
- **The "Graduate Student Descent" joke** — cute, no payoff.
- **Detailed exposition on different distributed training algorithms** — the practical decision (data parallel default; model/pipeline parallel only when needed) is what matters; specific algorithms (Hogwild!, etc.) are niche.

---

## Appendix B: Cross-chapter connections

Populated as later chapter skills are built.

### From Ch. 1 — Production Fundamentals

**Refinements:**
- **Ch. 1 Task 1's ML go/no-go gate** is sharpened by Ch. 5 Task 1's problem framing. After Ch. 1 confirms "we should use ML," Ch. 5 Task 1 asks "what *shape* of ML problem is this?" — inputs, outputs, objective.
- **Ch. 1 Task 2's stakeholder mapping** with conflicting objectives is answered technically by Ch. 5 Task 1's decoupling pattern. When stakeholders want different things (engagement vs. quality), don't combine into one loss; train separate models and tune the combination at serving time.
- **Ch. 1 Task 5's stakeholder talking points** on fairness/interpretability connect to Ch. 5 Task 5's invariance tests and slice-based evaluation. Those are the technical methods backing the strategic framing.

### From Ch. 2 — Data Infrastructure Decisions

**Refinements:**
- **Ch. 2 Task 4's reliability requirements** (ACID/BASE, OLTP/OLAP) inform Ch. 5 Task 3's distributed training. Data parallelism requires fast aggregation; model parallelism requires reliable inter-machine communication.

### From Ch. 3 — Training Data Strategy

**Refinements:**
- **Ch. 3 Task 4's class imbalance metrics** (F1, precision, recall, ROC, PR curves) are the metrics layer; **Ch. 5 Task 5's evaluation methods** are the broader gauntlet (perturbation, invariance, calibration, slice-based). They're complementary — Ch. 3 gives metrics; Ch. 5 gives the evaluation regime.
- **Ch. 3 Task 4's algorithm-level imbalance interventions** (focal loss, cost-sensitive learning) are loss-function modifications used during training. Ch. 5 Task 1's objective function selection should consider these when imbalance is present.
- **Ch. 3 Task 5's data augmentation** (perturbation as adversarial defense) and **Ch. 5 Task 5's perturbation tests** are paired: augmentation is the training-time defense; perturbation tests are the evaluation-time check that the defense worked.

### From Ch. 4 — Feature Engineering Decisions

**Refinements:**
- **Ch. 4 Task 4's feature evaluation** (importance via SHAP, generalization via coverage and distribution overlap) is feature-level. **Ch. 5 Task 5's evaluation methods** are model-level. Both run before deployment; both contribute to the deployment-readiness decision.
- **Ch. 4 Task 3's leakage prevention** has a Ch. 5 echo: "don't tune hyperparameters on test split" (Task 4 Step 4.1) is leakage prevention applied to AutoML.
- **Ch. 4's "more features isn't always better" framing** appears in Ch. 5's Tip 2 ("start with the simplest models") at the model level. Same principle, different layer.

### From Ch. 6 — Deployment and Inference Decisions

**Refinements:**
- **Ch. 5 Task 2's tradeoff evaluation** (compute vs. accuracy, interpretability vs. performance) feeds directly into **Ch. 6 Task 1** (online vs. batch — latency tolerance is the tradeoff) and **Ch. 6 Task 2** (cloud vs. edge — compute availability is the tradeoff). The Ch. 5 evaluation surfaces what tradeoffs matter; Ch. 6 forces concrete choices.
- **Ch. 5 Task 5's pre-deployment evaluation gauntlet** is the gate that should run *before* Ch. 6's deployment work. Don't deploy a model that hasn't passed baselines, perturbation, invariance, calibration, and slice-based evaluation.
- **Ch. 5 Task 2's "start with simplest models"** is a strong Ch. 6 input. The simplest model that solves the problem is also the easiest to compress, deploy, and serve at low latency. Compression (Ch. 6 Task 3) is sometimes a substitute for picking a smaller architecture upfront — but picking smaller upfront is usually cleaner.

**New concepts from Ch. 6 worth remembering when using Ch. 5:**
- **Compression (Ch. 6 Task 3) as a model selection input** — sometimes the right choice in Ch. 5 Task 2 is to pick a slightly worse-performing model that compresses better. Pre-distilled models (DistilBERT, MobileBERT) often beat compressed-after-training versions. Surface this option during model selection.
- **Latency budget cascading from Ch. 6 Task 1 to Ch. 5 Task 2** — when Ch. 6 Task 1 says "we need online prediction at p99 < 100ms," that constrains Ch. 5 Task 2's model choices. Some architectures are simply too slow for the latency budget regardless of optimization.
- **The "two pipelines anti-pattern"** (Ch. 6 Task 1) bites Ch. 5's reproducibility goal (Task 3). If training uses one feature pipeline and serving uses another, even with full experiment tracking you can't reproduce production behavior. Pipeline unification is part of reproducibility.

*Chapters 7–12 pending.*
