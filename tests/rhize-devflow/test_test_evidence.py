from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-devflow/scripts/test_evidence.py"
SPEC = importlib.util.spec_from_file_location("test_evidence", SCRIPT)
assert SPEC and SPEC.loader
test_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(test_evidence)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "package.json").write_text(json.dumps({"scripts": {"test": "node test.js"}}))
    (repo / "calc.js").write_text("exports.add = (a, b) => a + b;\n")
    (repo / "test.js").write_text(
        "const { add } = require('./calc');\nif (add(2, 3) !== 5) process.exit(1);\n"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "fixture")
    return repo


def spec(repo: Path, **overrides):
    value = {
        "schema_version": "rhize-test-evidence-run-v1",
        "base_sha": git(repo, "rev-parse", "HEAD"),
        "contract_class": "behavior",
        "invariant": "add returns the mathematical sum",
        "test_files": ["test.js"],
        "production_files": ["calc.js"],
        "oracle": {"kind": "independent", "evidence": "known arithmetic result 2+3=5"},
        "mutation": {"target_path": "calc.js", "search": "a + b", "replace": "a - b", "external_effect": False},
        "test_invocation": {"source": "package_script", "name": "test"},
        "timeout_seconds": 30,
    }
    value.update(overrides)
    return value


def test_isolated_mutation_is_killed_and_live_checkout_stays_clean(tmp_path: Path):
    repo = repository(tmp_path)
    raw = spec(repo)
    validated = test_evidence.validate_spec(raw, repo)
    output = tmp_path / "evidence" / "packet.json"
    packet = test_evidence.run_evidence(repo, validated, output, tmp_path / "leases")
    assert packet["verdict"] == "killed"
    assert packet["lifecycle"] == {
        "clean_before": True,
        "isolated": True,
        "lease_acquired": True,
        "clean_after": True,
        "final_clean_rerun": True,
    }
    assert packet["mutation"]["state_before_fingerprint"] == packet["mutation"]["state_after_fingerprint"]
    assert packet["repository"]["working_tree_fingerprint"] == packet["repository"]["final_working_tree_fingerprint"]
    assert git(repo, "status", "--porcelain") == ""
    assert "a + b" in (repo / "calc.js").read_text()
    assert test_evidence.validate_packet(json.loads(output.read_text()), repo)["review_verdict"] == "supported"
    malformed = json.loads(output.read_text())
    malformed["mutation"]["target_path"] = 7
    with pytest.raises(test_evidence.EvidenceError, match="invalid packet mutation"):
        test_evidence.validate_packet(malformed, repo)


def test_surviving_mutant_blocks_regression_claim(tmp_path: Path):
    repo = repository(tmp_path)
    raw = spec(repo)
    raw["mutation"] = {"target_path": "calc.js", "search": "exports.add", "replace": "exports.add", "external_effect": False}
    packet = test_evidence.run_evidence(repo, test_evidence.validate_spec(raw, repo), tmp_path / "packet.json", tmp_path / "leases")
    assert packet["verdict"] == "survived_mutation"
    assert test_evidence.validate_packet(packet, repo)["review_verdict"] == "unsupported"


def test_dirty_checkout_is_never_mutated(tmp_path: Path):
    repo = repository(tmp_path)
    (repo / "unrelated.txt").write_text("user work")
    packet = test_evidence.run_evidence(repo, test_evidence.validate_spec(spec(repo), repo), tmp_path / "packet.json", tmp_path / "leases")
    assert packet["verdict"] == "mutation_unavailable_dirty_state"
    assert packet["lifecycle"]["isolated"] is False
    assert (repo / "unrelated.txt").read_text() == "user work"


def test_packet_and_lease_paths_cannot_modify_target_repository(tmp_path: Path):
    repo = repository(tmp_path)
    validated = test_evidence.validate_spec(spec(repo), repo)
    with pytest.raises(test_evidence.EvidenceError, match="outside the target repository"):
        test_evidence.run_evidence(repo, validated, repo / "packet.json", tmp_path / "leases")
    with pytest.raises(test_evidence.EvidenceError, match="outside the target repository"):
        test_evidence.run_evidence(repo, validated, tmp_path / "packet.json", repo / ".leases")
    assert git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize("target", (".env", ".github/workflows/ci.yml", "migrations/001.sql", "billing/pay.ts"))
def test_protected_or_effectful_mutation_is_denied(tmp_path: Path, target: str):
    repo = repository(tmp_path)
    path = repo / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("unsafe")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "protected fixture")
    raw = spec(repo, base_sha=git(repo, "rev-parse", "HEAD"))
    raw["mutation"] = {"target_path": target, "search": "unsafe", "replace": "changed", "external_effect": False}
    with pytest.raises(test_evidence.EvidenceError, match="protected"):
        test_evidence.validate_spec(raw, repo)


