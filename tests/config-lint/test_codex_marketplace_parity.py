"""The Codex catalog must expose every published Rhize marketplace plugin."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_codex_catalog_matches_claude_catalog() -> None:
    claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert codex["name"] == claude["name"]
    expected = {entry["name"]: entry["source"] for entry in claude["plugins"]}
    actual = {entry["name"]: entry["source"] for entry in codex["plugins"]}
    assert len(actual) == len(codex["plugins"])
    assert actual == {
        name: {"source": "local", "path": source}
        for name, source in expected.items()
    }
    for source in expected.values():
        assert (ROOT / source).is_dir()
