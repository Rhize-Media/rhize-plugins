# Native plugin update safety

An installed-plugin update can remove an old version's cache while existing Claude or Codex
sessions still reference its hook scripts. A missing Stop script can then produce repeated
synthetic hook prompts. A source merge alone does not change installed caches.

Dev Flow checks installed Rhize package metadata for its own host before and after tools.
A Claude cache change therefore does not invalidate a Codex session, or vice versa.
Source-only test invocations without an installed host path conservatively watch both caches. Each loaded session
keeps its own private baseline. A changed, removed or replaced package marks that session
restart-required. PostToolUse returns `continue: false` once with restart guidance; subsequent
tools remain denied. Other running sessions detect the change on their next hooked tool.
No prompt, command, transcript or credentials are stored. Missing/corrupt identity or state is
unavailable and holds the task rather than claiming the packages are unchanged.
A native SessionStart establishes the post-restart baseline even when resuming the same chat
and Dev Flow version; it archives the previous hold instead of erasing its evidence.

The PreToolUse guard also denies recognizable `claude plugin` and `codex plugin` Rhize install,
update, removal and marketplace refresh commands inside an active session. Read-only list/help,
other marketplaces and ordinary repository edits/merges remain allowed. Static detection handles
direct commands, common command prefixes, chains and bounded shell `-c` wrappers; arbitrary
scripts, aliases, dynamic/encoded code and tools outside native hooks are not contained.

Dev Flow's hook definitions carry a shell existence check, so that check survives removal of
the versioned Python files. Missing pre-tool scripts return an explicit permission denial;
missing prompt/post/Stop scripts return unavailable/restart guidance with `continue: false`.
The Stop guard also ends a held session when drift was first detected before a tool could run,
so an unavailable session is not asked to execute reconciliation that its tool hold prevents.
The surviving update hook checks that all three required Dev Flow scripts still exist, so a
partial update also holds the task even when its package metadata did not change.
They never substitute another version, execute a stub, disable guards or report a passed check.
An existing script's substantive failure still propagates normally. This fallback covers Dev
Flow's hooks; it cannot change older loaded definitions or another plugin's missing hook.

## Automatic update procedure (macOS)

The coordinator installs `scripts/plugin_updates.py install` once and verifies the new global
hooks through each host's normal hook interface. The helper lives at
`~/.local/share/rhize/plugin-updates/plugin_updates.py`, outside every removable plugin cache.
Two user LaunchAgents (`media.rhize.plugin-updates.codex` and `.claude`) check pending work every
15 seconds, including after logout/login or a missed session-end event. No model or subscription
call runs in the background. No user Terminal command is required when closing an app.

For each approved release, the coordinator queues exact versions from a JSON object and the
reviewed marketplace commit, running from the source Git checkout containing that commit:

```bash
python3 scripts/plugin_updates.py queue codex --targets /absolute/reviewed-targets.json --commit REVIEWED_COMMIT
python3 scripts/plugin_updates.py queue claude --targets /absolute/reviewed-targets.json --commit REVIEWED_COMMIT
```

These are coordinator setup commands, not instructions for the user to run after closing apps.
Queueing reads the approved commit objects and freezes each target's full catalog entry and Git
tree hash, alongside existing installations; it does not refresh or update a live host cache. The helper waits for **that host's** native processes to exit and for a 15-second quiet
period. The user can quit Codex and Claude separately. An idle chat or a turn's Stop event does
not release a cache. Codex app-server processes may persist until the app quits. Native CLI and
embedded desktop sessions count; recognized MCP-only Codex workers and unrelated helpers do not.
Unsupported/custom host installations require a new process-detection qualification.

