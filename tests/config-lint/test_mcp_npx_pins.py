"""test_mcp_npx_pins.py — bundled MCP servers launched through npx must pin an
exact version.

An unpinned `npx <pkg>` (or `@latest`) silently picks up whatever upstream
publishes next, on every teammate's machine at a different moment. MCP's
2026-07-28 revision removed the `initialize` handshake, so an upstream release
that goes modern-only would break a plugin's server with no change in this
repo. Pinning makes such an upgrade a reviewed diff.

pytest-based, matching tests/config-lint/test_shared_shims.py's style.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXACT_SPEC = re.compile(r"^(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*@\d+\.\d+\.\d+([-+][\w.-]+)?$", re.IGNORECASE)
NPX_VALUE_FLAGS = {"-p", "--package", "-c", "--call"}


def npx_package_specs(server: dict) -> list[str]:
    """Package specs npx would fetch for one server entry: every `-p/--package`
    value, else the first positional argument after `npx`."""
    argv = [server.get("command", ""), *server.get("args", [])]
    if "npx" not in argv:
        return []
    rest = argv[argv.index("npx") + 1:]
    specs, i = [], 0
    while i < len(rest):
        arg = rest[i]
        if arg in ("-p", "--package"):
            specs.append(rest[i + 1] if i + 1 < len(rest) else "")
            i += 2
            continue
        if arg in NPX_VALUE_FLAGS:
            i += 2
            continue
        if arg.startswith("-"):
            i += 1
            continue
        return specs or [arg]
    return specs


def unpinned(server: dict) -> list[str]:
    return [spec for spec in npx_package_specs(server) if not EXACT_SPEC.match(spec)]


def _tracked_mcp_configs() -> list[Path]:
    result = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files", "*.mcp.json", ".mcp.json"],
                            capture_output=True, text=True, check=True)
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


CONFIGS = _tracked_mcp_configs()


def test_plugin_mcp_configs_exist() -> None:
    assert CONFIGS, "no tracked .mcp.json found; the glob or repo layout changed"


@pytest.mark.parametrize("config", CONFIGS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_npx_servers_pin_exact_versions(config: Path) -> None:
    servers = json.loads(config.read_text())["mcpServers"]
    offenders = {name: unpinned(cfg) for name, cfg in servers.items() if unpinned(cfg)}
    assert not offenders, f"{config.relative_to(REPO_ROOT)}: pin an exact @x.y.z version: {offenders}"


@pytest.mark.parametrize(
    ("args", "bad"),
    [
        (["--", "npx", "dataforseo-mcp-server"], ["dataforseo-mcp-server"]),
        (["--", "npx", "-y", "pkg@latest"], ["pkg@latest"]),
        (["--", "npx", "-y", "pkg@^1.2.0"], ["pkg@^1.2.0"]),
        (["--", "npx", "pkg@1.2.3"], []),
        (["--", "npx", "-y", "@scope/pkg@0.8.2"], []),
        (["--", "npx", "-p", "pkg@1.0.0", "bin-name"], []),
        (["--", "npx", "-p", "pkg", "bin-name"], ["pkg"]),
        (["serve"], []),
    ],
)
def test_spec_detection(args: list[str], bad: list[str]) -> None:
    assert unpinned({"command": "launcher.sh", "args": args}) == bad
