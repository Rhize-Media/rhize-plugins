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


def _stub_runtime(tmp_path: Path, help_exit: int) -> tuple[Path, Path]:
    """A stub rhize-skill (plus the python3 sibling the launcher version-checks) that logs argv."""
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "invocations.log"
    stub = bin_dir / "rhize-skill"
    stub.write_text(
        "#!/bin/sh\n"
        f'if [ "$2" = "--help" ]; then exit {help_exit}; fi\n'
        f'echo "$*" >> "{log}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "python3").write_text("#!/bin/sh\necho 0.2.0\n", encoding="utf-8")
    for path in bin_dir.iterdir():
        os.chmod(path, 0o755)
    return stub, log


def _run_launcher(tmp_path: Path, stub: Path, *args: str):
    import os
    import subprocess

    env = {**os.environ, "RHIZE_SKILL_BIN": str(stub), "HOME": str(tmp_path)}
    return subprocess.run(
        ["sh", str(PLUGIN / "skills/functionize/scripts/functionize.sh"), *args],
        capture_output=True, text=True, env=env,
    )


def test_functionize_launcher_recipes_mode_maps_to_functionize_recipes(tmp_path) -> None:
    launcher_text = (PLUGIN / "skills/functionize/scripts/functionize.sh").read_text(encoding="utf-8")
    assert 'command_name="functionize-recipes"' in launcher_text
    stub, log = _stub_runtime(tmp_path, help_exit=0)

    result = _run_launcher(tmp_path, stub, "recipes", "--since", "7d", "--json")

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").strip() == "functionize-recipes --since 7d --json"


def test_functionize_launcher_recipes_mode_refuses_an_older_runtime(tmp_path) -> None:
    stub, log = _stub_runtime(tmp_path, help_exit=2)

    result = _run_launcher(tmp_path, stub, "recipes", "--json")

    assert result.returncode == 78
    assert "does not support functionize-recipes" in result.stderr
    assert not log.exists()
