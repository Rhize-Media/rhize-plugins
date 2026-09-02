#!/usr/bin/env python3
"""build_local_skill_map.py — compatibility shim.

Moved to rhize-context-manager/scripts/build_local_skill_map.py on 2026-09-02
(R3 task 8 of the portability-readiness plan) — it now ships with the plugin
so a future rhize-ops setup orchestrator's `install-skill-map` step can build
the local overlay for installed users. This file forwards both CLI invocation
(`python3 scripts/build_local_skill_map.py ...`) and direct module import
(e.g. importlib-based tests) to the moved copy, unchanged.
"""
from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = (
    Path(__file__).resolve().parent.parent
    / "rhize-context-manager"
    / "scripts"
    / "build_local_skill_map.py"
)

globals().update(runpy.run_path(str(_TARGET), run_name=__name__))
