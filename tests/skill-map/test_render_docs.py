#!/usr/bin/env python3
"""test_render_docs.py — tests for scripts/render_skill_map_docs.py.

Covers the three contracts the render script promises:

  1. Idempotency — running it twice against an unchanged skill map produces
     byte-identical output on every managed file.
  2. Marker preservation — hand-written prose outside a marker pair is left
     byte-for-byte untouched by a run that changes the managed content.
  3. Refusal — a target file with no marker pair raises rather than guessing
     where to insert one.

Every test is hermetic: nothing here writes inside the repository. (1) copies
the renderer's real input set into a temp tree and runs there, so it still
detects a stale committed catalog — the copy starts as the committed state,
so a first render that changes anything fails the comparison — without
mutating the working tree. (2) and (3) build their own scratch files, so the
test never needs its own fixture map.

Before 2026-09-02 this file ran the renderer against the real repo with
`cwd=REPO_ROOT` and, despite a docstring claiming otherwise, never restored
anything. That made `pytest tests/` a write operation: a verification run
silently repaired a stale root README instead of reporting it. Keep this
hermetic — `test_idempotent` now asserts the real files are untouched.

Exit code 0 on success, 1 on any failure. Plain script, no pytest — matches
the other tests/skill-map/*.py files.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_SCRIPT = REPO_ROOT / "scripts" / "render_skill_map_docs.py"
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"

MANAGED_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "generated" / "SKILL-CATALOG.md",
    REPO_ROOT / "docs" / "README.md",
]


def _plugin_readmes() -> list[Path]:
    import json

    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    return [REPO_ROOT / entry["name"] / "README.md" for entry in marketplace["plugins"]]


def run_render(root: Path) -> subprocess.CompletedProcess:
    """Run the renderer against `root`.

    The script derives its own repo root from `__file__`, so invoking the copy
    inside `root` is what redirects every read and write into that tree.
    """
    return subprocess.run(
        [sys.executable, str(root / "scripts" / RENDER_SCRIPT.name)],
        cwd=root,
        capture_output=True,
        text=True,
    )


# Exactly what scripts/render_skill_map_docs.py reads or writes: the map it
# renders from, the marketplace list that names the plugin READMEs, and the
# three managed-file groups. Copying this set (rather than the whole repo)
# keeps the fixture cheap and makes an unnoticed new input fail loudly here.
def _materialize_inputs(root: Path) -> list[Path]:
    """Copy the renderer and its inputs into `root`. Returns the managed files."""
    for rel in (
        Path("scripts") / RENDER_SCRIPT.name,
        Path("generated") / "skill-map.static.json",
        Path("generated") / "SKILL-CATALOG.md",
        Path(".claude-plugin") / "marketplace.json",
        Path("README.md"),
        Path("docs") / "README.md",
    ):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, dest)

    for readme in _plugin_readmes():
        dest = root / readme.relative_to(REPO_ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(readme, dest)

    return [root / p.relative_to(REPO_ROOT) for p in MANAGED_FILES + _plugin_readmes()]


def test_idempotent() -> None:
    real_targets = MANAGED_FILES + _plugin_readmes()
    real_before = {p: p.read_text(encoding="utf-8") for p in real_targets}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        targets = _materialize_inputs(root)
        before = {p: p.read_text(encoding="utf-8") for p in targets}

        result = run_render(root)
        assert result.returncode == 0, f"first render failed: {result.stderr}"

        result2 = run_render(root)
        assert result2.returncode == 0, f"second render failed: {result2.stderr}"
        assert "No changes" in result2.stdout, (
            f"second run reported changes — not idempotent:\n{result2.stdout}"
        )

        # The copy started as the committed state, so a first render that
        # rewrote anything means the committed managed sections are stale.
        after = {p: p.read_text(encoding="utf-8") for p in targets}
        for p in targets:
            rel = p.relative_to(root)
            assert before[p] == after[p], (
                f"{rel} changed even though the skill map didn't — the committed "
                f"managed section is stale; run scripts/render_skill_map_docs.py "
                f"(and commit the result) after any version bump"
            )

    # Hermeticity is the contract this file broke before 2026-09-02; assert it
    # rather than claiming it in a docstring.
    for p in real_targets:
        assert real_before[p] == p.read_text(encoding="utf-8"), (
            f"{p.relative_to(REPO_ROOT)} was modified — this test must never "
            f"write inside the repository"
        )
    print("PASS: test_idempotent")


def test_marker_preservation() -> None:
    """Prose outside the marker pair must be untouched by a run that DOES change content."""
    module = load_module(RENDER_SCRIPT, "render_skill_map_docs")

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "README.md"
        target.write_text(
            "# Hand-written title\n\n"
            "Some hand-written prose before the marker.\n\n"
            f"{module.BEGIN}\nold managed content\n{module.END}\n\n"
            "Some hand-written prose after the marker.\n",
            encoding="utf-8",
        )
        changed = module.apply_markers(target, "new managed content")
        assert changed is True

        text = target.read_text(encoding="utf-8")
        assert "# Hand-written title" in text
        assert "Some hand-written prose before the marker." in text
        assert "Some hand-written prose after the marker." in text
        assert "new managed content" in text
        assert "old managed content" not in text

        # Second call with the same content must be a no-op (idempotency at
        # the marker-replacement level, independent of the full pipeline).
        changed_again = module.apply_markers(target, "new managed content")
        assert changed_again is False
    print("PASS: test_marker_preservation")


def test_refuses_without_markers() -> None:
    module = load_module(RENDER_SCRIPT, "render_skill_map_docs")

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "README.md"
        target.write_text("# No markers here\n\nJust prose.\n", encoding="utf-8")
        try:
            module.apply_markers(target, "content")
        except module.RenderError:
            pass
        else:
            raise AssertionError("apply_markers should have raised RenderError")
    print("PASS: test_refuses_without_markers")


def main() -> int:
    try:
        test_marker_preservation()
        test_refuses_without_markers()
        test_idempotent()
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
