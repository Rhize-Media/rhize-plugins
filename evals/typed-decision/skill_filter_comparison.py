"""Prospective, read-only Claude skill-filter comparison for the two weekly reviews."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics

import decision_cycle as cycle
from typed_decisions import cohorts, contract, records
from typed_decisions.locked_io import utc

START = utc("2026-11-28T00:00:00Z")
END = utc("2026-12-06T23:30:00Z")
NAMES = ("incumbent", "floor@3", "cosign-v1", "cosign@0.4")
POLICIES = dict((name, fn) for name, _, _, fn in cycle.policies() if name in NAMES)
# Frozen November 27 from the installed decision identity and actual observed model.
KEY = (
    "19509e93ee72927d5e46ad62dd4fe69bfd090a31f86ac4f944a0ad89085eb205",
    "8df42f4f0a89fb13fe696e5dd427e67cce7bd0ee0401ac1acecb027830a7b0ed",
    "55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851",
)


ROUTER = "6c470050e749cb09d0379e9e0a0b925317cd5082911d90c17285dcd93c88c438"
INDEX = "4866c671ae343187ff60a511cace5fe4cd89695792068dd5de44899e1bf1f580"


def compare(recs, labels, reserved, now):
    cutoff = min(now, END)
    exclude = {r["sessionHash"] for r in recs if utc(r["ts"]) < START or r["occurrenceKey"] in reserved}
    frame = [
        r
        for r in recs
        if START <= utc(r["ts"]) < cutoff
        and r["sessionHash"] not in exclude
        and r["basis"] == "live"
        and r["mode"] == "shadow"
        and cohorts.is_gate_record(r)
    ]
    cases = {}
    for label in labels:
        k = label["occurrenceKey"]
        if (
            label["cohortId"] is None
            and label["basis"] == "ai_model_reviewed"
            and len(set(label["annotators"])) >= 2
            and label["reviewer"] not in label["annotators"]
            and label["evidenceSha256"]
            and label["stratum"] in cycle.POOL_STRATA
            and START <= utc(label["labeledAt"]) < cutoff
        ):
            if k in cases and cases[k] != label:
                raise ValueError("conflicting development labels")
            cases[k] = label
    failures = Counter()
    latency = []
    clusters = defaultdict(list)
    missing = Counter()
    weights = []
    hits = [0] * len(NAMES)
    unsupported = 0
    for rec in frame:
        if cohorts.key_of(rec) != KEY or rec["routerSourceSha256"] != ROUTER or rec["indexSha256"] != INDEX:
            unsupported += 1
            continue
        failures[rec["laya"]["status"]] += 1
        if rec["laya"].get("latencyMs") is not None:
            latency.append(rec["laya"]["latencyMs"])
        choices = [POLICIES[n](rec) for n in NAMES]
        label = cases.get(rec["occurrenceKey"])
        if (
            not label
            or label["ambiguous"]
            or label["candidates"] != rec["shortlist"]
            or label["decisionId"] != rec["decisionId"]
        ):
            for n, choice in zip(NAMES, choices):
                if choices[0] != choice:
                    missing[n] += 1
            if choices[1] != choices[2]:
                missing["floor-v1"] += 1
            if choices[1] != choices[3]:
                missing["floor-tau"] += 1
            continue
        weight = (20 if rec["sourceStratum"] == "silent_sample" else 1) / label["inclusionProbability"]
        weights.append(weight)
        vector = []
        for i, choice in enumerate(choices):
            score = contract.score_suggestion(choice, label)
            hits[i] += int(score == "hit")
            vector.extend([weight * (score == "hit"), weight * (score in ("wrong", "false_fire"))])
        clusters[rec["sessionHash"]].append(vector)
    vectors = [[sum(col) for col in zip(*entries)] for entries in clusters.values()]
    sums = [sum(col) for col in zip(*vectors)] if vectors else [0.0] * 8
    rng = random.Random(20261127)
    draws = (
        [[sum(col) for col in zip(*rng.choices(vectors, k=len(vectors)))] for _ in range(2000)]
        if vectors
        else []
    )

    def lower(values):
        return sorted(values)[len(values) // 20] if values else None

    def delta(row, i, j, rate):
        return rate * (row[2 * i] - row[2 * j]) - row[2 * i + 1] + row[2 * j + 1]

    outcomes = {}
    winners = []
    for i, name in enumerate(NAMES):
        h, bad = sums[2 * i : 2 * i + 2]
        # A resample with no incumbent hits supplies no positive lower-bound evidence.
        retention = lower([row[2 * i] / row[0] if row[0] else 0 for row in draws])
        reduction = 1 - bad / sums[1] if sums[1] else None
        margins = {
            rate: [lower([delta(row, i, j, rate) for row in draws]) for j in ([0, 1] if i > 1 else [0])]
            for rate in (5, 10, 20)
        }
        uncertainty = missing[name] + (missing["floor-v1" if i == 2 else "floor-tau"] if i > 1 else 0)
        eligible = (
            i > 0
            and retention is not None
            and retention >= 0.8
            and reduction is not None
            and reduction >= 0.2
            and all(v is not None and v > 0 for vals in margins.values() for v in vals)
            and uncertainty == 0
        )
        if i > 1:
            unavailable = sum(failures.values()) - failures["ok"]
            eligible = (
                eligible
                and sum(failures.values()) >= 20
                and unavailable <= 0.05 * sum(failures.values())
                and len(latency) == sum(failures.values())
                and max(latency, default=0) <= 800
            )
        if eligible:
            winners.append(name)
        outcomes[name] = {
            "rawHits": hits[i],
            "weightedHits": h,
            "weightedIrrelevant": bad,
            "usefulPer100Estimated": 100 * h / sum(weights) if weights else None,
            "irrelevantPer100Estimated": 100 * bad / sum(weights) if weights else None,
            "retentionLower95": retention,
            "irrelevantReduction": reduction,
            "pairedNetLower95": margins,
            "unreviewedDecisionsThatCouldChangeComparison": uncertainty,
        }
    final = now >= END
    sufficient = hits[0] >= 60 and len(clusters) >= 100 and not unsupported
    return {
        "schema": "skill-filter-comparison-v1",
        "start": START.isoformat(),
        "cutoff": END.isoformat(),
        "result": (
            "collecting"
            if not final
            else "inconclusive"
            if not sufficient or not winners
            else "review_rules_only"
            if "floor@3" in winners
            else "review_candidate"
        ),
        "qualifyingCandidates": winners if final and sufficient else [],
        "authority": "report_only",
        "capturedEligible": len(frame),
        "differentVersion": unsupported,
        "reviewed": len(weights),
        "reviewedSessions": len(clusters),
        "unreviewedOrAmbiguous": len(frame) - unsupported - len(weights),
        "effectiveSampleSize": sum(weights) ** 2 / sum(w * w for w in weights) if weights else 0,
        "maxWeightShare": max(weights) / sum(weights) if weights else None,
        "policyInstrumentModel": KEY,
        "routerSha256": ROUTER,
        "indexSha256": INDEX,
        "observedStatus": dict(failures),
        "observedLatencyCount": len(latency),
        "meanObservedModelMs": statistics.mean(latency) if latency else None,
        "over800ms": sum(t > 800 for t in latency),
        "usage": None,
        "taskFamilyCoverage": "unavailable",
        "scope": "estimated rates per 100 represented opportunities; actual incremental latency and task benefit unmeasured",
        "policies": outcomes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=records.default_root())
    args = parser.parse_args()
    recs, a = cohorts.load_records(args.root)
    labels, b = cohorts.load_labels(args.root)
    events, c = records.read(args.root, "skill-fit", "cohorts")
    if a or b or c:
        raise ValueError("invalid source rows")
    reserved = {k for e in events if e["event"] == "reserve" for k in e["occurrenceKeys"]}
    reserved.update(l["occurrenceKey"] for l in labels if l["cohortId"] is not None)
    report = compare(recs, labels, reserved, datetime.now(timezone.utc))
    report["evaluatorSha256"] = hashlib.sha256(Path(cycle.__file__).read_bytes()).hexdigest()
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
