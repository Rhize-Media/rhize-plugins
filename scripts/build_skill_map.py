#!/usr/bin/env python3
"""build_skill_map.py — deterministic compiler for generated/skill-map.static.json.

Phase 1 of the skill-map-graph-substrate plan
(.claude/plans/skill-map-graph-substrate.md). Reads the sources listed below
and emits a single artifact conforming to schemas/skill-map.schema.json.
Semantic overlap detection is explicitly OUT of scope here — that stays with
skill-forge's organize/audit pipeline for a later phase.

Usage:
  python3 scripts/build_skill_map.py            # write generated/skill-map.static.json
  python3 scripts/build_skill_map.py --install  # also copy the artifact to
                                                 # ~/.claude/context-manager/skill-map.static.json
                                                 # (Phase 2: installed plugins, e.g. the
                                                 # skill-router.js hook, can't see this repo's
                                                 # generated/ dir and read from there instead)
  python3 scripts/build_skill_map.py --out <path>  # write to <path> instead of the default
                                                    # OUTPUT_PATH (used by --check-stale to
                                                    # rebuild into a temp file without touching
                                                    # the committed artifact)

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
      Every slug must exist in `catalog/tags.json`'s closed vocabulary
      (a BuildError otherwise); the tag node's description is set from
      that entry's gloss. Also reads `metadata.rhize.extends` — a list of
      targets, each a bare skill name (same plugin) or "plugin/skill-name"
      (cross-plugin) — and emits `extends` edges (source: frontmatter) once
      every plugin's skills have been loaded. An unresolved target is a
      BuildError naming the file and the target; chains deeper than 2 hops
      or containing a cycle are also BuildErrors (see
      `resolve_extends_edges()` / `check_extends_chains()`).

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
   -> `fork-of` edges from the corresponding skill node to a PER-SKILL
      `external` node (one node per upstream skill, not one shared node per
      marketplace — a single node can't carry a resolvable `path` for 7
      different upstream files), for every entry that is NOT marked RETIRED.
      Each external node's `path` is the entry's recorded `Source` value
      with `/SKILL.md` appended and the home directory rewritten to `~` for
      machine portability — this is what lets skill-forge's drift checker
      (`node.path` ?? `node.url`) actually read and hash the upstream file
      instead of reporting every fork-of edge `upstream-unreachable`. See
      `parse_sources_md()` for the exact grammar. An entry whose skill
      directory no longer exists (and which isn't marked RETIRED) is a build
      ERROR, not a silent skip — see `PARSE GRAMMAR` below and
      `parse_sources_md()`.
      NEVER execute anything read from this file: it is parsed with plain
      string/regex operations only, never passed to a shell.
      An entry's optional `- **Upstream baseline:** sha256:<hex> (recorded
      YYYY-MM-DD)` field (written by `scripts/baseline_upstreams.py`, never by
      this compiler) becomes `baselineHash` on the per-skill external node.
      The corresponding skill node also gains `contentHashNormalized` —
      sha256 of its SKILL.md with the Rhize-injected `metadata.rhize`
      frontmatter textually stripped (`strip_rhize_metadata_block()`) — so a
      consumer (skill-forge's `watch`) can compute the three-way
      in-sync/local-only/upstream-moved/diverged verdict from data this
      compiler already emits, per
      docs/superpowers/specs/2026-08-10-three-way-drift-design.md.

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
  external:<marketplace-name>/<upstream-skill-path>
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"
CATALOG_PATH = REPO_ROOT / "catalog" / "skill-relations.json"
TAGS_PATH = REPO_ROOT / "catalog" / "tags.json"
OUTPUT_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
INDEXES_OUTPUT_PATH = REPO_ROOT / "generated" / "skill-map.indexes.json"
SCHEMA_VERSION = "1.1.0"

try:
    import yaml
except ImportError:  # pragma: no cover - environment-dependent
    yaml = None


class BuildError(Exception):
    """Raised for conditions the plan requires to be a hard build failure."""


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


def strip_rhize_metadata_block(raw: bytes) -> bytes:
    """Textually remove the Rhize-injected `metadata.rhize` frontmatter subtree.

    This is the ONE normalization implementation named by
    docs/superpowers/specs/2026-08-10-three-way-drift-design.md ("the 5-line
    tagging exclusion"): skill-forge compares hashes it is handed and never
    re-implements this stripping itself (the duplicated-validator lesson).

    Precise rule: within the '---'-delimited frontmatter block, find a
    top-level (zero-indent) `metadata:` line.
      - If `rhize` is metadata's ONLY immediate child key, remove the
        `metadata:` line and all of its indented children.
      - Otherwise, remove only the `rhize:` line and its own indented
        children (metadata's other children are untouched).
    Operates on raw text lines only — no YAML parsing, so formatting/comment
    changes elsewhere in the frontmatter are never silently absorbed. Returns
    `raw` unchanged if there is no frontmatter block, no top-level `metadata:`
    key, or no `rhize` child under it (nothing to strip).
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return raw
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        return raw
    fm_lines = lines[1:close_idx]

    def indent_of(s: str) -> int:
        return len(s) - len(s.lstrip(" "))

    meta_idx = None
    for i, line in enumerate(fm_lines):
        if re.match(r"^metadata:\s*$", line):
            meta_idx = i
            break
    if meta_idx is None:
        return raw

    end_idx = len(fm_lines)
    for j in range(meta_idx + 1, len(fm_lines)):
        line = fm_lines[j]
        if line.strip() == "":
            continue
        if indent_of(line) == 0:
            end_idx = j
            break
    children = fm_lines[meta_idx + 1 : end_idx]

    non_blank_children = [(idx, line) for idx, line in enumerate(children) if line.strip() != ""]
    if not non_blank_children:
        return raw
    min_indent = min(indent_of(line) for _, line in non_blank_children)
    immediate_keys = []
    for idx, line in non_blank_children:
        if indent_of(line) == min_indent:
            m = re.match(r"^\s*([A-Za-z0-9_-]+):", line)
            if m:
                immediate_keys.append((idx, m.group(1)))
    rhize_entries = [(idx, k) for idx, k in immediate_keys if k == "rhize"]
    if not rhize_entries:
        return raw

    if len(immediate_keys) == 1:
        new_fm_lines = fm_lines[:meta_idx] + fm_lines[end_idx:]
    else:
        rhize_local_idx = rhize_entries[0][0]
        rhize_indent = indent_of(children[rhize_local_idx])
        subtree_end = len(children)
        for k in range(rhize_local_idx + 1, len(children)):
            line = children[k]
            if line.strip() == "":
                continue
            if indent_of(line) <= rhize_indent:
                subtree_end = k
                break
        abs_start = meta_idx + 1 + rhize_local_idx
        abs_end = meta_idx + 1 + subtree_end
        new_fm_lines = fm_lines[:abs_start] + fm_lines[abs_end:]

    new_lines = [lines[0]] + new_fm_lines + lines[close_idx:]
    return "\n".join(new_lines).encode("utf-8")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9_.\-]+", "-", value.strip().lower()).strip("-")


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []

    def add_node(self, node: dict) -> None:
        node_id = node["id"]
        if node_id not in self.nodes:
            self.nodes[node_id] = node
            return
        # Merge: keep richer of the two (non-destructive union), but flag a
        # real conflict on differing values for the same key. This loop is a
        # no-op when the two definitions are already identical.
        existing = self.nodes[node_id]
        for k, v in node.items():
            if k in existing and existing[k] != v:
                raise BuildError(
                    f"conflicting node definitions for {node_id!r}: "
                    f"{k}={existing[k]!r} vs {v!r}"
                )
            existing[k] = v

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


def load_tags() -> dict[str, dict[str, str]]:
    """Load catalog/tags.json — the closed topic/stack/condition vocabulary —
    into {"topic": {slug: gloss}, "stack": {slug: gloss}, "condition": {slug: gloss}}.

    Condition entries additionally carry `patterns` (regexes matched against
    FAILED tool output); collected separately into `condition_patterns`
    ({slug: [pattern, ...]}) rather than folded into the gloss maps above, so
    callers that only need "is this slug known" (the topic/stack shape) don't
    have to special-case the extra field.
    """
    tags: dict[str, dict[str, str]] = {"topic": {}, "stack": {}, "condition": {}}
    condition_patterns: dict[str, list[str]] = {}
    for entry in json.loads(TAGS_PATH.read_text()):
        tags[entry["kind"]][entry["slug"]] = entry["gloss"]
        if entry["kind"] == "condition":
            condition_patterns[entry["slug"]] = list(entry.get("patterns") or [])
    tags["_condition_patterns"] = condition_patterns  # type: ignore[assignment]
    return tags


def load_condition_patterns() -> dict[str, list[str]]:
    """Standalone accessor for the condition->patterns map, for callers (the
    indexes builder) that don't otherwise need load_tags()'s full return."""
    patterns: dict[str, list[str]] = {}
    for entry in json.loads(TAGS_PATH.read_text()):
        if entry["kind"] == "condition":
            patterns[entry["slug"]] = list(entry.get("patterns") or [])
    return patterns


def load_skills(
    graph: Graph,
    plugin_name: str,
    plugin_dir: Path,
    tags: dict,
    extends_decls: list[dict],
    augments_decls: list[dict],
    remediates_decls: list[dict],
    depends_on_decls: list[dict],
) -> None:
    skills_dir = plugin_dir / "skills"
    if not skills_dir.is_dir():
        return
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue  # e.g. seo-aeo-geo/skills/shared/ has no SKILL.md
        skill_name = skill_dir.name
        raw = skill_md.read_bytes()
        content_hash = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8")
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
                "contentHash": content_hash,
            }
        )
        graph.add_edge(contains_edge(plugin_name, node_id))

        rhize_meta = (frontmatter.get("metadata") or {}).get("rhize") or {}
        topics = rhize_meta.get("topics") or []
        stacks = rhize_meta.get("stacks") or []
        for topic in topics:
            slug = slugify(str(topic))
            gloss = tags["topic"].get(slug)
            if gloss is None:
                raise BuildError(
                    f"{rel_path}: topic tag {topic!r} (slug {slug!r}) is not in "
                    "catalog/tags.json's closed vocabulary"
                )
            tag_id = f"tag:topic/{slug}"
            graph.add_node({"id": tag_id, "kind": "tag", "name": str(topic), "description": gloss})
            graph.add_edge(
                {
                    "from": node_id,
                    "to": tag_id,
                    "type": "topic-tag",
                    "source": "frontmatter",
                }
            )
        for stack in stacks:
            slug = slugify(str(stack))
            gloss = tags["stack"].get(slug)
            if gloss is None:
                raise BuildError(
                    f"{rel_path}: stack tag {stack!r} (slug {slug!r}) is not in "
                    "catalog/tags.json's closed vocabulary"
                )
            tag_id = f"tag:stack/{slug}"
            graph.add_node({"id": tag_id, "kind": "tag", "name": str(stack), "description": gloss})
            graph.add_edge(
                {
                    "from": node_id,
                    "to": tag_id,
                    "type": "stack-tag",
                    "source": "frontmatter",
                }
            )

        extends_targets = rhize_meta.get("extends") or []
        if extends_targets:
            extends_decls.append(
                {
                    "skill_id": node_id,
                    "plugin": plugin_name,
                    "targets": [str(t) for t in extends_targets],
                    "rel_path": rel_path,
                }
            )

        for topic in rhize_meta.get("augments") or []:
            slug = slugify(str(topic))
            gloss = tags["topic"].get(slug)
            if gloss is None:
                raise BuildError(
                    f"{rel_path}: augments target {topic!r} (slug {slug!r}) is not in "
                    "catalog/tags.json's closed topic vocabulary"
                )
            augments_decls.append({"skill_id": node_id, "slug": slug, "gloss": gloss})

        for condition in rhize_meta.get("remediates") or []:
            slug = slugify(str(condition))
            gloss = tags["condition"].get(slug)
            if gloss is None:
                raise BuildError(
                    f"{rel_path}: remediates target {condition!r} (slug {slug!r}) is not in "
                    "catalog/tags.json's closed condition vocabulary"
                )
            remediates_decls.append({"skill_id": node_id, "slug": slug, "gloss": gloss})

        for target in rhize_meta.get("dependsOn") or []:
            depends_on_decls.append(
                {
                    "skill_id": node_id,
                    "plugin": plugin_name,
                    "target": str(target),
                    "rel_path": rel_path,
                }
            )


