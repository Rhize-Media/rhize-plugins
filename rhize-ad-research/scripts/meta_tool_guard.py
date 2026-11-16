#!/usr/bin/env python3
"""Restrict the dedicated research MCP server without granting tool permission."""
import json
import re
import sys


def main():
    try:
        event = json.load(sys.stdin)
        name = event.get('tool_name', '')
        blocked = bool(re.fullmatch(r'mcp__meta[-_]ads__.*', name)) and name not in {'mcp__meta-ads__ads_library_search', 'mcp__meta_ads__ads_library_search'}
    except (ValueError, TypeError, AttributeError):
        blocked = True
    if blocked:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
              'permissionDecision': 'deny', 'permissionDecisionReason':
              'Rhize Ad Research permits only ads_library_search on the dedicated Meta server.'}}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
