#!/usr/bin/env python3
"""Fixture-driven tests for rhize-devflow/scripts/devflow.py (Task 3 of the Dev Flow 3.0
control-plane plan — see .claude/plans/rhize-devflow-v3-engineering-control-plane.md).

`jsonschema` is not installed in this environment, so JSON shape is validated with
hand-rolled asserts against `rhize-devflow/schemas/devflow-evidence-v1.schema.json`'s
required-key list (the same house pattern as scripts/validate_skill_map.py's stdlib
fallback), not against the schema library itself.

Doctor fixtures are static hermetic plugin trees under fixtures/doctor_*/ (no git needed).
Evidence fixtures are git repos built fresh in tmp_path per test (git-dependent evidence,
so we build real repos rather than committing fake .git state).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVFLOW_SCRIPT = REPO_ROOT / "rhize-devflow" / "scripts" / "devflow.py"
EVIDENCE_SCHEMA = REPO_ROOT / "rhize-devflow" / "schemas" / "devflow-evidence-v1.schema.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

assert DEVFLOW_SCRIPT.is_file(), f"missing {DEVFLOW_SCRIPT}"
assert EVIDENCE_SCHEMA.is_file(), f"missing {EVIDENCE_SCHEMA}"

# Import as a module too, for direct unit-level checks alongside the subprocess/CLI checks.
_spec = importlib.util.spec_from_file_location("devflow_cli", DEVFLOW_SCRIPT)
devflow = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(devflow)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DEVFLOW_SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} failed in {repo}: {result.stderr}"
    return result


def make_git_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    run_git(repo, "init", "-q", "-b", "main")
    run_git(repo, "config", "user.email", "fixture@example.com")
    run_git(repo, "config", "user.name", "Fixture")
    return repo


def commit_all(repo: Path, message: str = "init") -> None:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message)


def load_evidence_required_keys() -> list[str]:
    schema = json.loads(EVIDENCE_SCHEMA.read_text())
    return schema["required"]


EVIDENCE_REQUIRED_KEYS = load_evidence_required_keys()


def assert_matches_evidence_schema(doc: dict) -> None:
    """Hand-rolled structural check against devflow-evidence-v1.schema.json's top-level
    required keys and their declared enums — stands in for `jsonschema`, which is not
    installed in this environment (see module docstring)."""
    for key in EVIDENCE_REQUIRED_KEYS:
        assert key in doc, f"evidence output missing required key {key!r}: {doc.keys()}"
    assert doc["schema_version"] == "devflow-evidence-v1"
    assert isinstance(doc["repo_root"], str)
    git = doc["git"]
    for key in ("is_git_repo", "head", "branch", "detached", "status", "base", "changed_files"):
        assert key in git
    assert git["is_git_repo"] is True
    assert git["status"] in ("clean", "dirty")
    assert git["base"]["resolved_via"] in (
        "explicit",
        "explicit-unresolved",
        "upstream",
        "default-branch",
        "local-fallback",
        "unresolved",
    )
    for entry in git["changed_files"]:
        assert entry["origin"] in ("committed", "working_tree")
    assert isinstance(doc["protected_matches"], list)
    assert isinstance(doc["findings"], list)
    for finding in doc["findings"]:
        assert finding["severity"] in ("error", "warning", "info")
    assert isinstance(doc["healthy"], bool)
    assert doc["healthy"] == (not any(f["severity"] != "info" for f in doc["findings"]))


# ---------------------------------------------------------------------------
# CLI-level sanity: argument parsing, exit codes for usage errors
# ---------------------------------------------------------------------------


def test_no_subcommand_is_a_usage_error() -> None:
    result = run_cli()
    assert result.returncode == 2


def test_doctor_nonexistent_plugin_root_is_a_usage_error(tmp_path: Path) -> None:
    result = run_cli("doctor", "--plugin-root", str(tmp_path / "does-not-exist"))
    assert result.returncode == 2
    assert "does not exist" in result.stderr


def test_evidence_nonexistent_repo_is_a_usage_error(tmp_path: Path) -> None:
    result = run_cli("evidence", "--repo", str(tmp_path / "does-not-exist"))
    assert result.returncode == 2


def test_evidence_non_git_directory_is_a_usage_error(tmp_path: Path) -> None:
    plain_dir = tmp_path / "not-a-repo"
    plain_dir.mkdir()
    result = run_cli("evidence", "--repo", str(plain_dir))
    assert result.returncode == 2
    assert "not a git repository" in result.stderr


# ---------------------------------------------------------------------------
# doctor fixtures
# ---------------------------------------------------------------------------


def test_doctor_clean_plugin_is_healthy() -> None:
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_clean"), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    assert doc["schema_version"] == "devflow-doctor-v1"
    assert doc["healthy"] is True
    blocking = [f for f in doc["findings"] if f["severity"] != "info"]
    assert blocking == [], blocking
    # Regression guard: hooks/python-shebang.sh must be checked as Python (py_compile),
    # never as bash — its shebang is #!/usr/bin/python3 despite the .sh extension, exactly
    # like the real rhize-devflow/hooks/protect-files.sh.
    assert not any(f["id"] == "bash-syntax-error" for f in doc["findings"])


def test_doctor_missing_asset_is_reported_and_blocks() -> None:
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_missing_asset"), "--json")
    assert result.returncode == 1
    doc = json.loads(result.stdout)
    assert doc["healthy"] is False
    missing = [f for f in doc["findings"] if f["id"] == "missing-asset"]
    assert len(missing) == 1
    assert missing[0]["severity"] == "error"
    assert "does_not_exist.py" in missing[0]["message"]


def test_doctor_corrupt_manifest_is_reported_and_blocks() -> None:
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_corrupt_manifest"), "--json")
    assert result.returncode == 1
    doc = json.loads(result.stdout)
    assert doc["healthy"] is False
    invalid = [f for f in doc["findings"] if f["id"] == "invalid-json-manifest"]
    assert len(invalid) == 1
    assert invalid[0]["path"] == "setup/manifest.json"
    assert invalid[0]["severity"] == "error"


def test_doctor_missing_optional_cli_dependency_is_degraded_not_failed() -> None:
    result = run_cli(
        "doctor", "--plugin-root", str(FIXTURES / "doctor_missing_cli_dependency"), "--json"
    )
    # Missing an optional dependency must never fail the whole plugin.
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    assert doc["healthy"] is True
    cap = doc["capabilities"]["fake-capability"]
    assert cap["status"] == "degraded"
    assert cap["kind"] == "cli"
    assert cap["dependency"] == "Definitely Fake CLI Tool"
    # Degraded capabilities are reported separately from `findings` and never appear there.
    assert all(f["id"] != "fake-capability" for f in doc["findings"])


def test_doctor_bad_bash_hook_blocks() -> None:
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_bad_bash_hook"), "--json")
    assert result.returncode == 1
    doc = json.loads(result.stdout)
    errors = [f for f in doc["findings"] if f["id"] == "bash-syntax-error"]
    assert len(errors) == 1
    assert errors[0]["path"] == "hooks/broken.sh"


def test_doctor_bad_python_shebang_hook_blocks_via_py_compile() -> None:
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_bad_python_hook"), "--json")
    assert result.returncode == 1
    doc = json.loads(result.stdout)
    errors = [f for f in doc["findings"] if f["id"] == "py-compile-error"]
    assert len(errors) == 1
    assert errors[0]["path"] == "hooks/broken.sh"
    # And it must NOT be misreported as a bash syntax error.
    assert not any(f["id"] == "bash-syntax-error" for f in doc["findings"])


def test_doctor_text_output_is_not_json_but_runs_cleanly() -> None:
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_clean"))
    assert result.returncode == 0
    assert "devflow doctor" in result.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


def test_doctor_real_plugin_manifest_dependencies_are_optional() -> None:
    """Task 3 also modifies rhize-devflow/setup/manifest.json: all four dependencies become
    plugin-level optional (required: false) and each names the capability it enables."""
    manifest = json.loads((REPO_ROOT / "rhize-devflow" / "setup" / "manifest.json").read_text())
    deps = manifest["dependencies"]
    assert len(deps) == 4
    expected_capabilities = {
        "Sentry MCP server": "error-lifecycle",
        "Vercel MCP server": "deploy-correlation",
        "GitHub MCP server": "commit-pr-correlation",
        "Chrome DevTools MCP server": "browser-qa",
    }
    for dep in deps:
        assert dep["required"] is False, dep["name"]
        assert dep.get("capability") == expected_capabilities[dep["name"]]


# ---------------------------------------------------------------------------
# MCP server detection — repo-local .mcp.json, ~/.claude.json, ~/.codex/config.toml
# ---------------------------------------------------------------------------


def _make_plugin_root(tmp_path: Path, name: str = "myplugin") -> Path:
    """A bare plugin dir under a fake repo root, matching the (plugin_root, plugin_root.parent)
    relationship devflow.py assumes: plugin_root.parent is the repo root that owns the
    repo-local .mcp.json and is the key devflow looks up in ~/.claude.json's `projects`."""
    repo_root = tmp_path / "repo"
    plugin_root = repo_root / name
    plugin_root.mkdir(parents=True)
    return plugin_root


