# Native plugin update safety

An installed-plugin update can remove an old version's cache while existing Claude or Codex
sessions still reference its hook scripts. A missing Stop script can then produce repeated
synthetic hook prompts. A source merge alone does not change installed caches.

Dev Flow checks installed Rhize package metadata before and after tools. Each loaded session
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

## Update procedure

1. Save durable checkpoints for every active chat and let ongoing work reach a safe stopping point.
2. Close **all Claude and Codex host sessions** that use the plugins. A warning to an agent or an
   idle chat does not unload its hooks. Do not hot-update a session to install this safeguard.
3. From a separate ordinary terminal, refresh the existing named Rhize marketplace and update
   the intended packages using each host's supported CLI. For Codex, use
   `codex plugin marketplace upgrade rhize-plugins` followed by
   `codex plugin add PLUGIN@rhize-plugins`; Claude uses
   `claude plugin marketplace update rhize-plugins` followed by
   `claude plugin update PLUGIN@rhize-plugins`. Do not remove caches manually.
4. Restart hosts, review changed hook trust through the normal host interface, verify versions
   and enabled status, then make a fresh native checkpoint and run `devflow.py doctor`.
   Never hand-edit approval hashes or redirect a stale path.

If a missing-hook loop is already running, press Stop, restart the host and resume once. Make
one minimal read-only check; stop again if it fails. Do not reply to duplicate synthetic hook
prompts, poll them or attempt repairs inside the broken session. A completed source release or
installation readback does not prove fresh native execution or natural performance recovery.

The guard needs installation and normal hook trust on each host. Local fixture tests prove the
JSON and shell behavior, not native activation. An external updater that bypasses the guard can
still remove other plugins' scripts before a post-tool hook runs; closed-host maintenance is the
prevention boundary for all packages and sessions. No background watcher or cross-chat messaging
is added.

Host output contracts: [Codex hooks](https://learn.chatgpt.com/docs/hooks) and
[Claude hooks](https://code.claude.com/docs/en/hooks). PreToolUse uses an explicit denial; it does
not send `continue: false`, which Codex does not support for that event. PostToolUse and Stop use
the supported stop fields instead of a blocking continuation request.
