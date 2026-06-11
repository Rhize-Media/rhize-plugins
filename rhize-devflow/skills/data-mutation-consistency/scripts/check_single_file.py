#!/usr/bin/env python3
"""
Single File Mutation Checker

Quick pattern check for a single file.
Returns inline result without file output.

Usage:
    python3 scripts/check_single_file.py --file path/to/file.ts
    python3 scripts/check_single_file.py --file path/to/file.ts --json
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common.models import ProjectConfig, MutationCategory
from common.patterns import PatternMatcher, detect_sub_skills
from common.scoring import ScoreCalculator
from common.output import format_single_file_result


def check_file(
    file_path: Path,
    project_root: Path = None,
    sub_skills: list[str] = None,
) -> dict:
    """Check a single file for mutation patterns."""
    if not file_path.exists():
        return {
            "error": f"File not found: {file_path}",
            "score": 0,
            "status": "error",
        }

    # Determine project root
    if project_root is None:
        project_root = find_project_root(file_path)

    # Detect sub-skills if not specified
    if sub_skills is None:
        sub_skills = detect_sub_skills(project_root)

    # Read file
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "error": f"Could not read file: {e}",
            "score": 0,
            "status": "error",
        }

    # Initialize tools
    matcher = PatternMatcher(sub_skills)
    scorer = ScoreCalculator()

    # Find mutations
    mutations = matcher.find_mutations(file_path, content)

    # Check for React Query mutations
    if "react-query-mutations" in sub_skills:
        rq_mutations = matcher.find_react_query_mutations(file_path, content)
        mutations.extend(rq_mutations)

    # Check for Payload collections
    if "payload-cms-hooks" in sub_skills:
        payload_mutations = matcher.find_payload_collections(file_path, content)
        mutations.extend(payload_mutations)

    if not mutations:
        return {
            "file": str(file_path),
            "mutations_found": 0,
            "score": 10.0,
            "status": "no_mutations",
            "message": "No mutations found in this file",
        }

    # Score mutations
    scores = []
    all_issues = []

    for mutation in mutations:
        score = scorer.score_mutation(mutation)
        scores.append(score)
        all_issues.extend(score.issues)

    # Calculate overall file score
    avg_score = sum(s.final_score for s in scores) / len(scores)

    # Determine status
    if avg_score >= 9.0:
        status = "passing"
    elif avg_score >= 7.0:
        status = "warning"
    else:
        status = "critical"

    # Build result
    result = {
        "file": str(file_path),
        "mutations_found": len(mutations),
        "score": round(avg_score, 1),
        "status": status,
        "mutations": [],
    }

    for score in scores:
        result["mutations"].append({
            "line": score.mutation.line_number,
            "type": score.mutation.mutation_type,
            "entity": score.mutation.table_or_entity,
            "score": score.final_score,
            "present": score.elements_present,
            "missing": score.elements_missing,
        })

    # Add issues summary
    result["issues"] = [
        {
            "element": i.element,
            "severity": i.severity.value,
            "message": i.message,
            "fix": i.fix_suggestion,
        }
        for i in all_issues
    ]

    return result


def find_project_root(file_path: Path) -> Path:
    """Find project root by looking for package.json."""
    current = file_path.parent

    while current != current.parent:
        if (current / "package.json").exists():
            return current
        current = current.parent

    return file_path.parent


def format_output(result: dict) -> str:
    """Format result for human-readable output."""
    if "error" in result:
        return f"❌ Error: {result['error']}"

    if result["status"] == "no_mutations":
        return f"ℹ️ {result['file']}: No mutations found"

    # Status emoji
    status_emoji = {
        "passing": "✅",
        "warning": "⚠️",
        "critical": "❌",
    }.get(result["status"], "❓")

    lines = [
        f"**{Path(result['file']).name}** - Score: {result['score']}/10 {status_emoji}",
        "",
    ]

    # Mutation details
    for mutation in result["mutations"]:
        present = ", ".join(mutation["present"][:3])
        missing = ", ".join(mutation["missing"][:3])

        lines.append(
            f"  Line {mutation['line']}: {mutation['entity']} ({mutation['type']}) - {mutation['score']}/10"
        )
        if present:
            lines.append(f"    ✅ {present}")
        if missing:
            lines.append(f"    ❌ {missing}")

    # Top fixes
    if result["issues"]:
        lines.extend([
            "",
            "**Fixes needed:**",
        ])
        for issue in result["issues"][:3]:
            severity_icon = {
                "critical": "🔴",
                "warning": "🟡",
                "info": "🔵",
            }.get(issue["severity"], "")
            lines.append(f"  {severity_icon} {issue['fix']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Check a single file for mutation patterns"
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="File to check",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root (auto-detected if not specified)",
    )
    parser.add_argument(
        "--sub-skills",
        type=str,
        default=None,
        help="Comma-separated list of sub-skills",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    # Parse sub-skills
    sub_skills = None
    if args.sub_skills:
        sub_skills = [s.strip() for s in args.sub_skills.split(",")]

    # Run check
    result = check_file(args.file, args.root, sub_skills)

    # Output
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_output(result))

    # Exit code based on status
    if result.get("status") == "critical":
        sys.exit(2)
    elif result.get("status") == "warning":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
