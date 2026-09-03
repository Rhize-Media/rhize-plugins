---
description: Interview-driven setup wizard for delegate-to-teammate — recipients, Jira/Slack lookups, project mapping
---

# /rhize-ops:delegate-setup

Also reachable from `/rhize-core:setup --plugin rhize-ops`. When that orchestrator launches
this wizard it passes `--from-rhize-setup` in `$ARGUMENTS`; ignore that token, and when the
interview ends, stop rather than pointing the user at other setup commands — the orchestrator
continues with its own remaining phases.

Interview-driven setup wizard for the `delegate-to-teammate` skill. Writes
`~/.claude/rhize-ops/delegate.config.json` — in your home directory, outside this plugin's install
path and outside this repo entirely, so it survives plugin updates/reinstalls and never gets
published if you fork or contribute back to this plugin.

Run this once before first using `delegate-to-teammate`, or any time you want to update a
recipient, add another teammate, refresh the project map, or fix a stale ID. This wizard
supports **multiple** recipients — each teammate gets their own key under `recipients`, and
`defaultRecipient` picks which one is used when the delegator doesn't name a person.

## Steps

### 1. Check for an existing config

Look for `$HOME/.claude/rhize-ops/delegate.config.json`.

- If it exists, show a summary (see the safe-summary format in step 9) and ask via
  AskUserQuestion whether the user wants to: **add another teammate** (append a new entry to
  `recipients`, optionally changing `defaultRecipient`), **replace it** (start fresh),
  **update selected fields** (e.g. just the project mapping, just one recipient, or Confluence),
  or **cancel**.
- If the existing file is in the legacy single-`recipient` shape (pre-0.4.0 — a top-level
  `recipient` object instead of `recipients`), treat this run as a **migration** — convert it
  to the current shape (see the SKILL.md "Legacy config compatibility" section for the exact
  field mapping) before applying whatever the user asked for in this run (add/replace/update).
- If it doesn't exist, proceed with a fresh setup for a single recipient (becomes the first entry
  under `recipients`, and `defaultRecipient`).

### 2. Ask who the recipient is

