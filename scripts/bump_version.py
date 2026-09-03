#!/usr/bin/env python3
"""bump_version.py — coordinated semver bumps for the rhize-plugins marketplace.

Keeps each plugin's Claude and optional Codex manifest versions, the marketplace manifest's
per-plugin entry + top-level version, and the CHANGELOG in sync. Plugins are auto-discovered (any
top-level dir with `.claude-plugin/plugin.json`), so new plugins need zero config.

Modes:
  --plugin NAME --level {major,minor,patch}   explicit single bump
  --auto                                       detect plugins changed since the last release,
                                               infer each level from conventional-commit subjects,
                                               apply (dry-run unless --yes)
  --check                                      validation only; non-zero exit if a changed plugin's
                                               version or the marketplace top-level wasn't bumped

Conventions: feat! / "BREAKING CHANGE" -> major; feat -> minor; everything else -> patch.
The marketplace top-level bump = the max level across changed plugins.

Never pushes. Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

LEVELS = {None: 0, "patch": 1, "minor": 2, "major": 3}
ORDER = {1: "patch", 2: "minor", 3: "major"}
REPOSITORY_CONTRACTS = (
    ("CodeGraph + impact-map contract", "tests/rhize-devflow/test_impact_map_contract.py"),
    ("Dev Flow test suite", "tests/rhize-devflow", "-q"),
    ("skill-map freshness", "scripts/validate_skill_map.py", "--check-stale"),
    ("Setup-artifacts freshness", "rhize-ops/scripts/setup_artifacts.py", "--check"),
    # Default (non-strict) mode deliberately: this contract exits non-zero only on
    # ERROR-severity findings (path-like unquoted ${VAR}, secret-shaped stdio env
    # values). A false positive in a release gate blocks every bump including
    # emergencies, and the usual human response is to delete the contract entirely —
    # so warnings (e.g. USERNAME-shaped keys, trailing-slash *_URL values) surface in
    # the gate's output without blocking it. See scripts/validate_plugin_configs.py.
    ("Plugin config lint", "scripts/validate_plugin_configs.py"),
)


def fail(msg: str) -> "None":
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def repo_root() -> Path:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return Path(r.stdout.strip())
    return Path(__file__).resolve().parent.parent


REPO = repo_root()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def discover_plugins() -> dict:
    """name -> plugin dir, for every top-level dir with .claude-plugin/plugin.json."""
    out = {}
    for mf in sorted(REPO.glob("*/.claude-plugin/plugin.json")):
        out[mf.parent.parent.name] = mf.parent.parent
    return out


def plugin_manifest(plug_dir: Path) -> Path:
    return plug_dir / ".claude-plugin" / "plugin.json"


def read_version(manifest: Path) -> str:
    return json.loads(manifest.read_text(encoding="utf-8"))["version"]


def bump_semver(ver: str, level: str) -> str:
    parts = ver.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        fail(f"non-semver version {ver!r}")
    major, minor, patch = (int(p) for p in parts)
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def last_release_ref(since: str | None) -> str:
    if since:
        return since
    # Key the release base on the last commit that CHANGED a version line in the
    # marketplace manifest, not merely touched the file — a commit that edits only
    # descriptions (or other non-version fields) must not be mistaken for a release.
    ref = git("log", "-1", "--format=%H", "-G\"version\"", "--", ".claude-plugin/marketplace.json")
    return ref or git("rev-list", "--max-parents=0", "HEAD")


def changed_dirs(base: str, plugins: dict) -> set:
    files = [f for f in git("diff", "--name-only", f"{base}..HEAD").splitlines() if f]
    dirty = set()
    for f in files:
        top = f.split("/", 1)[0]
        if top in plugins:
            dirty.add(top)
    return dirty


def level_of_commit(subject: str) -> str:
    s = subject.strip()
    if re.match(r"^\w+(\([^)]*\))?!:", s) or "BREAKING CHANGE" in s:
        return "major"
    m = re.match(r"^(\w+)(\([^)]*\))?:", s)
    return "minor" if (m and m.group(1).lower() == "feat") else "patch"


def infer_level(base: str, plug_name: str) -> str:
    subs = git("log", "--format=%s", f"{base}..HEAD", "--", plug_name).splitlines()
    best = None
    for s in subs:
        lvl = level_of_commit(s)
        if LEVELS[lvl] > LEVELS[best]:
            best = lvl
    return best or "patch"


def run_repository_contract_checks() -> list[str]:
    """Run repository contracts even when the current commit is itself the release base.

    A contract entry naming a `.py` file is run directly as a script (its own
    `if __name__ == "__main__":` guard is the pytest-independent entry point,
    e.g. test_impact_map_contract.py, validate_skill_map.py). A contract entry
    naming anything else (a directory, e.g. "tests/rhize-devflow") is run via
    `python3 -m pytest <target> <arguments>` instead, so a whole test suite's
    actual test functions execute and fail the gate on any regression — a
    plain `python3 <dir>` would not run pytest's test_* functions at all.
    """
    errors = []
    for label, relative_path, *arguments in REPOSITORY_CONTRACTS:
        target = REPO / relative_path
        if target.suffix == ".py":
            command = [sys.executable, str(target), *arguments]
        else:
            command = [sys.executable, "-m", "pytest", str(target), *arguments]
        result = subprocess.run(
            command,
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            errors.append(f"{label} failed")
    return errors


# ---------- writers ----------

def update_plugin_manifests(plugin: str, version: str) -> None:
    """Update host manifests and any runtime metadata shipped by a plugin together."""
    paths = [REPO / plugin / ".claude-plugin" / "plugin.json"]
    codex = REPO / plugin / ".codex-plugin" / "plugin.json"
    if codex.exists():
        paths.append(codex)
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        document["version"] = version
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    package = REPO / plugin / "package.json"
    if package.exists():
        document = json.loads(package.read_text(encoding="utf-8"))
        document["version"] = version
        package.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    runtime = REPO / plugin / "service" / "src" / "api" / "context.mjs"
    if runtime.exists():
        text = runtime.read_text(encoding="utf-8")
        updated, count = re.subn(r"^const VERSION = '[^']+';$", f"const VERSION = '{version}';", text, count=1, flags=re.MULTILINE)
        if count == 1:
            runtime.write_text(updated, encoding="utf-8")
        elif re.search(r"^const VERSION = JSON\.parse\(.*package\.json.*\)\.version;$", text, flags=re.MULTILINE):
            pass  # runtime derives its version from package.json; nothing to patch
        else:
            fail(f"could not update runtime version in {runtime.relative_to(REPO)}")

    info_plist = REPO / plugin / "native" / "reminders-helper" / "Resources" / "Info.plist"
    if info_plist.exists():
        text = info_plist.read_text(encoding="utf-8")
        pattern = r"(<key>CFBundleShortVersionString</key>\s*<string>)[^<]+(</string>)"
        updated, count = re.subn(pattern, rf"\g<1>{version}\g<2>", text, count=1)
        if count != 1:
            fail(f"could not update helper version in {info_plist.relative_to(REPO)}")
        info_plist.write_text(updated, encoding="utf-8")


def apply_bumps(plug_new: dict, mkt_new: str) -> None:
    """Apply one release's plugin-manifest and marketplace version updates."""
    for plugin, version in plug_new.items():
        update_plugin_manifests(plugin, version)
    update_marketplace(plug_new, mkt_new)


