---
description: Build and inspect a private Context Compiler pack without injecting it into a task
model: sonnet
---

# /context-pack

Build a source-bound preview with the checksum-verified, unmodified upstream Context Compiler.
This command never arms an experiment, injects context, or records a completed dogfood receipt.
It is the Phase 3 inspection path for deciding whether a target is safe enough to advance to a
later provider-neutral experiment.

Resolve the runner from the installed plugin root and run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/context_experiments/runner.py" pack \
  --provider upstream-python \
  --repo /absolute/path/to/repository \
  --target /absolute/path/to/repository/module.py
```

The runner binds the pack to the current Git snapshot, including a digest when the worktree is
dirty. Pass `--snapshot <expected-snapshot>` when the caller already has an expected value and
wants the command to fail if the repository changed. `--checkout`, `--max-hops`, and
`--max-tokens` override the pinned defaults.

Inspect the printed verdict before opening the private prompt file:

- `acceptedForInjection=false` is a successful conservative preview, not permission to inject.
- Any dynamic-dispatch, decorator-registration, callback-registration, unsupported-syntax,
  token-budget, coverage, or collision rejection requires baseline retrieval or a wider context
  path.
- `manifestPath` and `promptPath` are mode `0600` files under
  `~/.claude/rhize-context-manager/experiments/packs/` by default.
- Repeating the same source-bound request reuses the identical immutable pack. A same-ID content
  mismatch fails closed.

Only `/context-experiment compile` may produce a paired Arm A/Arm B receipt, and it still requires
an explicitly armed compiled-context run. This preview must not be counted as proof of improved
task correctness.
