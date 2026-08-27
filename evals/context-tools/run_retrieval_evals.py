#!/usr/bin/env python3
"""Run the Phase 1.5 offline retrieval corpus against real local providers.

Arm A executes each case's reviewed ripgrep patterns. Arm B-local executes
``grepai search`` with compact JSON when the CLI is available. Provider stdout
is parsed in memory and discarded: reports retain only repository-relative
candidate metadata and byte counts, never source excerpts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
DEFAULT_CASES = EVAL_ROOT / "retrieval_cases.json"
SCHEMA_VERSION = 1
LOCAL_GATE_POLICY_VERSION = "local-retrieval-correctness-v1"
PROVIDER_SPECS = {
    "baseline": {"provider": "ripgrep", "arm": "A", "binary": "rg"},
    "grepai": {"provider": "grepai-local", "arm": "B-local", "binary": "grepai"},
}
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_SENSITIVE_INTENT = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]"
)
_ABSOLUTE_INTENT_PATH = re.compile(r"(?:^|\s)/(?:Users|home|private|var|tmp)/")


class CorpusError(ValueError):
    """The reviewed retrieval corpus does not match its strict v1 contract."""


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise CorpusError(
            f"{label} fields differ: missing={sorted(expected - actual)} "
            f"unknown={sorted(actual - expected)}"
        )


def _repository_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise CorpusError(f"{label} must be a non-empty POSIX repository-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("./") or ".." in path.parts:
        raise CorpusError(f"{label} must be repository-relative without traversal")
    return path.as_posix()


def validate_corpus(document: Any, repo: Path) -> dict[str, Any]:
    """Validate the checked-in corpus, including every ground-truth fixture path."""
    if not isinstance(document, dict):
        raise CorpusError("corpus must be a JSON object")
    _require_exact_keys(
        document,
        {"schemaVersion", "corpusId", "repository", "review", "topK", "cases"},
        "corpus",
    )
    if document["schemaVersion"] != SCHEMA_VERSION:
        raise CorpusError(f"schemaVersion must be {SCHEMA_VERSION}")
    if document["repository"] != "rhize-plugins":
        raise CorpusError("corpus repository must be rhize-plugins")
    if not isinstance(document["corpusId"], str) or not document["corpusId"]:
        raise CorpusError("corpusId must be a non-empty string")
    if not isinstance(document["topK"], int) or isinstance(document["topK"], bool):
        raise CorpusError("topK must be an integer")
    if not 1 <= document["topK"] <= 50:
        raise CorpusError("topK must be between 1 and 50")

    review = document["review"]
    if not isinstance(review, dict):
        raise CorpusError("review must be an object")
    _require_exact_keys(
        review,
        {"status", "reviewedOn", "reviewedSnapshot", "scope"},
        "review",
    )
    if review["status"] != "reviewed":
        raise CorpusError("review.status must be reviewed")
    if not isinstance(review["reviewedOn"], str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", review["reviewedOn"]
    ):
        raise CorpusError("review.reviewedOn must be an ISO date")
    if not isinstance(review["reviewedSnapshot"], str) or not _HEX_40.fullmatch(
        review["reviewedSnapshot"]
    ):
        raise CorpusError("review.reviewedSnapshot must be a full lowercase Git SHA")
    if not isinstance(review["scope"], str) or not review["scope"]:
        raise CorpusError("review.scope must be a non-empty string")

    cases = document["cases"]
    if not isinstance(cases, list) or not cases:
        raise CorpusError("cases must be a non-empty list")
    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            raise CorpusError(f"{label} must be an object")
        _require_exact_keys(
            case,
            {"id", "intent", "baselineRgGlobs", "baselineRgPatterns", "groundTruth"},
            label,
        )
        case_id = case["id"]
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", case_id):
            raise CorpusError(f"{label}.id must be kebab-case")
        if case_id in seen_ids:
            raise CorpusError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)

        intent = case["intent"]
        if not isinstance(intent, str) or not 20 <= len(intent) <= 500 or "\n" in intent:
            raise CorpusError(f"{label}.intent must be one public line of 20-500 characters")
        if _SENSITIVE_INTENT.search(intent) or _ABSOLUTE_INTENT_PATH.search(intent):
            raise CorpusError(f"{label}.intent contains private-looking material")

        globs = case["baselineRgGlobs"]
        if not isinstance(globs, list) or not globs:
            raise CorpusError(f"{label}.baselineRgGlobs must be non-empty")
        for glob_index, glob in enumerate(globs):
            glob_label = f"{label}.baselineRgGlobs[{glob_index}]"
            if (
                not isinstance(glob, str)
                or not glob
                or glob.startswith(("/", "!"))
                or "\\" in glob
                or ".." in PurePosixPath(glob).parts
            ):
                raise CorpusError(f"{glob_label} must be an inclusive repository-relative glob")

        patterns = case["baselineRgPatterns"]
        if not isinstance(patterns, list) or not patterns:
            raise CorpusError(f"{label}.baselineRgPatterns must be non-empty")
        for pattern_index, pattern in enumerate(patterns):
            pattern_label = f"{label}.baselineRgPatterns[{pattern_index}]"
            if not isinstance(pattern, dict):
                raise CorpusError(f"{pattern_label} must be an object")
            _require_exact_keys(pattern, {"pattern", "mode"}, pattern_label)
            if (
                not isinstance(pattern["pattern"], str)
                or not pattern["pattern"]
                or "\n" in pattern["pattern"]
            ):
                raise CorpusError(f"{pattern_label}.pattern must be one non-empty line")
            if pattern["mode"] not in {"fixed", "regex"}:
                raise CorpusError(f"{pattern_label}.mode must be fixed or regex")
            if pattern["mode"] == "regex":
                try:
                    re.compile(pattern["pattern"])
                except re.error as error:
                    raise CorpusError(f"{pattern_label}.pattern is invalid: {error}") from error

        truth = case["groundTruth"]
        if not isinstance(truth, list) or not truth:
            raise CorpusError(f"{label}.groundTruth must be non-empty")
        seen_paths: set[str] = set()
        for truth_index, entry in enumerate(truth):
            truth_label = f"{label}.groundTruth[{truth_index}]"
            if not isinstance(entry, dict):
                raise CorpusError(f"{truth_label} must be an object")
            _require_exact_keys(entry, {"path", "critical", "rationale"}, truth_label)
            relative = _repository_relative_path(entry["path"], f"{truth_label}.path")
            if relative in seen_paths:
                raise CorpusError(f"{label} contains duplicate ground-truth path {relative}")
            seen_paths.add(relative)
            if not (repo / relative).is_file():
                raise CorpusError(f"{truth_label}.path does not exist in the repository")
            if not isinstance(entry["critical"], bool):
                raise CorpusError(f"{truth_label}.critical must be boolean")
            if not isinstance(entry["rationale"], str) or len(entry["rationale"]) < 20:
                raise CorpusError(f"{truth_label}.rationale must explain the relevance")
    return document


def load_corpus(path: Path, repo: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CorpusError(f"could not read corpus: {error}") from error
    return validate_corpus(document, repo)


def _run_git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError("git_snapshot_failed")
    return completed.stdout


def git_snapshot(repo: Path) -> dict[str, str | None]:
    """Return commit plus a content-aware dirty hash without exposing repo paths."""
    commit = _run_git(repo, "rev-parse", "HEAD").decode().strip()
    if not _HEX_40.fullmatch(commit):
        raise RuntimeError("git_snapshot_failed")
    diff = _run_git(repo, "diff", "--binary", "HEAD", "--")
    untracked_raw = _run_git(
        repo, "ls-files", "--others", "--exclude-standard", "-z"
    )
    untracked = sorted(path for path in untracked_raw.split(b"\0") if path)
    if not diff and not untracked:
        return {"commit": commit, "dirtyTreeHash": None}
    digest = hashlib.sha256()
    digest.update(b"tracked\0")
    digest.update(diff)
    for encoded_path in untracked:
        relative = encoded_path.decode("utf-8", errors="surrogateescape")
        safe_relative = _repository_relative_path(relative, "untracked path")
        path = repo / safe_relative
        digest.update(b"untracked\0")
        digest.update(encoded_path)
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        elif path.is_file():
            digest.update(path.read_bytes())
    return {"commit": commit, "dirtyTreeHash": digest.hexdigest()}


def _normalize_candidate_path(value: Any, repo: Path) -> str | None:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            relative = candidate.resolve(strict=False).relative_to(repo.resolve())
        except ValueError:
            return None
    else:
        cleaned = value[2:] if value.startswith("./") else value
        relative = Path(cleaned)
        if relative.parts and relative.parts[0] == repo.name:
            relative = Path(*relative.parts[1:])
    if not relative.parts or ".." in relative.parts:
        return None
    normalized = PurePosixPath(*relative.parts).as_posix()
    if normalized.startswith("/"):
        return None
    return normalized


def _integer_field(record: dict[str, Any], *names: str) -> int | None:
    for name in names:
        value = record.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def parse_rg_json(stdout: bytes, repo: Path) -> list[dict[str, Any]]:
    """Parse ripgrep JSON events into deduplicated, source-free candidates."""
    candidates: dict[str, dict[str, Any]] = {}
    for line in stdout.splitlines():
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("invalid_rg_json") from error
        if not isinstance(event, dict) or event.get("type") != "match":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        path_value = data.get("path")
        raw_path = path_value.get("text") if isinstance(path_value, dict) else path_value
        path = _normalize_candidate_path(raw_path, repo)
        if path is None:
            continue
        line_number = _integer_field(data, "line_number")
        candidate = candidates.setdefault(path, {"path": path})
        if line_number is not None and "lineStart" not in candidate:
            candidate["lineStart"] = line_number
            candidate["lineEnd"] = line_number
    return list(candidates.values())


def top_k_metrics(
    candidates: list[dict[str, Any]], ground_truth: list[dict[str, Any]], top_k: int
) -> dict[str, Any]:
    relevant = {entry["path"] for entry in ground_truth}
    critical = {entry["path"] for entry in ground_truth if entry["critical"]}
    top_paths = [candidate["path"] for candidate in candidates[:top_k]]
    found = relevant.intersection(top_paths)
    return {
        "topK": top_k,
        "returnedAtK": len(top_paths),
        "relevantAtK": len(found),
        "precisionAtK": round(len(found) / top_k, 6),
        "recallAtK": round(len(found) / len(relevant), 6),
        "misses": sorted(relevant - found),
        "criticalMisses": sorted(critical - found),
    }


def _candidate_bytes(candidates: list[dict[str, Any]]) -> int:
    payload = json.dumps(candidates, sort_keys=True, separators=(",", ":"))
    return len(payload.encode("utf-8"))


def _base_row(
    case: dict[str, Any],
    spec: dict[str, str],
    version: str | None,
    snapshot: dict[str, str | None],
) -> dict[str, Any]:
    return {
        "caseId": case["id"],
        "query": case["intent"],
        "arm": spec["arm"],
        "provider": spec["provider"],
        "providerVersion": version,
        "snapshot": snapshot,
    }


def skipped_row(
    case: dict[str, Any],
    spec: dict[str, str],
    version: str | None,
    snapshot: dict[str, str | None],
    reason: str,
) -> dict[str, Any]:
    return {
        **_base_row(case, spec, version, snapshot),
        "status": "skipped",
        "skipReason": reason,
        "errorReason": None,
        "elapsedMs": None,
        "searchCalls": 0,
        "candidateCount": None,
        "candidateBytes": None,
        "resultBytes": None,
        "topK": None,
        "returnedAtK": None,
        "relevantAtK": None,
        "precisionAtK": None,
        "recallAtK": None,
        "misses": None,
        "criticalMisses": None,
        "candidates": [],
    }


def _completed_row(
    case: dict[str, Any],
    spec: dict[str, str],
    version: str,
    snapshot: dict[str, str | None],
    elapsed_ms: float,
    search_calls: int,
    result_bytes: int,
    candidates: list[dict[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    retained = candidates[:top_k]
    return {
        **_base_row(case, spec, version, snapshot),
        "status": "completed",
        "skipReason": None,
        "errorReason": None,
        "elapsedMs": round(elapsed_ms, 3),
        "searchCalls": search_calls,
        "candidateCount": len(candidates),
        "candidateBytes": _candidate_bytes(retained),
        "resultBytes": result_bytes,
        **top_k_metrics(candidates, case["groundTruth"], top_k),
        "candidates": retained,
    }


def _failed_row(
    case: dict[str, Any],
    spec: dict[str, str],
    version: str,
    snapshot: dict[str, str | None],
    elapsed_ms: float,
    search_calls: int,
    result_bytes: int,
    reason: str,
) -> dict[str, Any]:
    return {
        **_base_row(case, spec, version, snapshot),
        "status": "failed",
        "skipReason": None,
        "errorReason": reason,
        "elapsedMs": round(elapsed_ms, 3),
        "searchCalls": search_calls,
        "candidateCount": None,
        "candidateBytes": None,
        "resultBytes": result_bytes,
        "topK": None,
        "returnedAtK": None,
        "relevantAtK": None,
        "precisionAtK": None,
        "recallAtK": None,
        "misses": None,
        "criticalMisses": None,
        "candidates": [],
    }


def _elapsed_ms(started_ns: int) -> float:
    return (time.perf_counter_ns() - started_ns) / 1_000_000


def run_baseline_case(
    case: dict[str, Any],
    repo: Path,
    executable: str,
    version: str,
    snapshot: dict[str, str | None],
    top_k: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    spec = PROVIDER_SPECS["baseline"]
    started = time.perf_counter_ns()
    result_bytes = 0
    search_calls = 0
    candidates: dict[str, dict[str, Any]] = {}
    try:
        for pattern in case["baselineRgPatterns"]:
            command = [
                executable,
                "--json",
                "--line-number",
                "--sort",
                "path",
                "--color",
                "never",
            ]
            if pattern["mode"] == "fixed":
                command.append("--fixed-strings")
            for glob in case["baselineRgGlobs"]:
                command.extend(["--glob", glob])
            command.extend(["--", pattern["pattern"], "."])
            completed = subprocess.run(
                command,
                cwd=repo,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
            search_calls += 1
            result_bytes += len(completed.stdout)
            if completed.returncode not in {0, 1}:
                return _failed_row(
                    case,
                    spec,
                    version,
                    snapshot,
                    _elapsed_ms(started),
                    search_calls,
                    result_bytes,
                    "search_command_failed",
                )
            for candidate in parse_rg_json(completed.stdout, repo):
                candidates.setdefault(candidate["path"], candidate)
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, bytes) else b""
        return _failed_row(
            case,
            spec,
            version,
            snapshot,
            _elapsed_ms(started),
            search_calls + 1,
            result_bytes + len(stdout),
            "search_timeout",
        )
    except ValueError:
        return _failed_row(
            case,
            spec,
            version,
            snapshot,
            _elapsed_ms(started),
            search_calls,
            result_bytes,
            "invalid_provider_json",
        )
    return _completed_row(
        case,
        spec,
        version,
        snapshot,
        _elapsed_ms(started),
        search_calls,
        result_bytes,
        list(candidates.values()),
        top_k,
    )


def run_grepai_case(
    case: dict[str, Any],
    repo: Path,
    provider: Any,
    version: str,
    snapshot: dict[str, str | None],
    top_k: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    spec = PROVIDER_SPECS["grepai"]
    started = time.perf_counter_ns()
    try:
        result = provider.search(
            repo,
            case["intent"],
            limit=top_k,
            timeout=int(timeout_seconds),
        )
    except (RuntimeError, ValueError):
        return _failed_row(
            case,
            spec,
            version,
            snapshot,
            _elapsed_ms(started),
            1,
            0,
            "provider_search_failed",
        )
    candidates = [candidate.to_dict() for candidate in result.candidates]
    return _completed_row(
        case,
        spec,
        version,
        snapshot,
        _elapsed_ms(started),
        1,
        result.result_bytes,
        candidates,
        top_k,
    )


def provider_version(executable: str, provider: str) -> str:
    attempts = [[executable, "--version"]]
    if provider == "grepai":
        attempts.append([executable, "version"])
    for command in attempts:
        completed = subprocess.run(command, capture_output=True, check=False, timeout=10)
        if completed.returncode != 0:
            continue
        output = (completed.stdout or completed.stderr).decode("utf-8", errors="replace")
        first_line = output.strip().splitlines()[0] if output.strip() else ""
        if first_line and len(first_line) <= 200 and not _ABSOLUTE_INTENT_PATH.search(first_line):
            return first_line
    return "unreported"


def grepai_ready(executable: str, repo: Path) -> tuple[Any | None, str | None]:
    """Use the pinned adapter doctor; never initialize, index, or start services here."""
    marker_path = repo / ".grepai" / "rhize-snapshot.json"
    if marker_path.is_symlink() or not marker_path.is_file():
        return None, "provider_snapshot_unverified"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        config_sha256 = marker.get("configSha256") if isinstance(marker, dict) else None
        if not isinstance(config_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", config_sha256
        ):
            return None, "provider_snapshot_unverified"
        scripts_root = REPO_ROOT / "rhize-context-manager" / "scripts"
        if str(scripts_root) not in sys.path:
            sys.path.insert(0, str(scripts_root))
        from context_experiments.providers.grepai import (  # noqa: PLC0415
            GrepaiLayout,
            GrepaiProvider,
        )

        provider = GrepaiProvider(
            GrepaiLayout(
                config=Path(".grepai/config.yaml"),
                index=Path(".grepai/index.gob"),
                snapshot_marker=Path(".grepai/rhize-snapshot.json"),
            ),
            expected_config_sha256=config_sha256,
            executable=executable,
        )
        health = provider.doctor(repo)
    except (ImportError, OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return None, "provider_not_ready"
    if health.ready:
        return provider, None
    if "snapshot" in health.note or "index" in health.note or "config" in health.note:
        return None, "provider_snapshot_unverified"
    return None, "provider_not_ready"


def summarize_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate each provider independently; skipped rows never become evidence."""
    by_provider: list[dict[str, Any]] = []
    identities = sorted({(row["arm"], row["provider"]) for row in rows})
    for arm, provider in identities:
        provider_rows = [
            row for row in rows if row["arm"] == arm and row["provider"] == provider
        ]
        completed = [row for row in provider_rows if row["status"] == "completed"]
        by_provider.append(
            {
                "arm": arm,
                "provider": provider,
                "completedCases": len(completed),
                "failedCases": sum(row["status"] == "failed" for row in provider_rows),
                "skippedCases": sum(row["status"] == "skipped" for row in provider_rows),
                "meanPrecisionAtK": (
                    round(sum(row["precisionAtK"] for row in completed) / len(completed), 6)
                    if completed
                    else None
                ),
                "meanRecallAtK": (
                    round(sum(row["recallAtK"] for row in completed) / len(completed), 6)
                    if completed
                    else None
                ),
                "totalCriticalMisses": (
                    sum(len(row["criticalMisses"]) for row in completed)
                    if completed
                    else None
                ),
                "medianElapsedMs": (
                    round(statistics.median(row["elapsedMs"] for row in completed), 3)
                    if completed
                    else None
                ),
            }
        )
    return {
        "evidenceRows": sum(row["status"] == "completed" for row in rows),
        "failedRows": sum(row["status"] == "failed" for row in rows),
        "skippedRows": sum(row["status"] == "skipped" for row in rows),
        "byProvider": by_provider,
    }