Under an exclusive per-host lock, the worker rechecks owners and installed state, uses only the
supported native marketplace refresh and package update commands, verifies exact approved target
versions, catalog entries and Git trees, then checks installed versions, enabled states and doctor.
An unrelated later catalog release may proceed only when every queued target remains identical to
its approved committed content. A modified target or catalog working tree, including untracked and ignored files, is refused.
Malformed or legacy approval records hold before native refresh. Git reads disable replacement
objects so approval identifies the actual committed directory trees. The original
approval commit and actual resolved commit are retained separately; shallow host catalogs do not
need to retain the original commit because queueing freezes its target identities.
Codex's add command has no disabled-preservation option: a requested disabled Codex package is
rejected before any mutation. No new package, unrelated marketplace or host trust is changed.
A changed target, unknown process state, interrupted update, native failure or failed check
produces a durable `held` receipt; it is never blindly retried or silently declared complete.
The coordinator diagnoses/requeues held work from a healthy host. A held partial mutation
requires explicit `queue --reconcile`, records the previous receipt digest, and keeps guards held
until the repair verifies. Routine closure needs no user terminal; if both hosts or the helper
runtime are broken, recovery requires a separate healthy control surface.

Stable global SessionStart/UserPromptSubmit/PreToolUse hooks record a private session-generation
baseline and deny tools if maintenance is running or that session crossed an update. A partial
failed package mutation holds new sessions too until the coordinator reconciles it. Missing-helper
shell fallbacks preserve that denial even when the recorded Python interpreter is missing
or exits unsuccessfully. Guard/worker Python runs isolated from PYTHONPATH and user site packages;
install with a durable interpreter, never a disposable virtual environment. The worker never edits native approval hashes. Verify normal
hook trust before arming the first queue. Queuing another release preserves existing baselines;
only actual maintenance advances the generation. Session IDs are hashed; prompts, transcripts,
arguments and credentials are not persisted.

**Native startup race:** an external updater cannot atomically lock a native app's startup.
The helper rechecks immediately before mutation; a session that starts in the remaining window
is held by the stable guard and must reopen after completion. This is detection and containment,
not a claim that the native host cannot read a cache during an update. The older missing-hook
hard stop still applies if any host reports a missing script. Never substitute stubs or restore
cache directories to hide that error.

**Transition from the combined guard:** in the current frontend rollout, Claude2.30.1 has no
combined guard, while Codex2.31.1 does. Queue the host-scoped Codex release first, then queue Claude
with `--after codex`. The dependency must complete the same reviewed source commit. Codex closes/updates first and can reopen while Claude remains open. When
Claude later closes it updates independently. If both hosts have legacy combined guards, their
bootstrap requires a naturally occurring zero-owner window on both hosts, or a separately
reviewed migration; do not claim the generic dependency option solves a dependency cycle.

Status is private JSON at `~/.local/share/rhize/plugin-updates/HOST/status.json`, including queued
time, owner count, approved/resolved commit, phase, before/after inventory and error. Doctor and
previous queue receipts are retained alongside it. Completion/hold triggers a local macOS
notification (delivery depends on OS notification settings). `complete` means installation and
static doctor verified; fresh native skill execution and normal hook trust remain separate proof.

If a missing-hook loop is already running, press Stop, restart the host and resume once. Make
one minimal read-only check; stop again if it fails. Do not reply to duplicate synthetic hook
prompts, poll them or attempt repairs inside the broken session. A completed source release or
installation readback does not prove fresh native execution or natural performance recovery.

The guard needs installation and normal hook trust on each host. Local fixture tests prove the
JSON and shell behavior, not native activation. An external updater that bypasses the guard can
still remove other plugins' scripts before a post-tool hook runs. The installed helper owns
automatic maintenance; it sends no cross-chat messages and never terminates user sessions.

Host output contracts: [Codex hooks](https://learn.chatgpt.com/docs/hooks) and
[Claude hooks](https://code.claude.com/docs/en/hooks). PreToolUse uses an explicit denial; it does
not send `continue: false`, which Codex does not support for that event. PostToolUse and Stop use
the supported stop fields instead of a blocking continuation request.