def test_prose_or_packet_cannot_supply_command_text(tmp_path: Path):
    repo = repository(tmp_path)
    raw = spec(repo)
    raw["test_invocation"] = {"source": "prose", "name": "test; curl example.com"}
    with pytest.raises(test_evidence.EvidenceError, match="package_script"):
        test_evidence.validate_spec(raw, repo)


def test_artifact_contract_and_stale_binding_are_distinct(tmp_path: Path):
    repo = repository(tmp_path)
    raw = spec(
        repo,
        contract_class="artifact",
        oracle={"kind": "artifact", "evidence": "package surface requires exact key"},
        mutation=None,
    )
    output = tmp_path / "packet.json"
    packet = test_evidence.run_evidence(repo, test_evidence.validate_spec(raw, repo), output, tmp_path / "leases")
    assert packet["verdict"] == "artifact_contract"
    (repo / "calc.js").write_text("exports.add = () => 0;\n")
    assert test_evidence.validate_packet(packet, repo)["review_verdict"] == "stale_packet"


def test_incomplete_supported_packet_is_rejected(tmp_path: Path):
    repo = repository(tmp_path)
    packet = test_evidence.run_evidence(
        repo,
        test_evidence.validate_spec(spec(repo), repo),
        tmp_path / "packet.json",
        tmp_path / "leases",
    )
    packet["lifecycle"]["final_clean_rerun"] = False
    with pytest.raises(test_evidence.EvidenceError, match="incomplete state or lifecycle"):
        test_evidence.validate_packet(packet, repo)


def test_cleanup_failure_requires_human_recovery(tmp_path: Path, monkeypatch):
    repo = repository(tmp_path)
    original = test_evidence.run_git

    def fail_removal(repo_path, *args):
        if args[:2] == ("worktree", "remove"):
            return subprocess.CompletedProcess([], 1, "", "injected removal failure")
        return original(repo_path, *args)

    monkeypatch.setattr(test_evidence, "run_git", fail_removal)
    packet = test_evidence.run_evidence(
        repo,
        test_evidence.validate_spec(spec(repo), repo),
        tmp_path / "packet.json",
        tmp_path / "leases",
    )
    assert packet["verdict"] == "cleanup_failed"
    assert packet["cleanup"] == {"status": "failed", "human_recovery_required": True}
    assert test_evidence.validate_packet(packet, repo)["review_verdict"] == "FAIL_REQUIRES_HUMAN"


def test_concurrent_live_drift_is_preserved_and_marks_packet_stale(tmp_path: Path, monkeypatch):
    repo = repository(tmp_path)
    original = test_evidence.run_process
    calls = 0

    def drift_during_run(command, cwd, timeout):
        nonlocal calls
        calls += 1
        result = original(command, cwd, timeout)
        if calls == 2:
            (repo / "concurrent-user-work.txt").write_text("preserve me")
        return result

    monkeypatch.setattr(test_evidence, "run_process", drift_during_run)
    packet = test_evidence.run_evidence(
        repo,
        test_evidence.validate_spec(spec(repo), repo),
        tmp_path / "packet.json",
        tmp_path / "leases",
    )
    assert packet["verdict"] == "stale_packet"
    assert (repo / "concurrent-user-work.txt").read_text() == "preserve me"
    assert test_evidence.validate_packet(packet, repo)["review_verdict"] == "stale_packet"


def test_schema_has_exact_verdict_vocabulary():
    schema = json.loads((REPO / "rhize-devflow/schemas/test-evidence-v1.schema.json").read_text())
    assert set(schema["properties"]["verdict"]["enum"]) == test_evidence.VERDICTS


def test_labeled_corpus_records_contract_and_oracle_rationale():
    labels = json.loads((REPO / "tests/rhize-devflow/fixtures/test-evidence/labels.json").read_text())
    assert {item["class"] for item in labels} == {"behavior", "artifact", "structural"}
    assert all(item["claimed_contract"] and item["oracle_rationale"] for item in labels)


def test_claude_and_codex_share_the_canonical_test_evidence_skill():
    skill = (REPO / "rhize-devflow/skills/test-evidence/SKILL.md").read_text()
    command = (REPO / "rhize-devflow/commands/test-evidence.md").read_text()
    codex = json.loads((REPO / "rhize-devflow/.codex-plugin/plugin.json").read_text())
    agent = (REPO / "rhize-devflow/skills/test-evidence/agents/openai.yaml").read_text()
    assert "../../scripts/test_evidence.py" in skill
    assert "canonical `rhize-devflow:test-evidence` skill" in command
    assert codex["skills"] == "./skills/"
    assert "$test-evidence" in agent
