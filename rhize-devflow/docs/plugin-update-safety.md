# Native plugin update safety

Source editing and merging do not require closing conversations. Installed updates use the
coordinator's exact reviewed-version queue. Open conversations must keep the old version paths
that their loaded hooks reference. An idle conversation has not released those references.

## Safe publication and its limits

Codex packages are prepared by the native CLI in a private isolated home from an archive of the
exact approved Git revision. No live settings, credentials or trust records are copied. The
worker verifies target catalog entries and trees against that same revision, then publishes only
new version directories. Existing directories are never replaced, restored, or deleted. Native
Codex discovery selects the newer version for future loads. Equal versions are no-ops; downgrades,
collisions, links, unexpected manifests and changed staged content hold before publication.
There is no automatic garbage collector: old versions remain even after sessions close.

An isolated native fixture verifies staging, additive discovery of the new version and retention
of the old directory. This is not proof of live hook activation or natural idle-event coverage.

**Claude remains on supported native closed-host updates.** Its registration is a separate shared
file; a helper-only lock cannot make a hand-written registry replacement atomic against native
writers. This helper does not edit that registry or host approval hashes. Claude can close at a
different time from Codex. Neither inactive windows nor a missing Stop event prove safe closure.

## Idle coordination

Stable global SessionStart, UserPromptSubmit, PreToolUse, Stop and SessionEnd hooks record hashed
session IDs, correlated turn IDs and ancestor process identities (PID plus kernel start time).
No prompts, tool arguments, transcripts or credentials are saved. New activity makes the session
active. Only a matching native turn-end event releases it; missing/mismatched turn IDs remain
active. There is no age-based expiry. PID reuse does not inherit an old session's idle state.

Codex idle publication requires the compatible installed guard, every native owner accounted for,
and every recorded conversation under those owners idle for a fresh 15-second quiet interval.
A turn during staging invalidates that interval. Owners already running at helper installation
are bootstrap-held until they exit; this prevents an unobserved old chat sharing a process from
being mistaken for idle. Legacy helpers, unknown owners, uncorrelated native events and older
guards retain the closed-host fallback. Do not claim every host build supports idle publication.

A short admission lock serializes hook admission against publication. The pre-tool hook waits
at most two seconds for the publication barrier, then returns a visible temporary denial; it
never waits indefinitely for its own conversation to stop. Verification in progress does not
permanently latch restart for an immutable update. A crash or failed partial publication records
`held` and requires original-receipt reconciliation; never blindly replay it.

The loaded plugin guard compares its original package metadata paths, accepting additions while
holding changed/removed/replaced baseline metadata. Corrupt baseline state holds. Legacy baseline
receipts retain their conservative comparison until a real native reload. Recognizable direct
Rhize install/update/removal commands remain denied inside active sessions; use the coordinator
queue. Missing-file shell fallbacks and the missing-hook hard stop remain enabled.

## Installation and queueing

Install `scripts/plugin_updates.py install` with a durable Python interpreter, then verify the
new global hooks through each host's normal trust interface. The stable helper and cache module
live outside removable caches at `~/.local/share/rhize/plugin-updates/`. Two existing per-host
LaunchAgents check queues every 15 seconds. Installation records bootstrap owners; it does not
establish native event coverage or trust. Do not reinstall the helper merely to release a hold.

Queue reviewed target versions from the source checkout containing the reviewed commit:

```bash
python3 scripts/plugin_updates.py queue codex --targets /absolute/reviewed-targets.json --commit REVIEWED_COMMIT
python3 scripts/plugin_updates.py queue claude --targets /absolute/reviewed-targets.json --commit REVIEWED_COMMIT
```

Queueing freezes exact target trees and catalog entries, not just version labels. An unrelated
later release is accepted only if every queued target is unchanged. Git reads disable replacement
objects; modified/untracked/ignored target source holds. Disabled Codex packages are rejected
before mutation because its native add command cannot preserve that state. No unselected package,
marketplace, host permission or native CLI version is changed.

`--after HOST` requires that host's completed receipt for the same reviewed commit. A held partial
mutation needs explicit `queue --reconcile`; prior receipts remain in history and the hold remains
until repair verifies. Ambiguous durable publication is not permission to overwrite a collision.
Status, staged inputs and doctor evidence remain under `~/.local/share/rhize/plugin-updates/HOST/`.
`complete` means inventory and static doctor passed; native discovery, normal hook trust and
fresh-session execution are separate proof. Local notifications depend on macOS settings.

An external updater or native auto-update outside this helper is not coordinated by its locks
and can still remove cache files. The guard detects that damage; it does not mask it by restoring
stubs or substituting another version. Native startup cannot be atomically locked by this helper;
unknown startup is contained by the stable hooks, with legacy updates requiring reopen. If a
missing-hook loop already exists, stop tools and restart the affected host once; make one minimal
read-only check on resume. Never retry synthetic hook failures or disable required guards.
