#!/usr/bin/env python3
"""Embed the skill map into the viewer HTML template.

Usage: build_viewer.py [output.html] [--map PATH] [--indexes PATH] [--note TEXT]

Reads the machine-local resolved map (~/.claude/context-manager/
skill-map.resolved.json) when present — that view includes the third-party
ecosystem overlay — and falls back to this repo's committed
generated/skill-map.static.json otherwise. `--map` overrides both. Output
defaults to skill-graph-viewer.html in the current directory.

Besides the slimmed node/edge payload, the template receives a small META
object (build date, data source, optional note) shown in the header/legend.
"""
import argparse
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RESOLVED = os.path.expanduser("~/.claude/context-manager/skill-map.resolved.json")
STATIC = os.path.join(HERE, "..", "..", "generated", "skill-map.static.json")
RESOLVED_INDEXES = os.path.expanduser("~/.claude/context-manager/skill-map.indexes.resolved.json")
MARKETPLACE = os.path.join(HERE, "..", "..", ".claude-plugin", "marketplace.json")

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("out", nargs="?", default="skill-graph-viewer.html")
ap.add_argument("--map", dest="map_path", help="skill-map JSON to embed (default: resolved, else static)")
ap.add_argument("--indexes", dest="indexes_path",
                help="resolved indexes JSON for inferred third-party tag edges (default: the machine-local one if present)")
ap.add_argument("--note", help="extra provenance line shown under the legend")
args = ap.parse_args()

map_path = args.map_path or (RESOLVED if os.path.exists(RESOLVED) else STATIC)
with open(map_path) as fh:
    doc = json.load(fh)

# Slim payload: keep only fields the viewer uses.
NODE_FIELDS = ("id", "kind", "name", "plugin", "description", "origin", "thirdPartyPlugin")
nodes = [{k: n.get(k) for k in NODE_FIELDS if n.get(k) is not None} for n in doc["nodes"]]
edges = [{k: e.get(k) for k in ("from", "to", "type", "source") if e.get(k) is not None}
         for e in doc["edges"]]

# Inferred router tags for third-party skills live only in the resolved indexes
# (build_local_skill_map.py), not as map edges. Surface them as viewer-only
# `tag-inferred` edges so the viewer shows how third-party skills reach the
# router. Missing/unreadable indexes simply mean no such edges.
indexes_path = args.indexes_path or (RESOLVED_INDEXES if os.path.exists(RESOLVED_INDEXES) else None)
if indexes_path:
    try:
        with open(indexes_path) as fh:
            signals = json.load(fh).get("router", {}).get("signals", {})
    except (OSError, ValueError, AttributeError):
        signals = {}
    node_ids = {n["id"] for n in nodes}
    tag_by_slug = {n["name"]: n["id"] for n in nodes if n["kind"] == "tag" and isinstance(n.get("name"), str)}
    for skill_id, sigs in sorted(signals.items()):
        if skill_id not in node_ids or not isinstance(sigs, list):
            continue
        for sig in sigs:
            if isinstance(sig, dict) and sig.get("kind") == "tag-inferred" and sig.get("label") in tag_by_slug:
                edges.append({"from": skill_id, "to": tag_by_slug[sig["label"]], "type": "tag-inferred", "source": "inferred"})

payload = json.dumps({"nodes": nodes, "edges": edges}, separators=(",", ":"))

source = "resolved map" if os.path.abspath(map_path) == os.path.abspath(RESOLVED) else os.path.basename(map_path)
meta = {"built": datetime.date.today().isoformat(), "source": source}
try:
    with open(MARKETPLACE) as fh:
        meta["marketplace"] = json.load(fh)["name"]
except (OSError, ValueError, KeyError):
    pass
if args.note:
    meta["note"] = args.note
# Escape "</" so a description can never close the inline <script> early.
meta_json = json.dumps(meta, separators=(",", ":")).replace("</", "<\\/")
payload = payload.replace("</", "<\\/")

with open(os.path.join(HERE, "viewer-template.html")) as fh:
    template = fh.read()
out = template.replace("/*__SKILL_MAP_DATA__*/", payload).replace("/*__SKILL_MAP_META__*/null", meta_json)
with open(args.out, "w") as fh:
    fh.write(out)
print(f"wrote {args.out} ({len(out)//1024} KB, {len(nodes)} nodes, {len(edges)} edges) from {os.path.relpath(map_path)}")
