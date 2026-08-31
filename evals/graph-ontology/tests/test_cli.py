from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from _support import CORE, FIXTURES, PACK, ROOT


CLI = ROOT / "rhize-context-manager" / "scripts" / "graph_memory" / "cli.py"


class HostNeutralCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> dict:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(CLI), "--core", str(CORE), "--pack", str(PACK), *arguments],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_status_is_explicitly_offline(self) -> None:
        status = self.run_cli("status")
        self.assertFalse(status["liveNeo4jEnabled"])
        self.assertEqual(status["liveCanaryIssue"], "RT-159")

    def test_preview_is_byte_equivalent_across_host_labels(self) -> None:
        arguments = (
            "preview", "--graph", str(FIXTURES / "graph.json"),
            "--manifest", str(FIXTURES / "manifest.json"),
            "--tenant", "tenant-a", "--namespace", "rhize-tools",
        )
        claude_output = self.run_cli(*arguments)
        codex_output = self.run_cli(*arguments)
        self.assertEqual(claude_output, codex_output)

    def test_manifest_binds_exported_graphify_commit_and_recorded_time(self) -> None:
        manifest = self.run_cli(
            "manifest", "--graph", str(FIXTURES / "graph.json"),
            "--corpus-id", "fixture", "--source-revision", "revision-1",
            "--extractor-version", "0.9.45", "--recorded-at", "2026-08-30T00:00:00Z",
            "--acl", "group:rhize-tools",
        )
        self.assertEqual(manifest["graphifyBuildCommit"], "a" * 40)
        self.assertEqual(manifest["recordedAt"], "2026-08-30T00:00:00Z")

    def test_ingest_receipt_is_hashes_counts_and_versions_only(self) -> None:
        result = self.run_cli(
            "ingest", "--graph", str(FIXTURES / "graph.json"),
            "--manifest", str(FIXTURES / "manifest.json"),
            "--tenant", "tenant-a", "--namespace", "rhize-tools",
            "--role", "ingest", "--idempotency-key", "cli-fixture",
        )
        receipt_text = json.dumps(result["receipt"], sort_keys=True)
        self.assertNotIn("tenant-a", receipt_text)
        self.assertNotIn("redacted", receipt_text)
        self.assertEqual(result["receipt"]["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
