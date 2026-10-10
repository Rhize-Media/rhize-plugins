#!/usr/bin/env python3
"""Score router output, compare runs, and gate against a baseline.

  score.py --rows rows.json --routes routes.json [--results results.json]
        Score one run: prints a table and writes results.json.
  score.py --compare A.json B.json
        Route-change list between two results.json files (plus metric deltas).
  score.py --compare-inferred A.json B.json
        Diff two inferred_signals.json files (third-party recall proxy).
  score.py --check baseline.json --thresholds thresholds.json [--results current.json | --rows ... --routes ...]
        Exit 1 when any gate fails.

Outcome definitions
  eval/probe positive   hit (routed to target) | wrong (routed elsewhere) | silent
  eval negative         false_trigger (routed to the target it must not trigger)
                        other_cross_plugin (routed to a skill in a DIFFERENT plugin than the target)
                        other_same_plugin (routed to a sibling in the target's plugin; usually the
                          intended route, so it is reported but never treated as wrong)
                        silent
  long negative         fire (routed to a skill not listed in the row's `acceptable`)
                        acceptable (routed to a listed skill) | silent
"""
from __future__ import annotations

import argparse
import hashlib
import json
import operator
import sys
from pathlib import Path

POS_KEYS = ("hit", "wrong", "silent")
NEG_KEYS = ("false_trigger", "other_cross_plugin", "other_same_plugin", "silent")


def plugin_of(skill_id: str | None) -> str | None:
    if not skill_id or not skill_id.startswith("skill:"):
        return None
    parts = skill_id[len("skill:"):].split("/")
    if len(parts) == 2:
        return parts[0]
    if len(parts) == 3:  # skill:<marketplace>/<plugin>/<name> -> third-party plugin
        return f"3p:{parts[1]}"
    return None


def load_rows(path: Path) -> list[dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, list) else doc["rows"]


def rows_sha(rows: list[dict]) -> str:
    canon = [
        [r["id"], r["group"], r["prompt"], r.get("target"), bool(r.get("should_trigger")), sorted(r.get("acceptable", []))]
        for r in sorted(rows, key=lambda r: r["id"])
    ]
    return hashlib.sha256(json.dumps(canon, sort_keys=True).encode()).hexdigest()[:16]


def classify(row: dict, top: str | None) -> str:
    g = row["group"]
    if g == "long_negative":
        if top is None:
            return "silent"
        return "acceptable" if top in row.get("acceptable", []) else "fire"
    if row["should_trigger"]:
        return "silent" if top is None else ("hit" if top in (row.get("targets") or [row["target"]]) else "wrong")
    if top is None:
        return "silent"
    if top == row["target"]:
        return "false_trigger"
    return "other_same_plugin" if plugin_of(top) == plugin_of(row["target"]) else "other_cross_plugin"


def bucket(row: dict) -> str:
    if row["group"] == "long_negative":
        return "long_negatives"
    if row["group"] == "probe":
        return "probes"
    return "eval_positives" if row["should_trigger"] else "eval_negatives"


def empty(name: str) -> dict:
    if name == "long_negatives":
        return {"n": 0, "fires": 0, "acceptable": 0, "silent": 0, "fire_rate": 0.0}
    keys = NEG_KEYS if name == "eval_negatives" else POS_KEYS
    return {"n": 0, **{k: 0 for k in keys}}


def score(rows: list[dict], routes: list[dict]) -> dict:
    by_id = {r["id"]: r for r in routes}
    missing = [r["id"] for r in rows if r["id"] not in by_id]
    if missing:
        raise SystemExit(f"score: router output is missing {len(missing)} rows (first: {missing[0]})")
    summary = {n: empty(n) for n in ("eval_positives", "eval_negatives", "probes", "long_negatives")}
    per_plugin: dict[str, dict] = {}
    out_rows, fires = [], []
    for row in rows:
        top = by_id[row["id"]]["top"]
        outcome = classify(row, top)
        b = bucket(row)
        s = summary[b]
        s["n"] += 1
        if b == "long_negatives":
            if outcome == "fire":
                s["fires"] += 1
                fires.append({"id": row["id"], "top": top})
            else:
                s[outcome] += 1
            pl = plugin_of(top) if outcome == "fire" else None
            if pl:
                pp = per_plugin.setdefault(pl, {})
                pp["long_negative_fires"] = pp.get("long_negative_fires", 0) + 1
        else:
            s[outcome] += 1
            pl = plugin_of(row["target"])
            pp = per_plugin.setdefault(pl, {})
            pb = pp.setdefault(b, empty(b))
            pb["n"] += 1
            pb[outcome] += 1
        out_rows.append({
            "id": row["id"], "group": row["group"], "target": row.get("target"),
            "should_trigger": bool(row.get("should_trigger")), "top": top, "outcome": outcome,
            "prompt": " ".join(row["prompt"].split())[:90],
        })
    ln = summary["long_negatives"]
    ln["fire_rate"] = round(ln["fires"] / ln["n"], 4) if ln["n"] else 0.0
    return {
        "schema": 1,
        "rows_sha": rows_sha(rows),
        "summary": summary,
        "per_plugin": {k: per_plugin[k] for k in sorted(per_plugin)},
        "fires": fires,
        "rows": out_rows,
    }


