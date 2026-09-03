import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-core" / "scripts" / "git_preflight.py"
SPEC = importlib.util.spec_from_file_location("git_preflight", SCRIPT)
git_preflight = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(git_preflight)


GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # core.excludesFile=/dev/null keeps fixtures hermetic against a machine-wide
    # default excludes file (e.g. `~/.config/git/ignore`), which GIT_CONFIG_GLOBAL
    # alone does not override.
    return subprocess.run(
        [
            "git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "-c", "core.excludesFile=/dev/null", *args,
        ],
        cwd=cwd, capture_output=True, text=True, check=True, env=GIT_ENV,
    )


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")


def commit_all(path: Path, message: str) -> None:
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", message)


def run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    full_env = {**GIT_ENV, **(env or {})}
    return subprocess.run(
        ["python3", str(SCRIPT), *args], capture_output=True, text=True, check=False, env=full_env,
    )


def row(result: dict, label: str) -> dict:
    matches = [r for r in result["rows"] if r["label"] == label]
    assert matches, f"no row for label {label!r} in {[r['label'] for r in result['rows']]}"
    return matches[0]


def report_single_path(path: str, env: dict | None = None) -> dict:
    completed = run_cli("report", "--paths", path, "--json", env=env)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    return result["rows"][0]


def test_json_schema_is_pinned(tmp_path: Path) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    init_repo(project)
    (project / "CLAUDE.md").write_text("hello\n")
    commit_all(project, "baseline")
    completed = run_cli(
        "report", "--project", str(project), "--home", str(home), "--json",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["schema"] == "rhize-git-preflight-v1"
    assert isinstance(result["rows"], list) and result["rows"]
    expected_keys = {
        "label", "path", "state", "baseline", "dirty",
        "would_be_ignored", "other_staged", "rollback_ready",
    }
    for entry in result["rows"]:
        assert set(entry) == expected_keys


def test_tracked_committed_clean_file_is_rollback_ready(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    target = repo / "CLAUDE.md"
    target.write_text("content\n")
    commit_all(repo, "baseline")
    entry = report_single_path(str(target))
    assert entry["state"] == "TRACKED"
    assert entry["baseline"] == "COMMITTED"
    assert entry["dirty"] is False
    assert entry["rollback_ready"] is True


def test_untracked_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "seed.txt").write_text("x\n")
    commit_all(repo, "seed")
    target = repo / "new.txt"
    target.write_text("new\n")
    entry = report_single_path(str(target))
    assert entry["state"] == "UNTRACKED"
    assert entry["baseline"] is None
    assert entry["rollback_ready"] is False


def test_ignored_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / ".gitignore").write_text("ignored.txt\n")
    commit_all(repo, "seed")
    target = repo / "ignored.txt"
    target.write_text("secret\n")
    entry = report_single_path(str(target))
    assert entry["state"] == "IGNORED"
    assert entry["dirty"] is False


