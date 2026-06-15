---
name: delegate-to-tom
tier: custom
domain: ops
maturity: stable
description: |
  Delegate tasks to Tom Cassidy by gathering session context, formatting clear instructions, creating Jira issues, and notifying via Slack. ALWAYS use this skill when Jim says "delegate this to Tom", "hand this off to Tom", "assign this to Tom", "Tom should handle this", "send this to Tom", "create a task for Tom", "Tom can do this", "pass this to Tom", or any variation of asking Tom to take over a task. Also trigger when Jim says "delegate", "hand off", or "assign" in the context of passing work to someone else — Tom is the default recipient. This skill handles the full delegation pipeline: context gathering, Fireflies transcript analysis, task formatting, Jira issue creation, and Slack notification with @mention.
---

# Delegate to Tom

This skill turns work from Jim's current session into a clearly structured handoff package for Tom Cassidy, who handles advertising, marketing, sales, and increasingly technical tasks across the Rhize Media stack.

Tom is sharp with marketing, ads, and sales — but he's still building his technical muscles. He's learning Claude Code/Cowork, Vercel, Sanity CMS, Next.js basics, and the DataForSEO APIs. The instructions you generate for him should be thorough and encouraging, never assuming deep technical knowledge. Think of it as writing instructions for a capable colleague who needs the "why" and "how" spelled out clearly, not just the "what."

## When This Skill Triggers

Any time Jim wants to hand off work to Tom. Common phrasings:
- "delegate this to Tom"
- "Tom should handle this"
- "create tasks for Tom"
- "hand this off"
- "assign to Tom"
- Just "delegate" (Tom is the default)

## Step-by-Step Workflow

### Step 1: Gather Context

Pull context from three sources to build a complete picture of what Tom needs to know:
**A) Current Session Context**
- Read the current conversation transcript using the `mcp__session_info__read_transcript` tool to understand what Jim has been working on
- Identify which tools, MCP servers, and skills were used during the session
- Note any decisions made, approaches tried, or problems encountered
- Capture any file paths, URLs, project names, or technical details that Tom will need

**B) Obsidian Vault Context**
- Search the Obsidian vault using `mcp__obsidian-mcp-server__obsidian_global_search` for notes related to the task's project or topic
- If the Obsidian MCP tools are disabled, fall back to searching the vault filesystem directly using Grep on the mounted vault directory
- Look for relevant project documentation, meeting notes, or reference materials
- Pull in any SOPs or guides Tom might need

**C) Git History (if applicable)**
- If the task involves code changes, check recent Git commits for relevant context
- Note branch names, recent changes, and deployment status

### Step 2: Check for Relevant Meeting Transcripts

Ask Jim if there's a relevant meeting transcript that would provide useful context for the task:

Use AskUserQuestion to ask:
> "Is there a recent meeting transcript (via Fireflies) that's relevant to this task? For example, a client call, planning session, or discussion where this work was decided on?"

**If Jim says yes:**
1. Use `mcp__40055401-2df4-48ac-b0bf-4e55036b92cd__fireflies_search` to find the transcript by keyword, client name, or date
2. If Jim provides a specific meeting, use `mcp__40055401-2df4-48ac-b0bf-4e55036b92cd__fireflies_get_transcript` to retrieve it
3. Use `mcp__40055401-2df4-48ac-b0bf-4e55036b92cd__fireflies_get_summary` to get the AI summary4. Analyze the transcript for:
   - Key decisions relevant to the delegated task
   - Action items that were assigned
   - Client preferences or requirements mentioned
   - Deadlines or constraints discussed
5. Include a **Meeting Context** section in the task package with:
   - A concise summary of the relevant insights
   - Direct link to the Fireflies transcript
   - Any specific quotes or requirements that Tom needs to be aware of

**If Jim says no or skips:** Proceed without transcript context.

### Step 3: Ask Jim for Task Details

Before creating anything, confirm the specifics with Jim using AskUserQuestion.

**Important: Ask about the Jira project for EACH task separately.** If there are multiple tasks being delegated, they may belong to different projects. Present a question per task, or ask Jim to confirm/override the project for each one.

Questions to ask:

1. **Which Jira project for each task?** Present relevant options based on the task type. If delegating multiple tasks, ask for each one individually — don't assume they all go to the same project. Here's the full project map for reference:

   | Key   | Name                    | Category    |
   |-------|-------------------------|-------------|
   | CPT   | CP Triangle             | Dev         |
   | ED    | Elev8 Distribution      | —           |
   | FEN   | Fenefab                 | —           |
   | GAI   | GHL AI Assistant        | Dev         |
   | GH    | Glenwood Homes          | —           |   | RHIZE | Rhize Media             | Dev         |
   | RMM   | Rhize Marketing         | Marketing   |
   | RSA   | Rhize SuperObsidian App | —           |
   | SGD   | SJ Glass & Door         | —           |
   | SJGS  | SJ Glass Services       | Service Desk|
   | SUM   | Summit Exteriors        | Dev         |
   | VBA   | vba-hoops               | Dev         |
   | WAN   | Wanderhome              | Dev         |
   | WH2   | Wanderhome-V2           | —           |

   When inferring the default project for each task, think about which project the task *actually* belongs to — a task about auditing Rhize's own tools should go under RHIZE or RMM, not a client project, even if the audit was prompted by client work.