def fmt_table(res: dict) -> str:
    s = res["summary"]
    lines = [f"rows_sha {res['rows_sha']}", ""]

    def line(label, d, keys):
        return f"  {label:<16} n={d['n']:<4} " + "  ".join(f"{k}={d[k]}" for k in keys)

    lines.append("Summary")
    lines.append(line("eval positives", s["eval_positives"], POS_KEYS))
    lines.append(line("eval negatives", s["eval_negatives"], NEG_KEYS))
    lines.append(line("probes", s["probes"], POS_KEYS))
    ln = s["long_negatives"]
    lines.append(f"  {'long negatives':<16} n={ln['n']:<4} fires={ln['fires']}  fire_rate={ln['fire_rate']:.4f}  acceptable={ln['acceptable']}  silent={ln['silent']}")
    lines += ["", "Per plugin (by target plugin; long-negative fires by routed plugin)"]
    lines.append(f"  {'plugin':<24} {'pos h/w/s':<11} {'neg f/x/s/-':<13} {'probe h/w/s':<12} ln_fires")
    for pl, d in res["per_plugin"].items():
        p, n, pr = d.get("eval_positives"), d.get("eval_negatives"), d.get("probes")
        ps = f"{p['hit']}/{p['wrong']}/{p['silent']}" if p else "-"
        ns = f"{n['false_trigger']}/{n['other_cross_plugin']}/{n['other_same_plugin']}/{n['silent']}" if n else "-"
        prs = f"{pr['hit']}/{pr['wrong']}/{pr['silent']}" if pr else "-"
        lines.append(f"  {pl:<24} {ps:<11} {ns:<13} {prs:<12} {d.get('long_negative_fires', 0)}")
    lines.append("  (neg columns: false_trigger / other_cross_plugin / other_same_plugin / silent)")
    if res["fires"]:
        lines += ["", "Long negatives that fire"]
        for f in res["fires"]:
            lines.append(f"  {f['id']} -> {f['top']}")
    return "\n".join(lines)


def short(skill_id):
    return skill_id.removeprefix("skill:") if skill_id else "(silent)"


def compare(a_path: Path, b_path: Path) -> int:
    a, b = json.loads(a_path.read_text()), json.loads(b_path.read_text())
    if a.get("rows_sha") != b.get("rows_sha"):
        print(f"WARNING: row sets differ (A {a.get('rows_sha')} vs B {b.get('rows_sha')}); only common ids are compared")
    ra, rb = {r["id"]: r for r in a["rows"]}, {r["id"]: r for r in b["rows"]}
    print("Metric deltas (B - A)")
    for bk, da in a["summary"].items():
        db = b["summary"][bk]
        parts = []
        for k, va in da.items():
            if isinstance(va, (int, float)) and k != "n":
                d = db[k] - va
                parts.append(f"{k} {va}->{db[k]}" + (f" ({d:+g})" if d else ""))
        print(f"  {bk:<16} " + "  ".join(parts))
    changes = [(i, ra[i], rb[i]) for i in sorted(ra) if i in rb and ra[i]["top"] != rb[i]["top"]]
    print(f"\nRoute changes: {len(changes)}")
    for i, x, y in changes:
        tag = f"{x['outcome']} -> {y['outcome']}" if x["outcome"] != y["outcome"] else f"{x['outcome']} (unchanged outcome)"
        print(f"  [{x['group']}] {i}: {short(x['top'])} -> {short(y['top'])}  | {tag}")
        print(f"      target={short(x['target'])} should_trigger={x['should_trigger']}  \"{x['prompt']}\"")
    return 0


