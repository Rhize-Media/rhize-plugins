#!/usr/bin/env python3
"""
Zen MCP Memory Integration for Data Mutation Consistency Skill

This module provides utilities to store and retrieve mutation analysis
results using Zen MCP memory for cross-session awareness.

The memory integration allows:
- Storing analysis results after each run
- Recalling previous findings in new sessions
- Tracking improvement trends over time
- Maintaining context about known issues

Usage:
    python3 scripts/zen_memory.py --store --report-path .claude/analysis/mutation-report-2024-12-05.md
    python3 scripts/zen_memory.py --recall
    python3 scripts/zen_memory.py --summary
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class MutationMemory:
    """Memory structure for mutation analysis results."""
    timestamp: str
    overall_score: float
    total_mutations: int
    passing_count: int
    warning_count: int
    critical_count: int
    top_issues: list[dict]
    affected_files: list[str]
    sub_skills_active: list[str]
    report_path: str


def parse_report_for_memory(report_path: str) -> Optional[MutationMemory]:
    """
    Parse a mutation report file and extract key information for memory storage.

    Args:
        report_path: Path to the mutation report markdown file

    Returns:
        MutationMemory object with extracted information, or None if parsing fails
    """
    try:
        with open(report_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Report not found: {report_path}", file=sys.stderr)
        return None

    # Extract overall score
    score_match = re.search(r"Overall Score[:\s|]+(\d+\.?\d*)/10", content)
    overall_score = float(score_match.group(1)) if score_match else 0.0

    # Extract counts
    total_match = re.search(r"Mutations Analyzed[:\s|]+(\d+)", content)
    total_mutations = int(total_match.group(1)) if total_match else 0

    passing_match = re.search(r"Passing[:\s|]+(\d+)", content)
    passing_count = int(passing_match.group(1)) if passing_match else 0

    warning_match = re.search(r"Warnings?[:\s|]+(\d+)", content)
    warning_count = int(warning_match.group(1)) if warning_match else 0

    critical_match = re.search(r"Critical[:\s|]+(\d+)", content)
    critical_count = int(critical_match.group(1)) if critical_match else 0

    # Extract top issues (P0 and P1)
    top_issues = []
    issue_pattern = re.compile(
        r"[-•]\s*(?:🚨|⚠️)?\s*(.+?)\s*\(([^)]+)\)",
        re.MULTILINE
    )
    for match in issue_pattern.finditer(content):
        issue_desc = match.group(1).strip()
        file_ref = match.group(2).strip()
        if len(top_issues) < 5:  # Limit to top 5 issues
            top_issues.append({
                "description": issue_desc,
                "location": file_ref
            })

    # Extract affected files
    affected_files = []
    file_pattern = re.compile(r"(app/[^\s]+\.ts|hooks/[^\s]+\.ts)")
    for match in file_pattern.finditer(content):
        file_path = match.group(1)
        if file_path not in affected_files:
            affected_files.append(file_path)

    # Detect sub-skills mentioned
    sub_skills = []
    if "react-query" in content.lower() or "tanstack" in content.lower():
        sub_skills.append("react-query-mutations")
    if "payload" in content.lower():
        sub_skills.append("payload-cms-hooks")

    return MutationMemory(
        timestamp=datetime.now().isoformat(),
        overall_score=overall_score,
        total_mutations=total_mutations,
        passing_count=passing_count,
        warning_count=warning_count,
        critical_count=critical_count,
        top_issues=top_issues,
        affected_files=affected_files[:10],  # Limit to 10 files
        sub_skills_active=sub_skills,
        report_path=report_path
    )


def format_for_zen_chat(memory: MutationMemory) -> str:
    """
    Format memory data for storage via Zen MCP chat tool.

    This creates a concise, structured prompt that can be sent to
    mcp__zen__chat for storage in the memory system.

    Args:
        memory: MutationMemory object to format

    Returns:
        Formatted string for Zen chat storage
    """
    lines = [
        "Store mutation analysis results for cross-session awareness:",
        "",
        f"**Analysis Date:** {memory.timestamp}",
        f"**Overall Score:** {memory.overall_score}/10",
        f"**Status:** {'⚠️ Needs attention' if memory.warning_count + memory.critical_count > 0 else '✅ Healthy'}",
        "",
        "**Mutation Counts:**",
        f"  - Total: {memory.total_mutations}",
        f"  - Passing: {memory.passing_count}",
        f"  - Warnings: {memory.warning_count}",
        f"  - Critical: {memory.critical_count}",
        "",
    ]

    if memory.top_issues:
        lines.append("**Top Issues:**")
        for i, issue in enumerate(memory.top_issues[:3], 1):
            lines.append(f"  {i}. {issue['description']} ({issue['location']})")
        lines.append("")

    if memory.affected_files:
        lines.append("**Key Files Needing Attention:**")
        for f in memory.affected_files[:5]:
            lines.append(f"  - {f}")
        lines.append("")

    if memory.sub_skills_active:
        lines.append(f"**Active Sub-Skills:** {', '.join(memory.sub_skills_active)}")
        lines.append("")

    lines.append(f"**Full Report:** {memory.report_path}")

    return "\n".join(lines)


def format_recall_prompt() -> str:
    """
    Format a prompt to recall previous mutation analysis from Zen memory.

    Returns:
        Formatted prompt string for Zen chat recall
    """
    return """Recall previous mutation analysis results for this project.

