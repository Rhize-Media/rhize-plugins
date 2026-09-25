---
description: Produce fail-closed, state-bound metadata for explicit regression claims
---
<!-- canonical-skill: rhize-devflow:test-evidence -->

# Test Evidence

Invoke the canonical `rhize-devflow:test-evidence` skill and follow it completely. This command is
the explicit pre-review writer; it binds only authorized package-script declarations but does not
execute them until a trusted sandbox adapter exists. It never mutates the live checkout. Pass
`$ARGUMENTS` unchanged as the requested claim/spec boundary. `/review` remains read-only and treats
the resulting unavailable packet as unsupported.

If the runner is invoked without `--output`, it writes the packet to a default location —
`~/.rhize/test-evidence/packets/<repo-slug>-<head-sha12>.json` — and prints the resolved path;
pass `--output` explicitly to choose a different location.

## Optional local Laya shadow signal

When `RHIZE_LAYA_DEVFLOW_SHADOW=1`, after this command's deterministic `test-evidence` evidence exists, call `scripts/typed_checkpoint.py --stage test-evidence --mode shadow` with the current deterministic evidence file and the bounded signal state in [the adapter contract](../docs/typed-checkpoint.md). Record its private receipt alongside Arm A's verdict. An unavailable model leaves the original verdict intact. A candidate directive does not change this command's obligations or approval gates.
