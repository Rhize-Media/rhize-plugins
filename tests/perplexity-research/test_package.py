import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("package", ROOT / "scripts/build_perplexity_plugin.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_complete_snapshot_without_credential_content(tmp_path):
    reference = tmp_path / "authorization.txt"
    reference.write_text("private authorization text stays outside the package")
    reference.chmod(0o600)
    destination = tmp_path / "snapshot"
    result = package.build(destination, reference)
    plugin = destination / "plugins/perplexity-research"
    assert result["plugin"] == "perplexity-research@perplexity-local"
    catalog = json.loads((destination / ".agents/plugins/marketplace.json").read_text())
    assert catalog["plugins"][0]["source"]["path"] == "./plugins/perplexity-research"
    manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
    server = manifest["mcpServers"]["perplexity_research"]
    assert server["cwd"] == "." and Path(server["command"]).is_absolute()
    assert server["args"][-1] == str(reference)
    for name in package.RUNTIME:
        assert (plugin / "scripts" / name).read_bytes() == (ROOT / "scripts" / name).read_bytes()
    hashes = json.loads((plugin / "snapshot.json").read_text())
    for path, digest in hashes.items():
        data = (plugin / path).read_bytes()
        assert package.hashlib.sha256(data).hexdigest() == digest
        assert reference.read_bytes() not in data
    with pytest.raises(FileExistsError):
        package.build(destination, reference)
    assert (plugin / "snapshot.json").exists()


@pytest.mark.parametrize("kind", ["shared", "symlink", "hardlink"])
def test_reject_unsafe_reference_before_writing(tmp_path, kind):
    reference = tmp_path / "reference"
    reference.write_text("authorization")
    reference.chmod(0o600)
    if kind == "shared":
        reference.chmod(0o644)
    elif kind == "symlink":
        link = tmp_path / "link"
        link.symlink_to(reference)
        reference = link
    else:
        (tmp_path / "link").hardlink_to(reference)
    with pytest.raises(ValueError):
        package.build(tmp_path / "snapshot", reference)
    assert not (tmp_path / "snapshot").exists()


@pytest.mark.parametrize("stage", ["dependency", "copy"])
def test_failure_leaves_no_partial_snapshot(tmp_path, monkeypatch, stage):
    reference = tmp_path / "reference"
    reference.write_text("authorization")
    reference.chmod(0o600)
    def fail(*args, **kwargs):
        raise OSError("fixture failure")
    if stage == "dependency":
        monkeypatch.setattr(package.subprocess, "run", fail)
    else:
        monkeypatch.setattr(package.shutil, "copyfile", fail)
    with pytest.raises(OSError):
        package.build(tmp_path / "snapshot", reference)
    assert not (tmp_path / "snapshot").exists()
    assert reference.read_text() == "authorization"
