from __future__ import annotations

import unittest

from decision_support import ROOT


class DecisionDeliveryContractTests(unittest.TestCase):
    def test_command_is_thin_and_refuses_shadow_or_direct_graph_writes(self) -> None:
        command = (ROOT / "rhize-context-manager" / "commands" / "graph-decision.md").read_text()
        self.assertIn("canonical `rhize-context-manager:graph-memory` skill", command)
        self.assertIn("return `unavailable`", command)
        self.assertIn("Never infer a decision from an agent", command)
        self.assertNotIn("MATCH (", command)
        self.assertNotIn("MERGE (", command)

    def test_no_semantica_or_live_neo4j_dependency_is_introduced(self) -> None:
        decisions = (
            ROOT / "rhize-context-manager" / "scripts" / "graph_memory" / "decisions.py"
        ).read_text()
        provenance = (
            ROOT / "rhize-context-manager" / "scripts" / "graph_memory" / "prov_export.py"
        ).read_text()
        self.assertNotIn("import neo4j", decisions)
        self.assertNotIn("import semantica", decisions.casefold())
        self.assertNotIn("import rdflib", provenance)


if __name__ == "__main__":
    unittest.main()
