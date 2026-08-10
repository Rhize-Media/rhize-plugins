#!/usr/bin/env python3
"""query_skill_map.py — interpreter for catalog/queries.json's declarative walk specs.

Second tier of the skill-map's two-tier query layer (skill-map-relationships-v2
design, decision 6). The first tier — generated/skill-map.indexes.json — is a
materialized view for the hot paths (router, disclosure, remediation,
succession) that hook code reads directly, no traversal logic in hook code.
This script is the second tier: everything else, expressed as named
declarative queries in catalog/queries.json and interpreted by ONE walker
here. Hooks never use this script (Node hooks would have to shell out to
Python, which the router/disclosure hooks explicitly avoid); it's a
developer/audit-time CLI.

Usage:
  python3 scripts/query_skill_map.py <name> [arg]
  python3 scripts/query_skill_map.py <name> [arg] --resolved
  python3 scripts/query_skill_map.py --list

  --resolved reads ~/.claude/context-manager/skill-map.resolved.json instead
  of generated/skill-map.static.json — required for what-follows (follows
  edges are local-overlay only) and useful for anything touching third-party
  nodes.

Spec shape (see catalog/queries.json):
  {"arg": "<argName>", "normalizeArg": "<mode>", "steps": [{"edge", "direction", "as"}, ...]}
    -> resolves `arg` to a start node id (see normalize_arg()), then for each
       step walks every edge of `edge` type in the given `direction` ("out":
       edge.from == start, "in": edge.to == start) and collects the OTHER
       endpoint under the `as` key.
  {"listEdges": "<edgeType>"}
    -> dumps every edge of that type as {"from", "to"} pairs.
  {"kind": "unroutable"}
    -> skills with no outgoing topic-tag or stack-tag edge.

Output: JSON to stdout. Exit 1 on a missing map or unknown query name.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
QUERIES_PATH = REPO_ROOT / "catalog" / "queries.json"
STATIC_MAP_PATH = REPO_ROOT / "generated" / "skill-map.static.json"
RESOLVED_MAP_PATH = Path.home() / ".claude" / "context-manager" / "skill-map.resolved.json"


def load_queries() -> dict:
    return json.loads(QUERIES_PATH.read_text())["queries"]


def load_map(resolved: bool) -> dict:
    path = RESOLVED_MAP_PATH if resolved else STATIC_MAP_PATH
    if not path.is_file():
        print(f"ERROR: map not found at {path}", file=sys.stderr)
        if resolved:
            print("  run scripts/build_local_skill_map.py first", file=sys.stderr)
        else:
            print("  run scripts/build_skill_map.py first", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text())


def normalize_arg(raw: str | None, mode: str | None) -> str | None:
    """Turn a bare CLI argument into a full node id per the query's
    `normalizeArg` mode. A value already containing ':' is assumed to
    already be a full node id and is passed through unchanged."""
    if raw is None or ":" in raw:
        return raw
    if mode == "skillId":
        return f"skill:{raw}" if "/" in raw else raw
    if mode == "tagConditionId":
        return f"tag:condition/{raw}"
    if mode == "mcpId":
        return f"mcp:{raw}"
    return raw


def run_steps(doc: dict, start_id: str, steps: list[dict]) -> dict:
    result: dict[str, list[str]] = {}
    for step in steps:
        edge_type, direction, key = step["edge"], step["direction"], step["as"]
        matches = []
        for edge in doc.get("edges", []):
            if edge.get("type") != edge_type:
                continue
            if direction == "out" and edge.get("from") == start_id:
                matches.append(edge["to"])
            elif direction == "in" and edge.get("to") == start_id:
                matches.append(edge["from"])
        result[key] = sorted(set(matches))
    return result


def run_list_edges(doc: dict, edge_type: str) -> list[dict]:
    pairs = [
        {"from": e["from"], "to": e["to"]}
        for e in doc.get("edges", [])
        if e.get("type") == edge_type
    ]
    pairs.sort(key=lambda p: (p["from"], p["to"]))
    return pairs


def run_unroutable(doc: dict) -> list[str]:
    skill_ids = {n["id"] for n in doc.get("nodes", []) if n.get("kind") == "skill"}
    routable = {
        e["from"]
        for e in doc.get("edges", [])
        if e.get("type") in ("topic-tag", "stack-tag") and e.get("from") in skill_ids
    }
    return sorted(skill_ids - routable)


def run_query(doc: dict, name: str, spec: dict, arg: str | None) -> dict:
    if "listEdges" in spec:
        return {"query": name, "edges": run_list_edges(doc, spec["listEdges"])}
    if spec.get("kind") == "unroutable":
        return {"query": name, "unroutableSkills": run_unroutable(doc)}

    arg_name = spec.get("arg")
    if arg_name and not arg:
        raise SystemExit(f"query {name!r} requires an argument ({arg_name})")
    start_id = normalize_arg(arg, spec.get("normalizeArg"))
    steps = spec.get("steps", [])
    out = {"query": name, "arg": start_id}
    out.update(run_steps(doc, start_id, steps))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", help="query name from catalog/queries.json")
    ap.add_argument("arg", nargs="?", default=None, help="query argument, if the query needs one")
    ap.add_argument("--resolved", action="store_true", help="read skill-map.resolved.json instead of the static artifact")
    ap.add_argument("--list", action="store_true", help="list available query names and exit")
    args = ap.parse_args()

    queries = load_queries()

    if args.list or not args.name:
        for name, spec in sorted(queries.items()):
            print(f"{name}: {spec.get('description', '')}")
        return 0

    if args.name not in queries:
        print(f"ERROR: unknown query {args.name!r}. Use --list to see available queries.", file=sys.stderr)
        return 1

    doc = load_map(args.resolved)
    try:
        result = run_query(doc, args.name, queries[args.name], args.arg)
    except SystemExit as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
