#!/usr/bin/env python3
"""
Sentry Integration for Data Mutation Consistency Skill

This module provides utilities to detect stale data issues from Sentry
and cross-reference them with mutation analysis results.

Usage:
    python3 scripts/sentry_integration.py --issue-url "https://sentry.io/..."
    python3 scripts/sentry_integration.py --check-recent --org "my-org" --project "my-project"
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class StaleDataIndicator(Enum):
    """Indicators that suggest stale data issues."""
    CACHE_MISMATCH = "cache_mismatch"
    OUTDATED_DISPLAY = "outdated_display"
    SYNC_FAILURE = "sync_failure"
    REVALIDATION_MISSING = "revalidation_missing"
    OPTIMISTIC_ROLLBACK = "optimistic_rollback"


@dataclass
class StaleDataSignal:
    """A detected signal that may indicate stale data."""
    indicator: StaleDataIndicator
    confidence: float  # 0.0 - 1.0
    context: str
    suggested_tables: list[str]
    suggested_action: str


# Patterns that suggest stale data issues in error messages/contexts
STALE_DATA_PATTERNS = {
    # Cache-related patterns
    r"stale\s+data": StaleDataIndicator.CACHE_MISMATCH,
    r"cache\s+(miss|stale|outdated)": StaleDataIndicator.CACHE_MISMATCH,
    r"data\s+(not\s+)?updated?": StaleDataIndicator.OUTDATED_DISPLAY,
    r"out\s+of\s+sync": StaleDataIndicator.SYNC_FAILURE,
    r"showing\s+old": StaleDataIndicator.OUTDATED_DISPLAY,

    # Mutation-related patterns
    r"mutation\s+(failed|error)": StaleDataIndicator.SYNC_FAILURE,
    r"update\s+(not\s+)?reflect(ed|ing)?": StaleDataIndicator.OUTDATED_DISPLAY,
    r"changes?\s+(not\s+)?appear(ing)?": StaleDataIndicator.OUTDATED_DISPLAY,

    # Revalidation patterns
    r"revalidat(e|ion)\s+(miss|fail|error)": StaleDataIndicator.REVALIDATION_MISSING,
    r"invalidat(e|ion)\s+(miss|fail|error)": StaleDataIndicator.REVALIDATION_MISSING,

    # Optimistic update patterns
    r"optimistic\s+(update\s+)?(rollback|fail)": StaleDataIndicator.OPTIMISTIC_ROLLBACK,
    r"rollback\s+(error|fail)": StaleDataIndicator.OPTIMISTIC_ROLLBACK,
}

# Table name extraction patterns
TABLE_PATTERNS = [
    r"from\s*\(\s*['\"](\w+)['\"]",  # Supabase from('table')
    r"table[:\s]+['\"]?(\w+)['\"]?",  # table: 'name' or table name
    r"collection[:\s]+['\"]?(\w+)['\"]?",  # collection: 'name'
    r"/api/(\w+)",  # API route patterns
    r"revalidateTag\s*\(\s*['\"](\w+)['\"]",  # revalidateTag('name')
]


def analyze_issue_for_stale_data(
    title: str,
    message: str,
    stacktrace: Optional[str] = None,
    tags: Optional[dict] = None
) -> list[StaleDataSignal]:
    """
    Analyze a Sentry issue for indicators of stale data problems.

    Args:
        title: Issue title
        message: Error message
        stacktrace: Optional stack trace
        tags: Optional Sentry tags

    Returns:
        List of detected stale data signals
    """
    signals: list[StaleDataSignal] = []

    # Combine all text for analysis
    full_text = f"{title}\n{message}\n{stacktrace or ''}"
    full_text_lower = full_text.lower()

    # Check for stale data patterns
    for pattern, indicator in STALE_DATA_PATTERNS.items():
        if re.search(pattern, full_text_lower):
            # Calculate confidence based on pattern specificity
            confidence = 0.7 if "stale" in pattern or "cache" in pattern else 0.5

            # Extract potential table names
            tables = extract_table_names(full_text)

            signal = StaleDataSignal(
                indicator=indicator,
                confidence=confidence,
                context=extract_context(full_text, pattern),
                suggested_tables=tables,
                suggested_action=get_suggested_action(indicator, tables)
            )
            signals.append(signal)

    # Check tags for additional signals
    if tags:
        if "cache" in str(tags).lower():
            signals.append(StaleDataSignal(
                indicator=StaleDataIndicator.CACHE_MISMATCH,
                confidence=0.6,
                context="Issue tagged with cache-related label",
                suggested_tables=extract_table_names(full_text),
                suggested_action="Run @analyze-mutations to check cache revalidation coverage"
            ))

    return signals


def extract_table_names(text: str) -> list[str]:
    """Extract potential database table names from text."""
    tables = set()

    for pattern in TABLE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        tables.update(matches)

    # Filter out common non-table words
    excluded = {"api", "app", "src", "lib", "components", "hooks", "utils"}
    return [t for t in tables if t.lower() not in excluded]


def extract_context(text: str, pattern: str) -> str:
    """Extract surrounding context for a pattern match."""
    match = re.search(pattern, text.lower())
    if match:
        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        return f"...{text[start:end]}..."
    return ""


def get_suggested_action(indicator: StaleDataIndicator, tables: list[str]) -> str:
    """Get suggested action based on the indicator type."""
    table_focus = f"--focus={','.join(tables)}" if tables else ""

    actions = {
        StaleDataIndicator.CACHE_MISMATCH:
            f"Run @analyze-mutations {table_focus} to check cache revalidation patterns",
        StaleDataIndicator.OUTDATED_DISPLAY:
            f"Run @analyze-mutations {table_focus} and verify query key factories match cache tags",
        StaleDataIndicator.SYNC_FAILURE:
            f"Run @analyze-mutations {table_focus} to check error handling and rollback patterns",
        StaleDataIndicator.REVALIDATION_MISSING:
            f"Run @analyze-mutations {table_focus} - likely missing revalidateTag/revalidatePath calls",
        StaleDataIndicator.OPTIMISTIC_ROLLBACK:
            f"Run @check-mutation on affected hooks - check rollback context implementation",
    }

    return actions.get(indicator, f"Run @analyze-mutations {table_focus}")


def format_signals_for_claude(signals: list[StaleDataSignal]) -> str:
    """Format signals as a suggestion for Claude to act on."""
    if not signals:
        return ""

    output = ["## 🔍 Stale Data Detection", ""]
    output.append("Based on Sentry issue analysis, potential stale data patterns detected:")
    output.append("")

    for i, signal in enumerate(signals, 1):
        confidence_bar = "█" * int(signal.confidence * 10) + "░" * (10 - int(signal.confidence * 10))
        output.append(f"### Signal {i}: {signal.indicator.value}")
        output.append(f"**Confidence:** [{confidence_bar}] {signal.confidence:.0%}")
        output.append(f"**Context:** {signal.context}")
        if signal.suggested_tables:
            output.append(f"**Affected Tables:** {', '.join(signal.suggested_tables)}")
        output.append(f"**Suggested Action:** {signal.suggested_action}")
        output.append("")

    # Overall recommendation
    high_confidence = [s for s in signals if s.confidence >= 0.7]
    if high_confidence:
        all_tables = set()
        for s in high_confidence:
            all_tables.update(s.suggested_tables)

        if all_tables:
            output.append(f"### Recommended Next Step")
            output.append(f"```")
            output.append(f"@analyze-mutations --focus={','.join(all_tables)}")
            output.append(f"```")
        else:
            output.append(f"### Recommended Next Step")
            output.append(f"```")
            output.append(f"@analyze-mutations")
            output.append(f"```")

    return "\n".join(output)


def create_sentry_hook_suggestion() -> str:
    """
    Generate hook code that integrates with Sentry MCP.
    This can be used in hooks/sentry-stale-data.sh
    """
    return '''#!/bin/bash
# Hook: sentry-stale-data.sh
# Trigger: When Sentry issue details are retrieved
# Purpose: Detect stale data patterns and suggest mutation analysis

# This hook should be called after mcp__sentry__get_issue_details

ISSUE_TITLE="$1"
ISSUE_MESSAGE="$2"

# Check for stale data keywords
if echo "$ISSUE_TITLE $ISSUE_MESSAGE" | grep -iE "(stale|cache|outdated|not updated|out of sync)" > /dev/null; then
    echo "🔍 Stale data pattern detected in Sentry issue."
    echo ""
    echo "Suggested action: Run @analyze-mutations to check mutation consistency."
    echo ""
    echo "This issue may be related to:"
    echo "  • Missing cache revalidation (revalidateTag/revalidatePath)"
    echo "  • Query key factory misalignment"
    echo "  • Missing error handling in mutations"
    echo ""
    exit 0
fi

exit 1
'''


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Sentry issues for stale data patterns"
    )
    parser.add_argument(
        "--title",
        help="Issue title to analyze"
    )
    parser.add_argument(
        "--message",
        help="Error message to analyze"
    )
    parser.add_argument(
        "--stacktrace",
        help="Optional stack trace"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--generate-hook",
        action="store_true",
        help="Generate Sentry integration hook script"
    )

    args = parser.parse_args()

    if args.generate_hook:
        print(create_sentry_hook_suggestion())
        return

    if not args.title and not args.message:
        # Demo mode with example
        demo_title = "Users seeing stale player data after updates"
        demo_message = "After updating player stats, the dashboard shows old values until refresh"
        print("Running demo analysis...", file=sys.stderr)
        print(f"Title: {demo_title}", file=sys.stderr)
        print(f"Message: {demo_message}", file=sys.stderr)
        print("", file=sys.stderr)

        signals = analyze_issue_for_stale_data(demo_title, demo_message)
    else:
        signals = analyze_issue_for_stale_data(
            title=args.title or "",
            message=args.message or "",
            stacktrace=args.stacktrace
        )

    if args.json:
        output = [{
            "indicator": s.indicator.value,
            "confidence": s.confidence,
            "context": s.context,
            "suggested_tables": s.suggested_tables,
            "suggested_action": s.suggested_action
        } for s in signals]
        print(json.dumps(output, indent=2))
    else:
        print(format_signals_for_claude(signals))


if __name__ == "__main__":
    main()