def resolve_extends_edges(graph: Graph, extends_decls: list[dict]) -> None:
    """Resolve `metadata.rhize.extends` declarations into `extends` edges.

    Each target is either a bare skill name (resolved against the declaring
    skill's own plugin) or "plugin/skill-name" (cross-plugin). An unresolved
    target is a BuildError naming the declaring file and the target. Must run
    after every plugin's skills have been loaded, so cross-plugin targets are
    already present in the graph.
    """
    for decl in extends_decls:
        for target in decl["targets"]:
            if "/" in target:
                target_plugin, target_skill = target.split("/", 1)
            else:
                target_plugin, target_skill = decl["plugin"], target
            target_id = f"skill:{target_plugin}/{target_skill}"
            if target_id not in graph.nodes:
                raise BuildError(
                    f"{decl['rel_path']}: extends target {target!r} does not "
                    f"resolve to a known skill (looked for {target_id!r})"
                )
            graph.add_edge(
                {
                    "from": decl["skill_id"],
                    "to": target_id,
                    "type": "extends",
                    "source": "frontmatter",
                }
            )


def check_extends_chains(graph: Graph) -> None:
    """Enforce the extends-chain rules: depth capped at 2, no cycles.

    Depth is measured in edges from the starting skill: A -> B -> C is depth
    2 (allowed); A -> B -> C -> D is depth 3 (a BuildError). Reusing a node
    already on the current path is a cycle (also a BuildError).
    """
    adjacency: dict[str, list[str]] = collections.defaultdict(list)
    for edge in graph.edges:
        if edge["type"] == "extends":
            adjacency[edge["from"]].append(edge["to"])

    def walk(node: str, path: list[str]) -> None:
        if node in path:
            chain = " -> ".join(path + [node])
            raise BuildError(f"extends cycle detected: {chain}")
        if len(path) > 2:
            chain = " -> ".join(path + [node])
            raise BuildError(
                "extends chains capped at 2 — deep trees recreate rigid "
                f"taxonomy (chain: {chain})"
            )
        for target in sorted(adjacency.get(node, [])):
            walk(target, path + [node])

    for start in sorted(adjacency.keys()):
        walk(start, [])


