"""Deterministic live/shadow arm assignment."""

from __future__ import annotations

from .models import Arm, Assignment, CapabilityConfig


def assign_arms(config: CapabilityConfig) -> Assignment:
    """Alternate live arms, starting with experimental Arm B.

    Starting with B guarantees that an explicitly armed first run exercises the new
    path instead of consuming the one-shot run on another baseline-only task.
    """

    if config.live_assignment != "alternate":
        raise ValueError(f"unsupported live assignment: {config.live_assignment}")
    live = (
        Arm.EXPERIMENTAL
        if config.mode == "continuous" or config.completed_runs % 2 == 0
        else Arm.BASELINE
    )
    shadow = None
    requested = [live]
    if config.shadow:
        shadow = Arm.BASELINE if live is Arm.EXPERIMENTAL else Arm.EXPERIMENTAL
        requested.append(shadow)
    return Assignment(tuple(requested), live, shadow)
