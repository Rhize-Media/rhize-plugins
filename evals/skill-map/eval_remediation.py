#!/usr/bin/env python3
"""eval_remediation.py — Eval 4: remediation pattern precision/recall.

Scores the catalog's remediation condition patterns (generated/
skill-map.indexes.json's "remediation" section, sourced from
catalog/tags.json) against the labeled subset of the failure corpus mined by
mine_failure_corpus.py.

Prediction rule mirrors remediation-suggester.js's matchCondition() exactly:
first condition (catalog/index insertion order) whose pattern matches wins —
NOT "any condition that matches" — so an entry can only ever be predicted
into one condition, same as the live hook's "at most one suggestion, ever"
contract.

Label semantics (evals/skill-map/data/failure-corpus.jsonl, hand-editable):
  - ""            unlabeled — excluded from precision/recall, counted as coverage gap.
  - "auto:<slug>" mine_failure_corpus.py's provisional label: exactly one
                  condition matched at mining time. By construction this
                  always agrees with the first-match prediction (there being
                  only one match to be "first"), so these can't surface a
                  false positive on their own — they exist to bootstrap
                  coverage, not to catch regressions.
  - "<slug>"      a human's corrected/confirmed label (condition slug with no
                  "auto:" prefix, or "none" for "no fixer applies").
  - "none"        human-confirmed: no condition should fire for this entry.

Metrics: per-condition precision/recall over ALL non-empty labels (auto or
manual), plus overall false-positive candidates — labeled entries where the
first-match prediction disagrees with the label — and label coverage (how
much of the corpus still needs a human pass).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from mine_failure_corpus import compile_pattern, load_conditions  # reuse identical logic

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = Path(__file__).resolve().parent / "data" / "failure-corpus.jsonl"


def load_corpus():
    if not CORPUS_PATH.exists():
        return []
    rows = []
    with open(CORPUS_PATH) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def predict(snippet, conditions):
    """First-match-wins, mirroring remediation-suggester.js's matchCondition()
    (catalog order, first pattern hit stops the search)."""
    for slug, patterns in conditions:
        for pattern in patterns:
            if pattern.search(snippet):
                return slug
    return None


def true_slug(label):
    """Normalizes a corpus label to a condition slug or None (no fixer)."""
    if not label:
        return None
    if label == "none":
        return None
    if label.startswith("auto:"):
        return label[len("auto:") :]
    return label


def main():
    conditions = load_conditions()
    corpus = load_corpus()

    labeled = [r for r in corpus if r.get("label")]
    unlabeled_count = len(corpus) - len(labeled)

    per_condition = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    false_positive_candidates = []
    overall_correct = 0

    all_slugs = {slug for slug, _ in conditions}

    for row in labeled:
        expected = true_slug(row["label"])
        predicted = predict(row["snippet"], conditions)

        if predicted == expected:
            overall_correct += 1
            if predicted is not None:
                per_condition[predicted]["tp"] += 1
        else:
            if predicted is not None:
                per_condition[predicted]["fp"] += 1
            if expected is not None:
                per_condition[expected]["fn"] += 1
            false_positive_candidates.append(
                {
                    "session_id": row.get("session_id"),
                    "label": row["label"],
                    "predicted": predicted,
                    "snippet_head": row["snippet"][:120],
                }
            )

    print(f"Corpus: {CORPUS_PATH}")
    print(f"  total entries: {len(corpus)}")
    print(f"  labeled: {len(labeled)}  unlabeled: {unlabeled_count}")
    coverage = (len(labeled) / len(corpus) * 100) if corpus else 0.0
    print(f"  label coverage: {coverage:.1f}%")
    print()

    if labeled:
        overall_accuracy = overall_correct / len(labeled)
        print(f"Overall accuracy on labeled subset: {overall_accuracy:.3f} ({overall_correct}/{len(labeled)})")
        print()

    print("Per-condition precision/recall (over labeled subset):")
    for slug in sorted(all_slugs):
        stats = per_condition[slug]
        tp, fp, fn = stats["tp"], stats["fp"], stats["fn"]
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        p_str = f"{precision:.3f}" if precision is not None else "n/a"
        r_str = f"{recall:.3f}" if recall is not None else "n/a"
        print(f"  {slug}: precision={p_str} recall={r_str} (tp={tp} fp={fp} fn={fn})")

    print()
    n_fp_candidates = len(false_positive_candidates)
    per_100 = (n_fp_candidates / len(labeled) * 100) if labeled else 0.0
    print(f"False-positive/disagreement candidates: {n_fp_candidates} ({per_100:.1f} per 100 labeled failures)")
    for c in false_positive_candidates[:20]:
        print(f"  label={c['label']!r} predicted={c['predicted']!r}: {c['snippet_head']!r}")
    if n_fp_candidates > 20:
        print(f"  ... and {n_fp_candidates - 20} more")


if __name__ == "__main__":
    main()