def test_not_in_repo(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    target = plain / "file.txt"
    target.write_text("x\n")
    entry = report_single_path(str(target))
    assert entry["state"] == "NOT_IN_REPO"
    assert entry["baseline"] is None
    assert entry["other_staged"] is None


def test_missing_not_in_repo(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    target = plain / "does-not-exist.txt"
    entry = report_single_path(str(target))
    assert entry["state"] == "MISSING"
    assert entry["would_be_ignored"] is None


def test_missing_inside_repo_would_be_ignored(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / ".gitignore").write_text("build/\n")
    commit_all(repo, "seed")
    ignored_missing = repo / "build" / "output.txt"
    entry = report_single_path(str(ignored_missing))
    assert entry["state"] == "MISSING"
    assert entry["would_be_ignored"] is True

    plain_missing = repo / "src" / "new.txt"
    entry2 = report_single_path(str(plain_missing))
    assert entry2["state"] == "MISSING"
    assert entry2["would_be_ignored"] is False


def test_mixed_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    target_dir = repo / "skills"
    target_dir.mkdir()
    (target_dir / "a.md").write_text("a\n")
    commit_all(repo, "seed a")
    (target_dir / "b.md").write_text("b\n")  # untracked sibling
    entry = report_single_path(str(target_dir))
    assert entry["state"] == "MIXED"


def test_partial_baseline_staged_but_uncommitted(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    target_dir = repo / "skills"
    target_dir.mkdir()
    (target_dir / "a.md").write_text("a\n")
    commit_all(repo, "seed a")
    (target_dir / "b.md").write_text("b\n")
    git(repo, "add", "skills/b.md")  # staged, never committed
    entry = report_single_path(str(target_dir))
    # Both files are tracked (in the index) -- MIXED is reserved for a mix of
    # tracked vs untracked/ignored content, a different axis from baseline.
    assert entry["state"] == "TRACKED"
    assert entry["baseline"] == "PARTIAL"


def test_no_head_empty_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    target = repo / "CLAUDE.md"
    target.write_text("fresh\n")
    git(repo, "add", "CLAUDE.md")
    entry = report_single_path(str(target))
    assert entry["state"] == "TRACKED"
    assert entry["baseline"] == "NO_HEAD"
    assert entry["rollback_ready"] is False


def test_other_staged_count(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "a.txt").write_text("a\n")
    (repo / "b.txt").write_text("b\n")
    commit_all(repo, "seed")
    (repo / "a.txt").write_text("a2\n")
    (repo / "b.txt").write_text("b2\n")
    git(repo, "add", "a.txt", "b.txt")
    entry = report_single_path(str(repo / "a.txt"))
    assert entry["other_staged"] == 1


def test_symlink_row_classified_as_the_link_itself(tmp_path: Path) -> None:
    outside_target = tmp_path / "outside_target_dir"
    outside_target.mkdir()
    (outside_target / "real.txt").write_text("real\n")

    repo = tmp_path / "repo"
    init_repo(repo)
    link = repo / "link_to_outside"
    os.symlink(outside_target, link)
    git(repo, "add", "link_to_outside")
    commit_all(repo, "add symlink")

    entry = report_single_path(str(link))
    # If the symlink had been followed, git would try to inspect
    # `outside_target`, which lives outside the repo entirely.
    assert entry["state"] == "TRACKED"
    assert entry["baseline"] == "COMMITTED"
    assert entry["rollback_ready"] is True


def test_glob_metacharacter_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    weird = repo / "weird[name]?.txt"
    weird.write_text("x\n")
    git(repo, "add", "--", "weird[name]?.txt")
    commit_all(repo, "weird name")
    entry = report_single_path(str(weird))
    assert entry["state"] == "TRACKED"
    assert entry["baseline"] == "COMMITTED"


def test_nested_repo(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    init_repo(outer)
    (outer / "outer.txt").write_text("outer\n")
    commit_all(outer, "outer baseline")

    inner = outer / "nested"
    init_repo(inner)
    inner_file = inner / "inner.txt"
    inner_file.write_text("inner\n")
    commit_all(inner, "inner baseline")

    entry = report_single_path(str(inner_file))
    assert entry["state"] == "TRACKED"
    assert entry["baseline"] == "COMMITTED"
    assert entry["rollback_ready"] is True
    # other_staged must reflect the INNER repo's index, not the outer one.
    assert entry["other_staged"] == 0


def test_git_absent(tmp_path: Path) -> None:
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = {"PATH": str(empty_bin)}
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "report", "--paths", str(tmp_path / "x.txt"), "--json"],
        capture_output=True, text=True, check=False, env=env,
    )
    assert completed.returncode == 2
    assert "git" in completed.stderr.lower()


def test_skill_forge_config_rows_appear_when_present(tmp_path: Path) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    config = tmp_path / "sf-config.json"
    config.write_text(json.dumps({
        "skillsRoots": [str(tmp_path / "root-a"), str(tmp_path / "root-b")],
        "defaultTarget": str(tmp_path / "root-a"),
    }))
    completed = run_cli(
        "report", "--project", str(project), "--home", str(home),
        "--skill-forge-config", str(config), "--json",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    labels = {entry["label"] for entry in result["rows"]}
    assert "skill-forge skillsRoots[0]" in labels
    assert "skill-forge skillsRoots[1]" in labels
    assert "skill-forge defaultTarget" in labels


def test_skill_forge_config_absent_adds_no_rows(tmp_path: Path) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    completed = run_cli(
        "report", "--project", str(project), "--home", str(home),
        "--skill-forge-config", str(tmp_path / "does-not-exist.json"), "--json",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    labels = {entry["label"] for entry in result["rows"]}
    assert not any(label.startswith("skill-forge") for label in labels)


def test_at_file_import_rows_are_discovered(tmp_path: Path) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    (home / ".claude").mkdir(parents=True)
    (project / "CLAUDE.md").write_text("intro\n@RULES.md\n\nmore text\n")
    (project / "RULES.md").write_text("rules\n")
    completed = run_cli("report", "--project", str(project), "--home", str(home), "--json")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    imported = row(result, "project CLAUDE.md import @RULES.md")
    # RULES.md exists on disk but `project` isn't a Git repo in this fixture.
    assert imported["state"] == "NOT_IN_REPO"
    assert imported["path"].endswith("RULES.md")


def test_default_rows_include_project_and_home_labels(tmp_path: Path) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    completed = run_cli("report", "--project", str(project), "--home", str(home), "--json")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    labels = {entry["label"] for entry in result["rows"]}
    for expected in (
        "project .claude/settings.json", "project .claude/skills/",
        "project .claude/commands/", "project CLAUDE.md",
        "home .claude/skills/", "home .claude/CLAUDE.md", "home .claude/settings.json",
    ):
        assert expected in labels


# --- track ---------------------------------------------------------------


def test_track_commits_only_named_paths_and_leaves_others_staged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "a.txt").write_text("a\n")
    (repo / "b.txt").write_text("b\n")
    commit_all(repo, "seed")
    (repo / "a.txt").write_text("a2\n")
    (repo / "b.txt").write_text("b2\n")
    git(repo, "add", "a.txt", "b.txt")

    completed = run_cli("track", "--path", str(repo / "a.txt"), "--message", "chore: baseline", "--json")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "committed"
    assert len(result["commit"]) == 40

    status = git(repo, "status", "--porcelain").stdout
    assert "M  b.txt" in status or "M b.txt" in status
    show = git(repo, "show", "--stat", "HEAD").stdout
    assert "a.txt" in show
    assert "b.txt" not in show


def test_track_refuses_missing_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "seed.txt").write_text("x\n")
    commit_all(repo, "seed")
    completed = run_cli("track", "--path", str(repo / "does-not-exist.txt"), "--message", "m")
    assert completed.returncode == 2
    assert "MISSING" in completed.stderr


def test_track_refuses_ignored_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / ".gitignore").write_text("secret.txt\n")
    commit_all(repo, "seed")
    (repo / "secret.txt").write_text("s\n")
    completed = run_cli("track", "--path", str(repo / "secret.txt"), "--message", "m")
    assert completed.returncode == 2
    assert "IGNORED" in completed.stderr


def test_track_refuses_not_in_repo(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    target = plain / "file.txt"
    target.write_text("x\n")
    completed = run_cli("track", "--path", str(target), "--message", "m")
    assert completed.returncode == 2
    assert "NOT_IN_REPO" in completed.stderr


def test_track_refuses_home_claude_root_itself(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    completed = run_cli(
        "track", "--path", str(home / ".claude"), "--message", "m",
        env={"HOME": str(home)},
    )
    assert completed.returncode == 2
    assert "entire home Claude directory" in completed.stderr


def test_track_refuses_plugins_and_projects_under_home_claude(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude" / "plugins" / "cache").mkdir(parents=True)
    (home / ".claude" / "projects" / "session").mkdir(parents=True)
    for sub in ("plugins/cache", "projects/session"):
        completed = run_cli(
            "track", "--path", str(home / ".claude" / sub), "--message", "m",
            env={"HOME": str(home)},
        )
        assert completed.returncode == 2, completed.stdout + completed.stderr
        assert "plugins" in completed.stderr or "projects" in completed.stderr


def test_track_refuses_settings_local_json(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.local.json").write_text("{}")
    commit_all(repo, "seed")
    completed = run_cli(
        "track", "--path", str(repo / ".claude" / "settings.local.json"), "--message", "m",
    )
    assert completed.returncode == 2
    assert "settings.local.json" in completed.stderr
