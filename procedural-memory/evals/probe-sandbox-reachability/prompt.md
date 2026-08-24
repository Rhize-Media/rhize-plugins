---
name: probe-sandbox-reachability
tags: [probe, infra]
runs: 1
max_turns: 3
timeout_seconds: 60
allowed_tools: [Bash]
---

Run this exact bash command and report the FULL raw output verbatim, including any error
messages — do not summarize or interpret it:

    echo "--- exec outside HOME ---"; /usr/bin/true; echo "exec exit: $?"
    echo "--- absolute path outside HOME, not on PATH by default ---"; /usr/bin/env RHIZE_PROBE=1 /usr/bin/id; echo "id exit: $?"
    echo "--- localhost:5432 (Postgres) reachability ---"; (exec 3<>/dev/tcp/127.0.0.1/5432 && echo "TCP CONNECT: reachable" || echo "TCP CONNECT: unreachable") 2>&1; echo "tcp probe exit: $?"

Then run:

    "${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh" doctor 2>&1; echo "launcher exit: $?"

Report every line of output and every exit code exactly as printed.
