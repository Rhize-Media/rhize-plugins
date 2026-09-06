#!/usr/bin/env python3
"""Build, verify, purge, and clean private preview-only memory context packs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from memory_context.core import MemoryContextAssembler, MemoryStore, default_memory_root, parse_time
else:
    from .core import MemoryContextAssembler, MemoryStore, default_memory_root, parse_time


def _time(value: str | None) -> datetime | None:
    return parse_time(value) if value else None


def command_preview(args: argparse.Namespace) -> int:
    request_path = Path(args.input).expanduser().resolve(strict=True)
    document = json.loads(request_path.read_text(encoding="utf-8"))
    manifest, payload = MemoryContextAssembler().assemble(document, _time(args.now))
    store = MemoryStore(Path(args.data_dir).expanduser() if args.data_dir else default_memory_root())
    manifest_path, payload_path = store.write(manifest, payload)
    print(json.dumps({
        "mode": "preview_only",
        "automaticInjection": False,
        "writeBack": False,
        "packId": manifest["packId"],
        "acceptedCandidates": len(manifest["candidates"]),
        "adapterStatuses": manifest["adapterStatuses"],
        "warnings": manifest["warnings"],
        "manifestPath": str(manifest_path),
        "payloadPath": str(payload_path),
    }, indent=2, sort_keys=True))
    return 0


def command_verify(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve(strict=True)
    payload_path = Path(args.payload).expanduser().resolve(strict=True)
    source_state = json.loads(
        Path(args.source_state).expanduser().resolve(strict=True).read_text()
    )
    if not isinstance(source_state, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in source_state.items()
    ):
        raise ValueError("source state must be a JSON object of sourceId to revision")
    root = Path(args.data_dir).expanduser() if args.data_dir else manifest_path.parent.parent
    result = MemoryStore(root).verify(
        manifest_path, payload_path, now=_time(args.now), source_state=source_state
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 2


def command_purge(args: argparse.Namespace) -> int:
    store = MemoryStore(Path(args.data_dir).expanduser() if args.data_dir else default_memory_root())
    print(json.dumps(store.purge(args.source_id, _time(args.now)), indent=2, sort_keys=True))
    return 0


def command_cleanup(args: argparse.Namespace) -> int:
    store = MemoryStore(Path(args.data_dir).expanduser() if args.data_dir else default_memory_root())
    print(json.dumps(store.cleanup_expired(_time(args.now)), indent=2, sort_keys=True))
    return 0


def command_awareness(args: argparse.Namespace) -> int:
    from memory_context.awareness import build_catalog, expand_catalog, read_document, render_context

    store = MemoryStore(Path(args.data_dir).expanduser() if args.data_dir else default_memory_root())
    document = read_document(Path(args.input).expanduser())
    source_state = read_document(Path(args.source_state).expanduser())
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in source_state.items()):
        raise ValueError("source state must map exact source IDs to revisions")
    if args.command == "catalog":
        manifest, payload = build_catalog(document, _time(args.now))
        accounting = {"catalogEstimatedTokens": manifest["totalEstimatedTokens"]}
    else:
        selection = read_document(Path(args.selection).expanduser())
        if set(selection) != {"memoryIds"}:
            raise ValueError("selection file must contain only memoryIds")
        manifest, payload, accounting = expand_catalog(
            store, Path(args.manifest).expanduser(), Path(args.payload).expanduser(),
            selection["memoryIds"], document,
            source_state, _time(args.now),
        )
    manifest_path, payload_path = store.write(manifest, payload)
    verification = store.verify(manifest_path, payload_path, now=_time(args.now), source_state=source_state)
    if not verification["valid"]:
        raise ValueError("awareness presentation verification failed: " + ", ".join(verification["reasons"]))
    print(json.dumps({
        "mode": "preview_only", "variant": f"awareness-{args.command}-v1",
        "automaticInjection": False, "writeBack": False,
        "packId": manifest["packId"], "manifestPath": str(manifest_path),
        "payloadPath": str(payload_path), "accounting": accounting,
        "adapterStatuses": manifest["adapterStatuses"], "warnings": manifest["warnings"],
        "context": render_context(manifest, payload),
    }, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preview = subparsers.add_parser("preview")
    preview.add_argument("--input", required=True)
    preview.add_argument("--data-dir")
    preview.add_argument("--now")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--payload", required=True)
    verify.add_argument("--source-state", required=True)
    verify.add_argument("--data-dir")
    verify.add_argument("--now")
    purge = subparsers.add_parser("purge")
    purge.add_argument("--source-id", required=True)
    purge.add_argument("--data-dir")
    purge.add_argument("--now")
    cleanup = subparsers.add_parser("cleanup-expired")
    cleanup.add_argument("--data-dir")
    cleanup.add_argument("--now")
    for name in ("catalog", "expand"):
        awareness = subparsers.add_parser(name)
        awareness.add_argument("--input", required=True)
        awareness.add_argument("--data-dir")
        awareness.add_argument("--now")
        awareness.add_argument("--source-state", required=True)
        if name == "expand":
            awareness.add_argument("--manifest", required=True)
            awareness.add_argument("--payload", required=True)
            awareness.add_argument("--selection", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return {
            "preview": lambda: command_preview(args),
            "verify": lambda: command_verify(args),
            "purge": lambda: command_purge(args),
            "cleanup-expired": lambda: command_cleanup(args),
            "catalog": lambda: command_awareness(args),
            "expand": lambda: command_awareness(args),
        }[args.command]()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
