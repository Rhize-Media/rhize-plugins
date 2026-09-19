#!/usr/bin/env python3
"""Opt-in, advisory Skylos evidence. No live-source writes or unsandboxed fallback."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

SCHEMA = "rhize-skylos-evidence-v1"
VERSION = "4.38.0"
MAX_FILE = 1_000_000
MAX_TOTAL = 32_000_000
MAX_FILES = 2000
MAX_OUTPUT = 2_000_000
EXTENSIONS = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
POLICY = {"version": 1, "skylos": VERSION, "extensions": sorted(EXTENSIONS),
          "jobs": 1, "contracts": False, "dependency_hallucinations": False, "network": "deny",
          "max_file_bytes": MAX_FILE, "max_total_bytes": MAX_TOTAL, "max_files": MAX_FILES,
          "max_output_bytes": MAX_OUTPUT, "timeout_seconds": 60, "full_repository_coverage": False}


class Unavailable(Exception):
    """A reason code, deliberately without subprocess output or private paths."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def policy_hash():
    return digest({"policy": POLICY, "adapter": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def environment(home):
    return {"PATH": "/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(home), "TMPDIR": str(home),
            "LANG": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0", "SKYLOS_JOBS": "1", "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1"}


def run_bounded(argv, *, cwd, env, timeout=60):
    """Bound output on disk and kill the process group on deadline/overflow."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True)
        except OSError as exc:
            raise Unavailable("process_unavailable") from exc
        deadline = time.monotonic() + timeout
        reason = None
        while process.poll() is None:
            if out.tell() + err.tell() > MAX_OUTPUT:
                reason = "output_limit"
                break
            if time.monotonic() >= deadline:
                reason = "timeout"
                break
            time.sleep(0.02)
        # Terminate descendants too, even when the process leader has already exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            # Cleanup could not be established; never return usable scanner evidence.
            try:
                process.kill()
                process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                pass
            raise Unavailable("process_cleanup_unavailable") from exc
        process.wait()
        if out.tell() + err.tell() > MAX_OUTPUT:
            reason = "output_limit"
        if reason:
            raise Unavailable(reason)
        out.seek(0)
        err.seek(0)
        return process.returncode, out.read(MAX_OUTPUT + 1), err.read(MAX_OUTPUT + 1)


def git(repo, *args):
    code, out, _ = run_bounded(["/usr/bin/git", "-c", "core.fsmonitor=false", "-c",
                               "core.hooksPath=/dev/null", "-C", str(repo), *args],
                              cwd=repo, env=environment("/nonexistent"), timeout=15)
    if code:
        raise Unavailable("git_unavailable")
    return out


def safe_name(name):
    path = PurePosixPath(name)
    return (bool(name) and not path.is_absolute() and ".." not in path.parts
            and "\\" not in name and not any(ord(c) < 32 for c in name)
            and path.as_posix() == name)


def selected(name):
    if not safe_name(name):
        raise Unavailable("unsafe_source_path")
    parts = PurePosixPath(name).parts
    return (PurePosixPath(name).suffix in EXTENSIONS
            and not any(p.startswith(".") or p in {"node_modules", "vendor", "dist", "build", "venv", "__pycache__"}
                        or re.search(r"(?:secret|credential|private[-_]?key)", p, re.I) for p in parts))


def read_regular(path, root, limit=MAX_FILE):
    """Refuse symlinks at every component; recheck identity after bounded reading."""
    try:
        relative = path.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise Unavailable("symlink_source")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise Unavailable("source_limit_or_type")
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if len(data) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise Unavailable("source_changed_during_read")
        if path.resolve() != path or path.stat().st_ino != before.st_ino:
            raise Unavailable("source_changed_during_read")
        return data
    except (OSError, ValueError) as exc:
        raise Unavailable("source_unavailable") from exc


def snapshot(repo, base):
    repo = Path(repo).resolve()
    if not base or base.startswith("-"):
        raise Unavailable("explicit_base_required")
    top = git(repo, "rev-parse", "--show-toplevel").decode().strip()
    if Path(top).resolve() != repo:
        raise Unavailable("repository_root_required")
    head = git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    base_sha = git(repo, "rev-parse", "--verify", base + "^{commit}").decode().strip()
    merge_base = git(repo, "merge-base", base_sha, head).decode().strip()
    status_bytes = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    before, after = {}, {}
    excluded = set()
    total = 0
    for record in git(repo, "ls-tree", "-rlz", merge_base).split(b"\0"):
        if not record:
            continue
        info, raw_name = record.split(b"\t", 1)
        name = raw_name.decode("utf-8")
        mode, kind, oid, size = info.split()
        if not selected(name):
            excluded.add(name)
            continue
        if kind != b"blob" or mode not in {b"100644", b"100755"}:
            raise Unavailable("unsupported_git_entry")
        if int(size) > MAX_FILE:
            raise Unavailable("source_limit_or_type")
        data = git(repo, "cat-file", "blob", oid.decode())
        before[name] = data
        total += len(data)
        if total > MAX_TOTAL or len(before) > MAX_FILES:
            raise Unavailable("snapshot_limit")
    names = set(git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")) - {b""}
    for raw_name in sorted(names):
        name = raw_name.decode("utf-8")
        if not selected(name):
            excluded.add(name)
            continue
        path = repo / name
        if not path.exists() and not path.is_symlink():
            continue  # A tracked deletion is represented by absence in the current tree.
        data = read_regular(path, repo)
        if b"\0" in data:
            raise Unavailable("binary_source")
        after[name] = data
        total += len(data)
        if total > MAX_TOTAL or len(after) > MAX_FILES:
            raise Unavailable("snapshot_limit")
    hashes = lambda files: {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    binding = {"repository": digest(str(repo)), "head": head, "base": base_sha, "merge_base": merge_base,
               "git_status": hashlib.sha256(status_bytes).hexdigest(), "before": digest(hashes(before)),
               "after": digest(hashes(after)), "policy": policy_hash()}
    scope = {"files": sorted(after), "deleted_files": sorted(set(before) - set(after)),
             "excluded_file_count": len(excluded), "full_repository_coverage": False}
    return binding, scope, before, after


def materialize(root, files):
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def prepare_copy(root, before, after):
    materialize(root, before)
    git(root, "init", "-q")
    git(root, "add", "--all")
    git(root, "-c", "user.name=Rhize fixture", "-c", "user.email=fixture@localhost",
        "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "Source baseline")
    for name in before:
        (root / name).unlink()
    materialize(root, after)
    # Stage so Git-aware detectors see newly added source without executing it.
    git(root, "add", "--all")


WORKER = r'''
import contextlib, importlib.metadata, json, os, resource, socket, sys
resource.setrlimit(resource.RLIMIT_FSIZE, (2000000, 2000000))
sys.dont_write_bytecode = True
# Require effective network denial before importing the optional scanner.
s = socket.socket()
try:
    s.bind(("127.0.0.1", 0))
except PermissionError:
    pass
else:
    raise RuntimeError("network isolation unavailable")
finally:
    s.close()
version = importlib.metadata.version("skylos")
if version != "4.38.0":
    raise RuntimeError("unsupported scanner version")
with contextlib.redirect_stdout(sys.stderr):
    from skylos.verify_change import verify_change_path
    result = verify_change_path(sys.argv[1], include_dependency_hallucinations=False,
                                contract_enabled=False)
print(json.dumps({"version": version, "result": result}))
'''


def sandbox_profile(root, scratch, runtime):
    # Only disposable scratch is writable; only selected source/runtime/system data is readable.
    quote = lambda p: json.dumps(str(Path(p).resolve()))
    reads = [root, scratch, runtime, "/System", "/usr", "/bin", "/sbin", "/opt/homebrew", "/Library/Apple", "/Library/Developer/CommandLineTools/usr", "/dev", "/private/var/db/dyld"]
    return ("(version 1)(deny default)(allow process*)(allow sysctl-read)(allow mach-lookup)"
            '(allow file-read-metadata)(allow file-read-data (literal "/"))'
            + "".join("(allow file-read* (subpath " + quote(p) + "))" for p in reads)
            + "(allow file-write* (subpath " + quote(scratch) + "))"
            + '(allow file-write* (literal "/dev/null"))(deny network*)')


def run_scanner(root, scratch, python):
    python = Path(python).absolute()
    runtime = python.parent.parent.resolve()
    if not python.is_file() or not (runtime / "pyvenv.cfg").is_file():
        raise Unavailable("dedicated_runtime_required")
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise Unavailable("sandbox_unavailable")
    if runtime == Path.home().resolve() or runtime == Path("/"):
        raise Unavailable("unsafe_runtime_root")
    code, output, _ = run_bounded(["/usr/bin/sandbox-exec", "-p", sandbox_profile(root, scratch, runtime),
                                   str(python), "-I", "-c", WORKER, str(root)],
                                  cwd=root, env=environment(scratch), timeout=POLICY["timeout_seconds"])
    if code:
        raise Unavailable("scanner_or_sandbox_failed")
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError) as exc:
        raise Unavailable("invalid_scanner_json") from exc
    if not isinstance(result, dict) or result.get("version") != VERSION:
        raise Unavailable("unsupported_scanner_version")
    return result.get("result")


def normalize(raw, scope):
    if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int or raw.get("schema_version") != 2 or raw.get("tool") != "verify_change":
        raise Unavailable("unsupported_scanner_schema")
    if not isinstance(raw.get("status"), str) or raw["status"] not in {"pass", "fail", "incomplete"}:
        raise Unavailable("invalid_scanner_status")
    findings = raw.get("findings")
    if not isinstance(findings, list) or len(findings) > 500:
        raise Unavailable("invalid_findings")
    normalized = []
    for finding in findings:
        if not isinstance(finding, dict) or not re.fullmatch(r"SKY-[A-Z][0-9]{3}", str(finding.get("rule_id", ""))):
            raise Unavailable("invalid_finding")
        location = finding.get("range", {})
        if not isinstance(location, dict) or location.get("file") not in scope["files"]:
            raise Unavailable("finding_outside_scope")
        start, end = location.get("start_line"), location.get("end_line")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= MAX_FILE:
            raise Unavailable("invalid_finding_range")
        severity = finding.get("severity")
        if not isinstance(severity, str) or severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL", "INFO"}:
            raise Unavailable("invalid_finding_severity")
        normalized.append({"rule_id": finding["rule_id"], "file": location["file"], "start_line": start,
                           "end_line": end, "severity": severity, "advisory": True})
    coverage = raw.get("coverage")
    checks = coverage.get("checks") if isinstance(coverage, dict) else None
    expected = coverage.get("expected_checks") if isinstance(coverage, dict) else None
    expected_valid = (isinstance(expected, list) and bool(expected)
                      and all(isinstance(e, dict) and isinstance(e.get("id"), str) for e in expected))
    expected_ids = {e["id"] for e in expected} if expected_valid else set()
    checked_ids = {c["id"] for c in checks if isinstance(c, dict) and isinstance(c.get("id"), str)
                   and c.get("status") == "completed"} if isinstance(checks, list) else set()
    complete = (isinstance(coverage, dict) and coverage.get("state") == "complete"
                and type(coverage.get("schema_version")) is int and coverage["schema_version"] == 1
                and coverage.get("missing_checks") == [] and expected_valid
                and expected_ids.issubset(checked_ids)
                and isinstance(checks, list) and bool(checks)
                and all(isinstance(c, dict) and isinstance(c.get("id"), str) and (
                    (c.get("status") == "completed" and isinstance(c.get("outcome"), str)
                     and c["outcome"] in {"pass", "fail"})
                    or (c.get("status") == "skipped" and type(c.get("applicable_files")) is int
                        and c["applicable_files"] == 0
                        and c.get("reasons") == [{"code": "no_supported_files", "count": 1}]
                        and c["id"] not in expected_ids)) for c in checks))
    reasons = [] if complete else ["coverage_incomplete_or_missing"]
    behavior = raw.get("behavior")
    behavior_status = behavior.get("status") if isinstance(behavior, dict) else None
    if not isinstance(behavior_status, str) or behavior_status not in {"equivalent", "unchanged"}:
        reasons.append("behavior_unproven")
    if raw["status"] == "incomplete":
        reasons.append("scanner_incomplete")
    if complete and any(c.get("outcome") == "fail" for c in checks) and not normalized:
        reasons.append("coverage_failure_without_findings")
    if raw["status"] == "fail" and not normalized:
        reasons.append("failure_without_findings")
    status = "findings" if normalized else ("incomplete" if reasons else "no_findings")
    return status, normalized, {"state": "complete" if complete else "incomplete",
                                 "check_count": len(checks) if isinstance(checks, list) else 0}, reasons


def seal(packet):
    packet["digest"] = digest({k: v for k, v in packet.items() if k != "digest"})
    return packet


def scan(repo, base, python):
    start = time.monotonic()
    packet = {"schema_version": SCHEMA, "advisory": True, "scanner_version": VERSION,
              "status": "unavailable", "binding": None, "scope": None, "findings": [],
              "coverage": {"state": "unavailable", "check_count": 0}, "reasons": [],
              "elapsed_ms": 0}
    try:
        binding, scope, before, after = snapshot(repo, base)
        packet.update(binding=binding, scope=scope)
        if not after:
            raise Unavailable("no_supported_sources")
        with tempfile.TemporaryDirectory(prefix="rhize-skylos-") as directory:
            workspace = Path(directory).resolve()
            root, scratch = workspace / "source", workspace / "scratch"
            root.mkdir(); scratch.mkdir()
            prepare_copy(root, before, after)
            raw = run_scanner(root, scratch, python)
            # The source is OS read-only to the scanner; verify live source did not drift too.
            current_binding, _, _, _ = snapshot(repo, base)
            if current_binding != binding:
                raise Unavailable("source_drift")
            status, findings, coverage, reasons = normalize(raw, scope)
            if any(Path(name).suffix != ".py" and before.get(name) != after.get(name)
                   for name in before.keys() | after.keys()):
                reasons.append("behavior_non_python_unmodeled")
                if status == "no_findings":
                    status = "incomplete"
            packet.update(status=status, findings=findings, coverage=coverage, reasons=reasons)
    except (Unavailable, OSError, UnicodeError, ValueError) as exc:
        packet.update(status="unavailable", findings=[], reasons=[str(exc) if isinstance(exc, Unavailable) else "input_unavailable"])
    packet["elapsed_ms"] = round((time.monotonic() - start) * 1000)
    return seal(packet)


def valid_shape(value, schema):
    """The local schema uses only these deliberately small JSON Schema primitives."""
    kinds = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
    if "anyOf" in schema:
        return any(valid_shape(value, option) for option in schema["anyOf"])
    kind = schema.get("type")
    if kind and type(value) is not kinds[kind]:
        return False
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, str):
        if len(value) > schema.get("maxLength", MAX_OUTPUT) or len(value) < schema.get("minLength", 0):
            return False
        if "pattern" in schema and not re.search(schema["pattern"], value):
            return False
    if type(value) is int and not schema.get("minimum", 0) <= value <= schema.get("maximum", 10**15):
        return False
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", MAX_FILES):
            return False
        return all(valid_shape(item, schema.get("items", {})) for item in value)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if not set(schema.get("required", [])).issubset(value):
            return False
        if schema.get("additionalProperties") is False and not set(value).issubset(props):
            return False
        return all(valid_shape(item, props.get(key, {})) for key, item in value.items())
    return True


def verify_report(repo, base, path):
    """Consistency/freshness check, not a signature or proof of trusted execution."""
    try:
        path = Path(path).absolute()
        raw = json.loads(read_regular(path, Path(path.anchor), MAX_OUTPUT))
        schema = json.loads((Path(__file__).resolve().parent.parent / "schemas/skylos-evidence-v1.schema.json").read_text())
        if not valid_shape(raw, schema):
            raise Unavailable("unsupported_report_schema")
        if raw.get("digest") != digest({k: v for k, v in raw.items() if k != "digest"}):
            raise Unavailable("report_digest_mismatch")
        if raw.get("scanner_version") != VERSION or raw.get("status") not in {"no_findings", "findings", "incomplete", "unavailable"}:
            raise Unavailable("invalid_report")
        binding, scope, _, _ = snapshot(repo, base)
        if raw.get("binding") != binding or raw.get("scope") != scope:
            raise Unavailable("report_source_or_policy_drift")
        for finding in raw["findings"]:
            if finding["file"] not in scope["files"] or finding["start_line"] > finding["end_line"]:
                raise Unavailable("finding_outside_scope")
        if (raw["status"] == "findings") != bool(raw["findings"]):
            raise Unavailable("invalid_report_status")
        if raw["status"] == "no_findings" and (raw["reasons"] or raw["coverage"]["state"] != "complete" or raw["coverage"]["check_count"] < 1):
            raise Unavailable("invalid_report_status")
        return {"accepted": True, "reason": None, "report": raw}
    except (Unavailable, OSError, ValueError, UnicodeError, TypeError) as exc:
        return {"accepted": False, "reason": str(exc) if isinstance(exc, Unavailable) else "invalid_report", "report": None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--repo", type=Path, required=True)
        command.add_argument("--base", required=True)
        if name == "scan":
            command.add_argument("--python", type=Path, required=True, help="Dedicated Skylos 4.38.0 venv interpreter")
        else:
            command.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    result = scan(args.repo, args.base, args.python) if args.command == "scan" else verify_report(args.repo, args.base, args.report)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command == "verify":
        return 0 if result["accepted"] else 2
    return {"no_findings": 0, "findings": 1, "incomplete": 2, "unavailable": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
