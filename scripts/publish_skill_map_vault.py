#!/usr/bin/env python3
"""publish_skill_map_vault.py — publish skill-map artifacts into the Obsidian vault.

Phase 5 of the skill-map-graph-substrate plan
(.claude/plans/skill-map-graph-substrate.md). Reads
`generated/skill-map.static.json` and writes, into a machine-local Obsidian
vault:

  - one Markdown note per skill, with structured frontmatter (plugin, topics,
    stacks, description), under `<target>/notes/`
  - a Bases `.base` file (`Skill Map.base`) that queries those notes for an
    inventory table/board view
  - a JSON Canvas file (`Skill Map.canvas`) showing plugin -> skill topology,
    fork-of/replaces/depends-on edges, and topic/stack tag clusters

No usage data (co-occurrence, session counts) is published — this is the
static/structural map only. Nothing under this script writes into this repo;
the vault path is resolved at runtime and never hardcoded or committed.

Vault path resolution, in order:
  1. `RHIZE_VAULT_PATH` env var
  2. The vault marked `"open": true` in Obsidian's own global config
     (`~/Library/Application Support/obsidian/obsidian.json`), falling back
     to the first configured vault if none is marked open.

Usage:
  python3 scripts/publish_skill_map_vault.py [--target "Projects/Rhize Media/Rhize Tools/Rhize-Plugins-Marketplace/Skill Map"]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
OBSIDIAN_GLOBAL_CONFIG = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"

DEFAULT_TARGET = "Projects/Rhize Media/Rhize Tools/Rhize-Plugins-Marketplace/Skill Map"


class PublishError(Exception):
    pass


def resolve_vault_path() -> Path:
    import os

    env = os.environ.get("RHIZE_VAULT_PATH")
    if env:
        return Path(env).expanduser()

    if not OBSIDIAN_GLOBAL_CONFIG.exists():
        raise PublishError(
            "No RHIZE_VAULT_PATH set and Obsidian's global config "
            f"({OBSIDIAN_GLOBAL_CONFIG}) was not found. Set RHIZE_VAULT_PATH "
            "to the vault directory to publish."
        )
    config = json.loads(OBSIDIAN_GLOBAL_CONFIG.read_text(encoding="utf-8"))
    vaults = config.get("vaults", {})
    if not vaults:
        raise PublishError(f"{OBSIDIAN_GLOBAL_CONFIG} has no configured vaults.")
    open_vault = next((v for v in vaults.values() if v.get("open")), None)
    chosen = open_vault or next(iter(vaults.values()))
    return Path(chosen["path"])


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def yaml_scalar(value: str) -> str:
    """Minimal YAML-safe scalar quoting for frontmatter string values."""
    if value == "":
        return '""'
    needs_quote = any(c in value for c in ':#[]{}"\'') or value.strip() != value
    if needs_quote:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def yaml_list(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(yaml_scalar(i) for i in items) + "]"


class SkillMap:
    def __init__(self, doc: dict):
        self.nodes = {n["id"]: n for n in doc["nodes"]}
        self.edges = doc["edges"]

    def plugins(self) -> list[dict]:
        return sorted((n for n in self.nodes.values() if n["kind"] == "plugin"), key=lambda n: n["name"])

    def skills_of(self, plugin_id: str) -> list[dict]:
        skill_ids = sorted(
            e["to"]
            for e in self.edges
            if e["from"] == plugin_id and e["type"] == "contains" and e["to"].startswith("skill:")
        )
        return [self.nodes[sid] for sid in skill_ids]

    def tags_of(self, skill_id: str) -> tuple[list[str], list[str]]:
        topics, stacks = [], []
        for e in self.edges:
            if e["from"] != skill_id or e["type"] not in ("topic-tag", "stack-tag"):
                continue
            tag = self.nodes[e["to"]]
            (topics if tag["id"].startswith("tag:topic/") else stacks).append(tag["name"])
        return sorted(topics), sorted(stacks)

    def plugin_of(self, skill_id: str) -> str | None:
        for e in self.edges:
            if e["type"] == "contains" and e["to"] == skill_id:
                return e["from"]
        return None

    def relation_edges(self) -> list[dict]:
        return [e for e in self.edges if e["type"] in ("fork-of", "replaces", "depends-on")]


def skill_note_filename(plugin_name: str, skill_name: str) -> str:
    return f"{plugin_name}-{skill_name}.md"


def render_skill_note(skill_map: SkillMap, skill: dict, plugin_name: str) -> str:
    topics, stacks = skill_map.tags_of(skill["id"])
    description = " ".join(skill.get("description", "").split())
    lines = [
        "---",
        "rhize_skill_map: true",
        f"plugin: {yaml_scalar(plugin_name)}",
        f"skill: {yaml_scalar(skill['name'])}",
        f"topics: {yaml_list(topics)}",
        f"stacks: {yaml_list(stacks)}",
        f"source_path: {yaml_scalar(skill.get('path', ''))}",
        "---",
        "",
        f"# {skill['name']}",
        "",
        description,
        "",
        f"Plugin: `{plugin_name}` · Repo path: `{skill.get('path', '')}`",
        "",
        "> Generated by `scripts/publish_skill_map_vault.py` from "
        "`generated/skill-map.static.json`. Do not hand-edit — re-run the "
        "script to refresh.",
        "",
    ]
    return "\n".join(lines)


BASE_TEMPLATE = """\
filters:
  and:
    - 'rhize_skill_map == true'
