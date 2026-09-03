"""test_setup_orchestrator.py — rhize-core/scripts/setup_orchestrator.py (hybrid-setup-wizard.md
R2 §2, §6; moved from rhize-ops in repo-shape R-B). Every fixture is hermetic: a throwaway --home
and --project tree, never the real machine or the real repo (except the one dry-run test at the
bottom of this file, which only reads the real repo and never writes to it).

Every fixture here builds a synthetic marketplace with a fake `rhize-ops` plugin dir as the
"is this a rhize-plugins root" signature — that keeps working unchanged because
is_rhize_marketplace() accepts EITHER `rhize-core` or `rhize-ops` (RHIZE_SIGNATURE_PLUGIN /
RHIZE_SIGNATURE_FALLBACK_PLUGIN), so these fixtures double as regression coverage for a
pre-rhize-core (or rhize-ops-only) marketplace.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-core" / "scripts" / "setup_orchestrator.py"
SPEC = importlib.util.spec_from_file_location("setup_orchestrator", SCRIPT)
setup_orchestrator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(setup_orchestrator)

MARKETPLACE_JSON = {"name": "rhize-plugins", "plugins": [{"name": "rhize-ops"}]}


def make_plugin_dir(root: Path, name: str, *, version: str = "1.0.0", manifest: dict | None = None) -> Path:
    plugin_dir = root / name
    plugin_json_dir = plugin_dir / ".claude-plugin"
    plugin_json_dir.mkdir(parents=True, exist_ok=True)
    (plugin_json_dir / "plugin.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
    if manifest is not None:
        setup_dir = plugin_dir / "setup"
        setup_dir.mkdir(exist_ok=True)
        (setup_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return plugin_dir


def make_marketplace_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin").mkdir(exist_ok=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(MARKETPLACE_JSON), encoding="utf-8")
    return root


def hook_manifest(item_id: str = "the-hook", event: str = "SessionStart", command: str = "${CLAUDE_PLUGIN_ROOT}/hooks/x.sh") -> dict:
    return {
        "schema": 3,
        "plugin": "rhize-ops",
        "items": [{"id": item_id, "title": "The hook", "tier": "T3", "event": event, "command": command, "description": "d", "default": False}],
        "dependencies": [],
        "artifacts": [],
        "evaluations": {"catalog": "rhize-evaluations-v1", "component": "rhize-ops"},
    }


def run_cli(*args: str) -> tuple[int, dict]:
    import subprocess
    completed = subprocess.run(["python3", str(SCRIPT), *args], capture_output=True, text=True, check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": completed.stdout, "stderr": completed.stderr}
    return completed.returncode, payload


# ---------- discover ----------

def test_discover_against_a_dev_repo(tmp_path: Path) -> None:
    dev_repo = make_marketplace_root(tmp_path / "dev-repo")
    make_plugin_dir(dev_repo, "rhize-ops", manifest=hook_manifest())
    home = tmp_path / "home"
    code, result = run_cli("discover", "--json", "--home", str(home), "--project", str(dev_repo))
    assert code == 0, result
    assert result["source"]["kind"] == "dev-repo"
    assert result["source"]["clone_name"] == "dev-repo"
    plugin = next(p for p in result["plugins"] if p["name"] == "rhize-ops")
    assert plugin["enabled"] is True
    assert plugin["enabled_reason"] == "dev-repo-default"
    assert plugin["manifest"]["schema"] == 3
    assert plugin["manifest"]["items"][0]["status"] == "not wired"


def test_discover_against_a_marketplace_clone(tmp_path: Path) -> None:
    home = tmp_path / "home"
    clone = make_marketplace_root(home / ".claude" / "plugins" / "marketplaces" / "rhize-plugins")
    make_plugin_dir(clone, "rhize-ops", manifest=hook_manifest())
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"rhize-ops@rhize-plugins": True}}), encoding="utf-8",
    )
    project = tmp_path / "some-project"
    project.mkdir()
    code, result = run_cli("discover", "--json", "--home", str(home), "--project", str(project))
    assert code == 0, result
    assert result["source"]["kind"] == "marketplace-clone"
    assert result["source"]["clone_name"] == "rhize-plugins"
    plugin = next(p for p in result["plugins"] if p["name"] == "rhize-ops")
    assert plugin["enabled"] is True
    assert plugin["enabled_reason"] == "enabledPlugins"


def test_discover_labels_machine_specific_entries_with_a_migration_hint(tmp_path: Path) -> None:
    """An entry wired with the absolute clone path is reported, never rewritten, and carries a
    hint naming the $HOME-portable prefix to switch to."""
    home = tmp_path / "home"
    clone = make_marketplace_root(home / ".claude" / "plugins" / "marketplaces" / "rhize-plugins")
    make_plugin_dir(clone, "rhize-ops", manifest=hook_manifest())
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"rhize-ops@rhize-plugins": True}}), encoding="utf-8",
    )
    project = tmp_path / "some-project"
    (project / ".claude").mkdir(parents=True)
    code, first = run_cli("discover", "--json", "--home", str(home), "--project", str(project))
    assert code == 0, first
    item = next(p for p in first["plugins"] if p["name"] == "rhize-ops")["manifest"]["items"][0]
    assert item["status"] == "not wired" and "migration_hint" not in item

    absolute = item["resolved_command"]
    wired = {"hooks": {item["event"]: [{"hooks": [{"type": "command", "command": absolute}]}]}}
    if item.get("matcher"):
        wired["hooks"][item["event"]][0]["matcher"] = item["matcher"]
    (project / ".claude" / "settings.json").write_text(json.dumps(wired), encoding="utf-8")

    code, second = run_cli("discover", "--json", "--home", str(home), "--project", str(project))
    assert code == 0, second
    item = next(p for p in second["plugins"] if p["name"] == "rhize-ops")["manifest"]["items"][0]
    assert item["status"] == "wired (machine-specific path)"
    assert "$HOME/.claude/plugins/marketplaces/rhize-plugins/rhize-ops" in item["migration_hint"]
    assert str(clone) in item["migration_hint"]


def test_discover_reports_disabled_plugin(tmp_path: Path) -> None:
    home = tmp_path / "home"
    clone = make_marketplace_root(home / ".claude" / "plugins" / "marketplaces" / "rhize-plugins")
    make_plugin_dir(clone, "rhize-ops", manifest=hook_manifest())
    make_plugin_dir(clone, "rhize-devflow", manifest=hook_manifest())
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"rhize-ops@rhize-plugins": True}}), encoding="utf-8",
    )
    project = tmp_path / "some-project"
    project.mkdir()
    code, result = run_cli("discover", "--json", "--home", str(home), "--project", str(project))
    assert code == 0, result
    devflow = next(p for p in result["plugins"] if p["name"] == "rhize-devflow")
    assert devflow["enabled"] is False
    assert devflow["enabled_reason"] == "not in enabledPlugins"


def test_discover_flags_clone_ahead_of_installed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    clone = make_marketplace_root(home / ".claude" / "plugins" / "marketplaces" / "rhize-plugins")
    make_plugin_dir(clone, "rhize-ops", version="2.0.0", manifest=hook_manifest())
    cache_dir = home / ".claude" / "plugins" / "cache" / "rhize-plugins" / "rhize-ops" / "1.0.0"
    cache_dir.mkdir(parents=True)
    project = tmp_path / "some-project"
    project.mkdir()
    code, result = run_cli("discover", "--json", "--home", str(home), "--project", str(project))
    assert code == 0, result
    plugin = next(p for p in result["plugins"] if p["name"] == "rhize-ops")
    assert plugin["clone_version"] == "2.0.0"
    assert plugin["installed_version"] == "1.0.0"
    assert plugin["clone_ahead_of_installed"] is True


def test_discover_reports_schema_1_as_evaluation_missing(tmp_path: Path) -> None:
    dev_repo = make_marketplace_root(tmp_path / "dev-repo")
    make_plugin_dir(dev_repo, "rhize-ops", manifest={
        "schema": 1, "plugin": "rhize-ops", "items": [], "dependencies": [],
    })
    home = tmp_path / "home"
    code, result = run_cli("discover", "--json", "--home", str(home), "--project", str(dev_repo))
    assert code == 0, result
    plugin = next(p for p in result["plugins"] if p["name"] == "rhize-ops")
    assert plugin["manifest"]["evaluation_status"] == "missing"
    assert any("evaluation catalog missing" in warning for warning in result["warnings"])


def test_discover_dry_run_against_the_real_dev_repo_finds_all_ten_plugins(tmp_path: Path) -> None:
    """Verification step from the task brief: a dry run against this dev repo (read-only —
    --home/--project point at throwaway fixtures) must print all ten plugins, including the new
    rhize-core split (repo-shape R-B)."""
    home = tmp_path / "home"
    code, result = run_cli("discover", "--json", "--home", str(home), "--project", str(REPO))
    assert code == 0, result
    assert result["source"]["kind"] == "dev-repo"
    assert len(result["plugins"]) == 10
    assert {p["name"] for p in result["plugins"]} == {
        "obsidian-second-brain", "procedural-memory", "project-launcher", "rhize-context-manager",
        "rhize-core", "rhize-cowork", "rhize-devflow", "rhize-ops", "rhize-tasks", "seo-aeo-geo",
    }


# ---------- hooks plan ----------

def test_hooks_plan_home_form_from_a_clone_path(tmp_path: Path) -> None:
    home = tmp_path / "home"
    clone = make_marketplace_root(home / ".claude" / "plugins" / "marketplaces" / "rhize-plugins")
    make_plugin_dir(clone, "rhize-ops", manifest=hook_manifest())
    project = tmp_path / "some-project"
    project.mkdir()
    code, result = run_cli(
        "hooks", "plan", "--plugin", "rhize-ops", "--item", "the-hook", "--json",
        "--home", str(home), "--project", str(project),
    )
    assert result["portability"] == "portable"
    assert result["resolved_command"] == "$HOME/.claude/plugins/marketplaces/rhize-plugins/rhize-ops/hooks/x.sh"


def test_hooks_plan_flags_dev_repo(tmp_path: Path) -> None:
    dev_repo = make_marketplace_root(tmp_path / "dev-repo")
    make_plugin_dir(dev_repo, "rhize-ops", manifest=hook_manifest())
    home = tmp_path / "home"
    code, result = run_cli(
        "hooks", "plan", "--plugin", "rhize-ops", "--item", "the-hook", "--json",
        "--home", str(home), "--project", str(dev_repo),
    )
    assert result["portability"] == "dev-repo"
    assert result["resolved_command"] == str(dev_repo / "rhize-ops" / "hooks" / "x.sh")


def test_smoke_test_expands_home_through_sh_c(tmp_path: Path) -> None:
    """The plan requires the smoke test to run through `sh -c` on the literal `$HOME` string
    so expansion is proven, not assumed -- this creates a real disposable hook script under
    the fixture home and confirms `$HOME` resolves to it."""
    home = tmp_path / "home"
    clone = make_marketplace_root(home / ".claude" / "plugins" / "marketplaces" / "rhize-plugins")
    make_plugin_dir(clone, "rhize-ops", manifest=hook_manifest(command="${CLAUDE_PLUGIN_ROOT}/hooks/x.sh"))
    hook_script = clone / "rhize-ops" / "hooks" / "x.sh"
    hook_script.parent.mkdir(parents=True, exist_ok=True)
    hook_script.write_text("#!/bin/sh\ntest -n \"$HOME\" && exit 0 || exit 1\n", encoding="utf-8")
    hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    project = tmp_path / "some-project"
    project.mkdir()

    code, result = run_cli(
        "hooks", "plan", "--plugin", "rhize-ops", "--item", "the-hook", "--json",
        "--home", str(home), "--project", str(project),
    )
    assert code == 0, result
    assert result["smoke_test"]["ran"] is True
    assert result["smoke_test"]["exit_code"] == 0
    assert result["smoke_test"]["passed"] is True
    assert result["smoke_test"]["stdin_kind"] == "empty"


def test_smoke_test_uses_tool_call_stdin_for_pretooluse() -> None:
    result = setup_orchestrator.smoke_test_command("cat >/dev/null", "PreToolUse", Path.home())
    assert result["stdin_kind"] == "tool-call"
    assert result["passed"] is True


# ---------- hooks apply ----------

def test_hooks_apply_merges_without_touching_other_entries(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    existing = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "/existing/unrelated-hook.sh"}]},
            ]
        },
        "enabledPlugins": {"someplugin@somewhere": True},
    }
    settings_path = project / ".claude" / "settings.json"
    settings_path.write_text(json.dumps(existing), encoding="utf-8")

    plan = [{
        "plugin": "rhize-ops", "item": "the-hook", "event": "SessionStart", "matcher": None,
        "resolved_command": "$HOME/.claude/plugins/marketplaces/rhize-plugins/rhize-ops/hooks/x.sh",
    }]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    code, result = run_cli("hooks", "apply", "--plan", str(plan_path), "--project", str(project), "--home", str(tmp_path / "home"))
    assert code == 0, result
    assert len(result["applied"]) == 1

    written = json.loads(settings_path.read_text())
    assert written["enabledPlugins"] == {"someplugin@somewhere": True}
    assert written["hooks"]["PreToolUse"] == existing["hooks"]["PreToolUse"]
    assert written["hooks"]["SessionStart"][0]["hooks"][0]["command"] == plan[0]["resolved_command"]


def test_hooks_apply_is_idempotent_and_never_duplicates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    plan = [{
        "plugin": "rhize-ops", "item": "the-hook", "event": "SessionStart", "matcher": None,
        "resolved_command": "$HOME/.claude/plugins/marketplaces/rhize-plugins/rhize-ops/hooks/x.sh",
    }]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    run_cli("hooks", "apply", "--plan", str(plan_path), "--project", str(project), "--home", str(tmp_path / "home"))
    code, result = run_cli("hooks", "apply", "--plan", str(plan_path), "--project", str(project), "--home", str(tmp_path / "home"))
    assert code == 0, result
    assert result["applied"] == []
    assert result["skipped"][0]["reason"] == "already wired"
    settings = json.loads((project / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["SessionStart"]) == 1


def test_hooks_apply_never_rewrites_a_machine_specific_entry(tmp_path: Path) -> None:
    """discover labels an absolute-path entry 'wired (machine-specific path)'; apply must
    never touch it -- it only appends new, separate entries, it doesn't rewrite in place."""
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    machine_specific_command = "/Users/someone/.claude/plugins/marketplaces/rhize-plugins/rhize-ops/hooks/x.sh"
    existing = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": machine_specific_command}]}]}}
    settings_path = project / ".claude" / "settings.json"
    settings_path.write_text(json.dumps(existing), encoding="utf-8")

    plan = [{
        "plugin": "rhize-ops", "item": "the-hook", "event": "SessionStart", "matcher": None,
        "resolved_command": "$HOME/.claude/plugins/marketplaces/rhize-plugins/rhize-ops/hooks/x.sh",
    }]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    run_cli("hooks", "apply", "--plan", str(plan_path), "--project", str(project), "--home", str(tmp_path / "home"))

    written = json.loads(settings_path.read_text())
    commands = [h["command"] for group in written["hooks"]["SessionStart"] for h in group["hooks"]]
    assert machine_specific_command in commands
    assert plan[0]["resolved_command"] in commands
    assert len(written["hooks"]["SessionStart"]) == 2