def test_mcp_names_default_sources_empty_when_nothing_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = _make_plugin_root(tmp_path)
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.delenv("DEVFLOW_MCP_CONFIG_PATHS", raising=False)
    monkeypatch.setattr(devflow.Path, "home", lambda: fake_home)
    assert devflow._configured_mcp_server_names(plugin_root) == {}


def test_mcp_names_repo_local_mcp_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_root = _make_plugin_root(tmp_path)
    (plugin_root.parent / ".mcp.json").write_text(json.dumps({"mcpServers": {"repo-server": {}}}))
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.delenv("DEVFLOW_MCP_CONFIG_PATHS", raising=False)
    monkeypatch.setattr(devflow.Path, "home", lambda: fake_home)
    names = devflow._configured_mcp_server_names(plugin_root)
    assert names == {"repo-server": {"repo"}}


def test_mcp_names_claude_user_top_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_root = _make_plugin_root(tmp_path)
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {"fake-mcp-server": {"command": "should-not-leak", "env": {"TOKEN": "secret"}}},
                "projects": {},
            }
        )
    )
    monkeypatch.delenv("DEVFLOW_MCP_CONFIG_PATHS", raising=False)
    monkeypatch.setattr(devflow.Path, "home", lambda: fake_home)
    names = devflow._configured_mcp_server_names(plugin_root)
    assert names == {"fake-mcp-server": {"claude-user"}}


