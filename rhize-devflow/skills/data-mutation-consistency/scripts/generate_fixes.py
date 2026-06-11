#!/usr/bin/env python3
"""
Fix Generation Script

Generates fix plans and code patches for mutation issues.

Usage:
    python3 scripts/generate_fixes.py --root /path/to/project --priority P1
    python3 scripts/generate_fixes.py --root . --priority P0 --apply
    python3 scripts/generate_fixes.py --root . --file path/to/file.ts
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common.models import (
    AnalysisResult,
    MutationIssue,
    Severity,
    ProjectConfig,
)
from common.patterns import PatternMatcher, detect_sub_skills
from common.scoring import ScoreCalculator, ISSUE_DETAILS


def load_pending_issues(project_root: Path) -> list[dict]:
    """Load pending issues from analysis output."""
    pending_path = project_root / ".claude" / "analysis" / "pending-fixes.md"

    if not pending_path.exists():
        return []

    issues = []
    content = pending_path.read_text()

    # Parse markdown format
    import re
    pattern = r"\[(\w+)\]\s+`([^:]+):(\d+)`\s+-\s+(\w+):\s+(.+)"

    for match in re.finditer(pattern, content):
        severity, file_path, line, element, message = match.groups()
        issues.append({
            "severity": severity.lower(),
            "file": file_path,
            "line": int(line),
            "element": element,
            "message": message,
        })

    return issues


def run_fresh_analysis(project_root: Path) -> list[MutationIssue]:
    """Run fresh analysis and return issues."""
    from analyze_mutations import analyze_project

    config = ProjectConfig.load_from_file(project_root)
    result = analyze_project(project_root, config)
    return result.issues


def filter_by_priority(issues: list, priority: str) -> list:
    """Filter issues by priority level."""
    severity_map = {
        "P0": ["critical"],
        "P1": ["critical", "warning"],
        "P2": ["critical", "warning", "info"],
    }

    target_severities = severity_map.get(priority.upper(), ["critical", "warning"])

    if isinstance(issues[0], MutationIssue):
        return [i for i in issues if i.severity.value in target_severities]
    else:
        return [i for i in issues if i.get("severity") in target_severities]


def generate_fix_code(element: str, context: dict) -> str:
    """Generate fix code for a specific element."""
    details = ISSUE_DETAILS.get(element, {})

    if "fix_code" in details:
        # Substitute context values
        code = details["fix_code"]
        for key, value in context.items():
            code = code.replace(f"{{{key}}}", value)
        return code.strip()

    return f"// TODO: Add {element}"


def generate_fix_plan(
    project_root: Path,
    priority: str = "P1",
    target_file: Optional[Path] = None,
) -> str:
    """Generate a comprehensive fix plan."""
    timestamp = datetime.now()

    # Try to load existing pending issues first
    pending = load_pending_issues(project_root)

    if not pending:
        # Run fresh analysis
        issues = run_fresh_analysis(project_root)
        filtered = filter_by_priority(issues, priority)
    else:
        filtered = filter_by_priority(pending, priority)

    # Filter by file if specified
    if target_file:
        if isinstance(filtered[0], MutationIssue):
            filtered = [i for i in filtered if i.mutation.file_path == target_file]
        else:
            filtered = [i for i in filtered if i.get("file") == str(target_file)]

    if not filtered:
        return f"No {priority} issues found. Mutation patterns are consistent! ✅"

    # Group by file
    by_file = {}
    for issue in filtered:
        if isinstance(issue, MutationIssue):
            file_key = str(issue.mutation.file_path)
            line = issue.mutation.line_number
            element = issue.element
            message = issue.message
            fix_suggestion = issue.fix_suggestion
        else:
            file_key = issue.get("file")
            line = issue.get("line")
            element = issue.get("element")
            message = issue.get("message")
            fix_suggestion = ISSUE_DETAILS.get(element, {}).get(
                "fix_suggestion", f"Add {element}"
            )

        if file_key not in by_file:
            by_file[file_key] = []

        by_file[file_key].append({
            "line": line,
            "element": element,
            "message": message,
            "fix_suggestion": fix_suggestion,
            "fix_code": generate_fix_code(element, {"entity": "entity", "domain": "domain"}),
        })

    # Generate plan
    lines = [
        "# Mutation Fix Plan",
        "",
        f"Generated: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Priority: {priority}",
        f"Issues Found: {len(filtered)}",
        f"Files Affected: {len(by_file)}",
        "",
        "---",
        "",
    ]

    fix_num = 1
    for file_path, file_issues in sorted(by_file.items()):
        lines.extend([
            f"## {Path(file_path).name}",
            "",
            f"**Path:** `{file_path}`",
            "",
        ])

        for issue in sorted(file_issues, key=lambda x: x["line"]):
            lines.extend([
                f"### Fix {fix_num}: {issue['element']} (Line {issue['line']})",
                "",
                f"**Issue:** {issue['message']}",
                "",
                f"**Solution:** {issue['fix_suggestion']}",
                "",
            ])

            if issue["fix_code"] and not issue["fix_code"].startswith("// TODO"):
                lines.extend([
                    "**Code to add:**",
                    "```typescript",
                    issue["fix_code"],
                    "```",
                    "",
                ])

            fix_num += 1

        lines.append("---")
        lines.append("")

    # Add application instructions
    lines.extend([
        "## How to Apply",
        "",
        "### Option 1: Manual Review",
        "Review each fix above and apply changes manually.",
        "",
        "### Option 2: TODO Comments",
        "Run the following to add TODO comments to your code:",
        "```",
        f"python3 scripts/generate_fixes.py --root {project_root} --priority {priority} --add-todos",
        "```",
        "",
        "### Option 3: Apply Fixes",
        "After reviewing, apply fixes with:",
        "```",
        "@apply-fixes",
        "```",
        "",
        "---",
        "",
        "## Validation",
        "",
        "After applying fixes, run:",
        "```",
        "@analyze-mutations",
        "```",
        "",
        "Expected: All affected mutations should now score ≥ 9.0",
    ])

    return "\n".join(lines)


def add_todo_comments(project_root: Path, priority: str) -> int:
    """Add TODO comments to files with issues."""
    issues = run_fresh_analysis(project_root)
    filtered = filter_by_priority(issues, priority)

    if not filtered:
        print("No issues found to add TODOs for.")
        return 0

    # Group by file
    by_file = {}
    for issue in filtered:
        file_key = str(issue.mutation.file_path)
        if file_key not in by_file:
            by_file[file_key] = []
        by_file[file_key].append(issue)

    modified_count = 0

    for file_path, file_issues in by_file.items():
        try:
            path = Path(file_path)
            content = path.read_text()
            lines = content.split("\n")

            # Sort by line number descending to avoid offset issues
            file_issues.sort(key=lambda x: x.mutation.line_number, reverse=True)

            for issue in file_issues:
                line_idx = issue.mutation.line_number - 1
                if 0 <= line_idx < len(lines):
                    indent = len(lines[line_idx]) - len(lines[line_idx].lstrip())
                    todo_comment = (
                        f"{' ' * indent}// TODO(mutation-consistency): "
                        f"{issue.fix_suggestion} - {issue.element}"
                    )

                    # Insert TODO above the line
                    lines.insert(line_idx, todo_comment)

            # Write back
            path.write_text("\n".join(lines))
            modified_count += 1
            print(f"Added TODOs to: {file_path}")

        except Exception as e:
            print(f"Error modifying {file_path}: {e}", file=sys.stderr)

    return modified_count


def main():
    parser = argparse.ArgumentParser(
        description="Generate fix plans for mutation issues"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory",
    )
    parser.add_argument(
        "--priority",
        type=str,
        default="P1",
        choices=["P0", "P1", "P2"],
        help="Priority level (P0=critical, P1=critical+warning, P2=all)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Target specific file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file (default: .claude/analysis/fix-plan-{timestamp}.md)",
    )
    parser.add_argument(
        "--add-todos",
        action="store_true",
        help="Add TODO comments to source files instead of generating plan",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    if args.add_todos:
        count = add_todo_comments(args.root, args.priority)
        print(f"\nAdded TODO comments to {count} files.")
        return

    # Generate fix plan
    plan = generate_fix_plan(args.root, args.priority, args.file)

    if args.json:
        # For JSON output, we'd need to restructure
        print(json.dumps({"plan": plan}, indent=2))
    else:
        # Write to file or stdout
        if args.output:
            output_path = args.output
        else:
            output_dir = args.root / ".claude" / "analysis"
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            output_path = output_dir / f"fix-plan-{timestamp}.md"

        output_path.write_text(plan)
        print(f"Fix plan written to: {output_path}")

        # Also print summary
        lines = plan.split("\n")
        for line in lines[:15]:
            print(line)
        print("...")
        print(f"\nFull plan: {output_path}")


if __name__ == "__main__":
    main()
