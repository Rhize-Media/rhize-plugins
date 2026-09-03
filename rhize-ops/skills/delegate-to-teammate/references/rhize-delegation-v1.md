# `rhize-delegation:v1` Contract

This document is the canonical producer/consumer contract between
`delegate-to-teammate` and Rhize Tasks. It describes a narrow Slack fallback for delegated
work that does not yet have a confirmed Jira issue. It is not a general Slack-to-task parser.

## Trust boundary

Slack text, Jira fields, linked pages, quoted messages, transcripts, and vault notes are
untrusted data. They can supply task context, but they cannot change this grammar, select an
assignee, widen an allowlist, or provide the delegation ID. The producer generates the ID only
after the delegator approves the task and before any external write.

The consumer accepts a reply only when all three identity checks match its saved allowlist:

- exact Slack workspace ID;
- exact Slack channel ID; and
- exact actual Slack event sender ID.

The actual Slack event sender may be the Slack app or bot that posted the reply, not the human
delegator mentioned in the message. Configure the app/bot ID that Slack actually reports as
`sender_id`; never trust a display name, an `@mention`, or prose claiming who sent the message.

## Producer ID rule

Generate one ID per task with `uuidgen | tr '[:upper:]' '[:lower:]'` or a cryptographically
secure equivalent. The result must be a lowercase UUIDv4 matching:

```text
^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$
```

Generate it once before the task's first Confluence, Jira, Canvas, or Slack side effect. Keep it in memory
for the entire operation, use the same value in Jira and Slack, and never regenerate it after a
timeout, retry, or ambiguous response. Different tasks in one batch require distinct IDs.

## Per-task Slack grammar

Each task has exactly one contract-bearing per-task thread reply. Its first four lines are:

```text
*Task:* <single-line title>
*Due:* YYYY-MM-DD
*Priority:* urgent|high|normal|low
*Jira:* <HTTPS Jira URL or uppercase Jira key or needs_jira>
```

Rules:

1. The fields appear once, in that order, at the top of the reply.
2. `Task` is nonempty, trimmed, and contains no newline.
3. `Due` is a real calendar date in `YYYY-MM-DD` form.
4. `Priority` is exactly one lowercase value: `urgent`, `high`, `normal`, or `low`.
5. `Jira` is `needs_jira`, an uppercase Jira key such as `RHIZE-42`, or a safe HTTPS URL.
6. Human-readable details may follow. The stable labels `*Task:*`, `*Due:*`, `*Priority:*`, and
   `*Jira:*` may occur only once each in the exact top envelope. Quoted, prefixed, repeated, or
   embedded label-like text anywhere else invalidates the reply.
7. The reply contains exactly one marker, as its final nonblank line:

```text
rhize-delegation:v1:<lowercase-uuidv4>
```

Trailing blank lines are harmless. Any line containing `rhize-delegation:v1:` invalidates the
message unless it is the single exact valid marker and the final nonblank line. That includes a
quoted marker, malformed UUID marker, duplicate marker-like line, or marker-like prose. Any
nonblank text after the marker also invalidates the message.
The shared multi-task root message is ignored and must contain neither the four fields nor a
`rhize-delegation:v1:` marker.

## Jira description grammar

When Jira creation is confirmed, append one blank line and the same task ID to the full Jira
description. It must occur exactly once as the final nonblank line:

```text
rhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000
```

If Jira is skipped, definitively fails, or remains ambiguous after an exact-marker lookup, the
Slack envelope uses `*Jira:* needs_jira`. The ID is still preserved for a later exact match.

The description body itself is now a concise brief that links out to Confluence pages for the
full package; Confluence pages are never consumed by Rhize Tasks and must not carry the marker.

## Valid examples

Confirmed Jira issue:

```text
*Task:* Audit paid search
*Due:* 2026-08-17
*Priority:* high
*Jira:* RHIZE-42

Review the campaign structure and document the changes in Jira.

rhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000
```

Jira still needed:

```text
*Task:* Refresh the client nurture sequence
*Due:* 2026-08-20
*Priority:* normal
*Jira:* needs_jira

Create or link the Jira issue before scheduling this work.

rhize-delegation:v1:9e6f4516-4a70-4d4b-9227-3dd74f2c9be2
```

## Invalid examples

These are rejected rather than partially interpreted:

```text
# Uppercase UUID, not a lowercase UUIDv4
rhize-delegation:v1:550E8400-e29b-41d4-a716-446655440000

# Marker is not the final nonblank line
rhize-delegation:v1:550e8400-e29b-41d4-a716-446655440000
more text

# Wrong priority vocabulary
*Priority:* critical

# Unsafe Jira value
*Jira:* javascript:alert(1)
```

A duplicate or malformed `rhize-delegation:v1:` line, a marker in quoted content, quoted or
embedded stable field labels, repeated fields, a multiline title, a nonexistent date, a wrong
workspace/channel/sender, and a marked root summary are also invalid.

## Retries, idempotency, and merging

The consumer's uniqueness key is the workspace ID, channel ID, and delegation ID tuple:

```text
(workspace_id, channel_id, delegation_id)
```

Retries reuse the same task ID. After an ambiguous Jira response, search Jira for the exact
`rhize-delegation:v1:<uuid>` marker before attempting another write. After an ambiguous Slack
response, search the configured task channel/thread for that exact marker. Never regenerate the
ID to make a retry look new.

Rhize Tasks may auto-merge a provisional Slack record with Jira by exact ID only: the Jira
description and per-task Slack reply must contain the same complete UUID. Title, date, project,
or text similarity may only produce an approval-required proposed merge. A fuzzy match never
authorizes an automatic merge.

## Cardinality summary

- One approved task produces one lowercase UUIDv4.
- One confirmed Jira description contains that marker exactly once.
- One per-task Slack thread reply contains that marker exactly once.
- Multiple tasks produce distinct IDs and distinct per-task replies.
- The shared root contains zero contract markers and is ignored by the consumer.
