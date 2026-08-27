---
description: Inspect, evaluate, arm, report, or disarm opt-in local retrieval, mgrep, and Context Compiler experiments
model: sonnet
---

# /context-experiment

Operate the controlled context-tool experiment defined in
`.claude/plans/mgrep-context-compiler-dogfood.md`. The implementation is off by default.
Only real providers count as dogfood evidence. The command supports pinned local grepai,
the pinned mgrep CLI, and an unmodified pinned upstream Context Compiler checkout.
Unit-test doubles never produce receipts or benchmark rows.

Resolve the runner from the installed plugin root:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/context_experiments/runner.py" status
```

Supported operations:

- `status` — print validated local configuration and provider readiness.
- `doctor` — report invalid config, pinned local grepai/index readiness, pinned mgrep readiness,
  and upstream checkout integrity.
- `arm --capability <localRetrieval|mgrep|compiledContext> --repo <absolute-path> --runs 1` — opt in
  to a bounded automatic run. mgrep additionally requires `--network-approved` and
  `--store rhize-dogfood-<repo>`; local retrieval and compiled context require
  `--smoke-approved`. Never infer either approval from a prior session.
- `disarm --capability <localRetrieval|mgrep|compiledContext>` — set `enabled=false` and
  `armedRuns=0`.
- `compile --repo <absolute-path> --target <absolute-python-file> --checkout <path>
  --snapshot <git-snapshot>` — run the real upstream compiler, write a private prompt pack,
  and record Arm A naive-context versus Arm B compiled-context metrics. The checkout must
  be at revision `4edb163911f9a6bc869f35970fa77acb3dd88b8f` with the expected source checksums.
- `pack --provider upstream-python --repo <absolute-path> --target <absolute-python-file>
  [--snapshot <git-snapshot>]`
  — build a deterministic private preview without arming, injection, or a receipt. This is the
  runner behind `/context-pack`; a rejected pack is a successful conservative preview.
- `mgrep-preflight --repo <absolute-path> --store rhize-dogfood-<name>` — write an
  independent, private file/hash inventory and invoke real `mgrep watch --dry-run`. It never
  uploads content and never counts as a completed semantic-search benchmark.
- `report` — aggregate compatible receipt metrics by capability and live Arm A/B variant.

Configuration is stored at
`~/.claude/rhize-context-manager/context-experiments.json`; raw redaction-safe receipts
are stored under `~/.claude/rhize-context-manager/experiments/`. Both locations can be
redirected in tests with `RHIZE_CONTEXT_EXPERIMENT_CONFIG` and
`RHIZE_CONTEXT_EXPERIMENT_DATA_DIR`.

Set `RHIZE_CONTEXT_COMPILER_CHECKOUT` to avoid passing `--checkout` manually. Before `arm`,
show the exact command and ask for confirmation. For mgrep, confirmation must explicitly
cover network indexing of the exact allowlisted repository and name the isolated store.
Do not infer upload approval from installation, login, a dry-run, or approval in a prior
session.

Use `/context-pack` for explicit Phase 3 inspection. Reserve `compile` for an armed paired
experiment; do not treat a preview pack as a completed Arm B run.

`localRetrieval` is currently a measured-but-paused capability. Its first real offline run
failed the relevant-file non-inferiority gate, and grepai 0.35.0 cannot safely scope its
watcher to a main checkout when linked worktrees exist. Do not arm it until a later reviewed
run clears both gates. The adapter and eval harness remain available for that re-evaluation.
