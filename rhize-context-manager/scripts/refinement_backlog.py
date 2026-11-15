#!/usr/bin/env python3
"""Read-only backlog report for the skill-refinement queue.

    refinement_backlog.py report [--queue PATH] [--top N] [--stale-days D]
                                 [--now ISO8601] [--root DIR ...]
                                 [--plugins-root DIR] [--json]

The script never writes: the queue is opened read-only and no backup, lock or
cache file is created. `stale` is derived at read time and never stored.

Ranking (pending entries only), descending, then `id` ascending:
  1. evidence count  <- top-level `count` when it is a positive int;
                        otherwise 1 (the entry is itself one observation).
                        Only 9 live entries carry `count`; `counts` holds
                        heterogeneous per-kind tallies and is not summed.
  2. recency of latest evidence <- latest parsable of `evidence.generated_at`
                        and the entry's `ts`.
  3. distinct sessions <- NO queue field identifies sessions, so this
                        criterion is omitted ("sessions": "not available").

Target check (advisory). `target_missing` is reported only when absence is
proved: an absolute path under a readable allowed root; a path with the
`rhize-context-manager/skills/` prefix; or a `<plugin>/<skill>` id whose plugin
directory exists. Every candidate must stay inside its base after symlinks are
resolved. A bare name that is not found, an unknown plugin, an unreadable root,
a path that leaves its base, or any filesystem error other than "not found"
is `lookup_failed`, never missing.

Supersession (advisory) needs the same target AND the same lesson (equal
non-empty `signal_type` and `subtype`, or an identical normalised `pattern`)
AND a strictly earlier valid timestamp. The pattern is only hashed for the
comparison and is never printed.

Privacy. Output holds identifier-shaped strings (no spaces, see NAME_RE and
ID_RE), numbers and counts only. pattern, note, evidence content, filter_note,
triage_reason, harvest_log and disposition are never emitted. A field that is
not a string of identifier shape is dropped, and a status outside the known
set is counted as `other`.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_QUEUE = "~/.claude/context-manager/refinement-queue.jsonl"
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
# Allowed roots per commands/skill-refine.md `review` step 3.
PLUGIN_SKILLS = PLUGIN_ROOT / "skills"
DEFAULT_ROOTS = [PLUGIN_SKILLS, Path("~/.claude/skills/learned").expanduser()]
PLUGIN_PREFIX = "rhize-context-manager/skills/"
# Installed copies live at <cache>/<plugin>/<version>/; a checkout at <repo>/<plugin>/.
IN_CACHE = bool(re.match(r"\d+\.\d+", PLUGIN_ROOT.name))
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}\Z")
NAME_RE = re.compile(r"^[A-Za-z0-9~/._][A-Za-z0-9_.:/@+~-]{0,255}\Z")
KNOWN_STATUS = ("pending", "triaged", "rejected", "consumed", "routed", "activation-pending")
RULE = ("evidence count desc, latest evidence recency desc, id asc "
        "(sessions: not available)")
NEVER = float("-inf")


def ident(v, pattern=NAME_RE):
    """An identifier-shaped string (no spaces), else None. Free text does not match."""
    return v if isinstance(v, str) and pattern.match(v) else None


def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and math.isfinite(v):
        return v
    return None


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


def epoch(dt):
    try:
        return dt.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def lesson_key(entry):
    st, sub = entry.get("signal_type"), entry.get("subtype")
    if isinstance(st, str) and st.strip() and isinstance(sub, str) and sub.strip():
        return ("type", st.strip(), sub.strip())
    pat = entry.get("pattern")
    if isinstance(pat, str) and pat.strip():
        norm = " ".join(pat.split()).lower().encode("utf-8", "replace")
        return ("pattern", hashlib.sha256(norm).hexdigest())
    return None


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


# ---- filesystem probes: every doubt is "inconclusive" (None), never "missing" ----

def dir_ok(path):
    try:
        return os.path.isdir(str(path)) and os.access(str(path), os.R_OK | os.X_OK)
    except (OSError, ValueError):
        return False


def probe(path):
    """True if it exists, False if provably absent, None if that cannot be decided."""
    try:
        os.stat(str(path))
        return True
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError):
        return None


def within(base, cand):
    """cand lies in base after symlinks are resolved; None when undecidable."""
    try:
        rb, rc = Path(base).resolve(), Path(cand).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return rc == rb or rb in rc.parents


def lookup(base, cands):
    """'present', 'missing', or None (inconclusive) for candidates that must lie in base."""
    if not dir_ok(base):
        return None
    conclusive = True
    for c in cands:
        if within(base, c) is not True:
            return None
        state = probe(c)
        if state is True:
            return "present"
        if state is None:
            conclusive = False
    return "missing" if conclusive else None


def outcome(pairs):
    """pairs: [(base, [candidates])]. Present anywhere wins; missing needs every base conclusive."""
    checked, all_missing = [], bool(pairs)
    for base, cands in pairs:
        state = lookup(base, cands)
        if state == "present":
            return {"status": "present"}
        if state != "missing":
            all_missing = False
        checked += [str(c) for c in cands]
    return {"status": "target_missing", "checked": checked} if all_missing else None


def plugin_skill_pairs(plugin, skill, plugins_root=None):
    """[(skills dir, [skill path])] for a `<plugin>/<skill>` id; empty when the plugin is unknown."""
    if plugins_root is not None or not IN_CACHE:
        base = Path(plugins_root) if plugins_root is not None else PLUGIN_ROOT.parent
        dirs = [base / plugin / "skills"]
    else:
        base = PLUGIN_ROOT.parent.parent
        try:
            dirs = [v / "skills" for v in sorted((base / plugin).iterdir())]
        except (OSError, ValueError):
            dirs = []
    return [(d, [d / skill]) for d in dirs if dir_ok(d) and within(base, d) is True]


def resolve_target(entry, roots, plugins_root=None):
    value = entry.get("target_path") or entry.get("target_skill")
    if not isinstance(value, str) or not value.strip():
        return None
    failed = {"status": "lookup_failed"}
    if ident(value.strip()) is None:
        # Not identifier-shaped (may be free text): never resolve it or echo it in `checked`.
        return failed
    try:
        raw = os.path.expanduser(value.strip())
        if os.path.isabs(raw):
            p = Path(os.path.normpath(raw))
            bases = [r for r in roots if r == p or r in p.parents]
            if not bases:
                return failed
            return outcome([(bases[0], [p, p.with_name(p.name + ".md")])]) or failed
        prefixed = raw.startswith(PLUGIN_PREFIX)
        rel = raw[len(PLUGIN_PREFIX):] if prefixed else raw
        parts = Path(rel).parts
        if os.path.isabs(rel) or ".." in parts or not parts:
            return failed
        res = outcome([(r, [r / rel, r / (rel + ".md")]) for r in roots])
        if res and res["status"] == "present":
            return res
        if prefixed:
            # An explicit path under the plugin's skills: absence is provable.
            return res or failed
        if len(parts) == 2:
            pairs = plugin_skill_pairs(parts[0], parts[1], plugins_root)
            return (outcome(pairs) if pairs else None) or failed
        # A bare name may be a built-in or another host's skill: absence is not provable.
        return failed
    except (OSError, RuntimeError, ValueError):
        return failed


def build(entries, unparsable, now, stale_days, roots, top, plugins_root=None):
    totals = {}
    pending = []
    for e in entries:
        st = e.get("status")
        key = st if isinstance(st, str) and st in KNOWN_STATUS else "other"
        totals[key] = totals.get(key, 0) + 1
        if st != "pending":
            continue
        ts = parse_ts(e.get("ts"))
        ts_epoch = epoch(ts) if ts is not None else None
        age = None if ts_epoch is None else max((epoch(now) - ts_epoch) / 86400.0, 0.0)
        ev = e.get("evidence")
        gen = parse_ts(ev.get("generated_at")) if isinstance(ev, dict) else None
        gen_epoch = epoch(gen) if gen is not None else None
        stamps = [t for t in (ts_epoch, gen_epoch) if t is not None]
        cnt = e.get("count")
        has_cnt = isinstance(cnt, int) and not isinstance(cnt, bool) and cnt > 0
        pending.append({
            "id": ident(e.get("id"), ID_RE),
            "source": ident(e.get("source")), "repo": ident(e.get("repo")),
            "target_skill": ident(e.get("target_skill")),
            "target_path": ident(e.get("target_path")),
            "signal_type": ident(e.get("signal_type")), "subtype": ident(e.get("subtype")),
            "status": "pending",
            "age_days": None if age is None else round(age, 1),
            "stale": age is not None and age >= stale_days,
            "age_unknown": age is None,
            "evidence_count": cnt if has_cnt else 1,
            "est_savings": num(e.get("est_savings")),
            "_latest": max(stamps) if stamps else NEVER,
            "_ts": ts_epoch if ts_epoch is not None else NEVER,
            "_raw": e,
        })
    pending.sort(key=lambda r: (-r["evidence_count"], -r["_latest"], r["id"] or ""))

    groups = {}
    for r in pending:
        key = lesson_key(r["_raw"])
        if key and r["id"] and r["target_skill"] and r["_ts"] != NEVER:
            groups.setdefault((r["target_skill"], key), []).append(r)
    supersession = []
    for g in groups.values():
        newest_ts = max(r["_ts"] for r in g)
        newest = min((r for r in g if r["_ts"] == newest_ts), key=lambda r: r["id"])
        supersession += [{"older_id": r["id"], "newer_id": newest["id"]}
                         for r in g if r["_ts"] < newest_ts]
    supersession.sort(key=lambda p: (p["older_id"], p["newer_id"]))

    target_loss = []
    for r in pending:
        if not r["id"]:
            continue
        res = resolve_target(r["_raw"], roots, plugins_root)
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
    rp.add_argument("--plugins-root", help="directory that holds <plugin>/skills/<skill>")
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
        if now is None or epoch(now) is None:
            print("error: unparsable --now", file=sys.stderr)
            return 2
    try:
        entries, bad = load(os.path.expanduser(args.queue))
    except OSError as e:
        print("error: cannot read queue: %s" % e.__class__.__name__, file=sys.stderr)
        return 2
    roots = [Path(os.path.expanduser(r)) for r in args.root] or DEFAULT_ROOTS
    plugins_root = os.path.expanduser(args.plugins_root) if args.plugins_root else None
    try:
        rep = build(entries, bad, now, args.stale_days, roots, max(args.top, 0), plugins_root)
        out = json.dumps(rep, indent=2, allow_nan=False) if args.json else render(rep)
    except Exception as e:  # never let a traceback carry queue content to the terminal
        print("error: report failed (%s)" % e.__class__.__name__, file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