# ---------- artifacts snapshot ----------

def artifact_manifest(path: str) -> dict:
    return {
        "schema": 3, "plugin": "rhize-ops", "items": [], "dependencies": [],
        "artifacts": [{
            "id": "the-artifact", "path": path, "kind": "file", "purpose": "p", "viewer": "v",
            "lifetime": "persistent", "confidentiality": "config", "source": "authored",
            "tracked": "project", "optional": True,
        }],
        "evaluations": {"catalog": "rhize-evaluations-v1", "component": "rhize-ops"},
    }


def test_artifacts_snapshot_before_and_after(tmp_path: Path) -> None:
    home = tmp_path / "home"
    clone = make_marketplace_root(home / ".claude" / "plugins" / "marketplaces" / "rhize-plugins")
    make_plugin_dir(clone, "rhize-ops", manifest=artifact_manifest("<project>/config.json"))
    project = tmp_path / "project"
    project.mkdir()

    code, before = run_cli(
        "artifacts", "snapshot", "--before", "--home", str(home), "--project", str(project),
        "--run", "run-1", "--plugin", "rhize-ops",
    )
    assert code == 0, before
    assert before["rows"][0]["exists"] is False

    (project / "config.json").write_text("{}", encoding="utf-8")

    code, after = run_cli(
        "artifacts", "snapshot", "--after", "--home", str(home), "--project", str(project),
        "--run", "run-1", "--plugin", "rhize-ops",
    )
    assert code == 0, after
    assert after["rows"][0]["exists"] is True

    state = json.loads((home / ".rhize" / "setup" / "runs" / "run-1.json").read_text())
    assert state["artifacts_before"]["rows"][0]["exists"] is False
    assert state["artifacts_after"]["rows"][0]["exists"] is True
    assert stat.S_IMODE((home / ".rhize" / "setup" / "runs" / "run-1.json").stat().st_mode) == 0o600


