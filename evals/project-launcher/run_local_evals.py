#!/usr/bin/env python3
"""Run the shared deterministic gate against this component's local fixtures."""
import os
import runpy
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
os.environ["RHIZE_LOCAL_EVAL_DIR"] = str(EVAL_DIR)
runpy.run_path(str(EVAL_DIR.parent / "seo-aeo-geo" / "run_local_evals.py"), run_name="__main__")
