"""Tests for paths.py — the single path resolver that makes skill-monitor
installable (no hardcoded ~/dev-local, iCloud/vault, or SCRIPT_DIR/data
literals in the other scripts).

Run: python3 -m pytest tests/test_paths.py -q   (from the skill-monitor dir)

Covers: home()/data_dir() across the three resolution branches (env set,
env unset + existing checkout data/, env unset + fresh install), the
snapshots/scorecards/cdn-cache subdirs, vault_root()/resolve_vault_paths()
across zero/one/multiple vaults and the OBSIDIAN_VAULT_PATH override,
vault_report_dir()'s None-propagation, and repo_roots()/repo_root() parsing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import paths  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    """Every test starts with a clean slate: none of skill-monitor's env
    vars set, and the checkout-data notice reset so its once-per-process
    flag doesn't leak between tests."""
    monkeypatch.delenv("RHIZE_SKILL_MONITOR_HOME", raising=False)
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    monkeypatch.delenv("RHIZE_REPO_ROOTS", raising=False)
    monkeypatch.setattr(paths, "_checkout_notice_printed", False)


# ---------------------------------------------------------------------------
# home() / data_dir()
# ---------------------------------------------------------------------------

def test_home_env_set(tmp_path, monkeypatch):
    custom = tmp_path / "custom-home"
    monkeypatch.setenv("RHIZE_SKILL_MONITOR_HOME", str(custom))
    assert paths.home() == custom


def test_home_env_unset_default(tmp_path, monkeypatch):
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(paths.Path, "home", staticmethod(lambda: fake_home))
    assert paths.home() == fake_home / ".rhize" / "skill-monitor"


def test_data_dir_env_set(tmp_path, monkeypatch):
    custom = tmp_path / "custom-home"
    monkeypatch.setenv("RHIZE_SKILL_MONITOR_HOME", str(custom))
    d = paths.data_dir()
    assert d == custom / "data"
    assert d.is_dir()


def test_data_dir_env_unset_with_checkout_data_uses_it(tmp_path, monkeypatch, capsys):
    """RHIZE_SKILL_MONITOR_HOME unset + a data/ dir already exists next to
    the scripts (an existing dev checkout) -> that data/ keeps being used,
    with a one-line stderr notice."""
    fake_script_dir = tmp_path / "skill-monitor"
    (fake_script_dir / "data").mkdir(parents=True)
    monkeypatch.setattr(paths, "SCRIPT_DIR", fake_script_dir)

    d = paths.data_dir()

    assert d == fake_script_dir / "data"
    err = capsys.readouterr().err
    assert "RHIZE_SKILL_MONITOR_HOME is not set" in err
    assert str(fake_script_dir / "data") in err


def test_data_dir_env_unset_with_checkout_data_notice_prints_once(tmp_path, monkeypatch, capsys):
    fake_script_dir = tmp_path / "skill-monitor"
    (fake_script_dir / "data").mkdir(parents=True)
    monkeypatch.setattr(paths, "SCRIPT_DIR", fake_script_dir)

    paths.data_dir()
    capsys.readouterr()  # drain the first notice
    paths.data_dir()
    err = capsys.readouterr().err
    assert err == "", "the checkout-data notice must print at most once per process"


def test_data_dir_env_unset_without_data_fresh_install(tmp_path, monkeypatch):
    """RHIZE_SKILL_MONITOR_HOME unset + no data/ dir next to the scripts (a
    fresh install, e.g. a read-only plugin cache) -> ~/.rhize/skill-monitor/data,
    never the (nonexistent) checkout-local data/."""
    fake_script_dir = tmp_path / "skill-monitor"
    fake_script_dir.mkdir(parents=True)
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(paths, "SCRIPT_DIR", fake_script_dir)
    monkeypatch.setattr(paths.Path, "home", staticmethod(lambda: fake_home))

    d = paths.data_dir()

    assert d == fake_home / ".rhize" / "skill-monitor" / "data"
    assert d.is_dir()
    assert not (fake_script_dir / "data").exists()


def test_data_dir_fresh_install_created_with_0700(tmp_path, monkeypatch):
    fake_script_dir = tmp_path / "skill-monitor"
    fake_script_dir.mkdir(parents=True)
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(paths, "SCRIPT_DIR", fake_script_dir)
    monkeypatch.setattr(paths.Path, "home", staticmethod(lambda: fake_home))

    d = paths.data_dir()

    assert (d.stat().st_mode & 0o777) == 0o700
    assert (paths.home().stat().st_mode & 0o777) == 0o700


def test_snapshots_scorecards_cdn_cache_subdirs(tmp_path, monkeypatch):
    monkeypatch.setenv("RHIZE_SKILL_MONITOR_HOME", str(tmp_path / "home"))
    assert paths.snapshots_dir() == paths.data_dir() / "snapshots"
    assert paths.scorecards_dir() == paths.data_dir() / "scorecards"
    assert paths.cdn_cache_dir() == paths.data_dir() / "cdn-cache"
    assert paths.snapshots_dir().is_dir()
    assert paths.scorecards_dir().is_dir()
    assert paths.cdn_cache_dir().is_dir()


