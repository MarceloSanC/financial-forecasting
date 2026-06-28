# DMLS Ch. 3 — Training Data Strategy (Task Reference)

Task-oriented notes from Chip Huyen's *Designing Machine Learning Systems*, Chapter 3. Organized around the decisions you make when building training data for a production ML model.

<!--
METADATA (for hybrid spine-skill assembly)
source: DMLS Ch. 3 — Training Data
tasks_supported:
  - task-1-choose-a-sampling-strategy
  - task-2-design-a-labeling-strategy-with-limited-hand-labels
  - task-3-manage-labeling-quality-and-multiplicity
  - task-4-handle-class-imbalance
  - task-5-apply-data-augmentation
spine_topics_likely_to_pull_from_this_chapter:
  - designing-the-data-strategy (primary, pairs with Ch. 2)
  - model-development-and-evaluation (metrics, augmentation)
  - operating-in-production (stream sampling, active learning)
-->

**Five tasks this reference supports:**
1. **Choose a Sampling Strategy** — pick the right sampling method for training data (or stream monitoring, or evaluation)
2. **Design a Labeling Strategy When Hand Labels Are Limited** — choose between weak supervision, semi-supervision, transfer learning, active learning, or a combination
3. **Manage Labeling Quality and Multiplicity** — run annotation operations with quality control, lineage, and disagreement resolution
4. **Handle Class Imbalance** — pick metrics, then data-level and/or algorithm-level interventions
5. **Apply Data Augmentation** — expand training data via transformations, perturbation, or synthesis

Each task is self-contained. Background and dated data points are in Appendix A.

**Dependency note:** This chapter picks up where Chapter 2 left off. Chapter 2 maps where data comes from; Chapter 3 turns that data into training data. Don't re-derive source taxonomy here — refer back to Ch. 2 Task 1 if the question involves "where does data come from."

---

## Task 1: Choose a Sampling Strategy

**Use when:** You need to select a subset of data for training, for evaluation splits, for monitoring, or for any situation where you can't use all available data. Sampling decisions bake in bias — getting this right up front is cheaper than fixing biased models later.

### Step 1.1 — Rule out non-probability sampling for production models

Non-probability sampling picks samples based on something other than probability — availability, convenience, expert judgment, or quotas. Common types:

| Method | How it works | Typical problem |
|--------|--------------|-----------------|
| Convenience | Sample what's easiest to get | Selection bias toward what's available |
| Snowball | Use existing samples to find next samples (e.g., scrape accounts via follow lists) | Bias propagates through the network |
| Judgment | Experts pick samples | Encodes expert's assumptions |
| Quota | Fixed counts per group, no randomization | Ignores real-world distribution |

**When to use:** bootstrapping an early prototype, fast iteration before real data is available. Fine for "can we even try this?" experiments.

**When NOT to use:** production models that need to generalize. Non-probability samples are not representative of the population and models trained on them inherit those biases.

**Real-world examples of this bias biting:**
- Language models trained on Wikipedia + CommonCrawl + Reddit — biased toward content creators who write there, not general population.
- Sentiment analysis trained on IMDB/Amazon reviews — biased toward people who leave online reviews.
- Self-driving car data from sunny Phoenix and the Bay Area — scarce data for rainy/snowy conditions.

If any of these patterns describe your situation, flag the bias risk explicitly.

### Step 1.2 — Pick a probability-based method

Five random sampling methods cover most production needs:

| Method | How it works | Use when | Drawback |
|--------|--------------|----------|----------|
| **Simple random** | Equal probability for every sample | Population is uniform enough that you don't care about rare classes | Rare classes (<1%) likely missed entirely |
| **Stratified** | Divide into strata (groups), sample from each separately | You have classes/groups you want to guarantee representation for | Hard/impossible when samples belong to multiple groups (multi-label tasks) |
| **Weighted** | Each sample has explicit probability weight | You have domain knowledge that some samples matter more (recency, rarity), OR your data distribution differs from the real-world target distribution | Getting the weights wrong amplifies bias |
| **Importance** | Sample from distribution Q (easy) and reweight to simulate P (hard) | You can't sample directly from the distribution you actually want; P(x) is expensive but Q(x) is available | Requires Q(x) > 0 whenever P(x) > 0 |
| **Reservoir** | Streaming algorithm; maintain a random sample of size k from an unbounded stream | You're sampling from a stream where you don't know the total size and can't fit it all in memory | More complex to implement than the others |

