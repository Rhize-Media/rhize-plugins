#!/usr/bin/env python3
"""Collection-side noise filter for /learn-harvest.

Why this exists
---------------
Queue entry ids are `sha1-12(source + pattern)`, so **any rephrasing of the same
fact produces a new id and slips past id-dedupe**. Headroom rephrases constantly:
on 2026-08-14, 3 of 5 headroom entries restated facts already folded into
CLAUDE.md on 2026-08-12, and the two largest `est_savings` claims (235k, 45k)
were the two most duplicative. That is ~30% of a day's yield spent re-litigating
settled facts.

This filter matches on **content**, not hash. A candidate is suppressed when its
normalized content tokens are largely contained in some reference chunk — an
existing queue pattern (any status) or a CLAUDE.md block.

Design constraints
------------------
- Stdlib only. System python3 (3.14) has no `jsonschema` and no third-party deps.
- Deterministic and reproducible: same inputs -> same decisions, no LLM, no network.
- **Never silent.** Every suppression is reported with the reference text it
  matched and its score, so a filtered run is distinguishable from a run that
  never happened. Tee the report next to the headroom capture.

Usage
-----
    # filter today's candidates, write survivors, tee a report
    python3 scripts/harvest_noise_filter.py \
        --candidates /tmp/candidates.jsonl \
        --queue ~/.claude/context-manager/refinement-queue.jsonl \
        --reference CLAUDE.md \
        --keep-out /tmp/kept.jsonl \
        | tee ~/.claude/context-manager/harvest-logs/$(date +%F)-filter.txt

    # calibration / audit: score entries already in the queue against everything else
    python3 scripts/harvest_noise_filter.py --self-audit --status pending

Exit codes: 0 always (a fully-suppressed batch is a legitimate result, not an error).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# Ordinary English + queue-boilerplate words carry no discriminating signal.
STOPWORDS = frozenset("""
a about after all also an and any are as at be been before being between both but by can
cannot could did do does doing done down during each else even ever every for from further
had has have having he her here hers him his how i if in into is it its itself just make
makes many may me more most much must my no nor not now of off on once only or other our
out over own per rather re same she should so some such than that the their them then there
these they this those through to too under until up use used uses using very was we were
what when where which while who whom why will with within without would you your
""".split())

TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+")
# Markdown noise stripped before tokenizing.
MD_STRIP_RE = re.compile(r"[`*_~#>|\[\]()]+")

MIN_CONTENT_TOKENS = 6  # below this a candidate is too thin to score meaningfully


def normalize(text: str) -> list[str]:
    """Lowercase, strip markdown, tokenize, drop stopwords and 1-char tokens."""
    text = MD_STRIP_RE.sub(" ", text or "")
    out = []
    for raw in TOKEN_RE.findall(text.lower()):
        tok = raw.strip("./-")
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        out.append(tok)
    return out


def containment(cand: set[str], ref: set[str]) -> float:
    """Fraction of the candidate's content tokens present in the reference."""
    if not cand:
        return 0.0
    return len(cand & ref) / len(cand)


def chunk_markdown(text: str) -> list[str]:
    """Split a markdown doc into bullet/paragraph blocks.

    Whole-document comparison is useless here: a 3-line pattern against a 40KB
    CLAUDE.md scores ~0 no matter how thoroughly the fact is already documented.
    Blocks restore the right granularity.
    """
    blocks: list[list[str]] = []
    cur: list[str] = []

    def flush():
        if cur and any(l.strip() for l in cur):
            blocks.append(cur.copy())
        cur.clear()

    for line in text.splitlines():
        stripped = line.strip()
        is_bullet = bool(re.match(r"^\s*[-*+]\s+", line)) or bool(re.match(r"^\s*\d+\.\s+", line))
        is_heading = stripped.startswith("#")
        if not stripped:
            flush()
            continue
        if is_bullet or is_heading:
            flush()
        cur.append(line)
    flush()
    return ["\n".join(b).strip() for b in blocks]


