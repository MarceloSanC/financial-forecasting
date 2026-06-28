---
name: skill-builder
description: Use this skill whenever the user wants to create, design, or improve a skill.md file, build a reusable agent workflow, codify a repeated task into a skill, or turn a successful back-and-forth session into something reusable. Trigger on phrases like "create a skill", "turn this into a skill", "make this reusable", "I keep doing this same workflow", "build me an agent for X", "help me write a skill.md", or when the user is frustrated that an agent keeps failing at the same task. Also use this when the user is about to write a skill from scratch without having run the workflow manually first — this skill prevents that mistake.
metadata:
  status: draft
---

# Skill Builder

A methodology for creating high-quality skills that actually work, based on the principle that **skills should be codified from successful experience, not written from imagination**.

## Core Philosophy

Models are exceptionally good now, but they don't think — they predict tokens. They will mimic a workflow perfectly, but only if you've given them something real to mimic. A skill written from scratch without having walked the agent through the actual task is almost always incomplete, because the author doesn't yet know where the agent will fail.

**The wrong way:** Identify a workflow → immediately write a skill.md → hope it works.

**The right way:** Identify a workflow → walk the agent through it step by step → observe failures → fix them live → once it works end-to-end, codify that successful run into a skill.

Treat agents like new employees. You wouldn't hand a new hire a one-page doc and say "go." You'd work alongside them, correct them, let them fail, then write the SOP once you both know what "done right" actually looks like.

## When to Use a Skill vs. an AGENTS.md / CLAUDE.md File

Before building anything, decide whether a skill is even the right container:

- **Skill** — Default choice. Only loaded into context when relevant (progressive disclosure: only the name + description sit in context; the body loads when the agent decides it needs it). Use for specific workflows, proprietary methodologies, task-specific step-by-step guides.
- **AGENTS.md / CLAUDE.md** — Only use if the information must be in context on *every single turn*. ~95% of use cases don't need this. If someone says "this codebase uses React," the agent can just read the code. Reserve these files for genuinely proprietary, always-relevant information (e.g., a specific company methodology that must be referenced every turn).

If in doubt, build a skill. Tokens in AGENTS.md cost you on every message; tokens in a skill cost nothing until needed.

## The Recursive Skill-Building Process

### Step 1: Identify a real workflow

Ask the user what they actually do — what task do they repeat often enough that codifying it would save time? Good candidates:

- Multi-step workflows that touch several tools or data sources
- Tasks where the user has a specific taste or standard the agent keeps missing
- Workflows with conditional logic ("if X, then check Y, otherwise do Z")

If the user hasn't yet run this workflow manually with an agent, **stop and do that first**. Don't skip to writing the skill.

### Step 2: Walk the agent through the workflow manually

This is the step most people skip. Sit with the agent and do the task together:

1. Give the agent the first small step ("research this company: check their Twitter, YouTube, Trustpilot, and whether they've raised funding").
2. Look at what it produces. Correct it when wrong. Be specific: "You missed Trustpilot. If two of those four signals are missing or weak, that's an automatic rejection."
3. Move to the next step. Keep correcting.
4. Watch for the silent failures — cases where the agent confidently says "looks good" because it didn't actually check deeply.

Every correction you make is a piece of information the skill will eventually need. You are generating the training data for the skill by doing the work once, properly.

### Step 3: Codify only after a successful end-to-end run

Once the agent has completed the workflow correctly at least once — with all your corrections baked in — *then* ask the agent itself to review what just happened and draft the skill:

> "Review the workflow we just completed. Write a skill.md that captures the steps, the decision criteria, and the gotchas you ran into. Use the structure below."

The agent has the context of what "done right" looks like, because you just did it together. It will write a far better skill than you could from scratch — and far better than the same agent would write cold without that shared context.

### Step 4: Use the skill, expect it to fail, improve it

The first version of the skill will still have gaps. That's expected. When it fails:

1. **Don't complain — diagnose.** Ask the agent: "Why did you fail? What error did you get?" The agent will usually tell you descriptively ("I got a 500 error — insufficient credits on the API").
2. **Pass the failure back.** Tell the agent: "You failed here. This is what went wrong. Fix it." Let it produce a fix.
3. **Update the skill.** Once fixed, say: "Now update the skill.md so this failure doesn't happen again." The agent will append the guardrail.

