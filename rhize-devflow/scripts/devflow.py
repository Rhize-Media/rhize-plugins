#!/usr/bin/env python3
"""devflow.py — deterministic doctor and evidence CLI for rhize-devflow.

Stdlib-only. Never executes package scripts, Markdown-derived commands, or shell text
extracted from prose/reports. Never initializes a CodeGraph index. Read-only against every
target repository/plugin it inspects.

Usage:
    python3 devflow.py doctor [--json] [--plugin-root PATH]
    python3 devflow.py evidence [--json] [--repo PATH] [--base REF]

Exit codes (both subcommands):
    0 = healthy — no finding with severity other than "info"
    1 = findings — at least one "error" or "warning" finding was recorded
    2 = usage or internal error (bad path, not a git repository, argparse failure, ...)

Path resolution
----------------
`doctor` defaults `--plugin-root` to the directory two levels above this file
(``Path(__file__).resolve().parent.parent``), i.e. the `rhize-devflow/` plugin root. That
resolution is relative to the script's own location, so it works identically whether this
file is read from the source checkout (`rhize-plugins/rhize-devflow/scripts/devflow.py`) or
from an installed plugin cache (e.g.
`~/.claude/plugins/marketplaces/rhize-plugins/rhize-devflow/scripts/devflow.py`) — both are
git clones that preserve the same `scripts/` position under the plugin root. Pass
`--plugin-root` to point at any other plugin directory (used by the test suite against
fixture plugin roots).

`evidence` defaults `--repo` to the current working directory.

Redaction
---------
JSON output never contains raw environment variable values. Paths inside the inspected
repo/plugin are emitted relative to that root; the root itself (the explicitly inspected
repo or plugin) may be named. No other absolute filesystem path is emitted in `--json`
output.

Doctor JSON shape
------------------
`schemas/devflow-evidence-v1.schema.json` documents the `evidence` subcommand's output
contract. `doctor`'s output is plugin-introspection, not repo evidence, and is documented
here instead:

    {
      "schema_version": "devflow-doctor-v1",
      "plugin_root": "<absolute path to the inspected plugin root>",
      "generated_at": "<ISO-8601 UTC timestamp>",
      "findings": [
        {"id": str, "severity": "error"|"warning"|"info", "message": str, "path": str|null}
      ],
      "capabilities": {
        "<capability-name>": {
          "status": "ok"|"degraded",
          "dependency": "<dependency name from setup/manifest.json>",
          "kind": "mcp"|"cli",
          "detail": str
        }
      },
      "healthy": bool
    }

`healthy` is true iff every finding has severity "info" — capability degradation is reported
independently in `capabilities` and never affects `healthy`. Most stale-token findings
(historical `zen`/`serena`/`graphiti` mentions) are informational only; a live-instruction
defect (`legacy-alias`, `/path/to/skill`) is reported at "warning" severity and does block
`healthy`, since a user copying that text would run something stale.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib
except ImportError:  # pragma: no cover — stdlib since Python 3.11; guarded for portability.
    tomllib = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_finding(
    finding_id: str, severity: str, message: str, path: Optional[str] = None
) -> dict:
    assert severity in ("error", "warning", "info")
    return {"id": finding_id, "severity": severity, "message": message, "path": path}


def is_healthy(findings: list[dict]) -> bool:
    return not any(f["severity"] != "info" for f in findings)


def rel(root: Path, path: Path) -> str:
    """Path relative to `root` for use in JSON output; falls back to the raw string only
    if `path` somehow isn't under `root` (should not happen for paths this CLI collects)."""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def default_plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# doctor — plugin/install health
# ---------------------------------------------------------------------------

_ASSET_PREFIXES = (
    "scripts/",
    "templates/",
    "template/",
    "reference/",
    "references/",
    "config/",
    "sub-skills/",
    "hooks/",
)
_ASSET_PATTERN = re.compile(
    r"`((?:%s)[A-Za-z0-9_\-./]+\.[A-Za-z0-9]+)`" % "|".join(re.escape(p) for p in _ASSET_PREFIXES)
)

# `docs/<name>.md` references are checked separately from `_ASSET_PATTERN` above: unlike
# scripts/templates/etc. (which are scoped per-skill by `_asset_base_dir`), `docs/` always
# lives at the plugin root, and a doc is as often linked as `[text](docs/x.md)` as it is
# backticked — so this pattern accepts either form.
_DOCS_LINK_PATTERN = re.compile(r"`(docs/[A-Za-z0-9_\-./]+\.md)`|\]\((docs/[A-Za-z0-9_\-./]+\.md)\)")