def test_mcp_names_claude_user_per_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_root = _make_plugin_root(tmp_path)
    repo_root = plugin_root.parent
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {},
                "projects": {
                    str(repo_root.resolve()): {"mcpServers": {"project-scoped-server": {}}},
                    str(tmp_path / "some-other-repo"): {"mcpServers": {"other-repo-server": {}}},
                },
            }
        )
    )
    monkeypatch.delenv("DEVFLOW_MCP_CONFIG_PATHS", raising=False)
    monkeypatch.setattr(devflow.Path, "home", lambda: fake_home)
    names = devflow._configured_mcp_server_names(plugin_root)
    # Only the entry for THIS repo's path is read — other projects' servers must not leak in.
    assert names == {"project-scoped-server": {"claude-user"}}


def test_mcp_names_codex_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_root = _make_plugin_root(tmp_path)
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    codex_dir = fake_home / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text('[mcp_servers.codex-server]\ncommand = "should-not-leak"\n')
    monkeypatch.delenv("DEVFLOW_MCP_CONFIG_PATHS", raising=False)
    monkeypatch.setattr(devflow.Path, "home", lambda: fake_home)
    names = devflow._configured_mcp_server_names(plugin_root)
    assert names == {"codex-server": {"codex-user"}}


def test_mcp_names_combines_all_default_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_root = _make_plugin_root(tmp_path)
    (plugin_root.parent / ".mcp.json").write_text(json.dumps({"mcpServers": {"repo-server": {}}}))
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".claude.json").write_text(json.dumps({"mcpServers": {"claude-server": {}}, "projects": {}}))
    codex_dir = fake_home / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text('[mcp_servers.codex-server]\ncommand = "x"\n')
    monkeypatch.delenv("DEVFLOW_MCP_CONFIG_PATHS", raising=False)
    monkeypatch.setattr(devflow.Path, "home", lambda: fake_home)
    names = devflow._configured_mcp_server_names(plugin_root)
    assert names == {
        "repo-server": {"repo"},
        "claude-server": {"claude-user"},
        "codex-server": {"codex-user"},
    }


