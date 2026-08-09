#!/usr/bin/env python3
"""build_local_skill_map.py — machine-local overlay + resolved skill map.

Phase 3 ("local overlay") of the skill-map-graph-substrate plan
(.claude/plans/skill-map-graph-substrate.md). Joins three machine-local,
optional inputs against the committed static artifact
(generated/skill-map.static.json) and writes two files under
~/.claude/context-manager/ (gitignored, never committed):

  - skill-map.local.json     — overlay facts only: enabled-plugin set, stack
                                config fingerprint, usage-cooccurs edges.
  - skill-map.resolved.json  — the merged consumer view (static + overlay)
                                that skill-router.js and /start read.

Inputs (each optional; a missing input degrades that piece of the overlay
and is noted in local.json's `sourceNotes` — it never fails the build):

  1. Enabled-plugin set — `~/.claude/plugins/installed_plugins.json`
     (version 2 shape: {"plugins": {"<name>@<marketplace>": [{"scope",
     "projectPath", ...}]}}). A plugin from this repo's own
     .claude-plugin/marketplace.json is "enabled" if it has an install
     entry with scope "user" (applies everywhere) or a "project" entry
     whose projectPath resolves to this repo. If the file is missing or
     unreadable, ALL of this repo's plugins are treated as enabled and the
     degradation is recorded in `sourceNotes.enabledPlugins`.

  2. Stack config — `~/.claude/rhize-context-manager/stack.config.json`
     (schemaVersion 2, written by /context-setup). We only need a cheap
     drift signal here, not the full layer inventory, so we record a
     sha256 fingerprint of the file plus this repo's `repoOverrides` entry
     (keyed by this repo's directory basename) if present.

  3. Usage co-occurrence — rhize-ops/skill-monitor's
     data/skill-cooccurrence.json (see monitor.py's build_cooccurrence()).
     Counts-only: {windowDays, totalSessions, pairs: [{a, b, sessions}],
     totals: {skill: sessions}}. Pair endpoints are "<plugin>:<skill>"
     (monitor's raw Skill-tool name) or a bare name for user-level skills
     outside any plugin. Only pairs where BOTH endpoints resolve to a
     `skill:<plugin>/<name>` node already present in the static artifact
     become `usage-cooccurs` edges — monitor observes skill usage across
     ALL of this machine's repos, most of which aren't in this map.

Resolved-map construction:
  resolved.nodes = static.nodes, unchanged.
  resolved.edges = static.edges + any usage-cooccurs edges derived above.
  No node is mutated (e.g. no "enabled" annotation) — this is what makes
  the "missing input degrades cleanly" contract exact: if the
  co-occurrence snapshot is absent, resolved.json is byte-for-byte
  equivalent (content-wise) to the static artifact.

Determinism: given identical inputs, two runs produce identical output.
Edges are sorted the same way build_skill_map.py's Graph.to_document()
sorts them; JSON is dumped with sort_keys=True and a trailing newline.

Usage:
  python3 scripts/build_local_skill_map.py
  python3 scripts/build_local_skill_map.py --out-dir <dir>        # override
      # ~/.claude/context-manager (used by tests with a fake HOME)
  python3 scripts/build_local_skill_map.py --static <path>        # override
      # generated/skill-map.static.json (used by tests with a fixture)
  python3 scripts/build_local_skill_map.py --cooccurrence <path>  # override
      # rhize-ops/skill-monitor/data/skill-cooccurrence.json
  python3 scripts/build_local_skill_map.py --installed-plugins <path>
  python3 scripts/build_local_skill_map.py --stack-config <path>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"
DEFAULT_STATIC_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
DEFAULT_COOCCURRENCE_PATH = (
    REPO_ROOT / "rhize-ops" / "skill-monitor" / "data" / "skill-cooccurrence.json"
)


def default_installed_plugins_path() -> Path:
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def default_stack_config_path() -> Path:
    return Path.home() / ".claude" / "rhize-context-manager" / "stack.config.json"


def default_out_dir() -> Path:
    return Path.home() / ".claude" / "context-manager"


def _load_json(path: Path) -> tuple[dict | None, str | None]:
    """Return (data, error). error is None on success."""
    if not path.is_file():
        return None, f"{path} not found"
    try:
        return json.loads(path.read_text()), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{path} unreadable: {exc}"


def resolve_enabled_plugins(
    marketplace_name: str,
    repo_plugin_names: list[str],
    installed_plugins_path: Path,
) -> tuple[set[str], str]:
    """Return (enabled_set, note). Degrades to "all enabled" on any failure."""
    data, err = _load_json(installed_plugins_path)
    if err:
        return set(repo_plugin_names), f"degraded: {err} — treating all repo plugins as enabled"

    plugins = data.get("plugins", {}) if isinstance(data, dict) else {}
    enabled: set[str] = set()
    for name in repo_plugin_names:
        pid = f"{name}@{marketplace_name}"
        installs = plugins.get(pid)
        if not isinstance(installs, list):
            continue
        for install in installs:
            scope = install.get("scope")
            if scope == "user":
                enabled.add(name)
                break
            if scope == "project":
                project_path = install.get("projectPath")
                if project_path and Path(project_path).resolve() == REPO_ROOT:
                    enabled.add(name)
                    break
    return enabled, f"read from {installed_plugins_path}"


def resolve_stack_fingerprint(stack_config_path: Path) -> tuple[dict | None, str]:
    data, err = _load_json(stack_config_path)
    if err:
        return None, f"degraded: {err} — no stack overlay applied"
    raw = stack_config_path.read_bytes()
    fingerprint = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "repoOverrides": (data.get("repoOverrides", {}) or {}).get(REPO_ROOT.name),
    }
    return fingerprint, f"read from {stack_config_path}"


# monitor.py's co-occurrence snapshot uses windowDays == 0 to mean "all-time"
# (`--days 0`), but the schema's usageWeight.windowDays has a minimum of 1
# (it measures the size of a rolling window). This sentinel represents
# "unbounded" without violating the schema; scheduled runs use a bounded
# window in practice (see rhize-ops/skill-monitor's weekly-skill-audit task).
ALL_TIME_WINDOW_SENTINEL = 36500  # ~100 years


def _skill_id_from_monitor_name(name: str) -> str:
    """Convert a monitor skill name ("<plugin>:<skill>" or a bare user-level
    name) into a skill-map node id ("skill:<plugin>/<skill>"). Bare names
    (no ':') don't belong to any plugin in this repo and never match a
    static node — they're filtered out by the caller, not here."""
    plugin, _, skill = name.partition(":")
    return f"skill:{plugin}/{skill}" if skill else f"skill:{plugin}"


