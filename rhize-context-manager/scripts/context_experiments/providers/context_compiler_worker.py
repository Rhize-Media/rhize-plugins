#!/usr/bin/env python3
"""Isolated bridge from the Rhize adapter to the unmodified upstream library."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path


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
    warnings = []
    if diagnostics and diagnostics.dynamic_dispatch_files:
        warnings.append("dynamic_dispatch_may_hide_dependencies")
    if diagnostics and diagnostics.decorator_hint_files:
        warnings.append("decorator_registration_may_hide_dependencies")
    if diagnostics and diagnostics.name_collisions:
        warnings.append("name_only_resolution_included_collisions")

    entries = []
    for entry in compiled.entries:
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
        "packId": f"pack-{uuid.uuid4().hex}",
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
            "dynamicDispatchFileCount": (
                len(diagnostics.dynamic_dispatch_files) if diagnostics else 0
            ),
            "decoratorHintFileCount": (
                len(diagnostics.decorator_hint_files) if diagnostics else 0
            ),
            "nameCollisionCount": len(diagnostics.name_collisions) if diagnostics else 0,
        },
        "warnings": warnings,
    }
    prompt_parts = []
    for entry in compiled.entries:
        label = "FULL SOURCE" if entry.tier == 1 else "SKELETON"
        prompt_parts.append(
            f"# ---- [{label}] {relative_path(entry.path, repo)} ----\n{entry.content}"
        )
    print(json.dumps({"manifest": manifest, "prompt": "\n\n".join(prompt_parts)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
