from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from context_experiments.config import arm_capability, load_config, write_config
from context_experiments.models import Capability, ExperimentConfig
from context_experiments.runner import (
    build_context_pack_preview,
    claim_hook_selection,
    finalize_hook_selection,
    git_snapshot,
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
    config = armed_mgrep(REPO_ROOT)
    payload = {
        "prompt": "Implement a new context experiment feature",
        "cwd": str(REPO_ROOT),
        "session_id": "session-claim",
    }
    provider_status = {Capability.MGREP: (True, True, "test-provider")}
    claimed = claim_hook_selection(payload, config, provider_status, tmp_path)
    assert claimed is not None
    assert claimed["assignment"].live_variant.value == "B"
    assert "prompt" not in claimed["pending"]
    assert "promptHash" in claimed["pending"]
    assert claim_hook_selection(payload, config, provider_status, tmp_path) is None

    assert finalize_hook_selection(payload, tmp_path) is True
    documents = list((tmp_path / "receipts").glob("*.json"))
    assert len(documents) == 1
    receipt = json.loads(documents[0].read_text())
    assert receipt["status"] == "incomplete"
    assert receipt["armsExecuted"] == []
    assert {item["reason"] for item in receipt["armsSkipped"]} == {
        "no_execution_evidence"
    }
    assert finalize_hook_selection(payload, tmp_path) is False


def test_compiled_context_hook_builds_real_pack_and_records_arms(
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
    )
    assert claimed is not None
    execution = claimed["pending"]["providerExecution"]
    assert execution["providerRevision"] == "rhize-native-context-pack-v1"
    assert (tmp_path / "data" / "packs" / execution["manifestFile"]).is_file()
    assert (tmp_path / "data" / "packs" / execution["promptFile"]).is_file()
    assert "prompt" not in claimed["pending"]

    assert finalize_hook_selection(payload, tmp_path / "data", config_path) is True
    receipt_path = next((tmp_path / "data" / "receipts").glob("*.json"))
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "completed"
    assert set(receipt["armsExecuted"]) == {"A", "B"}
    assert {metric["variant"] for metric in receipt["metrics"]} == {"A", "B"}
    assert "live_task_outcome_requires_human_review" in receipt["warnings"]
    assert "provider_revision_rhize-native-context-pack-v1" in receipt["warnings"]
    assert any(value.startswith("pack_id_pack-") for value in receipt["warnings"])
    updated = load_config(config_path)
    assert updated.compiled_context.armed_runs == 0
    assert updated.compiled_context.completed_runs == 1


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
