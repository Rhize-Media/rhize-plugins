#!/usr/bin/env python3
"""setup_artifacts.py — render the union of every setup/manifest.json's `artifacts` array into
the managed section of rhize-ops/docs/setup-artifacts.md (hybrid-setup-wizard.md R2 §5).

  --markdown              render in place (the marker pair must already exist in the file)
  --check                 rebuild into a temp copy and diff against the committed file; exits 1
                           on drift. Registered in scripts/bump_version.py REPOSITORY_CONTRACTS.
  --repo-root <path>      override the repo root (tests only; defaults to this file's own repo)

Same hermetic pattern as scripts/validate_skill_map.py --check-stale and
tests/skill-map/test_render_docs.py: --check never writes inside the real repo.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BEGIN = "<!-- SETUP-ARTIFACTS:BEGIN -->"
END = "<!-- SETUP-ARTIFACTS:END -->"
DOC_RELATIVE = Path("rhize-ops") / "docs" / "setup-artifacts.md"
COLUMNS = ["artifact", "producer", "path", "how to view", "lifetime", "confidentiality", "source", "tracked"]


class RenderError(Exception):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def escape_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def collect_rows(repo_root: Path) -> list[dict[str, str]]:
    marketplace = load_json(repo_root / ".claude-plugin" / "marketplace.json")
    rows: list[dict[str, str]] = []
    for entry in marketplace["plugins"]:
        plugin = entry["name"]
        manifest_path = repo_root / plugin / "setup" / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = load_json(manifest_path)
        for artifact in manifest.get("artifacts") or []:
            rows.append({
                "artifact": artifact["id"],
                "producer": plugin,
                "path": artifact["path"],
                "how to view": artifact["viewer"],
                "lifetime": artifact["lifetime"],
                "confidentiality": artifact["confidentiality"],
                "source": artifact["source"],
                "tracked": artifact["tracked"],
            })
    rows.sort(key=lambda row: (row["producer"], row["artifact"]))
    return rows


def render_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "_No plugin currently declares a setup artifact._"
    header = "| " + " | ".join(COLUMNS) + " |"
    separator = "| " + " | ".join("---" for _ in COLUMNS) + " |"
    lines = [header, separator]
    for row in rows:
        lines.append("| " + " | ".join(escape_cell(row[column]) for column in COLUMNS) + " |")
    return "\n".join(lines)


def apply_markers(path: Path, content: str) -> bool:
    if not path.is_file():
        raise RenderError(f"{path} does not exist — create it with the marker pair first.")
    text = path.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise RenderError(
            f"{path}: no {BEGIN} / {END} marker pair found. Insert the marker pair by hand "
            "at the intended location before running this script — it will not guess where "
            "to put the table."
        )
    start = text.index(BEGIN) + len(BEGIN)
    stop = text.index(END)
    if start > stop:
        raise RenderError(f"{path}: {END} appears before {BEGIN}.")
    new_text = text[:start] + "\n" + content + "\n" + text[stop:]
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def render(repo_root: Path) -> bool:
    return apply_markers(repo_root / DOC_RELATIVE, render_table(collect_rows(repo_root)))


def _materialize_inputs(repo_root: Path, root: Path) -> None:
    """Copy exactly what this script reads: the marketplace list, every plugin's manifest
    (when present), and the doc it renders into. Same fixture shape as
    tests/skill-map/test_render_docs.py's hermetic copy."""
    marketplace_src = repo_root / ".claude-plugin" / "marketplace.json"
    marketplace_dest = root / ".claude-plugin" / "marketplace.json"
    marketplace_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(marketplace_src, marketplace_dest)

    for entry in load_json(marketplace_src)["plugins"]:
        manifest_src = repo_root / entry["name"] / "setup" / "manifest.json"
        if manifest_src.is_file():
            manifest_dest = root / entry["name"] / "setup" / "manifest.json"
            manifest_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_src, manifest_dest)

    doc_src = repo_root / DOC_RELATIVE
    doc_dest = root / DOC_RELATIVE
    doc_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(doc_src, doc_dest)


def check(repo_root: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        _materialize_inputs(repo_root, root)
        try:
            changed = render(root)
        except RenderError as exc:
            print(f"FAIL --check: {exc}", file=sys.stderr)
            return 1
        if changed:
            print(
                f"FAIL --check: {DOC_RELATIVE} is stale — run "
                "python3 rhize-ops/scripts/setup_artifacts.py --markdown and commit the result",
                file=sys.stderr,
            )
            return 1
    print(f"PASS --check: {DOC_RELATIVE} is current")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--markdown", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    if args.check:
        return check(repo_root)
    try:
        changed = render(repo_root)
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"rendered {DOC_RELATIVE}" if changed else f"No changes to {DOC_RELATIVE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
