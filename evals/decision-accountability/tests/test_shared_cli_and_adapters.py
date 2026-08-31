from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "rhize-context-manager" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from graph_memory.contract import canonical_json, sha256_value  # noqa: E402
from graph_memory.decisions import (  # noqa: E402
    DecisionError,
    DecisionPreviewStore,
    InMemoryDecisionLedger,
)


CLI = SCRIPTS / "graph_memory" / "cli.py"
FIXTURES = (
    ROOT
    / "evals"
    / "decision-accountability"
    / "fixtures"
    / "typed-adapter-proposals.json"
)
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
PRINCIPAL = sha256_value("principal:typed-adapter-fixture")
SCOPES = ["decision:record", "group:fixture"]
NONCE = "typed-adapter-nonce-0001"
ZERO_HASH = "0" * 64


class SharedDecisionCliAndAdapterTests(unittest.TestCase):
    def test_three_consumer_fixtures_are_strict_deterministic_proposals(self) -> None:
        fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
        expected = {
            "rhize-devflow": ("release", "software-delivery", "git"),
            "rhize-ops": ("adoption", "operations-experiment", "jira"),
            "rhize-tasks": (
                "external_effect_routing",
                "routing-operations",
                "local-planning-state",
            ),
        }
        self.assertEqual(set(fixtures), set(expected))

        for workflow, proposal in fixtures.items():
            decision_class, domain, source_system = expected[workflow]
            self.assertEqual(proposal["workflow"], {"id": workflow, "revision": "adapter-v1"})
            self.assertEqual(
                (proposal["decisionClass"], proposal["domain"], proposal["source"]["system"]),
                (decision_class, domain, source_system),
            )
            self.assertEqual(proposal["tenantRef"], "tenant-fixture")
            self.assertNotIn("RT-", canonical_json(proposal))

            with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
                first_preview = self._preview(Path(first), proposal, workflow)
                second_preview = self._preview(Path(second), proposal, workflow)
                self.assertEqual(canonical_json(first_preview), canonical_json(second_preview))
                path = Path(first) / f"{first_preview['previewId']}.json"
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_fixture_adapter_rejects_private_trace_fields(self) -> None:
        proposal = json.loads(FIXTURES.read_text(encoding="utf-8"))["rhize-devflow"]
        proposal["transcript"] = "private agent trace"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DecisionError, "fields missing=.*unknown=.*transcript"):
                self._preview(Path(directory), proposal, "private-trace")

    def test_cli_preview_is_byte_stable_and_record_remains_unavailable(self) -> None:
        proposal = json.loads(FIXTURES.read_text(encoding="utf-8"))["rhize-devflow"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_path = root / "proposal.json"
            proposal_path.write_text(canonical_json(proposal), encoding="utf-8")
            first = self._cli_preview(proposal_path, root / "one")
            second = self._cli_preview(proposal_path, root / "two")
            self.assertEqual(first.stdout, second.stdout)
            payload = json.loads(first.stdout)
            self.assertEqual(payload["status"], "previewed_offline")
            self.assertEqual(payload["publication"], "not_published")
            preview_id = payload["previewReceipt"]["previewId"]
            self.assertNotIn("preview", payload)
            self.assertNotIn("proposal", first.stdout)
            self.assertNotIn("tenant-fixture", first.stdout)

            record = self._run_cli("decision", "record", "--preview-id", preview_id)
            record_payload = json.loads(record.stdout)
            self.assertEqual(record_payload["status"], "unavailable")
            self.assertFalse(record_payload["shadowStoreCreated"])
            self.assertTrue((root / "one" / f"{preview_id}.json").exists())

    def test_projection_operations_fail_closed_without_a_shadow_store(self) -> None:
        status = json.loads(self._run_cli("decision", "status").stdout)
        self.assertEqual(status["offlineOperations"], ["preview"])
        self.assertIn("record", status["projectionOperations"])
        self.assertFalse(status["liveNeo4jEnabled"])
        self.assertFalse(status["shadowStoreCreated"])

        commands = {
            "explain": ["--decision-id", ZERO_HASH],
            "impact": ["--decision-id", ZERO_HASH],
            "correct": ["--decision-id", ZERO_HASH],
            "precedents": [
                "--decision-class",
                "release",
                "--domain",
                "software-delivery",
                "--current-policy-digest",
                ZERO_HASH,
            ],
        }
        for operation, arguments in commands.items():
            payload = json.loads(self._run_cli("decision", operation, *arguments).stdout)
            self.assertEqual(payload["status"], "unavailable")
            self.assertEqual(payload["operation"], operation)
            self.assertFalse(payload["shadowStoreCreated"])

    def test_consumer_docs_point_to_one_shared_contract(self) -> None:
        reference = "typed-decision-adapters.md"
        for plugin in ("rhize-devflow", "rhize-ops", "rhize-tasks"):
            readme = (ROOT / plugin / "README.md").read_text(encoding="utf-8")
            guide = (ROOT / plugin / "GUIDE.md").read_text(encoding="utf-8")
            self.assertIn(reference, readme)
            self.assertIn("decision", guide.casefold())
            self.assertNotIn("MATCH (", readme)
            self.assertNotIn("MERGE (", readme)

        command = (
            ROOT / "rhize-context-manager" / "commands" / "graph-decision.md"
        ).read_text(encoding="utf-8")
        metadata = (
            ROOT
            / "rhize-context-manager"
            / "skills"
            / "graph-memory"
            / "agents"
            / "openai.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("graph-memory decision", command)
        self.assertIn("offline", metadata.casefold())

    def _preview(self, root: Path, proposal: dict, idempotency_key: str) -> dict:
        return InMemoryDecisionLedger(DecisionPreviewStore(root)).preview(
            proposal,
            principal_hash=PRINCIPAL,
            principal_scopes=SCOPES,
            idempotency_key=idempotency_key,
            nonce=NONCE,
            now=NOW,
        )

    def _cli_preview(self, proposal: Path, preview_root: Path) -> subprocess.CompletedProcess[str]:
        return self._run_cli(
            "decision",
            "preview",
            "--proposal",
            str(proposal),
            "--preview-root",
            str(preview_root),
            "--principal-hash",
            PRINCIPAL,
            "--principal-scope",
            SCOPES[0],
            "--principal-scope",
            SCOPES[1],
            "--idempotency-key",
            "cli-fixture",
            "--nonce",
            NONCE,
            "--at",
            "2026-08-30T12:00:00Z",
        )

    def _run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
