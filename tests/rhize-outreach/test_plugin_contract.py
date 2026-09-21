import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "rhize-outreach"
SCRIPT = PLUGIN / "scripts" / "outreach_setup.py"


def test_offline_evaluation_passes():
    result = subprocess.run([sys.executable, str(ROOT / "evals" / "rhize-outreach" / "run_evals.py")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["outcome"] == "PASS"
    assert report["checks"] == 12


def test_handoff_contains_names_but_no_values(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run([sys.executable, str(SCRIPT), "handoff"], env={**os.environ, "HOME": str(home)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    email = Path(output["email"]).read_text()
    assert "SUPABASE_ANON_KEY" in email
    assert "service-role key" in email
    assert "eyJ" not in email and "ghp_" not in email and "sntrys_" not in email


def test_doctor_is_redacted_when_unconfigured(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run([sys.executable, str(SCRIPT), "doctor", "--json"], env={**os.environ, "HOME": str(home)}, capture_output=True, text=True)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["outcome"] == "degraded"
    assert all(isinstance(value, bool) for value in report["secrets"].values())


def test_setup_pins_the_released_portable_runtime():
    manifest = json.loads((PLUGIN / "setup" / "manifest.json").read_text())
    runtime = next(item for item in manifest["dependencies"] if item["name"] == "rhize-outreach runtime")
    assert runtime["pin"] == "5104082e2e17ac8663a20f165e6247485927e4cc"
