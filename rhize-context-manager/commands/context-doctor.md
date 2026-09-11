---
description: Run the deterministic context-stack doctor and preserve its evidence-backed result
model: sonnet
---

# /context-doctor

Run the installed, versioned diagnostic directly:

```bash
/usr/bin/python3 "${CLAUDE_PLUGIN_ROOT}/scripts/context_doctor.py" run --repo "${CLAUDE_PROJECT_DIR}" --rtk-bin "${RHIZE_RTK_BIN}"
```

On a host without those variables, resolve this command's installed plugin root and the
requested repository explicitly, then invoke the same script by absolute path. Python
3.9+ is required. Resolve RTK explicitly and pass its absolute executable path (this host:
`/opt/homebrew/bin/rtk`); `HOME` or `--home` supplies the local data root. Do not invent a `claude context-doctor` CLI.

The script owns bounded probes, current-run identity, coverage, all arithmetic, baseline
comparison, atomic persistence, and report rendering. It reads local service/CLI/database/
expiry metadata, never raw observation text or token values. It writes private artifacts
under `~/.claude/context-manager/doctor/v1/`.

Preserve its headline, table, and delta. Optional diagnosis goes beneath **Commentary**.
Never substitute a previous report, mentally compute an age, infer a version from an
error, or replace a failed launch with “no drift.” Unchanged can still mean unhealthy.

Exit codes: `0` = mandatory checks passed; `1` = measured problems or missing mandatory
coverage; `2` = runner/monitor delivery failure. Exit 1 is an actionable diagnostic result;
preserve its artifact. If execution never starts, report `NOT_RUN` and the launch error.
Do not reconstruct the artifact manually.

Probe outcomes are `OK`, `PROBLEM`, and `NOT_RUN`. Required/optional status is declared
before execution. Missing evidence is never zero or healthy. Source-event time is
separate from the time its health file is read; OAuth access expiry is not login expiry.

This pilot measures Headroom endpoint availability, RTK executable availability,
claude-mem persistence/activity, CodeGraph currency, and credential expiry metadata.
Compression benefit, subjective latency, semantic recall quality, optional OpenWolf
health, unsupported adapters, and the host harness audit are not claimed as measured.
Optional omissions remain visible and have review deadlines.

The scheduled pilot uses the reviewed launcher in `claude-routines`, checks pinned source
hashes, and supplies external check-in configuration. Monitor activation and Slack access
are separate operational prerequisites. Ad-hoc calls do not send monitoring events
unless `--monitor-config` is explicitly supplied.

See [doctor operations](../docs/context-doctor.md) for configuration, validation, monitoring,
and the procedural-memory admission boundary. Configuration/repair belongs to a separately
authorized `/context-setup` task; the doctor never repairs, restarts, or upgrades services.
