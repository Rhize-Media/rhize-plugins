#!/usr/bin/env python3
"""record_provenance.py — Maintain the SOURCES.md ingestion ledger + a vault note stub.

Appends a structured provenance entry to <skills-root>/SOURCES.md and (optionally) writes a
companion Obsidian note stub so the decision lives in the second brain. Supports --check-drift
to list absorbed sources and their stored upstream refs / drift-check commands.

Stdlib only.

Usage (record):
    python3 record_provenance.py --source URL --name NAME --version V --license L \
        --verb ABSORB --target rhize-skill --took "what" --skills-root ROOT [--vault DIR]

Usage (drift):
    python3 record_provenance.py --check-drift --skills-root ROOT
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

VERBS = {"DEFER", "ABSORB", "FORK", "REJECT", "WATCH"}


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def record(args) -> None:
    if args.verb not in VERBS:
        fail(f"--verb must be one of {sorted(VERBS)}")
    root = Path(os.path.expanduser(args.skills_root)).resolve()
    if not root.is_dir():
        fail(f"skills-root not a directory: {root}")

    today = dt.date.today().isoformat()
    drift_cmd = args.drift_check or f"# define how to detect upstream change for {args.name}"
    entry = (
        f"\n## {args.name} — {today}\n"
        f"- **Source:** {args.source}\n"
        f"- **Upstream ref:** {args.version or 'n/a'}\n"
        f"- **License:** {args.license or 'UNKNOWN'}\n"
        f"- **Verb:** {args.verb}\n"
        f"- **Target:** {args.target or 'n/a'}\n"
        f"- **Took:** {args.took or 'nothing'}\n"
        f"- **Verified:** {args.verified or 'n/a'}\n"
        f"- **Drift check:** `{drift_cmd}`\n"
        f"- **Notes:** {args.notes or ''}\n"
    )

    ledger = root / "SOURCES.md"
    if not ledger.exists():
        ledger.write_text("# Rhize Skill Forge — Provenance Ledger\n\n"
                          "One entry per external-skill ingestion decision.\n")
    with ledger.open("a", encoding="utf-8") as f:
        f.write(entry)
    print(f"✓ appended ledger entry to {ledger}")

    if args.vault:
        vault = Path(os.path.expanduser(args.vault)).resolve()
        vault.mkdir(parents=True, exist_ok=True)
        note = vault / f"forge-{slug(args.name)}-{today}.md"
        note.write_text(
            f"---\n"
            f"type: skill-forge-decision\n"
            f"date: {today}\n"
            f"tags: [skill-forge, provenance, '{args.verb.lower()}']\n"
            f"source: {args.source}\n"
            f"license: {args.license or 'UNKNOWN'}\n"
            f"---\n\n"
            f"# Forge decision: {args.name}\n\n"
            f"**Verb:** {args.verb}  ·  **Target:** {args.target or 'n/a'}\n\n"
            f"## What was taken\n{args.took or 'nothing'}\n\n"
            f"## Why\n{args.notes or ''}\n\n"
            f"## Verification\n{args.verified or 'n/a'}\n\n"
            f"## Drift check\n`{drift_cmd}`\n\n"
            f"Related: [[rhize-skill-forge]] · [[{args.target}]]\n" if args.target else
            f"Related: [[rhize-skill-forge]]\n"
        )
        print(f"✓ wrote vault note {note}")


def check_drift(args) -> None:
    root = Path(os.path.expanduser(args.skills_root)).resolve()
    ledger = root / "SOURCES.md"
    if not ledger.exists():
        fail(f"no ledger at {ledger}")
    text = ledger.read_text()
    blocks = re.split(r"\n## ", text)
    rows = []
    for b in blocks[1:]:
        name = b.splitlines()[0].split(" — ")[0]
        verb = (re.search(r"\*\*Verb:\*\*\s*(\w+)", b) or [None, "?"])[1]
        ref = (re.search(r"\*\*Upstream ref:\*\*\s*(.+)", b) or [None, "?"])[1]
        cmd = (re.search(r"\*\*Drift check:\*\*\s*`([^`]*)`", b) or [None, ""])[1]
        if verb in ("REJECT",):
            continue
        rows.append((name, verb, ref.strip(), cmd))
    if not rows:
        print("No tracked (non-REJECT) sources in ledger.")
        return
    print("Tracked sources to drift-check against upstream:\n")
    for name, verb, ref, cmd in rows:
        print(f"  • {name}  [{verb}]  ref={ref}")
        if cmd:
            print(f"      run: {cmd}")
    print("\nCompare each stored ref to current upstream; re-run forge on any that moved.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Record provenance / check drift for ingested skills.")
    ap.add_argument("--skills-root", required=True)
    ap.add_argument("--check-drift", action="store_true")
    ap.add_argument("--source")
    ap.add_argument("--name")
    ap.add_argument("--version")
    ap.add_argument("--license")
    ap.add_argument("--verb")
    ap.add_argument("--target")
    ap.add_argument("--took")
    ap.add_argument("--verified")
    ap.add_argument("--notes")
    ap.add_argument("--drift-check", help="command string that detects upstream change")
    ap.add_argument("--vault", help="vault dir to also write a note stub into")
    args = ap.parse_args()

    if args.check_drift:
        check_drift(args)
    else:
        if not (args.source and args.name and args.verb):
            fail("recording requires --source, --name, and --verb")
        record(args)


if __name__ == "__main__":
    main()
