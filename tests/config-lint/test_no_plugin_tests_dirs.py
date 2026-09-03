"""test_no_plugin_tests_dirs.py — plugins don't ship their own tests/ trees.

Repo shape R-A consolidates every plugin-local test tree into the central
`tests/` directory (see `.claude/plans/repo-shape-r-a.md`, delta item 1) so
there is one test convention instead of eight. This test pins that: it walks
every top-level plugin directory (one containing `.claude-plugin/plugin.json`)
and fails if a `tests/`, `test/`, or `__tests__/` directory exists anywhere
under it, except the explicitly allowlisted exceptions below.

Allowlist, each with a reason it is not a violation of the convention:
  - `rhize-ops/skill-monitor/tests` — leaves the marketplace with the
    skill-monitor tool itself when it is extracted in release R-C.
  - `rhize-tasks/tests` — leaves the marketplace with the rhize-tasks
    runtime itself when it is extracted in release R-C.
  - `project-launcher/skills/rhize-visual-plan/obsidian-plugin/test` — this is
    a vendored JS package's own `test/` directory (its own build/test
    tooling expects it there), not a Rhize-authored test tree.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ALLOWLIST = {
    "rhize-ops/skill-monitor/tests",
    "rhize-tasks/tests",
    "project-launcher/skills/rhize-visual-plan/obsidian-plugin/test",
}

TEST_DIR_NAMES = {"tests", "test", "__tests__"}


def _plugin_dirs() -> list[Path]:
    return sorted(
        p.parent
        for p in REPO_ROOT.glob("*/.claude-plugin/plugin.json")
        if p.is_file()
    )


def _find_test_dirs(plugin_dir: Path) -> list[str]:
    found = []
    for path in plugin_dir.rglob("*"):
        if not path.is_dir():
            continue
        if "node_modules" in path.relative_to(REPO_ROOT).parts:
            continue
        if path.name in TEST_DIR_NAMES:
            found.append(str(path.relative_to(REPO_ROOT)))
    return found


def test_at_least_one_plugin_directory_found() -> None:
    assert _plugin_dirs(), f"no plugin directories found under {REPO_ROOT}"


def test_no_unlisted_tests_dirs_under_plugins() -> None:
    violations = []
    for plugin_dir in _plugin_dirs():
        for found in _find_test_dirs(plugin_dir):
            if found not in ALLOWLIST:
                violations.append(found)

    assert not violations, (
        "plugin-local test directories found outside the allowlist "
        f"(move them to tests/<plugin>/ instead): {sorted(violations)}"
    )


def test_allowlist_entries_all_still_exist() -> None:
    stale = [entry for entry in ALLOWLIST if not (REPO_ROOT / entry).is_dir()]
    assert not stale, (
        f"allowlisted test dirs no longer exist, remove from ALLOWLIST: {stale}"
    )
