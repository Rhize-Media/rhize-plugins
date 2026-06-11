"""
Shared data models for validation scripts.

Provides consistent data structures across all validators for:
- Issue severity classification
- Issue tracking and reporting
- Validation report generation
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any


class Severity(Enum):
    """Issue severity levels for validation findings."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Issue:
    """Represents a single validation issue found in the codebase."""
    file: str
    line: int
    severity: Severity
    rule: str
    message: str
    code_snippet: str = ""
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert issue to dictionary with severity as string."""
        return {
            **asdict(self),
            "severity": self.severity.value
        }


@dataclass
class BaseValidationReport:
    """Base validation report with common fields."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    total_files_scanned: int = 0
    errors: int = 0
    warnings: int = 0
    issues: List[Issue] = field(default_factory=list)
    passed: bool = True

    def add_issue(self, issue: Issue) -> None:
        """Add an issue and update error/warning counts."""
        self.issues.append(issue)
        if issue.severity == Severity.ERROR:
            self.errors += 1
        elif issue.severity == Severity.WARNING:
            self.warnings += 1

    def finalize(self) -> None:
        """Finalize report by setting passed status."""
        self.passed = self.errors == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "total_files_scanned": self.total_files_scanned,
            "errors": self.errors,
            "warnings": self.warnings,
            "passed": self.passed,
            "issues": [issue.to_dict() for issue in self.issues]
        }