### Step 1.3 — Stream sampling: the reservoir algorithm

When you have continually incoming data (user events, sensor data, tweets) and want to sample `k` items with equal probability, use reservoir sampling. You can stop the algorithm at any time and the samples will have the correct probabilities.

**Algorithm:**
1. Put the first `k` elements into the reservoir (an array of size `k`).
2. For each incoming `n`th element (where `n > k`), generate a random integer `i` such that `1 ≤ i ≤ n`.
3. If `i ≤ k`: replace the `i`th element in the reservoir with the `n`th element. Otherwise, do nothing.

**Property:** at any point, each element seen so far has `k/n` probability of being in the reservoir, where `n` is the number of elements seen. This is what "equal probability" means in the streaming setting.

### Step 1.4 — Weighted sampling vs. sample weights (don't confuse these)

| Concept | What it does | When used |
|---------|-------------|-----------|
| **Weighted sampling** | Selects which samples enter training | Dataset construction |
| **Sample weights** | Scales how much each sample contributes to the loss | Model training |

They sound similar and can have overlapping effects (both can correct for class imbalance), but they happen at different stages. Weighted sampling = before training; sample weights = during training.

### Step 1.5 — Questions to answer before finalizing a sampling strategy

- [ ] Does my data have rare classes that simple random would miss? (→ stratified or weighted)
- [ ] Do I have multi-label samples that break stratification? (→ weighted with per-label logic)
- [ ] Is my observed distribution different from the target distribution? (→ weighted or importance sampling)
- [ ] Is the data a stream with unknown total size? (→ reservoir)
- [ ] Am I sampling for training, for evaluation, or for monitoring? (Different splits may need different strategies — e.g., stratified for training to handle imbalance, simple random for held-out evaluation to preserve real-world distribution.)
- [ ] Are there biases in the *population* I'm sampling from that no sampling method can fix? (Flag this; sampling can't rescue a fundamentally biased source.)

---

## Task 2: Design a Labeling Strategy When Hand Labels Are Limited

**Use when:** Starting a supervised ML project, or stuck because labels are too expensive/slow/unavailable. Most production supervised ML runs into this — plan for it rather than discovering it mid-project.

### Step 2.1 — Audit what you have and what you can get

Answer these first:

- [ ] Do we have **natural labels** that appear as a byproduct of the product? (Click-through on an ad, user rating, purchase, conversion — these are free labels.)
- [ ] Do we have **any hand labels** already, even a small seed?
- [ ] Can we hire/contract annotators? At what cost? For what turnaround?
- [ ] Does our data have **privacy restrictions** that prevent sending it to third-party labelers?
- [ ] Is there a **pretrained model** in a related domain we can build on?
- [ ] Do we have **subject matter experts** on staff (doctors, lawyers, engineers) whose time we can spend on encoding rules?

The answers determine which approach(es) fit.

### Step 2.2 — Pick among the four approaches (or combine)