def build_usage_edges(
    cooccurrence_path: Path,
    static_skill_ids: set[str],
) -> tuple[list[dict], dict | None, str]:
    """Return (edges, snapshot_summary, note). Degrades to (no edges) on any
    failure or when a pair's endpoints don't resolve to nodes in the static
    artifact (monitor observes usage across every repo on the machine, not
    just this one)."""
    data, err = _load_json(cooccurrence_path)
    if err:
        return [], None, f"degraded: {err} — no usage-cooccurs edges added"

    window_days = data.get("windowDays") or 0
    total_sessions = data.get("totalSessions") or 0
    totals = data.get("totals") or {}
    pairs = data.get("pairs") or []

    edges: list[dict] = []
    for pair in pairs:
        a_name, b_name = pair.get("a"), pair.get("b")
        sessions_ab = pair.get("sessions") or 0
        if not a_name or not b_name or sessions_ab <= 0:
            continue
        a_id = _skill_id_from_monitor_name(a_name)
        b_id = _skill_id_from_monitor_name(b_name)
        if a_id not in static_skill_ids or b_id not in static_skill_ids:
            continue

        sessions_a = totals.get(a_name) or 0
        sessions_b = totals.get(b_name) or 0
        denom = sessions_a + sessions_b - sessions_ab
        jaccard = round(sessions_ab / denom, 4) if denom > 0 else 0.0
        lift = (
            round((sessions_ab * total_sessions) / (sessions_a * sessions_b), 4)
            if sessions_a > 0 and sessions_b > 0 and total_sessions > 0
            else 0.0
        )

        from_id, to_id = sorted((a_id, b_id))
        edges.append(
            {
                "from": from_id,
                "to": to_id,
                "type": "usage-cooccurs",
                "source": "monitor",
                "usageWeight": {
                    "sessions": sessions_ab,
                    "jaccard": jaccard,
                    "lift": lift,
                    "windowDays": window_days if window_days > 0 else ALL_TIME_WINDOW_SENTINEL,
                },
            }
        )

    edges.sort(key=lambda e: (e["from"], e["to"]))
    summary = {
        "windowDays": window_days,
        "totalSessions": total_sessions,
        "pairsConsidered": len(pairs),
        "edgesResolved": len(edges),
    }
    return edges, summary, f"read from {cooccurrence_path}"