_STALE_TOKEN_PATTERNS: dict[str, re.Pattern] = {
    "/path/to/skill": re.compile(re.escape("/path/to/skill")),
    "zen": re.compile(r"(?i)\bzen\b|zen_memory|mcp__zen__"),
    "serena": re.compile(r"(?i)\bserena\b|mcp__serena__"),
    "graphiti": re.compile(r"(?i)\bgraphiti\b"),
    "legacy-alias": re.compile(
        r"@(analyze-mutations|check-mutation|fix-mutations|browser-debug|browser-help|"
        r"browser-perf|browser-test)\b"
    ),
}

# legacy-alias and /path/to/skill are live-instruction defects (a user copying the text
# would run something stale) — always reported at warning severity, blocking `healthy`.
# zen/serena/graphiti are historical-reference mentions only — info severity.
_STALE_TOKEN_WARNING_NAMES = {"legacy-alias", "/path/to/skill"}

# Lines that legitimately still contain a legacy `@alias` and must not trip the scanner:
# (1) ANALYSIS_TRIGGERS-style compat-matcher array entries — bare quoted literals used to
# detect old-style invocations so they still work, not instructions telling anyone to run
# one; and (2) "(formerly @alias)" annotations that intentionally document the rename.
_LEGACY_ALIAS_ARRAY_LITERAL = re.compile(r'^"@[\w-]+"\s*,?\s*$')


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _markdown_files_to_scan(plugin_root: Path) -> list[Path]:
    files: list[Path] = []
    commands_dir = plugin_root / "commands"
    if commands_dir.is_dir():
        files += sorted(commands_dir.glob("*.md"))
    agents_dir = plugin_root / "agents"
    if agents_dir.is_dir():
        files += sorted(agents_dir.glob("*.md"))
    skills_dir = plugin_root / "skills"
    if skills_dir.is_dir():
        for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            skill_md = skill_dir / "SKILL.md"
            if skill_md.is_file():
                files.append(skill_md)
            skill_cmds = skill_dir / "commands"
            if skill_cmds.is_dir():
                files += sorted(skill_cmds.glob("*.md"))
    return files


def _asset_base_dir(md_path: Path, plugin_root: Path) -> Path:
    skills_root = plugin_root / "skills"
    try:
        rel_to_skills = md_path.relative_to(skills_root)
        return skills_root / rel_to_skills.parts[0]
    except ValueError:
        return plugin_root


def _check_manifest(
    path: Path, required: bool, required_keys: tuple[str, ...], findings: list[dict], plugin_root: Path
) -> None:
    if not path.is_file():
        if required:
            findings.append(
                make_finding("missing-manifest", "error", "required manifest is missing", rel(plugin_root, path))
            )
        return
    text = _read_text(path)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        findings.append(
            make_finding(
                "invalid-json-manifest",
                "error",
                f"manifest is not valid JSON: {exc}",
                rel(plugin_root, path),
            )
        )
        return
    if not isinstance(data, dict):
        findings.append(
            make_finding("invalid-manifest-shape", "error", "manifest JSON root is not an object", rel(plugin_root, path))
        )
        return
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        findings.append(
            make_finding(
                "missing-required-key",
                "error",
                f"manifest is missing required keys: {missing_keys}",
                rel(plugin_root, path),
            )
        )


def _check_commands_present(plugin_root: Path, findings: list[dict]) -> None:
    commands_dir = plugin_root / "commands"
    if not commands_dir.is_dir():
        findings.append(make_finding("no-commands-dir", "info", "no top-level commands/ directory", "commands"))
        return
    command_files = list(commands_dir.glob("*.md"))
    if not command_files:
        findings.append(
            make_finding("empty-commands-dir", "warning", "commands/ exists but contains no *.md files", "commands")
        )


def _docs_referencing_files(plugin_root: Path) -> list[Path]:
    """`commands/*.md` plus the plugin's own `README.md` — the only places a `docs/<name>.md`
    link is checked. Skill/agent Markdown is intentionally excluded here: docs/ is a
    plugin-root concept, not a per-skill one, and `_markdown_files_to_scan` already covers
    the skill-scoped assets `_ASSET_PATTERN` checks."""
    files: list[Path] = []
    commands_dir = plugin_root / "commands"
    if commands_dir.is_dir():
        files += sorted(commands_dir.glob("*.md"))
    readme = plugin_root / "README.md"
    if readme.is_file():
        files.append(readme)
    return files