| Approach | How it works | Ground truth needed? | Good for |
|----------|--------------|---------------------|---------|
| **Weak supervision** | Write labeling functions (LFs) that encode heuristics — keywords, regex, DB lookups, other models' outputs. Combine + denoise to get probabilistic labels. (Snorkel is the canonical tool; LLM-based labeling is now an alternative — see Appendix A.) | None strictly required; small hand-labeled sample highly recommended to evaluate LF quality | Strict data privacy (LFs apply without labelers seeing data); fast scaling; need to version expertise across team |
| **Semi-supervision** | Start with small labeled seed; use structural assumptions (self-training on high-confidence predictions, similarity clustering, or perturbation invariance) to propagate labels | Yes — a small seed of hand labels | You have *some* labels but not enough; structure in the data allows propagation |
| **Transfer learning** | Use a model pretrained on a related task as the starting point; use zero-shot or fine-tune | Zero-shot: none. Fine-tuning: yes, but often far fewer than training from scratch | Lots of related-domain pretrained models exist (almost always true now for text, image, audio); lowers cost of entry |
| **Active learning** | Model picks which unlabeled samples to send to annotators next — usually the most uncertain, or the samples a committee disagrees on | Yes — annotators in the loop | Labeling budget is limited and you want to maximize learning per label |

### Step 2.3 — Decision shortcut

Apply in roughly this order:

1. **Can we get natural labels?** If yes, start there. Supplement with hand labels for edge cases.
2. **Is there a strong pretrained model for this domain?** If yes, start with transfer learning. For text/image tasks in 2026, this is almost always the answer.
3. **Do we have subject matter expertise and privacy constraints?** Weak supervision fits well — SMEs encode heuristics once and they apply at scale without exposing data.
4. **Do we have a small seed of labels and structure in the data?** Semi-supervision can expand a seed cheaply.
5. **Is our labeling budget the constraint?** Active learning maximizes learning per label but requires active annotator involvement.

These are often combined. Common pattern: transfer learning base model + weak supervision to generate initial labels + active learning to refine on edge cases.

### Step 2.4 — Benchmarks worth knowing (all illustrative, not current)

- **Weak supervision effectiveness:** In a Stanford Medicine study, 8 hours of a single radiologist writing labeling functions produced models with comparable performance to models trained on nearly a year of hand labels (CXR and EXR tasks). Models kept improving with more unlabeled data even without more LFs. 6 LFs were reusable across related tasks.
- **Active learning effectiveness:** On a toy example, 30 random labels → 70% accuracy; 30 actively-chosen labels → 90% accuracy. Real gains vary widely but the pattern (active >> random) is consistent.
- **Hand labeling cost calibration:** Phonetic-level speech transcription takes ~400x the utterance duration. 1 hour of audio = 400 hours of annotator time. Plan accordingly.

### Step 2.5 — Questions to answer in the strategy write-up

- [ ] What's our target label count? For what time budget?
- [ ] What's the fallback if the primary approach underperforms?
- [ ] How will we measure label quality? (Gold set, inter-annotator agreement, downstream model performance?)
- [ ] Who owns the labeling operation? (→ Task 3)
- [ ] What's our plan when the task definition changes? (Relabeling vs. reapplying LFs vs. fine-tuning differ by approach.)

---

## Task 3: Manage Labeling Quality and Multiplicity

**Use when:** You're running an annotation operation — hand labeling, expert review, or crowdsourced labeling. Strategy (Task 2) decides *what* approach; this task decides *how* to run it.

### Step 3.1 — Write a clear problem definition before labeling starts

Most annotator disagreement comes from ambiguous instructions, not from genuine difference of opinion.

**Example of the problem:** Three annotators given the same entity-recognition sentence produce 3, 6, and 4 entities respectively — each with defensible interpretations.

**The fix:** define the rule. For the entity example, a rule like "when multiple nested entities are possible, pick the one spanning the longest substring" eliminates most of the disagreement.

**Checklist for the problem definition:**
- [ ] How do we handle ambiguous cases? (Specific rule, not "use your judgment.")
- [ ] What's the label schema? All valid labels, including edge cases like "unknown" or "not applicable"?
- [ ] What's an example of a correctly-labeled sample for each label class?
- [ ] What's an example of a commonly-confused pair, and the rule that disambiguates?

### Step 3.2 — Train annotators and measure agreement

- [ ] All annotators see the written problem definition and worked examples.
- [ ] Run a calibration round: have every annotator label the same small set (50–200 items) and measure inter-annotator agreement.
- [ ] For disagreements, go back to the definition and clarify. Iterate until agreement stabilizes.
- [ ] Plan ongoing quality checks — re-label a sample of each batch to catch drift.

