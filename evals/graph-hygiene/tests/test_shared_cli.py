from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "rhize-context-manager" / "scripts" / "graph_memory" / "cli.py"


class SharedHygieneCliTests(unittest.TestCase):
    def test_status_discloses_the_offline_only_boundary(self) -> None:
        status = self._run("status")
        self.assertEqual(status["status"], "offline_contract_only")
        self.assertEqual(status["sharedCliOperations"], ["status"])
        self.assertIn("preview", status["inProcessContractOperations"])
        self.assertFalse(status["privateStateAdapterConfigured"])
        self.assertFalse(status["automaticSameAs"])
        self.assertFalse(status["liveNeo4jEnabled"])

    def test_stateful_operations_are_deterministic_structured_unavailable(self) -> None:
        for operation in (
            "list", "show", "lease", "preview", "decide", "defer", "reverse",
            "consolidate", "quality",
        ):
            first = self._run(operation)
            second = self._run(operation)
            self.assertEqual(first, second)
            self.assertEqual(first["status"], "unavailable")
            self.assertEqual(
                first["reason"], "governed_private_state_adapter_not_configured"
            )
            self.assertFalse(first["shadowStoreCreated"])
            self.assertFalse(first["projectionPublished"])

    def test_supplied_artifact_is_not_read_or_misrepresented(self) -> None:
        payload = self._run("preview", "--state-artifact", "/not/read/state.json")
        self.assertEqual(payload["status"], "unavailable")
        self.assertTrue(payload["stateArtifactSupplied"])
        self.assertFalse(payload["privateStateAdapterConfigured"])

    def test_claude_and_codex_discovery_point_to_the_same_boundary(self) -> None:
        skill = (
            ROOT / "rhize-context-manager" / "skills" / "graph-memory" / "SKILL.md"
        ).read_text(encoding="utf-8")
        command = (
            ROOT / "rhize-context-manager" / "commands" / "graph-memory-review.md"
        ).read_text(encoding="utf-8")
        metadata = (
            ROOT
            / "rhize-context-manager"
            / "skills"
            / "graph-memory"
            / "agents"
            / "openai.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("graph-memory hygiene", command)
        self.assertIn("governed_private_state_adapter_not_configured", skill)
        self.assertIn("same skill", skill)
        self.assertIn("offline", metadata.casefold())
        self.assertNotIn("MATCH (", command)
        self.assertNotIn("MERGE (", command)

    @staticmethod
    def _run(*arguments: str) -> dict:
        completed = subprocess.run(
            [sys.executable, str(CLI), "hygiene", *arguments],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)


if __name__ == "__main__":
    unittest.main()