def _check_referenced_assets(plugin_root: Path, findings: list[dict]) -> None:
    for md_path in _markdown_files_to_scan(plugin_root):
        base_dir = _asset_base_dir(md_path, plugin_root)
        text = _read_text(md_path)
        for match in _ASSET_PATTERN.finditer(text):
            asset_rel = match.group(1)
            if not (base_dir / asset_rel).exists():
                findings.append(
                    make_finding(
                        "missing-asset",
                        "error",
                        f"references `{asset_rel}` which does not exist under {rel(plugin_root, base_dir)}",
                        rel(plugin_root, md_path),
                    )
                )

    for md_path in _docs_referencing_files(plugin_root):
        text = _read_text(md_path)
        seen: set[str] = set()
        for match in _DOCS_LINK_PATTERN.finditer(text):
            doc_rel = match.group(1) or match.group(2)
            if doc_rel in seen:
                continue
            seen.add(doc_rel)
            if not (plugin_root / doc_rel).exists():
                findings.append(
                    make_finding(
                        "missing-asset",
                        "error",
                        f"references `{doc_rel}` which does not exist under the plugin root",
                        rel(plugin_root, md_path),
                    )
                )


def _check_python_scripts(plugin_root: Path, findings: list[dict]) -> None:
    for py_path in sorted(plugin_root.rglob("*.py")):
        try:
            py_compile.compile(str(py_path), doraise=True, quiet=1)
        except py_compile.PyCompileError as exc:
            findings.append(
                make_finding("py-compile-error", "error", str(exc.exc_value or exc), rel(plugin_root, py_path))
            )
        except (SyntaxError, ValueError) as exc:
            findings.append(make_finding("py-compile-error", "error", str(exc), rel(plugin_root, py_path)))


_SHEBANG_BASH_RE = re.compile(r"^#!.*\b(bash|sh|zsh|dash)\b")
_SHEBANG_PYTHON_RE = re.compile(r"^#!.*\bpython3?\b")


def _check_shell_hooks(plugin_root: Path, findings: list[dict]) -> None:
    """Checks every `*.sh` file's syntax by its actual interpreter (from the shebang), not
    its extension — at least one shipped hook (hooks/protect-files.sh) has a `.sh` name but
    a `#!/usr/bin/python3` shebang, so blindly running `bash -n` on it is a false positive."""
    bash = shutil.which("bash")
    bash_unavailable_reported = False
    for sh_path in sorted(plugin_root.rglob("*.sh")):
        try:
            first_line = sh_path.open("r", encoding="utf-8", errors="ignore").readline()
        except OSError:
            continue

        if _SHEBANG_PYTHON_RE.match(first_line):
            try:
                py_compile.compile(str(sh_path), doraise=True, quiet=1)
            except py_compile.PyCompileError as exc:
                findings.append(make_finding("py-compile-error", "error", str(exc.exc_value or exc), rel(plugin_root, sh_path)))
            except (SyntaxError, ValueError) as exc:
                findings.append(make_finding("py-compile-error", "error", str(exc), rel(plugin_root, sh_path)))
            continue

        if not _SHEBANG_BASH_RE.match(first_line):
            continue  # unknown interpreter — not a bash script, nothing to check here

        if bash is None:
            if not bash_unavailable_reported:
                findings.append(make_finding("bash-unavailable", "info", "no `bash` on PATH — shell hook syntax not checked", None))
                bash_unavailable_reported = True
            continue

        result = subprocess.run([bash, "-n", str(sh_path)], capture_output=True, text=True)
        if result.returncode != 0:
            findings.append(
                make_finding(
                    "bash-syntax-error",
                    "error",
                    result.stderr.strip() or "bash -n reported a syntax error",
                    rel(plugin_root, sh_path),
                )
            )


def _line_has_unexcused_stale_hit(line: str, pattern: re.Pattern, name: str) -> bool:
    if not pattern.search(line):
        return False
    if name != "legacy-alias":
        return True
    if "formerly" in line.lower():
        return False
    if _LEGACY_ALIAS_ARRAY_LITERAL.match(line.strip()):
        return False
    return True


def _stale_tokens_in_text(text: str) -> list[str]:
    lines = text.splitlines()
    hits: list[str] = []
    for name, pattern in _STALE_TOKEN_PATTERNS.items():
        if any(_line_has_unexcused_stale_hit(line, pattern, name) for line in lines):
            hits.append(name)
    return hits


def _check_stale_tokens(plugin_root: Path, findings: list[dict]) -> None:
    # This module's own source defines the stale-token patterns as literal strings (the
    # words "zen"/"serena"/"graphiti", the "/path/to/skill" placeholder, the `@alias`
    # regex) — scanning it would be a self-referential false positive, not a real defect.
    self_path = Path(__file__).resolve()
    paths = set(plugin_root.rglob("*.md")) | set(plugin_root.rglob("*.sh")) | set(plugin_root.rglob("*.py"))
    paths = {p for p in paths if p.resolve() != self_path}
    for path in sorted(paths):
        text = _read_text(path)
        for name in _stale_tokens_in_text(text):
            severity = "warning" if name in _STALE_TOKEN_WARNING_NAMES else "info"
            findings.append(
                make_finding(
                    "stale-token",
                    severity,
                    f"contains stale token/reference: {name}",
                    rel(plugin_root, path),
                )
            )


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _mcp_names_from_json_tree(node: Any) -> set[str]:
    """Recursively collect every `mcpServers` dict's keys found anywhere in a JSON tree.
    Used for repo-local `.mcp.json` and env-override files, which are small and fully
    controlled — unlike `~/.claude.json`, there's no risk of pulling in unrelated projects."""
    names: set[str] = set()

    def _walk(n: Any) -> None:
        if isinstance(n, dict):
            servers = n.get("mcpServers")
            if isinstance(servers, dict):
                names.update(servers.keys())
            for value in n.values():
                _walk(value)

    _walk(node)
    return names


