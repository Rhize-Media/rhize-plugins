# Rhize Tasks Guide for Tom

Rhize Tasks gives you one realistic answer to “what should I work on now?” without pretending that Jira is your calendar or that your personal calendar belongs to Rhize.

It brings approved Rhize and client Jira work into a local plan, fits it around the commitments you choose to expose, creates focus blocks in one dedicated Google Calendar, and creates execution items in one `Rhize Tasks` reminder list. Work for other companies and personal projects can protect time without becoming Rhize tasks.

## Before you start

You need a Mac on macOS 14+, Node.js 22+, a compatible Swift/Xcode toolchain, and access to the Jira, Google, Reminders, and optional Slack accounts you want to connect. The installer does not ask Claude or Codex for credentials. Enter them only into the local dashboard when it opens.

Install from the plugin directory:

```bash
npm run install:local
```

Then use either assistant:

- Claude: “Use `/rhize-tasks:setup` to resume my local setup. Do not ask me for credentials in chat.”
- Codex: “Use `$rhize-tasks-setup` to open or resume the local setup wizard. Keep all secrets in the dashboard and Keychain.”

Both paths use the same installed service and saved preferences.

## Walk through the seven stages

### 1. Confirm the boundary

Read the safety summary. Rhize Tasks may plan only after you have saved preferences and approved the first plan. Scope expansions and the disposable access check require separate approval.

### 2. Identify your accounts

Save your name, timezone, locale, Jira site/account ID, and—if you use the Slack fallback—the exact workspace, `#tom-tasks` channel, and recognized bot/sender IDs.

Enter Jira, Google, and Slack credentials in the dashboard's Keychain forms. The fields clear before submission. If an assistant asks you to paste a token into chat, stop and return to the dashboard.

### 3. Choose Jira work

Discover projects and issue types first. Include every appropriate Rhize and client project you actually work in; exclude software-heavy types or projects that do not belong in your personal plan.

Set project importance and your competencies honestly. Good initial competencies are ads, marketing, GHL, and non-development-heavy Sanity work. Mark categories such as deep development as excluded if you do not want the opportunity engine to recommend them.

Assigned issues come first. Unassigned issues can appear only as suggestions when they meet your approved urgency and competency rules. A suggestion never claims the issue automatically.

### 4. Protect your time without mixing ownership

Create or choose one Google Calendar for Rhize focus blocks. Add every calendar whose busy time should constrain planning:

- Rhize and client calendars.
- Other-company calendars.
- Personal/family calendars.
- Project-specific calendars that contain real commitments.

The focus calendar is automatically included in read scope. Outside calendars remain read-only. Keep outside-title display off if Rhize should know only that you are busy, not why.

Create or select the exact Apple Reminders list named `Rhize Tasks`. Add personal or other-company reminder lists only as awareness lists. Choose how much protected time a due reminder represents and whether its title may appear. Rhize Tasks never writes into those awareness lists.

### 5. Describe a workable day

Add all working intervals and breaks separately for each day. Multiple intervals on the same day are supported—for example 8:30–12:00 and 13:00–17:30. Do not flatten a split day into one large window.

Choose a daily cap, buffer, focus-block length, minimum useful block, meeting buffer, and freeze window. A larger buffer makes the plan less full and more resilient. Splitting helps with long work, but very small blocks tend to create administrative noise.

### 6. Choose the planning policy

The recommended defaults are:

- Bounded replanning: adjust what needs adjusting while preserving active, completed, frozen, and manually moved blocks.
- Prompted reconciliation: show exact Jira changes before they happen.
- Morning, midday, and evening times that match how you already use Calendar and Reminders.

The LaunchAgent wakes periodically, but the service runs only one due phase. If the Mac was asleep, catch-up chooses one appropriate missed phase rather than replaying every missed run.

### 7. Review the dry run

Run the reversible probe only after checking the exact list and calendar names. It creates and removes one disposable item in each location and must verify both are gone.

Then preview the server-derived plan. Read every Calendar, Reminder, and approval-required operation at the displayed revision. Approve only when the scope and schedule look right. This first approval activates routine writes.

## Use it each day

Morning prompts:

- Claude: “Use `/rhize-tasks:today`. Show current, next, capacity, buffer, carryover, and any approvals. Do not approve anything for me.”
- Codex: “Use `$plan-my-day` for today. Keep assigned Jira work first and show me the exact revision before any approval.”

The dashboard is the live command center. It shows:

- A chronological timeline and current/next block.
- Planned, available, and buffered minutes.
- Carryover count and the decision required after repeated misses.
- Exact operations awaiting approval.
- Reconciliation items that need one bounded retry.
- Urgent unassigned opportunities with rationale and impact.
- Estimate warnings, connector freshness, degraded state, and pause state.

The standalone Claude artifact is a useful read-only companion when you want a clean visual snapshot. It cannot fetch, approve, pause, or mutate anything, and it always shows the plan revision that produced it.

## Handle interruptions and manual changes

