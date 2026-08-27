from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from context_experiments.providers.grepai import GrepaiLayout, GrepaiProvider


VERSION = "0.35.0"
MODEL = "nomic-embed-text:v1.5"
LAYOUT = GrepaiLayout(
    Path(".grepai/config.yaml"),
    Path(".grepai/index.gob"),
    Path(".grepai/rhize-snapshot.json"),
)


class ContractRunner:
    """Failure/shape stub only; it never creates benchmark evidence."""

    def __init__(
        self,
        *,
        version: str = VERSION,
        model_output: str | None = None,
        model_returncode: int = 0,
        search_output: str = "[]",
        search_returncode: int = 0,
        search_timeout: bool = False,
    ) -> None:
        self.version = version
        self.model_output = model_output or f"NAME ID SIZE MODIFIED\n{MODEL} 0a109f422b47 274 MB now\n"
        self.model_returncode = model_returncode
        self.search_output = search_output
        self.search_returncode = search_returncode
        self.search_timeout = search_timeout
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        self.calls.append(command)
        if command[0] == "/reviewed/bin/grepai":
            if command[1:] == ["version"]:
                return subprocess.CompletedProcess(command, 0, f"grepai version {self.version}\n", "")
            if command[1:] == ["status", "--no-ui"]:
                return subprocess.CompletedProcess(command, 0, "Index ready\n", "")
            if command[1] == "search":
                if self.search_timeout:
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                return subprocess.CompletedProcess(command, self.search_returncode, self.search_output, "private failure detail")
            raise AssertionError(f"unexpected grepai execution: {command}")
        if command[0] == "/reviewed/bin/ollama":
            return subprocess.CompletedProcess(command, self.model_returncode, self.model_output, "private endpoint detail")
        return subprocess.run(command, **kwargs)


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "src").mkdir()
    (repo / "src/app.py").write_text("def app():\n    return True\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "src/app.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
        check=True,
    )
    return repo


def _provider(repo: Path, runner: ContractRunner) -> GrepaiProvider:
    artifacts = repo / ".grepai"
    artifacts.mkdir(exist_ok=True)
    config = artifacts / "config.yaml"
    config.write_text("reviewed local ollama config\n", encoding="utf-8")
    (artifacts / "index.gob").write_bytes(b"local-index")
    models = repo / "ollama-models"
    manifest = models / "manifests/registry.ollama.ai/library/nomic-embed-text/v1.5"
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(b"reviewed-model-manifest")
    provider = GrepaiProvider(
        LAYOUT,
        expected_config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
        expected_model_digest=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        executable="/reviewed/bin/grepai",
        ollama_executable="/reviewed/bin/ollama",
        ollama_models_dir=models,
        command_runner=runner,
    )
    (artifacts / "rhize-snapshot.json").write_text(json.dumps(provider.build_snapshot_marker(repo)), encoding="utf-8")
    return provider