def evaluate_local_correctness_gate(summary: dict[str, Any]) -> dict[str, Any]:
    """Apply the reviewed offline non-inferiority rule to aggregate evidence."""

    providers = {
        (row["arm"], row["provider"]): row for row in summary.get("byProvider", [])
    }
    baseline = providers.get(("A", "ripgrep"))
    candidate = providers.get(("B-local", "grepai-local"))
    if not baseline or not candidate:
        return {
            "policyVersion": LOCAL_GATE_POLICY_VERSION,
            "decision": "not_evaluable",
            "reasons": ["paired_provider_evidence_missing"],
        }
    if (
        baseline["completedCases"] == 0
        or candidate["completedCases"] != baseline["completedCases"]
        or baseline["failedCases"]
        or candidate["failedCases"]
        or baseline["skippedCases"]
        or candidate["skippedCases"]
    ):
        return {
            "policyVersion": LOCAL_GATE_POLICY_VERSION,
            "decision": "not_evaluable",
            "reasons": ["paired_provider_evidence_incomplete"],
        }

    reasons: list[str] = []
    if candidate["totalCriticalMisses"]:
        reasons.append("candidate_has_critical_misses")
    if candidate["meanRecallAtK"] < baseline["meanRecallAtK"]:
        reasons.append("candidate_recall_below_baseline")
    return {
        "policyVersion": LOCAL_GATE_POLICY_VERSION,
        "decision": "pause" if reasons else "continue_candidate",
        "reasons": reasons,
        "note": (
            "A continue_candidate decision still requires the independent privacy, "
            "resource, and indexing-safety gates."
        ),
    }