Use AskUserQuestion (free text) for:
- **Name** — the person's full name
- **Email**
- **Role summary** — one sentence on what they own (e.g. "handles marketing, ads, and sales, and
  is growing into technical work")

When adding a teammate to an existing config, also ask for a short lowercase key to file them
under in `recipients` (e.g. `jane-doe`), and whether they should become the new
`defaultRecipient` or stay a named-only recipient.

### 3. Ask about their technical context

Ask (free text, can skip):
- What do they already know well? (a short list)
- What are they still learning? (a short list — instructions should over-explain these areas)
- Any tone preference for how instructions should be written? Default to "direct and
  encouraging — explain the why, give exact commands, flag anything that could break production."

### 4. Look up Jira identifiers (don't make the user hunt for these manually)

`jira.cloudId`, `jira.baseUrl`, and `jira.defaultLabels` are workspace-scoped — resolve them once
per workspace, not per recipient. When adding a teammate to a config where `jira.status` is
already `"ready"`, skip straight to step 2 below for the new recipient only.

If the Atlassian MCP is connected:
1. Call `getAccessibleAtlassianResources` to get the cloud ID and base URL — present the result
   and confirm with the user rather than asking them to paste it blind. (Skip if already set.)
2. Call `lookupJiraAccountId` (or `atlassianUserInfo` if searching by email) to resolve this
   recipient's Jira account ID from their email, and store it on `recipients.<key>.jiraAccountId`.
3. Call `getVisibleJiraProjects` to list every project the user can see, and ask the user to
   group them into `client` / `internal` / `service` categories (per `projectMapping` in the
   schema) with a one-line note each. This can be done a few at a time — the config can be
   extended later by re-running this command. (Skip if `projectMapping` is already populated.)
4. Ask what default labels new issues should get (default: `["delegated"]`). (Skip if already set.)
5. Mark `jira.status` as `"ready"`.

If the Atlassian MCP isn't connected, or any required field couldn't be resolved/confirmed, do
NOT ask the user to paste raw IDs as a substitute for a verified lookup. Instead set
`jira.status` to `"incomplete"`, leave the identifier fields null, and tell the user that tracker
issue creation will be skipped until they connect the Atlassian MCP and re-run this wizard.

### 5. Look up Confluence (where handoff briefs and context pages live)

`confluence` is workspace-scoped and shares the Atlassian site already resolved for Jira. When
adding a teammate to a config where `confluence.status` is already `"ready"`, skip this step.

If the Atlassian MCP is connected:
1. Call `getConfluenceSpaces` (same cloud ID as Jira). Show the current global spaces and ask
   which one should hold delegations. Store `spaceKey` and `spaceId`.
2. Search that space for a page titled "Delegations" (`searchConfluenceUsingCql` with
   `space = "<key>" AND type = page AND title = "Delegations"`). If exactly one exists, show its
   title and ask the user to confirm it; store `parentPageId` and `parentPageTitle`.
3. If none exists, ask via AskUserQuestion whether to create it now. On yes, call
   `createConfluencePage` with the space's homepage as parent, title "Delegations", and a
   one-paragraph body explaining that handoff briefs and context pages for delegated tasks are
   filed here. Store the returned page id. On no, leave `parentPageId` null and mark the block
   `incomplete`.
4. Mark `confluence.status` as `"ready"` once both ids are stored and confirmed.

If the Atlassian MCP isn't connected, or the space or parent page couldn't be resolved, do NOT
ask the user to paste a raw space or page id as a substitute for a verified lookup. Instead set
`confluence.status` to `"incomplete"`, leave the ids null, and tell the user that the skill will
keep the full task package inside the Jira description (today's behavior) until they re-run this
wizard with the MCP connected.

Note: the skill also keeps a small local ledger of exported context pages at
`~/.claude/rhize-ops/delegate.confluence-index.json`. It is created by the skill on first
export, not by this wizard, and it holds only page ids, URLs, titles, and content hashes.

### 6. Look up Slack identifiers

`slack.workspace` (top-level) is workspace-scoped and resolved once. The notification **channel**
is per-recipient (`recipients.<key>.slack.channel`/`channelId`) — every teammate can post to a
different channel.

If the Slack MCP is connected:
1. Ask which channel THIS recipient's delegated tasks should post to, then use
   `slack_search_channels` to resolve its channel ID, and store both on
   `recipients.<key>.slack`. Resolve the workspace name once (skip if already set).
2. Use `slack_search_users` to resolve this recipient's Slack member ID from their name/email,
   and store it on `recipients.<key>.slackUserId`.
3. Mark `slack.status` as `"ready"`.

If the Slack MCP isn't connected, or the channel/user couldn't be resolved, set `slack.status` to
`"incomplete"`, leave the identifier fields null, and tell the user that chat notification will be
skipped until they connect the Slack MCP and re-run this wizard.

### 7. Ask inference rules

Ask: "When a task's project isn't specified, how should I guess? (e.g. 'marketing tasks default
to project X', 'client site work matches by client name', 'internal tooling defaults to project
Y')." Capture as an ordered list, ending with a fallback like "if ambiguous, ask to clarify."

### 8. Write the config

Assemble everything into the shape defined by `rhize-ops/skills/delegate-to-teammate/references/delegate.config.schema.json`
(a real JSON Schema — validate against it before writing) and write it to
`$HOME/.claude/rhize-ops/delegate.config.json`:

- Create `$HOME/.claude/rhize-ops/` first if it doesn't exist (`chmod 700`).
- Write to a temp file in that same directory, then rename it into place (atomic write) rather
  than writing the target file directly.
- Set the file's permissions to `600` (user read/write only) after writing.

Include the `confluence` block assembled in step 5. `confluence` is not required by the
schema — a config written without it is read in memory as `{"status": "incomplete"}`, so there
is no need to force a rewrite of every existing config just to add an empty block.

`recipients` is a map keyed by the short lowercase key from step 2 — adding a teammate means
adding a new key to this map (and, if the user said so, updating `defaultRecipient`), never
overwriting an existing entry unless the user chose "update" in step 1. `defaultRecipient` must
always point at a key that exists in `recipients`.

**Migration note:** if step 1 detected a legacy single-`recipient` config, this is where the
migration actually happens — write the new shape (`recipients: { default: <old recipient> }`,
`defaultRecipient: "default"`, top-level `slack` trimmed to `status`/`workspace`, the old
top-level `slack.channel`/`channelId` moved onto `recipients.default.slack`) instead of the old
shape, even if the user only asked to "add a teammate" or "update the project mapping" — every
write of this file uses the current schema.

### 9. Confirm

Do **not** echo the full file contents back into the conversation by default — some of these
values are internal identifiers you don't need to redisplay every time. Show a **safe summary**
instead:
- Recipient names, with the `defaultRecipient` one marked (e.g. "Jane Doe (default), Tom Cassidy")
- Integration status: Jira `ready`/`incomplete`, Slack `ready`/`incomplete`
- Jira tenant hostname only (not the cloud ID or account ID)
- Slack workspace name, and each recipient's channel name (not the member/channel IDs)
- Confluence `ready`/`incomplete`, and the parent page **title** (not the id)
- Number of mapped projects
- Config file path

If the user explicitly asks to see the full file, read it back to them then — don't do it
unprompted. Then remind them:
- `delegate-to-teammate` will now trigger using this config
- If any integration shows `incomplete`, say plainly what won't work yet (no tracker issue / no
  chat notification) and what connecting that MCP + re-running this command would fix
- Re-run `/rhize-ops:delegate-setup` any time to update it
- The file lives outside this repo — if they fork this plugin publicly, their config stays private

### 10. Establish the evaluation baseline

After recipient and integration setup succeeds, continue with
`/rhize-core:setup --plugin rhize-ops --evaluations`. Offer the user's current delegation
handoff as Arm A, but never create Jira issues or send Slack messages solely to seed a benchmark.
The immediate deterministic suite is free/offline. Any natural capture must exclude recipient,
issue, channel, project, and session identifiers.
