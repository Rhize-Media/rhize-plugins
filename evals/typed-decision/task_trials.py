#!/usr/bin/env python3
"""Private coding-task A/B ledger with a 1M duplicate-control token ceiling.

Reservations stop new duplicate controls at the ceiling. A host must separately
enforce each run limit during execution; this ledger cannot interrupt an agent.
Missing usage keeps the full reservation charged and never becomes zero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sqlite3
from collections import Counter, defaultdict
from statistics import mean
from pathlib import Path
from uuid import uuid4

CAP = 1_000_000
HEX = re.compile(r"[0-9a-f]{64}\Z")
ARMS = {"A_control", "B_treatment", "A_single", "B_single"}


def file_hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1048576:
        raise ValueError("evidence file must be regular and <= 1 MiB")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("ledger path cannot be a symlink")
    prior = os.umask(0o077)
    try:
        connection = sqlite3.connect(path, timeout=15)
    finally:
        os.umask(prior)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY, task_hash TEXT NOT NULL, fixture_hash TEXT NOT NULL,
        arm TEXT NOT NULL, status TEXT NOT NULL, reserved_tokens INTEGER NOT NULL,
        input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER,
        cache_write_tokens INTEGER, reasoning_tokens INTEGER, used_tokens INTEGER,
        usage_state TEXT NOT NULL, usage_reason TEXT, usage_sha256 TEXT,
        outcome TEXT, outcome_sha256 TEXT, wall_ms INTEGER,
        quality_score REAL, required_checks_passed INTEGER,
        independent_review_passed INTEGER, critical_failure_count INTEGER,
        rework_count INTEGER, rubric_sha256 TEXT,
        host_limit_sha256 TEXT, recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(task_hash, fixture_hash, arm)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS run_telemetry (
        run_id TEXT PRIMARY KEY REFERENCES runs(run_id), packet_json TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL)""")
    connection.commit()
    return connection


def checked_hash(value: str, name: str) -> str:
    if not HEX.fullmatch(value):
        raise ValueError(f"{name} must be lowercase SHA-256")
    return value


def budget_used(db: sqlite3.Connection) -> int:
    row = db.execute("""SELECT COALESCE(SUM(CASE WHEN arm='A_control'
        THEN COALESCE(used_tokens, reserved_tokens) ELSE 0 END),0) FROM runs""").fetchone()
    return int(row[0])


def reserve_control(db: sqlite3.Connection, task_hash: str, fixture_hash: str,
                    limit_tokens: int, host_limit_evidence: Path) -> dict:
    checked_hash(task_hash, "task_hash")
    checked_hash(fixture_hash, "fixture_hash")
    if type(limit_tokens) is not int or limit_tokens <= 0 or limit_tokens > CAP:
        raise ValueError("run limit must be between 1 and 1000000")
    host_hash = file_hash(host_limit_evidence)
    db.execute("BEGIN IMMEDIATE")
    try:
        before = budget_used(db)
        if before + limit_tokens > CAP:
            raise ValueError("duplicate-control token ceiling exhausted")
        run_id = uuid4().hex
        db.execute("""INSERT INTO runs
            (run_id, task_hash, fixture_hash, arm, status, reserved_tokens,
             usage_state, host_limit_sha256)
            VALUES (?, ?, ?, 'A_control', 'reserved', ?, 'pending', ?)""",
            (run_id, task_hash, fixture_hash, limit_tokens, host_hash))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"runId": run_id, "arm": "A_control", "reservedTokens": limit_tokens,
            "budgetUsedOrReserved": before + limit_tokens, "remainingTokens": CAP - before - limit_tokens,
            "hostLimitEvidenceSha256": host_hash,
            "warning": "the host must enforce this per-run token limit; reservation alone cannot interrupt an agent"}


def usage_from_file(path: Path | None) -> tuple[dict | None, str | None]:
    if path is None:
        return None, None
    digest = file_hash(path)
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) != {
        "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens"
    }:
        raise ValueError("usage must have the five recorded token fields")
    if any(item is not None and (type(item) is not int or item < 0) for item in value.values()):
        raise ValueError("invalid token usage")
    return value, digest


