from __future__ import annotations

import copy
import json
import unittest

from decision_support import NOW, ROOT, load_fixture, policy_evaluation, proposal, sha256_value
from graph_memory.contract import compile_ontology
from graph_memory.decisions import (
    DecisionError,
    validate_policy_evaluation,
)


CORE = ROOT / "rhize-context-manager" / "catalog" / "graph-ontology" / "core-v1.json"
PACK = ROOT / "rhize-context-manager" / "catalog" / "graph-ontology" / "packs" / "decision-accountability-v1.json"
SCHEMAS = ROOT / "rhize-context-manager" / "schemas"


class DecisionContractTests(unittest.TestCase):
    def test_namespaced_pack_compiles_without_redefining_core(self) -> None:
        ontology = compile_ontology(CORE, [PACK])
        self.assertEqual(ontology.subtypes["rhize.decision-accountability:Decision"], "Entity")
        self.assertIn("CAUSED", ontology.relationship_types)
        self.assertEqual(ontology.relationship_contracts["BASED_ON"]["targets"], [
            "rhize.decision-accountability:EvidenceSet"
        ])

    def test_schemas_are_closed_draft_2020_12_contracts(self) -> None:
        for name in (
            "decision-record-v1.schema.json",
            "policy-evaluation-v1.schema.json",
            "decision-query-receipt-v1.schema.json",
        ):
            schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(schema["additionalProperties"])
            self.assertNotIn("prompt", json.dumps(schema).casefold())

    def test_policy_fixture_is_reproducible_and_unknown_fields_fail_closed(self) -> None:
        fixture = load_fixture("allow-policy-evaluation.json")
        validate_policy_evaluation(fixture)
        deny_fixture = load_fixture("deny-policy-evaluation.json")
        validate_policy_evaluation(deny_fixture)
        changed = copy.deepcopy(fixture)
        changed["result"] = "deny"
        with self.assertRaisesRegex(DecisionError, "not reproducible"):
            validate_policy_evaluation(changed)
        changed = policy_evaluation()
        changed["rawClientPayload"] = "forbidden"
        with self.assertRaisesRegex(DecisionError, "unknown"):
            validate_policy_evaluation(changed)

    def test_prompt_transcript_and_secret_shaped_content_fail_closed(self) -> None:
        from graph_memory.decisions import DecisionPreviewStore, InMemoryDecisionLedger
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            ledger = InMemoryDecisionLedger(DecisionPreviewStore(Path(directory)))
            item = proposal()
            item["source"]["system"] = "prompt"
            with self.assertRaisesRegex(DecisionError, "private agent traces"):
                ledger.preview(
                    item,
                    principal_hash=sha256_value("principal"),
                    principal_scopes=["decision:record", "group:rhize-tools"],
                    idempotency_key="one", nonce="nonce-for-fixture", now=NOW,
                )
            for index, secret in enumerate(("ghp_" + "a" * 36, "sntrys_" + "a" * 40)):
                item = proposal()
                item["tenantRef"] = secret
                with self.assertRaisesRegex(DecisionError, "secret-shaped content"):
                    ledger.preview(
                        item,
                        principal_hash=sha256_value("principal"),
                        principal_scopes=["decision:record", "group:rhize-tools"],
                        idempotency_key=f"secret-{index}",
                        nonce=f"secret-fixture-{index:02d}",
                        now=NOW,
                    )
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
