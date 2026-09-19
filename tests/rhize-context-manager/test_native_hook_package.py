"""Native plugin-hook package, cache-root transition, and failure-containment tests."""
from __future__ import annotations

import json
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import sys
import time
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
            if "hook_runtime.py" in hook["command"]
        ]
        if len(matches) != 1:
            raise AssertionError(f"expected one paired-measurement {event} command, got {matches}")
        result[event] = matches[0]
    return result


class NativeHookPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
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
        lock = self.root / "context/memory-context/hook-health-v1/worker.lock"
        if lock.exists():
            with lock.open() as stream:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            self.fail("fixture worker did not finish")
                        time.sleep(.02)
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

    def health(self, root):
        result = subprocess.run([sys.executable, str(root / "scripts/memory_context/hook_runtime.py"), "status"],
                                env=self.environment, capture_output=True, text=True, timeout=5)
        return json.loads(result.stdout)

    def assert_warning(self, result):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(set(json.loads(result.stdout)), {"systemMessage"})

    def test_missing_tool_and_stop_entrypoints_warn_once_and_recover(self) -> None:
        old_root = self.make_versioned_package("previous")
        new_root = self.make_versioned_package("current")
        (old_root / "hooks" / "memory-opportunity-tool.py").unlink()
        (old_root / "hooks" / "memory-opportunity-stop.py").unlink()

        for event_name in ("PostToolUse", "Stop"):
            event = self.event_for(event_name, stop_hook_active=True)
            for attempt in range(8):
                result = self.run_hook(self.events[event_name], old_root, event)
                self.assertEqual(result.returncode, 0, result.stderr)
                if attempt == 0:
                    self.assert_warning(result)
                else:
                    self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

            # A cache transition to a complete version restores ordinary capture.
            result = self.run_hook(
                self.events[event_name], new_root, self.event_for(event_name)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(self.health(new_root)["status"], "operational")
            self.assertEqual(self.health(old_root)["status"], "degraded")
            shutil.copyfile(new_root / "hooks" / ("memory-opportunity-tool.py" if event_name == "PostToolUse" else "memory-opportunity-stop.py"),
                            old_root / "hooks" / ("memory-opportunity-tool.py" if event_name == "PostToolUse" else "memory-opportunity-stop.py"))

    def test_stop_runtime_failure_cannot_request_an_automatic_continuation(self) -> None:
        root = self.make_versioned_package("runtime-failure")
        entrypoint = root / "hooks" / "memory-opportunity-stop.py"
        entrypoint.write_text("import sys\nprint('fixture failure', file=sys.stderr)\nsys.exit(2)\n")

        for attempt in range(8):
            result = self.run_hook(
                self.events["Stop"],
                root,
                self.event_for("Stop", stop_hook_active=True),
            )
            self.assertEqual(result.returncode, 0)
            if attempt == 0:
                self.assert_warning(result)
            else:
                self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
        status = self.health(root)
        self.assertEqual(status["status"], "degraded")
        self.assertEqual(status["records"][0]["exitCode"], 2)
        self.assertNotIn("fixture failure", json.dumps(status))

    def test_configured_capture_runs_both_arms_and_recovers_missing_entrypoint(self):
        root = self.make_versioned_package("real")
        (self.root / "STATE.md").write_text("# Prior decision\nRun tests and verify source data before release.")
        runner = root / "scripts/memory_context/runner.py"
        subprocess.run([sys.executable, str(runner), "opportunity-configure", "--workspace", str(self.root),
                        "--answer-pairs-per-day", "0"], env=self.environment, capture_output=True, check=True)
        for host in ("claude", "codex"):
            command = self.events["UserPromptSubmit"]
            if host == "claude":
                command = "unset PLUGIN_ROOT; " + command
            entry = root / "hooks/memory-opportunity.py"
            content = entry.read_text()
            entry.unlink()
            self.assert_warning(self.run_hook(command, root, self.event_for("UserPromptSubmit")))
            entry.write_text(content)
            for event_name in ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"):
                command = self.events[event_name]
                if host == "claude":
                    command = "unset PLUGIN_ROOT; " + command
                result = self.run_hook(command, root, self.event_for(event_name))
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        receipt_dir = self.root / "context/memory-context/paired-opportunities-v1/receipts"
        receipts = [json.loads(p.read_text()) for p in receipt_dir.glob("*.json")]
        self.assertEqual(len(receipts), 2)
        for receipt in receipts:
            self.assertEqual(receipt["comparisonStatus"], "complete")
            self.assertTrue(all(receipt["arms"][a]["actuallyRan"] for a in ("A", "B")))
            self.assertTrue(receipt["observation"]["ended"])
            self.assertEqual(receipt["observation"]["toolCalls"], 1)
        self.assertEqual(self.health(root)["status"], "operational")

    def test_bootstrap_import_protocol_and_payload_boundaries(self):
        root = self.make_versioned_package("boundaries")
        hook = root / "hooks/memory-opportunity-stop.py"
        original = hook.read_text()
        for source in ("import absent_fixture_module\n", "print('{\"outcome\":\"PRIVATE_SECRET\"}')\n",
                       "print('PRIVATE_SECRET' * 10000)\n"):
            hook.write_text(source)
            result = self.run_hook(self.events["Stop"], root, self.event_for("Stop"))
            self.assertEqual(result.returncode, 0)
            self.assertNotIn("PRIVATE_SECRET", result.stdout + result.stderr + json.dumps(self.health(root)))
        hook.write_text(original)
        event = self.event_for("PostToolUse")
        event["tool_response"] = "x" * (1024 * 1024 + 1)
        result = self.run_hook(self.events["PostToolUse"], root, event)
        self.assertEqual(result.stdout, "")
        self.assertIn("payload_too_large", json.dumps(self.health(root)))
        (root / "scripts/memory_context/hook_runtime.py").unlink()
        self.assert_warning(self.run_hook(self.events["Stop"], root, self.event_for("Stop")))
        self.assert_warning(self.run_hook("PATH=/nonexistent; " + self.events["Stop"], root, self.event_for("Stop")))

    def test_all_direct_entrypoints_dispatch_their_fixed_event(self):
        root = self.make_versioned_package("direct")
        for event, name in (("SessionStart", "memory-opportunity-session.py"),
                            ("UserPromptSubmit", "memory-opportunity.py"),
                            ("PostToolUse", "memory-opportunity-tool.py"), ("Stop", "memory-opportunity-stop.py")):
            result = subprocess.run([sys.executable, str(root / "hooks" / name)], input=json.dumps(self.event_for(event)),
                                    text=True, env=self.environment, capture_output=True, timeout=5)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        records = self.health(root)["records"]
        self.assertEqual({r["lane"] for r in records}, set(self.events))

    def test_worker_failure_is_visible_and_does_not_block_hook(self):
        root = self.make_versioned_package("worker")
        runner = root / "scripts/memory_context/runner.py"
        runner.write_text("def main(args):\n    raise ValueError('PRIVATE_SECRET')\n")
        (root / "hooks/memory-opportunity-session.py").write_text("print('{\"outcome\":\"observed\"}')\n")
        start = time.monotonic()
        self.run_hook(self.events["SessionStart"], root, self.event_for("SessionStart"))
        self.assertLess(time.monotonic() - start, 3)
        for _ in range(100):
            status = self.health(root)
            if any(r["error"] == "worker_failed" for r in status["records"]):
                break
            time.sleep(.02)
        else:
            self.fail("worker failure was not recorded")
        self.assertNotIn("PRIVATE_SECRET", json.dumps(status))
        result = self.run_hook(self.events["Stop"], root, self.event_for("Stop"))
        self.assert_warning(result)
        self.assertEqual(self.health(root)["status"], "degraded")
        runner.write_text("def main(args):\n    print('{}')\n    return 0\n")
        self.run_hook(self.events["SessionStart"], root, self.event_for("SessionStart"))
        for _ in range(100):
            if self.health(root)["status"] == "operational":
                break
            time.sleep(.02)
        else:
            self.fail("worker recovery was not recorded")


if __name__ == "__main__":
    unittest.main()