**The higher the domain expertise needed, the higher the expected disagreement.** Medical imaging, legal documents, nuanced text — expect disagreement and plan for arbitration. For simple tasks (spam classification), expect high agreement quickly.

### Step 3.3 — Track data lineage

**Data lineage** = tracking the origin and annotator of every sample. Without it, diagnosing a model regression is much harder.

**What to track for each sample:**
- Source (which dataset, which collection round, which data stream)
- Annotator or annotator pool
- Annotation date
- Annotation schema version (in case the label schema evolved)
- Quality-check status (gold-reviewed, spot-checked, unchecked)

**Why it matters:** Chip's concrete case study — a team added 1M crowdsourced labels to an existing 100K well-labeled set. Model performance *dropped*. Root cause was lower-quality labels in the new batch, but without lineage they couldn't separate the batches and the data was already mixed.

### Step 3.4 — Decide how to resolve multiplicity

When you have multiple labels for the same sample (multiple annotators, multiple sources, multiple labeling functions), pick a resolution strategy:

| Strategy | When to use |
|----------|-------------|
| Majority vote | Several annotators of roughly equal quality |
| Weighted vote by annotator quality | You have calibrated annotator accuracy (e.g., from a gold set) |
| Expert arbitration | High-stakes, low-volume disagreements |
| Probabilistic (Snorkel-style) | Many noisy sources; want uncertainty in the final label |
| Keep both and let the model handle it | Multi-label tasks where multiple labels can coexist |

### Step 3.5 — Privacy considerations during labeling

- [ ] Can data leave the organization? If no, annotation must be on-premise or via trusted contractors.
- [ ] Is PII present? Redaction may be required before annotators see data.
- [ ] If weak supervision fits, it's often the privacy-safest approach — LFs touch a small cleared sample; everything else is labeled programmatically.
- [ ] For healthcare or financial data, regulatory constraints often rule out third-party crowdsourcing entirely.

---

## Task 4: Handle Class Imbalance

**Use when:** Your training data has substantially more examples of some classes than others. This is *the norm* in real-world production ML — fraud, churn, disease, rare events. Not a fringe case; budget for it.

Before picking interventions, understand the three reasons imbalance hurts learning:
1. **Insufficient signal** for the minority class (few-shot territory or worse).
2. **The model can exploit majority-class-everywhere heuristics.** A 99.99% majority class gives a trivial 99.99%-accurate "always predict majority" model that gradient descent struggles to escape.
3. **Asymmetric error costs.** A missed cancer case is not the same kind of error as a false positive. Unless the loss function encodes this, the model treats them identically.

Also: class imbalance can be **inherent** (rare events), **sampling-caused** (your pipeline filters one class out before data lands in training), or **labeling-error-caused** (annotator mistakes). Diagnose the source before intervening.

### Step 4.1 — Fix metrics first, then interventions

Wrong metrics will hide model failures. Never start class-imbalance work by picking a technique; start by picking metrics that will tell you whether the technique worked.

**Don't use overall accuracy for imbalanced problems.**

Chip's illustration: Two cancer-detection models with 90% accuracy, but model A catches 10/100 cancers and model B catches 90/100 cancers. Overall accuracy can't distinguish them — you'd ship the useless one. Per-class accuracy, F1, and recall distinguish them sharply.

**Metrics that work for imbalance:**

| Metric | What it measures | When to use |
|--------|------------------|-------------|
| Per-class accuracy | How well the model does on each class separately | Always useful; the simplest corrective to overall accuracy |
| Precision | Of the samples predicted positive, how many actually are | When false positives are costly |
| Recall (true positive rate) | Of the actual positives, how many did we catch | When false negatives are costly (disease screening, fraud) |
| F1 | Harmonic mean of precision and recall | Balanced view of both; asymmetric by positive class choice |
| ROC curve / AUC | TPR vs. FPR across all thresholds | Threshold-free view; choose operating point after |
| Precision-recall curve | Precision vs. recall across all thresholds | More informative than ROC on heavily imbalanced data (Davis & Goadrich, 2006) |