def test_mcp_names_malformed_files_are_skipped_not_crashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = _make_plugin_root(tmp_path)
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".claude.json").write_text("{not valid json")
    codex_dir = fake_home / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text("this = is [ not valid toml")
    monkeypatch.delenv("DEVFLOW_MCP_CONFIG_PATHS", raising=False)
    monkeypatch.setattr(devflow.Path, "home", lambda: fake_home)
    # Must not raise — malformed sources are treated as absent.
    names = devflow._configured_mcp_server_names(plugin_root)
    assert names == {}


def test_mcp_names_env_override_replaces_defaults_entirely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = _make_plugin_root(tmp_path)
    (plugin_root.parent / ".mcp.json").write_text(json.dumps({"mcpServers": {"repo-server": {}}}))
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".claude.json").write_text(json.dumps({"mcpServers": {"claude-server": {}}, "projects": {}}))
    override_file = tmp_path / "override.json"
    override_file.write_text(json.dumps({"mcpServers": {"override-server": {}}}))
    monkeypatch.setenv("DEVFLOW_MCP_CONFIG_PATHS", str(override_file))
    monkeypatch.setattr(devflow.Path, "home", lambda: fake_home)
    names = devflow._configured_mcp_server_names(plugin_root)
    # Only the override file's names appear — repo-local and claude-user are NOT merged in.
    assert names == {"override-server": {"override"}}


def test_doctor_mcp_capability_degraded_with_no_sources_configured(tmp_path: Path) -> None:
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    env = dict(os.environ, HOME=str(fake_home))
    env.pop("DEVFLOW_MCP_CONFIG_PATHS", None)
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_mcp_dependency"), "--json", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    assert doc["capabilities"]["fake-mcp-capability"]["status"] == "degraded"


def test_doctor_mcp_capability_ok_from_claude_user_config(tmp_path: Path) -> None:
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {"fake-mcp-server": {"command": "leaked-command-should-not-appear"}},
                "projects": {},
            }
        )
    )
    env = dict(os.environ, HOME=str(fake_home))
    env.pop("DEVFLOW_MCP_CONFIG_PATHS", None)
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_mcp_dependency"), "--json", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    cap = doc["capabilities"]["fake-mcp-capability"]
    assert cap["status"] == "ok"
    assert cap["detail"] == "found in configured mcpServers (source: claude-user)"
    # Redaction: no absolute path to the user config file, and no config VALUES, in JSON output.
    raw = json.dumps(doc)
    assert str(fake_home) not in raw
    assert ".claude.json" not in raw
    assert "leaked-command-should-not-appear" not in raw


