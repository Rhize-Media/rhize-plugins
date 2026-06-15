#!/usr/bin/env python3
"""overlap_scan.py — Rank a candidate skill against the existing Rhize skill set.

Heuristic, dependency-free. Blends Jaccard token overlap with keyword containment of the
candidate's distinctive phrases. Prints a ranked table, the nearest Rhize skill, and a
suggested decision verb (a prior, not a verdict — see references/overlap-analysis.md).

Usage:
    python3 overlap_scan.py <candidate-path> --skills-root <rhize-skills-root> [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

STOPWORDS = set("""
a an the and or of to for in on with use used using when whether this that these those is are be
your you it its as at by from into via per also any all not no than then so if up out via about
skill skills user claude code based comprehensive enhanced practical including include includes
""".split())


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def read_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(errors="ignore")
    fm = {"name": skill_md.parent.name, "description": ""}
    if text.startswith("---\n"):
        block = text.split("---", 2)[1]
        m = re.search(r"^name:\s*(.+)$", block, re.M)
        if m:
            fm["name"] = m.group(1).strip().strip("'\"")
        m = re.search(r"^description:\s*(.*)$", block, re.M)
        if m:
            first = m.group(1).strip()
            if first in (">", ">-", "|", "|-", ""):
                lines = block.splitlines()
                idx = next(i for i, l in enumerate(lines) if re.match(r"^description:", l))
                buf = []
                for l in lines[idx + 1:]:
                    if re.match(r"^\s+\S", l):
                        buf.append(l.strip())
                    elif l.strip() == "":
                        continue
                    else:
                        break
                fm["description"] = " ".join(buf)
            else:
                fm["description"] = first.strip("'\"")
    else:
        # fall back to first heading + first paragraph
        heads = re.findall(r"^#\s+(.+)$", text, re.M)
        fm["description"] = (heads[0] if heads else "") + " " + text[:400]
    return fm


def tokenize(text: str) -> set:
    toks = re.findall(r"[a-zA-Z][a-zA-Z0-9+.-]{2,}", text.lower())
    return {t for t in toks if t not in STOPWORDS}


def keyphrases(text: str) -> set:
    """Distinctive quoted trigger phrases and salient words from a description."""
    quoted = set(re.findall(r'"([^"]{2,40})"', text)) | set(re.findall(r"'([^']{2,40})'", text))
    quoted = {q.lower().strip() for q in quoted}
    return quoted or tokenize(text)


def score(cand: dict, other: dict) -> float:
    a = tokenize(cand["name"] + " " + cand["description"])
    b = tokenize(other["name"] + " " + other["description"])
    if not a:
        return 0.0
    jaccard = len(a & b) / len(a | b) if (a | b) else 0.0
    # containment: how much of the candidate's vocabulary the other skill covers
    containment = len(a & b) / len(a)
    # phrase bonus: candidate's quoted trigger phrases whose words all appear in the other skill
    phrases = set(re.findall(r'"([^"]{2,40})"', cand["description"])) | \
        set(re.findall(r"'([^']{2,40})'", cand["description"]))
    pscore = 0.0
    if phrases:
        hits = 0
        for p in phrases:
            pw = tokenize(p)
            if pw and pw <= b:
                hits += 1
        pscore = hits / len(phrases)
    return round(0.30 * jaccard + 0.50 * containment + 0.20 * pscore, 3)


def suggest_verb(top_score: float) -> str:
    if top_score >= 0.45:
        return "ABSORB (or REJECT if ours is already better)"
    if top_score >= 0.20:
        return "FORK (re-skin), or ABSORB one piece"
    return "DEFER / new FORK (little overlap)"


def set_scan(root: Path, threshold: float) -> list:
    """N-way: pairwise overlap across the whole installed set; report pairs >= threshold.

    Symmetric: the pair score is max(score(a,b), score(b,a)) since `score` is candidate-centric.
    Surfaces internal redundancy (e.g. several skills covering one domain) for N-way ABSORB.
    """
    found: set = set()
    for g in ("*/SKILL.md", "skills/*/SKILL.md", "*/skills/*/SKILL.md"):
        found |= set(root.glob(g))
    paths = sorted(p for p in found if "/.git/" not in str(p))
    metas = [read_frontmatter(p) for p in paths]
    pairs = []
    for i in range(len(metas)):
        for j in range(i + 1, len(metas)):
            sc = max(score(metas[i], metas[j]), score(metas[j], metas[i]))
            if sc >= threshold:
                pairs.append({"a": metas[i]["name"], "b": metas[j]["name"], "score": round(sc, 3)})
    pairs.sort(key=lambda r: r["score"], reverse=True)
    return pairs


def main() -> None:
    try:  # ASCII-locale safety for the human-readable output path (e.g. LANG=C cron)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Rank a candidate vs the Rhize set, or scan the set for internal overlap.")
    ap.add_argument("candidate", nargs="?", help="candidate skill dir or SKILL.md (omit with --set-mode)")
    ap.add_argument("--skills-root", required=True, help="root containing existing Rhize skills")
    ap.add_argument("--set-mode", action="store_true",
                    help="N-way: rank internal redundancy across the whole set (no candidate)")
    ap.add_argument("--threshold", type=float, default=0.45,
                    help="min pair score to report in --set-mode (default 0.45)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(os.path.expanduser(args.skills_root)).resolve()
    if not root.is_dir():
        fail(f"skills-root not a directory: {root}")

    if args.set_mode:
        pairs = set_scan(root, args.threshold)
        if args.json:
            print(json.dumps({"set_mode": True, "threshold": args.threshold, "pairs": pairs}, indent=2))
            return
        print(f"Internal redundancy — pairs scoring >= {args.threshold}:")
        if not pairs:
            print("  none above threshold.")
            return
        for p in pairs:
            bar = "█" * int(p["score"] * 20)
            print(f"  {p['score']:.3f} {bar:<20} {p['a']}  <=>  {p['b']}")
        print("\nHigh pairs = merge candidates (N-way ABSORB) or DEFER one to the other.")
        print("The score points; you decide — open both bodies (see references/overlap-analysis.md).")
        return

    if not args.candidate:
        fail("candidate is required unless --set-mode is set")
    cpath = Path(os.path.expanduser(args.candidate)).resolve()
    if cpath.is_dir():
        cpath = cpath / "SKILL.md"
    if not cpath.exists():
        fail(f"candidate SKILL.md not found: {cpath}")

    cand = read_frontmatter(cpath)

    existing = sorted(set(root.glob("*/SKILL.md")) | set(root.glob("skills/*/SKILL.md"))
                      | set(root.glob("*/skills/*/SKILL.md")))
    existing = [p for p in existing if p.resolve() != cpath.resolve() and "/.git/" not in str(p)]
    if not existing:
        fail(f"no existing skills found under {root}")

    ranked = []
    for p in existing:
        other = read_frontmatter(p)
        ranked.append({"skill": other["name"], "path": str(p), "score": score(cand, other)})
    ranked.sort(key=lambda r: r["score"], reverse=True)

    top = ranked[0]
    verb = suggest_verb(top["score"])
    result = {"candidate": cand["name"], "nearest": top["skill"],
              "nearest_score": top["score"], "suggested_verb": verb, "ranking": ranked}

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"Candidate: {cand['name']}")
    print(f"Nearest Rhize skill: {top['skill']}  (overlap {top['score']})")
    print(f"Suggested verb: {verb}")
    print("\nFull ranking:")
    for r in ranked:
        bar = "█" * int(r["score"] * 20)
        print(f"  {r['score']:.3f} {bar:<20} {r['skill']}")
    print("\nNote: heuristic only — open the nearest skill + candidate before deciding.")


if __name__ == "__main__":
    main()