def outcome_from_file(path: Path, declared: str) -> tuple[dict, str]:
    digest = file_hash(path)
    value = json.loads(path.read_text())
    required = {"schema", "outcome", "quality_score", "required_checks_passed",
                "independent_review_passed", "critical_failure_count", "rework_count",
                "rubric_sha256"}
    if not isinstance(value, dict) or set(value) != required or value["schema"] != "rhize-typed-task-outcome-v1":
        raise ValueError("invalid task outcome evidence schema")
    if value["outcome"] != declared or not isinstance(value["rubric_sha256"], str) or not HEX.fullmatch(value["rubric_sha256"]):
        raise ValueError("outcome or frozen rubric mismatch")
    if (type(value["required_checks_passed"]) is not bool
            or type(value["independent_review_passed"]) is not bool
            or any(type(value[key]) is not int or value[key] < 0
                   for key in ("critical_failure_count", "rework_count"))):
        raise ValueError("invalid task outcome gate evidence")
    quality = value["quality_score"]
    if quality is not None and (isinstance(quality, bool) or not isinstance(quality, (int, float)) or not 0 <= quality <= 100):
        raise ValueError("quality score must be 0 to 100 or null")
    if declared == "accepted" and (quality is None or not value["required_checks_passed"]
                                   or not value["independent_review_passed"]
                                   or value["critical_failure_count"]):
        raise ValueError("accepted outcome requires scored quality and passed gates")
    return value, digest


def telemetry_from_file(path: Path | None) -> tuple[dict | None, str | None]:
    if path is None:
        return None, None
    digest = file_hash(path)
    value = json.loads(path.read_text())
    numeric = {'local_inference_ms', 'local_forward_passes', 'provider_cost_usd', 'review_cost_usd', 'local_cost_usd'}
    if (not isinstance(value, dict) or set(value) != numeric | {'schema', 'advice_exposure', 'advice_following'}
            or value['schema'] != 'rhize-task-telemetry-v1'
            or not isinstance(value['advice_exposure'], str) or not isinstance(value['advice_following'], str)
            or value['advice_exposure'] not in {'shown', 'holdback', 'not_shown', 'unknown'}
            or value['advice_following'] not in {'followed', 'overrode', 'unknown'}
            or (value['advice_exposure'] != 'shown' and value['advice_following'] != 'unknown')):
        raise ValueError('invalid task telemetry schema or exposure')
    for key in numeric:
        item = value[key]
        if item is not None and (type(item) not in (int, float) or not math.isfinite(item) or item < 0
                                 or (key == 'local_forward_passes' and type(item) is not int)):
            raise ValueError('invalid task telemetry metric')
    return value, digest


def finish(db: sqlite3.Connection, run_id: str, arm: str, status: str, task_hash: str | None,
           fixture_hash: str | None, usage_file: Path | None, usage_reason: str | None,
           outcome: str, outcome_evidence: Path, wall_ms: int | None, *, telemetry_file: Path | None = None) -> dict:
    if arm not in ARMS or status not in {"completed", "failed", "incomplete"}:
        raise ValueError("invalid arm or terminal status")
    if outcome not in {"accepted", "rejected", "undetermined"}:
        raise ValueError("outcome must be accepted, rejected or undetermined")
    if wall_ms is not None and (type(wall_ms) is not int or wall_ms < 0):
        raise ValueError("wall time must be nonnegative")
    outcome_packet, outcome_hash = outcome_from_file(outcome_evidence, outcome)
    telemetry, telemetry_hash = telemetry_from_file(telemetry_file)
    usage, usage_hash = usage_from_file(usage_file)
    complete_usage = usage is not None and type(usage["input_tokens"]) is int and type(usage["output_tokens"]) is int
    if not complete_usage and (not usage_reason or not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", usage_reason)):
        raise ValueError("missing input/output usage needs an explicit reason")
    used = usage["input_tokens"] + usage["output_tokens"] if complete_usage else None
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if arm == "A_control":
            if row is None or row["arm"] != arm or row["status"] != "reserved":
                raise ValueError("control must have a pending matching reservation")
            if used is not None and used > row["reserved_tokens"]:
                # Record the actual overrun; never hide it or make a second control possible.
                usage_reason = "host_limit_overrun"
            task_hash, fixture_hash = row["task_hash"], row["fixture_hash"]
        else:
            if row is not None:
                raise ValueError("run id already exists")
            checked_hash(task_hash or "", "task_hash")
            checked_hash(fixture_hash or "", "fixture_hash")
            db.execute("""INSERT INTO runs
                (run_id, task_hash, fixture_hash, arm, status, reserved_tokens,
                 usage_state, outcome_sha256)
                VALUES (?, ?, ?, ?, 'reserved', 0, 'pending', ?)""",
                (run_id, task_hash, fixture_hash, arm, outcome_hash))
        values = usage or {}
        db.execute("""UPDATE runs SET status=?, input_tokens=?, output_tokens=?,
            cache_read_tokens=?, cache_write_tokens=?, reasoning_tokens=?, used_tokens=?,
            usage_state=?, usage_reason=?, usage_sha256=?, outcome=?, outcome_sha256=?, wall_ms=?,
            quality_score=?, required_checks_passed=?, independent_review_passed=?,
            critical_failure_count=?, rework_count=?, rubric_sha256=?
            WHERE run_id=?""", (status, values.get("input_tokens"), values.get("output_tokens"),
            values.get("cache_read_tokens"), values.get("cache_write_tokens"),
            values.get("reasoning_tokens"), used,
            "reported" if complete_usage else "missing", usage_reason, usage_hash,
            outcome, outcome_hash, wall_ms, outcome_packet["quality_score"],
            int(outcome_packet["required_checks_passed"]),
            int(outcome_packet["independent_review_passed"]),
            outcome_packet["critical_failure_count"], outcome_packet["rework_count"],
            outcome_packet["rubric_sha256"], run_id))
        if telemetry is not None:
            db.execute('INSERT INTO run_telemetry VALUES (?, ?, ?)',
                       (run_id, json.dumps(telemetry, sort_keys=True), telemetry_hash))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"runId": run_id, "arm": arm, "status": status,
            "usageState": "reported" if complete_usage else "missing", "usedTokens": used,
            "budgetUsedOrReserved": budget_used(db), "remainingTokens": max(0, CAP - budget_used(db)),
            "capOverrun": budget_used(db) > CAP}