def test_doctor_mcp_capability_redacts_codex_config_path_and_values(tmp_path: Path) -> None:
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    codex_dir = fake_home / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(
        '[mcp_servers.fake-mcp-server]\ncommand = "leaked-codex-command-should-not-appear"\n'
    )
    env = dict(os.environ, HOME=str(fake_home))
    env.pop("DEVFLOW_MCP_CONFIG_PATHS", None)
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_mcp_dependency"), "--json", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    cap = doc["capabilities"]["fake-mcp-capability"]
    assert cap["status"] == "ok"
    assert cap["detail"] == "found in configured mcpServers (source: codex-user)"
    raw = json.dumps(doc)
    assert str(fake_home) not in raw
    assert "config.toml" not in raw
    assert "leaked-codex-command-should-not-appear" not in raw


def test_doctor_mcp_env_override_still_wins_over_home_configs(tmp_path: Path) -> None:
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".claude.json").write_text(json.dumps({"mcpServers": {"fake-mcp-server": {}}, "projects": {}}))
    override_file = tmp_path / "override.json"
    override_file.write_text(json.dumps({"mcpServers": {"unrelated-server": {}}}))
    env = dict(os.environ, HOME=str(fake_home), DEVFLOW_MCP_CONFIG_PATHS=str(override_file))
    result = run_cli("doctor", "--plugin-root", str(FIXTURES / "doctor_mcp_dependency"), "--json", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    # ~/.claude.json WOULD match, but the override replaces defaults entirely and doesn't
    # contain a matching server name, so the capability stays degraded.
    assert doc["capabilities"]["fake-mcp-capability"]["status"] == "degraded"


# ---------------------------------------------------------------------------
# evidence fixtures
# ---------------------------------------------------------------------------


def test_evidence_clean_repo(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "README.md").write_text("hello\n")
    commit_all(repo, "initial commit")

    result = run_cli("evidence", "--repo", str(repo), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    assert_matches_evidence_schema(doc)
    assert doc["repo_root"] == str(repo.resolve())
    assert doc["git"]["status"] == "clean"
    assert doc["git"]["detached"] is False
    assert doc["git"]["branch"] == "main"
    assert doc["protected_matches"] == []
    assert doc["findings"] == []
    assert doc["healthy"] is True


def test_evidence_detached_head(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "a.txt").write_text("a\n")
    commit_all(repo, "first")
    (repo / "b.txt").write_text("b\n")
    commit_all(repo, "second")
    first_sha = run_git(repo, "rev-parse", "HEAD~1").stdout.strip()
    run_git(repo, "checkout", "-q", first_sha)

    result = run_cli("evidence", "--repo", str(repo), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    assert_matches_evidence_schema(doc)
    assert doc["git"]["detached"] is True
    assert doc["git"]["branch"] is None
    detached_findings = [f for f in doc["findings"] if f["id"] == "detached-head"]
    assert len(detached_findings) == 1
    assert detached_findings[0]["severity"] == "info"
    # Detached HEAD alone is informational, not blocking.
    assert doc["healthy"] is True


def test_evidence_multi_repo_two_roots_detected_separately(tmp_path: Path) -> None:
    repo_a = make_git_repo(tmp_path, "repo-a")
    (repo_a / "only-in-a.txt").write_text("a\n")
    commit_all(repo_a, "a init")

    repo_b = make_git_repo(tmp_path, "repo-b")
    (repo_b / "only-in-b.txt").write_text("b\n")
    commit_all(repo_b, "b init")
    (repo_b / ".github" / "workflows").mkdir(parents=True)
    (repo_b / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    # leave this one uncommitted so it shows up as a protected working-tree change

    result_a = run_cli("evidence", "--repo", str(repo_a), "--json")
    result_b = run_cli("evidence", "--repo", str(repo_b), "--json")
    doc_a = json.loads(result_a.stdout)
    doc_b = json.loads(result_b.stdout)

    assert doc_a["repo_root"] == str(repo_a.resolve())
    assert doc_b["repo_root"] == str(repo_b.resolve())
    assert doc_a["repo_root"] != doc_b["repo_root"]

    # repo A's evidence must not leak repo B's protected-file finding, and vice versa.
    assert doc_a["protected_matches"] == []
    assert result_a.returncode == 0
    assert doc_b["protected_matches"] == [".github/workflows/ci.yml"]
    assert result_b.returncode == 1

    a_paths = {c["path"] for c in doc_a["git"]["changed_files"]}
    b_paths = {c["path"] for c in doc_b["git"]["changed_files"]}
    assert "only-in-b.txt" not in a_paths
    assert "only-in-a.txt" not in b_paths


def test_evidence_protected_file_touch(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "README.md").write_text("hello\n")
    commit_all(repo, "initial")
    (repo / ".env").write_text("SECRET=1\n")

    result = run_cli("evidence", "--repo", str(repo), "--json")
    assert result.returncode == 1
    doc = json.loads(result.stdout)
    assert_matches_evidence_schema(doc)
    assert ".env" in doc["protected_matches"]
    protected_findings = [f for f in doc["findings"] if f["id"] == "protected-file-touch"]
    assert len(protected_findings) == 1
    assert protected_findings[0]["severity"] == "warning"
    assert doc["healthy"] is False


def test_evidence_stale_codegraph_index(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('v1')\n")
    commit_all(repo, "initial")

    cg_dir = repo / ".codegraph"
    cg_dir.mkdir()
    db_path = cg_dir / "index.db"
    db_path.write_text("fake sqlite bytes")
    import os
    import time

    old_time = time.time() - 3600
    os.utime(db_path, (old_time, old_time))

    # Touch the tracked source file so it is newer than the (never-initialized-by-this-CLI)
    # CodeGraph db — devflow.py must report staleness, never rebuild the index.
    (repo / "src" / "main.py").write_text("print('v2')\n")
    commit_all(repo, "touch source")

    result = run_cli("evidence", "--repo", str(repo), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    assert_matches_evidence_schema(doc)
    assert doc["codegraph"]["exists"] is True
    assert doc["codegraph"]["db_present"] is True
    assert doc["codegraph"]["stale"] is True
    stale_findings = [f for f in doc["findings"] if f["id"] == "codegraph-stale"]
    assert len(stale_findings) == 1
    assert stale_findings[0]["severity"] == "info"
    # Staleness is report-only — never blocking, and never a reason to (re)initialize.
    assert doc["healthy"] is True
    assert not (cg_dir / "rebuilt").exists()


def test_evidence_missing_codegraph_index_is_reported_absent(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "README.md").write_text("hello\n")
    commit_all(repo, "initial")

    result = run_cli("evidence", "--repo", str(repo), "--json")
    doc = json.loads(result.stdout)
    assert doc["codegraph"] == {
        "exists": False,
        "db_present": False,
        "db_path": None,
        "db_mtime": None,
        "newest_source_mtime": None,
        "stale": None,
    }
    assert not (repo / ".codegraph").exists()


def test_evidence_never_executes_package_scripts(tmp_path: Path) -> None:
    """package.json scripts are collected as names/text only. A script that would fail
    loudly if executed proves the CLI never ran it."""
    repo = make_git_repo(tmp_path)
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "fixture",
                "scripts": {
                    "boom": "python3 -c \"import sys; sys.exit(1)\"",
                    "build": "echo would-build",
                },
            }
        )
    )
    commit_all(repo, "initial")

    result = run_cli("evidence", "--repo", str(repo), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    doc = json.loads(result.stdout)
    assert doc["package_scripts"] == {
        "boom": "python3 -c \"import sys; sys.exit(1)\"",
        "build": "echo would-build",
    }


def test_evidence_reports_changed_test_candidates_as_advisory_only(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "src.css").write_text(".dark { color: white }\n")
    (repo / "style.test.js").write_text(
        "const text = readFile('src.css');\nexpect(text).toContain('.dark');\n"
    )
    commit_all(repo, "initial")
    (repo / "style.test.js").write_text(
        "const text = readFile('src.css');\nexpect(text).toContain('color');\n"
    )

    result = run_cli("evidence", "--repo", str(repo), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    candidates = json.loads(result.stdout)["test_evidence_candidates"]
    assert candidates == [
        {
            "test_path": "style.test.js",
            "related_production_files": [],
            "declared_invariant": None,
            "contract_class": None,
            "oracle_status": "unreviewed",
            "review_status": "advisory",
            "signals": ["changed_test", "source_content_assertion"],
        }
    ]


def test_evidence_package_manager_and_instruction_file_facts(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "package-lock.json").write_text("{}\n")
    (repo / "CLAUDE.md").write_text("# instructions\n")
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.local.json").write_text("{}\n")
    commit_all(repo, "initial")

    result = run_cli("evidence", "--repo", str(repo), "--json")
    doc = json.loads(result.stdout)
    assert doc["package_manager"]["lockfiles"] == ["npm"]
    assert doc["instruction_files"]["CLAUDE.md"] is True
    assert doc["instruction_files"]["AGENTS.md"] is False
    assert doc["instruction_files"]["settings.json_glob"] == [".claude/settings.local.json"]


def test_evidence_redacts_paths_outside_repo_root(tmp_path: Path) -> None:
    """Every path in the JSON output besides repo_root itself must be repo-relative — no
    other absolute filesystem path (e.g. this tmp_path's parent, or the CLI's own install
    location) may leak into evidence output."""
    repo = make_git_repo(tmp_path)
    (repo / "README.md").write_text("hello\n")
    commit_all(repo, "initial")

    result = run_cli("evidence", "--repo", str(repo), "--json")
    doc = json.loads(result.stdout)
    raw = json.dumps(doc)
    assert str(tmp_path) not in raw.replace(doc["repo_root"], "")
    assert str(DEVFLOW_SCRIPT.parent) not in raw


def test_evidence_explicit_base_resolves(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "a.txt").write_text("a\n")
    commit_all(repo, "first")
    base_sha = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "b.txt").write_text("b\n")
    commit_all(repo, "second")

    result = run_cli("evidence", "--repo", str(repo), "--base", base_sha, "--json")
    doc = json.loads(result.stdout)
    assert doc["git"]["base"]["resolved_via"] == "explicit"
    assert doc["git"]["base"]["sha"] == base_sha
    committed = [c for c in doc["git"]["changed_files"] if c["origin"] == "committed"]
    assert {c["path"] for c in committed} == {"b.txt"}


def test_evidence_explicit_unresolvable_base_is_reported(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    (repo / "a.txt").write_text("a\n")
    commit_all(repo, "first")

    result = run_cli("evidence", "--repo", str(repo), "--base", "totally-not-a-ref", "--json")
    doc = json.loads(result.stdout)
    assert doc["git"]["base"]["resolved_via"] == "explicit-unresolved"
    unresolved = [f for f in doc["findings"] if f["id"] == "base-unresolved"]
    assert len(unresolved) == 1
    assert unresolved[0]["severity"] == "warning"
    assert doc["healthy"] is False
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Direct unit-level checks on the imported module (protected-path matcher,
# healthy computation) — cheap, no subprocess needed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        (".env", True),
        (".env.local", True),
        ("apps/web/.env.production", True),
        (".github/workflows/ci.yml", True),
        ("subdir/.github/workflows/nope.yml", False),  # only matches at repo root
        ("src/billing/invoice.ts", True),
        ("src/payments/charge.ts", True),
        ("src/env-utils.ts", False),
        ("README.md", False),
    ],
)
def test_is_protected_matcher(path: str, expected: bool) -> None:
    assert devflow.is_protected(path) is expected


def test_is_healthy_ignores_info_severity() -> None:
    findings = [
        devflow.make_finding("a", "info", "informational only"),
        devflow.make_finding("b", "info", "also informational"),
    ]
    assert devflow.is_healthy(findings) is True
    findings.append(devflow.make_finding("c", "warning", "this blocks"))
    assert devflow.is_healthy(findings) is False
