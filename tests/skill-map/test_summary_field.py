#!/usr/bin/env python3
"""test_summary_field.py — tests for `metadata.rhize.summary` end to end.

Covers the docs-front-door-index plan's "human summaries for skill tables"
change:

  1. scripts/build_skill_map.py carries a skill's `metadata.rhize.summary`
     frontmatter into the generated node as `summary`, verbatim.
  2. A skill with no `summary` frontmatter produces a node with no `summary`
     key at all (never an empty string) — so validate_skill_map.py's
     "is a node's summary present" checks and render_skill_map_docs.py's
     `s.get("summary") or first_sentence(...)` fallback both see "absent",
     not "empty".
  3. scripts/validate_skill_map.py rejects a summary over 160 characters and
     a summary containing a backtick, and accepts a valid one.

Runs scripts/build_skill_map.py against a small hermetic fixture repo in a
temp directory — NOT against this repository's own marketplace.json/skills
(see tests/skill-map/test_render_docs.py's docstring for why: a repo-wide
build here would also make this a write-to-the-real-repo operation, and it
would be slow for a two-node fixture). Copying the build script (and the
sources_md.py module it imports) into the fixture's own `scripts/` directory
is what redirects its REPO_ROOT-derived paths into the fixture tree, same
technique test_render_docs.py and test_local_build.py already use.

Exit code 0 on success, 1 on any failure. Plain script, no pytest — matches
the other tests/skill-map/*.py files.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_skill_map.py"
SOURCES_MD_MODULE = REPO_ROOT / "scripts" / "sources_md.py"
VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "validate_skill_map.py"

VALID_SUMMARY = "Does one plain-language thing, in one sentence, for a first-time reader."
SKILL_WITH_SUMMARY_ID = "skill:fixture-plugin/with-summary"
SKILL_WITHOUT_SUMMARY_ID = "skill:fixture-plugin/without-summary"


def _skill_md(*, name: str, description: str, summary: str | None) -> str:
    rhize_lines = ""
    if summary is not None:
        rhize_lines = f'    summary: "{summary}"\n'
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "metadata:\n"
        "  rhize:\n"
        f"{rhize_lines}"
        "    topics: []\n"
        "---\n\n"
        f"# {name}\n\nBody.\n"
    )


def _build_fixture_repo(root: Path, *, with_summary_value: str) -> None:
    """A minimal repo: one plugin, two skills — one whose `summary`
    frontmatter is `with_summary_value` (the value under test), one with no
    `summary` field at all (the omitted-key contract)."""
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(BUILD_SCRIPT, scripts_dir / BUILD_SCRIPT.name)
    shutil.copy2(SOURCES_MD_MODULE, scripts_dir / SOURCES_MD_MODULE.name)

    (root / "catalog").mkdir()
    (root / "catalog" / "tags.json").write_text("[]", encoding="utf-8")

    marketplace_dir = root / ".claude-plugin"
    marketplace_dir.mkdir()
    marketplace_dir.joinpath("marketplace.json").write_text(
        json.dumps(
            {
                "plugins": [
                    {"name": "fixture-plugin", "source": "./fixture-plugin", "description": "Fixture."}
                ]
            }
        ),
        encoding="utf-8",
    )

    with_summary_dir = root / "fixture-plugin" / "skills" / "with-summary"
    with_summary_dir.mkdir(parents=True)
    with_summary_dir.joinpath("SKILL.md").write_text(
        _skill_md(name="with-summary", description="Always invoke for X.", summary=with_summary_value),
        encoding="utf-8",
    )

    without_summary_dir = root / "fixture-plugin" / "skills" / "without-summary"
    without_summary_dir.mkdir(parents=True)
    without_summary_dir.joinpath("SKILL.md").write_text(
        _skill_md(name="without-summary", description="Always invoke for Y.", summary=None),
        encoding="utf-8",
    )


def run_build(root: Path) -> tuple[subprocess.CompletedProcess, Path]:
    out_path = root / "generated" / "skill-map.static.json"
    indexes_path = root / "generated" / "skill-map.indexes.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / BUILD_SCRIPT.name),
            "--out",
            str(out_path),
            "--indexes-out",
            str(indexes_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return result, out_path


def test_summary_flows_through_builder() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        _build_fixture_repo(root, with_summary_value=VALID_SUMMARY)
        result, out_path = run_build(root)
        if result.returncode != 0:
            raise AssertionError(f"build failed:\n{result.stdout}\n{result.stderr}")

        doc = json.loads(out_path.read_text())
        nodes = {n["id"]: n for n in doc["nodes"]}

        with_summary = nodes[SKILL_WITH_SUMMARY_ID]
        if with_summary.get("summary") != VALID_SUMMARY:
            raise AssertionError(
                f"expected summary {VALID_SUMMARY!r} on {SKILL_WITH_SUMMARY_ID}, "
                f"got {with_summary.get('summary')!r}"
            )

        without_summary = nodes[SKILL_WITHOUT_SUMMARY_ID]
        if "summary" in without_summary:
            raise AssertionError(
                f"{SKILL_WITHOUT_SUMMARY_ID} should have no 'summary' key "
                f"when the frontmatter doesn't set one, got {without_summary.get('summary')!r}"
            )

        validate_mod = load_module(VALIDATE_SCRIPT, "validate_skill_map")
        if not validate_mod.validate_document(doc, "fixture skill-map (valid summary)"):
            raise AssertionError("fixture artifact with a valid summary failed validation")
    print("PASS test_summary_flows_through_builder")


def test_validate_rejects_overlong_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        overlong = "x" * 200
        _build_fixture_repo(root, with_summary_value=overlong)
        result, out_path = run_build(root)
        if result.returncode != 0:
            raise AssertionError(f"build failed:\n{result.stdout}\n{result.stderr}")

        doc = json.loads(out_path.read_text())
        nodes = {n["id"]: n for n in doc["nodes"]}
        if nodes[SKILL_WITH_SUMMARY_ID].get("summary") != overlong:
            raise AssertionError("builder should carry the overlong summary through unmodified")

        validate_mod = load_module(VALIDATE_SCRIPT, "validate_skill_map")
        ok = validate_mod.validate_document(doc, "fixture skill-map (overlong summary)")
        if ok:
            raise AssertionError("validate_document should reject a 200-char summary")
    print("PASS test_validate_rejects_overlong_summary")


def test_validate_rejects_backtick_in_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        _build_fixture_repo(root, with_summary_value="Uses `git status` under the hood.")
        result, out_path = run_build(root)
        if result.returncode != 0:
            raise AssertionError(f"build failed:\n{result.stdout}\n{result.stderr}")

        doc = json.loads(out_path.read_text())
        validate_mod = load_module(VALIDATE_SCRIPT, "validate_skill_map")
        ok = validate_mod.validate_document(doc, "fixture skill-map (backtick summary)")
        if ok:
            raise AssertionError("validate_document should reject a summary containing a backtick")
    print("PASS test_validate_rejects_backtick_in_summary")


def main() -> int:
    try:
        test_summary_flows_through_builder()
        test_validate_rejects_overlong_summary()
        test_validate_rejects_backtick_in_summary()
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
