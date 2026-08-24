#!/usr/bin/env python3
"""Embed the skill map into the viewer HTML template.

Usage: build_viewer.py [output.html]

Reads the machine-local resolved map (~/.claude/context-manager/
skill-map.resolved.json) when present — that view includes the third-party
ecosystem overlay — and falls back to this repo's committed
generated/skill-map.static.json otherwise. Output defaults to
skill-graph-viewer.html in the current directory.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESOLVED = os.path.expanduser("~/.claude/context-manager/skill-map.resolved.json")
STATIC = os.path.join(HERE, "..", "..", "generated", "skill-map.static.json")

map_path = RESOLVED if os.path.exists(RESOLVED) else STATIC
doc = json.load(open(map_path))

# Slim payload: keep only fields the viewer uses.
nodes = [{k: n.get(k) for k in ("id", "kind", "name", "plugin", "description", "origin") if n.get(k) is not None}
         for n in doc["nodes"]]
edges = [{k: e.get(k) for k in ("from", "to", "type", "source") if e.get(k) is not None}
         for e in doc["edges"]]
payload = json.dumps({"nodes": nodes, "edges": edges}, separators=(",", ":"))

template = open(os.path.join(HERE, "viewer-template.html")).read()
out = template.replace("/*__SKILL_MAP_DATA__*/", payload)
out_path = sys.argv[1] if len(sys.argv) > 1 else "skill-graph-viewer.html"
open(out_path, "w").write(out)
print(f"wrote {out_path} ({len(out)//1024} KB, {len(nodes)} nodes, {len(edges)} edges) from {os.path.relpath(map_path)}")
