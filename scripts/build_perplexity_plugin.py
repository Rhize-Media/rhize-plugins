#!/usr/bin/env python3
"""Build a new, self-contained local Codex marketplace; never install or query."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NAME = "perplexity-research"
MARKETPLACE = "perplexity-local"
RUNTIME = ("perplexity_research.py", "perplexity_research_mcp.py", "perplexity_session_transfer.mjs")


def build(destination, permission_reference):
    reference = permission_reference.absolute()
    info = reference.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid() or info.st_nlink != 1):
        raise ValueError("authorization reference must be an owned, unshared mode-600 regular file")
    python = str(Path(sys.executable).resolve())
    subprocess.run([python, "-I", "-c", "import cryptography"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    destination.mkdir(mode=0o700)  # Refuse existing snapshots, including symlinks.
    try:
        plugin = destination / "plugins" / NAME
        files = ["scripts/" + name for name in RUNTIME] + [
            "scripts/launch-mcp.sh", "scripts/perplexity_config.py", "config/defaults.json", "config/schema.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
            ".mcp.json", "README.md", "GUIDE.md", "CHANGELOG.md", "setup/manifest.json",
            "commands/setup.md", "skills/SOURCES.md", "skills/perplexity-research/SKILL.md",
            "docs/perplexity-local-bridge.md", "docs/perplexity-pro-feasibility.md",
            "docs/perplexity-upstream-LICENSE.txt",
        ]
        for name in files:
            target = plugin / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(ROOT / NAME / name, target)
        (destination / ".agents/plugins").mkdir(parents=True, mode=0o700)
        manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
        manifest["mcpServers"] = {"perplexity_research": {"command": python, "cwd": ".",
            "args": ["-I", "scripts/perplexity_research_mcp.py",
                     "--permission-reference", str(reference)]}}
        marketplace = {"name": MARKETPLACE, "interface": {"displayName": "Perplexity Local"},
                       "plugins": [{"name": NAME, "source": {"source": "local", "path": "./plugins/" + NAME},
                                    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                                    "category": "Productivity"}]}
        for path, value in ((plugin / ".codex-plugin/plugin.json", manifest),
                            (destination / ".agents/plugins/marketplace.json", marketplace)):
            path.write_text(json.dumps(value, indent=2) + "\n")
        hashes = {str(path.relative_to(plugin)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted(plugin.rglob("*")) if path.is_file()}
        (plugin / "snapshot.json").write_text(json.dumps(hashes, indent=2) + "\n")
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {"marketplace": str(destination.absolute()), "plugin": NAME + "@" + MARKETPLACE}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New directory beneath an existing private parent")
    parser.add_argument("--permission-reference", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(build(args.destination, args.permission_reference)))
    except (OSError, ValueError, subprocess.SubprocessError):
        parser.exit(2, "Build failed: check new destination, private authorization reference and Python cryptography.\n")