What were the findings from the last mutation consistency analysis?
Include:
- Overall score
- Number of issues found
- Top issues that need attention
- Any patterns or recurring problems

If no previous analysis exists, indicate that this would be the first run."""


def format_trend_prompt() -> str:
    """
    Format a prompt to analyze mutation consistency trends.

    Returns:
        Formatted prompt string for trend analysis
    """
    return """Analyze mutation consistency trends for this project.

Based on stored analysis results:
1. Has the overall score improved or declined?
2. Are there recurring issues that keep appearing?
3. Which files have the most persistent problems?
4. What patterns emerge in the issues found?

Provide a brief trend summary with recommendations."""


def create_zen_integration_guide() -> str:
    """
    Create a guide for integrating with Zen MCP in the skill workflow.

    Returns:
        Markdown guide for Zen integration
    """
    return '''# Zen MCP Memory Integration Guide

## Overview

The Data Mutation Consistency skill integrates with Zen MCP to maintain
cross-session awareness of mutation analysis results.

## Storage Pattern

After running `@analyze-mutations`, store results:

```python
# In analyze_mutations.py, after generating report:
from zen_memory import parse_report_for_memory, format_for_zen_chat

memory = parse_report_for_memory(report_path)
zen_prompt = format_for_zen_chat(memory)

# Claude then calls:
# mcp__zen__chat(prompt=zen_prompt, model="gemini-2.5-flash", ...)
```

## Recall Pattern

At session start or when investigating issues:

```python
from zen_memory import format_recall_prompt

# Claude calls:
# mcp__zen__chat(prompt=format_recall_prompt(), model="gemini-2.5-flash", ...)
```

## Workflow Integration

### 1. After Analysis
```
@analyze-mutations
→ Report generated
→ Store key findings in Zen memory
→ Future sessions can recall context
```

### 2. New Session Start
```
User mentions mutations or stale data
→ Recall previous analysis from Zen
→ Provide context-aware suggestions
```

### 3. Trend Tracking
```
Multiple analyses over time
→ Zen maintains history
→ Can identify patterns and improvements
```

## Memory Schema

```json
{
  "timestamp": "2024-12-05T14:30:00",
  "overall_score": 8.2,
  "total_mutations": 25,
  "passing_count": 18,
  "warning_count": 5,
  "critical_count": 2,
  "top_issues": [
    {"description": "Missing error handling", "location": "app/actions/players.ts"}
  ],
  "affected_files": ["app/actions/players.ts", "hooks/useUpdateTeam.ts"],
  "sub_skills_active": ["react-query-mutations"],
  "report_path": ".claude/analysis/mutation-report-2024-12-05.md"
}
```

## Benefits

1. **Cross-Session Continuity**: Don't lose context between sessions
2. **Trend Awareness**: Track improvement over time
3. **Proactive Suggestions**: Recall known issues when relevant
4. **Reduced Re-Analysis**: Reference previous findings instead of re-running
'''


def main():
    parser = argparse.ArgumentParser(
        description="Zen MCP memory integration for mutation analysis"
    )
    parser.add_argument(
        "--store",
        action="store_true",
        help="Format analysis for storage in Zen memory"
    )
    parser.add_argument(
        "--recall",
        action="store_true",
        help="Generate recall prompt for Zen memory"
    )
    parser.add_argument(
        "--trends",
        action="store_true",
        help="Generate trend analysis prompt"
    )
    parser.add_argument(
        "--report-path",
        help="Path to mutation report file (for --store)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--guide",
        action="store_true",
        help="Show integration guide"
    )

    args = parser.parse_args()

    if args.guide:
        print(create_zen_integration_guide())
        return

    if args.store:
        if not args.report_path:
            print("Error: --report-path required for --store", file=sys.stderr)
            sys.exit(1)

        memory = parse_report_for_memory(args.report_path)
        if not memory:
            sys.exit(1)

        if args.json:
            print(json.dumps(asdict(memory), indent=2))
        else:
            print(format_for_zen_chat(memory))

    elif args.recall:
        print(format_recall_prompt())

    elif args.trends:
        print(format_trend_prompt())

    else:
        # Demo mode
        print("Zen Memory Integration - Demo", file=sys.stderr)
        print("", file=sys.stderr)
        print("Usage:", file=sys.stderr)
        print("  --store --report-path <path>  : Format report for Zen storage", file=sys.stderr)
        print("  --recall                      : Generate recall prompt", file=sys.stderr)
        print("  --trends                      : Generate trend analysis prompt", file=sys.stderr)
        print("  --guide                       : Show integration guide", file=sys.stderr)
        print("", file=sys.stderr)

        # Show example recall prompt
        print("Example recall prompt:")
        print("-" * 40)
        print(format_recall_prompt())


if __name__ == "__main__":
    main()
