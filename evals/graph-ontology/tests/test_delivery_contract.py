from __future__ import annotations

import re
import unittest

from _support import ROOT


class DeliveryContractTests(unittest.TestCase):
    def test_graphify_has_no_runnable_direct_neo4j_export(self) -> None:
        graphify = (ROOT / "rhize-context-manager" / "skills" / "graphify" / "SKILL.md").read_text()
        exports = (
            ROOT / "rhize-context-manager" / "skills" / "graphify" / "references" / "exports.md"
        ).read_text()
        self.assertIsNone(re.search(r"(?m)^graphify export neo4j(?:\s|$)", graphify))
        self.assertIsNone(re.search(r"(?m)^graphify export neo4j(?:\s|$)", exports))
        self.assertIn("never run Graphify's direct Neo4j exporter", graphify)
        self.assertIn("RT-159", exports)

    def test_claude_and_codex_share_one_canonical_skill_and_cli(self) -> None:
        skill = ROOT / "rhize-context-manager" / "skills" / "graph-memory" / "SKILL.md"
        codex = skill.parent / "agents" / "openai.yaml"
        command = ROOT / "rhize-context-manager" / "commands" / "graph-memory.md"
        cli = ROOT / "rhize-context-manager" / "scripts" / "graph_memory" / "cli.py"
        self.assertTrue(all(path.is_file() for path in (skill, codex, command, cli)))
        self.assertIn("host-neutral CLI", skill.read_text())
        self.assertIn("canonical `rhize-context-manager:graph-memory` skill", command.read_text())
        self.assertIn("$graph-memory", codex.read_text())


if __name__ == "__main__":
    unittest.main()
