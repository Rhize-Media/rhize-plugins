---
description: Re-run a promoted artifact's sandboxed smoke test (or every function under a CLI namespace) and refresh its health state
argument-hint: <artifact-name> | --cli <cli-name> [--offline] [--fixture <path>]
allowed-tools: Bash
---

Re-verify a procedural-memory registry artifact: $ARGUMENTS

Run:

    ${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh verify $ARGUMENTS

This is the only command that ever sets `health=ok` or `health=degraded` with a real
`last_verified` date — promotion alone never does. Use `--offline` to recover an artifact that
self-quarantined to `degraded` during an offline run, without opening a Postgres connection.

Report the pass/fail and every assertion result verbatim, including which specific assertion
(`exit_code`, `stdout_matches`, `stdout_captures`, `no_writes_outside`, `idempotent`) failed if
any did — a passing exit code with a failing assertion is still `degraded`, never `ok`, and the
user needs to know which check caught it.
