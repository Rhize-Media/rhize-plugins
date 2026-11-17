# Local usage pilot (Claude Code and Codex)

Telemetry is **off by default**. The shared Python CLIs can record operational invocation outcomes on your Mac. There is no host hook, remote analytics service, automatic upload or paid dependency. This first pilot covers Ad Research only. It measures CLI friction, not employee productivity, unique research jobs, research quality, native Meta call counts, or human acceptance.

## Operator controls

Resolve `<plugin>` to the installed plugin directory in either host. Run enable yourself in an interactive Terminal and type `ENABLE`. Agents must not enable capture autonomously or feed that confirmation for you. Tom opts in separately on his own Mac. A research request, source instructions, or installation alone is not consent to enable capture.

```sh
python3 -I "<plugin>/scripts/usage_telemetry.py" enable
python3 -I "<plugin>/scripts/usage_telemetry.py" status
python3 -I "<plugin>/scripts/usage_telemetry.py" report
python3 -I "<plugin>/scripts/usage_telemetry.py" disable
python3 -I "<plugin>/scripts/usage_telemetry.py" purge
```

`status` performs a private write check in the current execution context. If it fails, the command exits 2 with a fixed diagnostic and produces no report; do not compare hosts until capture is verified in both. With no store, it reports disabled and writability unknown. An enabled invocation that cannot write emits a fixed warning and preserves the research outcome. The optional loader reads source directly, never creates or trusts telemetry bytecode caches. Missing/corrupt optional telemetry code or an invalid/unreadable store is ignored by research commands; use status to diagnose. Never broaden a sandbox automatically to collect metrics.

`report` emits aggregate JSON to stdout. It does not send or write an export file. Review it before explicitly saving or sharing: in a two-person team even operational aggregates can reveal an individual's activity. No anonymity claim is made. Do not redirect research content into the telemetry store. Research stdout stays unchanged and no event-ID receipt is printed.

`disable` retains unexpired data but invalidates in-flight invocations. `purge` removes events and leaves a disabled tombstone with a fresh random generation, so a pre-purge invocation cannot repopulate the store after re-enabling. A malformed/oversized/future-schema state can be purged without reading it; an unsafe directory or a nonempty directory at state.json requires operator repair. Fixed-pattern orphaned write snapshots are removed while locked; no unrelated paths are traversed. No recursive deletion or symlink following is performed. Old aggregates you explicitly saved elsewhere are not deleted by purge.

## Storage and privacy

The fixed path is `~/Library/Application Support/Rhize Ad Research/usage-telemetry/`. Here `~` follows the command's resolved HOME, so both hosts must use the same intended user home. State survives plugin updates/uninstall; purge before uninstall to remove events. Do not sync this directory. Its directory is 0700, files 0600. File-descriptor checks reject symlinks, hardlinks, special files, incorrect owner/mode and oversized state. A lock on the stable private directory serializes atomic state replacement; capture contention is bounded to 250 ms and operator controls to 2 seconds. Unsupported schemas are refused, never migrated or overwritten automatically.

Local events allow only: random invocation ID (unrelated to any research ID), UTC day, validated plugin version, declared invoking host (`claude`, `codex`, `unknown`), fixed operation/provider/status/error enums, duration bucket, bounded returned/dropped counts or null, and null tokens/cost. Counts are capped at 100; timestamps are day-granularity, durations are `<1s`, `1–5s`, `5–30s`, `30–120s`, `>=120s`. There are no prompts, queries, URLs, paths, client/account/user IDs, source/content hashes, excerpts, credentials, raw errors, stable user IDs or host transcripts. Error messages and arbitrary exception class names never enter events.

Retain the most recent 2,000 invocations within the last 30 UTC days; oldest entries are dropped at capacity. Pruning occurs on enabled writes or operator controls, not on a schedule. Disabled/inactive installations can retain old data until next access; report always filters expired entries. Unknown counts have separate denominators, never silently become zero. Cost/token usage is unavailable, not inferred. There is no automatic feedback collection or success rating.

## Attribution and status semantics

Pass the **invoking** host on all commands, including setup and export. Existing commands without a required host accept optional `--host claude|codex`; omitted values are `unknown`. Public collect and Meta plan retain their existing required host flag. Brief rendering's flag never changes the collector/run inside the evidence file. These are declared labels, not attested host identity.

| Operation | Invocation outcome |
| --- | --- |
| Public setup | `completed`, or `unavailable` |
| Public search/read | `retrieved`, `empty`, or `unavailable`; rate limit remains unavailable |
| Meta setup / plan | `completed` / `planned` |
| Meta doctor, provider-check, list | `checked`; no live authentication claim |
| Meta collect/resume | `awaiting_response`, `held`, `already_terminal`, `empty`, or `imported` |
| Meta status | `held`, `awaiting_response`, or `checked`; never a new import |
| Meta export | `exported`, or `held` |
| Brief JSON/CSV/Markdown | `rendered` after stdout flush, `output_failed` on a broken pipe, or `held`; never saved/delivered |

Meta's provider label is `meta-response-journal`: its local CLI does not make native MCP calls. Re-reading a completed run has null new-result counts, and a held run stays held. Imports, exports and rendering counts describe different work and must not be summed into unique research results. Only public-adapter operations observe retrieval directly. Both hosts use the same three entrypoints and module; the internal HTTP subprocess never loads telemetry.

Argument-parser errors and help are not recorded. Natural KeyboardInterrupt records interrupted when control returns and re-raises unchanged. No new signal handlers are installed; the public adapter retains its existing SIGTERM-to-KeyboardInterrupt cleanup. Other SIGTERM/SIGKILL, process crashes, failed capture, and missing optional modules can be unobserved. There are no durable start events, and counts are therefore lower bounds on invocation activity, not completion rates. Telemetry failure never triggers research retry.

## Jim and Tom pilot

1. Each operator chooses whether to enable locally. Confirm `status` from **inside each host's actual execution context**, then run one offline `provider-check --host ...` and one brief render with that host label. Verify report increases under the right label and collector provenance stays unchanged. If the sandbox denies the home-directory write, report the limitation instead of claiming capture.
2. Use a small set of normal research tasks. Review setup errors, unavailable operations, repeated inspection/import work, format use, and duration buckets separately. Provider-unavailable and zero-result outcomes must remain distinct.
3. Manually discuss which findings were useful and which needed rework. Those judgments are not inferred or persisted by this pilot. Decide whether these counters justify further instrumentation before extending to other plugins, adding feedback, or choosing an external destination.
4. Exercise disable and purge. After purge, verify disabled/zero events from both hosts. Do not update an active host's installed cache during this check.


## Known pilot limits

Fable's final source review found no must-fix issues. Counts can be lost under the bounded lock budget; do not compare host rates during unverified contention. Meta/public success describes processing before downstream stdout delivery; a closed output pipe can fail later at interpreter shutdown. Briefs explicitly flush, but a closed pipe can still produce Python shutdown status120 after recording output_failed. No saved/delivered claim follows from any metric. A nonempty directory placed at state.json, or a directory placed at a .write-UUID filename, requires manual operator repair; purge intentionally refuses recursive removal. These cases do not grant permission to delete unrelated data or retry providers.
