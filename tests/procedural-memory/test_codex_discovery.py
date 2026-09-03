import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "procedural-memory"


def test_codex_manifest_discovers_the_shared_skill() -> None:
    claude = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    codex = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))

    assert codex["name"] == PLUGIN.name == claude["name"]
    assert codex["version"] == claude["version"]
    assert codex["skills"] == "./skills/"
    assert (PLUGIN / "skills/procedural-memory/agents/openai.yaml").is_file()
    assert (PLUGIN / "skills/functionize/agents/openai.yaml").is_file()


def test_shared_skill_uses_a_self_relative_launcher() -> None:
    skill = (PLUGIN / "skills/procedural-memory/SKILL.md").read_text(encoding="utf-8")
    launcher = PLUGIN / "skills/procedural-memory/scripts/procedural-memory.sh"

    assert "scripts/procedural-memory.sh" in skill
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/rhize-skill-launcher.sh" not in skill
    assert launcher.is_file()
    assert "scripts/rhize-skill-launcher.sh" in launcher.read_text(encoding="utf-8")


def test_functionize_skill_has_a_compile_only_launcher() -> None:
    skill = (PLUGIN / "skills/functionize/SKILL.md").read_text(encoding="utf-8")
    launcher = PLUGIN / "skills/functionize/scripts/functionize.sh"

    assert "scripts/functionize.sh" in skill
    assert launcher.is_file()
    launcher_text = launcher.read_text(encoding="utf-8")
    for allowed_mode in ("mine", "generate", "review"):
        assert allowed_mode in launcher_text
    for forbidden_command in ("promote", "approve", "verify", "run"):
        assert f'"{forbidden_command}"' not in launcher_text
