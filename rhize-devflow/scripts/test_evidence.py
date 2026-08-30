#!/usr/bin/env python3
"""Produce and validate state-bound test evidence in a disposable Git worktree."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rhize-test-evidence-v1"
RUN_SPEC_VERSION = "rhize-test-evidence-run-v1"
RUNNER_VERSION = "1.0.0"
VERDICTS = {
    "oracle_supported", "killed", "survived_mutation", "oracle_missing", "artifact_contract",
    "not_applicable", "mutation_unavailable", "mutation_unavailable_dirty_state", "stale_packet",
    "cleanup_failed",
}
CONTRACT_CLASSES = {"behavior", "artifact", "structural"}
ORACLE_KINDS = {"independent", "artifact", "missing", "not_applicable"}
ORACLES_BY_CONTRACT = {
    "behavior": {"independent", "missing"},
    "artifact": {"artifact"},
    "structural": {"independent", "missing", "not_applicable"},
}
SAFE_SCRIPT = re.compile(r"^test(?::[A-Za-z0-9:_-]+)?$")
PROTECTED = (
    re.compile(r"^\.github/workflows/"), re.compile(r"(^|/)\.env(?:\.|$)"),
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


def resolve_file(repo: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise EvidenceError(f"{label} must be a relative path")
    root = repo.resolve()
    path = (root / relative).resolve()
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


def file_records(repo: Path, paths: list[Any], label: str) -> list[dict[str, str]]:
    if not isinstance(paths, list):
        raise EvidenceError(f"{label} must be an array")
    return [{"path": value, "sha256": file_digest(resolve_file(repo, value, label))} for value in paths]


def package_script(repo: Path, name: str) -> str:
    if not isinstance(name, str) or not SAFE_SCRIPT.fullmatch(name):
        raise EvidenceError("only named test or test:* package scripts are approved")
    package_path = repo / "package.json"
    if not package_path.is_file():
        raise EvidenceError("package.json is required for package-script authorization")
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if not isinstance(package, dict) or not isinstance(package.get("scripts"), dict):
        raise EvidenceError("package.json scripts must be an object")
    script = package["scripts"].get(name)
    if not isinstance(script, str) or not script:
        raise EvidenceError("approved test script is not declared by package.json")
    return script


def package_invocation(repo: Path, name: str) -> list[str]:
    package_script(repo, name)
    if (repo / "pnpm-lock.yaml").is_file():
        return ["pnpm", "run", name]
    if (repo / "yarn.lock").is_file():
        return ["yarn", "run", name]
    if (repo / "bun.lockb").is_file() or (repo / "bun.lock").is_file():
        return ["bun", "run", name]
    return ["npm", "run", name]


def run_process(command: list[str], cwd: Path, timeout: int) -> int:
    process = subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        return 124


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
    package_invocation(repo, invocation["name"])
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
        if (
            mutation["external_effect"] is not False
            or not isinstance(mutation["target_path"], str)
            or protected(mutation["target_path"])
        ):
            raise EvidenceError("mutation target is protected or effectful")
        target = resolve_file(repo, mutation["target_path"], "mutation.target_path")
        if mutation["target_path"] not in spec["production_files"]:
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
            "target_path": mutation["target_path"],
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
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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


def run_evidence(repo: Path, spec: dict[str, Any], output: Path, lease_root: Path) -> dict[str, Any]:
    if is_within(output, repo) or is_within(lease_root, repo):
        raise EvidenceError("packet output and lease root must stay outside the target repository")
    initial_fingerprint, clean = working_fingerprint(repo)
    packet = base_packet(
        repo,
        spec,
        "mutation_unavailable_dirty_state" if not clean else "mutation_unavailable",
        fingerprint=initial_fingerprint,
        clean_before=clean,
    )
    if not clean:
        write_packet(output, packet)
        return packet
    contract_class = spec["contract_class"]
    oracle_kind = spec["oracle"]["kind"]
    if contract_class == "artifact":
        packet["verdict"] = "artifact_contract" if oracle_kind == "artifact" else "oracle_missing"
        packet["cleanup"] = {"status": "ok", "human_recovery_required": False}
        packet["lifecycle"]["clean_after"] = True
        write_packet(output, packet)
        return packet
    if spec["mutation"] is None:
        packet["verdict"] = "oracle_supported" if oracle_kind == "independent" else ("not_applicable" if oracle_kind == "not_applicable" else "oracle_missing")
        packet["cleanup"] = {"status": "ok", "human_recovery_required": False}
        packet["lifecycle"]["clean_after"] = True
        write_packet(output, packet)
        return packet

    lease_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lease_root.chmod(0o700)
    common = run_git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    lease_path = lease_root / (digest_text(str((repo / common).resolve())) + ".lock")
    lease_flags = os.O_WRONLY | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        lease_flags |= os.O_NOFOLLOW
    temporary = Path(tempfile.mkdtemp(prefix="rhize-test-evidence-"))
    try:
        lease_fd = os.open(lease_path, lease_flags, 0o600)
    except OSError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    worktree = temporary / "worktree"
    added = False
    try:
        os.fchmod(lease_fd, 0o600)
        try:
            fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise EvidenceError("another mutation run holds the exclusive lease") from exc
        packet["lifecycle"]["lease_acquired"] = True
        current_fingerprint, current_clean = working_fingerprint(repo)
        if not current_clean or current_fingerprint != initial_fingerprint:
            raise EvidenceError("target state changed before isolated mutation")
        add = run_git(repo, "worktree", "add", "--detach", str(worktree), packet["repository"]["head_sha"])
        if add.returncode:
            raise EvidenceError("could not create disposable worktree")
        added = True
        packet["lifecycle"]["isolated"] = True
        command = package_invocation(worktree, spec["test_invocation"]["name"])
        packet["baseline_test_exit_code"] = run_process(command, worktree, spec["timeout_seconds"])
        if packet["baseline_test_exit_code"] != 0:
            packet["verdict"] = "mutation_unavailable"
        else:
            mutation = spec["mutation"]
            target = resolve_file(worktree, mutation["target_path"], "mutation.target_path")
            original = target.read_text(encoding="utf-8")
            packet["mutation"]["state_before_fingerprint"] = working_fingerprint(worktree)[0]
            target.write_text(original.replace(mutation["search"], mutation["replace"]), encoding="utf-8")
            packet["mutation_test_exit_code"] = run_process(command, worktree, spec["timeout_seconds"])
            packet["verdict"] = "survived_mutation" if packet["mutation_test_exit_code"] == 0 else "killed"
            target.write_text(original, encoding="utf-8")
            packet["mutation"]["state_after_fingerprint"] = working_fingerprint(worktree)[0]
            packet["final_test_exit_code"] = run_process(command, worktree, spec["timeout_seconds"])
            clean_after = not bool(run_git(worktree, "status", "--porcelain", "--untracked-files=all").stdout.strip())
            packet["lifecycle"]["clean_after"] = clean_after
            packet["lifecycle"]["final_clean_rerun"] = packet["final_test_exit_code"] == 0
            if (
                not clean_after
                or packet["final_test_exit_code"] != 0
                or packet["mutation"]["state_before_fingerprint"] != packet["mutation"]["state_after_fingerprint"]
            ):
                packet["verdict"] = "mutation_unavailable"
    except (OSError, EvidenceError, json.JSONDecodeError):
        packet["verdict"] = "mutation_unavailable"
    finally:
        removal_ok = True
        if added:
            try:
                removal = run_git(repo, "worktree", "remove", "--force", str(worktree))
                removal_ok = removal.returncode == 0
            except OSError:
                removal_ok = False
        shutil.rmtree(temporary, ignore_errors=True)
        fingerprint_ok = True
        try:
            final_fingerprint = working_fingerprint(repo)[0]
            packet["repository"]["final_working_tree_fingerprint"] = final_fingerprint
        except (OSError, EvidenceError):
            fingerprint_ok = False
            final_fingerprint = None
            packet["repository"]["final_working_tree_fingerprint"] = None
        packet["cleanup"] = {
            "status": "ok" if removal_ok and fingerprint_ok else "failed",
            "human_recovery_required": not removal_ok or not fingerprint_ok,
        }
        if not removal_ok or not fingerprint_ok:
            packet["verdict"] = "cleanup_failed"
        elif final_fingerprint != initial_fingerprint:
            packet["verdict"] = "stale_packet"
        try:
            fcntl.flock(lease_fd, fcntl.LOCK_UN)
        finally:
            os.close(lease_fd)
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
    for group in ("test_files", "production_files"):
        if not isinstance(contract[group], list):
            raise EvidenceError(f"contract.{group} must be an array")
        for record in contract[group]:
            record = exact(record, {"path", "sha256"}, f"contract.{group} record")
            if not is_hex_digest(record["sha256"], 64):
                raise EvidenceError(f"contract.{group} digest must be sha256")
            if file_digest(resolve_file(repo, record["path"], group)) != record["sha256"]:
                stale = True
    if packet["mutation"] is not None:
        mutation = exact(
            packet["mutation"],
            {"target_path", "patch_digest", "state_before_fingerprint", "state_after_fingerprint"},
            "packet.mutation",
        )
        if (
            not isinstance(mutation["target_path"], str)
            or protected(mutation["target_path"])
            or not is_hex_digest(mutation["patch_digest"], 64)
        ):
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
    if verdict in {"killed", "survived_mutation"}:
        if (
            contract["class"] != "behavior"
            or packet["mutation"] is None
            or mutation["state_before_fingerprint"] is None
            or mutation["state_before_fingerprint"] != mutation["state_after_fingerprint"]
            or packet["baseline_test_exit_code"] != 0
            or packet["final_test_exit_code"] != 0
            or not all(lifecycle.values())
            or cleanup["status"] != "ok"
        ):
            raise EvidenceError("mutation verdict has incomplete state or lifecycle evidence")
        mutation_exit = packet["mutation_test_exit_code"]
        if mutation_exit is None or (verdict == "killed") == (mutation_exit == 0):
            raise EvidenceError("mutation verdict conflicts with the mutation test exit code")
    elif verdict == "oracle_supported":
        if (
            contract["class"] not in {"behavior", "structural"}
            or oracle["kind"] != "independent"
            or not clean_nonmutation
        ):
            raise EvidenceError("oracle_supported requires a clean independent oracle")
    elif verdict == "artifact_contract":
        if contract["class"] != "artifact" or oracle["kind"] != "artifact" or not clean_nonmutation:
            raise EvidenceError("artifact_contract has inconsistent contract evidence")
    elif verdict == "not_applicable":
        if contract["class"] != "structural" or oracle["kind"] != "not_applicable" or not clean_nonmutation:
            raise EvidenceError("not_applicable has inconsistent contract evidence")
    elif verdict == "oracle_missing":
        if oracle["kind"] != "missing" or not clean_nonmutation:
            raise EvidenceError("oracle_missing requires a clean missing-oracle contract")
    elif verdict == "mutation_unavailable_dirty_state":
        if lifecycle["clean_before"] or lifecycle["isolated"] or cleanup["status"] != "not_started":
            raise EvidenceError("dirty-state verdict has inconsistent lifecycle evidence")
    elif verdict == "stale_packet" and not stale:
        raise EvidenceError("stale_packet verdict requires state drift")
    if packet["verdict"] == "cleanup_failed" or cleanup["status"] == "failed":
        review_verdict = "FAIL_REQUIRES_HUMAN"
    elif stale:
        review_verdict = "stale_packet"
    elif packet["verdict"] in {"oracle_supported", "killed", "artifact_contract", "not_applicable"} and lifecycle["clean_after"]:
        review_verdict = "supported"
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
        repo = args.repo.resolve()
        if run_git(repo, "rev-parse", "--show-toplevel").returncode:
            raise EvidenceError("repo is not a Git repository")
        if args.command == "run":
            spec = validate_spec(json.loads(args.spec.read_text(encoding="utf-8")), repo)
            output = run_evidence(repo, spec, args.output, args.lease_root)
        else:
            output = validate_packet(json.loads(args.packet.read_text(encoding="utf-8")), repo)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