def resolve_augments_edges(graph: Graph, augments_decls: list[dict]) -> None:
    """Resolve `metadata.rhize.augments` declarations into `augments` edges
    (skill -> tag:topic/<slug>). Slug validity against catalog/tags.json is
    already checked in load_skills(); this only mints the tag node (if not
    already present from a topic-tag edge) and the edge itself."""
    for decl in augments_decls:
        tag_id = f"tag:topic/{decl['slug']}"
        graph.add_node({"id": tag_id, "kind": "tag", "description": decl["gloss"]})
        graph.add_edge(
            {
                "from": decl["skill_id"],
                "to": tag_id,
                "type": "augments",
                "source": "frontmatter",
            }
        )


def resolve_remediates_edges(graph: Graph, remediates_decls: list[dict]) -> None:
    """Resolve `metadata.rhize.remediates` declarations into `remediates`
    edges (skill -> tag:condition/<slug>). Slug validity is already checked
    in load_skills()."""
    for decl in remediates_decls:
        tag_id = f"tag:condition/{decl['slug']}"
        graph.add_node({"id": tag_id, "kind": "tag", "description": decl["gloss"]})
        graph.add_edge(
            {
                "from": decl["skill_id"],
                "to": tag_id,
                "type": "remediates",
                "source": "frontmatter",
            }
        )


