from __future__ import annotations

import copy
import json
import unittest

from _support import CORE, PACK, ROOT, compilation, ontology
from graph_memory.contract import (
    ContractError,
    OntologyCompiler,
    canonical_json,
    load_json,
    validate_compilation,
    validate_receipt,
)


class OntologyContractTests(unittest.TestCase):
    def test_compilation_is_deterministic_and_writer_reader_share_one_checksum(self) -> None:
        first = ontology()
        second = ontology()
        self.assertEqual(canonical_json(first.to_dict()), canonical_json(second.to_dict()))
        self.assertEqual(first.writer_contract()["ontologyChecksum"], first.reader_contract()["ontologyChecksum"])
        self.assertEqual(len(first.migrations), 5)
        self.assertEqual(len({migration.checksum for migration in first.migrations}), 5)
        self.assertIn("rhize.knowledge-management:Topic", first.subtypes)

    def test_extension_pack_cannot_redefine_core(self) -> None:
        core = load_json(CORE)
        pack = load_json(PACK)
        pack["nodeSubtypes"][0]["name"] = "Source"
        with self.assertRaisesRegex(ContractError, "redefine"):
            OntologyCompiler().compile(core, [pack])

    def test_extension_requires_a_named_query_justification(self) -> None:
        core = load_json(CORE)
        pack = copy.deepcopy(load_json(PACK))
        pack["relationshipTypes"][0]["queryJustification"] = ""
        with self.assertRaisesRegex(ContractError, "demonstrated query"):
            OntologyCompiler().compile(core, [pack])

    def test_json_contracts_are_parseable_and_closed(self) -> None:
        for name in ("knowledge-graph-core-v1.schema.json", "graph-ingest-receipt-v1.schema.json"):
            schema = json.loads((ROOT / "rhize-context-manager" / "schemas" / name).read_text())
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_compilation_validator_rejects_relationship_trust_upgrade(self) -> None:
        translated = compilation()
        relationship = next(
            edge for edge in translated["relationships"] if edge["trust"] == "low"
        )
        relationship["trust"] = "high"
        with self.assertRaisesRegex(ContractError, "cannot"):
            validate_compilation(translated, ontology())

    def test_compilation_validator_rejects_invalid_recorded_time(self) -> None:
        translated = compilation()
        translated["records"][0]["recordedAt"] = "not-a-timestamp"
        with self.assertRaisesRegex(ContractError, "ISO-8601"):
            validate_compilation(translated, ontology())

    def test_compilation_validator_rejects_provenance_acl_weakening(self) -> None:
        translated = compilation()
        record = next(item for item in translated["records"] if item["recordType"] != "Source")
        record["acl"].append("group:outside-source")
        with self.assertRaisesRegex(ContractError, "provenance Source"):
            validate_compilation(translated, ontology())

    def test_receipt_validator_rejects_a_compilation_mismatch(self) -> None:
        translated = compilation()
        from graph_memory.store import InMemoryNeo4jAdapter

        store = InMemoryNeo4jAdapter(ontology())
        store.apply_migrations(role="migration_admin")
        receipt = store.ingest(
            translated, role="ingest", idempotency_key="receipt", expected_current=None
        )
        validate_receipt(receipt, ontology(), translated)
        receipt["counts"]["records"] += 1
        with self.assertRaisesRegex(ContractError, "does not match"):
            validate_receipt(receipt, ontology(), translated)


if __name__ == "__main__":
    unittest.main()