formulas:
  topic_list: 'topics.join(", ")'
  stack_list: 'stacks.join(", ")'
properties:
  plugin:
    displayName: Plugin
  skill:
    displayName: Skill
  formula.topic_list:
    displayName: Topics
  formula.stack_list:
    displayName: Stacks
views:
  - type: table
    name: All skills
    order:
      - plugin
      - skill
      - formula.topic_list
      - formula.stack_list
    groupBy:
      property: plugin
      direction: ASC
    sort:
      - property: skill
        direction: ASC
  - type: cards
    name: By plugin
    groupBy:
      property: plugin
      direction: ASC
    order:
      - skill
      - formula.topic_list
"""


def render_base() -> str:
    return BASE_TEMPLATE


def render_canvas(skill_map: SkillMap) -> dict:
    nodes = []
    edges = []
    node_id_of: dict[str, str] = {}

    def nid(prefix: str, key: str) -> str:
        safe = key.replace(":", "_").replace("/", "_")
        return f"{prefix}_{safe}"

    # Plugin group nodes (containers), sized to hold their skill nodes.
    col_x = 0
    for plugin in skill_map.plugins():
        skills = skill_map.skills_of(plugin["id"])
        group_id = nid("group", plugin["id"])
        node_id_of[plugin["id"]] = group_id
        height = 120 + 90 * max(len(skills), 1)
        nodes.append(
            {
                "id": group_id,
                "type": "group",
                "x": col_x,
                "y": 0,
                "width": 320,
                "height": height,
                "label": plugin["name"],
            }
        )
        for i, skill in enumerate(skills):
            skill_id = nid("skill", skill["id"])
            node_id_of[skill["id"]] = skill_id
            nodes.append(
                {
                    "id": skill_id,
                    "type": "text",
                    "x": col_x + 20,
                    "y": 100 + i * 90,
                    "width": 280,
                    "height": 70,
                    "text": f"**{skill['name']}**",
                }
            )
        col_x += 400

    # Tag cluster nodes — one per tag actually used, placed below the plugin rows.
    used_tag_ids = sorted(
        {e["to"] for e in skill_map.edges if e["type"] in ("topic-tag", "stack-tag")}
    )
    tag_y = 900
    tag_x = 0
    for tag_id in used_tag_ids:
        tag = skill_map.nodes[tag_id]
        tag_node_id = nid("tag", tag_id)
        node_id_of[tag_id] = tag_node_id
        nodes.append(
            {
                "id": tag_node_id,
                "type": "text",
                "x": tag_x,
                "y": tag_y,
                "width": 200,
                "height": 50,
                "text": f"#{tag['name']}",
                "color": "4" if tag_id.startswith("tag:stack/") else "5",
            }
        )
        tag_x += 220
        if tag_x > col_x:
            tag_x = 0
            tag_y += 70
        for e in skill_map.edges:
            if e["type"] in ("topic-tag", "stack-tag") and e["to"] == tag_id:
                skill_node_id = node_id_of.get(e["from"])
                if skill_node_id:
                    edges.append(
                        {
                            "id": nid("edge", f"{e['from']}->{tag_id}"),
                            "fromNode": skill_node_id,
                            "fromSide": "bottom",
                            "toNode": tag_node_id,
                            "toSide": "top",
                            "color": "4" if tag_id.startswith("tag:stack/") else "5",
                        }
                    )

    # External nodes referenced by relation edges.
    for e in skill_map.relation_edges():
        for end in (e["from"], e["to"]):
            if end not in node_id_of:
                ext = skill_map.nodes.get(end, {"name": end, "kind": "external"})
                ext_id = nid("ext", end)
                node_id_of[end] = ext_id
                nodes.append(
                    {
                        "id": ext_id,
                        "type": "text",
                        "x": -400,
                        "y": len(nodes) * 60,
                        "width": 260,
                        "height": 60,
                        "text": f"_{ext.get('name', end)}_",
                    }
                )

    color_by_type = {"fork-of": "1", "replaces": "2", "depends-on": "6"}
    for e in skill_map.relation_edges():
        edges.append(
            {
                "id": nid("edge", f"{e['from']}->{e['to']}:{e['type']}"),
                "fromNode": node_id_of[e["from"]],
                "toNode": node_id_of[e["to"]],
                "label": e["type"],
                "color": color_by_type.get(e["type"], "0"),
            }
        )

    return {"nodes": nodes, "edges": edges}


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Vault-relative folder to publish into")
    parser.add_argument("--dry-run", action="store_true", help="Resolve paths and print plan without writing")
    args = parser.parse_args()

    if not MAP_PATH.exists():
        print(f"error: {MAP_PATH} not found — run scripts/build_skill_map.py first", file=sys.stderr)
        return 1

    try:
        vault_path = resolve_vault_path()
    except PublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    target_dir = vault_path / args.target
    if not target_dir.parent.exists():
        print(
            f"error: parent folder {target_dir.parent} does not exist in the vault — "
            "pick an existing --target or create the folder first.",
            file=sys.stderr,
        )
        return 1

    skill_map = SkillMap(load_json(MAP_PATH))

    notes_dir = target_dir / "notes"
    written: list[str] = []

    if args.dry_run:
        print(f"Would publish to: {target_dir}")
        return 0

    for plugin in skill_map.plugins():
        for skill in skill_map.skills_of(plugin["id"]):
            note_path = notes_dir / skill_note_filename(plugin["name"], skill["name"])
            if write_if_changed(note_path, render_skill_note(skill_map, skill, plugin["name"])):
                written.append(str(note_path))

    base_path = target_dir / "Skill Map.base"
    if write_if_changed(base_path, render_base()):
        written.append(str(base_path))

    canvas_path = target_dir / "Skill Map.canvas"
    canvas_content = json.dumps(render_canvas(skill_map), indent=2, sort_keys=True) + "\n"
    if write_if_changed(canvas_path, canvas_content):
        written.append(str(canvas_path))

    print(f"Vault target: {target_dir}")
    if written:
        print("Written/updated:")
        for w in written:
            print(f"  {w}")
    else:
        print("No changes (already up to date).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
