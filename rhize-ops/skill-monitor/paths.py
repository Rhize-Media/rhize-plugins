#!/usr/bin/env python3
"""
paths.py — single path resolver for skill-monitor, so the tool is installable.

Before this module existed, every script here computed its own data/vault/
repo paths: `SCRIPT_DIR / "data"` for generated output, a hardcoded iCloud
Obsidian vault path for reports, and hardcoded `~/dev-local/RHIZE/*` literals
for the repos it scans (OpenWolf ledgers, config-sync, CLAUDE.md recurrence
checks). That works only on the author's own Mac with that exact directory
layout — a marketplace user who installs `rhize-ops` gets scripts that try to
write into the read-only plugin cache and point at a vault that doesn't
exist.

Every other script in this directory should resolve its paths through this
module instead of recomputing any of the above directly.

Environment variables:
  RHIZE_SKILL_MONITOR_HOME  Base directory for this tool's own data. Default:
                            ~/.rhize/skill-monitor -- UNLESS this env var is
                            unset AND a data/ directory already exists next
                            to these scripts (an existing dev checkout), in
                            which case that checkout-local data/ keeps being
                            used (a one-line notice prints to stderr the
                            first time per process).
  OBSIDIAN_VAULT_PATH       ":"-separated list of vault roots, shared with
                            the obsidian-second-brain plugin. First entry
                            wins for vault_root() here.
  RHIZE_REPO_ROOTS          ":"-separated list of repo directories this
                            machine's owner wants scanned/measured
                            (recurrence.py's CLAUDE.md check, OpenWolf
                            ledgers, git_sync.py's config-sync sweep).
                            Default: [] -- this tool no longer assumes
                            ~/dev-local/RHIZE/* exists on every machine.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

_checkout_notice_printed = False


# ---------------------------------------------------------------------------
# This tool's own data
# ---------------------------------------------------------------------------

def home() -> Path:
    """Base directory for this tool's own data (config + data/)."""
    env = os.environ.get("RHIZE_SKILL_MONITOR_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".rhize" / "skill-monitor"


def _using_checkout_data() -> bool:
    """True when RHIZE_SKILL_MONITOR_HOME is unset AND a data/ directory
    already exists next to these scripts -- an existing dev checkout that
    should keep working exactly as before, with no env var required."""
    return not os.environ.get("RHIZE_SKILL_MONITOR_HOME") and (SCRIPT_DIR / "data").is_dir()


def data_dir() -> Path:
    """Where this tool reads/writes its own generated data.

    RHIZE_SKILL_MONITOR_HOME set             -> <home>/data
    RHIZE_SKILL_MONITOR_HOME unset + existing
      checkout-local data/ next to scripts   -> that data/ (unchanged path,
                                                 one-line stderr notice)
    RHIZE_SKILL_MONITOR_HOME unset, no
      existing data/ (fresh install)         -> ~/.rhize/skill-monitor/data
    """
    global _checkout_notice_printed
    if _using_checkout_data():
        if not _checkout_notice_printed:
            print(
                "[skill-monitor] RHIZE_SKILL_MONITOR_HOME is not set; using the "
                f"existing checkout-local data/ next to these scripts "
                f"({SCRIPT_DIR / 'data'}). Set RHIZE_SKILL_MONITOR_HOME to move it.",
                file=sys.stderr,
            )
            _checkout_notice_printed = True
        d = SCRIPT_DIR / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    h = home()
    h.mkdir(parents=True, exist_ok=True, mode=0o700)
    d = h / "data"
    d.mkdir(exist_ok=True, mode=0o700)
    return d


def _data_subdir(name: str) -> Path:
    d = data_dir() / name
    d.mkdir(exist_ok=True, mode=0o700)
    return d


def snapshots_dir() -> Path:
    return _data_subdir("snapshots")


def scorecards_dir() -> Path:
    return _data_subdir("scorecards")


def cdn_cache_dir() -> Path:
    return _data_subdir("cdn-cache")


# ---------------------------------------------------------------------------
# Obsidian vault (shared resolution with obsidian-second-brain)
# ---------------------------------------------------------------------------

def _load_vault_resolve():
    """Dynamically import obsidian-second-brain's vault_resolve.py.

    Tries the sibling path in this repo checkout first, then the installed
    marketplace plugin cache. Returns None if it cannot be found or fails to
    import -- this tool must never require the Obsidian plugin to run."""
    candidates: list[Path] = [
        SCRIPT_DIR / ".." / ".." / "obsidian-second-brain" / "hooks" / "scripts" / "vault_resolve.py",
    ]
    marketplaces_root = Path.home() / ".claude" / "plugins" / "marketplaces"
    try:
        if marketplaces_root.is_dir():
            candidates.extend(
                sorted(
                    marketplaces_root.glob(
                        "*/obsidian-second-brain/hooks/scripts/vault_resolve.py"
                    )
                )
            )
    except OSError:
        pass

    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            spec = importlib.util.spec_from_file_location(
                "_skill_monitor_vault_resolve", candidate
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception:
            continue
    return None


def resolve_vault_paths() -> list[str]:
    """Every resolved Obsidian vault root, deduplicated, via
    obsidian-second-brain's own resolution order (env -> obsidian.json ->
    legacy iCloud default). Returns [] if that plugin cannot be found --
    falling back to just OBSIDIAN_VAULT_PATH's own entries, if set, so a
    user who set the env var without having obsidian-second-brain installed
    is still honored."""
    module = _load_vault_resolve()
    if module is not None:
        try:
            return module.resolve_vault_paths()
        except Exception:
            return []
    raw = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    return [p for p in raw.split(":") if p]


def vault_root() -> Path | None:
    """The single vault root to write skill-monitor reports into, or None.

    OBSIDIAN_VAULT_PATH's first entry wins if set (even with several
    entries); otherwise the single vault from resolve_vault_paths(). None
    when nothing is configured/found, or when more than one vault resolves
    with no env var to disambiguate -- callers must then skip the vault
    write with a clear message, not crash.
    """
    env = os.environ.get("OBSIDIAN_VAULT_PATH")
    if env:
        first = env.split(":")[0].strip()
        return Path(first).expanduser() if first else None
    vaults = resolve_vault_paths()
    if len(vaults) == 1:
        return Path(vaults[0]).expanduser()
    return None


_VAULT_REPORT_SUBPATHS: dict[str, tuple[str, ...]] = {
    # <vault>/Projects/Rhize Media/Rhize Tools/Scheduled Agent Routines &
    # Automations/Skill-Audit-and-Monitoring/<...> -- the folder every
    # skill-monitor report (weekly markdown, cost reports, the live
    # dashboard) has always lived under.
    "weekly-reports": ("weekly-reports",),
    "cost-reports": ("cost-reports",),
    "dashboard": (),
}


def vault_report_dir(kind: str) -> Path | None:
    """Vault directory for one of skill-monitor's own written report
    families. `kind` is one of "weekly-reports", "cost-reports", "dashboard".

    Returns None when no single vault could be resolved (see vault_root()).
    Callers must then skip the vault write with a clear message, not crash.
    """
    if kind not in _VAULT_REPORT_SUBPATHS:
        raise ValueError(f"unknown vault_report_dir kind: {kind!r}")
    root = vault_root()
    if root is None:
        return None
    base = (
        root
        / "Projects"
        / "Rhize Media"
        / "Rhize Tools"
        / "Scheduled Agent Routines & Automations"
        / "Skill-Audit-and-Monitoring"
    )
    for part in _VAULT_REPORT_SUBPATHS[kind]:
        base = base / part
    return base


# ---------------------------------------------------------------------------
# Repo roots (recurrence.py, OpenWolf ledgers, git_sync.py config-sync)
# ---------------------------------------------------------------------------

def repo_roots() -> list[Path]:
    """Repo directories this machine's owner wants scanned/measured.
    ':'-separated RHIZE_REPO_ROOTS env var; [] when unset."""
    raw = os.environ.get("RHIZE_REPO_ROOTS", "")
    return [Path(p).expanduser() for p in raw.split(":") if p]


def repo_root(name: str) -> Path | None:
    """Find one configured repo root by directory basename, or None."""
    for root in repo_roots():
        if root.name == name:
            return root
    return None