def paired_uncertainty(pairs) -> dict:
    tasks = defaultdict(list)
    for arms in pairs:
        a, b = arms['A_control'], arms['B_treatment']
        tasks[a['task_hash']].append({'qualityScore': b['quality_score'] - a['quality_score'],
                                     'codingTokens': b['used_tokens'] - a['used_tokens'],
                                     'wallMs': b['wall_ms'] - a['wall_ms']})
    groups = [{key: mean(v[key] for v in values) for key in values[0]} for _, values in sorted(tasks.items())]
    result = {'independentTasks': len(groups), 'method': 'task-cluster percentile bootstrap; equal task weighting',
              'resamples': 1000, 'seed': 0, 'intervals95': None,
              'claimScope': 'descriptive complete matched pairs; small samples do not establish benefit'}
    if len(groups) < 2:
        return {**result, 'reason': 'too_few_independent_tasks'}
    rng = random.Random(0)
    draws = [rng.choices(groups, k=len(groups)) for _ in range(1000)]
    intervals = {}
    for key in groups[0]:
        values = sorted(mean(row[key] for row in draw) for draw in draws)
        intervals[key] = [values[24], values[974]]
    return {**result, 'point': {key: mean(g[key] for g in groups) for key in groups[0]}, 'intervals95': intervals}


def arm_summary(rows, telemetry) -> dict:
    packets = [telemetry.get(row['run_id']) for row in rows]
    def known(values):
        return sum(values) if values and all(v is not None for v in values) else None
    costs = known([known([p['provider_cost_usd'], p['review_cost_usd'], p['local_cost_usd']])
                   if p else None for p in packets])
    accepted = sum(row['outcome'] == 'accepted' for row in rows)
    return {'runs': len(rows), 'statuses': dict(Counter(row['status'] for row in rows)),
            'outcomes': dict(Counter(row['outcome'] or 'pending' for row in rows)),
            'criticalFailures': known([r['critical_failure_count'] for r in rows]),
            'rework': known([r['rework_count'] for r in rows]),
            'codingTokens': known([r['used_tokens'] for r in rows]),
            'cacheReadTokens': known([r['cache_read_tokens'] for r in rows]),
            'wallMs': known([r['wall_ms'] for r in rows]), 'telemetryMissing': sum(p is None for p in packets),
            'adviceExposure': dict(Counter(p['advice_exposure'] if p else 'unknown' for p in packets)),
            'adviceFollowing': dict(Counter(p['advice_following'] if p else 'unknown' for p in packets)),
            'localInferenceMs': known([p['local_inference_ms'] if p else None for p in packets]),
            'localForwardPasses': known([p['local_forward_passes'] if p else None for p in packets]),
            'recordedCostUsd': costs,
            'recordedCostPerAcceptedTaskUsd': costs / accepted if costs is not None and accepted else None,
            'costBasis': 'operator-reported disjoint provider/review/local marginal costs; missing stays null'}


