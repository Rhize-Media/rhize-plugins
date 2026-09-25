import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "rhize-outreach"
SCRIPT = PLUGIN / "scripts" / "rhize-outreach.mjs"


def test_offline_evaluation_passes():
    result = subprocess.run([sys.executable, str(ROOT / "evals" / "rhize-outreach" / "run_evals.py")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["outcome"] == "PASS"
    assert report["checks"] == 5


def test_setup_wizard_does_not_collect_provider_credentials():
    html = (PLUGIN / "assets" / "setup-wizard.html").read_text()
    assert "SUPABASE_ANON_KEY" not in html
    assert "GHL_ACCESS_TOKEN" not in html
    assert "Install pinned workflow" in html
    assert "escapeHTML" in html


def test_doctor_reports_local_setup_without_secrets(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    node = subprocess.check_output(["node", "-p", "process.execPath"], text=True).strip()
    result = subprocess.run([node, str(SCRIPT), "doctor", "--json"], env={**os.environ, "HOME": str(home)}, capture_output=True, text=True)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "blocked"
    assert "secrets" not in report

def test_setup_pins_the_released_portable_runtime():
    manifest = json.loads((PLUGIN / "setup" / "manifest.json").read_text())
    runtime = next(item for item in manifest["dependencies"] if item["name"] == "rhize-outreach runtime")
    assert runtime["pin"] == "c8778dda0bba65380bee5d8a7bf99e214a8b22fa"
