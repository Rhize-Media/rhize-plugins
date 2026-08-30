import json
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]


def test_codex_manifest_discovers_the_shared_skill() -> None:
    claude = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    codex = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))

    assert codex["name"] == PLUGIN.name == claude["name"]
    assert codex["version"] == claude["version"]
    assert codex["skills"] == "./skills/"
    assert (PLUGIN / "skills/procedural-memory/agents/openai.yaml").is_file()


def test_shared_skill_uses_a_self_relative_launcher() -> None:
    skill = (PLUGIN / "skills/procedural-memory/SKILL.md").read_text(encoding="utf-8")
    launcher = PLUGIN / "skills/procedural-memory/scripts/procedural-memory.sh"

    assert "scripts/procedural-memory.sh" in skill
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh" not in skill
    assert launcher.is_file()
    assert "scripts/rhize-skill-launcher.sh" in launcher.read_text(encoding="utf-8")