def report(db: sqlite3.Connection) -> dict:
    rows = db.execute("SELECT * FROM runs ORDER BY recorded_at, run_id").fetchall()
    used = budget_used(db)
    matched = {}
    for row in rows:
        key = (row["task_hash"], row["fixture_hash"])
        matched.setdefault(key, {})[row["arm"]] = row
    def evaluable(row: sqlite3.Row) -> bool:
        return (row["status"] == "completed" and row["usage_state"] == "reported"
                and row["outcome"] in {"accepted", "rejected"}
                and row["quality_score"] is not None and row["wall_ms"] is not None)
    paired = [arms for arms in matched.values() if {"A_control", "B_treatment"} <= arms.keys()]
    eligible = [arms for arms in paired if evaluable(arms["A_control"])
                and evaluable(arms["B_treatment"])
                and arms["A_control"]["rubric_sha256"] == arms["B_treatment"]["rubric_sha256"]]
    singles = [row for row in rows if row["arm"] in {"A_single", "B_single"} and evaluable(row)]
    telemetry = {r['run_id']: json.loads(r['packet_json']) for r in db.execute('SELECT * FROM run_telemetry')}
    return {"schema": "rhize-typed-task-trials-v1", "controlCap": CAP,
            "budgetUsedOrReserved": used, "remainingTokens": max(0, CAP - used),
            "capOverrun": used > CAP,
            "runs": len(rows), "pendingControls": sum(row["arm"] == "A_control" and row["status"] == "reserved" for row in rows),
            "missingUsage": sum(row["usage_state"] == "missing" for row in rows),
            "reportedUsage": sum(row["usage_state"] == "reported" for row in rows),
            "pairedGroups": len(paired), "evaluablePairs": len(eligible),
            "pairedMeanDeltaBMinusA": ({
                "qualityScore": mean(arms["B_treatment"]["quality_score"] - arms["A_control"]["quality_score"] for arms in eligible),
                "codingTokens": mean(arms["B_treatment"]["used_tokens"] - arms["A_control"]["used_tokens"] for arms in eligible),
                "wallMs": mean(arms["B_treatment"]["wall_ms"] - arms["A_control"]["wall_ms"] for arms in eligible),
            } if eligible else None),
            "pairedUncertainty": paired_uncertainty(eligible),
            "byArm": {arm: arm_summary([r for r in rows if r['arm'] == arm], telemetry)
                      for arm in sorted({r['arm'] for r in rows})},
            "singleExecutionGroups": sum(bool({"A_single", "B_single"} & arms.keys()) for arms in matched.values()),
            "evaluableSingleRuns": len(singles),
            "claimScope": "operator-reported task outcomes and usage; no independent quality attestation"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path.home() / ".local/share/rhize/typed-decisions/task-trials.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    reserve = commands.add_parser("reserve-control")
    reserve.add_argument("--task-hash", required=True)
    reserve.add_argument("--fixture-hash", required=True)
    reserve.add_argument("--limit-tokens", type=int, required=True)
    reserve.add_argument("--host-limit-evidence", type=Path, required=True)
    final = commands.add_parser("finalize")
    final.add_argument("--run-id", required=True)
    final.add_argument("--arm", choices=sorted(ARMS), required=True)
    final.add_argument("--status", choices=("completed", "failed", "incomplete"), required=True)
    final.add_argument("--task-hash")
    final.add_argument("--fixture-hash")
    final.add_argument("--usage-file", type=Path)
    final.add_argument("--usage-unavailable-reason")
    final.add_argument("--outcome", choices=("accepted", "rejected", "undetermined"), required=True)
    final.add_argument("--outcome-evidence", type=Path, required=True)
    final.add_argument("--wall-ms", type=int)
    final.add_argument("--telemetry-file", type=Path, help="optional source-bound cost/exposure packet; unknown values stay null")
    commands.add_parser("report")
    args = parser.parse_args()
    try:
        with database(args.db) as db:
            if args.command == "reserve-control":
                value = reserve_control(db, args.task_hash, args.fixture_hash,
                                        args.limit_tokens, args.host_limit_evidence)
            elif args.command == "finalize":
                value = finish(db, args.run_id, args.arm, args.status, args.task_hash,
                               args.fixture_hash, args.usage_file, args.usage_unavailable_reason,
                               args.outcome, args.outcome_evidence, args.wall_ms, telemetry_file=args.telemetry_file)
            else:
                value = report(db)
        print(json.dumps(value, sort_keys=True))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "reasonCode": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
