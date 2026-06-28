---
title: Runbook — <Operation name in English>
description: Step-by-step procedure for <operation>
when-use: <When this procedure should be executed — be specific>
keywords: [runbook, <operation>, <component>]
status: draft
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
runbook_id: <kebab-slug>
triggers:
  - <event or condition that triggers this runbook>
estimated_duration: <e.g., 15min>
---

# Runbook — <Operation name>

> Runbooks are written and consumed in **English**. They describe operational procedures executed by humans or agents.

## Purpose

<One paragraph. What does running this procedure accomplish?>

## Triggers

When to execute this runbook:
- <trigger 1>
- <trigger 2>

## Prerequisites

- [ ] <required access, credentials, tools>
- [ ] <required state of the system>
- [ ] <required information at hand>

## Procedure

### Step 1 — <Action>

```bash
<command>
```

**Expected output:**
```
<what success looks like>
```

**If it fails:** <what to check, where to look>

### Step 2 — <Action>

<...>

### Step 3 — <Action>

<...>

## Verification

How to confirm the operation succeeded:

```bash
<verification command>
```

Expected:
- <observable signal 1>
- <observable signal 2>

## Rollback

If the operation needs to be reversed:

### Step 1 — <Rollback action>
<...>

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---|---|---|
| <error message or behavior> | <cause> | <fix> |

## Related

- ADRs: <links>
- Other runbooks: <links>
- Code: <pointers to relevant modules>
