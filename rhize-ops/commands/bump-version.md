# /rhize-ops:bump-version

Coordinated semver bump for the `rhize-plugins` marketplace. Wraps `scripts/bump_version.py`,
which auto-discovers plugins (any `*/.claude-plugin/plugin.json`) and keeps each plugin's version,
the marketplace manifest's per-plugin entry + top-level version, and the CHANGELOG in sync. It
**never pushes**.

## Usage

- **Auto (recommended):** detect what changed since the last release and infer levels from
  conventional-commit subjects (`feat!`→major, `feat`→minor, else patch):
  - Dry-run: `python3 scripts/bump_version.py --auto`
  - Apply: `python3 scripts/bump_version.py --auto --yes`
- **Explicit:** `python3 scripts/bump_version.py --plugin <name> --level <major|minor|patch>`
- **Validate (no writes):** `python3 scripts/bump_version.py --check`

## Steps

1. From the repo root, run `python3 scripts/bump_version.py --auto` and show the proposed plan.
2. On the user's confirmation, run `--auto --yes`, then show `git diff` for review.
3. Remind the user to commit, and to push only when they say so. The opt-in pre-push hook
   (`.githooks/pre-push`, enabled via `git config core.hooksPath .githooks`) blocks pushes with
   stale versions; CI runs the same `--check` on PRs.

The marketplace top-level version bumps by the **max** level across the changed plugins.