def _mcp_names_from_claude_user_config(data: dict, repo_root: Path) -> set[str]:
    """Extract MCP server names from a `~/.claude.json`-shaped dict: the top-level
    `mcpServers` map plus the per-project `projects.<repo_root>.mcpServers` entry for this
    repo, if present. Deliberately does NOT walk the rest of the document (e.g. other
    projects' entries) — `~/.claude.json` carries inline MCP credentials, and only server
    NAMES for sources relevant to this repo may ever be extracted from it."""
    names: set[str] = set()
    top = data.get("mcpServers")
    if isinstance(top, dict):
        names.update(top.keys())
    projects = data.get("projects")
    if isinstance(projects, dict):
        project_entry = projects.get(str(repo_root.resolve()))
        if isinstance(project_entry, dict):
            project_servers = project_entry.get("mcpServers")
            if isinstance(project_servers, dict):
                names.update(project_servers.keys())
    return names


def _mcp_names_from_codex_config(data: dict) -> set[str]:
    """Extract MCP server names from a `~/.codex/config.toml`-shaped dict: the top-level
    `mcp_servers` table only."""
    servers = data.get("mcp_servers")
    if isinstance(servers, dict):
        return set(servers.keys())
    return set()


def _configured_mcp_server_names(plugin_root: Path) -> dict[str, set[str]]:
    """Best-effort, deterministic-for-tests mapping of {server_name: {source_categories}}
    this environment has configured. Controlled entirely by explicit config files so results
    never depend on machine-specific ambient state unless the caller opts in via env override.

    Default sources, in priority order, when DEVFLOW_MCP_CONFIG_PATHS is unset:
      (a) repo-local `.mcp.json`                    -> source "repo"
      (b) `~/.claude.json`                           -> source "claude-user" (top-level
          `mcpServers` plus `projects.<repo path>.mcpServers` for this repo)
      (c) `~/.codex/config.toml`                     -> source "codex-user" (`mcp_servers`
          table, best-effort — missing file, missing `tomllib`, or a parse error is skipped
          silently, never raised)
    Setting DEVFLOW_MCP_CONFIG_PATHS replaces ALL of the above with the given
    os.pathsep-separated JSON file list (source "override") — existing semantics unchanged.

    Only server NAMES are ever extracted from any source — never configs/values. Read or
    parse errors on any individual source are treated as that source being absent."""
    result: dict[str, set[str]] = {}

    def add(names: set[str], source: str) -> None:
        for name in names:
            result.setdefault(name, set()).add(source)

    override = os.environ.get("DEVFLOW_MCP_CONFIG_PATHS")
    if override:
        for raw_path in override.split(os.pathsep):
            if not raw_path:
                continue
            try:
                path = Path(raw_path)
                if path.is_file():
                    add(_mcp_names_from_json_tree(json.loads(_read_text(path))), "override")
            except (json.JSONDecodeError, OSError):
                continue
        return result

    # (a) repo-local .mcp.json
    try:
        repo_mcp_json = plugin_root.parent / ".mcp.json"
        if repo_mcp_json.is_file():
            add(_mcp_names_from_json_tree(json.loads(_read_text(repo_mcp_json))), "repo")
    except (json.JSONDecodeError, OSError):
        pass

    # (b) ~/.claude.json — carries inline MCP credentials; only names are ever read.
    try:
        claude_user_json = Path.home() / ".claude.json"
        if claude_user_json.is_file():
            data = json.loads(_read_text(claude_user_json))
            if isinstance(data, dict):
                add(_mcp_names_from_claude_user_config(data, plugin_root.parent), "claude-user")
    except (json.JSONDecodeError, OSError, ValueError):
        pass

    # (c) ~/.codex/config.toml — best-effort; no tomllib, missing file, or bad TOML -> skip.
    if tomllib is not None:
        try:
            codex_toml = Path.home() / ".codex" / "config.toml"
            if codex_toml.is_file():
                with codex_toml.open("rb") as fh:
                    data = tomllib.load(fh)
                add(_mcp_names_from_codex_config(data), "codex-user")
        except (tomllib.TOMLDecodeError, OSError, ValueError):
            pass

    return result


