#!/usr/bin/env python3
"""render_skill_map_docs.py — fill managed doc sections from the skill map.

Phase 5 of the skill-map-graph-substrate plan
(.claude/plans/skill-map-graph-substrate.md). Reads
`generated/skill-map.static.json` (rebuild it first with
`scripts/build_skill_map.py` if it's stale) and rewrites ONLY the content
between `<!-- SKILL-MAP:BEGIN -->` / `<!-- SKILL-MAP:END -->` marker pairs in:

  - every plugin's `README.md` (its skill table)
  - the root `README.md` (the Plugin Catalog table)
  - `generated/SKILL-CATALOG.md` (full cross-plugin catalog)
  - `docs/README.md` (the per-plugin index — name, version, description,
    README/GUIDE links, skill count)

Every human-facing skill table prefers a skill's `metadata.rhize.summary`
frontmatter (see build_skill_map.py) over the mechanically-derived
`first_sentence(description)` fallback, since `description` is a runtime
trigger string ("ALWAYS invoke this skill...") rather than a human summary.

Everything outside a marker pair is left byte-for-byte untouched. A target
file that has no marker pair is a hard error — markers are inserted by hand,
once, at the location a maintainer chooses; this script never guesses where
a table belongs.

Idempotent: running this twice against an unchanged skill map produces zero
diff on any target file.

Usage:
  python3 scripts/render_skill_map_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"

BEGIN = "<!-- SKILL-MAP:BEGIN -->"
END = "<!-- SKILL-MAP:END -->"

# Plugins that get the ⭐ hub annotation in the root Plugin Catalog table.
# Not derivable from marketplace.json (no "hub" field exists there) — a
# hand-declared exception, kept here rather than invented as new schema.
HUB_PLUGINS = {"rhize-ops"}

# Per-(plugin, marker-location) skill subsets that don't match "all skills
# in the plugin" — real hand-curated groupings that predate the skill map
# and aren't derivable from it. Each value is a predicate over a skill dict
# (as produced by `skill_info`). Plugins/locations not listed here get every
# skill the plugin contains.
SECTION_FILTERS = {
    # rhize-context-manager/README.md's "Rhize-authored" table excludes the
    # curated third-party skills, which are exactly the ones with a fork-of
    # edge to the upstream marketplace (see SOURCES.md).
    "rhize-context-manager": lambda s: not s["fork_of"],
    # obsidian-second-brain/README.md's "Skills — Second Brain" table is the
    # methodology/workflow group; "Format Skills" (obsidian-markdown,
    # obsidian-bases, json-canvas, obsidian-cli) is a separate hand-written
    # table left untouched outside any marker.
    "obsidian-second-brain": lambda s: s["name"]
    in {
        "second-brain",
        "vault-templates",
        "vault-alignment",
        "qmd-search",
        "defuddle",
        "knowledge-compiler",
    },
}


class RenderError(Exception):
    pass


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def first_sentence(description: str, limit: int = 140) -> str:
    """Collapse a long SKILL.md trigger description into one table-friendly line."""
    text = " ".join(description.split())
    # Prefer the first sentence (period followed by space/end), else just truncate.
    cut = text.find(". ")
    if 0 < cut < limit * 2:
        text = text[: cut + 1]
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


class SkillMap:
    def __init__(self, doc: dict):
        self.nodes = {n["id"]: n for n in doc["nodes"]}
        self.edges = doc["edges"]

    def plugins(self) -> list[dict]:
        return [n for n in self.nodes.values() if n["kind"] == "plugin"]

    def skills_of(self, plugin_id: str) -> list[dict]:
        skill_ids = sorted(
            e["to"]
            for e in self.edges
            if e["from"] == plugin_id and e["type"] == "contains" and e["to"].startswith("skill:")
        )
        return [self.skill_info(sid) for sid in skill_ids]

    def skill_info(self, skill_id: str) -> dict:
        node = self.nodes[skill_id]
        topics = sorted(
            self.nodes[e["to"]]["name"]
            for e in self.edges
            if e["from"] == skill_id and e["type"] in ("topic-tag", "stack-tag")
        )
        fork_of = [e["to"] for e in self.edges if e["from"] == skill_id and e["type"] == "fork-of"]
        return {
            "id": skill_id,
            "name": node["name"],
            "description": node.get("description", ""),
            "summary": node.get("summary", ""),
            "topics": topics,
            "fork_of": fork_of,
        }


def render_skill_table(skills: list[dict]) -> str:
    lines = ["| Skill | Description | Topics |", "| --- | --- | --- |"]
    for s in sorted(skills, key=lambda x: x["name"]):
        desc = (s.get("summary") or first_sentence(s["description"])).replace("|", "\\|")
        topics = ", ".join(s["topics"]) or "—"
        lines.append(f"| `{s['name']}` | {desc} | {topics} |")
    return "\n".join(lines)


def render_root_catalog(skill_map: SkillMap, marketplace: dict) -> str:
    lines = ["| Plugin | Version | Skill Count | Description | Docs |", "| --- | --- | --- | --- | --- |"]
    for entry in marketplace["plugins"]:
        name = entry["name"]
        plugin_id = f"plugin:{name}"
        count = len(skill_map.skills_of(plugin_id))
        label = f"[{name}](./{name})"
        if name in HUB_PLUGINS:
            label += " ⭐ **hub — recommended base install**"
        docs = f"[README](./{name}/README.md) · [GUIDE](./{name}/GUIDE.md)"
        desc = entry.get("description", "").replace("|", "\\|")
        lines.append(f"| {label} | {entry.get('version', '—')} | {count} | {desc} | {docs} |")
    return "\n".join(lines)


def render_catalog_md(skill_map: SkillMap, marketplace: dict) -> str:
    sections = []
    for entry in marketplace["plugins"]:
        name = entry["name"]
        plugin_id = f"plugin:{name}"
        skills = skill_map.skills_of(plugin_id)
        sections.append(f"## {name}\n\n{render_skill_table(skills)}" if skills else f"## {name}\n\n_No skills._")
    return "\n\n".join(sections)


def render_docs_index(skill_map: SkillMap, marketplace: dict) -> str:
    """docs/README.md's per-plugin index: one block per marketplace plugin
    with its version, canonical description, README/GUIDE links, and a skill
    count linking into the full cross-plugin catalog."""
    sections = []
    for entry in marketplace["plugins"]:
        name = entry["name"]
        plugin_id = f"plugin:{name}"
        count = len(skill_map.skills_of(plugin_id))
        version = entry.get("version", "—")
        desc = entry.get("description", "")
        skill_word = "skill" if count == 1 else "skills"
        sections.append(
            f"### {name}\n\n"
            f"Version {version}. {desc}\n\n"
            f"[README](../{name}/README.md) · [GUIDE](../{name}/GUIDE.md) · "
            f"[{count} {skill_word}](../generated/SKILL-CATALOG.md#{name})"
        )
    return "\n\n".join(sections)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def apply_markers(path: Path, content: str) -> bool:
    """Replace the region between BEGIN/END markers. Returns True if changed."""
    text = path.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise RenderError(
            f"{_display_path(path)}: no {BEGIN} / {END} marker pair found. "
            "Insert the marker pair by hand at the intended location before running "
            "this script — it will not guess where to put a managed table."
        )
    start = text.index(BEGIN) + len(BEGIN)
    stop = text.index(END)
    if start > stop:
        raise RenderError(f"{_display_path(path)}: {END} appears before {BEGIN}.")
    new_text = text[:start] + "\n" + content + "\n" + text[stop:]
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    if not MAP_PATH.exists():
        print(f"error: {MAP_PATH} not found — run scripts/build_skill_map.py first", file=sys.stderr)
        return 1
    skill_map = SkillMap(load_json(MAP_PATH))
    marketplace = load_json(MARKETPLACE_PATH)

    changed: list[str] = []
    errors: list[str] = []

    for entry in marketplace["plugins"]:
        name = entry["name"]
        readme = REPO_ROOT / name / "README.md"
        if not readme.exists():
            errors.append(f"{name}: README.md not found at {readme}")
            continue
        skills = skill_map.skills_of(f"plugin:{name}")
        section_filter = SECTION_FILTERS.get(name)
        if section_filter:
            skills = [s for s in skills if section_filter(s)]
        try:
            if apply_markers(readme, render_skill_table(skills)):
                changed.append(str(readme.relative_to(REPO_ROOT)))
        except RenderError as exc:
            errors.append(str(exc))

    root_readme = REPO_ROOT / "README.md"
    try:
        if apply_markers(root_readme, render_root_catalog(skill_map, marketplace)):
            changed.append(str(root_readme.relative_to(REPO_ROOT)))
    except RenderError as exc:
        errors.append(str(exc))

    catalog_md = REPO_ROOT / "generated" / "SKILL-CATALOG.md"
    try:
        if apply_markers(catalog_md, render_catalog_md(skill_map, marketplace)):
            changed.append(str(catalog_md.relative_to(REPO_ROOT)))
    except RenderError as exc:
        errors.append(str(exc))

    docs_readme = REPO_ROOT / "docs" / "README.md"
    try:
        if apply_markers(docs_readme, render_docs_index(skill_map, marketplace)):
            changed.append(str(docs_readme.relative_to(REPO_ROOT)))
    except RenderError as exc:
        errors.append(str(exc))

    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 1

    if changed:
        print("Updated:")
        for c in changed:
            print(f"  {c}")
    else:
        print("No changes (already up to date).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
