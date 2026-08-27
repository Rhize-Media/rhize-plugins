#!/usr/bin/env python3
"""Prepare one isolated parallel-agent skill evaluation run."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARM_A = Path(
    "/Users/jamesdeola/.codex/plugins/cache/ecc/ecc/2.2.0/skills/"
    "parallel-execution-optimizer/SKILL.md"
)
ARM_B = Path(
    "/Users/jamesdeola/.codex/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/"
    "dispatching-parallel-agents/SKILL.md"
)


def file_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args()

    manifest = json.loads((ROOT / "manifest.json").read_text())
    tasks = {item["id"]: item for item in manifest["tasks"]}
    if args.task not in tasks:
        parser.error(f"unknown task: {args.task}")
    if args.variant not in manifest["variants"]:
        parser.error(f"unknown variant: {args.variant}")
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")

    source = ROOT / "tasks" / args.task
    shutil.copytree(source, args.output)
    run_id = args.run_id or f"{args.task}-{args.variant}"
    context = {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": args.task,
        "variant": args.variant,
        "expected_decision": tasks[args.task]["expected_decision"],
        "required_checks": tasks[args.task]["required_checks"],
        "initial_hashes": file_hashes(args.output / "workspace"),
    }
    task_index = [item["id"] for item in manifest["tasks"]].index(args.task)
    if args.variant == "baseline":
        skill_order: list[str] = []
        variant_instruction = (
            "Do not read or apply either candidate skill. Use only the standing host and task "
            "instructions."
        )
    elif args.variant == "arm_a":
        skill_order = [str(ARM_A)]
        variant_instruction = f"Read {ARM_A} completely before acting, then apply it to this task."
    elif args.variant == "arm_b":
        skill_order = [str(ARM_B)]
        variant_instruction = f"Read {ARM_B} completely before acting, then apply it to this task."
    else:
        skill_order = [str(ARM_A), str(ARM_B)] if task_index % 2 == 0 else [str(ARM_B), str(ARM_A)]
        variant_instruction = (
            "Read both candidate skills completely in this order before acting, then apply both: "
            + " -> ".join(skill_order)
        )
    context["skill_order"] = skill_order
    (args.output / "RUN_CONTEXT.json").write_text(json.dumps(context, indent=2) + "\n")
    shutil.copy2(ROOT / "receipt.schema.json", args.output / "RECEIPT_SCHEMA.json")
    instructions = f"""# Independent evaluation run

Work only inside `{args.output}`. Do not inspect the parent investigation report, other run
directories, or their results. The user explicitly authorizes parallel subagents when the task
benefits from them, with a maximum of two nested agents at once.

1. Record the UTC start time before task work.
2. Read `RUN_CONTEXT.json`, `TASK.md`, and `RECEIPT_SCHEMA.json` completely.
3. Variant instruction: {variant_instruction}
4. Complete the task and its checks. All writes must stay inside this run directory.
5. Write `receipt.json` matching the schema. Report only checks actually run. Agent entries cover
   nested agents, not the coordinator. Use `null` plus an honest availability reason when the host
   does not expose authoritative tool or token counts. Record collisions and rework factually.
6. Record the UTC completion time after verification. Return a concise summary.
"""
    (args.output / "RUN_INSTRUCTIONS.md").write_text(instructions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
