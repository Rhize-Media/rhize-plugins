import importlib.util
import json
import stat
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-ops" / "scripts" / "evaluation_setup.py"
SPEC = importlib.util.spec_from_file_location("evaluation_setup", SCRIPT)
evaluation_setup = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evaluation_setup)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def setup_component(state_root: Path, plugin: str = "rhize-ops", *extra: str) -> dict:
    completed = run_cli(
        "setup", "--repo-root", str(REPO), "--state-root", str(state_root),
        "--capture-mode", "aggressive_local", "--plugin", plugin, *extra,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def valid_metrics() -> dict:
    return {
        "correctness_pass": True,
        "verification_required": 1,
        "verification_completed": 1,
        "verification_passed": 1,
        "routing_true_positives": 1,
        "routing_false_positives": 0,
        "routing_false_negatives": 0,
        "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None},
        "tokens_unavailable_reason": "host_not_exposed",
        "latency_ms": 12.5,
        "tool_calls": None,
        "tool_calls_unavailable_reason": "host_not_exposed",
        "follow_up_reads": 0,
        "corrections": 0,
        "rework_events": 0,
        "failures": 0,
        "refusals": 0,
    }


def test_catalog_covers_every_skill_and_groups_obsidian_with_context() -> None:
    completed = run_cli("validate", "--repo-root", str(REPO))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["plugin_skills"] == 56
    assert result["components"] == 10
    assert result["domains"]["knowledge-context"] == [
        "obsidian-second-brain", "rhize-context-manager", "procedural-memory"
    ]
    assert "rhize-ops" not in result["domains"]["knowledge-context"]


def test_catalog_rejects_runner_path_traversal(tmp_path: Path) -> None:
    catalog = json.loads((REPO / "rhize-ops/setup/evaluation-catalog.json").read_text())
    catalog["components"][0]["suites"][0]["path"] = "../outside.py"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    with pytest.raises(evaluation_setup.SetupError, match="without traversal"):
        evaluation_setup.validate_catalog(REPO, path)


def test_catalog_rejects_component_domain_disagreement(tmp_path: Path) -> None:
    catalog = json.loads((REPO / "rhize-ops/setup/evaluation-catalog.json").read_text())
    catalog["components"][0]["domain"] = "operations"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    with pytest.raises(evaluation_setup.SetupError, match="disagrees with the domain inventory"):
        evaluation_setup.validate_catalog(REPO, path)


def test_setup_preserves_confirmed_baseline_and_private_state(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({
        "plugins": {
            "obsidian-second-brain": {
                "status": "confirmed",
                "label": "manual vault search and review",
                "version": "2026-08-31",
                "validation_method": "same-vault answer key"
            }
        }
    }))
    first = setup_component(state_root, "obsidian-second-brain", "--baseline-decisions", str(decisions))
    assert first["components"]["obsidian-second-brain"]["baseline_status"] == "confirmed"
    config_path = state_root / "config.json"
    config = json.loads(config_path.read_text())
    baseline_id = config["plugins"]["obsidian-second-brain"]["baseline"]["baseline_id"]
    second = setup_component(state_root, "obsidian-second-brain")
    assert second["capture_mode"] == "aggressive_local"
    rerun = json.loads(config_path.read_text())
    assert rerun["plugins"]["obsidian-second-brain"]["baseline"]["baseline_id"] == baseline_id
    assert stat.S_IMODE(state_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((state_root / "hmac.key").stat().st_mode) == 0o600


def test_scoped_setup_supports_mixed_capture_modes(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    setup_component(state_root, "rhize-ops")
    completed = run_cli(
        "setup", "--repo-root", str(REPO), "--state-root", str(state_root),
        "--capture-mode", "deterministic_only", "--plugin", "obsidian-second-brain",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    config = json.loads((state_root / "config.json").read_text())
    assert config["capture_mode"] == "mixed"
    assert config["plugins"]["rhize-ops"]["capture_mode"] == "aggressive_local"
    assert config["plugins"]["obsidian-second-brain"]["capture_mode"] == "deterministic_only"


def test_free_smoke_runs_in_isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHIZE_SETUP_SENTINEL_SECRET", "must-not-be-forwarded")
    completed = run_cli(
        "setup", "--repo-root", str(REPO), "--state-root", str(tmp_path / "state"),
        "--capture-mode", "deterministic_only", "--plugin", "procedural-memory",
        "--run-free-smoke",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    suites = json.loads(completed.stdout)["components"]["procedural-memory"]["suite_statuses"]
    assert suites == {"procedural-memory-local": "pass", "procedural-memory-portable-schema": "pass"}


def test_suite_timeout_is_recorded_as_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = evaluation_setup.validate_catalog(REPO)
    suite = catalog["components"][0]["suites"][0]

    def time_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="offline-suite", timeout=1)

    monkeypatch.setattr(evaluation_setup.subprocess, "run", time_out)
    result = evaluation_setup.run_suite(REPO, tmp_path / "state", suite)
    assert result["status"] == "fail"
    assert result["reason"] == "timeout"


def test_receipt_lifecycle_is_append_only_and_source_free(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    setup_component(state_root)
    source = tmp_path / "sensitive-input.txt"
    sensitive = "client prompt and /private/customer/path must never be stored"
    source.write_text(sensitive)
    reserved = run_cli(
        "reserve", "--state-root", str(state_root), "--plugin", "rhize-ops",
        "--benchmark", "operations-existing-vs-rhize", "--variant", "A",
        "--input-file", str(source),
    )
    assert reserved.returncode == 0, reserved.stdout + reserved.stderr
    run_id = json.loads(reserved.stdout)["run_id"]
    receipt_path = next((state_root / "receipts").glob("*.jsonl"))
    pending_text = receipt_path.read_text()
    assert sensitive not in pending_text
    assert str(source) not in pending_text
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps(valid_metrics()))
    finalized = run_cli(
        "finalize", "--state-root", str(state_root), "--run-id", run_id,
        "--status", "completed", "--metrics", str(metrics),
    )
    assert finalized.returncode == 0, finalized.stdout + finalized.stderr
    rows = [json.loads(line) for line in receipt_path.read_text().splitlines()]
    assert [row["status"] for row in rows] == ["pending", "completed"]
    assert rows[0]["input_fingerprint"] == rows[1]["input_fingerprint"]
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    duplicate = run_cli(
        "finalize", "--state-root", str(state_root), "--run-id", run_id,
        "--status", "completed", "--metrics", str(metrics),
    )
    assert duplicate.returncode == 2
    assert "already terminal" in duplicate.stderr
    audit = run_cli("audit", "--state-root", str(state_root), "--stale-after-hours", "0")
    assert audit.returncode == 0
    assert json.loads(audit.stdout)["pending"] == 0


def test_receipt_rejects_unexplained_missing_counters(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    setup_component(state_root)
    source = tmp_path / "input.txt"
    source.write_text("bounded fixture")
    reserved = run_cli(
        "reserve", "--state-root", str(state_root), "--plugin", "rhize-ops",
        "--benchmark", "operations-existing-vs-rhize", "--variant", "B",
        "--input-file", str(source),
    )
    run_id = json.loads(reserved.stdout)["run_id"]
    metrics = valid_metrics()
    metrics["tokens_unavailable_reason"] = None
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(metrics))
    completed = run_cli(
        "finalize", "--state-root", str(state_root), "--run-id", run_id,
        "--status", "incomplete", "--metrics", str(metrics_path),
    )
    assert completed.returncode == 2
    assert "must exactly explain" in completed.stderr


def test_completed_receipt_requires_complete_passing_verification(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    setup_component(state_root)
    source = tmp_path / "input.txt"
    source.write_text("bounded fixture")
    reserved = run_cli(
        "reserve", "--state-root", str(state_root), "--plugin", "rhize-ops",
        "--benchmark", "operations-existing-vs-rhize", "--variant", "B",
        "--input-file", str(source),
    )
    run_id = json.loads(reserved.stdout)["run_id"]
    metrics = valid_metrics()
    metrics["verification_completed"] = 0
    metrics["verification_passed"] = 0
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(metrics))
    completed = run_cli(
        "finalize", "--state-root", str(state_root), "--run-id", run_id,
        "--status", "completed", "--metrics", str(metrics_path),
    )
    assert completed.returncode == 2
    assert "complete, passing verification" in completed.stderr


def test_setup_rejects_corrupt_existing_config(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    setup_component(state_root)
    config_path = state_root / "config.json"
    config = json.loads(config_path.read_text())
    config["unexpected"] = "must not survive"
    config_path.write_text(json.dumps(config))
    completed = run_cli(
        "setup", "--repo-root", str(REPO), "--state-root", str(state_root),
        "--capture-mode", "aggressive_local", "--plugin", "rhize-ops",
    )
    assert completed.returncode == 2
    assert "must contain exactly" in completed.stderr


def test_wizards_delegate_to_central_scoped_evaluation_setup() -> None:
    central = (REPO / "rhize-ops/commands/rhize-setup.md").read_text()
    assert "--run-free-smoke" in central
    assert "aggressive_local" in central
    assert "observational" in central
    scoped = {
        "obsidian-second-brain/commands/vault-setup.md": "obsidian-second-brain",
        "rhize-context-manager/commands/context-setup.md": "rhize-context-manager",
        "rhize-devflow/commands/devflow-setup.md": "rhize-devflow",
        "rhize-ops/commands/delegate-setup.md": "rhize-ops",
        "rhize-tasks/skills/rhize-tasks-setup/SKILL.md": "rhize-tasks",
    }
    for relative_path, component in scoped.items():
        contents = (REPO / relative_path).read_text()
        assert f"--plugin {component}" in contents
        assert "rhize-setup" in contents
