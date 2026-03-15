"""
Assertion evaluation engine for plugin evals.

Supports assertion types:
  - contains / not_contains: string presence checks
  - regex: pattern matching
  - min_length / max_length: output length bounds
  - calls_tool: checks if a specific MCP tool was invoked
  - section_count: minimum number of markdown ## sections
"""

import re
from typing import Any


def evaluate_assertion(assertion: dict, output: str, tool_calls: list[dict] | None = None) -> dict:
    """Evaluate a single assertion against output text and optional tool call list.

    Args:
        assertion: Dict with keys 'type', 'value', 'name' (display label).
        output: The full text output from the claude run.
        tool_calls: List of tool call dicts from claude JSON output (optional).

    Returns:
        Dict with 'name', 'type', 'passed' (bool), 'evidence' (str).
    """
    a_type = assertion["type"]
    value = assertion["value"]
    name = assertion.get("name", f"{a_type}:{value}")

    if a_type == "contains":
        passed = value.lower() in output.lower()
        evidence = _find_snippet(output, value) if passed else f"'{value}' not found in output"

    elif a_type == "not_contains":
        passed = value.lower() not in output.lower()
        evidence = "Correctly absent" if passed else f"Found unwanted '{value}' in output"

    elif a_type == "regex":
        match = re.search(value, output, re.IGNORECASE | re.MULTILINE)
        passed = match is not None
        evidence = f"Matched: '{match.group()}'" if passed else f"Pattern /{value}/ not found"

    elif a_type == "min_length":
        length = len(output)
        passed = length >= int(value)
        evidence = f"Output length: {length} (min: {value})"

    elif a_type == "max_length":
        length = len(output)
        passed = length <= int(value)
        evidence = f"Output length: {length} (max: {value})"

    elif a_type == "calls_tool":
        tool_calls = tool_calls or []
        matched = [t for t in tool_calls if value.lower() in t.get("name", "").lower()]
        passed = len(matched) > 0
        if passed:
            evidence = f"Tool '{matched[0]['name']}' was called"
        else:
            called = [t.get("name", "?") for t in tool_calls]
            evidence = f"Tool matching '{value}' not found. Tools called: {called}"

    elif a_type == "section_count":
        sections = re.findall(r"^##\s+", output, re.MULTILINE)
        count = len(sections)
        passed = count >= int(value)
        evidence = f"Found {count} sections (min: {value})"

    elif a_type == "has_data":
        # Check that output contains concrete data (numbers, URLs, percentages)
        # rather than purely generic advice. The 'value' is the minimum number of
        # distinct data points (numbers, percentages, URLs) required.
        min_data_points = int(value)
        # Match: standalone numbers (123, 1,234), percentages (45.2%), URLs, scores
        data_patterns = [
            r'\b\d{1,3}(?:,\d{3})+\b',          # comma-separated numbers: 1,234
            r'\b\d+\.\d+%',                        # percentages: 45.2%
            r'\b\d+%',                              # whole percentages: 45%
            r'https?://[^\s\)]+',                   # URLs
            r'\b\d+/100\b',                         # scores: 85/100
            r'\b\d+\s*(?:ms|KB|MB|GB|seconds?)\b',  # metrics with units
        ]
        data_points = set()
        for pat in data_patterns:
            for m in re.finditer(pat, output):
                data_points.add(m.group())
        count = len(data_points)
        passed = count >= min_data_points
        sample = list(data_points)[:5]
        evidence = f"Found {count} data points (min: {min_data_points}). Sample: {sample}"

    else:
        passed = False
        evidence = f"Unknown assertion type: {a_type}"

    return {
        "name": name,
        "type": a_type,
        "passed": passed,
        "evidence": evidence,
    }


def evaluate_all(assertions: list[dict], output: str, tool_calls: list[dict] | None = None) -> dict:
    """Evaluate all assertions and return summary.

    Returns:
        Dict with 'results' (list), 'passed' (int), 'failed' (int), 'total' (int), 'pass_rate' (float).
    """
    results = [evaluate_assertion(a, output, tool_calls) for a in assertions]
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    return {
        "results": results,
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "pass_rate": passed / total if total > 0 else 0.0,
    }


def _find_snippet(text: str, target: str, context_chars: int = 60) -> str:
    """Find the target in text and return a snippet with surrounding context."""
    idx = text.lower().find(target.lower())
    if idx == -1:
        return ""
    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(target) + context_chars)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return f"Found: '{snippet}'"
