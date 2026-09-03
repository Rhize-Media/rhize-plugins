"""test_skill_monitor_data_dir.py — precedence tests for skill_monitor_data_dir(),
duplicated (deliberately, per this repo's cross-plugin sharing rule — a plugin may
only reach another plugin's files by a discovered path with a documented degraded
mode) in both:

  - rhize-context-manager/scripts/build_local_skill_map.py
  - rhize-context-manager/scripts/suggestion_log_report.py

Both must mirror the standalone rhize-skill-monitor tool's own paths.py precedence
for its data directory:
  1. RHIZE_SKILL_MONITOR_HOME set -> <home>/data
  2. else RHIZE_SKILL_MONITOR_ROOT, or the default checkout
     (~/dev-local/RHIZE/rhize-skill-monitor); if its data/ is a directory -> that
  3. else ~/.rhize/skill-monitor/data

Also covers the documented degraded mode in suggestion_log_report.py: a missing
skill-usage.json must still resolve to "no usage data" (an empty mapping), never
an error.

Imports both scripts by file path, matching the importlib.util.spec_from_file_location
pattern used by tests/rhize-context-manager/test_skill_evals.py.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_LOCAL_SKILL_MAP = (
    REPO_ROOT / "rhize-context-manager" / "scripts" / "build_local_skill_map.py"
)
SUGGESTION_LOG_REPORT = (
    REPO_ROOT / "rhize-context-manager" / "scripts" / "suggestion_log_report.py"
)

ENV_KEYS = ("RHIZE_SKILL_MONITOR_HOME", "RHIZE_SKILL_MONITOR_ROOT")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def temp_env(**overrides: str):
    """Set the given env vars for the duration of the block, restoring exactly
    what was there before (including absence) on exit. Always clears the two
    RHIZE_SKILL_MONITOR_* vars first, unless the caller re-supplies them, so a
    test never inherits the developer's own shell setup."""
    keys = set(overrides) | set(ENV_KEYS)
    saved = {key: os.environ.get(key) for key in keys}
    try:
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class SkillMonitorDataDirPrecedenceMixin:
    """Shared precedence assertions, parameterized over which script's copy of
    skill_monitor_data_dir() is under test."""

    module_path: Path
    module_name: str

    def _resolver(self):
        module = _load_module(self.module_path, self.module_name)
        return module.skill_monitor_data_dir

    def test_home_override_wins_over_everything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitor_home = Path(tmp) / "custom-home"
            with temp_env(RHIZE_SKILL_MONITOR_HOME=str(monitor_home)):
                resolver = self._resolver()
                self.assertEqual(resolver(), monitor_home / "data")

    def test_root_override_used_when_its_data_dir_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom-checkout"
            (root / "data").mkdir(parents=True)
            with temp_env(RHIZE_SKILL_MONITOR_ROOT=str(root)):
                resolver = self._resolver()
                self.assertEqual(resolver(), root / "data")

    def test_default_checkout_data_dir_used_when_no_env_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            default_root = home / "dev-local" / "RHIZE" / "rhize-skill-monitor"
            (default_root / "data").mkdir(parents=True)
            with temp_env(HOME=str(home)):
                resolver = self._resolver()
                self.assertEqual(resolver(), default_root / "data")

    def test_falls_back_to_dot_rhize_when_nothing_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with temp_env(HOME=str(home)):
                resolver = self._resolver()
                self.assertEqual(
                    resolver(), home / ".rhize" / "skill-monitor" / "data"
                )

    def test_root_override_without_data_dir_falls_back_to_dot_rhize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom-checkout-missing-data"
            root.mkdir()
            home = Path(tmp) / "home"
            home.mkdir()
            with temp_env(RHIZE_SKILL_MONITOR_ROOT=str(root), HOME=str(home)):
                resolver = self._resolver()
                self.assertEqual(
                    resolver(), home / ".rhize" / "skill-monitor" / "data"
                )


class BuildLocalSkillMapResolverTests(
    SkillMonitorDataDirPrecedenceMixin, unittest.TestCase
):
    module_path = BUILD_LOCAL_SKILL_MAP
    module_name = "test_skill_monitor_data_dir__build_local_skill_map"


class SuggestionLogReportResolverTests(
    SkillMonitorDataDirPrecedenceMixin, unittest.TestCase
):
    module_path = SUGGESTION_LOG_REPORT
    module_name = "test_skill_monitor_data_dir__suggestion_log_report"


class SuggestionLogReportDegradedModeTests(unittest.TestCase):
    def test_missing_usage_file_degrades_to_empty_session_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with temp_env(HOME=str(home)):
                module = _load_module(
                    SUGGESTION_LOG_REPORT,
                    "test_skill_monitor_data_dir__degraded_mode",
                )
                usage_path = module._default_usage_path()
                self.assertFalse(usage_path.exists())
                self.assertEqual(module.load_session_skills(usage_path), {})


if __name__ == "__main__":
    unittest.main()