def update_marketplace(plug_new: dict, mkt_new: str) -> None:
    mf = REPO / ".claude-plugin" / "marketplace.json"
    d = json.loads(mf.read_text(encoding="utf-8"))
    d["version"] = mkt_new
    for pl in d.get("plugins", []):
        if pl.get("name") in plug_new:
            pl["version"] = plug_new[pl["name"]]
    mf.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def changelog_insert(bullets: list) -> None:
    cl = REPO / "CHANGELOG.md"
    if not cl.exists():
        return
    t = cl.read_text(encoding="utf-8")
    block = "".join(f"- {b}\n" for b in bullets)
    updated = _insert_under_unreleased_added(t, block)
    if updated is None:
        print("WARN: no [Unreleased] section in CHANGELOG; skipped", file=sys.stderr)
        return
    cl.write_text(updated, encoding="utf-8")


_UNRELEASED_ADDED = re.compile(r"## \[Unreleased\]\n+### Added\n*")


def _insert_under_unreleased_added(text: str, block: str) -> "str | None":
    """Insert `block` directly under `## [Unreleased]` / `### Added`, reusing an existing
    `### Added` heading whatever whitespace follows it (a freshly scaffolded plugin changelog
    ends `### Added\n`, not `### Added\n\n`), and creating the heading only when the
    section has none. Returns None when there is no `## [Unreleased]` section at all."""
    match = _UNRELEASED_ADDED.search(text)
    if match:
        head = text[:match.end()].rstrip("\n") + "\n\n"
        return head + block + text[match.end():]
    if "## [Unreleased]" in text:
        return text.replace("## [Unreleased]\n", "## [Unreleased]\n\n### Added\n\n" + block, 1)
    return None