_MCP_TARGET_RE = re.compile(r"^mcp:(.+)$")


def resolve_depends_on_edges(graph: Graph, depends_on_decls: list[dict]) -> None:
    """Resolve `metadata.rhize.dependsOn` declarations into `depends-on`
    edges. Each target is either `mcp:<name>` (mints an `mcp-server` node if
    not already present) or a skill target using the same bare-name /
    "plugin/skill-name" resolution as `extends`. An unresolved skill target
    is a BuildError naming the declaring file and the target. Must run after
    every plugin's skills have been loaded, so cross-plugin targets are
    already present in the graph."""
    for decl in depends_on_decls:
        target = decl["target"]
        mcp_match = _MCP_TARGET_RE.match(target)
        if mcp_match:
            mcp_id = f"mcp:{mcp_match.group(1)}"
            graph.add_node({"id": mcp_id, "kind": "mcp-server", "name": mcp_match.group(1)})
            graph.add_edge(
                {
                    "from": decl["skill_id"],
                    "to": mcp_id,
                    "type": "depends-on",
                    "source": "frontmatter",
                }
            )
            continue

        if "/" in target:
            target_plugin, target_skill = target.split("/", 1)
        else:
            target_plugin, target_skill = decl["plugin"], target
        target_id = f"skill:{target_plugin}/{target_skill}"
        if target_id not in graph.nodes:
            raise BuildError(
                f"{decl['rel_path']}: dependsOn target {target!r} does not "
                f"resolve to a known skill or mcp:<name> (looked for {target_id!r})"
            )
        graph.add_edge(
            {
                "from": decl["skill_id"],
                "to": target_id,
                "type": "depends-on",
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
        for group in groups:
            matcher = group.get("matcher", "")
            for hook_entry in group.get("hooks", []):
                command = hook_entry.get("command", "")
                fallback = f"inline-{hashlib.sha256(command.encode()).hexdigest()[:8]}"
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
        # setup/manifest.json items are hooks in every plugin observed in
        # this repo (schema 1: {id, title, tier, event, matcher?, command,
        # description, default}). Restrict to items that look like a hook
        # (have an "event" field) so this stays correct if a future manifest
        # schema adds non-hook item kinds; the schema is where event
        # vocabulary would be policed, not this loader.
        if not item.get("event"):
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
#   - **Upstream baseline:** sha256:<hex> (recorded YYYY-MM-DD)  (OPTIONAL —
#     written/updated by scripts/baseline_upstreams.py, never by this
#     compiler; the reviewed-upstream-state anchor for the three-way drift
#     verdict, see docs/superpowers/specs/2026-08-10-three-way-drift-design.md)
#   - **Notes:** <value>
#   - **RETIRED <date>:** <text>     (OPTIONAL — only present if retired)
#
# Parsing rule: split the file on lines starting with "## ", each block's
# first line (after stripping "## ") up to " — " is the skill-name; the rest
# of the block is scanned line-by-line for "- **<Field>:** <value>" bullets.
# A block containing a bullet whose field name starts with "RETIRED" marks
# that entry retired — its skill is expected to no longer exist under
# rhize-context-manager/skills/, and no fork-of edge is emitted for it.
# A non-retired entry's "Source" value is expected to contain either:
#   (a) a local path: ".../marketplaces/<marketplace-name>/skills/<upstream-path>"
#   (b) an http(s) URL to the upstream SKILL.md, e.g.
#       "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/skills/<upstream-path>/SKILL.md"
# Either form mints a PER-SKILL `external:<marketplace-name>/<upstream-path>`
# node — not a single node shared by the whole marketplace — because the
# drift checker resolves an upstream file from the node's own `path`/`url`,
# and one node-level location can't serve every fork's distinct upstream
# file. For form (a) the node carries `path`: the raw "Source" value with
# "/SKILL.md" appended and the caller's home directory rewritten to "~"
# (portable across machines). For form (b) the node carries `url` instead of
# `path` (skill-forge's drift checker — src/gate/skillMapDrift.ts — reads
# `node.url ?? node.path` and fetches over HTTPS when the value looks like a
# URL): the raw "Source" value verbatim, since it already points at the file.
# Either way the fork-of edge's driftCheck.upstreamPath is the parsed
# <upstream-path>. If the "Source" value is neither a recognizable local
# marketplace path nor an http(s) URL, this is a BuildError (existing
# behavior) rather than silently emitting a location-less node — a genuinely
# unreachable upstream (e.g. the marketplace was since uninstalled, or a URL
# that 404s) is still recorded, just with a `path`/`url` that legitimately
# fails to resolve at drift-check time.
#
# SECURITY: this parser performs ONLY string splitting, regex matching, and
# URL parsing (urllib.parse, no network I/O). Nothing read from this file is
# ever passed to a shell, eval, or exec, and no request is made here.
_HEADING_RE = re.compile(r"^##\s+(.+?)\s+—\s+(.+)$")
_BULLET_RE = re.compile(r"^-\s+\*\*([^:*]+):\*\*\s*(.*)$")
_SOURCE_PATH_RE = re.compile(r"/marketplaces/([^/]+)/(?:.+/)?skills/(.+)$")
_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)
_BASELINE_HASH_RE = re.compile(r"^sha256:([a-f0-9]{64})\b")


def _parse_url_source(source_value: str) -> tuple[str, str]:
    """Derives (marketplace_name, upstream_path) from an http(s) Source URL.

    For a raw.githubusercontent.com URL — the shape produced when repointing
    a marketplace-cache fork upstream to its real remote — marketplace_name is
    "<owner>/<repo>" and upstream_path is the skill's path segment (mirroring
    the <upstream-path> a local marketplace path would yield, e.g.
    "context-fundamentals" from ".../skills/context-fundamentals/SKILL.md").
    Any other https(s) host falls back to using the URL's netloc as
    marketplace_name and its full path as upstream_path — still deterministic,
    just without the GitHub-specific trimming.
    """
    parsed = urlparse(source_value)
    parts = [p for p in parsed.path.split("/") if p]
    if parsed.netloc == "raw.githubusercontent.com" and len(parts) >= 3:
        owner, repo = parts[0], parts[1]
        rest = "/".join(parts[3:])  # drop owner, repo, branch
        skills_match = re.search(r"(?:^|/)skills/(.+?)(?:/SKILL\.md)?$", rest)
        upstream_path = skills_match.group(1) if skills_match else rest
        return f"{owner}/{repo}", upstream_path
    return parsed.netloc, parsed.path.lstrip("/")


def parse_sources_md(path: Path) -> list[dict]:
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


def load_sources_md(graph: Graph, plugin_name: str, plugin_dir: Path) -> None:
    plugin_skills_dir = plugin_dir / "skills"
    sources_path = plugin_skills_dir / "SOURCES.md"
    if not sources_path.is_file():
        return  # plugin has no fork-tracking file — nothing to do
    entries = parse_sources_md(sources_path)
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
        is_url = bool(_URL_SCHEME_RE.match(source_value))
        if is_url:
            marketplace_name, upstream_path = _parse_url_source(source_value)
            external_node = {
                "id": f"external:{marketplace_name}/{upstream_path}",
                "kind": "external",
                "name": skill_name,
                "url": source_value,
            }
        else:
            match = _SOURCE_PATH_RE.search(source_value)
            if not match:
                raise BuildError(
                    f"SOURCES.md entry {skill_name!r}: could not parse an "
                    f"upstream marketplace/skill path or URL out of Source={source_value!r}"
                )
            marketplace_name, upstream_path = match.group(1), match.group(2)
            upstream_skill_md = f"{source_value.rstrip('/')}/SKILL.md"
            home = str(Path.home())
            if upstream_skill_md.startswith(home):
                upstream_skill_md = "~" + upstream_skill_md[len(home):]
            external_node = {
                "id": f"external:{marketplace_name}/{upstream_path}",
                "kind": "external",
                "name": skill_name,
                "path": upstream_skill_md,
            }
        baseline_value = entry["fields"].get("Upstream baseline", "")
        baseline_match = _BASELINE_HASH_RE.match(baseline_value)
        if baseline_match:
            external_node["baselineHash"] = baseline_match.group(1)
        external_id = external_node["id"]
        graph.add_node(external_node)
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
                    "method": "content-hash",
                },
            }
        )
        normalized = strip_rhize_metadata_block((skill_dir / "SKILL.md").read_bytes())
        graph.add_node(
            {
                "id": skill_node_id,
                "contentHashNormalized": hashlib.sha256(normalized).hexdigest(),
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
    tags = load_tags()
    plugins = load_marketplace(graph)
    extends_decls: list[dict] = []
    augments_decls: list[dict] = []
    remediates_decls: list[dict] = []
    depends_on_decls: list[dict] = []
    for plugin in plugins:
        load_skills(
            graph, plugin["name"], plugin["dir"], tags,
            extends_decls, augments_decls, remediates_decls, depends_on_decls,
        )
        load_commands(graph, plugin["name"], plugin["dir"])
        load_hooks_json(graph, plugin["name"], plugin["dir"])
        load_manifest_hooks(graph, plugin["name"], plugin["dir"])
        load_sources_md(graph, plugin["name"], plugin["dir"])
    # Resolved after every plugin's skills are loaded so cross-plugin
    # "plugin/skill-name" targets are already present in the graph.
    resolve_extends_edges(graph, extends_decls)
    check_extends_chains(graph)
    resolve_augments_edges(graph, augments_decls)
    resolve_remediates_edges(graph, remediates_decls)
    resolve_depends_on_edges(graph, depends_on_decls)
    load_catalog(graph)
    return graph.to_document()


# ---------------------------------------------------------------------------
# Materialized indexes (generated/skill-map.indexes.json)
# ---------------------------------------------------------------------------
# Precomputes the flat lookups the router/disclosure/remediation/succession
# hooks need, mirroring the exact matching semantics those hooks already
# implement (rhize-context-manager/hooks/skill-router.js and
# session-disclosure.js as of schema 1.1) so a future refactor of those hooks
# to read this file instead of walking edges directly is a pure data swap.
#
#   router:      per-skill tag/name signal lists (skill-router.js's
#                tagEdgesByFrom + name-word signal) plus the extends
#                base/extender adjacency it uses for its tie-break. The hook
#                still owns the token-matching/scoring loop; this only saves
#                it from re-deriving signals from doc.edges every call.
#   disclosure:  per single stack slug, the folded base+extenders list
#                session-disclosure.js's relevantSkills() would compute for
#                a detectedStacks set containing only that one stack. A
#                caller with multiple detected stacks unions the per-stack
#                lists and re-sorts by matched-stack count, same as today.
#   remediation: condition slug -> {patterns, skills} — skills declared via
#                `remediates` edges, sorted by skill id (no declared ranking
#                signal exists yet; alphabetical is the deterministic
#                default until a promotion/ranking mechanism lands).
#   succession:  node id -> {precedes, follows} from declared `precedes`
#                edges. `follows` is always [] here — mined follows edges are
#                local-overlay-only (see build_local_skill_map.py) and are
#                merged in at ~/.claude/context-manager/skill-map.indexes.resolved.json.
def _skill_nodes(document: dict) -> dict[str, dict]:
    return {n["id"]: n for n in document["nodes"] if n["kind"] == "skill"}


def _tag_nodes(document: dict) -> dict[str, dict]:
    return {n["id"]: n for n in document["nodes"] if n["kind"] == "tag"}


def build_router_index(document: dict) -> dict:
    skills = _skill_nodes(document)
    tags = _tag_nodes(document)
    signals: dict[str, list[dict]] = {}
    extends_bases: dict[str, list[str]] = {}

    for edge in document["edges"]:
        if edge["type"] in ("topic-tag", "stack-tag") and edge["from"] in skills:
            tag = tags.get(edge["to"])
            if not tag:
                continue
            signals.setdefault(edge["from"], []).append(
                {"kind": "tag", "weight": 2, "label": str(tag.get("name") or tag["id"])}
            )
        elif edge["type"] == "extends" and edge["from"] in skills and edge["to"] in skills:
            extends_bases.setdefault(edge["from"], []).append(edge["to"])

    for skill_id, skill in skills.items():
        signals.setdefault(skill_id, []).append(
            {"kind": "name", "weight": 1, "label": skill["name"]}
        )
        signals[skill_id].sort(key=lambda s: (s["kind"], s["label"]))

    for bases in extends_bases.values():
        bases.sort()

    return {"signals": signals, "extendsBases": extends_bases}


def build_disclosure_index(document: dict) -> dict:
    skills = _skill_nodes(document)
    tags = _tag_nodes(document)

    matches_by_stack: dict[str, dict[str, set]] = {}  # stackSlug -> skillId -> set() (placeholder)
    stack_matches: dict[str, set[str]] = {}  # stackSlug -> set(skillId)
    for edge in document["edges"]:
        if edge["type"] != "stack-tag" or edge["from"] not in skills:
            continue
        tag = tags.get(edge["to"])
        if not tag:
            continue
        m = re.match(r"^tag:stack/(.+)$", tag["id"])
        if not m:
            continue
        stack_matches.setdefault(m.group(1), set()).add(edge["from"])

    extends_bases: dict[str, set[str]] = {}
    for edge in document["edges"]:
        if edge["type"] == "extends" and edge["from"] in skills and edge["to"] in skills:
            extends_bases.setdefault(edge["from"], set()).add(edge["to"])

    disclosure: dict[str, list[dict]] = {}
    for stack_slug, matched in stack_matches.items():
        deeper_by_base: dict[str, set[str]] = {}
        folded = set()
        for extender_id, bases in extends_bases.items():
            if extender_id not in matched:
                continue
            for base_id in bases:
                if base_id not in matched:
                    continue
                deeper_by_base.setdefault(base_id, set()).add(extender_id)
                folded.add(extender_id)
        entries = []
        for skill_id in sorted(matched):
            if skill_id in folded:
                continue
            deeper = sorted(deeper_by_base.get(skill_id, ()))
            entries.append({"skillId": skill_id, "deeper": deeper})
        disclosure[stack_slug] = entries

    return disclosure


def build_remediation_index(document: dict, condition_patterns: dict[str, list[str]]) -> dict:
    # Deliberately NOT restricted to kind=="skill": remediates edges may
    # originate from an `external` node representing a third-party
    # capability that isn't inventoried as a proper skill node (e.g. an ecc
    # build-resolver agent — see catalog/skill-relations.json). The
    # remediation surface cares about "what to suggest", not the node kind.
    remediation: dict[str, dict] = {
        slug: {"patterns": list(patterns), "skills": []}
        for slug, patterns in condition_patterns.items()
    }
    for edge in document["edges"]:
        if edge["type"] != "remediates":
            continue
        m = re.match(r"^tag:condition/(.+)$", edge["to"])
        if not m:
            continue
        slug = m.group(1)
        remediation.setdefault(slug, {"patterns": [], "skills": []})
        remediation[slug]["skills"].append(edge["from"])
    for entry in remediation.values():
        entry["skills"] = sorted(set(entry["skills"]))
    return remediation


def build_succession_index(document: dict) -> dict:
    node_ids = {n["id"] for n in document["nodes"]}
    succession: dict[str, dict] = {}
    for edge in document["edges"]:
        if edge["type"] != "precedes":
            continue
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            continue
        succession.setdefault(edge["from"], {"precedes": [], "follows": []})
        succession[edge["from"]]["precedes"].append(edge["to"])
        succession.setdefault(edge["to"], {"precedes": [], "follows": []})
    for entry in succession.values():
        entry["precedes"] = sorted(set(entry["precedes"]))
        entry["follows"] = sorted(set(entry["follows"]))
    return succession


def build_indexes(document: dict, condition_patterns: dict[str, list[str]]) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "router": build_router_index(document),
        "disclosure": build_disclosure_index(document),
        "remediation": build_remediation_index(document, condition_patterns),
        "succession": build_succession_index(document),
    }


def dump(document: dict) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# --install copies the built artifacts here for installed (non-checkout) plugin consumers; see docs/skill-map.md.
INSTALL_PATH = Path.home() / ".claude" / "context-manager" / "skill-map.static.json"
INSTALL_INDEXES_PATH = Path.home() / ".claude" / "context-manager" / "skill-map.indexes.json"


def main() -> int:
    args = sys.argv[1:]
    install = "--install" in args
    out_path = OUTPUT_PATH
    if "--out" in args:
        out_path = Path(args[args.index("--out") + 1])
    indexes_out_path = INDEXES_OUTPUT_PATH
    if "--indexes-out" in args:
        indexes_out_path = Path(args[args.index("--indexes-out") + 1])
    try:
        document = build()
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    text = dump(document)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)

    indexes = build_indexes(document, load_condition_patterns())
    indexes_text = dump(indexes)
    indexes_out_path.parent.mkdir(parents=True, exist_ok=True)
    indexes_out_path.write_text(indexes_text)

    node_kinds = collections.Counter(n["kind"] for n in document["nodes"])
    edge_types = collections.Counter(e["type"] for e in document["edges"])
    print(f"Wrote {out_path}")
    print(f"Wrote {indexes_out_path}")
    print(f"Nodes by kind: {json.dumps(node_kinds, sort_keys=True)}")
    print(f"Edges by type: {json.dumps(edge_types, sort_keys=True)}")
    if install:
        INSTALL_PATH.parent.mkdir(parents=True, exist_ok=True)
        INSTALL_PATH.write_text(text)
        INSTALL_INDEXES_PATH.write_text(indexes_text)
        print(f"Installed copy to {INSTALL_PATH}")
        print(f"Installed copy to {INSTALL_INDEXES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