2. **Due date?** Ask when Tom should complete this by. Convert any relative date ("by Friday", "next week") to an absolute date.

3. **Priority?** Ask if this is urgent, normal, or low priority.

4. **Any additional context?** Give Jim a chance to add notes, warnings, or preferences not captured in the session.

### Step 4: Format the Task Package

Structure each task as a clear, Tom-friendly document. The format should feel approachable — not like a cold spec, but like a helpful handoff from a colleague.

Use this template for each task:

```markdown
# Task: [Clear, action-oriented title]

## What You're Doing
[2-3 sentences explaining the task in plain language. No jargon without explanation.]
## Why This Matters
[Brief context on why this task is important — business impact, client need, deadline driver. Tom does better work when he understands the bigger picture.]

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
- **Server Name** — what it provides and how Tom will use it

### CLI Commands
[Any terminal commands Tom might need, with full syntax and explanation]
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
- [Any relevant URLs, docs, Obsidian notes, or Jira links]
```

### Step 5: Recommend Additional Tools

Beyond what was used in Jim's session, think about what else would help Tom:

- Scan the available skills list and identify any that are relevant to the delegated task but weren't used in the current session
- Consider MCP servers that could provide useful data or automation
- Think about Tom's skill level — recommend tools that will make the task easier, not harder

Add these to the "Tools & Skills You'll Need" section with a note like: "Jim didn't use this in his session, but it could help you with [specific part of the task]."
### Step 6: Create Jira Issues

Use the Jira MCP to create issues for each task. Use the Atlassian cloud ID `ac62d3a2-66bb-4513-a8e8-b634d3465466`.

**Each task may go to a different Jira project** based on Jim's selections in Step 3.

For each task, create a Jira issue with:
- **Project:** The project key Jim selected **for this specific task** in Step 3
- **Issue type:** "Task" (use the appropriate issue type ID for the selected project)
- **Summary:** The task title from the formatted package
- **Description:** The full task package content (formatted in Jira markdown). If a Fireflies transcript was found in Step 2, include the transcript link in the Reference Links section.
- **Assignee:** Tom Cassidy — account ID `712020:9b48bab7-6363-4355-8b10-19833b0d3dfe`
- **Due date:** The date Jim specified
- **Priority:** As Jim specified
- **Labels:** `["delegated-by-jim"]`

After creating each issue, capture the issue key (e.g., `RHIZE-123`) and the URL for the Slack message.

### Step 7: Share Relevant Obsidian Documents as Slack Canvases

Tom cannot access Jim's local Obsidian vault. If relevant vault documents were found during Step 1 context gathering, share them with Tom as Slack Canvases.

**For each relevant document:**

1. Read the full content from the Obsidian vault (use `Read` tool or `mcp__obsidian-mcp-server__obsidian_read_note`)
2. For `.docx` files, extract content using `pandoc` via Bash
3. Create a Slack Canvas using `mcp__e6f1171c-902d-4f23-920c-131343ab5e80__slack_create_canvas`:
   - **Title:** `[Client/Project Name] — [Document Name]`
   - **Content:** Full document content, reformatted as Canvas-flavored Markdown
4. Share the Canvas in the `#tom-tasks` channel (Channel ID: `C0APDPAF1PD`) by including the Canvas link in the main Slack message (Step 8). **Do NOT send via DM** — keep everything co-located in #tom-tasks with the rest of Tom's task notifications.
5. Add a comment to the relevant Jira issue linking to the Canvas: `"📋 Shared via Slack Canvas: [Canvas URL]"`

**Guidelines:**
- Create **one Canvas per document** (not one giant combined Canvas) for better organization
- Prioritize sharing documents that Tom will actively use (checklists, SOPs, reference docs) over background context docs
- If a document is very long (>5000 chars), summarize non-essential sections but keep actionable content (checklists, steps, tables) in full
- Always include the Canvas link in both the Jira ticket comment AND the Slack message to Tom

**Why this step exists:** Slack Canvases are the best available method for sharing vault content since neither the Slack, Jira, nor Google Drive MCPs support file uploads. Canvases are searchable, bookmarkable, and render with full formatting in Slack.

### Step 8: Send to Slack #tom-tasks (Enriched Multi-Message Format)