def _check_capability_dependencies(plugin_root: Path, findings: list[dict]) -> dict:
    """Returns the capabilities dict. Never appends to `findings` — missing optional
    dependencies degrade the owning capability, they never fail the plugin as a whole."""
    capabilities: dict[str, dict] = {}
    manifest_path = plugin_root / "setup" / "manifest.json"
    if not manifest_path.is_file():
        return capabilities
    try:
        data = json.loads(_read_text(manifest_path))
    except json.JSONDecodeError:
        return capabilities
    dependencies = data.get("dependencies")
    if not isinstance(dependencies, list):
        return capabilities

    configured_mcp_names = None  # lazy — most manifests have zero mcp deps

    for dep in dependencies:
        if not isinstance(dep, dict):
            continue
        name = dep.get("name", "unknown-dependency")
        kind = dep.get("kind", "mcp")
        capability = dep.get("capability") or _slugify(name)

        if kind == "cli":
            binary = dep.get("binary") or _slugify(name).replace("-", "")
            available = shutil.which(binary) is not None
            detail = f"`{binary}` found on PATH" if available else f"`{binary}` not found on PATH"
        else:
            if configured_mcp_names is None:
                configured_mcp_names = _configured_mcp_server_names(plugin_root)
            matched_sources: set[str] = set()
            for configured, sources in configured_mcp_names.items():
                if _slugify(name) in _slugify(configured) or _slugify(configured) in _slugify(name):
                    matched_sources.update(sources)
            available = bool(matched_sources)
            if available:
                detail = "found in configured mcpServers (source: " + ", ".join(sorted(matched_sources)) + ")"
            else:
                detail = "not found in any configured mcpServers"

        capabilities[capability] = {
            "status": "ok" if available else "degraded",
            "dependency": name,
            "kind": kind,
            "detail": detail,
        }
    return capabilities


def run_doctor(plugin_root: Path, as_json: bool) -> int:
    if not plugin_root.is_dir():
        print(f"ERROR: --plugin-root does not exist or is not a directory: {plugin_root}", file=sys.stderr)
        return 2

    findings: list[dict] = []

    _check_manifest(plugin_root / ".claude-plugin" / "plugin.json", True, ("name", "version"), findings, plugin_root)
    # Coordination constraint: .codex-plugin/plugin.json may not exist yet — optional.
    _check_manifest(plugin_root / ".codex-plugin" / "plugin.json", False, ("name", "version"), findings, plugin_root)
    _check_manifest(plugin_root / "setup" / "manifest.json", False, ("schema", "plugin", "items"), findings, plugin_root)

    _check_commands_present(plugin_root, findings)
    _check_referenced_assets(plugin_root, findings)
    _check_python_scripts(plugin_root, findings)
    _check_shell_hooks(plugin_root, findings)
    _check_stale_tokens(plugin_root, findings)
    capabilities = _check_capability_dependencies(plugin_root, findings)

    result = {
        "schema_version": "devflow-doctor-v1",
        "plugin_root": str(plugin_root.resolve()),
        "generated_at": now_iso(),
        "findings": findings,
        "capabilities": capabilities,
        "healthy": is_healthy(findings),
    }

    if as_json:
        print(json.dumps(result, indent=2, sort_keys=False))
    else:
        _print_doctor_text(result)

    return 0 if result["healthy"] else 1


def _print_doctor_text(result: dict) -> None:
    status = "HEALTHY" if result["healthy"] else "FINDINGS"
    print(f"devflow doctor — {status}")
    print(f"plugin root: {result['plugin_root']}")
    blocking = [f for f in result["findings"] if f["severity"] != "info"]
    info = [f for f in result["findings"] if f["severity"] == "info"]
    if blocking:
        print(f"\n{len(blocking)} blocking finding(s):")
        for f in blocking:
            loc = f" [{f['path']}]" if f["path"] else ""
            print(f"  - ({f['severity']}) {f['id']}{loc}: {f['message']}")
    if info:
        print(f"\n{len(info)} informational finding(s):")
        for f in info:
            loc = f" [{f['path']}]" if f["path"] else ""
            print(f"  - {f['id']}{loc}: {f['message']}")
    if result["capabilities"]:
        print("\ncapabilities:")
        for cap, info_dict in sorted(result["capabilities"].items()):
            print(f"  - {cap}: {info_dict['status']} ({info_dict['dependency']}) — {info_dict['detail']}")
    if not blocking and not info and not result["capabilities"]:
        print("\nno findings.")


# ---------------------------------------------------------------------------
# evidence — deterministic Git/repo-state evidence packet
# ---------------------------------------------------------------------------

