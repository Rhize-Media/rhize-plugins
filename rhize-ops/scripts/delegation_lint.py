#!/usr/bin/env python3
"""delegation_lint.py — gate run before any external write (Jira description, Confluence
body, or Slack message) for path leaks (vault-relative paths, obsidian:// URLs) and
jira-description contract-shape mistakes (delegation marker placement, starter-prompt
count, embedded step-by-step sections, length). Reads text from --file or stdin.

Rules:
  absolute-path          FAIL  all kinds           /Users/..., /home/..., ~/..., or a Windows
                                                     drive path (C:\\... or C:/...)
  obsidian-url            FAIL  all kinds           obsidian://... anywhere in a token
  vault-note-path          FAIL  all kinds           a token containing "/" whose last segment
                                                      ends in .md/.canvas/.base, OR (line-level
                                                      backstop) a line with a separate slash
                                                      token and a separate note-suffix token
                                                      (e.g. split across an em dash)
  directory-path             FAIL  all kinds           a non-URL token containing "/" that ends
                                                        with "/"
  bare-note-file               WARN  all kinds           a lone token ending in .md/.canvas/.base
                                                          with no "/" anywhere in it
  ask-for-file                   FAIL  all kinds           "ask ... for/to send" on a line that
                                                            also hit vault-note-path/bare-note-file
  marker-missing                   FAIL  jira-description   no rhize-delegation:v1: marker found
  marker-not-last                    FAIL  jira-description   marker isn't the sole, final
                                                                nonblank line
  marker-in-confluence                 FAIL  confluence-body   marker text anywhere (never
                                                                 allowed on a Confluence page)
  multiple-starter-prompts               FAIL  jira-description   more than one
                                                                    "Paste into Claude:" line
  no-starter-prompt                        WARN  jira-description   no "Paste into Claude:" line
  steps-in-jira                              FAIL  jira-description   a "## Step-by-Step" heading
                                                                       (suppress with --allow-steps
                                                                       for the full-package Jira
                                                                       fallback)
  too-long                                     WARN/FAIL jira-description   over --warn-chars /
                                                                             --max-chars
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


KINDS = ("jira-description", "confluence-body", "slack-message")
TOKEN_SPLIT_RE = re.compile(r"[\s`'\"()<>,]+")
DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
NOTE_SUFFIXES = (".md", ".canvas", ".base")
TRAILING_PUNCTUATION = ".,;:)"
MARKER_SUBSTRING = "rhize-delegation:v1:"
MARKER_LINE_RE = re.compile(
    r"^rhize-delegation:v1:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
STARTER_PROMPT = "Paste into Claude:"
ASK_FOR_FILE_RE = re.compile(r"(?i)\bask \w+ (for|to send)")
STEPS_RE = re.compile(r"^#{1,6}\s*Step-by-Step")


def excerpt_of(line: str) -> str:
    return line.strip()[:80]


def is_url_token(token: str) -> bool:
    return token.startswith("http://") or token.startswith("https://")


def token_findings(line: str) -> tuple[list[dict[str, Any]], bool]:
    """Return (findings, note_path_hit) for one line's whitespace/punctuation-delimited
    tokens. note_path_hit is True when a token triggered vault-note-path or bare-note-file
    (feeds the ask-for-file rule)."""
    findings: list[dict[str, Any]] = []
    note_path_hit = False
    for raw_token in TOKEN_SPLIT_RE.split(line):
        if not raw_token:
            continue
        token = raw_token.rstrip(TRAILING_PUNCTUATION)
        if not token:
            continue
        if is_url_token(token):
            continue
        if token.startswith("/Users/") or token.startswith("/home/") or token.startswith("~/") or DRIVE_PATH_RE.match(token):
            findings.append({"severity": "FAIL", "rule": "absolute-path"})
        if "obsidian://" in token:
            findings.append({"severity": "FAIL", "rule": "obsidian-url"})
        if "/" in token:
            if token.endswith("/"):
                findings.append({"severity": "FAIL", "rule": "directory-path"})
            last_segment = token.rsplit("/", 1)[-1]
            if last_segment.endswith(NOTE_SUFFIXES):
                findings.append({"severity": "FAIL", "rule": "vault-note-path"})
                note_path_hit = True
        elif token.endswith(NOTE_SUFFIXES):
            findings.append({"severity": "WARN", "rule": "bare-note-file"})
            note_path_hit = True
    return findings, note_path_hit


def line_has_split_note_path(line: str) -> bool:
    """Ruling 13 line-level backstop: True when a line contains at least one non-URL token
    with "/" AND at least one (possibly different) non-URL token ending in a note suffix —
    catches a vault note path split across tokens (e.g. by an em dash or extra spaces) that
    no single token's own vault-note-path check would catch."""
    has_slash_token = False
    has_note_suffix_token = False
    for raw_token in TOKEN_SPLIT_RE.split(line):
        if not raw_token:
            continue
        token = raw_token.rstrip(TRAILING_PUNCTUATION)
        if not token or is_url_token(token):
            continue
        if "/" in token:
            has_slash_token = True
        if token.endswith(NOTE_SUFFIXES):
            has_note_suffix_token = True
    return has_slash_token and has_note_suffix_token


