# /rhize-ops:delegate-setup

Interview-driven setup wizard for the `delegate-to-teammate` skill. Writes
`~/.claude/rhize-ops/delegate.config.json` — in your home directory, outside this plugin's install
path and outside this repo entirely, so it survives plugin updates/reinstalls and never gets
published if you fork or contribute back to this plugin.

Run this once before first using `delegate-to-teammate`, or any time you want to update the
recipient, refresh the project map, or fix a stale ID. This wizard supports exactly **one**
recipient — it is not designed for delegating to multiple different people from the same config.

## Steps

### 1. Check for an existing config

Look for `$HOME/.claude/rhize-ops/delegate.config.json`.

- If it exists, show a summary (see the safe-summary format in step 8) and ask via
  AskUserQuestion whether the user wants to: **replace it** (start fresh), **update selected
  fields** (e.g. just the project mapping, or just the recipient), or **cancel**.
- If it doesn't exist, proceed with a fresh setup.

### 2. Ask who the recipient is

Use AskUserQuestion (free text) for:
- **Name** — the person's full name
- **Email**
- **Role summary** — one sentence on what they own (e.g. "handles marketing, ads, and sales, and
  is growing into technical work")

### 3. Ask about their technical context

Ask (free text, can skip):
- What do they already know well? (a short list)
- What are they still learning? (a short list — instructions should over-explain these areas)
- Any tone preference for how instructions should be written? Default to "direct and
  encouraging — explain the why, give exact commands, flag anything that could break production."

### 4. Look up Jira identifiers (don't make the user hunt for these manually)

If the Atlassian MCP is connected:
1. Call `getAccessibleAtlassianResources` to get the cloud ID and base URL — present the result
   and confirm with the user rather than asking them to paste it blind.
2. Call `lookupJiraAccountId` (or `atlassianUserInfo` if searching by email) to resolve the
   recipient's Jira account ID from their email.
3. Call `getVisibleJiraProjects` to list every project the user can see, and ask the user to
   group them into `client` / `internal` / `service` categories (per `projectMapping` in the
   schema) with a one-line note each. This can be done a few at a time — the config can be
   extended later by re-running this command.
4. Ask what default labels new issues should get (default: `["delegated"]`).
5. Mark `jira.status` as `"ready"`.

If the Atlassian MCP isn't connected, or any required field couldn't be resolved/confirmed, do
NOT ask the user to paste raw IDs as a substitute for a verified lookup. Instead set
`jira.status` to `"incomplete"`, leave the identifier fields null, and tell the user that tracker
issue creation will be skipped until they connect the Atlassian MCP and re-run this wizard.

### 5. Look up Slack identifiers

If the Slack MCP is connected:
1. Ask which channel delegated tasks should post to, then use `slack_search_channels` to resolve
   its channel ID and workspace.
2. Use `slack_search_users` to resolve the recipient's Slack member ID from their name/email.
3. Mark `slack.status` as `"ready"`.

If the Slack MCP isn't connected, or the channel/user couldn't be resolved, set `slack.status` to
`"incomplete"`, leave the identifier fields null, and tell the user that chat notification will be
skipped until they connect the Slack MCP and re-run this wizard.

### 6. Ask inference rules

Ask: "When a task's project isn't specified, how should I guess? (e.g. 'marketing tasks default
to project X', 'client site work matches by client name', 'internal tooling defaults to project
Y')." Capture as an ordered list, ending with a fallback like "if ambiguous, ask to clarify."

### 7. Write the config

Assemble everything into the shape defined by `rhize-ops/skills/delegate-to-teammate/references/delegate.config.schema.json`
(a real JSON Schema — validate against it before writing) and write it to
`$HOME/.claude/rhize-ops/delegate.config.json`:

- Create `$HOME/.claude/rhize-ops/` first if it doesn't exist (`chmod 700`).
- Write to a temp file in that same directory, then rename it into place (atomic write) rather
  than writing the target file directly.
- Set the file's permissions to `600` (user read/write only) after writing.

There is exactly one `recipient` object — never structure this as an array or offer to append a
second recipient.

### 8. Confirm

Do **not** echo the full file contents back into the conversation by default — some of these
values are internal identifiers you don't need to redisplay every time. Show a **safe summary**
instead:
- Recipient name
- Integration status: Jira `ready`/`incomplete`, Slack `ready`/`incomplete`
- Jira tenant hostname only (not the cloud ID or account ID)
- Slack workspace/channel name only (not the member/channel ID)
- Number of mapped projects
- Config file path

If the user explicitly asks to see the full file, read it back to them then — don't do it
unprompted. Then remind them:
- `delegate-to-teammate` will now trigger using this config
- If any integration shows `incomplete`, say plainly what won't work yet (no tracker issue / no
  chat notification) and what connecting that MCP + re-running this command would fix
- Re-run `/rhize-ops:delegate-setup` any time to update it
- The file lives outside this repo — if they fork this plugin publicly, their config stays private