_PROTECTED_PATTERNS = (
    re.compile(r"^\.github/workflows/.+"),
    re.compile(r"(^|/)\.env(\..+)?$"),
    re.compile(r"(?i)(^|/)(billing|payment)s?(/|$)"),
)

_LOCKFILES = {
    "npm": "package-lock.json",
    "pnpm": "pnpm-lock.yaml",
    "yarn": "yarn.lock",
    "bun": "bun.lockb",
}

_INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md")


def is_protected(path: str) -> bool:
    return any(p.search(path) for p in _PROTECTED_PATTERNS)


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _git_head_info(repo: Path) -> tuple[Optional[str], bool, Optional[str], Optional[str]]:
    branch_r = run_git(repo, "symbolic-ref", "-q", "--short", "HEAD")
    detached = branch_r.returncode != 0
    branch = None if detached else branch_r.stdout.strip() or None
    sha_r = run_git(repo, "rev-parse", "HEAD")
    short_r = run_git(repo, "rev-parse", "--short", "HEAD")
    sha = sha_r.stdout.strip() if sha_r.returncode == 0 else None
    short = short_r.stdout.strip() if short_r.returncode == 0 else None
    return branch, detached, sha, short


def _resolve_base(repo: Path, base_arg: Optional[str]) -> dict:
    if base_arg:
        verify = run_git(repo, "rev-parse", "--verify", base_arg)
        if verify.returncode == 0:
            return {"ref": base_arg, "sha": verify.stdout.strip(), "resolved_via": "explicit"}
        return {"ref": base_arg, "sha": None, "resolved_via": "explicit-unresolved"}

    upstream = run_git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream.returncode == 0 and upstream.stdout.strip():
        ref = upstream.stdout.strip()
        sha = run_git(repo, "rev-parse", ref)
        return {"ref": ref, "sha": sha.stdout.strip() if sha.returncode == 0 else None, "resolved_via": "upstream"}

    origin_head = run_git(repo, "symbolic-ref", "refs/remotes/origin/HEAD")
    if origin_head.returncode == 0 and origin_head.stdout.strip():
        ref = origin_head.stdout.strip().replace("refs/remotes/", "", 1)
        sha = run_git(repo, "rev-parse", ref)
        return {
            "ref": ref,
            "sha": sha.stdout.strip() if sha.returncode == 0 else None,
            "resolved_via": "default-branch",
        }

    for candidate in ("main", "master"):
        verify = run_git(repo, "rev-parse", "--verify", candidate)
        if verify.returncode == 0:
            return {"ref": candidate, "sha": verify.stdout.strip(), "resolved_via": "local-fallback"}

    return {"ref": None, "sha": None, "resolved_via": "unresolved"}


def _parse_name_status(output: str) -> list[tuple[str, str]]:
    items = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        items.append((parts[0], parts[-1]))
    return items


def _parse_porcelain(output: str) -> list[tuple[str, str]]:
    items = []
    for line in output.splitlines():
        if not line:
            continue
        code = line[:2].strip()
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ")[-1]
        items.append((code, path.strip('"')))
    return items


def _changed_files(repo: Path, base: dict, head_sha: Optional[str]) -> list[dict]:
    changed: list[dict] = []
    if base.get("sha") and head_sha and base["sha"] != head_sha:
        diff = run_git(repo, "diff", "--name-status", f"{base['sha']}...{head_sha}")
        if diff.returncode == 0:
            for status, path in _parse_name_status(diff.stdout):
                changed.append({"path": path, "status": status, "origin": "committed"})

    # --untracked-files=all: without it, git status collapses a brand-new untracked
    # directory to a single "?? dirname/" entry, hiding files inside it (e.g. a fresh
    # .env dropped in a new directory would never surface as a protected-file match).
    status_r = run_git(repo, "status", "--porcelain", "--untracked-files=all")
    if status_r.returncode == 0:
        for code, path in _parse_porcelain(status_r.stdout):
            changed.append({"path": path, "status": code, "origin": "working_tree"})

    return changed


def _test_evidence_candidates(repo: Path, changed: list[dict]) -> list[dict]:
    """Return advisory candidates for changed tests; never infer a blocking contract."""
    candidates = []
    seen: set[str] = set()
    for item in changed:
        path = item["path"]
        lower = path.lower()
        is_test = (
            lower.startswith(("test/", "tests/", "__tests__/"))
            or "/tests/" in lower
            or any(marker in lower for marker in (".test.", ".spec.", "_test.py"))
        )
        if not is_test or path in seen:
            continue
        seen.add(path)
        signals = ["changed_test"]
        target = repo / path
        if target.is_file():
            text = _read_text(target)
            if re.search(r"\b(readFile|read_text|open)\b", text) and re.search(
                r"\b(toContain|assertIn|in\s+[^\n]+)\b", text
            ):
                signals.append("source_content_assertion")
        candidates.append(
            {
                "test_path": path,
                "related_production_files": [],
                "declared_invariant": None,
                "contract_class": None,
                "oracle_status": "unreviewed",
                "review_status": "advisory",
                "signals": signals,
            }
        )
    return sorted(candidates, key=lambda value: value["test_path"])


