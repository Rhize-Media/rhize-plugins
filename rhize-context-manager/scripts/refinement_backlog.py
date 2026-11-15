#!/usr/bin/env python3
"""Read-only backlog report for the skill-refinement queue.

    refinement_backlog.py report [--queue PATH] [--top N] [--stale-days D]
                                 [--now ISO8601] [--root DIR ...] [--json]

The script never writes: the queue is opened read-only and no backup, lock or
cache file is created. `stale` is derived at read time and never stored.

Ranking (pending entries only), descending, then `id` ascending:
  1. evidence count  <- top-level `count` when it is an int (not bool);
                        otherwise 1 (the entry is itself one observation).
                        Only 9 live entries carry `count`; `counts` holds
                        heterogeneous per-kind tallies and is not summed.
  2. recency of latest evidence <- latest parsable of `evidence.generated_at`
                        and the entry's `ts`.
  3. distinct sessions <- NO queue field identifies sessions, so this
                        criterion is omitted ("sessions": "not available").

Output is limited to non-free-text fields (see _PUBLIC); pattern, note,
evidence content, filter_note, triage_reason, harvest_log and disposition are
never emitted.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_QUEUE = "~/.claude/context-manager/refinement-queue.jsonl"
# Allowed roots per commands/skill-refine.md `review` step 3.
PLUGIN_SKILLS = Path(__file__).resolve().parent.parent / "skills"
DEFAULT_ROOTS = [PLUGIN_SKILLS, Path("~/.claude/skills/learned").expanduser()]
PLUGIN_PREFIX = "rhize-context-manager/skills/"
RULE = ("evidence count desc, latest evidence recency desc, id asc "
        "(sessions: not available)")


def parse_ts(value):
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def load(path):
    entries, unparsable = [], 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                unparsable += 1
                continue
            if isinstance(obj, dict):
                entries.append(obj)
            else:
                unparsable += 1
    return entries, unparsable


def resolve_target(entry, roots):
    value = entry.get("target_path") or entry.get("target_skill")
    if not isinstance(value, str) or not value.strip():
        return None
    raw = os.path.expanduser(value.strip())
    readable = [r for r in roots if r.is_dir() and os.access(str(r), os.R_OK | os.X_OK)]
    if os.path.isabs(raw):
        p = Path(os.path.normpath(raw))
        roots_ok = [r for r in roots if r == p or r in p.parents]
        if not roots_ok or not os.access(str(roots_ok[0]), os.R_OK | os.X_OK) \
                or not roots_ok[0].is_dir():
            return {"status": "lookup_failed"}
        cands = [p, p.with_name(p.name + ".md")]
        scope = roots_ok[:1]
    else:
        rel = raw[len(PLUGIN_PREFIX):] if raw.startswith(PLUGIN_PREFIX) else raw
        if ".." in Path(rel).parts or not rel.strip("/"):
            return {"status": "lookup_failed"}
        scope = roots
        cands = [r / rel for r in roots] + [r / (rel + ".md") for r in roots]
    for c in cands:
        try:
            if c.exists():
                return {"status": "present"}
        except OSError:
            return {"status": "lookup_failed"}
    scope_ok = [r for r in scope if r in readable]
    if len(scope_ok) != len(scope) or not scope_ok:
        return {"status": "lookup_failed"}
    return {"status": "target_missing", "checked": [str(c) for c in cands]}


def build(entries, unparsable, now, stale_days, roots, top):
    totals = {}
    pending = []
    for e in entries:
        st = e.get("status")
        st = st if isinstance(st, str) else "unknown"
        totals[st] = totals.get(st, 0) + 1
        if st != "pending":
            continue
        ts = parse_ts(e.get("ts"))
        age = None if ts is None else max((now - ts).total_seconds() / 86400.0, 0.0)
        ev = e.get("evidence")
        gen = parse_ts(ev.get("generated_at")) if isinstance(ev, dict) else None
        stamps = [t for t in (ts, gen) if t is not None]
        cnt = e.get("count")
        has_cnt = isinstance(cnt, int) and not isinstance(cnt, bool)
        pending.append({
            "id": str(e.get("id", "")),
            "source": e.get("source"), "repo": e.get("repo"),
            "target_skill": e.get("target_skill"), "target_path": e.get("target_path"),
            "signal_type": e.get("signal_type"), "subtype": e.get("subtype"),
            "status": st,
            "age_days": None if age is None else round(age, 1),
            "stale": age is not None and age >= stale_days,
            "age_unknown": age is None,
            "evidence_count": cnt if has_cnt else 1,
            "est_savings": num(e.get("est_savings")),
            "_latest": max(stamps).timestamp() if stamps else float("-inf"),
            "_ts": ts.timestamp() if ts else float("-inf"),
            "_raw": e,
        })
    pending.sort(key=lambda r: (-r["evidence_count"], -r["_latest"], r["id"]))

    groups = {}
    for r in pending:
        if isinstance(r["target_skill"], str) and r["target_skill"].strip():
            groups.setdefault((r["target_skill"], r["signal_type"], r["subtype"]), []).append(r)
    supersession = []
    for g in groups.values():
        newest = max(g, key=lambda r: (r["_ts"], r["id"]))
        supersession += [{"older_id": r["id"], "newer_id": newest["id"]}
                         for r in g if r is not newest]
    supersession.sort(key=lambda p: (p["older_id"], p["newer_id"]))

    target_loss = []
    for r in pending:
        res = resolve_target(r["_raw"], roots)
        if res and res["status"] != "present":
            target_loss.append(dict(res, id=r["id"]))
    target_loss.sort(key=lambda t: t["id"])

    def public(r):
        return {k: v for k, v in r.items() if not k.startswith("_")}

    return {
        "totals_by_status": totals,
        "pending": len(pending),
        "stale": sum(1 for r in pending if r["stale"]),
        "unparsable": unparsable,
        "stale_days": stale_days,
        "ranking": {"rule": RULE, "sessions": "not available"},
        "top": [public(r) for r in pending[:top]],
        "supersession_candidates": supersession,
        "target_loss_candidates": target_loss,
    }


def render(rep):
    t = ", ".join("%s=%d" % kv for kv in sorted(rep["totals_by_status"].items()))
    out = ["Refinement backlog (read-only)",
           "totals: %s" % (t or "none"),
           "pending: %d  stale(>=%sd): %d  unparsable lines: %d"
           % (rep["pending"], rep["stale_days"], rep["stale"], rep["unparsable"]),
           "ranking: %s" % rep["ranking"]["rule"], "", "Top %d pending:" % len(rep["top"])]
    for i, r in enumerate(rep["top"], 1):
        age = "unknown" if r["age_unknown"] else "%sd" % r["age_days"]
        out.append("%2d. %s  n=%s  age=%s%s  skill=%s type=%s/%s  src=%s repo=%s savings=%s"
                   % (i, r["id"], r["evidence_count"], age, " STALE" if r["stale"] else "",
                      r["target_skill"], r["signal_type"], r["subtype"], r["source"],
                      r["repo"], r["est_savings"]))
    out += ["", "Supersession candidates (advisory): %d" % len(rep["supersession_candidates"])]
    out += ["  %s superseded by %s" % (p["older_id"], p["newer_id"])
            for p in rep["supersession_candidates"]]
    out += ["", "Target-loss candidates (advisory): %d" % len(rep["target_loss_candidates"])]
    for c in rep["target_loss_candidates"]:
        out.append("  %s  %s%s" % (c["id"], c["status"],
                                   "  checked: " + "; ".join(c["checked"]) if "checked" in c else ""))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="refinement_backlog.py")
    sub = ap.add_subparsers(dest="cmd")
    rp = sub.add_parser("report")
    rp.add_argument("--queue", default=DEFAULT_QUEUE)
    rp.add_argument("--top", type=int, default=10)
    rp.add_argument("--stale-days", type=float, default=30)
    rp.add_argument("--now")
    rp.add_argument("--root", action="append", default=[])
    rp.add_argument("--json", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if args.cmd != "report":
        ap.print_usage(sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    if args.now:
        now = parse_ts(args.now)
        if now is None:
            print("error: unparsable --now", file=sys.stderr)
            return 2
    try:
        entries, bad = load(os.path.expanduser(args.queue))
    except OSError as e:
        print("error: cannot read queue: %s" % e, file=sys.stderr)
        return 2
    roots = [Path(os.path.expanduser(r)) for r in args.root] or DEFAULT_ROOTS
    rep = build(entries, bad, now, args.stale_days, roots, max(args.top, 0))
    print(json.dumps(rep, indent=2) if args.json else render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
