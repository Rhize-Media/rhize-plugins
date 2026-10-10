"""Owner links between catalog `external:` nodes and installed third-party plugins.

`catalog/skill-relations.json` references individual third-party agents and skills
(ECC's build resolvers, superpowers skills, ...) as `external:` nodes carrying a
`thirdPartyPlugin` owner. The machine-local overlay must link each one to the
installed plugin node that ships it, so they never render as islands beside the
overlay's own inventory of that plugin.
"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_LOCAL_SKILL_MAP = REPO_ROOT / "rhize-context-manager" / "scripts" / "build_local_skill_map.py"
STATIC_MAP = REPO_ROOT / "generated" / "skill-map.static.json"
CATALOG = REPO_ROOT / "catalog" / "skill-relations.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


blm = _load_module(BUILD_LOCAL_SKILL_MAP, "build_local_skill_map_owner_edges")


class OwnerEdgesTest(unittest.TestCase):
    def test_links_external_to_installed_owner_plugin(self):
        static_nodes = [
            {"id": "external:ecc-git-workflow", "kind": "external", "thirdPartyPlugin": "everything-claude-code/ecc"},
            {"id": "external:ecc-go-build-resolver", "kind": "external", "thirdPartyPlugin": "everything-claude-code/ecc"},
            {"id": "external:skill-forge", "kind": "external"},
        ]
        third_party = [
            {"id": "plugin:everything-claude-code/ecc", "kind": "plugin", "origin": "third-party"},
            {"id": "skill:everything-claude-code/ecc/git-workflow", "kind": "skill", "origin": "third-party"},
        ]
        self.assertEqual(
            blm.build_owner_edges(static_nodes, third_party),
            [
                {"from": "plugin:everything-claude-code/ecc", "to": "external:ecc-git-workflow",
                 "type": "contains", "source": "marketplace"},
                {"from": "plugin:everything-claude-code/ecc", "to": "external:ecc-go-build-resolver",
                 "type": "contains", "source": "marketplace"},
            ],
        )

    def test_no_edge_when_owner_not_installed(self):
        static_nodes = [{"id": "external:superpowers-systematic-debugging", "kind": "external",
                         "thirdPartyPlugin": "claude-plugins-official/superpowers"}]
        self.assertEqual(blm.build_owner_edges(static_nodes, []), [])

    def test_ignores_owner_field_on_non_external_nodes(self):
        static_nodes = [{"id": "skill:x/y", "kind": "skill", "thirdPartyPlugin": "m/p"}]
        third_party = [{"id": "plugin:m/p", "kind": "plugin"}]
        self.assertEqual(blm.build_owner_edges(static_nodes, third_party), [])

    def test_every_third_party_named_external_declares_an_owner(self):
        """ecc-*/superpowers-* catalog externals must carry an owner, or they float."""
        catalog = json.loads(CATALOG.read_text())
        missing = [
            n["id"] for n in catalog["nodes"]
            if n["kind"] == "external"
            and n["id"].startswith(("external:ecc-", "external:superpowers-"))
            and not n.get("thirdPartyPlugin")
        ]
        self.assertEqual(missing, [])

    def test_owner_field_survives_into_static_map(self):
        static = json.loads(STATIC_MAP.read_text())
        owners = {n["id"]: n.get("thirdPartyPlugin") for n in static["nodes"] if n["kind"] == "external"}
        self.assertEqual(owners.get("external:ecc-git-workflow"), "everything-claude-code/ecc")


if __name__ == "__main__":
    unittest.main()
