#!/usr/bin/env python3
"""validate_plugin_configs.py — lint plugin hooks.json / .mcp.json for known footguns.

Three checks, each written to catch a real 2026-08 incident:

  (a) Unquoted ${VAR} expansion in a hook `command` string.
      `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/x.py` word-splits once
      CLAUDE_PLUGIN_ROOT expands under a path containing a space (e.g.
      "~/Library/Application Support/..."), so python3 receives only
      "/Users/x/Library/Application" as argv[1]. ERROR for path-like variables
      (CLAUDE_PLUGIN_ROOT, or any variable immediately followed by `/`) —
      WARNING elsewhere, since unquoted expansion is sometimes deliberate
      word-splitting.

  (b) Secret-shaped env values in a stdio MCP server's `env` block — either a
      "${VAR}" reference or an inline plaintext literal. `${VAR}` only expands
      when the variable happens to be in Claude Code's own process env;
      otherwise the literal string is passed through and the server 401s
      opaquely. Correct fix: the mcp-secret-launcher.sh shim (see
      docs/mcp-secret-launcher.md), which resolves secrets from the macOS
      Keychain and never puts them in a config file. Key names are matched by
      their last `_`/`-`-separated component so `SLACK_TEAM_ID` and
      `KEY_FILE_PATH` are not mistaken for secrets; a bare `USERNAME`-shaped
      name is capped at WARNING (never ERROR by default) since it is often a
      non-secret identifier. HTTP-transport blocks (`url`/`headers`) are out
      of scope for this check — `${VAR}` is the only mechanism available
      there and is correct.

  (c) Trailing slash on a `*_URL` / `*_BASE_URL` env value.
      obsidian-mcp-server concatenates baseUrl + path unnormalized, so
      "https://host/" produced "https://host//tags/" and 404'd every
      endpoint. Always WARNING — a trailing slash is legitimate when the
      client does proper RFC 3986 URL resolution.

Design:
  - Exit 0 unless at least one ERROR-severity finding survives suppression.
    `--strict` promotes WARNING findings to ERROR for the exit-code decision.
  - Findings are suppressed individually, by (file, JSON pointer) — see
    `--suppressions`. There is no flag that disables a whole check: an escape
    hatch that broad is worse than no lint.
  - Fixture directories are excluded from discovery: any path with a `tests`
    or `fixtures` path component is skipped, so this repo's own lint-test
    fixtures (deliberately bad configs) never trip the real scan.

Usage:
  python3 scripts/validate_plugin_configs.py [--strict] [--root PATH]
                                              [--suppressions PATH]

Exit code 0 on success (no errors, or only suppressed/warning findings in
non-strict mode), 1 if any error-severity finding survives.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# ${VAR} or ${VAR:-default} — used for both check (a) and check (b)'s ${VAR:-...} form.
VAR_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\}")

# check (a): variables whose expansion is always path-like, regardless of context.
PATH_LIKE_VARS = {"CLAUDE_PLUGIN_ROOT"}

# check (b): last name-component -> severity. "KEY" alone (not as a suffix) would
# false-positive on things like KEY_FILE_PATH, so matching is last-component-only.
STRONG_SECRET_COMPONENTS = {
    "KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD", "PWD", "CREDENTIAL", "CREDENTIALS",
}
WEAK_SECRET_COMPONENTS = {"USERNAME"}

SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}


class Finding:
    """Plain class, not @dataclass — this script is loaded via
    importlib.util.module_from_spec()/exec_module() by tests without being
    registered in sys.modules first (the same pattern tests/skill-map/_util.py
    and tests/test_bump_version.py use), and @dataclass's KW_ONLY detection
    looks the module up in sys.modules by name, which crashes when it's
    absent. A plain __init__ sidesteps that entirely.
    """

    def __init__(
        self,
        file: Path,
        plugin: str,
        pointer: str,
        severity: str,  # "info" | "warning" | "error"
        message: str,
        fix: str,
        suppressed: bool = False,
        suppression_reason: str | None = None,
    ) -> None:
        self.file = file
        self.plugin = plugin
        self.pointer = pointer
        self.severity = severity
        self.message = message
        self.fix = fix
        self.suppressed = suppressed
        self.suppression_reason = suppression_reason

    def rel_file(self, root: Path) -> str:
        try:
            return self.file.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return str(self.file)

    def effective_severity(self, strict: bool) -> str:
        if self.suppressed:
            return "info"
        if strict and self.severity == "warning":
            return "error"
        return self.severity


# ---------- discovery ----------

def is_excluded(path: Path, root: Path) -> bool:
    """Fixture/test paths are never part of the real scan (see module docstring)."""
    try:
        rel_parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        rel_parts = path.parts
    return "tests" in rel_parts or "fixtures" in rel_parts or "node_modules" in rel_parts


def discover_config_files(root: Path) -> list[tuple[Path, str, str]]:
    """Return (absolute_path, plugin_name, kind) for every plugin's hooks.json / .mcp.json.

    Plugins are top-level directories (the marketplace convention); this does
    not require a `.claude-plugin/plugin.json` manifest to exist.
    """
    results: list[tuple[Path, str, str]] = []
    if not root.is_dir():
        return results
    for hooks_path in sorted(root.glob("*/hooks/hooks.json")):
        if is_excluded(hooks_path, root):
            continue
        plugin = hooks_path.relative_to(root).parts[0]
        results.append((hooks_path, plugin, "hooks"))
    for mcp_path in sorted(root.glob("*/.mcp.json")):
        if is_excluded(mcp_path, root):
            continue
        plugin = mcp_path.relative_to(root).parts[0]
        results.append((mcp_path, plugin, "mcp"))
    return results


# ---------- check (a): unquoted ${VAR} in hook commands ----------

def quote_state_at(s: str, index: int) -> str | None:
    """Return the quote context ('"', "'", or None) active just before s[index]."""
    state: str | None = None
    i = 0
    while i < index:
        c = s[i]
        if state == '"':
            if c == "\\" and i + 1 < len(s):
                i += 2
                continue
            if c == '"':
                state = None
        elif state == "'":
            if c == "'":
                state = None
        else:
            if c == '"':
                state = '"'
            elif c == "'":
                state = "'"
        i += 1
    return state


def find_unquoted_var_refs(command: str) -> list[tuple[str, bool, str]]:
    """Return (var_name, path_like, matched_text) for each ${VAR} not inside double quotes.

    A variable inside single quotes is skipped: bash never expands it there,
    so it cannot exhibit the word-splitting bug this check targets.
    """
    out: list[tuple[str, bool, str]] = []
    for m in VAR_REF_RE.finditer(command):
        if quote_state_at(command, m.start()) is not None:
            continue
        var_name = m.group(1)
        followed_by_slash = m.end() < len(command) and command[m.end()] == "/"
        path_like = var_name in PATH_LIKE_VARS or followed_by_slash
        out.append((var_name, path_like, m.group(0)))
    return out


def lint_hooks_file(path: Path, plugin: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [Finding(path, plugin, "", "error", f"could not parse JSON: {exc}",
                         "fix the JSON syntax error")]

    events = doc.get("hooks") if isinstance(doc, dict) else None
    if not isinstance(events, dict):
        return findings

    for event_name, entries in events.items():
        if not isinstance(entries, list):
            continue
        for i, entry in enumerate(entries):
            hook_list = entry.get("hooks") if isinstance(entry, dict) else None
            if not isinstance(hook_list, list):
                continue
            for j, hook in enumerate(hook_list):
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command")
                if not isinstance(command, str):
                    continue
                pointer = f"/hooks/{event_name}/{i}/hooks/{j}/command"
                for var_name, path_like, matched_text in find_unquoted_var_refs(command):
                    severity = "error" if path_like else "warning"
                    reason = (
                        "path-like variable (immediately followed by '/', or "
                        "CLAUDE_PLUGIN_ROOT which is always path-like)"
                        if path_like else
                        "no evidence it's meant to word-split into multiple arguments"
                    )
                    findings.append(Finding(
                        file=path, plugin=plugin, pointer=pointer, severity=severity,
                        message=(
                            f"unquoted {matched_text} in hook command — {reason}. "
                            "CLAUDE_PLUGIN_ROOT can expand under a path containing a "
                            "space (e.g. '.../Library/Application Support/...'), so an "
                            "unquoted use word-splits into multiple argv entries."
                        ),
                        fix=(
                            f'wrap the expansion in double quotes, e.g. "{matched_text}..." '
                            "— only leave it bare if this specific variable is meant to "
                            "word-split into multiple shell arguments."
                        ),
                    ))
    return findings


# ---------- checks (b) and (c): .mcp.json env blocks ----------

def _last_component(key: str) -> str:
    parts = [c for c in re.split(r"[_\-]+", key.upper()) if c]
    return parts[-1] if parts else ""


def secret_key_severity(key: str) -> str | None:
    last = _last_component(key)
    if last in STRONG_SECRET_COMPONENTS:
        return "error"
    if last in WEAK_SECRET_COMPONENTS:
        return "warning"
    return None


def is_url_key(key: str) -> bool:
    return _last_component(key) == "URL"


def lint_mcp_file(path: Path, plugin: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [Finding(path, plugin, "", "error", f"could not parse JSON: {exc}",
                         "fix the JSON syntax error")]

    servers = doc.get("mcpServers") if isinstance(doc, dict) else None
    if not isinstance(servers, dict):
        return findings

    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        is_stdio = "command" in cfg
        is_http = ("url" in cfg) or ("headers" in cfg)

        env = cfg.get("env")
        if isinstance(env, dict):
            for key, value in env.items():
                if not isinstance(value, str):
                    continue
                pointer = f"/mcpServers/{name}/env/{key}"

                # check (b): stdio only — HTTP transport has no other mechanism
                # for secrets and is explicitly out of scope.
                if is_stdio:
                    sev = secret_key_severity(key)
                    if sev is not None:
                        findings.append(Finding(
                            file=path, plugin=plugin, pointer=pointer, severity=sev,
                            message=(
                                f"env key '{key}' looks credential-shaped in a stdio "
                                f"MCP server's env block (value: {value!r}). \"${{VAR}}\" "
                                "here only expands when the variable happens to be in "
                                "Claude Code's own process env; otherwise the literal "
                                "string is passed through and the server 401s opaquely "
                                "with no indication it's a config problem."
                            ),
                            fix=(
                                f"move '{key}' out of env: pass it as a launcher arg "
                                "before '--' in mcp-secret-launcher.sh (see "
                                "docs/mcp-secret-launcher.md) so it resolves from the "
                                "macOS Keychain instead of a config file."
                            ),
                        ))

                # check (c): applies to any transport's env block.
                if is_url_key(key) and value.endswith("/"):
                    findings.append(Finding(
                        file=path, plugin=plugin, pointer=pointer, severity="warning",
                        message=(
                            f"env key '{key}' ends with a trailing slash ({value!r}). "
                            "Some MCP server clients (e.g. obsidian-mcp-server) "
                            "concatenate base URL + path unnormalized, producing a "
                            "doubled slash that 404s every endpoint."
                        ),
                        fix=(
                            f"drop the trailing slash ('{value.rstrip('/')}') unless "
                            "you've verified this client does proper RFC 3986 URL "
                            "resolution."
                        ),
                    ))

        if is_http and not is_stdio:
            headers = cfg.get("headers")
            if isinstance(headers, dict):
                for key, value in headers.items():
                    if isinstance(value, str) and VAR_REF_RE.search(value):
                        pointer = f"/mcpServers/{name}/headers/{key}"
                        findings.append(Finding(
                            file=path, plugin=plugin, pointer=pointer, severity="info",
                            message=(
                                f"HTTP-transport header '{key}' uses \"${{VAR}}\" — this "
                                "is out of scope for the secret-shaped-env check and is "
                                "the correct (only available) mechanism for HTTP "
                                "transport, not a finding."
                            ),
                            fix="no action needed.",
                        ))
    return findings


# ---------- suppressions ----------

def load_suppressions(path: Path | None) -> list[dict]:
    if path is None or not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"suppressions file {path} must contain a JSON array")
    for entry in data:
        if not isinstance(entry, dict) or "file" not in entry or "pointer" not in entry:
            raise ValueError(
                f"suppressions file {path}: every entry needs 'file' and 'pointer' "
                "(and should carry 'reason')"
            )
    return data


def apply_suppressions(findings: list[Finding], suppressions: list[dict], root: Path) -> None:
    index = {(s["file"], s["pointer"]) for s in suppressions}
    reasons = {(s["file"], s["pointer"]): s.get("reason", "(no reason given)") for s in suppressions}
    for f in findings:
        key = (f.rel_file(root), f.pointer)
        if key in index:
            f.suppressed = True
            f.suppression_reason = reasons[key]


# ---------- orchestration ----------

def collect_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path, plugin, kind in discover_config_files(root):
        if kind == "hooks":
            findings.extend(lint_hooks_file(path, plugin))
        else:
            findings.extend(lint_mcp_file(path, plugin))
    return findings


def format_report(findings: list[Finding], root: Path, strict: bool) -> tuple[str, int]:
    lines: list[str] = []

    ordered = sorted(
        findings,
        key=lambda f: (-SEVERITY_RANK[f.effective_severity(strict)], f.rel_file(root), f.pointer),
    )

    for f in ordered:
        eff = f.effective_severity(strict)
        if f.suppressed:
            tag = f"SUPPRESSED ({f.suppression_reason})"
        else:
            tag = eff.upper()
        lines.append(f"[{tag}] {f.rel_file(root)}  (plugin: {f.plugin})")
        lines.append(f"  path:  {f.pointer or '(document root)'}")
        lines.append(f"  issue: {f.message}")
        lines.append(f"  fix:   {f.fix}")
        lines.append("")

    real_errors = sum(1 for f in findings if not f.suppressed and f.effective_severity(strict) == "error")
    real_warnings = sum(1 for f in findings if not f.suppressed and f.effective_severity(strict) == "warning")
    real_info = sum(1 for f in findings if not f.suppressed and f.severity == "info")
    suppressed = sum(1 for f in findings if f.suppressed)

    if not findings:
        lines.append("No issues found.")
    else:
        mode = "strict" if strict else "default"
        lines.append(
            f"{real_errors} error(s), {real_warnings} warning(s), {real_info} info, "
            f"{suppressed} suppressed  [{mode} mode]"
        )

    exit_code = 1 if real_errors else 0
    return "\n".join(lines), exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint plugin hooks.json / .mcp.json for known config footguns.",
    )
    parser.add_argument("--strict", action="store_true",
                         help="promote warning-severity findings to errors")
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                         help="repository root to scan (default: this script's own repo)")
    parser.add_argument("--suppressions", type=Path, default=None,
                         help="path to a JSON array of {file, pointer, reason} suppressions")
    args = parser.parse_args(argv)

    findings = collect_findings(args.root)
    suppressions = load_suppressions(args.suppressions)
    apply_suppressions(findings, suppressions, args.root)

    report, exit_code = format_report(findings, args.root, args.strict)
    print(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