def compare_inferred(a_path: Path, b_path: Path) -> int:
    a, b = json.loads(a_path.read_text()), json.loads(b_path.read_text())
    gained = lost = changed = 0
    lines = []
    for sid in sorted(set(a) | set(b)):
        sa, sb = a.get(sid), b.get(sid)
        if sa == sb:
            continue
        if sa is None or sb is None:
            lines.append(f"  {'+' if sa is None else '-'} {short(sid)}: {sorted(sb if sa is None else sa)}")
            # A skill present on one side only still gains/loses its slugs.
            if sa is None:
                gained += len(sb or [])
            else:
                lost += len(sa or [])
            continue
        changed += 1
        add, rem = sorted(set(sb) - set(sa)), sorted(set(sa) - set(sb))
        gained += len(add)
        lost += len(rem)
        lines.append(f"  ~ {short(sid)}: +{add} -{rem}")
    n_a = sum(1 for v in a.values() if v)
    n_b = sum(1 for v in b.values() if v)
    print(f"Inferred signals: skills with any inferred tag {n_a} -> {n_b}; skills changed {changed}; slugs gained {gained}, lost {lost}")
    print("\n".join(lines))
    return 0


OPS = {"==": operator.eq, "<=": operator.le, ">=": operator.ge, "<": operator.lt, ">": operator.gt}


def dig(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def check(base: dict, cur: dict, thresholds: dict, strict_rows: bool) -> int:
    failed = 0
    if base.get("rows_sha") != cur.get("rows_sha"):
        msg = f"row set differs from baseline (baseline {base.get('rows_sha')}, current {cur.get('rows_sha')}); baseline-relative gates may mislead - regenerate the baseline"
        print(("FAIL  " if strict_rows else "WARN  ") + msg, file=sys.stderr)
        failed += 1 if strict_rows else 0
    for bucket_name in ("eval_positives", "eval_negatives", "probes", "long_negatives"):
        if not dig(cur, f"summary.{bucket_name}.n"):
            print(f"FAIL  empty bucket: summary.{bucket_name} has no rows", file=sys.stderr)
            failed += 1
    for g in thresholds["gates"]:
        got = dig(cur, g["metric"])
        limit = dig(base, g["metric"]) if g["value"] == "baseline" else g["value"]
        if got is None or limit is None:
            ok = False
        else:
            op = OPS[g["op"]]
            ok = op(round(got, 9), round(limit, 9))
        shown = f"{g['metric']} {got} {g['op']} {limit}" + (" (baseline)" if g["value"] == "baseline" else "")
        print(f"{'PASS' if ok else 'FAIL'}  {g['id']}: {shown}")
        failed += 0 if ok else 1
    print(f"\n{'all gates passed' if not failed else str(failed) + ' gate(s) failed'}")
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", help="merged rows.json (corpus + long negatives)")
    ap.add_argument("--routes", help="router output from run_router.js")
    ap.add_argument("--results", help="results.json to write (scoring) or read (--check without --rows)")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    ap.add_argument("--compare-inferred", nargs=2, metavar=("A", "B"))
    ap.add_argument("--check", metavar="BASELINE")
    ap.add_argument("--thresholds")
    # Corpus identity is part of the gate (Codex review 2026-10-10): a reduced
    # corpus must not pass absolute gates. --allow-row-drift downgrades to a warning.
    ap.add_argument("--strict-rows", action="store_true", default=True, help=argparse.SUPPRESS)
    ap.add_argument("--allow-row-drift", action="store_true", help="--check: warn (not fail) when the row set differs from the baseline's")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.compare:
        return compare(Path(args.compare[0]), Path(args.compare[1]))
    if args.compare_inferred:
        return compare_inferred(Path(args.compare_inferred[0]), Path(args.compare_inferred[1]))

    res = None
    if args.rows and args.routes:
        res = score(load_rows(Path(args.rows)), json.loads(Path(args.routes).read_text()))
        if args.results:
            Path(args.results).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        if not args.quiet:
            print(fmt_table(res))
    elif args.check and args.results:
        res = json.loads(Path(args.results).read_text())
    elif not args.check:
        ap.error("need --rows and --routes, or --compare/--compare-inferred, or --check")

    if args.check:
        if not args.thresholds or res is None:
            ap.error("--check needs --thresholds and either --results (existing) or --rows/--routes")
        print()
        return check(json.loads(Path(args.check).read_text()), res, json.loads(Path(args.thresholds).read_text()), args.strict_rows and not args.allow_row_drift)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
