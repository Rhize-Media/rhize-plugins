#!/usr/bin/env python3
"""One command: build corpus, build the resolved index for a checkout, run the router, score.

  python3 evals/skill-map-routing/run.py                      # repo root checkout, results in ./out/
  python3 evals/skill-map-routing/run.py --checkout ../wt-x --out /tmp/x
  python3 evals/skill-map-routing/run.py --checkout ../wt-x --compare-to baseline.json
  python3 evals/skill-map-routing/run.py --check baseline.json --thresholds thresholds.json

The corpus (eval rows, probes) is always built from the repo that holds this harness, so
different checkouts are measured on identical prompts. Only the router index, tag catalog,
inference code and route-core come from --checkout.
Outputs in --out: corpus.json, rows.json, resolved_index.json, inferred_signals.json,
routes.json, results.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_corpus  # noqa: E402


def merged_rows(corpus: dict, long_path: Path, skill_ids: set[str]) -> list[dict]:
    rows = list(corpus["rows"])
    seen: set[str] = set()
    for r in json.loads(long_path.read_text(encoding="utf-8"))["rows"]:
        if r["id"] in seen:
            raise SystemExit(f"run.py: duplicate long-negative id {r['id']}")
        seen.add(r["id"])
        unknown = [a for a in r.get("acceptable", []) if a not in skill_ids]
        if unknown:
            raise SystemExit(f"run.py: {r['id']} lists unknown acceptable skill ids {unknown}")
        rows.append({
            "id": r["id"], "group": "long_negative", "source": "long_negatives.json", "prompt": r["prompt"],
            "target": None, "should_trigger": False, "authored": "author-written",
            "kind": r.get("kind"), "acceptable": sorted(r.get("acceptable", [])),
        })
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkout", default=str(HERE.parent.parent), help="checkout under test (default: repo root of this harness)")
    ap.add_argument("--out", default=str(HERE / "out"), help="output directory (default: evals/skill-map-routing/out, git-ignored)")
    ap.add_argument("--third-party", default=str(HERE / "third_party_snapshot.json"), help="snapshot JSON, or 'none'")
    ap.add_argument("--node", default=shutil.which("node") or "node")
    ap.add_argument("--compare-to", metavar="RESULTS", help="also print the route-change list against this results.json")
    ap.add_argument("--check", metavar="BASELINE", help="gate this run against a baseline results.json")
    ap.add_argument("--thresholds", default=str(HERE / "thresholds.json"))
    ap.add_argument("--strict-rows", action="store_true", help="(default; kept for compatibility)")
    ap.add_argument("--allow-row-drift", action="store_true", help="--check: warn instead of failing when the row set differs from the baseline")
    args = ap.parse_args(argv)

    co = Path(args.checkout).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    corpus = build_corpus.build(HERE.parent.parent)
    (out / "corpus.json").write_text(json.dumps(corpus, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    static = json.loads((HERE.parent.parent / "generated" / "skill-map.static.json").read_text(encoding="utf-8"))
    rows = merged_rows(corpus, HERE / "long_negatives.json", {n["id"] for n in static["nodes"] if n.get("kind") == "skill"})
    (out / "rows.json").write_text(json.dumps(rows, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    def run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.stderr.write(r.stdout + r.stderr)
            raise SystemExit(f"run.py: step failed: {' '.join(map(str, cmd[:3]))}")
        return r.stdout

    run([py, str(HERE / "make_resolved.py"), "--checkout", str(co), "--third-party", args.third_party,
         "--out", str(out / "resolved_index.json"), "--inferred-out", str(out / "inferred_signals.json")])
    run([args.node, str(HERE / "run_router.js"), str(co / "rhize-context-manager" / "hooks" / "lib" / "route-core.js"),
         str(out / "resolved_index.json"), str(out / "rows.json"), str(out / "routes.json")])

    cmd = [py, str(HERE / "score.py"), "--rows", str(out / "rows.json"), "--routes", str(out / "routes.json"),
           "--results", str(out / "results.json")]
    rc = subprocess.run(cmd).returncode
    if rc:
        return rc
    if args.compare_to:
        print()
        subprocess.run([py, str(HERE / "score.py"), "--compare", args.compare_to, str(out / "results.json")])
    if args.check:
        print()
        cmd = [py, str(HERE / "score.py"), "--check", args.check, "--thresholds", args.thresholds, "--results", str(out / "results.json")]
        if args.allow_row_drift:
            cmd.append("--allow-row-drift")
        return subprocess.run(cmd).returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
