#!/usr/bin/env python3
"""test_suggestion_log_report.py — tests for scripts/suggestion_log_report.py's
source-split between the legacy `{hook, suggested}` rows and the newer
`{source: "agent-dispatch", namedSkills, suggestedSkills}` rows.

Covers:
  1. Backward compatibility: the legacy per-hook numbers (and the router
     silence-sample count) are IDENTICAL whether or not agent-dispatch rows
     are present in the log — agent-dispatch rows carry no `hook` key and
     must be routed to their own section, never counted by the legacy logic.
  2. The three new agent-dispatch metrics (named-rate, candidate-present,
     candidate-miss rate) against hand-computed values, using a fixture with
     one named+suggested-same row, one suggested-disjoint row, and one
     no-candidate row:
       - named-rate = 1/3 (only the first row names a skill)
       - candidate-present = 2 (rows 1 and 2 have a non-empty suggestion)
       - candidate-miss rate = 1/2 (of those 2, only row 2's suggestion is
         disjoint from its named skills — a dispatch with no candidate, like
         row 3, can't miss and is excluded from the denominator)
       - top unnamed-but-suggested skill ids: the one id from row 2's miss.
  3. The per-agentType breakdown (`by_agent_type`): the fixture's rows 1-2 are
     agentType "executor" (Skill-capable) and row 3 is agentType "verifier"
     (Skill-less), hand-computed as:
       - executor: total=2, named_rate=1/2 (row 1 only), candidate_present=2
         (rows 1-2), candidate_miss_rate=1/2 (row 2 only)
       - verifier: total=1, named_rate=0.0 (row 3 named nothing),
         candidate_present=0, candidate_miss_rate=0.0 (no candidate to miss)

Does not use pytest (matches this repo's other skill-map tests) — runs with
a bare `python3 tests/skill-map/test_suggestion_log_report.py`.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "suggestion_log_report.py"

LEGACY_ROWS = [
    {
        "ts": "2026-08-26T00:00:00Z",
        "session_id": "sessA",
        "hook": "router",
        "suggested": "skill:rhize-context-manager/graphify",
        "context_hash": "aaaa1111",
    },
    {
        "ts": "2026-08-26T00:01:00Z",
        "session_id": "sessB",
        "hook": "disclosure",
        "suggested": ["skill:x/y"],
        "context_hash": "bbbb2222",
    },
]

# Row 1: named+suggested-same — brief named the exact skill route-core would
#   also have suggested. Not a miss (overlap), so it does not contribute to
#   candidate_miss or top_unnamed_suggested, but it IS candidate_present.
#   agentType "executor" — a Skill-capable roster (briefed to NAME a skill).
# Row 2: suggested-disjoint — brief named nothing, but route-core suggested a
#   skill. candidate_present + candidate_miss (fully disjoint from named=[]).
#   Also agentType "executor", so rows 1-2 together form the executor group.
# Row 3: no-candidate — brief named nothing and route-core had no candidate
#   above BRIEF_MIN_SCORE. Neither named nor candidate_present. agentType
#   "verifier" — a Skill-less roster (briefed to INLINE content, never name
#   a skill), kept in its own group to exercise the by_agent_type split.
AGENT_DISPATCH_ROWS = [
    {
        "ts": "2026-08-26T00:02:00Z",
        "source": "agent-dispatch",
        "agentType": "executor",
        "briefHash": "c1c1c1c1c1c1c1c1",
        "briefLength": 100,
        "namedSkills": ["skill:rhize-context-manager/graphify"],
        "suggestedSkills": ["skill:rhize-context-manager/graphify"],
        "advisoryEmitted": False,
    },
    {
        "ts": "2026-08-26T00:03:00Z",
        "source": "agent-dispatch",
        "agentType": "executor",
        "briefHash": "c2c2c2c2c2c2c2c2",
        "briefLength": 200,
        "namedSkills": [],
        "suggestedSkills": ["skill:rhize-context-manager/foo"],
        "advisoryEmitted": False,
    },
    {
        "ts": "2026-08-26T00:04:00Z",
        "source": "agent-dispatch",
        "agentType": "verifier",
        "briefHash": "c3c3c3c3c3c3c3c3",
        "briefLength": 50,
        "namedSkills": [],
        "suggestedSkills": [],
        "advisoryEmitted": False,
    },
]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_legacy_numbers_identical_with_and_without_agent_dispatch_rows() -> None:
    mod = load_module(SCRIPT_PATH, "suggestion_log_report")
    tmpdir = Path(tempfile.mkdtemp())
    try:
        legacy_only_path = tmpdir / "legacy-only.jsonl"
        mixed_path = tmpdir / "mixed.jsonl"
        _write_jsonl(legacy_only_path, LEGACY_ROWS)
        _write_jsonl(mixed_path, LEGACY_ROWS + AGENT_DISPATCH_ROWS)

        legacy_only_report = mod.compute_report(mod.load_log(legacy_only_path), {})
        mixed_report = mod.compute_report(mod.load_log(mixed_path), {})

        if mixed_report["per_hook"] != legacy_only_report["per_hook"]:
            raise AssertionError(
                "per_hook must be byte-for-byte identical with agent-dispatch rows "
                f"present; legacy-only={legacy_only_report['per_hook']!r} "
                f"mixed={mixed_report['per_hook']!r}"
            )
        if mixed_report["router_silence_samples"] != legacy_only_report["router_silence_samples"]:
            raise AssertionError(
                "router_silence_samples must be identical with agent-dispatch rows "
                f"present; legacy-only={legacy_only_report['router_silence_samples']!r} "
                f"mixed={mixed_report['router_silence_samples']!r}"
            )
        print("PASS test_legacy_numbers_identical_with_and_without_agent_dispatch_rows")
    finally:
        shutil.rmtree(tmpdir)


def test_agent_dispatch_metrics_match_hand_computed_values() -> None:
    mod = load_module(SCRIPT_PATH, "suggestion_log_report")
    tmpdir = Path(tempfile.mkdtemp())
    try:
        log_path = tmpdir / "mixed.jsonl"
        _write_jsonl(log_path, LEGACY_ROWS + AGENT_DISPATCH_ROWS)

        report = mod.compute_report(mod.load_log(log_path), {})
        ad = report["agent_dispatch"]

        if ad["total"] != 3:
            raise AssertionError(f"expected total=3, got {ad['total']!r}")

        expected_named_rate = 1 / 3
        if abs(ad["named_rate"] - expected_named_rate) > 1e-9:
            raise AssertionError(f"expected named_rate=1/3, got {ad['named_rate']!r}")

        if ad["candidate_present"] != 2:
            raise AssertionError(f"expected candidate_present=2, got {ad['candidate_present']!r}")

        expected_miss_rate = 1 / 2
        if abs(ad["candidate_miss_rate"] - expected_miss_rate) > 1e-9:
            raise AssertionError(f"expected candidate_miss_rate=1/2, got {ad['candidate_miss_rate']!r}")

        expected_top = [{"skill_id": "skill:rhize-context-manager/foo", "count": 1}]
        if ad["top_unnamed_suggested"] != expected_top:
            raise AssertionError(
                f"expected top_unnamed_suggested={expected_top!r}, got "
                f"{ad['top_unnamed_suggested']!r}"
            )
        print("PASS test_agent_dispatch_metrics_match_hand_computed_values")
    finally:
        shutil.rmtree(tmpdir)


def test_agent_dispatch_by_agent_type_breakdown_matches_hand_computed_values() -> None:
    mod = load_module(SCRIPT_PATH, "suggestion_log_report")
    tmpdir = Path(tempfile.mkdtemp())
    try:
        log_path = tmpdir / "mixed.jsonl"
        _write_jsonl(log_path, LEGACY_ROWS + AGENT_DISPATCH_ROWS)

        report = mod.compute_report(mod.load_log(log_path), {})
        by_type = report["agent_dispatch"]["by_agent_type"]

        if set(by_type.keys()) != {"executor", "verifier"}:
            raise AssertionError(f"expected agentTypes {{'executor', 'verifier'}}, got {set(by_type.keys())!r}")

        executor = by_type["executor"]
        if executor["total"] != 2:
            raise AssertionError(f"expected executor total=2, got {executor['total']!r}")
        if abs(executor["named_rate"] - 0.5) > 1e-9:
            raise AssertionError(f"expected executor named_rate=1/2, got {executor['named_rate']!r}")
        if executor["candidate_present"] != 2:
            raise AssertionError(
                f"expected executor candidate_present=2, got {executor['candidate_present']!r}"
            )
        if abs(executor["candidate_miss_rate"] - 0.5) > 1e-9:
            raise AssertionError(
                f"expected executor candidate_miss_rate=1/2, got {executor['candidate_miss_rate']!r}"
            )

        verifier = by_type["verifier"]
        if verifier["total"] != 1:
            raise AssertionError(f"expected verifier total=1, got {verifier['total']!r}")
        if abs(verifier["named_rate"] - 0.0) > 1e-9:
            raise AssertionError(f"expected verifier named_rate=0.0, got {verifier['named_rate']!r}")
        if verifier["candidate_present"] != 0:
            raise AssertionError(
                f"expected verifier candidate_present=0, got {verifier['candidate_present']!r}"
            )
        if abs(verifier["candidate_miss_rate"] - 0.0) > 1e-9:
            raise AssertionError(
                f"expected verifier candidate_miss_rate=0.0, got {verifier['candidate_miss_rate']!r}"
            )
        print("PASS test_agent_dispatch_by_agent_type_breakdown_matches_hand_computed_values")
    finally:
        shutil.rmtree(tmpdir)


def main() -> int:
    tests = [
        test_legacy_numbers_identical_with_and_without_agent_dispatch_rows,
        test_agent_dispatch_metrics_match_hand_computed_values,
        test_agent_dispatch_by_agent_type_breakdown_matches_hand_computed_values,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            print(f"FAIL {test.__name__}: {exc}")
            failures += 1
    if failures:
        print(f"\n{failures} test(s) failed.")
        return 1
    print("\nAll suggestion_log_report tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
