#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "rhize-outreach"


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)


def main() -> None:
    claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    check(claude["name"] == codex["name"] == "rhize-outreach", "manifest name drift")
    check(claude["version"] == codex["version"], "manifest version drift")
    setup = json.loads((PLUGIN / "setup" / "manifest.json").read_text())
    serialized = json.dumps(setup).lower()
    check("service_role" not in serialized and "database_password" not in serialized, "operator manifest requests privileged secrets")
    manifest = json.loads((PLUGIN / "assets" / "templates" / "manifest.json").read_text())
    check(len(manifest["templates"]) >= 4, "reviewed template package incomplete")
    for item in manifest["templates"]:
        path = PLUGIN / "assets" / "templates" / item["path"]
        check(path.is_file(), f"missing template {item['path']}")
        check(hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], f"template digest mismatch {item['path']}")
    setup_html = (PLUGIN / "assets" / "setup-wizard.html").read_text()
    check("if(pending)return" in setup_html and "finally{pending=false" in setup_html, "async controls lack handler re-entry guard/finally reset")
    check("service-role" in setup_html and "not operator inputs" in setup_html, "privileged-secret boundary missing from wizard")
    handoff_source = (PLUGIN / "scripts" / "outreach_setup.py").read_text()
    check("Do not reply with them" in handoff_source and "service-role key" in handoff_source, "handoff secret boundary missing")
    check("plugin-compatibility.json" in handoff_source and "templateManifestSha256" in handoff_source, "runtime/template compatibility check missing")
    check("/api/dry-run" in handoff_source and "externalEffects" in handoff_source, "no-send dry run missing")
    print(json.dumps({"schema": "rhize-outreach-eval-v1", "outcome": "PASS", "checks": 12}))


if __name__ == "__main__":
    main()
