import json
import importlib.util
import subprocess
import tempfile
import unittest
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
    def prepare(self, task_id: str, root: Path) -> Path:
        run_dir = root / task_id
        subprocess.run(
            [
                "python3",
                str(PREPARE),
                "--task",
                task_id,
                "--variant",
                "baseline",
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

    def receipt(self, task: dict) -> dict:
        return {
            "schema_version": 1,
            "run_id": f"{task['id']}-baseline",
            "variant": "baseline",
            "task_id": task["id"],
            "started_at": "2026-08-27T20:00:00+00:00",
            "completed_at": "2026-08-27T20:00:01+00:00",
            "decision": task["expected_decision"],
            "decision_reason": "golden harness test",
            "lanes_planned": 1,
            "agents": [],
            "tool_calls": None,
            "tool_calls_availability_reason": "test host does not expose authoritative counts",
            "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None},
            "tokens_availability_reason": "test host does not expose authoritative counts",
            "required_checks": task["required_checks"],
            "completed_checks": task["required_checks"],
            "passed_checks": task["required_checks"],
            "collisions": 0,
            "rework_events": 0,
            "correctness_claimed": True,
        }

    def test_all_golden_outcomes_grade_cleanly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for task in MANIFEST["tasks"]:
                with self.subTest(task=task["id"]):
                    run_dir = self.prepare(task["id"], root)
                    self.solve(task["id"], run_dir)
                    (run_dir / "receipt.json").write_text(json.dumps(self.receipt(task)) + "\n")
                    completed = subprocess.run(
                        ["python3", str(GRADE), str(run_dir)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                    grade = json.loads((run_dir / "grade.json").read_text())
                    self.assertTrue(grade["correctness_pass"])
                    self.assertTrue(grade["appropriateness_pass"])

    def test_overlap_requires_intersecting_agent_intervals(self):
        agents = [
            {
                "started_at": "2026-08-27T20:00:00Z",
                "completed_at": "2026-08-27T20:00:10Z",
            },
            {
                "started_at": "2026-08-27T20:00:05Z",
                "completed_at": "2026-08-27T20:00:15Z",
            },
        ]
        metrics = AGGREGATE_MODULE.overlap_metrics(agents)
        self.assertEqual(metrics["max_concurrency"], 2)
        self.assertEqual(metrics["concurrent_agent_seconds"], 5.0)
        self.assertEqual(metrics["parallelism_ratio"], 0.25)
        self.assertTrue(metrics["actual_overlap"])

        agents[1]["started_at"] = "2026-08-27T20:00:10Z"
        metrics = AGGREGATE_MODULE.overlap_metrics(agents)
        self.assertEqual(metrics["max_concurrency"], 1)
        self.assertFalse(metrics["actual_overlap"])


if __name__ == "__main__":
    unittest.main()