def plugin_changelog_insert(plugin: str, bullet: str) -> None:
    """Insert one bump bullet into a plugin's own CHANGELOG.md, under
    ## [Unreleased] / ### Added — creating the ### Added marker if the file
    has ## [Unreleased] without one. Skips with a stderr WARN if the plugin
    has no CHANGELOG.md."""
    cl = REPO / plugin / "CHANGELOG.md"
    if not cl.exists():
        print(f"WARN: {plugin} has no CHANGELOG.md; skipped", file=sys.stderr)
        return
    t = cl.read_text(encoding="utf-8")
    updated = _insert_under_unreleased_added(t, f"- {bullet}\n")
    if updated is None:
        print(f"WARN: no [Unreleased] section in {plugin}/CHANGELOG.md; skipped", file=sys.stderr)
        return
    cl.write_text(updated, encoding="utf-8")


# ---------- modes ----------

def plan_rows(plugins: dict, levels: dict) -> list:
    rows = []
    for name, lvl in levels.items():
        old = read_version(plugin_manifest(plugins[name]))
        rows.append((name, old, bump_semver(old, lvl), lvl))
    return rows


def apply(plugins: dict, levels: dict) -> None:
    rows = plan_rows(plugins, levels)
    plug_new = {name: new for name, _old, new, _lvl in rows}
    mkt_mf = REPO / ".claude-plugin" / "marketplace.json"
    mkt_old = json.loads(mkt_mf.read_text(encoding="utf-8"))["version"]
    mkt_level = ORDER[max(LEVELS[l] for l in levels.values())]
    mkt_new = bump_semver(mkt_old, mkt_level)
    apply_bumps(plug_new, mkt_new)
    today = dt.date.today().isoformat()
    bullets = [f"**{n}** {o} → {nv} ({l})" for n, o, nv, l in rows]
    changelog_insert([f"_{today}_ version bump — " + "; ".join(bullets)
                      + f"; marketplace {mkt_old} → {mkt_new}."])
    for n, o, nv, l in rows:
        plugin_changelog_insert(
            n,
            f"_{today}_ version bump — {o} → {nv} ({l}); marketplace {mkt_old} → {mkt_new}.",
        )
    print(f"✓ applied. marketplace {mkt_old} → {mkt_new}")
    for n, o, nv, l in rows:
        print(f"    {n}: {o} → {nv} ({l})")
    print("\nNext: review `git diff`, then commit. (This tool never pushes.)")