def _package_manager_facts(repo: Path) -> dict:
    lockfiles = [name for name, fname in _LOCKFILES.items() if (repo / fname).is_file()]
    return {
        "lockfiles": lockfiles,
        "python": {
            "pyproject_toml": (repo / "pyproject.toml").is_file(),
            "requirements_txt": (repo / "requirements.txt").is_file(),
        },
    }


def _package_scripts(repo: Path, findings: list[dict]) -> Optional[dict]:
    package_json = repo / "package.json"
    if not package_json.is_file():
        return None
    try:
        data = json.loads(_read_text(package_json))
    except json.JSONDecodeError as exc:
        findings.append(make_finding("package-json-invalid", "warning", f"package.json is not valid JSON: {exc}", "package.json"))
        return None
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(k): str(v) for k, v in scripts.items()}


def _instruction_files(repo: Path) -> dict:
    present = {name: (repo / name).is_file() for name in _INSTRUCTION_FILES}
    settings_matches = sorted((repo / ".claude").glob("settings*.json")) if (repo / ".claude").is_dir() else []
    present["settings.json_glob"] = [rel(repo, p) for p in settings_matches]
    return present


def _codegraph_status_stale(repo: Path) -> Optional[bool]:
    """Return CodeGraph's authoritative freshness verdict when available.

    The database mtime is only a compatibility fallback: tracked Markdown or JSON can be newer
    than the database without being part of CodeGraph's supported source inventory.
    """
    executable = shutil.which("codegraph")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "status", "--json"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        status = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    pending = status.get("pendingChanges")
    index = status.get("index")
    if status.get("initialized") is not True or not isinstance(pending, dict) or not isinstance(index, dict):
        return None
    counts = [pending.get(key) for key in ("added", "modified", "removed")]
    if any(type(value) is not int or value < 0 for value in counts):
        return None
    pending_refs = index.get("pendingRefs")
    if type(pending_refs) is not int or pending_refs < 0:
        return None
    return bool(
        sum(counts)
        or status.get("worktreeMismatch") is not None
        or index.get("state") != "complete"
        or index.get("reindexRecommended") is True
        or pending_refs
    )


def _codegraph_evidence(repo: Path, findings: list[dict]) -> dict:
    cg_dir = repo / ".codegraph"
    exists = cg_dir.is_dir()
    if not exists:
        return {"exists": False, "db_present": False, "db_path": None, "db_mtime": None, "newest_source_mtime": None, "stale": None}

    db_files = sorted(cg_dir.rglob("*.db")) + sorted(cg_dir.rglob("*.sqlite")) + sorted(cg_dir.rglob("*.sqlite3"))
    db_present = bool(db_files)
    db_mtime = max((f.stat().st_mtime for f in db_files), default=None)
    db_path = rel(repo, db_files[0]) if db_files else None

    tracked_r = run_git(repo, "ls-files")
    tracked_paths = [repo / p for p in tracked_r.stdout.splitlines() if p] if tracked_r.returncode == 0 else []
    if not tracked_paths:
        skip_dirs = {".git", ".codegraph", "node_modules"}
        tracked_paths = [
            p
            for p in repo.rglob("*")
            if p.is_file() and not any(part in skip_dirs for part in p.relative_to(repo).parts)
        ]
    newest_source_mtime = max((p.stat().st_mtime for p in tracked_paths if p.is_file()), default=None)

    stale = _codegraph_status_stale(repo) if db_present else None
    authoritative_status = stale is not None
    if stale is None and db_mtime is not None and newest_source_mtime is not None:
        stale = db_mtime < newest_source_mtime
    if stale:
        if authoritative_status:
            message = "CodeGraph reports pending, mismatched, or incomplete index state — report only, never auto-initialized/rebuilt"
        else:
            message = "CodeGraph index is older than the newest tracked source file — timestamp fallback only, never auto-initialized/rebuilt"
        findings.append(
            make_finding(
                "codegraph-stale",
                "info",
                message,
                db_path,
            )
        )

    return {
        "exists": True,
        "db_present": db_present,
        "db_path": db_path,
        "db_mtime": db_mtime,
        "newest_source_mtime": newest_source_mtime,
        "stale": stale,
    }


