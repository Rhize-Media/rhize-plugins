"""Controlled dogfood experiments for context retrieval and compilation."""

from .assignment import assign_arms
from .eligibility import EligibilityInput, classify_task, evaluate_eligibility
from .models import (
    Arm,
    Assignment,
    Capability,
    CapabilityConfig,
    ExperimentConfig,
    ExperimentReceipt,
    Metric,
    RunStatus,
)

__all__ = [
    "Arm",
    "Assignment",
    "Capability",
    "CapabilityConfig",
    "EligibilityInput",
    "ExperimentConfig",
    "ExperimentReceipt",
    "Metric",
    "RunStatus",
    "assign_arms",
    "classify_task",
    "evaluate_eligibility",
]
