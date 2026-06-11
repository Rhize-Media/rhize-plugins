#!/usr/bin/env python3
"""profile_skill.py — Structured profile of an external skill candidate.

Accepts a directory, a single SKILL.md, or a .skill (zip) bundle. Produces a JSON or
human-readable profile: frontmatter, license, body size/structure, bundled resources,
declared MCP/tool dependencies, and external package imports.

Stdlib only. Fails loudly with clear messages rather than guessing.

Usage:
    python3 profile_skill.py <path-to-skill|SKILL.md|.skill> [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

SPDX_HINTS = {
    "mit": "MIT (permissive)",
    "apache": "Apache-2.0 (permissive)",
    "bsd": "BSD (permissive)",
    "isc": "ISC (permissive)",
    "unlicense": "Unlicense (public domain)",
    "cc0": "CC0 (public domain)",
    "mozilla public license": "MPL (weak copyleft)",
    "gnu general public": "GPL (copyleft)",
    "gnu affero": "AGPL (copyleft)",
    "creative commons attribution-sharealike": "CC-BY-SA (copyleft)",
    "creative commons attribution": "CC-BY (attribution)",
    "all rights reserved": "All rights reserved (restrictive)",
}

RESOURCE_DIRS = ["scripts", "references", "reference", "commands", "hooks", "assets", "templates", "sub-skills"]


def fail(msg: str) -> "None":
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def resolve_skill_md(path: Path) -> tuple[Path, Path, Path | None]:
    """Return (skill_md_path, skill_root, tempdir_to_cleanup)."""
    tmp = None
    if path.suffix == ".skill" or (path.is_file() and zipfile.is_zipfile(str(path))):
        tmp = Path(tempfile.mkdtemp(prefix="forge_"))
        with zipfile.ZipFile(str(path)) as z:
            z.extractall(str(tmp))
        path = tmp
    if path.is_file() and path.name == "SKILL.md":
        return path, path.parent, tmp
    if path.is_dir():
        direct = path / "SKILL.md"
        if direct.exists():
            return direct, path, tmp
        # look one level down (plugin layout: skills/<name>/SKILL.md)
        matches = list(path.glob("*/SKILL.md")) + list(path.glob("skills/*/SKILL.md"))
        if len(matches) == 1:
            return matches[0], matches[0].parent, tmp
        if len(matches) > 1:
            fail(f"multiple SKILL.md found under {path}; point at a single skill dir:\n  "
                 + "\n  ".join(str(m) for m in matches))
    fail(f"no SKILL.md found at {path}")


def parse_frontmatter(text: str) -> dict:
    fm: dict = {}
    if not text.startswith("---\n"):
        fm["_valid_frontmatter"] = False
        return fm
    fm["_valid_frontmatter"] = True
    block = text.split("---", 2)[1]
    for key in ("name", "version", "license"):
        m = re.search(rf"^{key}:\s*(.+)$", block, re.M)
        if m:
            fm[key] = m.group(1).strip().strip("'\"")
    # description may be folded (>- or |) or inline
    m = re.search(r"^description:\s*(.*)$", block, re.M)
    if m:
        first = m.group(1).strip()
        if first in (">", ">-", "|", "|-", ""):
            # gather indented continuation lines
            lines = block.splitlines()
            idx = next(i for i, l in enumerate(lines) if re.match(r"^description:", l))
            buf = []
            for l in lines[idx + 1:]:
                if re.match(r"^\s+\S", l):
                    buf.append(l.strip())
                elif l.strip() == "":
                    continue
                else:
                    break
            fm["description"] = " ".join(buf).strip()
        else:
            fm["description"] = first.strip("'\"")
    return fm


def detect_license(root: Path, fm: dict) -> str:
    if fm.get("license"):
        return fm["license"]
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "license"):
        p = root / name
        if p.exists():
            head = p.read_text(errors="ignore")[:2000].lower()
            for hint, label in SPDX_HINTS.items():
                if hint in head:
                    return label
            return "present but unrecognized"
    return "NONE STATED"


def profile(path: Path) -> dict:
    skill_md, root, tmp = resolve_skill_md(path)
    try:
        text = skill_md.read_text(errors="ignore")
        fm = parse_frontmatter(text)
        body_lines = text.count("\n") + 1
        headers = re.findall(r"^#{1,3}\s+(.+)$", text, re.M)

        resources = {}
        for d in RESOURCE_DIRS:
            dp = root / d
            if dp.is_dir():
                files = [f for f in dp.rglob("*") if f.is_file()]
                resources[d] = len(files)

        mcp_refs = sorted(set(re.findall(r"mcp__[a-zA-Z0-9_]+", text)))
        # also scan scripts/ and references/ for mcp refs + python imports
        imports: set = set()
        for sub in (root / "scripts",):
            if sub.is_dir():
                for f in sub.rglob("*.py"):
                    ft = f.read_text(errors="ignore")
                    mcp_refs = sorted(set(mcp_refs) | set(re.findall(r"mcp__[a-zA-Z0-9_]+", ft)))
                    for im in re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)", ft, re.M):
                        imports.add(im)
        stdlib = {"os", "sys", "re", "json", "argparse", "pathlib", "tempfile", "zipfile",
                  "subprocess", "collections", "datetime", "math", "itertools", "typing",
                  "shutil", "glob", "hashlib", "urllib", "csv", "io", "functools", "__future__"}
        external = sorted(imports - stdlib)

        return {
            "input_path": str(path),
            "skill_md": str(skill_md),
            "name": fm.get("name"),
            "version": fm.get("version"),
            "valid_frontmatter": fm.get("_valid_frontmatter", False),
            "description": fm.get("description"),
            "license": detect_license(root, fm),
            "body_lines": body_lines,
            "header_count": len(headers),
            "top_headers": headers[:12],
            "resources": resources,
            "mcp_dependencies": mcp_refs,
            "external_python_deps": external,
        }
    finally:
        if tmp:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Profile an external skill candidate.")
    ap.add_argument("path", help="skill dir, SKILL.md, or .skill bundle")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    p = Path(os.path.expanduser(args.path)).resolve()
    if not p.exists():
        fail(f"path does not exist: {p}")

    data = profile(p)
    if args.json:
        print(json.dumps(data, indent=2))
        return

    print(f"Skill:        {data['name']}  (v{data['version']})")
    print(f"Frontmatter:  {'valid' if data['valid_frontmatter'] else 'INVALID — would not trigger'}")
    print(f"License:      {data['license']}")
    print(f"Body:         {data['body_lines']} lines, {data['header_count']} headers")
    print(f"Resources:    {data['resources'] or 'none'}")
    print(f"MCP deps:     {', '.join(data['mcp_dependencies']) or 'none'}")
    print(f"External deps:{' ' + ', '.join(data['external_python_deps']) if data['external_python_deps'] else ' none'}")
    print(f"\nDescription:\n  {data['description']}")


if __name__ == "__main__":
    main()
