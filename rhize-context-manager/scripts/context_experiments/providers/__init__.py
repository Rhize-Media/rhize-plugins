"""Provider interfaces and real adapters for controlled context experiments."""

from .base import Provider, ProviderResult, TaskRequest
from .context_compiler import ContextCompilerProvider, ProviderHealth
from .mgrep import MgrepProvider

__all__ = [
    "ContextCompilerProvider",
    "MgrepProvider",
    "Provider",
    "ProviderHealth",
    "ProviderResult",
    "TaskRequest",
]
