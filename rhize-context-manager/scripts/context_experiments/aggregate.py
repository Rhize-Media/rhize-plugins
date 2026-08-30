"""Aggregate compatible receipt metrics without mixing units or evidence classes."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Iterable, Mapping, Any


def aggregate_receipts(receipts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for receipt in receipts:
        capability = receipt.get("capability")
        live_variant = receipt.get("liveVariant")
        if capability and live_variant:
            groups[(str(capability), str(live_variant))].append(receipt)

    output = []
    for (capability, live_variant), rows in sorted(groups.items()):
        metric_values: dict[tuple[str, str, str, str, str], list[float]] = defaultdict(list)
        for row in rows:
            for metric in row.get("metrics", []):
                if not isinstance(metric, Mapping):
                    continue
                value = metric.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                key = (
                    str(metric.get("name", "")),
                    str(metric.get("unit", "")),
                    str(metric.get("evidence", "")),
                    str(metric.get("variant", "")),
                    str(metric.get("role", "")),
                )
                metric_values[key].append(float(value))
        metrics = []
        for (name, unit, evidence, variant, role), values in sorted(metric_values.items()):
            metrics.append(
                {
                    "name": name,
                    "unit": unit,
                    "evidence": evidence,
                    "variant": variant,
                    "role": role,
                    "samples": len(values),
                    "median": statistics.median(values),
                    "minimum": min(values),
                    "maximum": max(values),
                }
            )
        arm_accounting = {
            arm: {
                "executed": sum(arm in row.get("armsExecuted", []) for row in rows),
                "skipped": sum(
                    any(
                        isinstance(item, Mapping) and item.get("arm") == arm
                        for item in row.get("armsSkipped", [])
                    )
                    for row in rows
                ),
            }
            for arm in ("A", "B")
        }
        output.append(
            {
                "capability": capability,
                "liveVariant": live_variant,
                "runs": len(rows),
                "completed": sum(row.get("status") == "completed" for row in rows),
                "incomplete": sum(row.get("status") == "incomplete" for row in rows),
                "failed": sum(row.get("status") == "failed" for row in rows),
                "evidenceBacked": sum(
                    isinstance(row.get("evidenceDigest"), str) for row in rows
                ),
                "comparableRuns": sum(_has_comparable_pair(row) for row in rows),
                "armAccounting": arm_accounting,
                "fallbacks": sum(bool(row.get("fallbackUsed")) for row in rows),
                "metrics": metrics,
            }
        )
    return {"schemaVersion": 2, "groups": output}


def _has_comparable_pair(receipt: Mapping[str, Any]) -> bool:
    if not {"A", "B"}.issubset(set(receipt.get("armsExecuted", []))):
        return False
    signatures: dict[str, set[tuple[str, str, str]]] = {"A": set(), "B": set()}
    for metric in receipt.get("metrics", []):
        if not isinstance(metric, Mapping):
            continue
        variant = metric.get("variant")
        if variant in signatures:
            signatures[str(variant)].add(
                (
                    str(metric.get("name", "")),
                    str(metric.get("unit", "")),
                    str(metric.get("evidence", "")),
                )
            )
    return bool(signatures["A"] & signatures["B"])
