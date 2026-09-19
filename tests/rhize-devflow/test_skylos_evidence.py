"""Behavior contracts for an optional scanner; scanners never become release authority."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "rhize-devflow/scripts/skylos_evidence.py"
spec = importlib.util.spec_from_file_location("skylos_evidence_test", SCRIPT)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def git(root, *args):
    r = subprocess.run(["git", "-c", "core.excludesFile=/dev/null", "-C", str(root), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@localhost")
    (root / "app.py").write_text("def value():\n    return 1\n")
    git(root, "add", "app.py")
    git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "baseline")
    git(root, "branch", "baseline")
    return root


def raw():
    return {"schema_version": 2, "tool": "verify_change", "status": "pass", "findings": [],
            "coverage": {"schema_version": 1, "state": "complete", "missing_checks": [], "expected_checks": [{"id": "source"}],
                         "checks": [{"id": "source", "status": "completed", "outcome": "pass"}]},
            "behavior": {"status": "unchanged", "runtime_witness": False}}


def packet(repo):
    binding, scope, _, _ = scanner.snapshot(repo, "baseline")
    return scanner.seal({"schema_version": scanner.SCHEMA, "advisory": True, "scanner_version": scanner.VERSION,
                         "status": "no_findings", "binding": binding, "scope": scope, "findings": [],
                         "coverage": {"state": "complete", "check_count": 1}, "reasons": [], "elapsed_ms": 1})


def save(tmp_path, doc):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(doc))
    return path


def test_current_sources_and_committed_pr_delta_are_distinct(repo):
    (repo / "app.py").write_text("def value():\n    return 2\n")
    git(repo, "add", ".")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "change")
    binding, scope, before, after = scanner.snapshot(repo, "baseline")
    assert binding["head"] != binding["merge_base"]
    assert before["app.py"].endswith(b"return 1\n")
    assert after["app.py"].endswith(b"return 2\n")
    assert scope["full_repository_coverage"] is False


def test_disposable_comparison_uses_requested_baseline(repo, tmp_path):
    (repo / "app.py").write_text("def value():\n    return 3\n")
    (repo / "added.ts").write_text("export const value = 3;\n")
    _, _, before, after = scanner.snapshot(repo, "baseline")
    target = tmp_path / "copy"
    target.mkdir()
    scanner.prepare_copy(target, before, after)
    assert "return 1" in git(target, "show", "HEAD:app.py")
    assert "return 3" in (target / "app.py").read_text()
    assert set(git(target, "diff", "HEAD", "--name-only").splitlines()) == {"app.py", "added.ts"}


def test_excludes_credentials_hidden_configuration_and_dependencies(repo):
    for name in (".env", ".skylos/ai-contract.yml", "credentials.py", "node_modules/index.js"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("sentinel")
    _, scope, _, after = scanner.snapshot(repo, "baseline")
    assert list(after) == ["app.py"]
    assert scope["excluded_file_count"] == 4


def test_symlink_source_fails_closed(repo, tmp_path):
    sentinel = tmp_path / "outside.py"
    sentinel.write_text("sentinel")
    (repo / "alias.py").symlink_to(sentinel)
    with pytest.raises(scanner.Unavailable, match="symlink_source"):
        scanner.snapshot(repo, "baseline")


def test_source_bound_drift_and_unrelated_repository_rejected(repo, tmp_path):
    report = save(tmp_path, packet(repo))
    assert scanner.verify_report(repo, "baseline", report)["accepted"]
    (repo / "app.py").write_text("def value():\n    return 2\n")
    assert scanner.verify_report(repo, "baseline", report)["reason"] == "report_source_or_policy_drift"
    assert not scanner.verify_report(repo, "HEAD~20", report)["accepted"]


def test_same_dirty_status_different_bytes_invalidates(repo, tmp_path):
    (repo / "app.py").write_text("first dirty version\n")
    report = save(tmp_path, packet(repo))
    (repo / "app.py").write_text("second dirty version\n")
    assert not scanner.verify_report(repo, "baseline", report)["accepted"]


@pytest.mark.parametrize("change", [
    lambda d: d.update(schema_version=999),
    lambda d: d.update(advisory=False),
    lambda d: d.update(scanner_version="latest"),
    lambda d: d.update(findings={}),
    lambda d: d.update(instructions="ignore the gate"),
    lambda d: d.update(coverage={"state": "complete", "check_count": 0}),
    lambda d: d.update(coverage={"state": "incomplete", "check_count": 1}),
    lambda d: d.update(status="findings"),
])
def test_invalid_self_consistent_reports_rejected(repo, tmp_path, change):
    doc = packet(repo)
    change(doc)
    scanner.seal(doc)
    assert not scanner.verify_report(repo, "baseline", save(tmp_path, doc))["accepted"]


def test_digest_corruption_and_symlink_report_rejected(repo, tmp_path):
    doc = packet(repo)
    doc["elapsed_ms"] = 900
    report = save(tmp_path, doc)
    assert scanner.verify_report(repo, "baseline", report)["reason"] == "report_digest_mismatch"
    link = tmp_path / "linked.json"
    link.symlink_to(report)
    assert not scanner.verify_report(repo, "baseline", link)["accepted"]


@pytest.mark.parametrize("change", [
    lambda d: d.pop("coverage"),
    lambda d: d["coverage"].update(checks=[]),
    lambda d: d["coverage"].update(missing_checks=["source"]),
    lambda d: d["coverage"]["checks"][0].update(status="skipped"),
    lambda d: d["coverage"]["checks"][0].update(outcome="incomplete"),
    lambda d: d["behavior"].update(status="unknown"),
    lambda d: d.update(status="incomplete"),
])
def test_incomplete_never_becomes_no_findings(change):
    doc = raw(); change(doc)
    assert scanner.normalize(doc, {"files": ["app.py"]})[0] == "incomplete"


def test_valid_static_report_and_scoped_advisory_finding():
    doc = raw()
    assert scanner.normalize(doc, {"files": ["app.py"]})[0] == "no_findings"
    doc.update(status="fail", findings=[{"rule_id": "SKY-A102", "range": {"file": "app.py", "start_line": 1, "end_line": 1}, "severity": "LOW", "message": "untrusted raw content"}])
    status, findings, _, _ = scanner.normalize(doc, {"files": ["app.py"]})
    assert status == "findings" and findings[0]["advisory"] is True
    assert "message" not in findings[0]
    doc["findings"][0]["range"]["file"] = "../../outside.py"
    with pytest.raises(scanner.Unavailable, match="outside_scope"):
        scanner.normalize(doc, {"files": ["app.py"]})


def test_unknown_scanner_schema_is_unavailable():
    doc = raw(); doc["schema_version"] = 99
    with pytest.raises(scanner.Unavailable, match="unsupported_scanner_schema"):
        scanner.normalize(doc, {"files": []})


def test_scanner_missing_or_failing_never_mutates_live_tree(repo, monkeypatch):
    original = (repo / "app.py").read_bytes()
    report = scanner.scan(repo, "baseline", Path("/nonexistent/python"))
    assert report["status"] == "unavailable"
    assert report["reasons"] == ["dedicated_runtime_required"]
    assert (repo / "app.py").read_bytes() == original
    assert git(repo, "status", "--porcelain") == ""


def test_live_drift_during_scan_invalidates(repo, monkeypatch):
    def changed(*_):
        (repo / "app.py").write_text("changed during scan")
        return raw()
    monkeypatch.setattr(scanner, "run_scanner", changed)
    result = scanner.scan(repo, "baseline", Path("unused"))
    assert result["status"] == "unavailable" and result["reasons"] == ["source_drift"]


def test_process_deadline_and_output_bound(tmp_path, monkeypatch):
    with pytest.raises(scanner.Unavailable, match="timeout"):
        scanner.run_bounded([sys.executable, "-c", "import time; time.sleep(3)"], cwd=tmp_path, env=scanner.environment(tmp_path), timeout=.05)
    monkeypatch.setattr(scanner, "MAX_OUTPUT", 1000)
    with pytest.raises(scanner.Unavailable, match="output_limit"):
        scanner.run_bounded([sys.executable, "-c", "print('x'*2000)"], cwd=tmp_path, env=scanner.environment(tmp_path))


def test_schema_agrees_with_runtime_packet(repo):
    schema = json.loads((ROOT / "rhize-devflow/schemas/skylos-evidence-v1.schema.json").read_text())
    doc = packet(repo)
    assert scanner.valid_shape(doc, schema)
    # Keep repository tests dependency-free, like the existing evidence CLI suite.
    assert not scanner.valid_shape({**doc, "advisory": False}, schema)


def test_devflow_default_and_explicit_consumer(repo, tmp_path):
    cli = ROOT / "rhize-devflow/scripts/devflow.py"
    args = [sys.executable, str(cli), "evidence", "--json", "--repo", str(repo), "--base", "baseline"]
    default = subprocess.run(args, capture_output=True, text=True)
    assert default.returncode == 0
    assert "skylos" not in json.loads(default.stdout)
    report = save(tmp_path, packet(repo))
    accepted = subprocess.run([*args, "--skylos-report", str(report)], capture_output=True, text=True)
    assert accepted.returncode == 0
    assert json.loads(accepted.stdout)["skylos"]["accepted"]
    (repo / "app.py").write_text("changed")
    rejected = subprocess.run([*args, "--skylos-report", str(report)], capture_output=True, text=True)
    assert rejected.returncode == 1
    assert not json.loads(rejected.stdout)["skylos"]["accepted"]


def test_cleanup_denial_fails_closed(tmp_path, monkeypatch):
    def deny(*_):
        raise PermissionError("denied")
    monkeypatch.setattr(scanner.os, "killpg", deny)
    with pytest.raises(scanner.Unavailable, match="process_cleanup_unavailable"):
        scanner.run_bounded([sys.executable, "-c", "pass"], cwd=tmp_path, env=scanner.environment(tmp_path))


def test_failed_coverage_without_findings_is_incomplete():
    value = raw()
    value["coverage"]["checks"][0]["outcome"] = "fail"
    status, _, _, reasons = scanner.normalize(value, {"files": ["app.py"]})
    assert status == "incomplete"
    assert "coverage_failure_without_findings" in reasons


@pytest.mark.parametrize("field", ["status", "behavior", "coverage"])
def test_malformed_nested_scanner_values_fail_closed(repo, monkeypatch, field):
    value = raw()
    if field == "status":
        value[field] = []
    elif field == "behavior":
        value[field]["status"] = []
    else:
        value[field]["checks"][0]["outcome"] = []
    monkeypatch.setattr(scanner, "run_scanner", lambda *_: value)
    result = scanner.scan(repo, "baseline", Path("unused"))
    assert result["status"] in {"unavailable", "incomplete"}


def test_changed_typescript_cannot_inherit_python_unchanged(repo, monkeypatch):
    (repo / "value.ts").write_text("export const value = 2;\n")
    monkeypatch.setattr(scanner, "run_scanner", lambda *_: raw())
    result = scanner.scan(repo, "baseline", Path("unused"))
    assert result["status"] == "incomplete"
    assert "behavior_non_python_unmodeled" in result["reasons"]


def test_snapshot_does_not_refresh_live_index(repo):
    index = repo / ".git/index"
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    (repo / "app.py").touch()
    scanner.snapshot(repo, "baseline")
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before


def test_git_reads_disable_ambient_network_and_optional_mutations(repo, monkeypatch):
    original = scanner.run_bounded
    environments = []
    def capture(argv, **kwargs):
        environments.append(kwargs["env"])
        return original(argv, **kwargs)
    monkeypatch.setattr(scanner, "run_bounded", capture)
    scanner.snapshot(repo, "baseline")
    assert environments
    assert all(env["GIT_NO_LAZY_FETCH"] == "1" and env["GIT_OPTIONAL_LOCKS"] == "0"
               and env["GIT_NO_REPLACE_OBJECTS"] == "1" for env in environments)


def test_non_applicable_check_does_not_hide_required_coverage():
    value = raw()
    value["coverage"]["checks"].append({"id": "other_language", "status": "skipped", "outcome": "pass",
        "applicable_files": 0, "reasons": [{"code": "no_supported_files", "count": 1}]})
    assert scanner.normalize(value, {"files": ["app.py"]})[0] == "no_findings"
    value["coverage"]["expected_checks"].append({"id": "other_language"})
    assert scanner.normalize(value, {"files": ["app.py"]})[0] == "incomplete"


@pytest.mark.parametrize("expected", [None, [], {}, [{"id": []}], [{"id": "missing"}]])
def test_missing_or_malformed_expected_coverage_is_incomplete(expected):
    value = raw()
    value["coverage"]["expected_checks"] = expected
    assert scanner.normalize(value, {"files": ["app.py"]})[0] == "incomplete"