**Key subtlety:** F1 and recall are *asymmetric* — they depend on which class you call positive. For a cancer detector, calling CANCER the positive class is the right framing. If you flip it, your F1 looks great but on the wrong class.

### Step 4.2 — Data-level interventions (resampling)

Change the data distribution to make it less imbalanced.

| Technique | What it does | Risk |
|-----------|-------------|------|
| **Random oversampling** | Duplicate minority class samples until ratio is acceptable | Overfitting on repeated samples |
| **Random undersampling** | Drop majority class samples | Losing useful information |
| **SMOTE** | Generate synthetic minority samples as convex combinations of existing ones | Only works on low-dimensional data; risky for high-dim feature spaces |
| **Tomek links** | Remove majority-class samples that are closest to minority-class samples, sharpening the decision boundary | Can remove useful edge-case info; only low-dim |
| **Two-phase learning** | Train on resampled (balanced) data, then fine-tune on original imbalanced data | More complex pipeline |
| **Dynamic sampling** | During training, oversample currently-underperforming classes and undersample currently-well-performing ones | Requires mid-training performance tracking |

**Hard rule:** Never evaluate on resampled data. Always evaluate on the original distribution (or a representative held-out set). Evaluating on resampled data produces optimistic numbers that won't hold in production.

### Step 4.3 — Algorithm-level interventions (loss function)

Keep the data distribution; change how the model weights errors.

| Technique | What it does | When to use |
|-----------|-------------|-------------|
| **Cost-sensitive learning** | Define a cost matrix `C_ij` for "actual i, predicted j" and weight the loss accordingly | You have specific, quantifiable asymmetric costs (e.g., cost of missed fraud vs. cost of false alarm) |
| **Class-balanced loss** | Weight each class inversely proportional to its size in training data | Good default when you don't have specific cost numbers. Refinements exist (e.g., Cui et al. 2019 account for sample overlap) |
| **Focal loss** | Scale loss so easy-to-classify samples contribute less, hard samples contribute more | Useful when the majority class contains many "trivially easy" samples the model dispatches quickly; frees capacity for harder minority examples (originated in object detection) |

### Step 4.4 — Decision procedure

Walk this order:

1. **Diagnose the source of imbalance.** Inherent? Sampling pipeline? Labeling errors? Fix the labeling/sampling issues first if present.
2. **Pick metrics** that will reveal per-class performance. Set baseline numbers.
3. **Consider whether to fix imbalance at all.** Large modern networks sometimes learn imbalanced data fine on their own. If you have a big model and lots of data, try first without resampling and see the metrics.
4. **If metrics say intervention is needed, try algorithm-level first.** Class-balanced loss or focal loss usually beats resampling for modern deep networks on high-dim data.
5. **Use data-level methods when algorithm-level isn't enough** or when you're using a model family that can't easily take weighted losses.
6. **Expect to iterate.** Imbalance intervention often needs tuning against the metrics, not a one-shot fix.

### Step 4.5 — Context on when imbalance is less of a problem

- **Binary imbalance** is much easier to handle than **multiclass imbalance**.
- **Linearly separable problems** are unaffected by imbalance at all (Japkowicz 2000).
- **Deeper networks** handle imbalance better than shallow ones (Ding et al. 2017 — "very deep" then meant >10 layers; modern nets are vastly deeper and generally more robust).
- **Sensitivity to imbalance increases with problem complexity.**

So the first question isn't "how imbalanced is the data" but "how hard is this classification problem, and how much capacity does my model have?"

---

## Task 5: Apply Data Augmentation

**Use when:** You have limited training data, OR your model is overfitting, OR you want robustness to noise and adversarial inputs. Increasingly a default for computer vision and making inroads in NLP.