def run_evidence(repo: Path, base_arg: Optional[str], as_json: bool) -> int:
    if not repo.is_dir():
        print(f"ERROR: --repo does not exist or is not a directory: {repo}", file=sys.stderr)
        return 2

    top_level = run_git(repo, "rev-parse", "--show-toplevel")
    if top_level.returncode != 0:
        print(f"ERROR: not a git repository: {repo}", file=sys.stderr)
        return 2
    repo_root = Path(top_level.stdout.strip()).resolve()

    findings: list[dict] = []

    branch, detached, head_sha, head_short = _git_head_info(repo_root)
    if detached:
        findings.append(make_finding("detached-head", "info", "HEAD is detached", None))

    status_r = run_git(repo_root, "status", "--porcelain", "--untracked-files=all")
    status = "dirty" if status_r.returncode == 0 and status_r.stdout.strip() else "clean"

    base = _resolve_base(repo_root, base_arg)
    if base["resolved_via"] == "unresolved":
        findings.append(make_finding("base-unresolved", "info", "could not resolve a base ref (no upstream, no origin/HEAD, no local main/master)", None))
    elif base["resolved_via"] == "explicit-unresolved":
        findings.append(make_finding("base-unresolved", "warning", f"explicit --base '{base['ref']}' does not resolve in this repository", None))

    changed = _changed_files(repo_root, base, head_sha)

    protected_matches = sorted({c["path"] for c in changed if is_protected(c["path"])})
    for p in protected_matches:
        findings.append(make_finding("protected-file-touch", "warning", "changed file matches a protected pattern (.github/workflows/*, .env*, billing/payment paths)", p))

    package_scripts = _package_scripts(repo_root, findings)
    codegraph = _codegraph_evidence(repo_root, findings)

    result = {
        "schema_version": "devflow-evidence-v1",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "git": {
            "is_git_repo": True,
            "head": {"sha": head_sha, "short_sha": head_short},
            "branch": branch,
            "detached": detached,
            "status": status,
            "base": base,
            "changed_files": changed,
        },
        "protected_matches": protected_matches,
        "instruction_files": _instruction_files(repo_root),
        "package_manager": _package_manager_facts(repo_root),
        "package_scripts": package_scripts,
        "codegraph": codegraph,
        "test_evidence_candidates": _test_evidence_candidates(repo_root, changed),
        "findings": findings,
        "healthy": is_healthy(findings),
    }

    if as_json:
        print(json.dumps(result, indent=2, sort_keys=False))
    else:
        _print_evidence_text(result)

    return 0 if result["healthy"] else 1


def _print_evidence_text(result: dict) -> None:
    git_info = result["git"]
    status = "PASS" if result["healthy"] else "FINDINGS"
    print(f"devflow evidence — {status}")
    print(f"repo: {result['repo_root']}")
    print(f"HEAD: {git_info['head']['short_sha'] or '(no commits)'}  branch: {git_info['branch'] or '(detached)'}  status: {git_info['status']}")
    print(f"base: {git_info['base']['ref'] or '(unresolved)'} via {git_info['base']['resolved_via']}")
    print(f"changed files: {len(git_info['changed_files'])}")
    if result["protected_matches"]:
        print(f"protected-file matches: {result['protected_matches']}")
    if result["findings"]:
        print("\nfindings:")
        for f in result["findings"]:
            loc = f" [{f['path']}]" if f["path"] else ""
            print(f"  - ({f['severity']}) {f['id']}{loc}: {f['message']}")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devflow.py", description="Deterministic doctor and evidence CLI for rhize-devflow.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    doctor_p = sub.add_parser("doctor", help="Validate plugin health (manifests, assets, scripts, hooks, capabilities).")
    doctor_p.add_argument("--json", action="store_true", help="Emit stable JSON instead of a text summary.")
    doctor_p.add_argument("--plugin-root", type=Path, default=None, help="Plugin root to inspect (defaults to this script's own plugin).")

    evidence_p = sub.add_parser("evidence", help="Collect a deterministic Git/repo-state evidence packet.")
    evidence_p.add_argument("--json", action="store_true", help="Emit stable JSON instead of a text summary.")
    evidence_p.add_argument("--repo", type=Path, default=None, help="Repository to inspect (defaults to cwd).")
    evidence_p.add_argument("--base", type=str, default=None, help="Base ref to diff against (defaults to upstream, then default branch).")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse calls sys.exit(2) on its own for usage errors — normalize to our contract.
        return exc.code if isinstance(exc.code, int) else 2

    try:
        if args.subcommand == "doctor":
            plugin_root = args.plugin_root.resolve() if args.plugin_root else default_plugin_root()
            return run_doctor(plugin_root, args.json)
        if args.subcommand == "evidence":
            repo = args.repo.resolve() if args.repo else Path.cwd()
            return run_evidence(repo, args.base, args.json)
    except Exception as exc:  # noqa: BLE001 - top-level safety net per CLI contract
        print(f"ERROR: internal error: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    sys.exit(main())
