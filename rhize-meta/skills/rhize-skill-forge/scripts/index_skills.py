#!/usr/bin/env python3
"""index_skills.py — Build the Rhize skill capability registry.

Scans a skills-root for SKILL.md files, reads the capability frontmatter
(tier / domain / consumes / provenance / maturity — see references/capability-schema.md),
and optionally joins usage counts from a skill-monitor snapshot. Emits registry.json
(or a human summary) and flags untagged entries (rot detection).

This is the *set-level* counterpart to profile_skill.py (which profiles one candidate).
Stdlib only. Fails loudly.

Usage:
    python3 index_skills.py --skills-root <root> [--usage-snapshot <snap.json>] \
        [--out registry.json] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

TIERS = {"resource", "custom"}
MATURITIES = {"seedling", "stable", "deprecated"}


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_list(block: str, key: str) -> list:
    """Parse a YAML list value, inline (`key: [a, b]`) or block (`- a` lines)."""
    m = re.search(rf"^{key}:\s*\[(.*?)\]\s*$", block, re.M)
    if m:
        return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
    if not re.search(rf"^{key}:\s*$", block, re.M):
        return []
    out, lines = [], block.splitlines()
    idx = next(i for i, l in enumerate(lines) if re.match(rf"^{key}:\s*$", l))
    for l in lines[idx + 1:]:
        ml = re.match(r"^\s*-\s*(.+)$", l)
        if ml:
            out.append(ml.group(1).strip().strip("'\""))
        elif l.strip() == "":
            continue
        else:
            break
    return out


def parse_frontmatter(text: str, fallback_name: str) -> tuple:
    """Return (fields_dict, valid_frontmatter_bool)."""
    fm = {"name": fallback_name, "description": "", "consumes": []}
    if not text.startswith("---\n"):
        return fm, False
    block = text.split("---", 2)[1]
    for key in ("name", "tier", "domain", "provenance", "maturity"):
        m = re.search(rf"^{key}:\s*(.+)$", block, re.M)
        if m:
            fm[key] = m.group(1).strip().strip("'\"")
    fm["consumes"] = parse_list(block, "consumes")
    m = re.search(r"^description:\s*(.*)$", block, re.M)
    if m:
        first = m.group(1).strip()
        if first in (">", ">-", "|", "|-", ""):
            lines = block.splitlines()
            idx = next(i for i, l in enumerate(lines) if re.match(r"^description:", l))
            buf = []
            for l in lines[idx + 1:]:
                if re.match(r"^\s+\S", l):
                    buf.append(l.strip())
                elif l.strip() == "":
                    continue
                else:
                    break
            fm["description"] = " ".join(buf).strip()
        else:
            fm["description"] = first.strip("'\"")
    return fm, True


def load_usage(snap_path: str) -> dict:
    """Join usage from a skill-monitor snapshot's report.top_skills (best-effort)."""
    try:
        d = json.loads(Path(os.path.expanduser(snap_path)).read_text(errors="ignore"))
    except Exception as e:  # noqa: BLE001 — best-effort, never fatal
        print(f"WARN: could not read usage snapshot ({e}); proceeding without usage", file=sys.stderr)
        return {}
    top = (d.get("report") or {}).get("top_skills") or []
    usage: dict = {}
    for row in top:
        if isinstance(row, list) and len(row) == 2:
            name, count = row
            usage[name] = count
            if isinstance(name, str) and ":" in name:
                usage.setdefault(name.split(":")[-1], count)  # bare-slug fallback for `plugin:skill`
    return usage


def find_skill_mds(root: Path) -> list:
    globs = ("*/SKILL.md", "skills/*/SKILL.md", "*/skills/*/SKILL.md")
    found: set = set()
    for g in globs:
        found |= set(root.glob(g))
    return sorted(p for p in found if "/.git/" not in str(p))


def build_registry(root: Path, usage: dict) -> dict:
    skill_mds = find_skill_mds(root)
    if not skill_mds:
        fail(f"no SKILL.md found under {root}")

    skills, untagged, warnings = [], [], []
    for p in skill_mds:
        fm, valid = parse_frontmatter(p.read_text(errors="ignore"), p.parent.name)
        name = fm.get("name", p.parent.name)
        tier = fm.get("tier")
        maturity = fm.get("maturity")
        if tier and tier not in TIERS:
            warnings.append(f"{name}: tier '{tier}' not in {sorted(TIERS)}")
        if maturity and maturity not in MATURITIES:
            warnings.append(f"{name}: maturity '{maturity}' not in {sorted(MATURITIES)}")
        entry = {
            "name": name,
            "path": str(p),
            "tier": tier,
            "domain": fm.get("domain"),
            "consumes": fm.get("consumes", []),
            "provenance": fm.get("provenance"),
            "maturity": maturity,
            "valid_frontmatter": valid,
            "usage": usage.get(name),
        }
        skills.append(entry)
        missing = [f for f in ("tier", "domain") if not entry.get(f)]
        if missing:
            untagged.append({"name": name, "missing": missing})

    by_tier: dict = {}
    by_domain: dict = {}
    for s in skills:
        by_tier[s["tier"] or "untagged"] = by_tier.get(s["tier"] or "untagged", 0) + 1
        by_domain[s["domain"] or "untagged"] = by_domain.get(s["domain"] or "untagged", 0) + 1

    return {
        "skills_root": str(root),
        "count": len(skills),
        "by_tier": by_tier,
        "by_domain": by_domain,
        "untagged": untagged,
        "warnings": warnings,
        "usage_joined": bool(usage),
        "skills": skills,
    }


def main() -> None:
    try:  # ASCII-locale safety for the human-readable output path (e.g. LANG=C cron)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Build the Rhize skill capability registry.")
    ap.add_argument("--skills-root", required=True)
    ap.add_argument("--usage-snapshot", help="skill-monitor snapshot JSON to join usage from")
    ap.add_argument("--out", help="write registry JSON to this path")
    ap.add_argument("--json", action="store_true", help="print registry JSON to stdout")
    args = ap.parse_args()

    root = Path(os.path.expanduser(args.skills_root)).resolve()
    if not root.is_dir():
        fail(f"skills-root not a directory: {root}")

    usage = load_usage(args.usage_snapshot) if args.usage_snapshot else {}
    reg = build_registry(root, usage)
    if usage and not any(s["usage"] is not None for s in reg["skills"]):
        print("WARN: usage snapshot loaded but 0 skills matched by name — registry `name:` vs "
              "telemetry key mismatch; the usage column will be empty", file=sys.stderr)

    if args.out:
        Path(os.path.expanduser(args.out)).write_text(json.dumps(reg, indent=2))
        print(f"✓ wrote registry ({reg['count']} skills, {len(reg['untagged'])} untagged) "
              f"to {args.out}", file=sys.stderr)

    if args.json:
        print(json.dumps(reg, indent=2))
        return

    print(f"Registry: {reg['count']} skills under {root}")
    print(f"  by tier:   {reg['by_tier']}")
    print(f"  by domain: {reg['by_domain']}")
    print(f"  usage joined: {reg['usage_joined']}")
    print(f"  untagged (missing tier/domain): {len(reg['untagged'])}")
    for u in reg["untagged"][:30]:
        print(f"    - {u['name']}: missing {', '.join(u['missing'])}")
    if reg["warnings"]:
        print("  warnings:")
        for w in reg["warnings"]:
            print(f"    ! {w}")


if __name__ == "__main__":
    main()