def test_doctor_rejects_version_mismatch(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    provider = _provider(repo, ContractRunner(version="9.9.9"))

    health = provider.doctor(repo)

    assert health.ready is False
    assert health.version == "9.9.9"
    assert "pinned version" in health.note


@pytest.mark.parametrize(
    ("host", "model_output", "returncode", "note"),
    [
        ("https://private.example.invalid", None, 0, "not local"),
        ("http://127.0.0.1:11434", None, 1, "unavailable locally"),
        ("http://127.0.0.1:11434", "NAME ID SIZE MODIFIED\nother:1 id 1 MB now\n", 0, "unavailable locally"),
    ],
)
def test_doctor_rejects_unavailable_model_or_endpoint_without_leakage(
    tmp_path: Path, host: str, model_output: str | None, returncode: int, note: str
) -> None:
    repo = _repository(tmp_path)
    runner = ContractRunner(model_output=model_output, model_returncode=returncode)
    provider = _provider(repo, runner)
    provider.ollama_host = host

    health = provider.doctor(repo)

    assert health.ready is False
    assert note in health.note
    assert "private.example.invalid" not in health.note
    assert "private endpoint detail" not in health.note


def test_inventory_keeps_hard_denies_when_grepaiignore_negates_them(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    (repo / ".env.production").write_text("SECRET=value\n", encoding="utf-8")
    (repo / "identity.pem").write_text("SECRET\n", encoding="utf-8")
    (repo / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    (repo / ".grepaiignore").write_text("ignored.txt\n!.env.production\n!identity.pem\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-f", ".env.production", "identity.pem", "ignored.txt"], check=True)
    provider = GrepaiProvider(LAYOUT, expected_config_sha256="a" * 64, command_runner=ContractRunner())

    inventory = provider.inventory(repo)

    included = {row["path"] for row in inventory["included"]}
    excluded = {row["path"]: row["reason"] for row in inventory["excluded"]}
    assert {".env.production", "identity.pem", "ignored.txt"}.isdisjoint(included)
    assert excluded[".env.production"] == "hidden_path"
    assert excluded["identity.pem"] == "secret_suffix"
    assert excluded["ignored.txt"] == "git_or_grepai_ignore"


@pytest.mark.parametrize(
    "output",
    [
        "not-json",
        json.dumps({"error": "model unavailable"}),
        json.dumps([{"file_path": "/private/source.py", "start_line": 1, "end_line": 2, "score": 0.9}]),
        json.dumps([{"file_path": "../source.py", "start_line": 1, "end_line": 2, "score": 0.9}]),
    ],
)
def test_search_rejects_malformed_error_or_absolute_results(tmp_path: Path, output: str) -> None:
    repo = _repository(tmp_path)
    provider = _provider(repo, ContractRunner(search_output=output))

    with pytest.raises(RuntimeError):
        provider.search(repo, "find application")


def test_search_rejects_denied_result_paths(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    (repo / ".env").write_text("SECRET=value\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-f", ".env"], check=True)
    output = json.dumps([{"file_path": ".env", "start_line": 1, "end_line": 1, "score": 0.8}])
    provider = _provider(repo, ContractRunner(search_output=output))

    with pytest.raises(RuntimeError, match="denied or unindexed"):
        provider.search(repo, "credentials")


@pytest.mark.parametrize("timeout", [True, False])
def test_search_fails_closed_on_timeout_or_failure(tmp_path: Path, timeout: bool) -> None:
    repo = _repository(tmp_path)
    runner = ContractRunner(search_timeout=timeout, search_returncode=0 if timeout else 7)
    provider = _provider(repo, runner)

    with pytest.raises(RuntimeError) as raised:
        provider.search(repo, "find application")

    assert "private failure detail" not in str(raised.value)
    assert ("bounded timeout" in str(raised.value)) is timeout


def test_search_returns_only_relative_candidate_metadata(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    output = json.dumps([{"file_path": "src/app.py", "start_line": 1, "end_line": 2, "score": 0.875, "symbol_name": "app", "feature_path": "application"}])
    provider = _provider(repo, ContractRunner(search_output=output))

    result = provider.search(repo, "find application", limit=5)

    assert [candidate.to_dict() for candidate in result.candidates] == [
        {"path": "src/app.py", "score": 0.875, "startLine": 1, "endLine": 2}
    ]
    assert result.manifest["snapshotCurrent"] is True
    assert result.manifest["queryHash"] == hashlib.sha256(b"find application").hexdigest()
    assert result.result_bytes == len(output.encode())
    assert "find application" not in json.dumps(result.manifest)
    assert "symbol_name" not in repr(result)


def test_search_deduplicates_ranked_chunks_by_file(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    output = json.dumps(
        [
            {"file_path": "src/app.py", "start_line": 1, "end_line": 2, "score": 0.9},
            {"file_path": "src/app.py", "start_line": 3, "end_line": 4, "score": 0.8},
        ]
    )
    provider = _provider(repo, ContractRunner(search_output=output))

    result = provider.search(repo, "find application", limit=5)

    assert [candidate.to_dict() for candidate in result.candidates] == [
        {"path": "src/app.py", "score": 0.9, "startLine": 1, "endLine": 2}
    ]


def test_doctor_rejects_stale_snapshot_and_commands_are_explicit(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    runner = ContractRunner()
    provider = _provider(repo, runner)
    executions_before = sum(call[0] == "/reviewed/bin/grepai" for call in runner.calls)
    assert provider.init_command(repo)[1:] == ["init", "--provider", "ollama", "--backend", "gob", "--yes"]
    assert provider.index_command(repo)[1:] == ["watch", "--no-ui"]
    assert [command[1:] for command in provider.cleanup_commands()] == [["watch", "--status"], ["watch", "--stop"]]
    assert sum(call[0] == "/reviewed/bin/grepai" for call in runner.calls) == executions_before

    (repo / "src/app.py").write_text("def changed():\n    return False\n", encoding="utf-8")
    health = provider.doctor(repo)
    assert health.ready is False
    assert "stale or unverified" in health.note


def test_linked_worktree_blocks_doctor_init_and_index(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    provider = _provider(repo, ContractRunner())
    linked = tmp_path / "linked"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b", "fixture-linked", str(linked)], check=True)

    health = provider.doctor(repo)

    assert health.ready is False
    assert "linked Git worktrees" in health.note
    with pytest.raises(RuntimeError, match="linked Git worktrees"):
        provider.init_command(repo)
    with pytest.raises(RuntimeError, match="linked Git worktrees"):
        provider.index_command(repo)