def build(
    static_path: Path,
    installed_plugins_path: Path,
    stack_config_path: Path,
    cooccurrence_path: Path,
) -> tuple[dict, dict]:
    """Return (local_doc, resolved_doc)."""
    static_doc = json.loads(static_path.read_text())
    marketplace = json.loads(MARKETPLACE_PATH.read_text())
    marketplace_name = marketplace["name"]
    repo_plugin_names = sorted(p["name"] for p in marketplace["plugins"])

    enabled_plugins, enabled_note = resolve_enabled_plugins(
        marketplace_name, repo_plugin_names, installed_plugins_path
    )
    stack_fingerprint, stack_note = resolve_stack_fingerprint(stack_config_path)

    static_skill_ids = {n["id"] for n in static_doc["nodes"] if n["kind"] == "skill"}
    usage_edges, cooc_summary, cooc_note = build_usage_edges(
        cooccurrence_path, static_skill_ids
    )

    generated_at = datetime.now(timezone.utc).isoformat()

    local_doc = {
        "generatedAt": generated_at,
        "enabledPlugins": sorted(enabled_plugins),
        "stack": stack_fingerprint,
        "usageCooccursEdges": usage_edges,
        "cooccurrenceSummary": cooc_summary,
        "sourceNotes": {
            "enabledPlugins": enabled_note,
            "stack": stack_note,
            "cooccurrence": cooc_note,
        },
    }

    resolved_doc = {
        "schemaVersion": static_doc["schemaVersion"],
        "nodes": static_doc["nodes"],
        "edges": static_doc["edges"] + usage_edges,
    }

    return local_doc, resolved_doc


def dump(document: dict) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--static", default=str(DEFAULT_STATIC_PATH))
    ap.add_argument("--installed-plugins", default=None,
                     help="default: ~/.claude/plugins/installed_plugins.json")
    ap.add_argument("--stack-config", default=None,
                     help="default: ~/.claude/rhize-context-manager/stack.config.json")
    ap.add_argument("--cooccurrence", default=str(DEFAULT_COOCCURRENCE_PATH))
    ap.add_argument("--out-dir", default=None,
                     help="default: ~/.claude/context-manager")
    args = ap.parse_args()

    static_path = Path(args.static)
    installed_plugins_path = (
        Path(args.installed_plugins) if args.installed_plugins
        else default_installed_plugins_path()
    )
    stack_config_path = (
        Path(args.stack_config) if args.stack_config else default_stack_config_path()
    )
    cooccurrence_path = Path(args.cooccurrence)
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir()

    if not static_path.is_file():
        print(f"ERROR: static artifact not found at {static_path}", file=sys.stderr)
        print("  run scripts/build_skill_map.py first", file=sys.stderr)
        return 1

    local_doc, resolved_doc = build(
        static_path, installed_plugins_path, stack_config_path, cooccurrence_path
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    local_path = out_dir / "skill-map.local.json"
    resolved_path = out_dir / "skill-map.resolved.json"
    local_path.write_text(dump(local_doc))
    resolved_path.write_text(dump(resolved_doc))

    print(f"Wrote {local_path}")
    print(f"Wrote {resolved_path}")
    print(f"Enabled plugins: {local_doc['enabledPlugins']}")
    print(f"Usage-cooccurs edges: {len(local_doc['usageCooccursEdges'])}")
    for key, note in local_doc["sourceNotes"].items():
        print(f"  [{key}] {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