Three families of techniques. Pick based on your data type and goal.

### Step 5.1 — Simple label-preserving transformations

Modify inputs in ways that don't change the correct label. The classic approach.

**For computer vision:**
- Random crops, flips (horizontal/vertical), rotations
- Color jitter, brightness/contrast changes
- Random erasing (black out parts of the image)
- Inversion

A rotated dog is still a dog. Done on CPU while GPU trains the previous batch → effectively free compute-wise (noted in the original AlexNet paper).

**For NLP:**
- Synonym swap using a thesaurus or word embeddings (swap "happy" for "glad")
- Case preservation: "I'm so happy to see you" → "I'm so glad to see you"

**Goal:** cheap 2–3x expansion of training data. No robustness benefit against adversarial inputs.

### Step 5.2 — Perturbation (adversarial augmentation)

Add noise to inputs. The purpose is robustness, not just data expansion.

**Why:** neural networks are surprisingly fragile. One-pixel attacks can misclassify 67.97% of CIFAR-10 and 16.04% of ImageNet test images. Small, humanly-invisible perturbations can flip model predictions.

**Defense:** train the model on perturbed samples. Model learns to be robust to small input changes.

**For computer vision:**
- Random noise injection (Gaussian noise to pixel values)
- Targeted adversarial samples (e.g., DeepFool finds the minimum perturbation needed to cause misclassification; train on these)

**For NLP:**
- Adversarial augmentation is harder (random characters make nonsense, not a semantically similar sentence)
- BERT-style masking: randomly mask 15% of tokens; replace 10% of those with random words. Small perturbation during pretraining improves robustness

**When to use:**
- Your model will face adversarial inputs (spam, fraud, content moderation)
- You want better generalization beyond your training distribution
- Security-sensitive deployments

### Step 5.3 — Data synthesis

Generate new training samples from scratch or from combinations of existing samples.

**For NLP — templates:**
- Pattern: `"Find me a [CUISINE] restaurant within [NUMBER] miles of [LOCATION]."`
- Fill with lists of cuisines, reasonable numbers, and locations
- Generates thousands of queries from one template
- Useful for bootstrapping conversational AI or narrow-domain intent classifiers

**For computer vision — mixup:**
- Given two labeled samples `(x1, y1)` and `(x2, y2)`, generate `x' = γ·x1 + (1−γ)·x2` with label `y' = γ·y1 + (1−γ)·y2`
- Labels become continuous (e.g., 0.7 dog + 0.3 cat)
- Benefits: improved generalization, reduced memorization of corrupt labels, better adversarial robustness, more stable GAN training

**For any domain — generative model synthesis:**
- Use a trained generative model (GAN, diffusion, LLM) to produce new training samples
- CycleGAN for CT segmentation (Sandfort et al. 2019) improved model performance significantly
- Actively researched, not yet standard in production
- In the LLM era (2024+), using large models to generate synthetic training data for smaller task-specific models is becoming common; quality filtering is critical

### Step 5.4 — Decision table

| Goal | Best augmentation family |
|------|-------------------------|
| More training data, cheap | Label-preserving transformations |
| Model robustness to noise or adversarial inputs | Perturbation / adversarial augmentation |
| Very limited real data; need to bootstrap | Data synthesis (templates for NLP; generative models for complex domains) |
| Reduce overfitting on small datasets | Transformations + perturbation together |

### Step 5.5 — Questions to answer before committing to an augmentation pipeline

- [ ] Does each augmentation actually preserve the label? (Rotating an MNIST 6 by 180° gives a 9. Flipping a medical image may flip anatomy.)
- [ ] Is the augmentation representative of the real-world variation the model will face? (Adding noise types that never occur in production wastes capacity.)
- [ ] Is it cheap enough to run on-the-fly during training, or do we need to pre-generate?
- [ ] Are we measuring the augmentation's impact on the validation set, not just training loss?
- [ ] If using generative models for synthesis: how do we validate synthetic sample quality before feeding it to training?

---