# ---------- <vault> resolution: zero / one / multiple / absent ----------

def write_vault_resolve(root: Path, paths: list[str]) -> None:
    module_dir = root / "obsidian-second-brain" / "hooks" / "scripts"
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "vault_resolve.py").write_text(
        f"def resolve_vault_paths():\n    return {paths!r}\n", encoding="utf-8",
    )


@pytest.mark.parametrize("paths,expected_status", [
    ([], "unresolved (no vault found)"),
    (["/vaults/only-one"], "resolved"),
    (["/vaults/one", "/vaults/two"], "unresolved (multiple vaults found: 2)"),
])
def test_vault_placeholder_resolution_zero_one_multiple(tmp_path: Path, paths: list[str], expected_status: str) -> None:
    dev_repo = make_marketplace_root(tmp_path / "dev-repo")
    make_plugin_dir(dev_repo, "rhize-ops", manifest=artifact_manifest("<vault>/notes/file.md"))
    write_vault_resolve(dev_repo, paths)
    project = tmp_path / "project"
    project.mkdir()
    code, result = run_cli(
        "artifacts", "snapshot", "--before", "--home", str(tmp_path / "home"), "--project", str(dev_repo),
        "--plugin", "rhize-ops",
    )
    assert code == 0, result
    assert result["rows"][0]["vault_status"] == expected_status


