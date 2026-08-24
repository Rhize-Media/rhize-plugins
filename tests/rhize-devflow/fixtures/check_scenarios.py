"""Fixture repo builders for `/rhize-devflow:check` contract tests.

Each builder constructs a hermetic `tmp_path` git repo representing one of the seven check
scenarios named in `.claude/plans/rhize-devflow-v3-engineering-control-plane.md`, Task 5's
Verify list: frontend root, backend root, unavailable dependency, failing focused test,
failing required build, legitimate warning, and a no-code documentation-only change.

`/rhize-devflow:check` itself is an agent workflow — pytest never runs it. These builders
exist so `tests/rhize-devflow/test_command_contracts.py` can run the deterministic half
(`devflow.py evidence`) against a representative repo and assert the evidence packet gives
the agent the facts its command text needs to reach the right verdict. Git-repo-building
mirrors `test_devflow_cli.py`'s `make_git_repo`/`commit_all` conventions rather than
committing static trees, because every scenario here depends on real Git state (diffs,
working-tree status, protected-path matching).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} failed in {repo}: {result.stderr}"
    return result


def make_git_repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    run_git(repo, "init", "-q", "-b", "main")
    run_git(repo, "config", "user.email", "fixture@example.com")
    run_git(repo, "config", "user.name", "Fixture")
    return repo


def commit_all(repo: Path, message: str = "init") -> None:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message)


def write_package_json(repo: Path, scripts: dict) -> None:
    (repo / "package.json").write_text(
        json.dumps({"name": "fixture", "scripts": scripts}, indent=2) + "\n"
    )


def build_frontend_root(tmp_path: Path) -> Path:
    """A frontend workspace: package.json + npm lockfile, all four gate scripts declared,
    one changed source file under src/ (working-tree, not yet committed)."""
    repo = make_git_repo(tmp_path, "frontend")
    write_package_json(
        repo,
        {
            "test": "vitest run",
            "lint": "eslint .",
            "typecheck": "tsc --noEmit",
            "build": "next build",
        },
    )
    (repo / "package-lock.json").write_text("{}\n")
    (repo / "src").mkdir()
    (repo / "src" / "Widget.tsx").write_text("export const Widget = () => null;\n")
    commit_all(repo, "initial")
    (repo / "src" / "Widget.tsx").write_text("export const Widget = () => <div />;\n")
    return repo


def build_backend_root(tmp_path: Path) -> Path:
    """A Python backend workspace: pyproject.toml, no package.json, one changed source file
    under app/ (working-tree, not yet committed)."""
    repo = make_git_repo(tmp_path, "backend")
    (repo / "pyproject.toml").write_text('[project]\nname = "fixture-backend"\n')
    (repo / "app").mkdir()
    (repo / "app" / "routes.py").write_text("def health():\n    return 'ok'\n")
    commit_all(repo, "initial")
    (repo / "app" / "routes.py").write_text("def health():\n    return {'status': 'ok'}\n")
    return repo


def build_unavailable_dependency(tmp_path: Path) -> Path:
    """package.json declares gate scripts, but no lockfile is ever committed — the
    dependency state is unknown/unavailable, not merely "no gates declared"."""
    repo = make_git_repo(tmp_path, "unavailable-dep")
    write_package_json(repo, {"test": "jest", "build": "next build"})
    (repo / "index.js").write_text("module.exports = () => 1;\n")
    commit_all(repo, "initial")
    (repo / "index.js").write_text("module.exports = () => 2;\n")
    return repo


def build_failing_focused_test(tmp_path: Path) -> Path:
    """The declared `test` script genuinely exits non-zero when run — proves the evidence
    packet reports the exact command text an agent needs to reach `BLOCKED`."""
    repo = make_git_repo(tmp_path, "failing-test")
    write_package_json(
        repo,
        {"test": 'python3 -c "import sys; sys.exit(1)"', "build": 'python3 -c "pass"'},
    )
    (repo / "package-lock.json").write_text("{}\n")
    (repo / "src").mkdir()
    (repo / "src" / "broken.py").write_text("def add(a, b):\n    return a + b\n")
    commit_all(repo, "initial")
    (repo / "src" / "broken.py").write_text("def add(a, b):\n    return a - b  # bug\n")
    return repo


def build_failing_required_build(tmp_path: Path) -> Path:
    """The focused `test` script passes, but the required `build` script genuinely exits
    non-zero — proves a passing focused test cannot mask a failing required broader gate."""
    repo = make_git_repo(tmp_path, "failing-build")
    write_package_json(
        repo,
        {"test": 'python3 -c "pass"', "build": 'python3 -c "import sys; sys.exit(1)"'},
    )
    (repo / "package-lock.json").write_text("{}\n")
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('v1')\n")
    commit_all(repo, "initial")
    (repo / "src" / "main.py").write_text("print('v2')\n")
    return repo


def build_legitimate_warning(tmp_path: Path) -> Path:
    """A protected-file touch (`.env.local`) that repository instructions explicitly
    sanction for local dev — evidence must still surface it (severity: warning), never
    silently clear it, which is what lets the agent choose `PASS_WITH_WARNINGS` over
    `BLOCKED`."""
    repo = make_git_repo(tmp_path, "legit-warning")
    (repo / "CLAUDE.md").write_text(
        "# Repo policy\n\n"
        "`.env.local` changes are expected for local development and do not block "
        "`/rhize-devflow:check`.\n"
    )
    commit_all(repo, "initial")
    (repo / ".env.local").write_text("LOCAL_ONLY=1\n")
    return repo


def build_docs_only_change(tmp_path: Path) -> Path:
    """Only Markdown files changed — no source file changed, so no package script should be
    selected even though gate scripts are declared."""
    repo = make_git_repo(tmp_path, "docs-only")
    write_package_json(repo, {"test": "vitest run", "build": "next build"})
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text("# Guide\n\nOriginal.\n")
    commit_all(repo, "initial")
    (repo / "docs" / "guide.md").write_text("# Guide\n\nUpdated wording only.\n")
    (repo / "README.md").write_text("# Fixture docs-only\n")
    return repo