## Appendix A: Background Context (not task-critical)

### Natural labels

Some tasks generate labels as a byproduct of the product itself — ad clicks (click-through rate), recommendation clicks, purchase conversions, user ratings. These are essentially free and continuous. Always check if natural labels exist before building a hand-labeling operation.

### The LLM-era update to weak supervision (post-book development)

*Chapter 3 was written before large LLMs became cheap and practical for labeling. Worth knowing:*

The chapter's Snorkel-based weak supervision (LFs written by humans, combined probabilistically) still works and is still the right frame. But in 2024–2026, using LLMs (GPT-4, Claude, etc.) to generate labels or verify labels has become a major complement or alternative. Typical pattern:

- LLM generates initial labels on a large unlabeled set
- Small hand-labeled gold set evaluates LLM accuracy per class
- Disagreements are flagged for human review
- The process combines weak supervision's scale with LLM-level semantic understanding

The chapter's core framing (programmatic labeling is cheap, adaptive, versionable, privacy-friendly) applies to LLM-based labeling too. It's the same pattern with a more capable labeling function.

Caveats: LLM labels inherit LLM biases, can hallucinate confidently, and may not be appropriate for regulated domains without human review.

### Semi-supervision method taxonomy (if needed for deeper work)

- **Self-training:** train on small labeled set, predict on unlabeled, add high-confidence predictions to training set, repeat
- **Similarity-based:** assume samples with similar characteristics share labels (clustering, K-nearest neighbor)
- **Perturbation-based:** assume small perturbations preserve labels; augment training data accordingly

Pointers for deeper work: Xiaojin Zhu's "Semi-Supervised Learning Literature Survey" (2008); Engelen and Hoos, "A Survey on Semi-Supervised Learning" (2018).

### Transfer learning context

*As of 2026:* transfer learning has continued to dominate. A non-trivial portion of production ML is pretrained-model-based. For most text/image/audio tasks, starting with a pretrained model is the default, not the exception. The chapter's prediction that "only a handful of companies can afford to train large pretrained models" has proven correct — frontier model training costs have grown into the hundreds of millions of dollars.

### Active learning methods beyond uncertainty sampling

The chapter focuses on uncertainty sampling (label what the model is least confident about) and query-by-committee (label what an ensemble disagrees on most). Other methods from Burr Settles's survey include: expected gradient length, expected model change, expected error reduction, density-weighted methods. For most production use cases, uncertainty sampling is the right starting point and works well.

### Dated data points (treat as illustrative, not current)

- **Snorkel / Stanford Medicine weak supervision study:** 8-hour LF writing ≈ ~1-year hand labeling (CXR / EXR tasks, circa 2020). Specifically valuable as proof of concept; exact numbers depend on task.
- **Credit card fraud rate:** 6.8¢ per $100 (2018). Rates vary; use as illustrative of typical imbalance magnitude.
- **Spam rate:** ~85% of email is spam (2021, Talos Intelligence). Similar — directionally consistent over years.
- **Resume screening:** 98% eliminated at initial pass. Stable across years, worth keeping.
- **One-pixel attack:** 67.97% CIFAR-10 / 16.04% ImageNet misclassification rate with one-pixel change (Su et al. 2017). Still a valid benchmark illustration.
- **"Very deep" networks:** >10 layers was "very deep" in 2017. Modern models are vastly deeper — the finding (deeper networks handle imbalance better) still holds but the threshold is no longer relevant.
- **GPT-3 training cost:** tens of millions USD. Now dated — GPT-4-class and later models cost hundreds of millions.

### Things we didn't save (and why)

- **Full derivation of importance sampling.** The equation and use case matter; the proof doesn't.
- **Historical note on semi-supervision originating in the 90s.** No action follows from this.
- **The long list of active learning heuristics beyond uncertainty and committee.** Diminishing returns.
- **Detailed math for cost-sensitive loss, class-balanced loss, focal loss.** The *when to use each* matters; formulas are standard and googleable.

---

## Appendix B: Cross-chapter connections

