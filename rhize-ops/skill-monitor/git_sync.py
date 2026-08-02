#!/usr/bin/env python3
"""
git_sync.py — self-sync for the skill-monitor scheduled run (stdlib only).

Wired into monitor.py's main(): pull --rebase before scanning, commit+push
new snapshots after. Also provides the Phase 4.1 config-sync sweep for the
other tracked config repos, run standalone by the scheduled task.
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOTS_DIR = Path(__file__).resolve().parent / "data" / "snapshots"
CONFIG_SYNC_REPOS = [
    Path.home() / ".claude",
    Path.home() / ".agents",
    Path.home() / "dev-local" / "RHIZE" / "rhize-plugins",
    Path.home() / "dev-local" / "RHIZE" / "skill-forge",
]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def _fail(repo: Path, what: str, result: subprocess.CompletedProcess) -> None:
    print(f"[config-sync FAIL] {repo}: {what}\n{result.stderr.strip()}")


def pull_rebase(repo: Path = REPO_ROOT) -> None:
    """Run before the monitor scans. Never leaves a rebase in progress."""
    result = _run(["git", "pull", "--rebase"], repo)
    if result.returncode != 0:
        _run(["git", "rebase", "--abort"], repo)
        _fail(repo, "pull --rebase conflicted, aborted rebase — resolve manually", result)


def commit_and_push_snapshots(repo: Path = REPO_ROOT) -> None:
    """Run after the monitor writes its snapshot. Commits only the snapshots dir."""
    status = _run(["git", "status", "--porcelain", "--", str(SNAPSHOTS_DIR)], repo)
    if not status.stdout.strip():
        return
    _run(["git", "add", "--", str(SNAPSHOTS_DIR)], repo)
    msg = f"chore(skill-monitor): snapshot {date.today().isoformat()}"
    commit = _run(["git", "commit", "-m", msg], repo)
    if commit.returncode != 0:
        return _fail(repo, "snapshot commit failed", commit)
    push = _run(["git", "push"], repo)
    if push.returncode != 0:
        _fail(repo, "snapshot push failed", push)


def config_sync_sweep() -> None:
    """Phase 4.1: for each tracked config repo, commit+push if dirty, else pull if behind."""
    today = date.today().isoformat()
    for repo in CONFIG_SYNC_REPOS:
        if not (repo / ".git").exists():
            continue
        status = _run(["git", "status", "--porcelain"], repo)
        if status.returncode != 0:
            _fail(repo, "git status errored", status)
            continue
        if status.stdout.strip():
            _run(["git", "add", "-A"], repo)
            commit = _run(["git", "commit", "-m", f"chore(sync): scheduled config sync {today}"], repo)
            if commit.returncode != 0:
                _fail(repo, "commit failed", commit)
                continue
            push = _run(["git", "push"], repo)
            if push.returncode != 0:
                _fail(repo, "push failed", push)
            continue
        _run(["git", "fetch"], repo)
        behind = _run(["git", "rev-list", "--count", "HEAD..@{u}"], repo)
        if behind.returncode == 0 and behind.stdout.strip() not in ("", "0"):
            rebase = _run(["git", "pull", "--rebase"], repo)
            if rebase.returncode != 0:
                _run(["git", "rebase", "--abort"], repo)
                _fail(repo, "pull --rebase conflicted, aborted rebase", rebase)


if __name__ == "__main__":
    config_sync_sweep()
