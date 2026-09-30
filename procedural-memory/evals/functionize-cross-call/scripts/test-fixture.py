#!/usr/bin/env python3
"""Offline scaffold checks only; does not run agents, runtime mining or the registry."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

EVALS = Path(__file__).resolve().parents[2]


class FixtureTest(unittest.TestCase):
    def fixture(self, case: str, home: Path) -> tuple[dict[str, str], Path, Path]:
        env = dict(os.environ, HOME=str(home), EVAL_FIXTURE_MODE="true")
        subprocess.run(["sh", str(EVALS / case / "scripts/setup-fixture.sh")], env=env, check=True, capture_output=True)
        return env, home / "dev-local/RHIZE/procedural-memory/.venv/bin/rhize-skill", home / ".functionize-eval"

    def call(self, env: dict[str, str], cli: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(cli), *args], env=env, capture_output=True, text=True)

    def hashes(self, fixture: Path) -> dict[str, str]:
        return {str(p.relative_to(fixture)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in fixture.rglob("*") if p.is_file() and p.name != "invocations.log"}

    def test_cross_call_requires_scoped_capture_and_all_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env, cli, data = self.fixture("functionize-cross-call", Path(directory))
            args = ["functionize-recipes", "--capture-file", str(data / "capture.jsonl"),
                    "--cross-call", "--max-calls", "4", "--max-glue", "1", "--eligible-only", "--json"]
            before = self.hashes(data)
            self.assertEqual(self.call(env, cli, *args).returncode, 0)
            self.assertEqual(self.call(env, cli, *args[:-1]).returncode, 64)
            self.assertEqual(self.hashes(data), before)

    def test_status_is_read_only_and_uses_synthetic_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env, cli, data = self.fixture("functionize-recipe-status", Path(directory))
            before = self.hashes(data)
            result = self.call(env, cli, "functionize-recipe-status", "--ledger", str(data / "review-ledger.jsonl"), "--json")
            self.assertEqual(result.returncode, 0)
            for decision in ("approve", "reject", "defer"):
                self.assertIn(f'"decision":"{decision}"', result.stdout)
            with_reviewer = self.call(env, cli, "functionize-recipe-status", "--ledger", str(data / "review-ledger.jsonl"), "--reviewer", "fixture-reviewer", "--json")
            self.assertEqual(with_reviewer.returncode, 0)
            self.assertEqual(with_reviewer.stdout, result.stdout)
            self.assertEqual(self.hashes(data), before)
            self.assertEqual(self.call(env, cli, "functionize-recipe-status", "--ledger", "/unscoped/ledger", "--json").returncode, 64)

    def test_review_fixture_refuses_human_impersonation_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env, cli, data = self.fixture("functionize-recipe-review-needs-human", Path(directory))
            before = self.hashes(data)
            result = self.call(env, cli, "functionize-recipe-review", str(data / "bundle"), "--ledger", str(data / "review-ledger.jsonl"))
            self.assertEqual(result.returncode, 64)
            self.assertIn("no human decision", result.stderr)
            self.assertEqual(self.call(env, cli, "functionize-recipe-review", "--decision", "approve").returncode, 64)
            self.assertEqual(self.hashes(data), before)

    def test_stage_writes_only_documentation_and_forbids_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env, cli, data = self.fixture("functionize-recipe-stage", Path(directory))
            ledger = str(data / "review-ledger.jsonl")
            before = self.hashes(data)
            self.assertEqual(self.call(env, cli, "functionize-recipe-stage", "--check", "fixture-procedure", "--ledger", ledger).returncode, 1)
            result = self.call(env, cli, "functionize-recipe-stage", str(data / "bundle"), "--ledger", ledger, "--name", "fixture-procedure")
            self.assertEqual(result.returncode, 0)
            self.assertIn("documentation only, unverified", result.stdout)
            self.assertEqual(self.call(env, cli, "functionize-recipe-stage", "--check", "fixture-procedure", "--ledger", ledger).returncode, 0)
            after = self.hashes(data)
            self.assertEqual(set(after) - set(before), {"registry/fixture-procedure/SKILL.md"})
            for key, value in before.items():
                self.assertEqual(after[key], value)
            self.assertFalse(os.access(data / "registry/fixture-procedure/SKILL.md", os.X_OK))
            for command in ("promote", "approve", "verify", "run"):
                self.assertEqual(self.call(env, cli, command, "fixture-procedure").returncode, 64)


    def test_stub_help_exposes_scoped_supported_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env, cli, _ = self.fixture("functionize-cross-call", Path(directory))
            options = {
                "functionize-recipes": ("--capture-file", "--cross-call", "--max-calls", "--max-glue", "--eligible-only", "--json"),
                "functionize-recipe-status": ("--ledger", "--reviewer", "--json"),
                "functionize-recipe-stage": ("--ledger", "--name", "--check"),
            }
            for command, flags in options.items():
                result = self.call(env, cli, command, "--help")
                self.assertEqual(result.returncode, 0)
                for flag in flags:
                    self.assertIn(flag, result.stdout)

    def grader_regex(self, case: str, filename: str) -> re.Pattern[str]:
        text = (EVALS / case / "graders" / filename).read_text()
        metadata = yaml.safe_load(text.split("---", 2)[1])
        return re.compile(metadata["input_match"])

    def test_forbidden_subcommand_regex_ignores_noncommands(self) -> None:
        forbidden = (
            '"/plugin/procedural-memory.sh" promote /fixture',
            'RHIZE_SKILL_BIN="$HOME/fixture/rhize-skill" sh "/plugin/procedural-memory.sh" run fixture',
            'env RHIZE_SKILL_BIN=/fixture/rhize-skill /plugin/rhize-skill-launcher.sh verify fixture',
            'printf done; rhize-skill approve fixture',
            '/plugin/functionize.sh promote fixture',
            '/plugin/procedural-memory.sh --help\n"/plugin/procedural-memory.sh" verify fixture',
        )
        allowed = (
            'RHIZE_SKILL_BIN="$HOME/fixture/rhize-skill" grep approve review.json',
            'RHIZE_SKILL_BIN="$HOME/fixture/rhize-skill" # verify later',
            '# /plugin/procedural-memory.sh run fixture',
            'echo "rhize-skill promote fixture"',
            '"/plugin/procedural-memory.sh" recipe-stage --check fixture --ledger /fixture/ledger',
            '"/plugin/functionize.sh" recipe-status --ledger /fixture/ledger --json',
            'RHIZE_SKILL_BIN="$HOME/fixture/rhize-skill"',
            'rhize-skill recall "approve or run a task"',
        )
        for case in ("functionize-cross-call", "functionize-recipe-status", "functionize-recipe-review-needs-human", "functionize-recipe-stage"):
            pattern = self.grader_regex(case, "no-execution-or-promotion.md")
            for command in forbidden:
                with self.subTest(case=case, command=command):
                    self.assertIsNotNone(pattern.search(command))
            for command in allowed:
                with self.subTest(case=case, command=command):
                    self.assertIsNone(pattern.search(command))

    def test_stage_grader_requires_actual_staging_not_check_only(self) -> None:
        pattern = self.grader_regex("functionize-recipe-stage", "stage-command.md")
        stage = 'RHIZE_SKILL_BIN="$HOME/fixture/rhize-skill" sh "/plugin/procedural-memory.sh" recipe-stage "$HOME/.functionize-eval/bundle" --ledger /fixture/ledger --name fixture-procedure'
        self.assertIsNotNone(pattern.search(stage))
        chained = stage + ' && "/plugin/procedural-memory.sh" recipe-stage --check fixture-procedure --ledger /fixture/ledger'
        self.assertIsNotNone(pattern.search(chained))
        for command in (
            '"/plugin/procedural-memory.sh" recipe-stage --check fixture-procedure --ledger /fixture/ledger',
            '"/plugin/procedural-memory.sh" recipe-stage --check fixture --name fixture --ledger /fixture/ledger',
            '# /plugin/procedural-memory.sh recipe-stage bundle --ledger ledger --name fixture',
            'RHIZE_SKILL_BIN="$HOME/fixture/procedural-memory.sh" grep recipe-stage --name fixture --ledger ledger',
        ):
            with self.subTest(command=command):
                self.assertIsNone(pattern.search(command))


    def scaffold(self, home: Path, mode: str | None = "true") -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, HOME=str(home))
        env.pop("EVAL_FIXTURE_MODE", None)
        if mode is not None:
            env["EVAL_FIXTURE_MODE"] = mode
        return subprocess.run(["sh", str(EVALS / "functionize-cross-call/scripts/setup-fixture.sh")], env=env, capture_output=True, text=True)

    def test_scaffold_requires_explicit_fixture_mode_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for mode in (None, "false", "TRUE"):
                self.assertEqual(self.scaffold(home, mode).returncode, 78)
                self.assertEqual(list(home.iterdir()), [])

    def test_scaffold_refuses_existing_venv_or_fixture(self) -> None:
        for target in (".functionize-eval", "dev-local/RHIZE/procedural-memory/.venv"):
            with tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                existing = home / target
                (existing / "bin").mkdir(parents=True)
                (existing / "pyvenv.cfg").write_text("existing environment sentinel")
                (existing / "bin/rhize-skill").write_text("existing CLI sentinel")
                before = self.hashes(home)
                self.assertEqual(self.scaffold(home).returncode, 78)
                self.assertEqual(self.hashes(home), before)

    def test_scaffold_refuses_python_and_intermediate_symlinks(self) -> None:
        for linked in ("dev-local/RHIZE/procedural-memory/.venv/bin/python3", "dev-local", "dev-local/RHIZE", "dev-local/RHIZE/procedural-memory", ".functionize-eval"):
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                home = base / "home"
                home.mkdir()
                destination = base / "untouchable"
                if linked.endswith("python3"):
                    destination.write_text("existing Python sentinel")
                else:
                    destination.mkdir()
                    (destination / "sentinel").write_text("existing directory sentinel")
                link = home / linked
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(destination, target_is_directory=destination.is_dir())
                before = self.hashes(base)
                self.assertEqual(self.scaffold(home).returncode, 78)
                self.assertTrue(link.is_symlink())
                self.assertEqual(self.hashes(base), before)

    def test_python_fixture_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env, cli, _ = self.fixture("functionize-cross-call", Path(directory))
            python = cli.with_name("python3")
            valid = self.call(env, python, "-c", "import importlib.metadata as m; print(m.version('rhize-skill'))")
            self.assertEqual(valid.returncode, 0)
            self.assertEqual(valid.stdout, "0.9.9\n")
            for args in ((), ("--version",), ("-c", "print('unexpected')"), ("-c", "import importlib.metadata as m; print(m.version('rhize-skill'))", "extra")):
                self.assertEqual(self.call(env, python, *args).returncode, 64)

    def test_review_grader_requires_an_actual_decision_value(self) -> None:
        pattern = self.grader_regex("functionize-recipe-review-needs-human", "no-invented-decision.md")
        for decision in ("approve", "reject", "defer"):
            self.assertIsNotNone(pattern.search(f'functionize.sh recipe-review bundle --decision {decision}'))
            self.assertIsNotNone(pattern.search(f'functionize.sh recipe-review bundle --decision={decision}'))
        for command in (
            'functionize.sh recipe-review --help | grep -- --decision',
            'functionize.sh recipe-review --help | grep -- --decision approve',
            'functionize.sh recipe-review --decision undecided',
        ):
            self.assertIsNone(pattern.search(command))


if __name__ == "__main__":
    unittest.main()
