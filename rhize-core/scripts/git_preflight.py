#!/usr/bin/env python3
"""Report Git tracking state for setup-wizard-managed customization surfaces, and
(only via the `track` subcommand) make a pathspec-limited baseline commit on
explicit request.

`report` (the default subcommand) never mutates anything. `track` is the only
mutating entry point, and only ever runs `git add` / `git commit` limited to
the exact paths it was given.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA = "rhize-git-preflight-v1"
FORBIDDEN_TRACK_STATES = {"MISSING", "IGNORED", "NOT_IN_REPO"}
ROW_KEYS = (
    "label", "path", "state", "baseline", "dirty",
    "would_be_ignored", "other_staged", "rollback_ready",
)
IMPORT_RE = re.compile(r"^@(\S+)$")


class PreflightError(ValueError):
    pass


def git_binary() -> str:
    binary = shutil.which("git")
    if binary is None:
        raise PreflightError("git is not installed or not on PATH")
    return binary


def run_git(git: str, cwd: Path | str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [git, "--literal-pathspecs", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def git_lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in result.stdout.split("\0") if line]


def check_would_be_ignored(git: str, cwd: str, pathspec: str) -> bool:
    # `check-ignore` rejects `--literal-pathspecs` outright ("pathspec magic
    # not supported by this command"). Its own arguments are always treated
    # as literal filesystem paths, never as gitignore-style patterns, so
    # omitting the flag here is safe.
    result = subprocess.run(
        [git, "-C", cwd, "check-ignore", "--no-index", "-q", "--", pathspec],
        capture_output=True, text=True, check=False,
    )
    return result.returncode == 0


def nearest_existing_ancestor(path: Path) -> Path:
    """Return an existing, real (non-symlink) directory at or above `path`,
    suitable for a git `-C` argument. A symlink is never followed to reach
    its target -- its parent is used instead -- and a file can't be `-C`'d
    into, so its parent is used too."""
    current = path
    while os.path.islink(current) or not os.path.isdir(current):
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current


def repo_pathspec(git: str, ancestor: Path, target: Path) -> tuple[str | None, str | None]:
    """Return (repo_root, pathspec) for `target`, or (None, None) if not in a repo.

    `ancestor` must be a real filesystem ancestor of `target` (or `target` itself).
    The pathspec is derived lexically from `ancestor` -> `target` plus git's own
    `--show-prefix`, so no path is ever resolved through a symlink to compute it —
    `-C <repo_root>` (git's own answer) is used for every subsequent command.
    """
    toplevel = run_git(git, ancestor, "rev-parse", "--show-toplevel")
    if toplevel.returncode != 0:
        return None, None
    repo_root = toplevel.stdout.strip()
    prefix = run_git(git, ancestor, "rev-parse", "--show-prefix").stdout.strip()
    tail = "" if target == ancestor else target.relative_to(ancestor).as_posix()
    combined = (prefix + tail).strip("/")
    return repo_root, combined or "."


def count_other_staged(git: str, repo_root: str, pathspecs: list[str]) -> int:
    staged = git_lines(run_git(git, repo_root, "diff", "--cached", "--name-only", "-z"))

    def under_any(entry: str) -> bool:
        return any(entry == spec or entry.startswith(spec + "/") for spec in pathspecs)

    return len([entry for entry in staged if not under_any(entry)])


def blank_row(state: str, would_be_ignored: bool | None = None) -> dict[str, Any]:
    return {
        "state": state,
        "baseline": None,
        "dirty": False,
        "would_be_ignored": would_be_ignored,
        "other_staged": None,
        "rollback_ready": False,
    }


def classify(git: str, path: Path, is_directory: bool) -> dict[str, Any]:
    exists = os.path.lexists(path)
    ancestor = nearest_existing_ancestor(path)
    repo_root, pathspec = repo_pathspec(git, ancestor, path)

    if repo_root is None:
        return blank_row("MISSING" if not exists else "NOT_IN_REPO")

    if not exists:
        row = blank_row("MISSING", would_be_ignored=check_would_be_ignored(git, repo_root, pathspec))
        row["other_staged"] = count_other_staged(git, repo_root, [pathspec])
        return row

    tracked = git_lines(run_git(git, repo_root, "ls-files", "-z", "--", pathspec))
    untracked = git_lines(run_git(git, repo_root, "ls-files", "-z", "--others", "--exclude-standard", "--", pathspec))
    ignored = git_lines(run_git(git, repo_root, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", pathspec))

    if tracked and (untracked or ignored) and is_directory:
        state = "MIXED"
    elif tracked:
        state = "TRACKED"
    elif untracked:
        state = "UNTRACKED"
    elif ignored:
        state = "IGNORED"
    else:
        # Nothing reported by any ls-files call (e.g. an empty directory): fall
        # back to whether it would be excluded if something were added to it.
        state = "IGNORED" if check_would_be_ignored(git, repo_root, pathspec) else "UNTRACKED"

    dirty = bool(git_lines(run_git(git, repo_root, "status", "--porcelain", "-z", "--", pathspec)))

    baseline = None
    if state in ("TRACKED", "MIXED"):
        head_probe = run_git(git, repo_root, "rev-parse", "--verify", "HEAD")
        if head_probe.returncode != 0:
            baseline = "NO_HEAD"
        else:
            head_files = set(git_lines(run_git(git, repo_root, "ls-tree", "-rz", "--name-only", "HEAD", "--", pathspec)))
            tracked_set = set(tracked)
            if tracked_set and tracked_set <= head_files:
                baseline = "COMMITTED"
            elif tracked_set and not (tracked_set & head_files):
                baseline = "UNCOMMITTED"
            else:
                baseline = "PARTIAL"

    return {
        "state": state,
        "baseline": baseline,
        "dirty": dirty,
        "would_be_ignored": None,
        "other_staged": count_other_staged(git, repo_root, [pathspec]),
        "rollback_ready": state == "TRACKED" and baseline == "COMMITTED" and not dirty,
    }


def display_path(path: Path, home: Path) -> str:
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


def resolve_cli_path(raw: str, base: Path | None = None) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (base or Path.cwd()) / path
    return Path(os.path.normpath(str(path)))


def find_imports(claude_md: Path, base_dir: Path) -> list[tuple[str, Path]]:
    if not claude_md.is_file():
        return []
    try:
        text = claude_md.read_text(encoding="utf-8")
    except OSError as exc:
        raise PreflightError(f"{claude_md} is not readable: {exc}") from exc
    imports: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = IMPORT_RE.match(line.strip())
        if not match:
            continue
        name = match.group(1)
        if name in seen or Path(name).is_absolute():
            continue
        seen.add(name)
        imports.append((f"@{name}", base_dir / name))
    return imports


def skill_forge_rows(config_path: Path) -> list[tuple[str, Path, bool]]:
    if not config_path.exists():
        return []
    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PreflightError(f"skill-forge config is not readable: {exc}") from exc
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PreflightError(f"skill-forge config is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        return []
    rows: list[tuple[str, Path, bool]] = []
    roots = config.get("skillsRoots")
    if isinstance(roots, list):
        for index, entry in enumerate(roots):
            if isinstance(entry, str) and entry.strip():
                rows.append((f"skill-forge skillsRoots[{index}]", Path(entry).expanduser(), True))
    target = config.get("defaultTarget")
    if isinstance(target, str) and target.strip():
        rows.append(("skill-forge defaultTarget", Path(target).expanduser(), True))
    return rows


def build_rows(
    project: Path, home: Path, skill_forge_config: Path, only_paths: list[str] | None,
) -> list[dict[str, Any]]:
    git = git_binary()
    rows: list[dict[str, Any]] = []

    def add_row(label: str, path: Path, is_directory: bool) -> None:
        info = classify(git, path, is_directory)
        rows.append({"label": label, "path": display_path(path, home), **info})

    if only_paths:
        for raw in only_paths:
            path = resolve_cli_path(raw)
            is_directory = path.is_dir() and not path.is_symlink()
            add_row(raw, path, is_directory)
        return rows

    project_rows = [
        ("project .claude/settings.json", project / ".claude" / "settings.json", False),
        ("project .claude/skills/", project / ".claude" / "skills", True),
        ("project .claude/commands/", project / ".claude" / "commands", True),
        ("project CLAUDE.md", project / "CLAUDE.md", False),
    ]
    home_rows = [
        ("home .claude/skills/", home / ".claude" / "skills", True),
        ("home .claude/CLAUDE.md", home / ".claude" / "CLAUDE.md", False),
        ("home .claude/settings.json", home / ".claude" / "settings.json", False),
    ]
    for label, path, is_directory in project_rows + home_rows:
        add_row(label, path, is_directory)

    import_sources = (
        ("project CLAUDE.md", project / "CLAUDE.md", project),
        ("home CLAUDE.md", home / ".claude" / "CLAUDE.md", home / ".claude"),
    )
    for source_label, claude_md, base_dir in import_sources:
        for import_name, import_path in find_imports(claude_md, base_dir):
            add_row(f"{source_label} import {import_name}", import_path, False)

    for label, path, is_directory in skill_forge_rows(skill_forge_config):
        add_row(label, path, is_directory)

    return rows


def render_table(rows: list[dict[str, Any]]) -> str:
    header = " | ".join(ROW_KEYS)
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(" | ".join(str(row.get(key, "")) for key in ROW_KEYS))
    return "\n".join(lines)


def report_command(args: argparse.Namespace) -> int:
    try:
        rows = build_rows(
            resolve_cli_path(str(args.project)),
            resolve_cli_path(str(args.home)),
            resolve_cli_path(str(args.skill_forge_config)),
            args.paths,
        )
    except PreflightError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"schema": SCHEMA, "rows": rows}, indent=2, sort_keys=True))
    else:
        print(render_table(rows))
    return 0


def refusal_reason(target: Path, home_claude_root: Path) -> str | None:
    if target == home_claude_root:
        return "refusing to track the entire home Claude directory"
    if target.name == "settings.local.json":
        return "settings.local.json must never be tracked"
    try:
        relative_to_home_claude = target.relative_to(home_claude_root)
    except ValueError:
        relative_to_home_claude = None
    if relative_to_home_claude is not None and any(
        part in ("plugins", "projects") for part in relative_to_home_claude.parts
    ):
        return "paths under ~/.claude/plugins/ or ~/.claude/projects/ must never be tracked"
    return None


def track_command(args: argparse.Namespace) -> int:
    try:
        git = git_binary()
    except PreflightError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    home_claude_root = resolve_cli_path(str(Path.home() / ".claude"))
    targets: list[Path] = []
    for raw in args.path:
        target = resolve_cli_path(raw)
        reason = refusal_reason(target, home_claude_root)
        if reason:
            print(f"error: {reason}: {target}", file=sys.stderr)
            return 2
        is_directory = target.is_dir() and not target.is_symlink()
        status = classify(git, target, is_directory)
        if status["state"] in FORBIDDEN_TRACK_STATES:
            print(f"error: refusing to track {target}: state is {status['state']}", file=sys.stderr)
            return 2
        targets.append(target)

    repo_root: str | None = None
    pathspecs: list[str] = []
    for target in targets:
        ancestor = nearest_existing_ancestor(target)
        target_repo_root, pathspec = repo_pathspec(git, ancestor, target)
        if target_repo_root is None:
            print(f"error: {target} is not inside a Git repository", file=sys.stderr)
            return 2
        if repo_root is None:
            repo_root = target_repo_root
        elif target_repo_root != repo_root:
            print(f"error: {target} is not inside the same Git repository as {targets[0]}", file=sys.stderr)
            return 2
        pathspecs.append(pathspec)

    assert repo_root is not None  # guaranteed: targets is non-empty (argparse requires --path)
    other_staged = count_other_staged(git, repo_root, pathspecs)

    add_argv = [git, "--literal-pathspecs", "-C", repo_root, "add", "--", *pathspecs]
    commit_argv = [git, "--literal-pathspecs", "-C", repo_root, "commit", "-m", args.message, "--", *pathspecs]
    # Informational preamble goes to stderr so stdout carries only the final result.
    print(f"other_staged: {other_staged}", file=sys.stderr)
    print("will run:", file=sys.stderr)
    print("  " + " ".join(add_argv), file=sys.stderr)
    print("  " + " ".join(commit_argv), file=sys.stderr)

    add_result = subprocess.run(add_argv, capture_output=True, text=True, check=False)
    if add_result.returncode != 0:
        print(f"error: git add failed: {add_result.stderr.strip()}", file=sys.stderr)
        return 2
    commit_result = subprocess.run(commit_argv, capture_output=True, text=True, check=False)
    if commit_result.returncode != 0:
        print(f"error: git commit failed: {commit_result.stderr.strip()}", file=sys.stderr)
        return 2
    commit_hash = subprocess.run(
        [git, "-C", repo_root, "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
    ).stdout.strip()

    result = {"status": "committed", "commit": commit_hash, "paths": pathspecs, "other_staged": other_staged}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"committed {commit_hash}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report")
    report.add_argument("--project", type=Path, default=Path.cwd())
    report.add_argument("--home", type=Path, default=Path.home())
    report.add_argument("--skill-forge-config", type=Path, default=Path.home() / ".skill-forge" / "config.json")
    report.add_argument("--paths", action="append")
    report.add_argument("--json", action="store_true")
    report.set_defaults(handler=report_command)

    track = sub.add_parser("track")
    track.add_argument("--path", action="append", required=True)
    track.add_argument("--message", required=True)
    track.add_argument("--json", action="store_true")
    track.set_defaults(handler=track_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("report", "track"):
        argv = ["report", *argv]
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
