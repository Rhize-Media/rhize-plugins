#!/usr/bin/env python3
"""build_skill_map.py — deterministic compiler for generated/skill-map.static.json.

Phase 1 of the skill-map-graph-substrate plan
(.claude/plans/skill-map-graph-substrate.md). Reads the sources listed below
and emits a single artifact conforming to schemas/skill-map.schema.json.
Semantic overlap detection is explicitly OUT of scope here — that stays with
skill-forge's organize/audit pipeline for a later phase.

Determinism contract: two runs against an unchanged working tree MUST produce
byte-identical output. To hold that contract:
  - no `generatedAt` timestamp is written to the artifact
  - all node/edge lists are sorted by a stable key before serialization
  - directory listings are sorted before iteration
  - JSON is dumped with sort_keys=True, a fixed separator, and a trailing
    newline

Inputs and what they produce
-----------------------------
1. `.claude-plugin/marketplace.json`
   -> one `plugin` node per entry, plus `contains` edges (source: marketplace)
      from each plugin to every skill/command/hook node discovered under it.
      Attributing ALL `contains` edges to `source: marketplace` (rather than
      splitting by which sub-scan found the child) matches the plan's own
      phrasing for this input ("plugin nodes + contains edges (source:
      marketplace)") and keeps edge provenance simple: "contains" answers
      "was this plugin registered in the marketplace", not "which scanner
      walked the directory".

2. Each plugin's `skills/*/SKILL.md`
   -> one `skill` node per skill directory that has a SKILL.md (path,
      description, contentHash = sha256 of the file's raw bytes), plus
      `topic-tag` / `stack-tag` edges from that skill to `tag:topic/<slug>`
      and `tag:stack/<slug>` nodes, read from the file's
      `metadata.rhize.{topics,stacks}` frontmatter (source: frontmatter).

3. Each plugin's `commands/*.md`
   -> one `command` node per file (description from frontmatter if present).

4. Each plugin's `hooks/hooks.json` (auto-wired hooks) AND
   `setup/manifest.json` (opt-in hooks, `default: false` items) where present
   -> one `hook` node per hook entry: event, matcher (if any), command path,
      owner (the plugin), and `status` ("wired" for hooks.json entries,
      "opt-in" for manifest.json entries). rhize-context-manager's
      setup/manifest.json items point at skill-bundled hook scripts under
      `skills/context-engineering/hooks/*.sh` — those are picked up the same
      way as any other manifest item, no special-casing needed.

5. `rhize-context-manager/skills/SOURCES.md` (the plan names
   `rhize-context-manager/SOURCES.md`; the file actually lives one level
   deeper, at `skills/SOURCES.md` — read from the real path)
   -> `fork-of` edges from the corresponding skill node to an `external`
      node representing the upstream marketplace, for every entry that is
      NOT marked RETIRED. See `parse_sources_md()` for the exact grammar.
      An entry whose skill directory no longer exists (and which isn't
      marked RETIRED) is a build ERROR, not a silent skip — see
      `PARSE GRAMMAR` below and `parse_sources_md()`.
      NEVER execute anything read from this file: it is parsed with plain
      string/regex operations only, never passed to a shell.

6. `catalog/skill-relations.json`
   -> hand-declared nodes/edges (overlaps-with / depends-on / replaces),
      merged in verbatim (source: relations-catalog, already set in the
      file itself).

Node id scheme (must match schemas/skill-map.schema.json's nodeId pattern):
  plugin:<plugin>
  skill:<plugin>/<skill-dir>
  command:<plugin>/<command-stem>
  hook:<plugin>/<slug>              (slug = script basename stem, or a
                                      positional fallback for inline commands)
  tag:topic/<slug>  tag:stack/<slug>
  external:<name>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"
CATALOG_PATH = REPO_ROOT / "catalog" / "skill-relations.json"
SOURCES_MD_PATH = REPO_ROOT / "rhize-context-manager" / "skills" / "SOURCES.md"
OUTPUT_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
SCHEMA_VERSION = "1.0.0"

try:
    import yaml
except ImportError:  # pragma: no cover - environment-dependent
    yaml = None


class BuildError(Exception):
    """Raised for conditions the plan requires to be a hard build failure."""


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body) for a '---\\n...\\n---\\n' delimited file.

    Returns ({}, text) if there is no frontmatter block or it can't be parsed.
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n---", 2)
    # text.split on the closing delimiter: first chunk includes the opening
    # '---', so strip it.
    if len(parts) < 2:
        return {}, text
    raw_fm = parts[0]
    if raw_fm.startswith("---"):
        raw_fm = raw_fm[3:]
    body = parts[1]
    if body.startswith("\n"):
        body = body[1:]
    if yaml is not None:
        try:
            data = yaml.safe_load(raw_fm) or {}
            if not isinstance(data, dict):
                data = {}
            return data, body
        except yaml.YAMLError:
            return {}, body
    return {}, body


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9_.\-]+", "-", value.strip().lower()).strip("-")


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []

    def add_node(self, node: dict) -> None:
        node_id = node["id"]
        if node_id in self.nodes:
            existing = self.nodes[node_id]
            if existing != node:
                # Merge: keep richer of the two (non-destructive union),
                # but flag a real conflict on differing values for the same key.
                merged = dict(existing)
                for k, v in node.items():
                    if k in merged and merged[k] != v:
                        raise BuildError(
                            f"conflicting node definitions for {node_id!r}: "
                            f"{k}={merged[k]!r} vs {v!r}"
                        )
                    merged[k] = v
                self.nodes[node_id] = merged
            return
        self.nodes[node_id] = node

    def add_edge(self, edge: dict) -> None:
        self.edges.append(edge)

    def to_document(self) -> dict:
        node_ids = set(self.nodes.keys())
        dangling = [
            e for e in self.edges if e["from"] not in node_ids or e["to"] not in node_ids
        ]
        if dangling:
            raise BuildError(f"dangling edge references: {dangling}")
        nodes_sorted = sorted(self.nodes.values(), key=lambda n: n["id"])
        edges_sorted = sorted(
            self.edges, key=lambda e: (e["from"], e["to"], e["type"], e["source"])
        )
        # de-duplicate identical edges (same from/to/type/source) that may
        # arise from independent inputs describing the same relationship.
        seen = set()
        deduped = []
        for e in edges_sorted:
            key = (e["from"], e["to"], e["type"], e["source"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(e)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "nodes": nodes_sorted,
            "edges": deduped,
        }


def load_marketplace(graph: Graph) -> list[dict]:
    data = json.loads(MARKETPLACE_PATH.read_text())
    plugins = []
    for entry in data["plugins"]:
        name = entry["name"]
        source = entry["source"]
        plugin_dir_name = source[2:] if source.startswith("./") else source
        graph.add_node(
            {
                "id": f"plugin:{name}",
                "kind": "plugin",
                "name": name,
                "path": plugin_dir_name,
                "description": entry.get("description", ""),
            }
        )
        plugins.append({"name": name, "dir": REPO_ROOT / plugin_dir_name})
    plugins.sort(key=lambda p: p["name"])
    return plugins


def contains_edge(plugin_name: str, child_id: str) -> dict:
    return {
        "from": f"plugin:{plugin_name}",
        "to": child_id,
        "type": "contains",
        "source": "marketplace",
    }


def load_skills(graph: Graph, plugin_name: str, plugin_dir: Path) -> None:
    skills_dir = plugin_dir / "skills"
    if not skills_dir.is_dir():
        return
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue  # e.g. seo-aeo-geo/skills/shared/ has no SKILL.md
        skill_name = skill_dir.name
        text = skill_md.read_text()
        frontmatter, _ = split_frontmatter(text)
        description = frontmatter.get("description", "")
        if isinstance(description, str):
            description = description.strip()
        else:
            description = str(description)
        rel_path = str(skill_md.relative_to(REPO_ROOT))
        node_id = f"skill:{plugin_name}/{skill_name}"
        graph.add_node(
            {
                "id": node_id,
                "kind": "skill",
                "name": skill_name,
                "path": rel_path,
                "description": description,
                "contentHash": sha256_of_file(skill_md),
            }
        )
        graph.add_edge(contains_edge(plugin_name, node_id))

        rhize_meta = (frontmatter.get("metadata") or {}).get("rhize") or {}
        topics = rhize_meta.get("topics") or []
        stacks = rhize_meta.get("stacks") or []
        for topic in topics:
            tag_id = f"tag:topic/{slugify(str(topic))}"
            graph.add_node({"id": tag_id, "kind": "tag", "name": str(topic)})
            graph.add_edge(
                {
                    "from": node_id,
                    "to": tag_id,
                    "type": "topic-tag",
                    "source": "frontmatter",
                }
            )
        for stack in stacks:
            tag_id = f"tag:stack/{slugify(str(stack))}"
            graph.add_node({"id": tag_id, "kind": "tag", "name": str(stack)})
            graph.add_edge(
                {
                    "from": node_id,
                    "to": tag_id,
                    "type": "stack-tag",
                    "source": "frontmatter",
                }
            )


def load_commands(graph: Graph, plugin_name: str, plugin_dir: Path) -> None:
    commands_dir = plugin_dir / "commands"
    if not commands_dir.is_dir():
        return
    for cmd_md in sorted(commands_dir.glob("*.md")):
        stem = cmd_md.stem
        text = cmd_md.read_text()
        frontmatter, _ = split_frontmatter(text)
        description = frontmatter.get("description", "")
        if not isinstance(description, str):
            description = str(description)
        node_id = f"command:{plugin_name}/{stem}"
        graph.add_node(
            {
                "id": node_id,
                "kind": "command",
                "name": stem,
                "path": str(cmd_md.relative_to(REPO_ROOT)),
                "description": description.strip(),
            }
        )
        graph.add_edge(contains_edge(plugin_name, node_id))


# Only treat a path as identifying the hook when it sits under a hooks/
# directory (optionally nested, e.g. hooks/scripts/foo.py) — otherwise an
# inline SessionStart command that merely *checks for* a project file like
# "next.config.js" would be misread as naming a hook script.
_SCRIPT_RE = re.compile(r"hooks/(?:[A-Za-z0-9_.\-]+/)*([A-Za-z0-9_.\-]+\.(?:sh|js|py))")


def hook_slug(command: str, fallback: str) -> str:
    match = _SCRIPT_RE.search(command)
    if match:
        return Path(match.group(1)).stem
    return fallback


def load_hooks_json(graph: Graph, plugin_name: str, plugin_dir: Path) -> None:
    hooks_json_path = plugin_dir / "hooks" / "hooks.json"
    if not hooks_json_path.is_file():
        return
    data = json.loads(hooks_json_path.read_text())
    hooks_by_event = data.get("hooks", {})
    for event in sorted(hooks_by_event.keys()):
        groups = hooks_by_event[event]
        for g_idx, group in enumerate(groups):
            matcher = group.get("matcher", "")
            for h_idx, hook_entry in enumerate(group.get("hooks", [])):
                command = hook_entry.get("command", "")
                fallback = f"{event.lower()}-{g_idx}-{h_idx}"
                slug = hook_slug(command, fallback)
                node_id = f"hook:{plugin_name}/{slug}"
                graph.add_node(
                    {
                        "id": node_id,
                        "kind": "hook",
                        "name": slug,
                        "path": str(hooks_json_path.relative_to(REPO_ROOT)),
                        "event": event,
                        "matcher": matcher,
                        "command": command,
                        "owner": plugin_name,
                        "status": "wired",
                    }
                )
                graph.add_edge(contains_edge(plugin_name, node_id))


def load_manifest_hooks(graph: Graph, plugin_name: str, plugin_dir: Path) -> None:
    manifest_path = plugin_dir / "setup" / "manifest.json"
    if not manifest_path.is_file():
        return
    data = json.loads(manifest_path.read_text())
    for item in data.get("items", []):
        if item.get("event") not in _MANIFEST_HOOK_EVENTS:
            continue
        item_id = item["id"]
        node_id = f"hook:{plugin_name}/{item_id}"
        graph.add_node(
            {
                "id": node_id,
                "kind": "hook",
                "name": item_id,
                "path": str(manifest_path.relative_to(REPO_ROOT)),
                "event": item.get("event", ""),
                "matcher": item.get("matcher", ""),
                "command": item.get("command", ""),
                "owner": plugin_name,
                "status": "opt-in" if item.get("default") is False else "opt-in-default-on",
            }
        )
        graph.add_edge(contains_edge(plugin_name, node_id))


# setup/manifest.json items are hooks in every plugin observed in this repo
# (schema 1: {id, title, tier, event, matcher?, command, description,
# default}). Restrict to items that look like a hook (have an "event" field)
# so this stays correct if a future manifest schema adds non-hook item kinds.
_MANIFEST_HOOK_EVENTS = {
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
    "Notification",
    "PreCompact",
}


# ---------------------------------------------------------------------------
# SOURCES.md parse grammar
# ---------------------------------------------------------------------------
# The file is a flat sequence of entries, most-recent-appended-last. Each
# entry is:
#
#   ## <skill-name> — <date>
#   - **Source:** <absolute path, typically .../marketplaces/<name>/skills/<rest>>
#   - **Upstream ref:** <value>
#   - **License:** <value>
#   - **Verb:** <value>              (FORK | DEFER | ADAPT | ... — free text)
#   - **Target:** <value>
#   - **Took:** <value>
#   - **Verified:** <value>
#   - **Drift check:** <value>
#   - **Notes:** <value>
#   - **RETIRED <date>:** <text>     (OPTIONAL — only present if retired)
#
# Parsing rule: split the file on lines starting with "## ", each block's
# first line (after stripping "## ") up to " — " is the skill-name; the rest
# of the block is scanned line-by-line for "- **<Field>:** <value>" bullets.
# A block containing a bullet whose field name starts with "RETIRED" marks
# that entry retired — its skill is expected to no longer exist under
# rhize-context-manager/skills/, and no fork-of edge is emitted for it.
# A non-retired entry's "Source" value is expected to contain
# ".../marketplaces/<marketplace-name>/skills/<upstream-path>"; the
# marketplace name becomes an `external:<marketplace-name>` node and the
# fork-of edge's driftCheck.upstreamPath is the parsed <upstream-path>.
#
# SECURITY: this parser performs ONLY string splitting and regex matching.
# Nothing read from this file is ever passed to a shell, eval, or exec.
_HEADING_RE = re.compile(r"^##\s+(.+?)\s+—\s+(.+)$")
_BULLET_RE = re.compile(r"^-\s+\*\*([^:*]+):\*\*\s*(.*)$")
_SOURCE_PATH_RE = re.compile(r"/marketplaces/([^/]+)/skills/(.+)$")


def parse_sources_md(path: Path) -> list[dict]:
    if not path.is_file():
        raise BuildError(f"SOURCES.md not found at expected path: {path}")
    lines = path.read_text().splitlines()
    entries: list[dict] = []
    current: dict | None = None
    for line in lines:
        heading = _HEADING_RE.match(line)
        if heading:
            if current is not None:
                entries.append(current)
            current = {"skill_name": heading.group(1).strip(), "fields": {}, "retired": False}
            continue
        if current is None:
            continue
        bullet = _BULLET_RE.match(line.strip())
        if bullet:
            field, value = bullet.group(1).strip(), bullet.group(2).strip()
            if field.upper().startswith("RETIRED"):
                current["retired"] = True
            else:
                current["fields"][field] = value
    if current is not None:
        entries.append(current)
    return entries


def load_sources_md(graph: Graph) -> None:
    entries = parse_sources_md(SOURCES_MD_PATH)
    plugin_name = "rhize-context-manager"
    plugin_skills_dir = REPO_ROOT / plugin_name / "skills"
    for entry in entries:
        skill_name = entry["skill_name"]
        if entry["retired"]:
            continue
        skill_dir = plugin_skills_dir / skill_name
        if not (skill_dir / "SKILL.md").is_file():
            raise BuildError(
                f"SOURCES.md entry {skill_name!r} is not marked RETIRED but "
                f"no SKILL.md exists at {skill_dir} — unresolvable reference"
            )
        source_value = entry["fields"].get("Source", "")
        match = _SOURCE_PATH_RE.search(source_value)
        if not match:
            raise BuildError(
                f"SOURCES.md entry {skill_name!r}: could not parse an "
                f"upstream marketplace/skill path out of Source={source_value!r}"
            )
        marketplace_name, upstream_path = match.group(1), match.group(2)
        external_id = f"external:{marketplace_name}"
        graph.add_node(
            {
                "id": external_id,
                "kind": "external",
                "name": marketplace_name,
            }
        )
        skill_node_id = f"skill:{plugin_name}/{skill_name}"
        graph.add_edge(
            {
                "from": skill_node_id,
                "to": external_id,
                "type": "fork-of",
                "source": "sources-md",
                "driftCheck": {
                    "upstreamRepo": marketplace_name,
                    "upstreamPath": upstream_path,
                    "method": "manual",
                },
            }
        )


def load_catalog(graph: Graph) -> None:
    if not CATALOG_PATH.is_file():
        return
    data = json.loads(CATALOG_PATH.read_text())
    for node in data.get("nodes", []):
        graph.add_node(node)
    for edge in data.get("edges", []):
        graph.add_edge(edge)


def build() -> dict:
    graph = Graph()
    plugins = load_marketplace(graph)
    for plugin in plugins:
        load_skills(graph, plugin["name"], plugin["dir"])
        load_commands(graph, plugin["name"], plugin["dir"])
        load_hooks_json(graph, plugin["name"], plugin["dir"])
        load_manifest_hooks(graph, plugin["name"], plugin["dir"])
    load_sources_md(graph)
    load_catalog(graph)
    return graph.to_document()


def dump(document: dict) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    try:
        document = build()
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(dump(document))
    node_kinds: dict[str, int] = {}
    for node in document["nodes"]:
        node_kinds[node["kind"]] = node_kinds.get(node["kind"], 0) + 1
    edge_types: dict[str, int] = {}
    for edge in document["edges"]:
        edge_types[edge["type"]] = edge_types.get(edge["type"], 0) + 1
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"Nodes by kind: {json.dumps(node_kinds, sort_keys=True)}")
    print(f"Edges by type: {json.dumps(edge_types, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
