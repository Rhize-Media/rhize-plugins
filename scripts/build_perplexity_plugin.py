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
DESCRIPTION = "Local Perplexity subscription Search and Research with durable jobs and Keychain session setup."
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
        (plugin / "scripts").mkdir(parents=True, mode=0o700)
        (plugin / "docs/research").mkdir(parents=True, mode=0o700)
        (plugin / ".codex-plugin").mkdir(mode=0o700)
        (destination / ".agents/plugins").mkdir(parents=True, mode=0o700)
        for name in RUNTIME:
            shutil.copyfile(ROOT / "scripts" / name, plugin / "scripts" / name)
        for name in ("perplexity-local-bridge.md", "perplexity-pro-feasibility.md", "perplexity-upstream-LICENSE.txt"):
            shutil.copyfile(ROOT / "docs/research" / name, plugin / "docs/research" / name)
        (plugin / "README.md").write_text(
            "# Perplexity Research\n\n" + DESCRIPTION + "\n\n"
            "See [GUIDE.md](GUIDE.md) for setup, all eleven MCP tools, installation and limits.\n"
            "Queries consume subscription allowance; no automatic retries or password login.\n")
        (plugin / "GUIDE.md").write_text(
            "# Usage guide\n\nSee the [complete bridge guide](docs/research/perplexity-local-bridge.md) "
            "for installation, native session refresh, all MCP tools and verification limits.\n")
        (plugin / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 0.1.0\n\nInitial local snapshot: Search/Research, durable jobs, "
            "recovery, exports and native encrypted browser-to-Keychain setup. "
            "Accepts Codex discovery progress metadata. Search thread reads request the answer "
            "and explicit citation rows together while retaining strict citation validation.\n")
        manifest = {"name": NAME, "version": "0.1.0", "description": DESCRIPTION,
                    "author": {"name": "Rhize Media"}, "mcpServers": {
                        "perplexity_research": {"command": python, "cwd": ".",
                            "args": ["-I", "scripts/perplexity_research_mcp.py",
                                     "--permission-reference", str(reference)]}}}
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
