#!/usr/bin/env python3
"""audit_machine_mcp_configs.py — machine-wide diagnostic scan for MCP secret-delivery footguns.

Extracted from the `python3 - <<'PY'` heredoc that used to live inline in
docs/mcp-secret-launcher.md ("## Detecting regressions") — see that section's
history for the incident this was written to catch: on 2026-08-19,
`~/.claude.json` held DataForSEO credentials written as literal inline values
(no `${` anywhere), and the heredoc's `${...}`-only scan reported it clean.

NOT the same tool as scripts/validate_plugin_configs.py:

  - validate_plugin_configs.py is REPO-scoped (only this repo's plugin dirs),
    runs on every version bump via `REPOSITORY_CONTRACTS` in bump_version.py,
    and is a real CI gate.
  - This script is MACHINE-WIDE: every installed plugin under
    ~/.claude/plugins, every `.mcp.json` under ~/dev-local, plus the top-level
    `mcpServers` block in ~/.claude.json. It is a manual troubleshooting tool
    (run it by hand when chasing a specific 401/403), deliberately NOT wired
    into any release gate — a false positive here should never block a bump.

Two independent checks, both restricted to `env` (stdio and HTTP transport)
and `headers` (HTTP transport) blocks of an MCP server config:

  (a) `${VAR}` references, classified stdio vs HTTP.
      Claude Code only expands `${VAR}` when the variable happens to be in
      its own process env at load time; otherwise the literal string is
      passed to the server, which then 401s with no indication it's a config
      problem (see docs/mcp-secret-launcher.md). A **stdio** server has a
      child process the mcp-secret-launcher.sh shim can wrap, so any `${VAR}`
      there is ACTIONABLE — it should have been migrated already. An
      **HTTP**-transport server (`url`/`headers`) has no child process to
      wrap, so `${VAR}` is the only mechanism available there — that's the
      documented, unfixable gap, reported informationally and never as an
      error.

  (b) Inline plaintext credentials — an `env`/`headers` key whose name looks
      credential-shaped (matched via validate_plugin_configs.py's own
      last-`_`/`-`-component logic, so `SLACK_TEAM_ID` and `KEY_FILE_PATH`
      don't false-positive) whose value contains no `${` at all. This is the
      check the original heredoc did NOT have, and its absence is what let
      the 2026-08-19 incident read as clean: a `${...}`-only scan gives a
      false all-clear on a credential written as a literal. Never prints the
      value — only the key name and its length.

Design:
  - stdio `${VAR}` -> ERROR (actionable now; every legitimate stdio env value
    is either a credential that belongs in the shim, or a non-secret literal
    — never a `${VAR}` template, per docs/mcp-secret-launcher.md's Rules).
  - HTTP `${VAR}` -> INFO (the known gap; correct as-is, not a failure).
  - inline plaintext, strong-shaped key (KEY/TOKEN/SECRET/PASSWORD/...) ->
    ERROR.
  - inline plaintext, weak-shaped key (USERNAME/LOGIN) -> WARNING.
  - Exit 0 unless at least one ERROR-severity finding is present.

Usage:
  python3 scripts/audit_machine_mcp_configs.py [--root PATH]

  --root overrides the three default machine locations with a single
  directory, globbed recursively for `**/.mcp.json` — used to point the scan
  at throwaway fixtures (e.g. /tmp) instead of real machine config.
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Reuse validate_plugin_configs.py's own credential-key-shape guard rather than
# reinventing it — it's the thing that already keeps SLACK_TEAM_ID and
# KEY_FILE_PATH from false-positiving, and it must stay in lockstep with the
# repo-scoped lint. Loaded via importlib (not a plain `import`) so this script
# still works if scripts/ is ever run from outside its own directory.
_VPC_SPEC = importlib.util.spec_from_file_location(
    "validate_plugin_configs", REPO_ROOT / "scripts" / "validate_plugin_configs.py"
)
assert _VPC_SPEC is not None and _VPC_SPEC.loader is not None
vpc = importlib.util.module_from_spec(_VPC_SPEC)
_VPC_SPEC.loader.exec_module(vpc)

VAR_REF_RE = vpc.VAR_REF_RE

# check (b): USERNAME/LOGIN are lower-severity than KEY/TOKEN/SECRET/... —
# LOGIN isn't in validate_plugin_configs.py's WEAK_SECRET_COMPONENTS, so it's
# added here rather than changing that script's behavior.
WEAK_SECRET_COMPONENTS = vpc.WEAK_SECRET_COMPONENTS | {"LOGIN"}

SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}

DEFAULT_MCP_GLOBS = [
    "~/.claude/plugins/**/.mcp.json",
    "~/dev-local/**/.mcp.json",
]
DEFAULT_SINGLE_FILES = [
    "~/.claude.json",
]


class Finding:
    def __init__(
        self,
        file: Path,
        server: str,
        pointer: str,
        kind: str,  # "stdio" | "HTTP"
        category: str,  # "var_ref" | "inline_plaintext"
        severity: str,  # "info" | "warning" | "error"
        message: str,
    ) -> None:
        self.file = file
        self.server = server
        self.pointer = pointer
        self.kind = kind
        self.category = category
        self.severity = severity
        self.message = message


def secret_key_severity(key: str) -> str | None:
    """Same shape-matching as validate_plugin_configs.py, plus LOGIN as weak."""
    last = vpc._last_component(key)
    if last in vpc.STRONG_SECRET_COMPONENTS:
        return "error"
    if last in WEAK_SECRET_COMPONENTS:
        return "warning"
    return None


# ---------- discovery ----------

def is_excluded(path: str) -> bool:
    return "/node_modules/" in path or "/test/fixtures/" in path


def discover_config_files(root: str | None) -> list[Path]:
    """Return every .mcp.json / mcpServers-holding config file to scan.

    With --root, glob `**/.mcp.json` recursively under that single directory
    (fixture testing). Without it, scan the three real machine locations.
    """
    paths: list[str] = []
    if root is not None:
        paths += glob.glob(str(Path(root).expanduser()) + "/**/.mcp.json", recursive=True)
    else:
        for pattern in DEFAULT_MCP_GLOBS:
            paths += glob.glob(str(Path(pattern).expanduser()), recursive=True)
        paths += [str(Path(p).expanduser()) for p in DEFAULT_SINGLE_FILES]

    seen: list[Path] = []
    for p in sorted(set(paths)):
        if is_excluded(p):
            continue
        fp = Path(p)
        if fp.is_file():
            seen.append(fp)
    return seen


# ---------- scanning ----------

def scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return findings

    servers = doc.get("mcpServers") if isinstance(doc, dict) else None
    if not isinstance(servers, dict):
        return findings

    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        kind = "HTTP" if ("url" in cfg or "headers" in cfg) else "stdio"

        for block in ("env", "headers"):
            values = cfg.get(block)
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                if not isinstance(value, str):
                    continue
                pointer = f"/mcpServers/{name}/{block}/{key}"

                if VAR_REF_RE.search(value):
                    # check (a): ${VAR} reference.
                    if kind == "stdio":
                        findings.append(Finding(
                            file=path, server=name, pointer=pointer, kind=kind,
                            category="var_ref", severity="error",
                            message=(
                                f"{block}.{key} uses \"${{...}}\" in a stdio server's "
                                "config — actionable. Migrate to mcp-secret-launcher.sh "
                                "(see docs/mcp-secret-launcher.md) or, if this is a "
                                "non-secret setting, replace it with a plain literal."
                            ),
                        ))
                    else:
                        findings.append(Finding(
                            file=path, server=name, pointer=pointer, kind=kind,
                            category="var_ref", severity="info",
                            message=(
                                f"{block}.{key} uses \"${{...}}\" in an HTTP-transport "
                                "server's config — this is the documented, unfixable gap "
                                "(no child process for the launcher to wrap). Not a "
                                "failure; track it, don't paper over it."
                            ),
                        ))
                else:
                    # check (b): inline plaintext, no ${ at all.
                    if not value:
                        continue  # empty value carries no credential material
                    sev = secret_key_severity(key)
                    if sev is not None:
                        findings.append(Finding(
                            file=path, server=name, pointer=pointer, kind=kind,
                            category="inline_plaintext", severity=sev,
                            message=(
                                f"{block}.{key} looks credential-shaped and holds an "
                                f"inline plaintext value ({len(value)} chars, no \"${{\") "
                                "instead of a Keychain-backed reference. This is exactly "
                                "the case a \"${VAR}\"-only scan misses (2026-08-19: "
                                "DataForSEO creds inline in ~/.claude.json read as clean)."
                            ),
                        ))
    return findings


def collect_findings(root: str | None) -> list[Finding]:
    findings: list[Finding] = []
    for path in discover_config_files(root):
        findings.extend(scan_file(path))
    return findings


# ---------- reporting ----------

def format_report(findings: list[Finding]) -> tuple[str, int]:
    lines: list[str] = []
    ordered = sorted(
        findings,
        key=lambda f: (-SEVERITY_RANK[f.severity], str(f.file), f.pointer),
    )
    for f in ordered:
        lines.append(f"[{f.severity.upper()}] {f.kind:5} {f.server:24} {f.file}")
        lines.append(f"  path:  {f.pointer}")
        lines.append(f"  issue: {f.message}")
        lines.append("")

    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    infos = sum(1 for f in findings if f.severity == "info")

    if not findings:
        lines.append("No issues found.")
    else:
        lines.append(f"{errors} error(s), {warnings} warning(s), {infos} info")

    exit_code = 1 if errors else 0
    return "\n".join(lines), exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Machine-wide diagnostic scan for MCP secret-delivery footguns "
            "(${VAR} in stdio env, inline plaintext credentials). Not a CI gate."
        ),
    )
    parser.add_argument(
        "--root", type=str, default=None,
        help=(
            "scan only this directory (globbed recursively for **/.mcp.json) "
            "instead of the real machine locations — for fixture testing"
        ),
    )
    args = parser.parse_args(argv)

    findings = collect_findings(args.root)
    report, exit_code = format_report(findings)
    print(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