# ---------------------------------------------------------------------------
# resolve_vault_paths() / vault_root()
# ---------------------------------------------------------------------------

def test_resolve_vault_paths_delegates_to_obsidian_second_brain(monkeypatch):
    """When the shared resolver is available, resolve_vault_paths() returns
    exactly what it reports — this repo checkout does ship it, so the real
    module is exercised here (its own behavior is unit-tested in
    obsidian-second-brain/tests/test_vault_resolve.py)."""
    module = paths._load_vault_resolve()
    assert module is not None, "expected to find obsidian-second-brain's vault_resolve.py in this checkout"


def test_resolve_vault_paths_falls_back_to_env_when_module_unavailable(monkeypatch):
    monkeypatch.setattr(paths, "_load_vault_resolve", lambda: None)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", "/a/vault:/b/vault")
    assert paths.resolve_vault_paths() == ["/a/vault", "/b/vault"]


def test_resolve_vault_paths_empty_when_module_unavailable_and_no_env(monkeypatch):
    monkeypatch.setattr(paths, "_load_vault_resolve", lambda: None)
    assert paths.resolve_vault_paths() == []


def test_vault_root_zero_vaults_is_none(monkeypatch):
    monkeypatch.setattr(paths, "resolve_vault_paths", lambda: [])
    assert paths.vault_root() is None


def test_vault_root_one_vault(tmp_path, monkeypatch):
    vault = tmp_path / "MyVault"
    monkeypatch.setattr(paths, "resolve_vault_paths", lambda: [str(vault)])
    assert paths.vault_root() == vault


def test_vault_root_multiple_vaults_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(
        paths, "resolve_vault_paths", lambda: [str(tmp_path / "A"), str(tmp_path / "B")]
    )
    assert paths.vault_root() is None


def test_vault_root_env_var_first_entry_wins_even_with_multiple_vaults(tmp_path, monkeypatch):
    """OBSIDIAN_VAULT_PATH's first entry wins outright -- it doesn't need
    resolve_vault_paths() to resolve to exactly one vault."""
    env_vault = tmp_path / "EnvVault"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", f"{env_vault}:{tmp_path / 'Other'}")
    monkeypatch.setattr(
        paths, "resolve_vault_paths", lambda: [str(tmp_path / "A"), str(tmp_path / "B")]
    )
    assert paths.vault_root() == env_vault


def test_vault_report_dir_none_when_no_vault(monkeypatch):
    monkeypatch.setattr(paths, "vault_root", lambda: None)
    assert paths.vault_report_dir("weekly-reports") is None
    assert paths.vault_report_dir("cost-reports") is None
    assert paths.vault_report_dir("dashboard") is None


def test_vault_report_dir_kinds(tmp_path, monkeypatch):
    vault = tmp_path / "Vault"
    monkeypatch.setattr(paths, "vault_root", lambda: vault)
    base = (
        vault
        / "Projects"
        / "Rhize Media"
        / "Rhize Tools"
        / "Scheduled Agent Routines & Automations"
        / "Skill-Audit-and-Monitoring"
    )
    assert paths.vault_report_dir("weekly-reports") == base / "weekly-reports"
    assert paths.vault_report_dir("cost-reports") == base / "cost-reports"
    assert paths.vault_report_dir("dashboard") == base


def test_vault_report_dir_unknown_kind_raises(monkeypatch):
    monkeypatch.setattr(paths, "vault_root", lambda: Path("/somewhere"))
    with pytest.raises(ValueError):
        paths.vault_report_dir("not-a-real-kind")


# ---------------------------------------------------------------------------
# repo_roots() / repo_root()
# ---------------------------------------------------------------------------

def test_repo_roots_empty_when_unset():
    assert paths.repo_roots() == []


def test_repo_roots_parses_colon_separated(monkeypatch):
    monkeypatch.setenv("RHIZE_REPO_ROOTS", "/a/repo-one:/b/repo-two")
    assert paths.repo_roots() == [Path("/a/repo-one"), Path("/b/repo-two")]


def test_repo_roots_expands_user(monkeypatch):
    monkeypatch.setenv("RHIZE_REPO_ROOTS", "~/repo-one")
    assert paths.repo_roots() == [Path.home() / "repo-one"]


def test_repo_root_finds_by_basename(monkeypatch):
    monkeypatch.setenv("RHIZE_REPO_ROOTS", "/a/rhize-plugins:/b/skill-forge")
    assert paths.repo_root("skill-forge") == Path("/b/skill-forge")
    assert paths.repo_root("rhize-plugins") == Path("/a/rhize-plugins")


def test_repo_root_not_found_returns_none(monkeypatch):
    monkeypatch.setenv("RHIZE_REPO_ROOTS", "/a/rhize-plugins")
    assert paths.repo_root("does-not-exist") is None


def test_repo_root_empty_roots_returns_none():
    assert paths.repo_root("anything") is None
