#!/usr/bin/env python3
"""Build a resolved router index (static router + third-party skills) and inferred_signals.json.

The static index (generated/skill-map.indexes.json) only knows this repo's skills.
On a real machine the resolved index also carries every installed third-party
skill: a name signal plus up to 3 half-weight `tag-inferred` signals chosen by
build_local_skill_map.py's `_inferred_by_skill` against catalog/tags.json. This
script reproduces that from a point-in-time third-party snapshot so the result
does not depend on the machine running it. The inference code and the tag
catalog are loaded from the checkout under test, so tag changes show up.

Usage:
  python3 make_resolved.py --checkout PATH [--third-party third_party_snapshot.json] \
      --out resolved_index.json --inferred-out inferred_signals.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SNAPSHOT = HERE / "third_party_snapshot.json"


def load_blm(path: Path):
    spec = importlib.util.spec_from_file_location("build_local_skill_map_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def load_third_party(path: Path | None) -> list[dict]:
    if path is None:
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    nodes = doc if isinstance(doc, list) else doc.get("nodes", [])
    # A snapshot may keep or drop `origin`; when present it must say third-party.
    return [n for n in nodes if isinstance(n, dict) and n.get("origin", "third-party") == "third-party"]


def build(checkout: Path, indexes: Path, tags: Path, blm_path: Path, snapshot: Path | None):
    blm = load_blm(blm_path)
    idx = json.loads(indexes.read_text(encoding="utf-8"))
    if hasattr(blm, "load_tags_catalog"):
        catalog, _note = blm.load_tags_catalog(tags)
    else:
        catalog = json.loads(tags.read_text(encoding="utf-8"))
    signals = {sid: list(sigs) for sid, sigs in idx["router"]["signals"].items()}
    inferred: dict[str, list[str]] = {}
    for sid, name, inf in blm._inferred_by_skill(load_third_party(snapshot), catalog):
        signals[sid] = [{"kind": "name", "weight": 1, "label": name}] + [
            {"kind": "tag-inferred", "weight": 0.5, "label": s} for s in inf
        ]
        inferred[sid] = sorted(inf)
    resolved = {"router": {"signals": signals, "extendsBases": idx["router"].get("extendsBases", {})}}
    return resolved, dict(sorted(inferred.items()))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkout", default=str(HERE.parent.parent), help="checkout under test (default: this repo)")
    ap.add_argument("--indexes", help="static indexes file (default: <checkout>/generated/skill-map.indexes.json)")
    ap.add_argument("--tags", help="tag catalog (default: <checkout>/catalog/tags.json)")
    ap.add_argument("--blm", help="build_local_skill_map.py (default: <checkout>/rhize-context-manager/scripts/build_local_skill_map.py)")
    ap.add_argument("--third-party", default=str(DEFAULT_SNAPSHOT), help="third-party snapshot JSON; 'none' to skip")
    ap.add_argument("--out", required=True, help="resolved index output")
    ap.add_argument("--inferred-out", required=True, help="skill -> sorted inferred slugs output")
    args = ap.parse_args(argv)
    co = Path(args.checkout).resolve()
    snap = None if args.third_party == "none" else Path(args.third_party)
    resolved, inferred = build(
        co,
        Path(args.indexes) if args.indexes else co / "generated" / "skill-map.indexes.json",
        Path(args.tags) if args.tags else co / "catalog" / "tags.json",
        Path(args.blm) if args.blm else co / "rhize-context-manager" / "scripts" / "build_local_skill_map.py",
        snap,
    )
    Path(args.out).write_text(json.dumps(resolved, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    Path(args.inferred_out).write_text(json.dumps(inferred, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    n_inf = sum(1 for v in inferred.values() if v)
    print(f"resolved index: {len(resolved['router']['signals'])} skills ({len(inferred)} third-party, {n_inf} with inferred tags)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
