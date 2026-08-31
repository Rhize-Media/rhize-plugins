#!/usr/bin/env python3
"""Reserve one isolated baseline/Superpowers/Rhize comparison group."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def canonical_uuid(value: str) -> str:
    parsed = uuid.UUID(value)
    if str(parsed) != value.lower():
        raise ValueError("comparison-id must be a canonical lowercase UUID")
    return value


def guide_identity(path: Path, expected_name: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    if not re.search(rf"(?m)^name:\s*{re.escape(expected_name)}\s*$", text):
        raise ValueError(f"guide must have frontmatter name: {expected_name}")
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--comparison-id", required=True)
    parser.add_argument("--superpowers-guide", type=Path, required=True)
    parser.add_argument("--rhize-guide", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    comparison_manifest = json.loads((ROOT / "guide-comparison.manifest.json").read_text())
    fixture_manifest = json.loads((ROOT / comparison_manifest["fixture_manifest"]).read_text())
    tasks = {item["id"]: item for item in fixture_manifest["tasks"]}
    if args.task not in tasks:
        parser.error(f"unknown task: {args.task}")
    if str(args.repetition) not in comparison_manifest["order_by_repetition"]:
        parser.error("repetition must be 1, 2, or 3")
    try:
        comparison_id = canonical_uuid(args.comparison_id)
        superpowers_text, superpowers_hash = guide_identity(args.superpowers_guide, "dispatching-parallel-agents")
        rhize_text, rhize_hash = guide_identity(args.rhize_guide, "parallel-agent-optimization")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")

    task = tasks[args.task]
    order = comparison_manifest["order_by_repetition"][str(args.repetition)]
    identities = {"baseline": None, "superpowers": superpowers_hash, "rhize": rhize_hash}
    guide_text = {"superpowers": superpowers_text, "rhize": rhize_text}
    started_at = datetime.now(timezone.utc).isoformat()
    args.output.mkdir(parents=True)
    reservation = {
        "schema_version": "rhize-guide-comparison-reservation-v1",
        "comparison_id": comparison_id,
        "task_id": args.task,
        "task_class": task["task_class"],
        "repetition": args.repetition,
        "status": "pending",
        "started_at": started_at,
        "order": order,
        "guide_sha256": identities,
        "isolated": True,
        "live_mutation": False,
        "feeds_rhize_v2_readiness": False,
    }
    (args.output / "GROUP_RESERVATION.json").write_text(json.dumps(reservation, indent=2) + "\n")
    shutil.copy2(ROOT / "guide-comparison-receipt.schema.json", args.output / "RECEIPT_SCHEMA.json")

    for position, variant in enumerate(order, start=1):
        run_dir = args.output / f"{position}-{variant}"
        shutil.copytree(ROOT / "tasks" / args.task, run_dir)
        if variant in guide_text:
            (run_dir / "GUIDE_SNAPSHOT.md").write_text(guide_text[variant], encoding="utf-8")
        context = {
            "schema_version": "rhize-guide-comparison-context-v1",
            "run_id": str(uuid.uuid4()),
            "comparison_id": comparison_id,
            "variant": variant,
            "guide_sha256": identities[variant],
            "task_id": args.task,
            "task_class": task["task_class"],
            "repetition": args.repetition,
            "order_position": position,
            "expected_decision": task["expected_decision"],
        }
        (run_dir / "RUN_CONTEXT.json").write_text(json.dumps(context, indent=2) + "\n")
        if variant == "baseline":
            instruction = "Use standing host instructions and TASK.md only. Do not load either guide."
        else:
            instruction = "Use GUIDE_SNAPSHOT.md as the sole parallel-agent guide; do not load the other guide."
        (run_dir / "RUN_INSTRUCTIONS.md").write_text(
            "# Isolated guide-comparison run\n\n"
            "Work only in this run directory and do not inspect sibling runs or results. "
            "Complete runs sequentially in the reservation order.\n\n"
            f"Variant actually assigned: `{variant}`. {instruction}\n\n"
            "Record only factual common metrics in receipt.json. Unknown tool/token counters remain null with an allowed reason. "
            "Do not include prompts, code, commands, paths, names, URLs, session IDs, or issue IDs.\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