def lint(
    text: str, kind: str, warn_chars: int, max_chars: int, allow_steps: bool = False,
) -> list[dict[str, Any]]:
    lines = text.splitlines()
    findings: list[dict[str, Any]] = []

    def add(severity: str, rule: str, line_no: int, excerpt: str) -> None:
        findings.append({"severity": severity, "rule": rule, "line": line_no, "excerpt": excerpt})

    nonblank_indices = [i for i, line in enumerate(lines) if line.strip()]
    last_nonblank = nonblank_indices[-1] if nonblank_indices else None
    marker_line_indices = [i for i, line in enumerate(lines) if MARKER_LINE_RE.match(line)]
    mention_indices = [i for i, line in enumerate(lines) if MARKER_SUBSTRING in line]

    for i, line in enumerate(lines, start=1):
        hits, note_path_hit = token_findings(line)
        already_vault_note_path = any(hit["rule"] == "vault-note-path" for hit in hits)
        for hit in hits:
            add(hit["severity"], hit["rule"], i, excerpt_of(line))
        if not already_vault_note_path and line_has_split_note_path(line):
            add("FAIL", "vault-note-path", i, excerpt_of(line))
            note_path_hit = True
        if note_path_hit and ASK_FOR_FILE_RE.search(line):
            add("FAIL", "ask-for-file", i, excerpt_of(line))
        if kind == "confluence-body" and MARKER_SUBSTRING in line:
            add("FAIL", "marker-in-confluence", i, excerpt_of(line))
        if kind == "jira-description" and not allow_steps and STEPS_RE.match(line):
            add("FAIL", "steps-in-jira", i, excerpt_of(line))

    if kind == "jira-description":
        starter_indices = [i for i, line in enumerate(lines) if STARTER_PROMPT in line]
        if len(starter_indices) > 1:
            second = starter_indices[1]
            add("FAIL", "multiple-starter-prompts", second + 1, excerpt_of(lines[second]))
        elif not starter_indices:
            line_no = (last_nonblank + 1) if last_nonblank is not None else 1
            add("WARN", "no-starter-prompt", line_no, "no 'Paste into Claude:' line found")

        if not marker_line_indices:
            line_no = (last_nonblank + 1) if last_nonblank is not None else 1
            add("FAIL", "marker-missing", line_no, "no rhize-delegation:v1: marker found")
        else:
            not_last = max(marker_line_indices) != last_nonblank
            duplicate = len(marker_line_indices) > 1
            extra_mentions = [i for i in mention_indices if i not in marker_line_indices]
            if not_last or duplicate or extra_mentions:
                if duplicate:
                    offending = marker_line_indices[1]
                elif not_last:
                    offending = marker_line_indices[-1]
                else:
                    offending = extra_mentions[0]
                add("FAIL", "marker-not-last", offending + 1, excerpt_of(lines[offending]))

        chars = len(text)
        line_no = len(lines) if lines else 1
        if chars > max_chars:
            add("FAIL", "too-long", line_no, f"{chars} chars exceeds max {max_chars}")
        elif chars > warn_chars:
            add("WARN", "too-long", line_no, f"{chars} chars exceeds warn {warn_chars}")

    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--warn-chars", type=int, default=1500)
    parser.add_argument("--max-chars", type=int, default=3000)
    parser.add_argument(
        "--allow-steps", action="store_true",
        help=(
            "suppress only the steps-in-jira rule (kind=jira-description). Use this for the "
            "full-package Jira description fallback when confluence.status isn't ready — that "
            "template legitimately contains a '## Step-by-Step Instructions' section. All other "
            "rules, including path-leak rules, still apply."
        ),
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)

    try:
        text = args.file.read_text(encoding="utf-8") if args.file is not None else sys.stdin.read()
    except OSError as exc:
        print(f"delegation_lint: cannot read input: {exc}", file=sys.stderr)
        return 2

    findings = lint(text, args.kind, args.warn_chars, args.max_chars, args.allow_steps)
    fail_count = sum(1 for f in findings if f["severity"] == "FAIL")
    warn_count = sum(1 for f in findings if f["severity"] == "WARN")
    ok = fail_count == 0

    if args.json:
        payload = {"ok": ok, "kind": args.kind, "chars": len(text), "findings": findings}
        print(json.dumps(payload))
    else:
        for finding in findings:
            print(f"{finding['severity']} {finding['rule']} line {finding['line']}: {finding['excerpt']}")
        print("PASS" if ok else f"FAIL ({fail_count} fail, {warn_count} warn)")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