def cmd_auto(args, plugins: dict) -> int:
    base = last_release_ref(args.since)
    dirty = changed_dirs(base, plugins)
    if not dirty:
        print(f"No plugin changes since last release ({base[:9]}). Nothing to bump.")
        return 0
    levels = {name: (args.level or infer_level(base, name)) for name in sorted(dirty)}
    rows = plan_rows(plugins, levels)
    mkt_level = ORDER[max(LEVELS[l] for l in levels.values())]
    print(f"Plan (changed since {base[:9]}):")
    for n, o, nv, l in rows:
        print(f"  {n}: {o} → {nv}   [{l}]")
    print(f"  marketplace: → {mkt_level} bump")
    if not args.yes:
        print("\n(dry-run) pass --yes to apply.")
        return 0
    apply(plugins, levels)
    return 0


def cmd_plugin(args, plugins: dict) -> int:
    if args.plugin not in plugins:
        fail(f"unknown plugin {args.plugin!r}; known: {', '.join(sorted(plugins))}")
    apply(plugins, {args.plugin: args.level})
    return 0


def cmd_check(args, plugins: dict) -> int:
    base = last_release_ref(args.since)
    dirty = changed_dirs(base, plugins)
    errors = run_repository_contract_checks()
    if not dirty:
        if errors:
            print("✗ check failed — repository contract errors:", file=sys.stderr)
            for error in errors:
                print(f"    - {error}", file=sys.stderr)
            return 1
        print("✓ check: no plugin changes since last release.")
        return 0
    for name in sorted(dirty):
        cur = read_version(plugin_manifest(plugins[name]))
        based = git("show", f"{base}:{name}/.claude-plugin/plugin.json")
        if based:
            old = json.loads(based).get("version")
            if old == cur:
                errors.append(f"{name}: changed but version still {cur} (not bumped)")
    mkt_cur = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())["version"]
    mkt_based = git("show", f"{base}:.claude-plugin/marketplace.json")
    if mkt_based and json.loads(mkt_based).get("version") == mkt_cur:
        errors.append(f"marketplace top-level still {mkt_cur} (not bumped)")
    if not git("diff", "--name-only", f"{base}..HEAD", "--", "CHANGELOG.md"):
        print("  note: CHANGELOG.md not updated since last release.", file=sys.stderr)
    if errors:
        print("✗ check failed — validation errors:", file=sys.stderr)
        for e in errors:
            print(f"    - {e}", file=sys.stderr)
        print("  run: python3 scripts/bump_version.py --auto --yes", file=sys.stderr)
        return 1
    print(f"✓ check: {len(dirty)} changed plugin(s) all version-bumped.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Coordinated semver bumps for the rhize-plugins marketplace.")
    ap.add_argument("--plugin", help="explicit: plugin name to bump (with --level)")
    ap.add_argument("--level", choices=["major", "minor", "patch"], help="explicit bump level / override --auto inference")
    ap.add_argument("--auto", action="store_true", help="detect changed plugins since last release and infer levels")
    ap.add_argument("--check", action="store_true", help="validation only; non-zero exit if a changed plugin wasn't bumped")
    ap.add_argument("--since", help="base ref for change detection (default: last commit touching marketplace.json)")
    ap.add_argument("--yes", action="store_true", help="apply changes in --auto (otherwise dry-run)")
    args = ap.parse_args()

    plugins = discover_plugins()
    if not plugins:
        fail("no plugins found (no */.claude-plugin/plugin.json)")

    if args.check:
        sys.exit(cmd_check(args, plugins))
    if args.plugin:
        if not args.level:
            fail("--plugin requires --level")
        sys.exit(cmd_plugin(args, plugins))
    if args.auto:
        sys.exit(cmd_auto(args, plugins))
    ap.error("choose a mode: --auto, --plugin NAME --level L, or --check")


if __name__ == "__main__":
    main()