Post a structured delegation to the `#tom-tasks` Slack channel (Channel ID: `C0APDPAF1PD`) using a **main message + thread replies** pattern. This keeps the channel scannable while giving Tom full context in-thread.

**Always tag Tom using `<@U0A9KK3BDU0>`** so he gets a notification.

Use the `mcp__e6f1171c-902d-4f23-920c-131343ab5e80__slack_send_message` tool.

The Slack MCP does NOT support Block Kit — use standard Slack mrkdwn only.
#### 8a. Post the Main Channel Message

This is what Tom sees first in the channel. Keep it clean and scannable.

**Priority emoji mapping:**
- Urgent/Highest → :red_circle:
- High → :large_orange_circle:
- Medium/Normal → :large_yellow_circle:
- Low → :white_circle:

Format the main message:

```
:clipboard: *New Tasks for <@U0A9KK3BDU0>*
Delegated by Jim · [date]

*1. [Task 1 Title]*
[priority emoji] [Priority] · :ticket: <[Jira URL]|[ISSUE-KEY]> · :calendar: Due [date] · `[PROJECT-KEY]`
> [1-2 sentence summary of what Tom needs to do]

*2. [Task 2 Title]* (if multiple)
[priority emoji] [Priority] · :ticket: <[Jira URL]|[ISSUE-KEY]> · :calendar: Due [date] · `[PROJECT-KEY]`
> [1-2 sentence summary]

:page_facing_up: *Shared Documents:* (if Slack Canvases were created in Step 7)
<[Canvas URL 1]|[Document Title 1]> · <[Canvas URL 2]|[Document Title 2]>

:thread: *Full instructions, starter prompts, and gotchas are in the thread below — start there!*
```

**IMPORTANT:** Capture the `ts` (timestamp) from the response of this first message. You'll need it for the thread replies.

#### 8b. Post Thread Reply: Per-Task Details

For EACH task, send a thread reply using the `thread_ts` parameter set to the main message's `ts`.
Format each task's thread reply:

```
:pushpin: *Task [N]: [Task Title]*
:ticket: <[Jira URL]|[ISSUE-KEY]> · [priority emoji] [Priority] · :calendar: Due [date]

*Why this matters:*
> [2-3 sentences on business context — why this task is important, what it unblocks, who it impacts]

*Context from [source]:* (if Fireflies transcript or Obsidian note was found)
> _"[Key excerpt — a direct quote or paraphrase from the transcript/note that gives Tom the 'why' or a critical requirement]"_
> :link: <[Fireflies/Obsidian URL]|View full transcript>

*Key steps:*
1. [Step 1 — brief, action-oriented]
2. [Step 2]
3. [Step 3]
(Full step-by-step with explanations is in the Jira ticket)

*Gotchas:*
:warning: [Most important gotcha — the thing most likely to trip Tom up]

*Get started — paste this into Claude:*
```[First starter prompt from the task package]```
```

### Step 9: Confirm with Jim

After everything is created, give Jim a summary:
- List the Jira issues created (with links), noting which project each went to
- Confirm the Slack messages were sent: main message + [N] thread replies
- List any Slack Canvases created from Obsidian vault documents (with links)
- Note whether context snippets from Fireflies transcripts or Obsidian notes were included
- Note any issues or things that need manual follow-up
## Tom's Technical Context

When writing instructions for Tom, keep these in mind:

**What Tom knows well:**
- Advertising platforms and strategy
- Marketing campaigns and content
- Sales processes and outreach
- Business strategy and client relations

**What Tom is learning:**
- Claude Code and Cowork (getting comfortable, but spell out skill invocations)
- Vercel deployments (knows the basics, may need guidance on preview vs. production)
- Sanity CMS (can edit content, still learning schema and GROQ)
- Next.js (understands page structure, not deep into components or API routes)
- DataForSEO APIs (learning the available endpoints and what data they return)
- SEO tooling and analysis workflows

**Writing tone for Tom's instructions:**
- Direct and encouraging — Tom is capable, he just needs the technical bridges
- Always explain the "why" behind technical steps
- Provide exact commands and prompts rather than general directions
- Include screenshots or visual references when describing UI workflows
- Flag anything that could break production with a clear warning

## Jira Configuration Reference

- **Cloud ID:** `ac62d3a2-66bb-4513-a8e8-b634d3465466`
- **Tom's Account ID:** `712020:9b48bab7-6363-4355-8b10-19833b0d3dfe`
- **Tom's Email:** `tom@rhize.media`
- **Atlassian URL:** `https://amesdigitalsolutions.atlassian.net`

## Slack Configuration Reference

- **Target Channel:** `#tom-tasks` (Channel ID: `C0APDPAF1PD`)
- **Tom's Slack User ID:** `U0A9KK3BDU0` (use `<@U0A9KK3BDU0>` to tag him)
- **Slack Workspace:** rhize-media