#!/usr/bin/env python3
"""test_tree_digest.py — skill-node treeHash / fileCount / totalBytes and the
MCP Skills extension (SEP-2640) per-skill limits check.

  1. skill_tree_digest() hashes only git-tracked files, so untracked build
     output (a viewer's node_modules in a dev checkout) never changes the
     committed artifact; the canonical form is reproducible by hand.
  2. Outside a git work tree it falls back to a walk that skips .git/ and
     node_modules/ (the hermetic fixture trees other tests copy the builder into).
  3. Every rhize skill node in the committed artifact carries the fields, and
     fileCount matches `git ls-files` for that skill directory.
  4. validate_skill_map.py's skill_limits_valid() rejects 513 files or more than
     16 MiB and accepts the limits exactly.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
build = load_module(REPO_ROOT / "scripts" / "build_skill_map.py", "build_skill_map_tree")
validate = load_module(REPO_ROOT / "scripts" / "validate_skill_map.py", "validate_skill_map_tree")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "core.excludesFile=/dev/null", "-C", str(root), *args],
                   check=True, capture_output=True)


def _expected(files: dict[str, bytes]) -> str:
    tree = hashlib.sha256()
    for rel in sorted(files):
        data = files[rel]
        tree.update(f"{rel}\0{hashlib.sha256(data).hexdigest()}\0{len(data)}\n".encode())
    return tree.hexdigest()


def _make_skill(root: Path) -> tuple[Path, dict[str, bytes]]:
    skill = root / "plug" / "skills" / "demo"
    files = {"SKILL.md": b"---\nname: demo\ndescription: d\n---\n", "references/guide.md": b"guide\n"}
    for rel, data in files.items():
        (skill / rel).parent.mkdir(parents=True, exist_ok=True)
        (skill / rel).write_bytes(data)
    return skill, files


def test_tracked_files_only(tmp_path, monkeypatch):
    skill, files = _make_skill(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "plug")
    (skill / "viewer" / "node_modules").mkdir(parents=True)
    (skill / "viewer" / "node_modules" / "big.js").write_bytes(b"x" * 1000)
    (skill / "untracked.md").write_bytes(b"not staged\n")
    monkeypatch.setattr(build, "REPO_ROOT", tmp_path)
    result = build.skill_tree_digest(skill)
    assert result == {
        "treeHash": _expected(files),
        "fileCount": 2,
        "totalBytes": sum(len(v) for v in files.values()),
    }


def test_non_git_fallback_skips_node_modules(tmp_path, monkeypatch):
    skill, files = _make_skill(tmp_path)
    (skill / "node_modules").mkdir()
    (skill / "node_modules" / "dep.js").write_bytes(b"dep")
    monkeypatch.setattr(build, "REPO_ROOT", tmp_path)
    result = build.skill_tree_digest(skill)
    assert result["treeHash"] == _expected(files)
    assert result["fileCount"] == 2


def test_committed_artifact_counts_match_git(doc):
    skills = [n for n in doc["nodes"] if n["kind"] == "skill" and n.get("origin", "rhize") == "rhize"]
    assert skills
    for node in skills:
        assert len(node["treeHash"]) == 64
        skill_dir = str(Path(node["path"]).parent)
        tracked = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--", skill_dir],
                                 capture_output=True, check=True).stdout.split(b"\0")
        assert node["fileCount"] == len([p for p in tracked if p]), node["id"]
        assert node["fileCount"] <= validate.MAX_SKILL_FILES
        assert node["totalBytes"] <= validate.MAX_SKILL_BYTES


def test_limits_check():
    def doc_with(**fields):
        return {"nodes": [{"id": "skill:p/s", "kind": "skill", **fields}]}
    assert validate.skill_limits_valid(doc_with(fileCount=512, totalBytes=16 * 1024 * 1024))[0]
    ok, err = validate.skill_limits_valid(doc_with(fileCount=513, totalBytes=1))
    assert not ok and "513" in err
    ok, err = validate.skill_limits_valid(doc_with(fileCount=1, totalBytes=16 * 1024 * 1024 + 1))
    assert not ok and "16 MiB" in err
    assert validate.skill_limits_valid(doc_with())[0]