def render_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--provider",
        action="append",
        choices=tuple(PROVIDER_SPECS),
        dest="providers",
        help="Provider to run; repeat for a pair. Defaults to baseline plus grepai.",
    )
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        repo = args.repo.expanduser().resolve(strict=True)
        if args.timeout_seconds <= 0:
            raise ValueError("timeout must be positive")
        corpus = load_corpus(args.cases.expanduser().resolve(strict=True), repo)
        snapshot = git_snapshot(repo)
        if snapshot["commit"] != corpus["review"]["reviewedSnapshot"]:
            raise CorpusError("selected repository commit differs from the reviewed corpus")
    except (CorpusError, OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    cases = corpus["cases"]
    if args.case_ids:
        requested_cases = set(args.case_ids)
        cases = [case for case in cases if case["id"] in requested_cases]
        missing = requested_cases - {case["id"] for case in cases}
        if missing:
            print(f"ERROR: unknown case ids: {sorted(missing)}", file=sys.stderr)
            return 2

    requested_providers = list(dict.fromkeys(args.providers or ["baseline", "grepai"]))
    provider_states: dict[str, dict[str, Any]] = {}
    for provider_key in requested_providers:
        spec = PROVIDER_SPECS[provider_key]
        executable = shutil.which(spec["binary"])
        version = provider_version(executable, provider_key) if executable else None
        ready = executable is not None
        provider_adapter = None
        skip_reason = None if ready else "provider_unavailable"
        if provider_key == "grepai" and executable:
            provider_adapter, skip_reason = grepai_ready(executable, repo)
            ready = provider_adapter is not None
        provider_states[provider_key] = {
            **spec,
            "installed": executable is not None,
            "available": ready,
            "version": version,
            "skipReason": skip_reason,
            "executable": executable,
            "providerAdapter": provider_adapter,
        }

    rows: list[dict[str, Any]] = []
    for case in cases:
        for provider_key in requested_providers:
            state = provider_states[provider_key]
            spec = PROVIDER_SPECS[provider_key]
            if not state["available"]:
                rows.append(
                    skipped_row(
                        case, spec, state["version"], snapshot, state["skipReason"]
                    )
                )
                continue
            if provider_key == "baseline":
                rows.append(
                    run_baseline_case(
                        case,
                        repo,
                        state["executable"],
                        state["version"],
                        snapshot,
                        corpus["topK"],
                        args.timeout_seconds,
                    )
                )
            else:
                rows.append(
                    run_grepai_case(
                        case,
                        repo,
                        state["providerAdapter"],
                        state["version"],
                        snapshot,
                        corpus["topK"],
                        args.timeout_seconds,
                    )
                )

    public_provider_states = [
        {
            key: value
            for key, value in provider_states[provider].items()
            if key not in {"executable", "providerAdapter"}
        }
        for provider in requested_providers
    ]
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "benchmarkKind": "offline-paired-retrieval",
        "repository": corpus["repository"],
        "snapshot": snapshot,
        "corpus": {
            "id": corpus["corpusId"],
            "review": corpus["review"],
            "caseCount": len(cases),
            "topK": corpus["topK"],
        },
        "providers": public_provider_states,
        "summary": summarize_results(rows),
        "results": rows,
    }
    report["gate"] = evaluate_local_correctness_gate(report["summary"])
    payload = render_report(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")

    completed = report["summary"]["evidenceRows"]
    failed = report["summary"]["failedRows"]
    if completed == 0:
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