def test_vault_placeholder_resolution_plugin_absent(tmp_path: Path) -> None:
    dev_repo = make_marketplace_root(tmp_path / "dev-repo")
    make_plugin_dir(dev_repo, "rhize-ops", manifest=artifact_manifest("<vault>/notes/file.md"))
    # No obsidian-second-brain plugin at all under this source root.
    code, result = run_cli(
        "artifacts", "snapshot", "--before", "--home", str(tmp_path / "home"), "--project", str(dev_repo),
        "--plugin", "rhize-ops",
    )
    assert code == 0, result
    assert result["rows"][0]["vault_status"] == "unresolved (obsidian-second-brain plugin not found)"
    assert result["rows"][0]["exists"] is False


# ---------- install-skill-map ----------

def test_install_skill_map_copies_and_reports_missing_overlay(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "generated").mkdir(parents=True)
    (source / "generated" / "skill-map.static.json").write_text("{}", encoding="utf-8")
    (source / "generated" / "skill-map.indexes.json").write_text("{}", encoding="utf-8")
    home = tmp_path / "home"

    code, result = run_cli("install-skill-map", "--source", str(source), "--home", str(home))
    assert code == 0, result
    assert sorted(result["copied"]) == ["skill-map.indexes.json", "skill-map.static.json"]
    assert result["missing"] == []
    assert result["overlay_status"] == "local overlay unavailable in installed mode"
    assert (home / ".claude" / "context-manager" / "skill-map.static.json").is_file()


