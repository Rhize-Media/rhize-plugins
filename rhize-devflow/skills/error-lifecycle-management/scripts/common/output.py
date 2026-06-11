"""
Output helpers for validation reports.

Provides consistent report generation in JSON and Markdown formats
across all validators.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import BaseValidationReport, Issue, Severity


def output_json(
    report: BaseValidationReport,
    output_dir: Path,
    filename: str
) -> Path:
    """
    Write validation report to JSON file.

    Args:
        report: Validation report with to_dict() method
        output_dir: Directory to write report
        filename: Name of output file (e.g., 'error-coverage-report.json')

    Returns:
        Path to written file
    """
    path = output_dir / filename
    with open(path, 'w') as f:
        json.dump(report.to_dict(), f, indent=2)
    print(f"JSON report: {path}")
    return path


def output_markdown(
    report: BaseValidationReport,
    output_dir: Path,
    filename: str,
    title: str,
    custom_sections: Optional[Callable[[BaseValidationReport], str]] = None,
    max_issues: int = 30
) -> Path:
    """
    Write validation report to Markdown file.

    Args:
        report: Validation report
        output_dir: Directory to write report
        filename: Name of output file (e.g., 'error-coverage-report.md')
        title: Report title
        custom_sections: Optional function to generate custom report sections
        max_issues: Maximum number of issues to include

    Returns:
        Path to written file
    """
    status = "✅ PASSED" if report.passed else "❌ FAILED"

    md = f"""# {title}

**Generated**: {report.timestamp}
**Status**: {status}

## Summary

| Metric | Count |
|--------|-------|
| Files Scanned | {report.total_files_scanned} |
| Errors | {report.errors} |
| Warnings | {report.warnings} |

"""

    # Add custom sections if provided
    if custom_sections:
        md += custom_sections(report)

    # Add issues section
    if report.issues:
        md += "## Issues\n\n"

        # Group by severity
        errors = [i for i in report.issues if i.severity == Severity.ERROR]
        warnings = [i for i in report.issues if i.severity == Severity.WARNING]
        infos = [i for i in report.issues if i.severity == Severity.INFO]

        shown_count = 0

        if errors and shown_count < max_issues:
            md += "### ❌ Errors\n\n"
            for issue in errors[:max_issues - shown_count]:
                md += _format_issue_md(issue)
                shown_count += 1

        if warnings and shown_count < max_issues:
            md += "### ⚠️ Warnings\n\n"
            for issue in warnings[:max_issues - shown_count]:
                md += _format_issue_md(issue)
                shown_count += 1

        if infos and shown_count < max_issues:
            md += "### ℹ️ Info\n\n"
            for issue in infos[:max_issues - shown_count]:
                md += _format_issue_md(issue)
                shown_count += 1

        remaining = len(report.issues) - shown_count
        if remaining > 0:
            md += f"\n*...and {remaining} more issues*\n"

    else:
        md += "## ✅ No Issues Found\n\nAll checks passed!\n"

    path = output_dir / filename
    with open(path, 'w') as f:
        f.write(md)
    print(f"Markdown report: {path}")
    return path


def _format_issue_md(issue: Issue) -> str:
    """Format a single issue as Markdown."""
    md = f"""#### {issue.rule}
**File**: `{issue.file}:{issue.line}`

{issue.message}

"""
    if issue.code_snippet:
        md += f"""```typescript
{issue.code_snippet}
```

"""
    if issue.suggestion:
        md += f"💡 **Suggestion**: {issue.suggestion}\n\n"

    md += "---\n\n"
    return md


def print_summary_box(
    title: str,
    lines: List[str],
    passed: bool,
    width: int = 50
) -> None:
    """
    Print a formatted summary box to console.

    Args:
        title: Box title
        lines: Lines to display in box
        passed: Whether validation passed
        width: Box width in characters
    """
    print("\n" + "=" * width)
    print(title)
    print("=" * width)
    for line in lines:
        print(line)
    print(f"Status: {'✅ PASSED' if passed else '❌ FAILED'}")
    print("=" * width + "\n")
