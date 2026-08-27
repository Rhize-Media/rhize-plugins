#!/usr/bin/env python3
"""Isolated bridge from the Rhize adapter to the unmodified upstream library."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path


_IGNORED_PARTS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
_CALLBACK_REGISTRATION_NAMES = {
    "add_listener",
    "connect",
    "hook",
    "on",
    "register",
    "subscribe",
}


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _CallbackRegistrationVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.found = False

    def visit_Call(self, node: ast.Call) -> None:
        callback_values = [*node.args, *(keyword.value for keyword in node.keywords)]
        if _call_name(node.func) in _CALLBACK_REGISTRATION_NAMES and any(
            isinstance(value, (ast.Name, ast.Attribute, ast.Lambda))
            for value in callback_values
        ):
            self.found = True
        self.generic_visit(node)


def repository_guardrails(repo: Path) -> dict[str, int]:
    from symbol_resolver import KNOWN_EVENT_DECORATORS, extract_symbols

    dynamic_files = 0
    decorator_files = 0
    callback_files = 0
    syntax_error_files = 0
    for path in repo.rglob("*.py"):
        if any(part in _IGNORED_PARTS for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            symbols = extract_symbols(source)
        except (SyntaxError, UnicodeDecodeError):
            syntax_error_files += 1
            continue
        dynamic_files += int(symbols.uses_dynamic_dispatch)
        decorator_files += int(bool(symbols.uses_decorators & KNOWN_EVENT_DECORATORS))
        visitor = _CallbackRegistrationVisitor()
        visitor.visit(tree)
        callback_files += int(visitor.found)
    return {
        "dynamicDispatchFileCount": dynamic_files,
        "decoratorHintFileCount": decorator_files,
        "callbackRegistrationFileCount": callback_files,
        "syntaxErrorFileCount": syntax_error_files,
    }


def relative_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--max-hops", type=int, required=True)
    args = parser.parse_args()

    checkout = args.checkout.resolve()
    repo = args.repo.resolve()
    sys.path.insert(0, str(checkout))
    from compiler import ContextCompiler  # type: ignore[import-not-found]

    compiled = ContextCompiler(repo, max_hops=args.max_hops).compile(args.target)
    diagnostics = compiled.diagnostics
    guardrails = repository_guardrails(repo)
    warnings = []
    if guardrails["dynamicDispatchFileCount"]:
        warnings.append("dynamic_dispatch_may_hide_dependencies")
    if guardrails["decoratorHintFileCount"]:
        warnings.append("decorator_registration_may_hide_dependencies")
    if guardrails["callbackRegistrationFileCount"]:
        warnings.append("callback_registration_may_hide_dependencies")
    if guardrails["syntaxErrorFileCount"]:
        warnings.append("unsupported_python_syntax_may_hide_dependencies")
    if diagnostics and diagnostics.name_collisions:
        warnings.append("name_only_resolution_included_collisions")

    compiled_entries = sorted(
        compiled.entries,
        key=lambda entry: relative_path(entry.path, repo),
    )
    entries = []
    for entry in compiled_entries:
        content = entry.content
        entries.append(
            {
                "path": relative_path(entry.path, repo),
                "tier": entry.tier,
                "hopDistance": entry.hop_distance,
                "contentHash": hashlib.sha256(content.encode()).hexdigest(),
                "estimatedTokens": entry.tokens,
            }
        )
    manifest = {
        "schemaVersion": 1,
        "packId": "pack-" + "0" * 32,
        "targetPath": relative_path(compiled.target_file, repo),
        "compiler": {
            "name": "context-compiler",
            "revision": "4edb163911f9a6bc869f35970fa77acb3dd88b8f",
            "maxHops": args.max_hops,
        },
        "entries": entries,
        "excludedCount": compiled.excluded_count,
        "totalRepoFiles": compiled.total_repo_files,
        "naiveDumpTokens": compiled.naive_dump_tokens,
        "compiledTokens": compiled.compiled_tokens,
        "reductionPercent": compiled.reduction_pct(),
        "buildMilliseconds": compiled.build_seconds * 1000,
        "diagnostics": {
            "unresolvedCallCount": len(diagnostics.unresolved_calls) if diagnostics else 0,
            **guardrails,
            "nameCollisionCount": len(diagnostics.name_collisions) if diagnostics else 0,
        },
        "warnings": warnings,
    }
    prompt_parts = []
    for entry in compiled_entries:
        label = "FULL SOURCE" if entry.tier == 1 else "SKELETON"
        prompt_parts.append(
            f"# ---- [{label}] {relative_path(entry.path, repo)} ----\n{entry.content}"
        )
    print(json.dumps({"manifest": manifest, "prompt": "\n\n".join(prompt_parts)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
