"""Provider protocol shared by baseline and experimental retrieval paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import Arm, Metric


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    prompt_hash: str
    snapshot: str
    arm: Arm
    execution_role: str


@dataclass(frozen=True)
class ProviderResult:
    arm: Arm
    metrics: tuple[Metric, ...]
    warnings: tuple[str, ...] = ()
    fallback_used: bool = False


class Provider(Protocol):
    name: str

    def run(self, request: TaskRequest) -> ProviderResult: ...