def load_jsonish(path: str) -> list[dict]:
    """Accept either a JSON array or JSON-lines."""
    with open(os.path.expanduser(path)) as fh:
        raw = fh.read().strip()
    if not raw:
        return []
    if raw.lstrip().startswith("["):
        return json.loads(raw)
    return [json.loads(l) for l in raw.splitlines() if l.strip()]


class Reference:
    __slots__ = ("origin", "label", "text", "tokens")

    def __init__(self, origin: str, label: str, text: str):
        self.origin = origin          # 'queue' | 'doc'
        self.label = label            # entry id, or "<file>:<block#>"
        self.text = text
        self.tokens = set(normalize(text))


def build_references(queue_path: str | None, doc_paths: list[str],
                     exclude_ids: set[str]) -> list[Reference]:
    refs: list[Reference] = []
    if queue_path and os.path.exists(os.path.expanduser(queue_path)):
        for row in load_jsonish(queue_path):
            rid = row.get("id")
            if rid in exclude_ids:
                continue
            pattern = row.get("pattern") or ""
            if not pattern.strip():
                continue
            label = f"{rid} [{row.get('status', '?')}]"
            refs.append(Reference("queue", label, pattern))
    for doc in doc_paths:
        p = os.path.expanduser(doc)
        if not os.path.exists(p):
            print(f"warning: reference doc not found, skipping: {doc}", file=sys.stderr)
            continue
        with open(p, encoding="utf-8", errors="replace") as fh:
            for i, block in enumerate(chunk_markdown(fh.read())):
                if len(normalize(block)) < 4:
                    continue
                refs.append(Reference("doc", f"{os.path.basename(p)}:block{i}", block))
    return refs


