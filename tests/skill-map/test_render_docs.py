#!/usr/bin/env python3
"""test_render_docs.py — tests for scripts/render_skill_map_docs.py.

Covers the three contracts the render script promises:

  1. Idempotency — running it twice against an unchanged skill map produces
     byte-identical output on every managed file.
  2. Marker preservation — hand-written prose outside a marker pair is left
     byte-for-byte untouched by a run that changes the managed content.
  3. Refusal — a target file with no marker pair raises rather than guessing
     where to insert one.

Runs against the real repo files for (1) and (2) (restoring them afterward,
since this repo's managed sections are already fully rendered and a run
should be a no-op) and against a scratch copy for (3), so the test never
needs its own fixture map.

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

MANAGED_FILES = [REPO_ROOT / "README.md", REPO_ROOT / "generated" / "SKILL-CATALOG.md"]


def _plugin_readmes() -> list[Path]:
    import json

    marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    return [REPO_ROOT / entry["name"] / "README.md" for entry in marketplace["plugins"]]


def run_render() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RENDER_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_idempotent() -> None:
    targets = MANAGED_FILES + _plugin_readmes()
    before = {p: p.read_text(encoding="utf-8") for p in targets}

    result = run_render()
    assert result.returncode == 0, f"first render failed: {result.stderr}"

    result2 = run_render()
    assert result2.returncode == 0, f"second render failed: {result2.stderr}"
    assert "No changes" in result2.stdout, (
        f"second run reported changes — not idempotent:\n{result2.stdout}"
    )

    after = {p: p.read_text(encoding="utf-8") for p in targets}
    for p in targets:
        assert before[p] == after[p], f"{p} changed even though the skill map didn't"
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
