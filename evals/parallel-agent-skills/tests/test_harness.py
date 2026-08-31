import importlib.util
import json
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "scripts" / "prepare_run.py"
GRADE = ROOT / "scripts" / "grade_run.py"
AGGREGATE = ROOT / "scripts" / "aggregate_results.py"
MANIFEST = json.loads((ROOT / "manifest.json").read_text())

SPEC = importlib.util.spec_from_file_location("aggregate_results", AGGREGATE)
AGGREGATE_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(AGGREGATE_MODULE)


class HarnessTests(unittest.TestCase):
    def prepare(self, task_id: str, root: Path, *, variant="baseline", repetition=1) -> Path:
        run_dir = root / f"{task_id}-{variant}-{repetition}"
        subprocess.run(
            [
                "python3",
                str(PREPARE),
                "--task",
                task_id,
                "--variant",
                variant,
                "--repetition",
                str(repetition),
                "--comparison-id",
                str(uuid.uuid4()),
                "--output",
                str(run_dir),
            ],
            check=True,
        )
        return run_dir

    def solve(self, task_id: str, run_dir: Path) -> None:
        workspace = run_dir / "workspace"
        if task_id == "parallel-read":
            (workspace / "submission.json").write_text(
                json.dumps(
                    {
                        "active_accounts": 3,
                        "production_endpoint": "https://api.rhize.test/v2",
                        "fourth_retry_seconds": 8,
                    }
                )
                + "\n"
            )
        elif task_id == "disjoint-write":
            (workspace / "src" / "pricing.py").write_text(
                "def discounted_total(subtotal: float, percent: float) -> float:\n"
                "    return round(subtotal * (1 - percent / 100), 2)\n"
            )
            (workspace / "src" / "labels.py").write_text(
                "def slugify(label: str) -> str:\n"
                "    return '-'.join(label.lower().split())\n"
            )
        elif task_id == "shared-state":
            (workspace / "src" / "normalizer.py").write_text(
                "import re\n\n\n"
                "def normalize_email(value: str) -> str:\n"
                "    return value.strip().lower()\n\n\n"
                "def normalize_phone(value: str) -> str:\n"
                "    return re.sub(r'[^0-9]', '', value)\n"
            )
        elif task_id == "dependency-chain":
            (workspace / "src" / "schema.py").write_text(
                "from dataclasses import dataclass\n\n\n"
                "@dataclass\n"
                "class UserRecord:\n"
                "    full_name: str\n"
            )
            (workspace / "src" / "renderer.py").write_text(
                "from src.schema import UserRecord\n\n\n"
                "def render_user(user: UserRecord) -> str:\n"
                "    return f'User: {user.full_name}'\n"
            )

    def provisional_receipt(self, context: dict) -> dict:
        expected = context["expected_decision"]
        parallel = expected == "parallel"
        return {
            "schema_version": 2,
            "run_id": context["run_id"],
            "comparison_id": context["comparison_id"],
            "variant": context["variant"],
            "task_id": context["task_id"],
            "task_class": context["task_class"],
            "repetition": context["repetition"],
            "status": "completed",
            "started_at": "2026-08-30T20:00:00+00:00",
            "completed_at": "2026-08-30T20:00:01+00:00",
            "expected_decision": expected,
            "decision": expected,
            "lanes_planned": 2 if parallel else 1,
            "agents": (
                [
                    {
                        "started_at": "2026-08-30T20:00:00+00:00",
                        "completed_at": "2026-08-30T20:00:00.900000+00:00",
                        "status": "completed",
                    },
                    {
                        "started_at": "2026-08-30T20:00:00.100000+00:00",
                        "completed_at": "2026-08-30T20:00:01+00:00",
                        "status": "completed",
                    },
                ]
                if parallel
                else []
            ),
            "tool_calls": None,
            "tool_calls_unavailable_reason": "host_not_exposed",
            "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None},
            "tokens_unavailable_reason": "host_not_exposed",
            "required_checks": context["required_checks"],
            "completed_checks": context["required_checks"],
            "passed_checks": context["required_checks"],
            "collisions": 0,
            "rework_events": 0,
            "correctness_pass": True,
        }

    def test_manifest_is_repeated_baseline_vs_rhize_v2(self):
        self.assertEqual(MANIFEST["schema_version"], 2)
        self.assertEqual(MANIFEST["variants"], ["baseline", "rhize"])
        self.assertEqual(MANIFEST["repetitions"], 3)
        self.assertEqual(len(MANIFEST["tasks"]), 6)

    def test_prepare_has_pending_lifecycle_and_no_vendor_runtime_instruction(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.prepare("parallel-read", Path(temporary), variant="rhize")
            reservation = json.loads((run_dir / "RUN_RESERVATION.json").read_text())
            instructions = (run_dir / "RUN_INSTRUCTIONS.md").read_text()
            self.assertEqual(reservation["status"], "pending")
            self.assertEqual(reservation["schema_version"], 2)
            self.assertIn("Rhize self-contained routing", instructions)
            self.assertNotIn("parallel-execution-optimizer", instructions)
            self.assertNotIn("dispatching-parallel-agents", instructions)

    def test_all_golden_outcomes_grade_to_completed_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for task in MANIFEST["tasks"]:
                with self.subTest(task=task["id"]):
                    run_dir = self.prepare(task["id"], root)
                    self.solve(task["id"], run_dir)
                    context = json.loads((run_dir / "RUN_CONTEXT.json").read_text())
                    (run_dir / "receipt.json").write_text(
                        json.dumps(self.provisional_receipt(context)) + "\n"
                    )
                    completed = subprocess.run(
                        ["python3", str(GRADE), str(run_dir)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                    receipt = json.loads((run_dir / "receipt.json").read_text())
                    grade = json.loads((run_dir / "grade.json").read_text())
                    self.assertEqual(receipt["status"], "completed")
                    self.assertTrue(receipt["correctness_pass"])
                    self.assertTrue(grade["receipt_valid"])

    def test_missing_runner_receipt_finalizes_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self.prepare("parallel-read", Path(temporary))
            completed = subprocess.run(
                ["python3", str(GRADE), str(run_dir)], capture_output=True, text=True, check=False
            )
            self.assertNotEqual(completed.returncode, 0)
            receipt = json.loads((run_dir / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "incomplete")
            self.assertIsNone(receipt["decision"])
            self.assertIsNone(receipt["correctness_pass"])

    def test_overlap_requires_intersecting_agent_intervals(self):
        agents = [
            {"started_at": "2026-08-30T20:00:00Z", "completed_at": "2026-08-30T20:00:10Z"},
            {"started_at": "2026-08-30T20:00:05Z", "completed_at": "2026-08-30T20:00:15Z"},
        ]
        metrics = AGGREGATE_MODULE.overlap_metrics(agents)
        self.assertEqual(metrics["max_concurrency"], 2)
        self.assertEqual(metrics["concurrent_agent_seconds"], 5.0)
        self.assertTrue(metrics["actual_overlap"])
        agents[1]["started_at"] = "2026-08-30T20:00:10Z"
        self.assertFalse(AGGREGATE_MODULE.overlap_metrics(agents)["actual_overlap"])

    def test_aggregate_requires_every_repeated_cell(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "missing evaluation cells"):
                AGGREGATE_MODULE.load_rows(Path(temporary), MANIFEST)

    def test_readiness_keeps_unavailable_optional_metrics_nonblocking(self):
        rows = []
        for task in MANIFEST["tasks"]:
            for repetition in range(1, MANIFEST["repetitions"] + 1):
                comparison_id = str(uuid.uuid4())
                for variant in MANIFEST["variants"]:
                    is_parallel_rhize = (
                        task["expected_decision"] == "parallel" and variant == "rhize"
                    )
                    rows.append(
                        {
                            "run_id": str(uuid.uuid4()),
                            "comparison_id": comparison_id,
                            "task_id": task["id"],
                            "task_class": task["task_class"],
                            "variant": variant,
                            "repetition": repetition,
                            "status": "completed",
                            "expected_decision": task["expected_decision"],
                            "actual_decision": task["expected_decision"],
                            "elapsed_seconds": 80 if variant == "rhize" else 100,
                            "agents_spawned": 2 if is_parallel_rhize else 0,
                            "max_concurrency": 2 if is_parallel_rhize else 0,
                            "concurrent_agent_seconds": 10 if is_parallel_rhize else 0,
                            "total_agent_seconds": 20 if is_parallel_rhize else 0,
                            "parallelism_ratio": 0.5 if is_parallel_rhize else 0,
                            "actual_overlap": is_parallel_rhize,
                            "collisions": 0,
                            "rework_events": 0,
                            "verification_completeness": 1.0,
                            "correctness_pass": True,
                            "appropriateness_pass": True,
                            "receipt_valid": True,
                            "tool_calls": None,
                            "tokens": {
                                "input": None,
                                "output": None,
                                "cache_read": None,
                                "cache_write": None,
                            },
                            "token_totals_available": False,
                        }
                    )
        summary = AGGREGATE_MODULE.build_summary(rows, MANIFEST)
        self.assertEqual(summary["decision_readiness"]["decision"], "ready")
        self.assertEqual(
            summary["decision_readiness"]["optional_metrics"]["tokens"]["status"],
            "unavailable",
        )
        self.assertFalse(
            summary["decision_readiness"]["optional_metrics"]["tokens"][
                "required_for_decision"
            ]
        )


if __name__ == "__main__":
    unittest.main()
