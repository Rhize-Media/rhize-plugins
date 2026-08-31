from __future__ import annotations

import json
import unittest

from hygiene_support import ROOT


class DeliveryContractTests(unittest.TestCase):
    def test_identity_schemas_are_closed_and_parseable(self) -> None:
        for name in (
            "identity-review-v1.schema.json", "identity-decision-ledger-v1.schema.json"
        ):
            schema = json.loads((ROOT / "rhize-context-manager" / "schemas" / name).read_text())
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(set(schema["required"]), set(schema["properties"]))

    def test_claude_command_is_thin_and_preserves_canonical_cli_ownership(self) -> None:
        command = (
            ROOT / "rhize-context-manager" / "commands" / "graph-memory-review.md"
        ).read_text()
        self.assertIn("canonical `rhize-context-manager:graph-memory` skill", command)
        self.assertIn("host-neutral graph-memory CLI", command)
        self.assertIn("Never physically merge", command)
        self.assertNotIn("neo4j://", command)

    def test_fixture_inventory_covers_poison_race_failure_and_reversal(self) -> None:
        fixtures = ROOT / "evals" / "graph-hygiene" / "fixtures"
        for name in (
            "labeled-pairs.json", "poison-corpus.json", "race-and-failure.json",
            "golden-reversal.json",
        ):
            payload = json.loads((fixtures / name).read_text())
            self.assertTrue(payload)


if __name__ == "__main__":
    unittest.main()
