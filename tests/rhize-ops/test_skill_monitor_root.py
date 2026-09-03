"""Tests for rhize-ops/scripts/skill_monitor_root.sh — the resolver skills use
to find the standalone rhize-skill-monitor tool now that it no longer ships
bundled at rhize-ops/skill-monitor/ (extracted to Rhize-Media/rhize-skill-monitor,
repo shape R-C).

Runs the script as a subprocess (it is POSIX sh, not Python) and checks the
three resolution outcomes: env override, default path, and the exit-78
fix-it message when neither resolves to a real checkout.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-ops" / "scripts" / "skill_monitor_root.sh"


def run_script(env: dict) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.pop("RHIZE_SKILL_MONITOR_ROOT", None)
    full_env.update(env)
    return subprocess.run(
        ["sh", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=full_env,
    )


class SkillMonitorRootScriptExistsTests(unittest.TestCase):
    def test_script_is_executable(self) -> None:
        self.assertTrue(SCRIPT.is_file(), f"{SCRIPT} does not exist")
        self.assertTrue(os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable")

    def test_script_has_a_posix_sh_shebang(self) -> None:
        first_line = SCRIPT.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, "#!/bin/sh")


class SkillMonitorRootResolutionTests(unittest.TestCase):
    def test_env_override_wins_when_it_contains_monitor_py(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom-checkout"
            root.mkdir()
            (root / "monitor.py").write_text("# stub\n", encoding="utf-8")

            result = run_script({"RHIZE_SKILL_MONITOR_ROOT": str(root)})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(root))

    def test_default_path_used_when_env_var_is_unset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            default_root = home / "dev-local" / "RHIZE" / "rhize-skill-monitor"
            default_root.mkdir(parents=True)
            (default_root / "monitor.py").write_text("# stub\n", encoding="utf-8")

            result = run_script({"HOME": str(home)})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(default_root))

    def test_missing_tool_exits_78_with_clone_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # HOME has no dev-local/RHIZE/rhize-skill-monitor/monitor.py at all.
            home = Path(tmp)

            result = run_script({"HOME": str(home)})

            self.assertEqual(result.returncode, 78)
            self.assertEqual(result.stdout, "")
            self.assertIn(
                "git clone https://github.com/Rhize-Media/rhize-skill-monitor.git",
                result.stderr,
            )
            self.assertIn("RHIZE_SKILL_MONITOR_ROOT", result.stderr)

    def test_env_override_pointing_at_a_missing_checkout_also_exits_78(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "does-not-have-monitor-py"
            root.mkdir()

            result = run_script({"RHIZE_SKILL_MONITOR_ROOT": str(root)})

            self.assertEqual(result.returncode, 78)
            self.assertIn(str(root), result.stderr)


if __name__ == "__main__":
    unittest.main()