def test_install_skill_map_builds_local_overlay_when_available(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "generated").mkdir(parents=True)
    (source / "generated" / "skill-map.static.json").write_text("{}", encoding="utf-8")
    (source / "generated" / "skill-map.indexes.json").write_text("{}", encoding="utf-8")
    builder_dir = source / "rhize-context-manager" / "scripts"
    builder_dir.mkdir(parents=True)
    (builder_dir / "build_local_skill_map.py").write_text(
        "import sys\nsys.exit(0)\n", encoding="utf-8",
    )
    home = tmp_path / "home"
    code, result = run_cli("install-skill-map", "--source", str(source), "--home", str(home))
    assert code == 0, result
    assert result["overlay_status"] == "local overlay built"


# ---------- report ----------

def test_report_renders_every_recorded_section(tmp_path: Path) -> None:
    home = tmp_path / "home"
    run_id = "fixture-run"
    state = {
        "discover": {
            "plugins": [
                {"name": "rhize-ops", "enabled": True, "clone_version": "1.0.0", "installed_version": "1.0.0",
                 "clone_ahead_of_installed": False,
                 "manifest": {"items": [{"id": "the-hook", "tier": "T3", "event": "SessionStart", "matcher": None, "status": "wired"}]}},
            ],
        },
        "dependency_check": {"rows": [{"plugin": "rhize-ops", "dependency": "rtk", "status": "present"}]},
        "artifacts_before": {"rows": [{"plugin": "rhize-ops", "id": "cfg", "resolved_path": str(home / ".rhize" / "cfg.json"), "exists": False, "vault_status": None}]},
        "artifacts_after": {"rows": [{"plugin": "rhize-ops", "id": "cfg", "resolved_path": str(home / ".rhize" / "cfg.json"), "exists": True, "vault_status": None}]},
        "install_skill_map": {"copied": ["skill-map.static.json"], "missing": [], "overlay_status": "local overlay built"},
    }
    setup_orchestrator.private_write_json(setup_orchestrator.run_state_path(home, run_id), state)

    # report prints plain text (tables), not JSON -- run_cli's JSON parse would just fall
    # back to {"stdout": ..., "stderr": ...}, so invoke it directly for the raw text.
    import subprocess
    completed = subprocess.run(
        ["python3", str(SCRIPT), "report", "--run", run_id, "--home", str(home)],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0
    text = completed.stdout
    assert "## Discovery" in text
    assert "## Hooks" in text
    assert "## Dependencies" in text
    assert "## Artifacts (before)" in text
    assert "## Artifacts (after)" in text
    assert "## Skill map install" in text
    assert "~/.rhize/cfg.json" in text
    assert "rhize-ops" in text


def test_report_record_persists_an_arbitrary_section(tmp_path: Path) -> None:
    home = tmp_path / "home"
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps({"rows": [{"a": 1}]}), encoding="utf-8")
    code, result = run_cli("report", "record", "--run", "run-2", "--section", "version_control", "--data", str(data_path), "--home", str(home))
    assert code == 0, result
    assert result["status"] == "recorded"
    state = json.loads(setup_orchestrator.run_state_path(home, "run-2").read_text())
    assert state["version_control"]["rows"] == [{"a": 1}]


def test_report_missing_run_exits_nonzero(tmp_path: Path) -> None:
    import subprocess
    completed = subprocess.run(
        ["python3", str(SCRIPT), "report", "--run", "does-not-exist", "--home", str(tmp_path / "home")],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 2
