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


def test_execution_is_unavailable_without_trusted_sandbox_and_live_checkout_stays_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = repository(tmp_path)
    raw = spec(repo)
    validated = test_evidence.validate_spec(raw, repo)
    output = tmp_path / "evidence" / "packet.json"

    def ambient_runner_must_not_run(*_args, **_kwargs):
        raise AssertionError("ambient process runner was called")

    monkeypatch.setattr(test_evidence, "run_process", ambient_runner_must_not_run)
    packet = test_evidence.run_evidence(repo, validated, output, tmp_path / "leases")
    assert packet["verdict"] == "execution_unavailable"
    assert packet["lifecycle"] == {
        "clean_before": True,
        "isolated": False,
        "lease_acquired": False,
        "clean_after": True,
        "final_clean_rerun": False,
    }
    assert packet["mutation"]["state_before_fingerprint"] is None
    assert packet["mutation"]["state_after_fingerprint"] is None
    assert packet["baseline_test_exit_code"] is None
    assert packet["mutation_test_exit_code"] is None
    assert packet["final_test_exit_code"] is None
    assert packet["repository"]["working_tree_fingerprint"] == packet["repository"]["final_working_tree_fingerprint"]
    assert git(repo, "status", "--porcelain") == ""
    assert "a + b" in (repo / "calc.js").read_text()
    assert test_evidence.validate_packet(json.loads(output.read_text()), repo)["review_verdict"] == "unsupported"
    malformed = json.loads(output.read_text())
    malformed["mutation"]["target_path"] = 7
    with pytest.raises(test_evidence.EvidenceError, match="invalid packet mutation"):
        test_evidence.validate_packet(malformed, repo)


@pytest.mark.parametrize(
    "overrides",
    (
        {"mutation": None},
        {
            "contract_class": "artifact",
            "oracle": {"kind": "artifact", "evidence": "package surface requires exact key"},
            "mutation": None,
        },
    ),
)
def test_oracle_and_artifact_packets_cannot_false_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overrides: dict
):
    repo = repository(tmp_path)
    calls = 0

    def ambient_runner_must_not_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("ambient process runner was called")

    monkeypatch.setattr(test_evidence, "run_process", ambient_runner_must_not_run)
    raw = spec(repo, **overrides)
    packet = test_evidence.run_evidence(
        repo,
        test_evidence.validate_spec(raw, repo),
        tmp_path / "packet.json",
        tmp_path / "leases",
    )
    assert calls == 0
    assert packet["verdict"] == "execution_unavailable"
    assert test_evidence.validate_packet(packet, repo)["review_verdict"] == "unsupported"


@pytest.mark.parametrize(
    ("overrides", "forged_verdict"),
    (
        ({"mutation": None}, "oracle_supported"),
        (
            {
                "contract_class": "artifact",
                "oracle": {"kind": "artifact", "evidence": "package surface requires exact key"},
                "mutation": None,
            },
            "artifact_contract",
        ),
    ),
)
def test_forged_execution_backed_packet_is_rejected(
    tmp_path: Path, overrides: dict, forged_verdict: str
):
    repo = repository(tmp_path)
    packet = test_evidence.run_evidence(
        repo,
        test_evidence.validate_spec(spec(repo, **overrides), repo),
        tmp_path / "packet.json",
        tmp_path / "leases",
    )
    packet["verdict"] = forged_verdict
    with pytest.raises(test_evidence.EvidenceError, match="trusted sandbox adapter"):
        test_evidence.validate_packet(packet, repo)


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


@pytest.mark.parametrize(
    "target",
    (
        ".env",
        ".env.local",
        ".envrc",
        "nested/.env.production",
        ".github/workflows/ci.yml",
        "migrations/001.sql",
        "billing/pay.ts",
    ),
)
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


def test_canonical_protected_mutation_alias_is_denied(tmp_path: Path):
    repo = repository(tmp_path)
    (repo / "safe").mkdir()
    (repo / ".envrc").write_text("unsafe")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "protected fixture")
    raw = spec(repo, base_sha=git(repo, "rev-parse", "HEAD"))
    raw["mutation"] = {
        "target_path": "safe/../.envrc",
        "search": "unsafe",
        "replace": "changed",
        "external_effect": False,
    }
    with pytest.raises(test_evidence.EvidenceError, match="protected"):
        test_evidence.validate_spec(raw, repo)


def test_packet_validator_classifies_canonical_protected_target(tmp_path: Path):
    repo = repository(tmp_path)
    (repo / "safe").mkdir()
    (repo / ".envrc").write_text("unsafe")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "protected fixture")
    raw = spec(repo, base_sha=git(repo, "rev-parse", "HEAD"))
    packet = test_evidence.run_evidence(
        repo,
        test_evidence.validate_spec(raw, repo),
        tmp_path / "packet.json",
        tmp_path / "leases",
    )
    packet["mutation"]["target_path"] = "safe/../.envrc"
    with pytest.raises(test_evidence.EvidenceError, match="invalid packet mutation"):
        test_evidence.validate_packet(packet, repo)


