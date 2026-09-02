#!/usr/bin/env python3
"""suggestion_log_report.py — compatibility shim.

Moved to rhize-context-manager/scripts/suggestion_log_report.py on 2026-09-02
(R3 task 8 of the portability-readiness plan) — it now ships with the plugin
so /rhize-context-manager:suggestion-report can invoke it via
$CLAUDE_PLUGIN_ROOT. This file forwards both CLI invocation
(`python3 scripts/suggestion_log_report.py ...`) and direct module import
(e.g. importlib-based tests) to the moved copy, unchanged.
"""
from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = (
    Path(__file__).resolve().parent.parent
    / "rhize-context-manager"
    / "scripts"
    / "suggestion_log_report.py"
)

globals().update(runpy.run_path(str(_TARGET), run_name=__name__))