Move a Rhize focus block in Google Calendar when reality changes. On the next sync, the moved block becomes protected and the task is locally locked; bounded replanning will work around it instead of putting it back at the old time.

If you finish a plugin-created `Rhize Tasks` reminder, Rhize Tasks marks the associated local block/task complete and proposes an approval-required Jira reconciliation comment. Review the actual Jira workflow before deciding whether the issue should be Done, Blocked, Partially complete, or merely awaiting evidence. The first release does not guess project-specific transition IDs.

When a scheduled task remains unfinished, evening planning increments carryover once. One miss is rescheduled. A second asks whether it is blocked, underestimated, or no longer important. Repeated misses require an explicit choice: split, delegate, defer, or renegotiate.

## Review extra Jira work

- Claude: “Use `/rhize-tasks:review-opportunities`. Show only urgent, high-fit work in my approved Jira scope. Do not claim it.”
- Codex: “Use `$review-task-opportunities` and compare each suggestion with today's remaining capacity and assigned work.”

Treat opportunities as offers, not assignments. A high-fit marketing issue can still be the wrong use of the day. Claiming requires the current plan revision and explicit approval; it may not silently displace assigned work.

## Use the Slack fallback correctly

The fallback accepts only recognized structured delegation replies in the configured `#tom-tasks` channel from approved senders. Usually the delegation has a Jira issue. If it does not, Rhize Tasks creates an approval-required provisional item labeled `Needs Jira` and refuses to schedule it. Once a Jira issue contains the exact delegation marker, the local provisional record merges into that canonical task.

Normal conversation, pasted URLs, quoted markers, malformed fields, and messages from other channels/senders are ignored. Slack is not a second general-purpose task database.

## Reconcile safely

- Claude: “Use `/rhize-tasks:reconcile`. Show the exact operation IDs and revision, then wait for my approval.”
- Codex: “Use `$reconcile-rhize-tasks`. Diagnose first, and only submit IDs already displayed in TodayView.”

Reconciliation is for ambiguous writes, revision drift, and interrupted connector calls. Restore the affected connector, refresh TodayView, select exact displayed operation IDs, and approve one bounded attempt. If the item returns to reconciliation, stop; do not keep retrying.

## Change preferences

- Claude: “Use `/rhize-tasks:preferences` to add a Wednesday afternoon interval. Preserve every other saved value.”
- Codex: “Use `$manage-task-preferences` to exclude deep development opportunities. Preview the exact change first.”

Scope expansion needs discovery and approval. Narrowing can be immediate. Material planning changes invalidate the previous activation approval, so review and approve a new plan. Your interval rows, breaks, competency weights, and exclusions round-trip without being flattened.

## Pause and recover

Pause from the dashboard before rotating credentials, changing macOS permissions, reorganizing the focus calendar or reminder list, or investigating unexpected connector behavior. A paused routine performs no sync or write.

Diagnostic prompts:

- Claude: “Use `/rhize-tasks:doctor`. Give me only redacted local health and the narrowest recovery step.”
- Codex: “Use `$rhize-tasks-doctor`. Do not mutate any connector.”

Common states:

- `offline`: the source cannot currently be reached. Only affected writes pause.
- `revoked`: a token or macOS permission is no longer valid. Restore it in the dashboard/Keychain or System Settings.
- `revision_conflict`: the plan changed; refresh and review the new revision.
- `reconciliation_required`: the outcome may be ambiguous; approve only an exact displayed retry.
- Dashboard unavailable: run `doctor --json`, confirm port `43179` is free, and inspect the private logs under Application Support.

Never “fix” the installation by copying the runtime or plist manually. Reinstall so the transactional installer can verify paths and restore the prior service if activation fails.

## Uninstall deliberately

You must choose both what happens to local planning data and what happens to plugin-created Calendar/Reminder items.

```bash
# Keep everything, remove only the runtime/agent.
npm run uninstall:local -- --retain-data --retain-items

# Remove local state but leave Calendar/Reminder items.
npm run uninstall:local -- --delete-data --retain-items

# Keep local state but remove verified plugin-owned items.
npm run uninstall:local -- --retain-data --delete-items

# Remove both local state and verified plugin-owned items.
npm run uninstall:local -- --delete-data --delete-items
```

Deleting items is intentionally fail-closed. The installed runtime derives exact IDs/ownership markers from its own attempted operations, removes only matching records, verifies absence, and returns counts. If it cannot prove cleanup, uninstall stops before deleting local state.

## Tom-Mac acceptance before enabling real writes

Use an approved Jira test issue and disposable Calendar/Reminder containers. Complete all seven stages, approve one plan, create one block/reminder, move the block, complete the reminder, review Jira reconciliation, let one item carry over, pause/restart/catch up, revoke and restore one permission, and test the intended uninstall retention choice. Confirm unrelated records are unchanged.

The automated suite proves those flows with fakes and never touches live accounts. This Mac-level acceptance proves TCC, OAuth, Jira transitions, calendars, lists, and local toolchains in the environment that will actually run the plugin.
