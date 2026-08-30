from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import pytest

import context_experiments.runner as runner_module
from context_experiments.config import (
    arm_capability,
    load_config,
    record_completed_run,
    write_config,
)
from context_experiments.models import Arm, Capability, ExperimentConfig, ExperimentEvidence
from context_experiments.receipt_store import EvidenceStore
from context_experiments.runner import (
    build_context_pack_preview,
    claim_hook_selection,
    finalize_hook_selection,
    git_snapshot,
    main,
    run_context_compiler_experiment,
    select_next,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "rhize-context-manager"
SELECTOR = PLUGIN_ROOT / "hooks" / "context-experiment-selector.js"
FINALIZER = PLUGIN_ROOT / "hooks" / "context-experiment-finalizer.js"


def armed_mgrep(repo: Path) -> ExperimentConfig:
    return arm_capability(
        ExperimentConfig(),
        Capability.MGREP,
        repo,
        1,
        network_approved=True,
        store="rhize-dogfood-test",
    )


def armed_local_retrieval(repo: Path) -> ExperimentConfig:
    return arm_capability(
        ExperimentConfig(),
        Capability.LOCAL_RETRIEVAL,
        repo,
        1,
        smoke_approved=True,
    )


def armed_compiled_context(repo: Path) -> ExperimentConfig:
    return arm_capability(
        ExperimentConfig(),
        Capability.COMPILED_CONTEXT,
        repo,
        1,
        smoke_approved=True,
    )


def test_legacy_compiler_completion_transition_is_bound_without_checkout() -> None:
    assert runner_module.record_completed_run is record_completed_run


def test_unavailable_real_provider_keeps_selection_inert() -> None:
    selection = select_next(
        {
            "prompt": "Implement a new context experiment feature",
            "cwd": str(REPO_ROOT),
            "session_id": "session-real-unavailable",
        },
        armed_mgrep(REPO_ROOT),
        {Capability.MGREP: (False, False, "provider-unavailable")},
    )
    assert selection is None


def test_local_retrieval_is_selected_only_with_current_real_snapshot() -> None:
    selection = select_next(
        {
            "prompt": "Implement a new context experiment feature",
            "cwd": str(REPO_ROOT),
            "session_id": "session-local-retrieval",
        },
        armed_local_retrieval(REPO_ROOT),
        {Capability.LOCAL_RETRIEVAL: (True, True, "verified local index")},
    )
    assert selection is not None
    assert selection["capability"] is Capability.LOCAL_RETRIEVAL

    stale = select_next(
        {
            "prompt": "Implement a new context experiment feature",
            "cwd": str(REPO_ROOT),
            "session_id": "session-local-retrieval-stale",
        },
        armed_local_retrieval(REPO_ROOT),
        {Capability.LOCAL_RETRIEVAL: (True, False, "stale local index")},
    )
    assert stale is None


def test_claim_is_atomic_and_interrupted_finalization_does_not_consume_run(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Rhize Tests",
            "-c", "user.email=tests@rhize.media", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    config = armed_mgrep(repo)
    config_path = tmp_path / "config.json"
    write_config(config, config_path)
    payload = {
        "prompt": "Implement a new context experiment feature",
        "cwd": str(repo),
        "session_id": "session-claim",
    }
    provider_status = {Capability.MGREP: (True, True, "test-provider")}
    claimed = claim_hook_selection(
        payload, config, provider_status, tmp_path, config_path
    )
    assert claimed is not None
    assert claimed["assignment"].live_variant.value == "B"
    assert "prompt" not in claimed["pending"]
    assert "promptHash" in claimed["pending"]
    frozen = load_config(config_path).mgrep
    assert frozen.enabled is False
    assert frozen.armed_runs == 0
    assert frozen.completed_runs == 0
    assert claim_hook_selection(
        payload, config, provider_status, tmp_path, config_path
    ) is None

    write_config(config, config_path)  # Finalization must re-freeze manual drift.
    assert finalize_hook_selection(payload, tmp_path, config_path) is True
    documents = list((tmp_path / "receipts").glob("*.json"))
    assert len(documents) == 1
    receipt = json.loads(documents[0].read_text())
    assert receipt["status"] == "incomplete"
    assert receipt["armsExecuted"] == []
    assert receipt["schemaVersion"] == 2
    assert receipt["evidenceDigest"] is None
    assert receipt["armsSkipped"] == [
        {"arm": "B", "reason": "missing_task_validation_evidence"},
        {"arm": "A", "reason": "no_comparable_shadow_evidence"},
    ]
    assert load_config(config_path).mgrep == frozen
    assert finalize_hook_selection(payload, tmp_path) is False


def test_compiled_context_pack_construction_alone_freezes_incomplete_run(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text(
        "def normalize(value: str) -> str:\n    return value.strip()\n"
    )
    (repo / "app.py").write_text(
        "from service import normalize\n\ndef run(value: str) -> str:\n    return normalize(value)\n"
    )
    (repo / "unused.py").write_text("\n".join(f"unused_{index} = {index}" for index in range(80)))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Rhize Tests",
            "-c", "user.email=tests@rhize.media", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    config_path = tmp_path / "config.json"
    write_config(armed_compiled_context(repo), config_path)
    payload = {
        "prompt": "Implement the app normalize service behavior for this feature",
        "cwd": str(repo),
        "session_id": "session-native-auto",
    }
    claimed = claim_hook_selection(
        payload,
        load_config(config_path),
        {Capability.COMPILED_CONTEXT: (True, True, "native provider")},
        tmp_path / "data",
        config_path,
    )
    assert claimed is not None
    execution = claimed["pending"]["providerExecution"]
    assert execution["providerRevision"] == "rhize-native-context-pack-v2"
    assert (tmp_path / "data" / "packs" / execution["manifestFile"]).is_file()
    assert (tmp_path / "data" / "packs" / execution["promptFile"]).is_file()
    assert "prompt" not in claimed["pending"]

    assert execution["claimPackVerified"] is True
    assert finalize_hook_selection(payload, tmp_path / "data", config_path) is True
    receipt_path = next((tmp_path / "data" / "receipts").glob("*.json"))
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "incomplete"
    assert receipt["armsExecuted"] == []
    assert receipt["metrics"] == []
    assert receipt["claimPackVerified"] is True
    assert receipt["finalPackVerification"] == "valid"
    assert receipt["armsSkipped"] == [
        {"arm": "B", "reason": "missing_pack_use_task_validation_evidence"},
        {"arm": "A", "reason": "no_comparable_shadow_evidence"},
    ]
    updated = load_config(config_path)
    assert updated.compiled_context.armed_runs == 0
    assert updated.compiled_context.completed_runs == 0
    assert updated.compiled_context.enabled is False


def test_review_sidecar_completes_only_evidenced_live_arm(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text("def normalize(value):\n    return value.strip()\n")
    (repo / "app.py").write_text("from service import normalize\n")
    (repo / "unused.py").write_text("\n".join(f"unused_{index} = {index}" for index in range(80)))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Rhize Tests",
            "-c", "user.email=tests@rhize.media", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    config_path = tmp_path / "config.json"
    write_config(armed_compiled_context(repo), config_path)
    data_dir = tmp_path / "data"
    payload = {
        "prompt": "Implement the app normalize service behavior for this feature",
        "cwd": str(repo),
        "session_id": "session-native-evidence",
    }
    claimed = claim_hook_selection(
        payload,
        load_config(config_path),
        {Capability.COMPILED_CONTEXT: (True, True, "native provider")},
        data_dir,
        config_path,
    )
    assert claimed is not None
    pending = claimed["pending"]
    evidence = ExperimentEvidence(
        experiment_id=pending["experimentId"],
        recorded_at="2026-08-30T12:00:00Z",
        task_outcome="completed",
        pack_use_observed=True,
        validation_ids=("pytest-context-tools",),
        arms_executed=(Arm.EXPERIMENTAL,),
        arms_skipped=({"arm": "A", "reason": "no_comparable_shadow_evidence"},),
    )
    EvidenceStore(data_dir / "evidence").write(evidence)

    assert finalize_hook_selection(payload, data_dir, config_path) is True
    receipt = json.loads(next((data_dir / "receipts").glob("*.json")).read_text())
    assert receipt["status"] == "completed"
    assert receipt["armsExecuted"] == ["B"]
    assert receipt["armsSkipped"] == [
        {"arm": "A", "reason": "no_comparable_shadow_evidence"}
    ]
    assert receipt["evidenceDigest"] == evidence.digest()
    assert {metric["variant"] for metric in receipt["metrics"]} == {"B"}
    frozen = load_config(config_path).compiled_context
    assert frozen.enabled is False
    assert frozen.armed_runs == 0
    assert frozen.completed_runs == 1


def test_repo_capability_lease_never_stale_reclaims_an_accepted_pending(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n")
    (repo / "unused.py").write_text("\n".join(f"unused_{index} = {index}" for index in range(80)))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Rhize Tests",
            "-c", "user.email=tests@rhize.media", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    config_path = tmp_path / "config.json"
    config = armed_compiled_context(repo)
    write_config(config, config_path)
    status = {Capability.COMPILED_CONTEXT: (True, True, "native provider")}
    first = claim_hook_selection(
        {
            "prompt": "Implement the app value behavior for this feature",
            "cwd": str(repo),
            "session_id": "session-one",
        },
        config,
        status,
        tmp_path / "data",
        config_path,
    )
    assert first is not None
    lease_path = tmp_path / "data" / "leases" / first["pending"]["leaseFile"]
    old = time.time() - 10_000
    os.utime(lease_path, (old, old))
    write_config(config, config_path)  # Simulate an unsafe manual re-arm.

    second = claim_hook_selection(
        {
            "prompt": "Implement another app value behavior for this feature",
            "cwd": str(repo),
            "session_id": "session-two",
        },
        config,
        status,
        tmp_path / "data",
        config_path,
    )
    assert second is None
    assert lease_path.exists()


def test_dirty_repo_and_expired_duration_refuse_before_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n")
    (repo / "unused.py").write_text("\n".join(f"unused_{index} = {index}" for index in range(80)))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Rhize Tests",
            "-c", "user.email=tests@rhize.media", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    config_path = tmp_path / "config.json"
    config = armed_compiled_context(repo)
    write_config(config, config_path)
    payload = {
        "prompt": "Implement the application behavior for this feature",
        "cwd": str(repo),
        "session_id": "session-dirty",
    }
    (repo / "app.py").write_text("value = 2\n")
    assert claim_hook_selection(
        payload,
        config,
        {Capability.COMPILED_CONTEXT: (True, True, "native provider")},
        tmp_path / "dirty-data",
        config_path,
    ) is None
    assert load_config(config_path).compiled_context.armed_runs == 1

    subprocess.run(["git", "-C", str(repo), "restore", "app.py"], check=True)
    short = config.with_capability(
        Capability.COMPILED_CONTEXT,
        replace(config.compiled_context, max_duration_seconds=1),
    )
    write_config(short, config_path)
    ticks = iter((0.0, 2.0))
    monkeypatch.setattr("context_experiments.runner.time.monotonic", lambda: next(ticks))
    assert claim_hook_selection(
        {**payload, "session_id": "session-timeout"},
        short,
        {Capability.COMPILED_CONTEXT: (True, True, "native provider")},
        tmp_path / "timeout-data",
        config_path,
    ) is None
    assert load_config(config_path).compiled_context.armed_runs == 1
    assert not (tmp_path / "timeout-data" / "pending").exists()


def test_real_context_compiler_writes_pack_and_receipt_before_consuming_arm(
    tmp_path: Path,
) -> None:
    checkout_value = os.environ.get("RHIZE_CONTEXT_COMPILER_TEST_CHECKOUT")
    if not checkout_value:
        pytest.skip("set RHIZE_CONTEXT_COMPILER_TEST_CHECKOUT for the real-provider test")
    checkout = Path(checkout_value)
    target = PLUGIN_ROOT / "scripts" / "context_experiments" / "runner.py"
    config_path = tmp_path / "config.json"
    data_dir = tmp_path / "data"
    config = arm_capability(
        ExperimentConfig(),
        Capability.COMPILED_CONTEXT,
        REPO_ROOT,
        1,
        smoke_approved=True,
    )
    write_config(config, config_path)

    result, receipt_path, manifest_path, prompt_path = run_context_compiler_experiment(
        REPO_ROOT,
        target,
        "implementation",
        "real-checkout-test",
        checkout=checkout,
        config_path=config_path,
        data_dir=data_dir,
    )
    assert receipt_path.exists()
    assert manifest_path.exists()
    assert prompt_path.exists()
    assert "runner.py" in prompt_path.read_text()
    assert str(REPO_ROOT) not in prompt_path.read_text()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["snapshot"] == "real-checkout-test"
    assert isinstance(manifest["policy"]["acceptedForInjection"], bool)
    assert result.live_variant.value == "B"
    assert result.shadow_variant is not None and result.shadow_variant.value == "A"
    assert {metric.role for metric in result.metrics} == {"live", "shadow"}
    updated = load_config(config_path)
    assert updated.compiled_context.armed_runs == 0
    assert updated.compiled_context.completed_runs == 1
    assert list((data_dir / "leases").glob("*.lease")) == []
    with pytest.raises(ValueError, match="no_armed_runs"):
        run_context_compiler_experiment(
            REPO_ROOT,
            target,
            "implementation",
            "real-checkout-test-2",
            checkout=checkout,
            config_path=config_path,
            data_dir=data_dir,
        )


def test_real_context_pack_preview_is_reproducible_and_source_bound(
    tmp_path: Path,
) -> None:
    checkout_value = os.environ.get("RHIZE_CONTEXT_COMPILER_TEST_CHECKOUT")
    if not checkout_value:
        pytest.skip("set RHIZE_CONTEXT_COMPILER_TEST_CHECKOUT for the real-provider test")
    repo = tmp_path / "repo"
    shutil.copytree(
        REPO_ROOT / "evals" / "context-tools" / "fixtures" / "context-compiler" / "static-alias",
        repo,
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Rhize Tests",
            "-c",
            "user.email=tests@rhize.media",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    snapshot = git_snapshot(repo)
    assert snapshot is not None

    first = build_context_pack_preview(
        repo,
        repo / "app.py",
        snapshot,
        checkout=Path(checkout_value),
        data_dir=tmp_path / "data",
    )
    second = build_context_pack_preview(
        repo,
        repo / "app.py",
        snapshot,
        checkout=Path(checkout_value),
        data_dir=tmp_path / "data",
    )
    assert first[0]["policy"]["acceptedForInjection"] is True
    assert first[0]["packId"] == second[0]["packId"]
    assert first[1:] == second[1:]

    (repo / "app.py").write_text("from service import run\nrun(2)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot mismatch"):
        build_context_pack_preview(
            repo,
            repo / "app.py",
            snapshot,
            checkout=Path(checkout_value),
            data_dir=tmp_path / "data",
        )


def run_hook(hook: Path, payload: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
        "RHIZE_CONTEXT_EXPERIMENT_CONFIG": str(tmp_path / "config.json"),
        "RHIZE_CONTEXT_EXPERIMENT_DATA_DIR": str(tmp_path / "data"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        ["node", str(hook)],
        input=payload,
        capture_output=True,
        text=True,
        env=environment,
        timeout=10,
        check=False,
    )


@pytest.mark.parametrize("hook", [SELECTOR, FINALIZER])
def test_hooks_fail_silent_on_malformed_input(hook: Path, tmp_path: Path) -> None:
    result = run_hook(hook, "{not-json", tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_unconfigured_selector_is_a_noop(tmp_path: Path) -> None:
    result = run_hook(
        SELECTOR,
        json.dumps(
            {
                "prompt": "Implement a new context experiment feature",
                "cwd": str(REPO_ROOT),
                "session_id": "hook-noop",
            }
        ),
        tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert not (tmp_path / "data").exists()


def test_selector_and_finalizer_wrappers_freeze_pack_only_attempt(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n")
    (repo / "unused.py").write_text("\n".join(f"unused_{index} = {index}" for index in range(80)))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Rhize Tests",
            "-c", "user.email=tests@rhize.media", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    write_config(armed_compiled_context(repo), tmp_path / "config.json")
    payload = json.dumps(
        {
            "prompt": "Implement the app value behavior for this feature",
            "cwd": str(repo),
            "session_id": "hook-paired-lifecycle",
        }
    )

    selected = run_hook(SELECTOR, payload, tmp_path)
    assert selected.returncode == 0
    output = json.loads(selected.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "Context experiment selected: compiledContext" in context
    pending = json.loads(
        next((tmp_path / "data" / "pending").glob("*.json")).read_text()
    )
    runner_path = (PLUGIN_ROOT / "scripts" / "context_experiments" / "runner.py").resolve()
    evidence_command = shlex.join(
        [
            "python3",
            str(runner_path),
            "record-evidence",
            "--experiment-id",
            pending["experimentId"],
            "--task-outcome",
            "completed",
            "--pack-used",
            "--validation-id",
            "validation-id-REPLACE_ME",
            "--executed-arm",
            "B",
            "--skip-arm",
            "A:no_comparable_shadow_evidence",
        ]
    )
    assert f"Evidence runner: {runner_path}." in context
    assert f"`{evidence_command}`" in context
    assert "read and use the accepted prompt pack before implementation" in context
    assert "validate the task before recording success" in context
    assert "Replace validation-id-REPLACE_ME" in context
    assert load_config(tmp_path / "config.json").compiled_context.enabled is False

    finalized = run_hook(FINALIZER, payload, tmp_path)
    assert finalized.returncode == 0
    receipt = json.loads(next((tmp_path / "data" / "receipts").glob("*.json")).read_text())
    assert receipt["status"] == "incomplete"
    assert receipt["armsExecuted"] == []
    assert receipt["evidenceDigest"] is None


def test_record_evidence_command_requires_pending_and_is_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n")
    (repo / "unused.py").write_text("\n".join(f"unused_{index} = {index}" for index in range(80)))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Rhize Tests",
            "-c", "user.email=tests@rhize.media", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    config_path = tmp_path / "config.json"
    write_config(armed_compiled_context(repo), config_path)
    data_dir = tmp_path / "data"
    claimed = claim_hook_selection(
        {
            "prompt": "Implement the app value behavior for this feature",
            "cwd": str(repo),
            "session_id": "evidence-command",
        },
        load_config(config_path),
        {Capability.COMPILED_CONTEXT: (True, True, "native provider")},
        data_dir,
        config_path,
    )
    assert claimed is not None
    experiment_id = claimed["pending"]["experimentId"]
    monkeypatch.setenv("RHIZE_CONTEXT_EXPERIMENT_DATA_DIR", str(data_dir))
    arguments = [
        "record-evidence",
        "--experiment-id", experiment_id,
        "--task-outcome", "completed",
        "--pack-used",
        "--validation-id", "pytest-context-tools",
        "--executed-arm", "B",
        "--skip-arm", "A:no_comparable_shadow_evidence",
    ]

    assert main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["experimentId"] == experiment_id
    assert len(result["evidenceDigest"]) == 64
    assert main(arguments) == 2
    assert "already exists" in capsys.readouterr().err
