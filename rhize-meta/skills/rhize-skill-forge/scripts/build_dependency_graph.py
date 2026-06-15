#!/usr/bin/env python3
"""build_dependency_graph.py — Custom→resource dependency graph from `consumes:` edges.

Reads capability frontmatter across a skills-root (reusing index_skills.py) or an existing
registry.json, and emits a dependency graph: nodes (skills with tier/domain) and edges
(custom --consumes--> resource). Surfaces orphans (customs with no `consumes`), hot resources
(consumed by many), dangling edges (a `consumes` target that doesn't exist), and cycles.

This is Phase-2 substrate for the Skill Customizer & Organizer: metadata acted upon, no runtime
engine. See references/capability-schema.md.

Stdlib only.

Usage:
    python3 build_dependency_graph.py --skills-root <root> [--out graph.json] [--json]
    python3 build_dependency_graph.py --registry registry.json [--out graph.json] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index_skills  # noqa: E402  (same-dir sibling script, reused for scanning)


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def find_cycles(adj: dict) -> list:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    stack: list = []
    cycles: list = []

    def dfs(u: str) -> None:
        color[u] = GRAY
        stack.append(u)
        for v in adj.get(u, []):
            if v not in color:        # dangling target — not a node
                continue
            if color[v] == GRAY and v in stack:
                cycles.append(stack[stack.index(v):] + [v])
            elif color[v] == WHITE:
                dfs(v)
        color[u] = BLACK
        stack.pop()

    for n in list(adj):
        if color[n] == WHITE:
            dfs(n)
    return cycles


def build_graph(skills: list) -> dict:
    names = {s["name"] for s in skills}
    nodes = [{"id": s["name"], "tier": s.get("tier"), "domain": s.get("domain")} for s in skills]
    adj = {s["name"]: list(s.get("consumes") or []) for s in skills}

    edges, dangling = [], []
    incoming: dict = {n: 0 for n in names}
    for s in skills:
        for tgt in (s.get("consumes") or []):
            edges.append({"from": s["name"], "to": tgt})
            if tgt in names:
                incoming[tgt] += 1
            else:
                dangling.append({"from": s["name"], "to": tgt})

    orphans = [s["name"] for s in skills
               if (s.get("tier") == "custom") and not (s.get("consumes") or [])]
    hot = sorted(({"resource": n, "consumed_by": c} for n, c in incoming.items() if c > 0),
                 key=lambda r: r["consumed_by"], reverse=True)
    cycles = find_cycles(adj)

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "orphans": orphans,
        "hot_resources": hot,
        "dangling_edges": dangling,
        "cycles": cycles,
    }


def main() -> None:
    try:  # ASCII-locale safety for the human-readable output path (e.g. LANG=C cron)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Build the custom→resource dependency graph.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--skills-root", help="scan this root (via index_skills)")
    src.add_argument("--registry", help="read an existing registry.json from index_skills")
    ap.add_argument("--out", help="write graph JSON to this path")
    ap.add_argument("--json", action="store_true", help="print graph JSON to stdout")
    args = ap.parse_args()

    if args.registry:
        try:
            reg = json.loads(Path(os.path.expanduser(args.registry)).read_text(errors="ignore"))
        except Exception as e:  # noqa: BLE001
            fail(f"could not read registry: {e}")
        skills = reg.get("skills", [])
    else:
        root = Path(os.path.expanduser(args.skills_root)).resolve()
        if not root.is_dir():
            fail(f"skills-root not a directory: {root}")
        skills = index_skills.build_registry(root, {})["skills"]

    graph = build_graph(skills)

    if args.out:
        Path(os.path.expanduser(args.out)).write_text(json.dumps(graph, indent=2))
        print(f"✓ wrote graph ({graph['node_count']} nodes, {graph['edge_count']} edges) "
              f"to {args.out}", file=sys.stderr)

    if args.json:
        print(json.dumps(graph, indent=2))
        return

    print(f"Dependency graph: {graph['node_count']} nodes, {graph['edge_count']} edges")
    if graph["edges"]:
        print("\n  Edges (custom → resource):")
        for e in graph["edges"]:
            print(f"    {e['from']}  →  {e['to']}")
    if graph["hot_resources"]:
        print("\n  Hot resources (consumed by N customs):")
        for h in graph["hot_resources"]:
            print(f"    {h['consumed_by']}×  {h['resource']}")
    if graph["dangling_edges"]:
        print("\n  ⚠ Dangling edges (consumes a skill not in the set):")
        for d in graph["dangling_edges"]:
            print(f"    {d['from']}  →  {d['to']}  (missing)")
    if graph["cycles"]:
        print("\n  ⚠ Cycles (consumes should be acyclic):")
        for c in graph["cycles"]:
            print(f"    {' → '.join(c)}")
    if graph["orphans"]:
        print(f"\n  Custom skills with no declared `consumes` ({len(graph['orphans'])}):")
        for o in graph["orphans"][:30]:
            print(f"    - {o}")


if __name__ == "__main__":
    main()