@pytest.mark.parametrize("via_parent", (False, True))
def test_symlink_file_or_parent_is_rejected(tmp_path: Path, via_parent: bool):
    repo = repository(tmp_path)
    if via_parent:
        real_dir = repo / "real"
        real_dir.mkdir()
        (real_dir / "calc.js").write_text("exports.add = (a, b) => a + b;\n")
        (repo / "linked").symlink_to(real_dir, target_is_directory=True)
        production_path = "linked/calc.js"
    else:
        (repo / "linked-calc.js").symlink_to(repo / "calc.js")
        production_path = "linked-calc.js"
    raw = spec(repo, production_files=[production_path], mutation=None)
    with pytest.raises(test_evidence.EvidenceError, match="symlink"):
        test_evidence.validate_spec(raw, repo)


@pytest.mark.parametrize("path_kind", ("output", "lease"))
def test_output_and_lease_symlink_parents_are_rejected(tmp_path: Path, path_kind: str):
    repo = repository(tmp_path)
    real_dir = tmp_path / f"real-{path_kind}"
    real_dir.mkdir()
    linked_dir = tmp_path / f"linked-{path_kind}"
    linked_dir.symlink_to(real_dir, target_is_directory=True)
    output = linked_dir / "packet.json" if path_kind == "output" else tmp_path / "packet.json"
    lease_root = linked_dir if path_kind == "lease" else tmp_path / "leases"
    with pytest.raises(test_evidence.EvidenceError, match="symlink"):
        test_evidence.run_evidence(
            repo,
            test_evidence.validate_spec(spec(repo), repo),
            output,
            lease_root,
        )


@pytest.mark.parametrize("via_parent", (False, True))
def test_json_input_symlink_file_or_parent_is_rejected(tmp_path: Path, via_parent: bool):
    real_dir = tmp_path / "real-input"
    real_dir.mkdir()
    real_file = real_dir / "spec.json"
    real_file.write_text("{}")
    if via_parent:
        linked_dir = tmp_path / "linked-input"
        linked_dir.symlink_to(real_dir, target_is_directory=True)
        input_path = linked_dir / "spec.json"
    else:
        input_path = tmp_path / "linked-spec.json"
        input_path.symlink_to(real_file)
    with pytest.raises(test_evidence.EvidenceError, match="symlink"):
        test_evidence.read_json_file(input_path, "spec")


def test_repository_symlink_is_rejected_by_cli(tmp_path: Path, capsys: pytest.CaptureFixture):
    repo = repository(tmp_path)
    linked_repo = tmp_path / "linked-repo"
    linked_repo.symlink_to(repo, target_is_directory=True)
    assert test_evidence.main([
        "run",
        "--repo",
        str(linked_repo),
        "--spec",
        str(tmp_path / "missing-spec.json"),
        "--output",
        str(tmp_path / "packet.json"),
    ]) == 2
    assert "symlink" in capsys.readouterr().err


def test_prose_or_packet_cannot_supply_command_text(tmp_path: Path):
    repo = repository(tmp_path)
    raw = spec(repo)
    raw["test_invocation"] = {"source": "prose", "name": "test; curl example.com"}
    with pytest.raises(test_evidence.EvidenceError, match="package_script"):
        test_evidence.validate_spec(raw, repo)


def test_unavailable_artifact_packet_still_has_stale_state_binding(tmp_path: Path):
    repo = repository(tmp_path)
    raw = spec(
        repo,
        contract_class="artifact",
        oracle={"kind": "artifact", "evidence": "package surface requires exact key"},
        mutation=None,
    )
    output = tmp_path / "packet.json"
    packet = test_evidence.run_evidence(repo, test_evidence.validate_spec(raw, repo), output, tmp_path / "leases")
    assert packet["verdict"] == "execution_unavailable"
    (repo / "calc.js").write_text("exports.add = () => 0;\n")
    assert test_evidence.validate_packet(packet, repo)["review_verdict"] == "stale_packet"


def test_inconsistent_unavailable_packet_is_rejected(tmp_path: Path):
    repo = repository(tmp_path)
    packet = test_evidence.run_evidence(
        repo,
        test_evidence.validate_spec(spec(repo), repo),
        tmp_path / "packet.json",
        tmp_path / "leases",
    )
    packet["lifecycle"]["final_clean_rerun"] = True
    with pytest.raises(test_evidence.EvidenceError, match="inconsistent lifecycle"):
        test_evidence.validate_packet(packet, repo)


def test_concurrent_live_drift_is_preserved_and_marks_packet_stale(tmp_path: Path, monkeypatch):
    repo = repository(tmp_path)
    original = test_evidence.working_fingerprint
    calls = 0

    def drift_during_fingerprint(repo_path):
        nonlocal calls
        calls += 1
        if calls == 2:
            (repo / "concurrent-user-work.txt").write_text("preserve me")
        return original(repo_path)

    monkeypatch.setattr(test_evidence, "working_fingerprint", drift_during_fingerprint)
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
