#!/usr/bin/env python3
"""Build the routing-harness corpus (corpus.json) deterministically.

Rows come from the repo's own trigger/routing eval files plus the author-written
retired-vocabulary probes in probes.json. SKILL.md trigger phrases are
deliberately NOT mined: that would be circular (see README.md).

Usage:  python3 build_corpus.py [--repo PATH] [--out corpus.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parent.parent


def load_skills(repo: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    static = json.loads((repo / "generated" / "skill-map.static.json").read_text(encoding="utf-8"))
    ids = {n["id"]: n["id"] for n in static["nodes"] if n.get("kind") == "skill"}
    by_name: dict[str, list[str]] = {}
    for sid in sorted(ids):
        by_name.setdefault(sid.rsplit("/", 1)[-1], []).append(sid)
    return ids, by_name


def make_resolver(ids, by_name):
    def resolve(target) -> str | None:
        if not isinstance(target, str) or not target.strip():
            return None
        t = target.strip()
        if t in ids:
            return t
        t = t.removeprefix("skill:")
        if f"skill:{t}" in ids:
            return f"skill:{t}"
        name = t.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
        cands = by_name.get(name, [])
        return cands[0] if len(cands) == 1 else None

    return resolve


def row(rid, group, source, prompt, target, should, authored, targets=None):
    r = {
        "id": rid,
        "group": group,
        "source": source,
        "prompt": prompt,
        "target": target,
        "should_trigger": bool(should),
        "authored": authored,
    }
    if targets and len(targets) > 1:
        # Alternatives: a route to ANY listed skill is a hit (Codex review 2026-10-10).
        r["targets"] = sorted(targets)
    return r


def collect(repo: Path, resolve):
    rows, skipped = [], []
    evals = repo / "evals"

    def add_list_file(path: Path, target_key: str):
        rel = path.relative_to(repo).as_posix()
        stem = path.parent.name
        for i, case in enumerate(json.loads(path.read_text(encoding="utf-8"))):
            if not isinstance(case, dict) or not isinstance(case.get("prompt"), str):
                continue
            raw = case.get(target_key)
            sid = resolve(raw)
            cid = case.get("id") or f"case-{i}"
            if not sid:
                skipped.append({"source": rel, "id": cid, "target": raw, "reason": "unresolved-or-ambiguous"})
                continue
            rows.append(row(f"{stem}/{cid}", "eval", rel, case["prompt"], sid, case.get("should_trigger", True), "eval"))

    for p in sorted(evals.glob("*/trigger_evals.json")):
        add_list_file(p, "target_skill")
    add_list_file(evals / "rhize-context-manager" / "routing_cases.json", "target")
    add_list_file(evals / "rhize-devflow" / "trigger_cases.json", "target")

    for p in sorted(evals.glob("*/skill-evals.json")):
        rel = p.relative_to(repo).as_posix()
        stem = p.parent.name
        data = json.loads(p.read_text(encoding="utf-8"))
        cases = {c["id"]: c for c in data.get("cases", []) if isinstance(c, dict) and "id" in c}
        negs: dict[str, list[str]] = {}
        for sk in data.get("skills", []):
            for cid in sk.get("negative_cases", []):
                negs.setdefault(cid, []).append(sk["id"])
        for cid, case in cases.items():
            exp = case.get("expected") or []
            if exp:
                # A multi-skill `expected` list is a set of acceptable alternatives:
                # one row, scored as a hit when the route lands on any of them.
                sids = []
                for name in exp:
                    sid = resolve(name)
                    if not sid:
                        skipped.append({"source": rel, "id": cid, "target": name, "reason": "unresolved-or-ambiguous"})
                        continue
                    sids.append(sid)
                if sids:
                    rows.append(row(f"{stem}/{cid}", "eval", rel, case["prompt"], sids[0], True, "eval", targets=sids))
            else:
                if cid not in negs:
                    skipped.append({"source": rel, "id": cid, "target": None, "reason": "no-target"})
                for name in negs.get(cid, []):
                    sid = resolve(name)
                    if not sid:
                        skipped.append({"source": rel, "id": cid, "target": name, "reason": "unresolved-or-ambiguous"})
                        continue
                    rows.append(row(f"{stem}/{cid}@{name}", "eval", rel, case["prompt"], sid, False, "eval"))

    probe_doc = json.loads((HERE / "probes.json").read_text(encoding="utf-8"))
    for pr in probe_doc["probes"]:
        sid = resolve(pr["target"])
        if not sid:
            skipped.append({"source": "probes.json", "id": pr["id"], "target": pr["target"], "reason": "unresolved-or-ambiguous"})
            continue
        if pr.get("should_trigger", True) is not True:
            raise SystemExit(f"build_corpus.py: probe {pr['id']} is negative; probes are positive-only (scored as hit/wrong/silent)")
        rows.append(row(pr["id"], "probe", "probes.json", pr["prompt"], sid, True, "author-written"))

    # Drop exact duplicates (same prompt, target, label); ids must stay unique.
    seen, out, used = set(), [], set()
    for r in rows:
        k = (r["prompt"], r["target"], r["should_trigger"], r["group"])
        if k in seen:
            continue
        seen.add(k)
        rid, n = r["id"], 2
        while r["id"] in used:
            r["id"] = f"{rid}#{n}"
            n += 1
        used.add(r["id"])
        out.append(r)
    return out, skipped


def build(repo: Path) -> dict:
    ids, by_name = load_skills(repo)
    rows, skipped = collect(repo, make_resolver(ids, by_name))
    counts: dict[str, int] = {}
    for r in rows:
        key = f"{r['group']}:{'pos' if r['should_trigger'] else 'neg'}"
        counts[key] = counts.get(key, 0) + 1
    return {"version": 1, "counts": dict(sorted(counts.items())), "skipped": skipped, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=str(DEFAULT_REPO), help="checkout whose evals/ and static map define the corpus (default: this repo)")
    ap.add_argument("--out", default=str(HERE / "corpus.json"))
    args = ap.parse_args(argv)
    doc = build(Path(args.repo).resolve())
    text = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"corpus: {len(doc['rows'])} rows {doc['counts']}; skipped {len(doc['skipped'])}; sha256 {hashlib.sha256(text.encode()).hexdigest()[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
