"""Native plugin-hook package, cache-root transition, and failure-containment tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "rhize-context-manager"
HOOKS_FILE = PLUGIN_ROOT / "hooks" / "hooks.json"
ROOT_TOKEN = "${CLAUDE_PLUGIN_ROOT}"
ENTRYPOINT_PATTERN = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"]+)")


def commands_by_event() -> dict[str, str]:
    hooks = json.loads(HOOKS_FILE.read_text())["hooks"]
    result = {}
    for event in ("UserPromptSubmit", "SessionStart", "PostToolUse", "Stop"):
        matches = [
            hook["command"]
            for group in hooks[event]
            for hook in group["hooks"]
            if "memory-opportunity" in hook["command"]
        ]
        if len(matches) != 1:
            raise AssertionError(f"expected one paired-measurement {event} command, got {matches}")
        result[event] = matches[0]
    return result


class NativeHookPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.events = commands_by_event()
        self.environment = os.environ.copy()
        self.environment.update(
            HOME=str(self.root / "home"),
            XDG_DATA_HOME=str(self.root / "data"),
            RHIZE_CONTEXT_HOME=str(self.root / "context"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        self.environment.pop("RHIZE_MEMORY_EVAL_CHILD", None)
        (self.root / "home").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_versioned_package(self, name: str) -> Path:
        destination = self.root / "codex" / "rhize-plugins" / "rhize-context-manager" / name
        destination.mkdir(parents=True)
        shutil.copytree(PLUGIN_ROOT / "hooks", destination / "hooks")
        (destination / "scripts").mkdir()
        shutil.copytree(
            PLUGIN_ROOT / "scripts" / "memory_context",
            destination / "scripts" / "memory_context",
        )
        return destination

    def run_hook(self, command: str, root: Path, event: dict) -> subprocess.CompletedProcess:
        env = dict(self.environment)
        env["CLAUDE_PLUGIN_ROOT"] = str(root)
        env["PLUGIN_ROOT"] = str(root)
        return subprocess.run(
            command,
            shell=True,
            executable="/bin/sh",
            input=json.dumps(event),
            text=True,
            capture_output=True,
            cwd=self.root,
            env=env,
            timeout=10,
            check=False,
        )

    def event_for(self, event_name: str, *, stop_hook_active: bool = False) -> dict:
        event = {
            "hook_event_name": event_name,
            "session_id": "isolated-hook-smoke",
            "cwd": str(self.root),
            "turn_id": "isolated-hook-turn",
        }
        if event_name == "UserPromptSubmit":
            event["prompt"] = "Please recall the prior decision."
        elif event_name == "PostToolUse":
            event.update(tool_name="Bash", tool_use_id="fixture-tool", tool_response={"is_error": False})
        elif event_name == "Stop":
            event.update(
                stop_hook_active=stop_hook_active,
                last_assistant_message="Task complete.",
            )
        return event

    def test_every_configured_hook_entrypoint_is_packaged(self) -> None:
        config = json.loads(HOOKS_FILE.read_text())
        for event, groups in config["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    command = hook["command"]
                    match = ENTRYPOINT_PATTERN.search(command)
                    self.assertIsNotNone(match, f"{event} command is not plugin-root-relative: {command}")
                    entrypoint = PLUGIN_ROOT / match.group(1)
                    self.assertTrue(entrypoint.is_file(), f"{event} package misses {entrypoint}")

    def test_previous_and_current_versioned_roots_resolve_hooks(self) -> None:
        # Codex keeps marketplace installs under versioned cache roots. The host chooses
        # PLUGIN_ROOT for each loaded install; commands must remain independent of a
        # literal version/path so both old and new roots work during a transition.
        old_root = self.make_versioned_package("previous")
        new_root = self.make_versioned_package("current")
        for root in (old_root, new_root):
            for event_name, command in self.events.items():
                result = self.run_hook(command, root, self.event_for(event_name))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
        for command in self.events.values():
            self.assertIn(ROOT_TOKEN, command)
            self.assertNotRegex(command, r"/plugins/cache/.+?/\d+\.\d+\.\d+/")

    def test_missing_tool_and_stop_entrypoints_fail_silently_on_repeated_events(self) -> None:
        old_root = self.make_versioned_package("previous")
        new_root = self.make_versioned_package("current")
        (old_root / "hooks" / "memory-opportunity-tool.py").unlink()
        (old_root / "hooks" / "memory-opportunity-stop.py").unlink()

        for event_name in ("PostToolUse", "Stop"):
            event = self.event_for(event_name, stop_hook_active=True)
            for _ in range(8):
                result = self.run_hook(self.events[event_name], old_root, event)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

            # A cache transition to a complete version restores ordinary capture.
            result = self.run_hook(
                self.events[event_name], new_root, self.event_for(event_name)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    def test_stop_runtime_failure_cannot_request_an_automatic_continuation(self) -> None:
        root = self.make_versioned_package("runtime-failure")
        entrypoint = root / "hooks" / "memory-opportunity-stop.py"
        entrypoint.write_text("import sys\nprint('fixture failure', file=sys.stderr)\nsys.exit(2)\n")

        for _ in range(8):
            result = self.run_hook(
                self.events["Stop"],
                root,
                self.event_for("Stop", stop_hook_active=True),
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
