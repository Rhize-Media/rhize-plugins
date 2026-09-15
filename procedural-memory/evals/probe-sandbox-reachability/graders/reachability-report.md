---
name: reachability-report
type: llm
criteria: >-
  The transcript must show the agent actually running the probe commands (exec outside HOME,
  absolute-path exec of /usr/bin/id, an `nc -z` TCP connect attempt to 127.0.0.1:5432, printing
  the scaffold-recorded plugin root, the launcher's `doctor` subcommand, the Postgres Unix-socket
  probe, and the shell / CLAUDE_PLUGIN_ROOT / PROCEDURAL_MEMORY_PLUGIN_ROOT echoes with the
  launcher-via-export exit code) and reporting their real output and exit codes verbatim, not a
  summary. This is a reachability PROBE, not a pass/fail correctness test — score 1 if the agent
  ran the commands and reported real output either way (whether they succeeded or failed is the
  finding, not the grade). Score 0 only if the agent fabricated output, refused to run the
  commands, edited the commands, or summarized instead of reporting verbatim.
focus: trace
---

This case answers the open question in this plugin's README ("Eval coverage"): can Bash inside
an eval case reach an absolute path outside the sandbox's fresh HOME, does "network is not
blocked" extend to localhost Postgres, and can the real launcher be reached at all. The grader
only checks that the measurement actually happened — read the raw transcript output yourself
for the answer and keep `evals/README.md`'s "Probe result" section current.

Why the commands look the way they do (lessons from the first real run, 2026-09-15): the tool
shell is zsh, so bash's `/dev/tcp` pseudo-device silently tests nothing — `nc -z` is used
instead; and `${CLAUDE_PLUGIN_ROOT}` is unset in the Bash environment, so the launcher path
comes from the scaffold-recorded plugin root rather than the variable. The second Bash call
records both facts explicitly so a future harness change shows up as a diff in the transcript.

The second call also reports `PROCEDURAL_MEMORY_PLUGIN_ROOT`, which this plugin's SessionStart
hook exports through `CLAUDE_ENV_FILE`; with the plugin loaded it should be the plugin path and the
launcher must run through it, without the plugin it should be `unset`. The Unix-socket probe exists
because TCP to 127.0.0.1:5432 was measured unreachable (2026-09-15) — the eval sandbox's network is
the `WebFetch(domain:…)` grants only, through its proxy — and the socket transport needed its own
measurement before the README could say "unreachable" for Postgres as a whole.
