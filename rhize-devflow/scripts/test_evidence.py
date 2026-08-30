#!/usr/bin/env python3
"""Produce and validate fail-closed, state-bound test-evidence packets."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rhize-test-evidence-v1"
RUN_SPEC_VERSION = "rhize-test-evidence-run-v1"
RUNNER_VERSION = "1.1.0"
VERDICTS = {
    "oracle_supported", "killed", "survived_mutation", "oracle_missing", "artifact_contract",
    "not_applicable", "mutation_unavailable", "mutation_unavailable_dirty_state", "stale_packet",
    "cleanup_failed", "execution_unavailable",
}
EXECUTION_CLAIM_VERDICTS = {"oracle_supported", "killed", "survived_mutation", "artifact_contract"}
CONTRACT_CLASSES = {"behavior", "artifact", "structural"}
ORACLE_KINDS = {"independent", "artifact", "missing", "not_applicable"}
ORACLES_BY_CONTRACT = {
    "behavior": {"independent", "missing"},
    "artifact": {"artifact"},
    "structural": {"independent", "missing", "not_applicable"},
}
SAFE_SCRIPT = re.compile(r"^test(?::[A-Za-z0-9:_-]+)?$")
PROTECTED = (
    re.compile(r"^\.github/workflows/"), re.compile(r"(?i)(^|/)\.env[^/]*$"),
    re.compile(r"(?i)(^|/)(billing|payment)s?(/|$)"),
    re.compile(r"(?i)(^|/)(migrations?|generated|deploy(?:ment)?)(/|$)"),
    re.compile(r"(?i)(^|/)(vercel\.json|dockerfile|[^/]+\.sql)$"),
)


class EvidenceError(ValueError):
    """Input or stored evidence violates the test-evidence contract."""


def exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise EvidenceError(f"{label} keys invalid")
    return value


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def is_hex_digest(value: Any, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def head_sha(repo: Path) -> str:
    result = run_git(repo, "rev-parse", "HEAD")
    if result.returncode or not re.fullmatch(r"[0-9a-f]{40}", result.stdout.strip()):
        raise EvidenceError("repository needs a valid HEAD")
    return result.stdout.strip()


def working_fingerprint(repo: Path) -> tuple[str, bool]:
    status = run_git(repo, "status", "--porcelain", "--untracked-files=all")
    diff = run_git(repo, "diff", "--binary", "HEAD")
    if status.returncode or diff.returncode:
        raise EvidenceError("cannot inspect repository state")
    payload = (head_sha(repo) + "\n" + status.stdout + "\n" + diff.stdout).encode()
    return hashlib.sha256(payload).hexdigest(), not bool(status.stdout.strip())


def reject_symlink_components(path: Path, label: str, *, stop: Path | None = None) -> None:
    """Reject an existing symlink at the path or in its parent chain."""
    current = path
    while True:
        if current.is_symlink():
            raise EvidenceError(f"{label} cannot use a symlink path or parent")
        if current == stop or current.parent == current:
            return
        current = current.parent


def resolve_file(repo: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise EvidenceError(f"{label} must be a relative path")
    root = repo.resolve()
    unresolved = root / relative
    reject_symlink_components(unresolved, label, stop=root)
    path = unresolved.resolve()
    if path != root and root not in path.parents:
        raise EvidenceError(f"{label} escapes the repository")
    if not path.is_file():
        raise EvidenceError(f"{label} does not exist")
    return path


def is_within(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    root = root.resolve()
    return resolved == root or root in resolved.parents


def protected(path: str) -> bool:
    return any(pattern.search(path) for pattern in PROTECTED)


def repository_relative(repo: Path, path: Path) -> str:
    return path.relative_to(repo.resolve()).as_posix()


def file_records(repo: Path, paths: list[Any], label: str) -> list[dict[str, str]]:
    if not isinstance(paths, list):
        raise EvidenceError(f"{label} must be an array")
    records = []
    for value in paths:
        path = resolve_file(repo, value, label)
        records.append({"path": repository_relative(repo, path), "sha256": file_digest(path)})
    return records


def package_script(repo: Path, name: str) -> str:
    if not isinstance(name, str) or not SAFE_SCRIPT.fullmatch(name):
        raise EvidenceError("only named test or test:* package scripts are approved")
    package_path = resolve_file(repo, "package.json", "package.json")
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if not isinstance(package, dict) or not isinstance(package.get("scripts"), dict):
        raise EvidenceError("package.json scripts must be an object")
    script = package["scripts"].get(name)
    if not isinstance(script, str) or not script:
        raise EvidenceError("approved test script is not declared by package.json")
    return script


def run_process(_command: list[str], _cwd: Path, _timeout: int) -> int:
    """Reserved adapter boundary; direct ambient process execution is disabled."""
    raise EvidenceError("test execution unavailable: no trusted sandbox adapter is configured")


def validate_spec(raw: Any, repo: Path) -> dict[str, Any]:
    keys = {"schema_version", "base_sha", "contract_class", "invariant", "test_files", "production_files", "oracle", "mutation", "test_invocation", "timeout_seconds"}
    spec = exact(raw, keys, "run spec")
    if (
        spec["schema_version"] != RUN_SPEC_VERSION
        or not isinstance(spec["contract_class"], str)
        or spec["contract_class"] not in CONTRACT_CLASSES
    ):
        raise EvidenceError("invalid run spec identity")
    if not isinstance(spec["invariant"], str) or not spec["invariant"].strip():
        raise EvidenceError("invariant is required")
    oracle = exact(spec["oracle"], {"kind", "evidence"}, "oracle")
    if (
        not isinstance(oracle["kind"], str)
        or oracle["kind"] not in ORACLE_KINDS
        or (
            oracle["evidence"] is not None
            and (not isinstance(oracle["evidence"], str) or len(oracle["evidence"]) > 20_000)
        )
    ):
        raise EvidenceError("invalid oracle")
    if oracle["kind"] == "missing":
        if oracle["evidence"] is not None:
            raise EvidenceError("missing oracle must use evidence=null")
    elif not oracle["evidence"] or not oracle["evidence"].strip():
        raise EvidenceError("declared oracle requires bounded evidence")
    if oracle["kind"] not in ORACLES_BY_CONTRACT[spec["contract_class"]]:
        raise EvidenceError("oracle kind does not match the contract class")
    invocation = exact(spec["test_invocation"], {"source", "name"}, "test_invocation")
    if invocation["source"] != "package_script":
        raise EvidenceError("test invocation must come from package_script")
    package_script(repo, invocation["name"])
    if isinstance(spec["timeout_seconds"], bool) or not isinstance(spec["timeout_seconds"], int) or not 1 <= spec["timeout_seconds"] <= 1800:
        raise EvidenceError("timeout_seconds must be 1..1800")
    if not isinstance(spec["base_sha"], str) or run_git(repo, "rev-parse", "--verify", spec["base_sha"]).returncode:
        raise EvidenceError("base_sha does not resolve")
    if run_git(repo, "merge-base", "--is-ancestor", spec["base_sha"], "HEAD").returncode:
        raise EvidenceError("base_sha must be an ancestor of HEAD")
    file_records(repo, spec["test_files"], "test_files")
    file_records(repo, spec["production_files"], "production_files")
    mutation = spec["mutation"]
    if mutation is not None:
        if spec["contract_class"] != "behavior":
            raise EvidenceError("isolated mutation is limited to behavior contracts")
        mutation = exact(mutation, {"target_path", "search", "replace", "external_effect"}, "mutation")
        if mutation["external_effect"] is not False or not isinstance(mutation["target_path"], str):
            raise EvidenceError("mutation target is protected or effectful")
        target = resolve_file(repo, mutation["target_path"], "mutation.target_path")
        canonical_target = repository_relative(repo, target)
        if protected(canonical_target):
            raise EvidenceError("mutation target is protected or effectful")
        production_paths = {
            repository_relative(repo, resolve_file(repo, path, "production_files"))
            for path in spec["production_files"]
        }
        if canonical_target not in production_paths:
            raise EvidenceError("mutation target must be listed in production_files")
        for field in ("search", "replace"):
            if not isinstance(mutation[field], str) or len(mutation[field]) > 20_000:
                raise EvidenceError(f"mutation.{field} must be bounded text")
        if not mutation["search"] or target.read_text(encoding="utf-8").count(mutation["search"]) != 1:
            raise EvidenceError("mutation search must match exactly once")
    return spec


def base_packet(
    repo: Path,
    spec: dict[str, Any],
    verdict: str,
    *,
    fingerprint: str,
    clean_before: bool,
) -> dict[str, Any]:
    oracle = spec["oracle"]
    mutation = spec["mutation"]
    return {
        "schema_version": SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": {
            "base_sha": run_git(repo, "rev-parse", spec["base_sha"]).stdout.strip(),
            "head_sha": head_sha(repo),
            "working_tree_fingerprint": fingerprint,
            "final_working_tree_fingerprint": fingerprint,
        },
        "contract": {
            "class": spec["contract_class"], "invariant_digest": digest_text(spec["invariant"]),
            "test_files": file_records(repo, spec["test_files"], "test_files"),
            "production_files": file_records(repo, spec["production_files"], "production_files"),
            "oracle": {"kind": oracle["kind"], "evidence_digest": digest_text(oracle["evidence"]) if oracle["evidence"] else None},
        },
        "mutation": None if mutation is None else {
            "target_path": repository_relative(
                repo, resolve_file(repo, mutation["target_path"], "mutation.target_path")
            ),
            "patch_digest": digest_text(mutation["search"] + "\0" + mutation["replace"]),
            "state_before_fingerprint": None,
            "state_after_fingerprint": None,
        },
        "invocation": {
            "source": "package_script",
            "name": spec["test_invocation"]["name"],
            "script_digest": digest_text(package_script(repo, spec["test_invocation"]["name"])),
        },
        "lifecycle": {"clean_before": clean_before, "isolated": False, "lease_acquired": False, "clean_after": False, "final_clean_rerun": False},
        "verdict": verdict,
        "baseline_test_exit_code": None, "mutation_test_exit_code": None, "final_test_exit_code": None,
        "cleanup": {"status": "not_started", "human_recovery_required": False},
    }


def write_packet(path: Path, packet: dict[str, Any]) -> None:
    path = path.absolute()
    reject_symlink_components(path, "output")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    reject_symlink_components(path, "output")
    if path.exists() or path.is_symlink():
        raise EvidenceError("output already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        payload = (json.dumps(packet, indent=2, sort_keys=True) + "\n").encode()
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("packet write made no progress")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_json_file(path: Path, label: str) -> Any:
    path = path.absolute()
    reject_symlink_components(path, label)
    if not path.is_file():
        raise EvidenceError(f"{label} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def run_evidence(repo: Path, spec: dict[str, Any], output: Path, lease_root: Path) -> dict[str, Any]:
    output = output.absolute()
    lease_root = lease_root.absolute()
    reject_symlink_components(output, "output")
    reject_symlink_components(lease_root, "lease root")
    if is_within(output, repo) or is_within(lease_root, repo):
        raise EvidenceError("packet output and lease root must stay outside the target repository")
    initial_fingerprint, clean = working_fingerprint(repo)
    packet = base_packet(
        repo,
        spec,
        "mutation_unavailable_dirty_state" if not clean else "execution_unavailable",
        fingerprint=initial_fingerprint,
        clean_before=clean,
    )
    if not clean:
        write_packet(output, packet)
        return packet
    final_fingerprint, final_clean = working_fingerprint(repo)
    packet["repository"]["final_working_tree_fingerprint"] = final_fingerprint
    packet["cleanup"] = {"status": "ok", "human_recovery_required": False}
    packet["lifecycle"]["clean_after"] = final_clean
    if final_fingerprint != initial_fingerprint:
        packet["verdict"] = "stale_packet"
    write_packet(output, packet)
    return packet


def validate_packet(raw: Any, repo: Path) -> dict[str, Any]:
    top = {"schema_version", "runner_version", "generated_at", "repository", "contract", "mutation", "invocation", "lifecycle", "verdict", "baseline_test_exit_code", "mutation_test_exit_code", "final_test_exit_code", "cleanup"}
    packet = exact(raw, top, "packet")
    if (
        packet["schema_version"] != SCHEMA_VERSION
        or packet["runner_version"] != RUNNER_VERSION
        or not isinstance(packet["verdict"], str)
        or packet["verdict"] not in VERDICTS
    ):
        raise EvidenceError("unknown packet version or verdict")
    try:
        generated_at = dt.datetime.fromisoformat(packet["generated_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise EvidenceError("generated_at must be a timezone-aware timestamp") from exc
    if generated_at.tzinfo is None:
        raise EvidenceError("generated_at must be a timezone-aware timestamp")
    repository = exact(
        packet["repository"],
        {"base_sha", "head_sha", "working_tree_fingerprint", "final_working_tree_fingerprint"},
        "repository",
    )
    if any(not is_hex_digest(repository[key], 40) for key in ("base_sha", "head_sha")):
        raise EvidenceError("repository SHAs must be full lowercase Git SHAs")
    if not is_hex_digest(repository["working_tree_fingerprint"], 64):
        raise EvidenceError("working_tree_fingerprint must be sha256")
    if (
        repository["final_working_tree_fingerprint"] is not None
        and not is_hex_digest(repository["final_working_tree_fingerprint"], 64)
    ):
        raise EvidenceError("final_working_tree_fingerprint must be sha256 or null")
    if any(run_git(repo, "cat-file", "-e", sha + "^{commit}").returncode for sha in (repository["base_sha"], repository["head_sha"])):
        raise EvidenceError("packet references an unavailable commit")
    current_fingerprint, _ = working_fingerprint(repo)
    stale = (
        repository["head_sha"] != head_sha(repo)
        or repository["working_tree_fingerprint"] != current_fingerprint
        or repository["final_working_tree_fingerprint"] != current_fingerprint
    )
    contract = exact(packet["contract"], {"class", "invariant_digest", "test_files", "production_files", "oracle"}, "contract")
    if (
        not isinstance(contract["class"], str)
        or contract["class"] not in CONTRACT_CLASSES
        or not is_hex_digest(contract["invariant_digest"], 64)
    ):
        raise EvidenceError("invalid contract class")
    oracle = exact(contract["oracle"], {"kind", "evidence_digest"}, "contract.oracle")
    if not isinstance(oracle["kind"], str) or oracle["kind"] not in ORACLE_KINDS or (
        oracle["evidence_digest"] is not None
        and not is_hex_digest(oracle["evidence_digest"], 64)
    ):
        raise EvidenceError("invalid packet oracle")
    if (oracle["kind"] == "missing") != (oracle["evidence_digest"] is None):
        raise EvidenceError("packet oracle kind conflicts with its evidence digest")
    if oracle["kind"] not in ORACLES_BY_CONTRACT[contract["class"]]:
        raise EvidenceError("packet oracle kind does not match the contract class")
    bound_paths: dict[str, set[str]] = {}
    for group in ("test_files", "production_files"):
        if not isinstance(contract[group], list):
            raise EvidenceError(f"contract.{group} must be an array")
        bound_paths[group] = set()
        for record in contract[group]:
            record = exact(record, {"path", "sha256"}, f"contract.{group} record")
            if not is_hex_digest(record["sha256"], 64):
                raise EvidenceError(f"contract.{group} digest must be sha256")
            bound_file = resolve_file(repo, record["path"], group)
            bound_paths[group].add(repository_relative(repo, bound_file))
            if file_digest(bound_file) != record["sha256"]:
                stale = True
    if packet["mutation"] is not None:
        mutation = exact(
            packet["mutation"],
            {"target_path", "patch_digest", "state_before_fingerprint", "state_after_fingerprint"},
            "packet.mutation",
        )
        if not isinstance(mutation["target_path"], str) or not is_hex_digest(mutation["patch_digest"], 64):
            raise EvidenceError("invalid packet mutation")
        mutation_target = resolve_file(repo, mutation["target_path"], "packet.mutation.target_path")
        canonical_target = repository_relative(repo, mutation_target)
        if protected(canonical_target) or canonical_target not in bound_paths["production_files"]:
            raise EvidenceError("invalid packet mutation")
        for field in ("state_before_fingerprint", "state_after_fingerprint"):
            if mutation[field] is not None and not is_hex_digest(mutation[field], 64):
                raise EvidenceError(f"packet.mutation.{field} must be sha256 or null")
    invocation = exact(packet["invocation"], {"source", "name", "script_digest"}, "invocation")
    if (
        invocation["source"] != "package_script"
        or not isinstance(invocation["name"], str)
        or not SAFE_SCRIPT.fullmatch(invocation["name"])
        or not is_hex_digest(invocation["script_digest"], 64)
    ):
        raise EvidenceError("invalid packet invocation")
    if digest_text(package_script(repo, invocation["name"])) != invocation["script_digest"]:
        raise EvidenceError("packet test invocation has drifted")
    lifecycle = exact(packet["lifecycle"], {"clean_before", "isolated", "lease_acquired", "clean_after", "final_clean_rerun"}, "lifecycle")
    if any(not isinstance(lifecycle[key], bool) for key in lifecycle):
        raise EvidenceError("lifecycle values must be booleans")
    cleanup = exact(packet["cleanup"], {"status", "human_recovery_required"}, "cleanup")
    if (
        not isinstance(cleanup["status"], str)
        or cleanup["status"] not in {"ok", "failed", "not_started"}
        or not isinstance(cleanup["human_recovery_required"], bool)
    ):
        raise EvidenceError("invalid cleanup state")
    for field in ("baseline_test_exit_code", "mutation_test_exit_code", "final_test_exit_code"):
        if packet[field] is not None and (isinstance(packet[field], bool) or not isinstance(packet[field], int)):
            raise EvidenceError(f"{field} must be an integer or null")
    verdict = packet["verdict"]
    if verdict in EXECUTION_CLAIM_VERDICTS:
        raise EvidenceError("execution-backed verdicts require a trusted sandbox adapter")
    clean_nonmutation = (
        packet["mutation"] is None
        and lifecycle["clean_before"]
        and lifecycle["clean_after"]
        and cleanup["status"] == "ok"
    )
    if cleanup["status"] == "ok" and cleanup["human_recovery_required"]:
        raise EvidenceError("successful cleanup cannot require human recovery")
    if verdict == "cleanup_failed":
        if cleanup["status"] != "failed" or not cleanup["human_recovery_required"]:
            raise EvidenceError("cleanup_failed requires named human recovery")
    elif cleanup["status"] == "failed" or repository["final_working_tree_fingerprint"] is None:
        raise EvidenceError("failed or incomplete cleanup requires cleanup_failed")
    if verdict == "not_applicable":
        if contract["class"] != "structural" or oracle["kind"] != "not_applicable" or not clean_nonmutation:
            raise EvidenceError("not_applicable has inconsistent contract evidence")
    elif verdict == "oracle_missing":
        if oracle["kind"] != "missing" or not clean_nonmutation:
            raise EvidenceError("oracle_missing requires a clean missing-oracle contract")
    elif verdict == "mutation_unavailable_dirty_state":
        if lifecycle["clean_before"] or lifecycle["isolated"] or cleanup["status"] != "not_started":
            raise EvidenceError("dirty-state verdict has inconsistent lifecycle evidence")
    elif verdict == "execution_unavailable":
        mutation_state = packet["mutation"] is not None and any(
            packet["mutation"][field] is not None
            for field in ("state_before_fingerprint", "state_after_fingerprint")
        )
        if (
            not lifecycle["clean_before"]
            or not lifecycle["clean_after"]
            or lifecycle["isolated"]
            or lifecycle["lease_acquired"]
            or lifecycle["final_clean_rerun"]
            or cleanup["status"] != "ok"
            or mutation_state
            or any(packet[field] is not None for field in (
                "baseline_test_exit_code", "mutation_test_exit_code", "final_test_exit_code"
            ))
        ):
            raise EvidenceError("execution_unavailable has inconsistent lifecycle evidence")
    elif verdict == "stale_packet" and not stale:
        raise EvidenceError("stale_packet verdict requires state drift")
    if packet["verdict"] == "cleanup_failed" or cleanup["status"] == "failed":
        review_verdict = "FAIL_REQUIRES_HUMAN"
    elif stale:
        review_verdict = "stale_packet"
    else:
        review_verdict = "unsupported"
    return {"valid": True, "packet_verdict": packet["verdict"], "review_verdict": review_verdict, "stale": stale}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--repo", type=Path, required=True)
    run.add_argument("--spec", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--lease-root", type=Path, default=Path.home() / ".rhize/test-evidence/leases")
    validate = sub.add_parser("validate")
    validate.add_argument("--repo", type=Path, required=True)
    validate.add_argument("--packet", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        repo_path = args.repo.absolute()
        reject_symlink_components(repo_path, "repo")
        repo = repo_path.resolve()
        if run_git(repo, "rev-parse", "--show-toplevel").returncode:
            raise EvidenceError("repo is not a Git repository")
        if args.command == "run":
            spec = validate_spec(read_json_file(args.spec, "spec"), repo)
            output = run_evidence(repo, spec, args.output, args.lease_root)
        else:
            output = validate_packet(read_json_file(args.packet, "packet"), repo)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
