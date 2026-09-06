#!/usr/bin/env python3
"""Event-specific discovery entry point for the shared paired-measurement hook."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("memory-opportunity.py")), run_name="__main__")
