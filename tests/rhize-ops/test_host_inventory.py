"""Real config/cache fixtures for static Codex inventory; no host/provider calls."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "rhize-ops/scripts/host_inventory.py"
SPEC = importlib.util.spec_from_file_location("host_inventory", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def setup(tmp_path):
    config = tmp_path / ".codex/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('[plugins."ops@rhize"]\nenabled = true\n[plugins."unused@rhize"]\nenabled = false\n')
    install = tmp_path / ".codex/plugins/cache/rhize/ops/1.0.0"
    (install / ".codex-plugin").mkdir(parents=True)
    (install / ".codex-plugin/plugin.json").write_text(json.dumps({"name": "ops", "version": "1.0.0", "skills": "./skills/"}))
    (install / "skills/test").mkdir(parents=True)
    (install / "skills/test/SKILL.md").write_text("---\nname: test\n---\n")
    return install


def test_config_and_manifest_are_not_runtime_proof(tmp_path):
    setup(tmp_path)
    result = module.inventory(tmp_path)
    assert result["complete"]
    installed, disabled = result["plugins"]
    assert installed["status"] == "installed"
    assert len(installed["skillDirs"]) == 1
    assert installed["runtimeVerified"] is False
    assert disabled["status"] == "disabled"


def test_multiple_versions_and_project_config_are_explicitly_unknown(tmp_path):
    install = setup(tmp_path)
    other = install.parent / "2.0.0/.codex-plugin"
    other.mkdir(parents=True)
    (other / "plugin.json").write_text('{"name":"ops"}')
    result = module.inventory(tmp_path, tmp_path)
    assert not result["complete"]
    assert result["plugins"][0]["status"] == "unknown"
    assert "2 cached versions" in result["plugins"][0]["reason"]
    assert any("Project Codex config" in n for n in result["notices"])


def test_escape_and_missing_declared_directory_are_not_empty_success(tmp_path):
    install = setup(tmp_path)
    (install / "skills/test/SKILL.md").unlink()
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    (install / "skills/test/SKILL.md").symlink_to(outside)
    result = module.inventory(tmp_path)
    assert not result["complete"]
    assert "escapes" in result["plugins"][0]["reason"]
    (install / ".codex-plugin/plugin.json").write_text('{"name":"ops","skills":"./missing"}')
    assert "missing" in module.inventory(tmp_path)["plugins"][0]["reason"]


def test_real_toml_parser_rejects_malformed_configuration(tmp_path):
    setup(tmp_path)
    (tmp_path / ".codex/config.toml").write_text('[plugins."ops@rhize"\nenabled = true')
    with pytest.raises(ValueError):
        module.inventory(tmp_path)