def score_candidate(cand_tokens: set[str], refs: list[Reference], max_blocks: int = 3):
    """Greedy set-cover: how much of the candidate is covered by up to N reference blocks.

    Max-single-block containment systematically under-scores real duplicates,
    because one harvested pattern routinely restates facts that CLAUDE.md keeps in
    *separate* bullets — e.g. skill-forge's build command lives under "Repository
    layout" while "read the file once" lives under "Edit/Read discipline". Scoring
    only the single best block called that pair novel. Unioning the whole document
    is the opposite error (a 40KB doc contains nearly every token), so cover is
    capped at a few blocks.
    """
    if not cand_tokens:
        return 0.0, []
    covered: set[str] = set()
    used: list[Reference] = []
    for _ in range(max_blocks):
        best_ref, best_gain = None, 0
        for ref in refs:
            gain = len(cand_tokens & ref.tokens - covered)
            if gain > best_gain:
                best_ref, best_gain = ref, gain
        if best_ref is None or best_gain == 0:
            break
        covered |= (cand_tokens & best_ref.tokens)
        used.append(best_ref)
    return len(covered) / len(cand_tokens), used


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", help="JSON or JSONL of candidate queue entries")
    ap.add_argument("--queue", default="~/.claude/context-manager/refinement-queue.jsonl",
                    help="existing queue, used as reference (all statuses)")
    ap.add_argument("--reference", action="append", default=[],
                    help="markdown doc to match against; repeatable (e.g. CLAUDE.md)")
    ap.add_argument("--threshold", type=float, default=0.75,
                    help="coverage at or above which a candidate is suppressed "
                         "(calibrated 2026-08-14: keepers topped out at 0.70, "
                         "fully-covered restatements started at 0.80)")
    ap.add_argument("--flag-threshold", type=float, default=0.45,
                    help="coverage at or above which a candidate is KEPT but flagged as a "
                         "partial duplicate for the human triage step")
    ap.add_argument("--max-blocks", type=int, default=3,
                    help="max reference blocks unioned when scoring coverage")
    ap.add_argument("--keep-out", help="write surviving entries here as JSONL")
    ap.add_argument("--self-audit", action="store_true",
                    help="score existing queue entries against everything else (calibration)")
    ap.add_argument("--status", default="pending",
                    help="with --self-audit: which status to audit")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON report")
    args = ap.parse_args()

    if args.self_audit:
        rows = load_jsonish(args.queue)
        candidates = [r for r in rows if r.get("status") == args.status]
        exclude = {r.get("id") for r in candidates}
    elif args.candidates:
        candidates = load_jsonish(args.candidates)
        # A candidate must never match itself: exact repeats are already handled by
        # id-dedupe, and self-matching would score 1.00 and suppress everything.
        exclude = {c.get("id") for c in candidates}
    else:
        ap.error("need --candidates or --self-audit")
        return 2

    refs = build_references(args.queue, args.reference, exclude)

    kept, suppressed, thin, flagged = [], [], [], []
    for c in candidates:
        tokset = set(normalize(c.get("pattern") or ""))
        score, used = score_candidate(tokset, refs, args.max_blocks)
        origins = sorted({r.origin for r in used})
        rec = {
            "id": c.get("id"),
            "source": c.get("source"),
            "pattern": c.get("pattern"),
            "score": round(score, 3),
            "matched": [r.label for r in used],
            "matched_origin": "+".join(origins) if origins else None,
            "matched_text": [r.text[:180] for r in used],
            "content_tokens": len(tokset),
        }
        if len(tokset) < MIN_CONTENT_TOKENS:
            rec["reason"] = "thin: too few content tokens to be an actionable signal"
            thin.append((c, rec))
        elif score >= args.threshold:
            rec["reason"] = (f"duplicate: {score:.0%} of content already covered by "
                             f"{len(used)} block(s) in {rec['matched_origin']}")
            suppressed.append((c, rec))
        elif score >= args.flag_threshold:
            # Composite entries ("Topic — Fact1. Fact2. Fact3.") land here: each fact is
            # already documented but the bundle keeps enough novel tokens to stay under
            # the suppress threshold. Auto-suppressing at this score would also kill
            # genuine signals, so flag for the human instead of guessing.
            rec["reason"] = (f"partial-duplicate: {score:.0%} already covered by "
                             f"{rec['matched_origin']} — may be a composite of known facts")
            c["filter_note"] = rec["reason"]
            flagged.append((c, rec))
            kept.append((c, rec))
        else:
            kept.append((c, rec))

    if args.json:
        print(json.dumps({
            "threshold": args.threshold,
            "flag_threshold": args.flag_threshold,
            "candidates": len(candidates),
            "kept": [r for _, r in kept],
            "suppressed": [r for _, r in suppressed],
            "thin": [r for _, r in thin],
            "flagged": [r for _, r in flagged],
        }, indent=2))
    else:
        print(f"harvest noise filter — {len(candidates)} candidates, "
              f"suppress>={args.threshold:.2f} flag>={args.flag_threshold:.2f}, "
              f"{len(refs)} reference chunks")
        print(f"  kept {len(kept)} (of which {len(flagged)} flagged) | "
              f"suppressed {len(suppressed)} | thin {len(thin)}")
        for title, group in (("SUPPRESSED", suppressed), ("THIN", thin),
                             ("FLAGGED (kept, needs a look at triage)", flagged),
                             ("KEPT", kept)):
            if not group:
                continue
            print(f"\n--- {title} ({len(group)}) ---")
            for _, r in sorted(group, key=lambda x: -x[1]["score"]):
                print(f"[{r['score']:.2f}] {r['id']} ({r['source']})")
                print(f"    {(r['pattern'] or '')[:150]}")
                if not title.startswith("KEPT"):
                    for label, text in zip(r.get("matched") or [], r.get("matched_text") or []):
                        print(f"    ^ {label}: {text[:130]}")

    if args.keep_out:
        with open(os.path.expanduser(args.keep_out), "w") as fh:
            for c, _ in kept:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"\nsurvivors written to {args.keep_out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
