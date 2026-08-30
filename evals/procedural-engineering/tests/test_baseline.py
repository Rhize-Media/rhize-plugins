import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_baseline", ROOT / "validate_baseline.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def load_baseline() -> dict:
    return json.loads((ROOT / "baseline-2026-08-30.json").read_text(encoding="utf-8"))


def test_frozen_baseline_validates() -> None:
    MODULE.validate(load_baseline())


def test_forbidden_sensitive_field_is_rejected() -> None:
    payload = load_baseline()
    payload["token"] = "not-real"
    with pytest.raises(SystemExit, match="forbidden key"):
        MODULE.validate(payload)


def test_duplicate_enabled_scheduler_is_rejected() -> None:
    payload = load_baseline()
    dormant = next(
        record
        for record in payload["schedulers"]
        if record["canonicalRegistry"] == "registry_b_dormant_duplicate"
    )
    dormant["enabled"] = True
    with pytest.raises(SystemExit, match="exactly one scheduler"):
        MODULE.validate(payload)