Populated as later chapter skills are built.

### From Ch. 2 — Data Infrastructure Decisions

**Refinements:**
- **Ch. 2 Task 1's data source taxonomy** (user input, system-generated, user behavior, internal DB, third-party) determines which sampling method fits in Ch. 3 Task 1. Streaming user input → reservoir sampling. Static internal DB → any method. Third-party data → often already sampled by vendor; be aware of their sampling choices.
- **Ch. 2 Task 3's static vs. dynamic features** ties to Ch. 3 Task 2's active learning. Dynamic features from streams feed naturally into active learning's real-time flavor.

**New concepts from Ch. 3 that refine Ch. 2:**
- **Data lineage (Task 3)** extends Ch. 2 Task 2's versioning concern. Versioning data isn't just about schema — it's about origin and annotator too.

### From Ch. 4 — Feature Engineering Decisions

**Refinements:**
- **Ch. 3 Task 1's sampling decisions** and **Ch. 4 Task 3's leakage prevention** share the same core practice: split before doing anything else. Ch. 3 says *what* to sample; Ch. 4 says *how* to split without leaking. They're joined decisions in any real pipeline.
- **Ch. 3 Task 4's class imbalance diagnosis** and **Ch. 4 Task 1's missingness diagnosis** share a meta-principle: figure out *why* the data looks the way it does before trying to "fix" it. Class imbalance can be inherent / sampling-caused / labeling-caused. Missingness can be MNAR / MAR / MCAR. Same diagnostic discipline.
- **Ch. 3's natural labels (Task 2)** combined with **Ch. 4's feature evaluation (Task 4)** — natural labels make a feature's importance and generalization much easier to measure (you can iterate quickly).

**New concepts from Ch. 4 worth remembering when using Ch. 3:**
- **Group leakage** (Ch. 4 Task 3 cause #5) is a sampling problem that Ch. 3 Task 1 doesn't directly address. When a single entity (patient, user, session) appears multiple times in your data, you have to split at the *entity* level, not the example level. This sharpens Ch. 3's stratified-sampling discussion.
- **Coverage and value-distribution overlap** (Ch. 4 Task 4) are diagnostic checks that should run on training data right after Ch. 3's sampling. If a feature's coverage differs significantly between splits, that's a flag for Ch. 3 sampling work to revisit.

### From Ch. 5 — Model Development and Evaluation

**Refinements:**
- **Ch. 3 Task 4's class imbalance metrics** (F1, precision, recall, ROC, PR curves) and **Ch. 5 Task 5's evaluation gauntlet** (perturbation, invariance, calibration, slice-based) are complementary layers. Ch. 3 gives the right *metrics* for imbalanced data; Ch. 5 gives the broader *evaluation regime*. Use both: pick imbalance-appropriate metrics (Ch. 3), then run them through the full Ch. 5 evaluation flow before deployment.
- **Ch. 3 Task 4's algorithm-level interventions** (focal loss, cost-sensitive learning, class-balanced loss) are loss-function modifications that fit into **Ch. 5 Task 1's objective function selection**. When framing a problem with imbalance, the objective function decision is where Ch. 3's interventions live.
- **Ch. 3 Task 5's data augmentation (perturbation as adversarial defense)** and **Ch. 5 Task 5's perturbation tests** are paired: augmentation is the training-time defense; perturbation tests are the evaluation-time check that the defense worked.

**New concepts from Ch. 5 worth remembering when using Ch. 3:**
- **Slice-based evaluation (Ch. 5 Task 5)** sharpens Ch. 3's class imbalance work. Aggregate metrics on imbalanced data can hide subgroup failures even when overall imbalance metrics look fine. A model with good F1 overall might still fail on a critical demographic slice.
- **Pre-deployment evaluation gauntlet (Ch. 5 Task 5)** is the gate that should run after Ch. 3's training data work. Don't deploy a model trained on imbalanced data without running invariance and slice-based tests.

*Chapters 6–12 pending.*
