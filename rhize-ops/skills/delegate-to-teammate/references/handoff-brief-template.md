# Handoff Brief Template

This file holds what used to live inline in `SKILL.md` Step 4: the full task-package template, the Confluence handoff brief page layout, and the attached-note-copy conventions. `SKILL.md` links here rather than inlining them, to keep the skill's own front door short.

## Full Task Package

Use this template for each task. It is the content of the Confluence handoff brief (Step 7), and the fallback Jira description when `confluence.status` isn't `ready`:

```markdown
# Task: [Clear, action-oriented title]

## What You're Doing
[2-3 sentences explaining the task in plain language. No jargon without explanation.]

## Why This Matters
[Brief context on why this task is important — business impact, client need, deadline driver. The recipient does better work when they understand the bigger picture.]

## Meeting Context (if applicable)
[Summary of key insights from the Fireflies transcript]
[Link to full transcript: Fireflies URL]

## Step-by-Step Instructions

### 1. [First step name]
**What to do:** [Clear instruction]
**How:** [Specific commands, clicks, or actions — spell it out]
**Why:** [Brief reason this step matters]

### 2. [Next step...]
[Continue pattern...]

## Tools & Skills You'll Need

### Skills to Invoke
[List relevant Cowork/Claude Code skills with the exact trigger phrase]
- `/skill-name` — what it does and when to use it during this task

### MCP Servers
[List connected MCP servers relevant to this task]
- **Server Name** — what it provides and how the recipient will use it

### CLI Commands
[Any terminal commands the recipient might need, with full syntax and explanation]

## How to Know You're Done (Validation Criteria)
- [ ] [Specific, checkable criterion]
- [ ] [Another criterion]
- [ ] [Final check — e.g., "the page loads without errors at the preview URL"]

## Watch Out For (Gotchas)
- **[Issue name]:** [What might go wrong and how to avoid/fix it]
- **[Another issue]:** [Explanation]

## Starter Prompts
Copy-paste these into Claude Code or Cowork to get going:

> "[Prompt 1 — a good opening prompt that gets Claude oriented on the task]"

> "[Prompt 2 — a follow-up prompt for the next phase of the task]"

## Reference Links
- [Attachments on the issue (by filename), public URLs, or tracker links — never a local, vault-relative, or repo-relative path]
```

## Confluence Handoff Brief Page

Body = a metadata table, then the full task package above.

| Field | Value |
|---|---|
| Delegated on | [date] |
| Due | [date] |
| Priority | [urgent\|high\|normal\|low] |
| Project | [PROJECT-KEY] |
| Delegation ID | [delegation-id] — plain text, never the `rhize-delegation:v1:` marker line |
| Jira issue | [added after creation — Step 7.5] |

The **Reference Links** section of the full package above may contain only attachment filenames, public URLs, and the Fireflies link — never a local, vault-relative, or repo-relative path.

## Attached note copies (per vault document)

- **Filename:** `<title>.md`, as written by the exporter's `--out-dir`.
- **Body:** `body_markdown` verbatim — no additional wrapper. It already ends with "Attached to this issue" and, when needed, "Files to request from the delegator".
- **Embedded files:** uploaded alongside it, under their own names, from `attachments[].path`.
- The delegation marker never appears in an attachment.

`unresolved_links` are never inside an attachment — they go to the Step 10 report only.
