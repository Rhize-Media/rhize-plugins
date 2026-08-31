#!/usr/bin/env python3
"""Prepare one isolated v2 baseline-versus-Rhize evaluation run."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def canonical_uuid(value: str, label: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be a UUID") from exc
    if str(parsed) != value.lower():
        raise argparse.ArgumentTypeError(f"{label} must be canonical lowercase")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--comparison-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args()

    manifest = json.loads((ROOT / "manifest.json").read_text())
    tasks = {item["id"]: item for item in manifest["tasks"]}
    if args.task not in tasks:
        parser.error(f"unknown task: {args.task}")
    if args.variant not in manifest["variants"]:
        parser.error(f"unknown variant: {args.variant}")
    if not 1 <= args.repetition <= manifest["repetitions"]:
        parser.error(f"repetition must be between 1 and {manifest['repetitions']}")
    try:
        comparison_id = canonical_uuid(args.comparison_id, "comparison-id")
        run_id = canonical_uuid(args.run_id, "run-id") if args.run_id else str(uuid.uuid4())
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")

    source = ROOT / "tasks" / args.task
    shutil.copytree(source, args.output)
    started_at = datetime.now(timezone.utc).isoformat()
    task = tasks[args.task]
    context = {
        "schema_version": 2,
        "run_id": run_id,
        "comparison_id": comparison_id,
        "task_id": args.task,
        "task_class": task["task_class"],
        "variant": args.variant,
        "repetition": args.repetition,
        "expected_decision": task["expected_decision"],
        "required_checks": task["required_checks"],
        "initial_hashes": file_hashes(args.output / "workspace"),
    }
    reservation = {
        key: context[key]
        for key in (
            "schema_version", "run_id", "comparison_id", "task_id", "task_class", "variant",
            "repetition", "expected_decision"
        )
    }
    reservation.update({"status": "pending", "started_at": started_at})
    (args.output / "RUN_CONTEXT.json").write_text(json.dumps(context, indent=2) + "\n")
    (args.output / "RUN_RESERVATION.json").write_text(json.dumps(reservation, indent=2) + "\n")
    shutil.copy2(ROOT / "receipt.schema.json", args.output / "RECEIPT_SCHEMA.json")

    if args.variant == "baseline":
        variant_instruction = (
            "Use only standing host and task instructions. Do not invoke the Rhize routing skill."
        )
    else:
        variant_instruction = (
            "Apply the Rhize self-contained routing strategy from "
            "rhize-ops:parallel-agent-optimization; do not load any vendor parallel-agent skill."
        )
    instructions = f"""# Independent controlled evaluation run

Work only inside this prepared run directory. Do not inspect other run directories or results.
The user authorizes at most two nested agents when the deterministic fixture benefits from them.

1. Read `RUN_CONTEXT.json`, `RUN_RESERVATION.json`, `TASK.md`, and `RECEIPT_SCHEMA.json`.
2. Variant instruction: {variant_instruction}
3. Record factual timezone-aware start/completion and nested-agent intervals.
4. Complete the fixture and its checks. Keep all writes inside this run directory.
5. Write provisional `receipt.json` matching `RECEIPT_SCHEMA.json`. Use null plus an allowed
   availability reason for authoritative tool/token counts the host does not expose. Never estimate.
6. Run `grade_run.py` for this directory. The grader owns observable checks and always finalizes
   the accepted reservation as completed, failed, or incomplete.

Receipt data contains no prompts, code, commands, source paths, names, URLs, or external IDs.
"""
    (args.output / "RUN_INSTRUCTIONS.md").write_text(instructions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