Each failure → fix → skill-update loop makes the skill materially better. After ~5 iterations, most skills become nearly bulletproof. This is the **recursive** part of recursive skill building: the skill improves itself through use.

## Skill Anatomy

A skill.md has two parts:

**1. YAML frontmatter (always in context):**

```
---
name: skill-name-in-kebab-case
description: One or two sentences. What the skill does AND when to trigger it. Include trigger phrases the user might actually say. Lean slightly "pushy" — models tend to under-trigger skills, so err toward inclusion.
---
```

The description is the *only* thing besides the name that sits in context until the skill fires. It must do two jobs at once: tell the agent what the skill does, and give it strong triggering signals (specific phrases, specific contexts). A vague description means the skill never gets used.

**2. Body (loads only when triggered):**

Everything else. Step-by-step workflow, decision criteria, gotchas, example inputs/outputs, references to other files if the skill is large. Keep under ~500 lines; if bigger, split into a SKILL.md that points to reference files in a `references/` subdirectory.

## Writing the Description (the most important part)

The description is what makes or breaks a skill. A skill with a perfect body but a weak description is dead weight — the agent will never load it.

Rules:

- **Lead with when to trigger, not what it does.** The agent is scanning for relevance, not reading a manual.
- **Include specific user phrases.** "Use when the user says 'generate a report', 'pull the analytics', or mentions any of [Notion, Dub, YouTube Analytics]."
- **Be slightly pushy.** Instead of "helps with reports", write "Use this skill whenever the user mentions reports, analytics, dashboards, or weekly summaries, even if they don't explicitly say 'generate a report'."
- **Name the tools/domains involved.** Helps the agent match on context even when the user's phrasing is ambiguous.

## Anti-Patterns to Avoid

- **Writing skills from scratch without running the workflow first.** The skill will be missing the failures you haven't discovered yet.
- **Downloading skills from the internet or a marketplace.** You don't have the context of what a successful run looks like for *your* setup — and downloaded skills are a real attack vector.
- **Putting workflow instructions in AGENTS.md / CLAUDE.md instead of skills.** Wastes tokens on every turn and bloats the context window, making the agent dumber as the window fills.
- **Telling the agent things it already knows.** Don't write "use React" when the codebase obviously uses React. Don't say "use a dollar sign for money." Reserve skill content for what's unique to you.
- **Scaling prematurely.** Don't set up 15 sub-agents and 30 skills on day one. Start with one agent doing one workflow well. Add sub-agents only when the main agent has enough real, codified skills that delegation makes sense.

## Token Economy

Why this matters concretely: a 1,000-line AGENTS.md is ~7,000+ tokens added to every turn. A skill with the same content costs ~50 tokens (name + description) until it's needed, then loads the body just once.

The context window is a budget. As it fills past ~70–80%, the agent gets noticeably worse — it forgets earlier instructions, confuses steps, hallucinates. Keeping context lean isn't just about cost; it's about keeping the agent sharp.

## Template

When the user is ready to draft a skill, use this structure:

```markdown
---
name: [kebab-case-name]
description: [when to trigger + what it does, with specific phrases and contexts]
---

# [Skill Name]

[One-paragraph summary of what this skill does and why it exists.]

## When to use

[Bullet list of specific scenarios. Be concrete.]

## Workflow

[Numbered step-by-step. Each step should be a specific action with a specific expected output. Include decision criteria ("if X, do Y; otherwise Z").]

## Gotchas / Known failures

[Every failure you hit during the manual walkthrough goes here, with the fix. This section grows over time via the recursive loop.]

## Examples (optional)

[One or two worked examples showing input and expected output.]
```

## How to Use This Skill

When a user asks you to help create or improve a skill:

1. **Check whether they've actually run the workflow manually.** If not, redirect: "Let's walk through this together once before writing it down — that way the skill captures real steps and real failures." Only skip this if the workflow is trivial or they insist.
2. **Run the workflow with them**, correcting as you go. Keep informal notes on every correction.
3. **After a successful end-to-end run, propose the skill.md.** Use the template above. Fill in the gotchas section with every correction from step 2.
4. **Offer the failure-loop explicitly.** Tell them: "When this skill fails later, tell me what went wrong — I'll fix it and update the skill so it doesn't happen again."
5. **Discourage shortcuts.** If they want to download a skill or skip the manual walkthrough, explain briefly why that tends to produce skills that don't work, then let them decide.
