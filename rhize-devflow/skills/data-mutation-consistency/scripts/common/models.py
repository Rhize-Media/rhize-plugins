"""
Data Models for Mutation Consistency Analysis

Defines core data structures used throughout the skill.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path
from datetime import datetime


class Severity(Enum):
    """Issue severity levels."""
    CRITICAL = "critical"  # Score < 7.0, blocks without override
    WARNING = "warning"    # Score < 9.0, strong recommendation
    INFO = "info"          # Improvement opportunity


class MutationCategory(Enum):
    """Categories of mutations for scoring."""
    SERVER_ACTION = "server_action"
    API_ROUTE = "api_route"
    CLIENT_MUTATION = "client_mutation"
    PAYLOAD_HOOK = "payload_hook"
    REACT_QUERY = "react_query"


@dataclass
class MutationInfo:
    """Information about a detected mutation."""
    file_path: Path
    line_number: int
    mutation_type: str  # insert, update, delete, upsert
    table_or_entity: str
    category: MutationCategory
    code_snippet: str
    function_name: Optional[str] = None

    # Detected elements
    has_error_handling: bool = False
    has_cache_revalidation: bool = False
    has_type_safety: bool = False
    has_optimistic_update: bool = False
    has_rollback_logic: bool = False
    has_input_validation: bool = False
    has_user_feedback: bool = False
    has_audit_trail: bool = False

    # React Query specific
    has_query_key_factory: bool = False
    has_on_settled: bool = False
    has_on_error: bool = False

    # Payload specific
    has_after_change_hook: bool = False
    has_after_delete_hook: bool = False
    has_before_change_hook: bool = False

    @property
    def is_user_facing(self) -> bool:
        """Determine if mutation is user-facing (requires optimistic UI)."""
        user_facing_indicators = [
            "component" in str(self.file_path).lower(),
            "hook" in str(self.file_path).lower(),
            "use" in (self.function_name or "").lower(),
        ]
        return any(user_facing_indicators)


@dataclass
class MutationIssue:
    """An issue found during mutation analysis."""
    mutation: MutationInfo
    element: str  # What's missing
    severity: Severity
    message: str
    fix_suggestion: str
    fix_code: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "file": str(self.mutation.file_path),
            "line": self.mutation.line_number,
            "element": self.element,
            "severity": self.severity.value,
            "message": self.message,
            "fix_suggestion": self.fix_suggestion,
        }


@dataclass
class MutationScore:
    """Scoring result for a single mutation."""
    mutation: MutationInfo
    raw_score: float
    max_score: float
    final_score: float  # Normalized to 10-point scale

    elements_present: list[str] = field(default_factory=list)
    elements_missing: list[str] = field(default_factory=list)
    issues: list[MutationIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.final_score >= 9.0:
            return "passing"
        elif self.final_score >= 7.0:
            return "warning"
        else:
            return "critical"

    @property
    def status_emoji(self) -> str:
        if self.final_score >= 9.0:
            return "✅"
        elif self.final_score >= 7.0:
            return "⚠️"
        else:
            return "❌"


@dataclass
class SubSkillResult:
    """Results from a sub-skill analysis."""
    name: str  # react-query-mutations, payload-cms-hooks
    mutations_found: int
    average_score: float
    issues: list[MutationIssue] = field(default_factory=list)
    scores: list[MutationScore] = field(default_factory=list)

    # Sub-skill specific metrics
    query_key_factories_found: int = 0
    query_key_factories_missing: int = 0
    collections_with_hooks: int = 0
    collections_without_hooks: int = 0


@dataclass
class AnalysisResult:
    """Complete analysis result for a project."""
    project_root: Path
    timestamp: datetime

    # Overall metrics
    total_mutations: int = 0
    overall_score: float = 0.0
    passing_count: int = 0  # Score >= 9.0
    warning_count: int = 0  # 7.0 <= Score < 9.0
    critical_count: int = 0  # Score < 7.0

    # Detailed results
    mutations: list[MutationInfo] = field(default_factory=list)
    scores: list[MutationScore] = field(default_factory=list)
    issues: list[MutationIssue] = field(default_factory=list)

    # Sub-skill results
    sub_skills_loaded: list[str] = field(default_factory=list)
    sub_skill_results: dict[str, SubSkillResult] = field(default_factory=dict)

    # Cross-layer validation
    cache_tag_alignment: dict[str, bool] = field(default_factory=dict)
    misaligned_tags: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.overall_score >= 9.0:
            return "healthy"
        elif self.overall_score >= 7.0:
            return "needs_attention"
        else:
            return "critical"

    @property
    def status_emoji(self) -> str:
        if self.overall_score >= 9.0:
            return "✅"
        elif self.overall_score >= 7.0:
            return "⚠️"
        else:
            return "🚨"

    def get_top_issues(self, count: int = 3) -> list[MutationIssue]:
        """Get top N issues by severity."""
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.WARNING: 1,
            Severity.INFO: 2,
        }
        sorted_issues = sorted(
            self.issues,
            key=lambda i: (severity_order[i.severity], -i.mutation.line_number)
        )
        return sorted_issues[:count]

    def to_summary_dict(self) -> dict:
        """Generate summary for chat output (minimal context usage)."""
        return {
            "overall_score": round(self.overall_score, 1),
            "status": self.status,
            "total_mutations": self.total_mutations,
            "passing": self.passing_count,
            "warnings": self.warning_count,
            "critical": self.critical_count,
            "sub_skills": self.sub_skills_loaded,
            "top_issues": [i.to_dict() for i in self.get_top_issues(3)],
        }


@dataclass
class ProjectConfig:
    """Project-specific configuration."""
    project_root: Path

    # Platform settings
    deployment: str = "vercel"
    framework: str = "nextjs"
    database: str = "supabase"

    # Sub-skill settings
    auto_detect_sub_skills: bool = True
    enabled_sub_skills: list[str] = field(default_factory=list)

    # Enforcement settings
    mode: str = "advisory"  # advisory | strict
    warning_threshold: float = 9.0
    critical_threshold: float = 7.0
    add_todos: bool = True

    # Analysis settings
    output_dir: Path = field(default_factory=lambda: Path(".claude/analysis"))

    # Ignore patterns
    ignore_paths: list[str] = field(default_factory=lambda: [
        "**/test/**",
        "**/__mocks__/**",
        "**/migrations/**",
    ])
    ignore_files: list[str] = field(default_factory=lambda: [
        "*.test.ts",
        "*.spec.ts",
        "*.d.ts",
    ])

    @classmethod
    def load_from_file(cls, project_root: Path) -> "ProjectConfig":
        """Load config from .claude/mutation-patterns.yaml if exists."""
        import yaml

        config_path = project_root / ".claude" / "mutation-patterns.yaml"
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f)

            return cls(
                project_root=project_root,
                deployment=data.get("platform", {}).get("deployment", "vercel"),
                framework=data.get("platform", {}).get("framework", "nextjs"),
                database=data.get("platform", {}).get("database", "supabase"),
                auto_detect_sub_skills=data.get("sub_skills", {}).get("auto_detect", True),
                enabled_sub_skills=data.get("sub_skills", {}).get("enabled", []),
                mode=data.get("enforcement", {}).get("mode", "advisory"),
                warning_threshold=data.get("enforcement", {}).get("warning_threshold", 9.0),
                critical_threshold=data.get("enforcement", {}).get("critical_threshold", 7.0),
                add_todos=data.get("enforcement", {}).get("add_todos", True),
                output_dir=Path(data.get("analysis", {}).get("output_dir", ".claude/analysis")),
                ignore_paths=data.get("ignore", {}).get("paths", cls.ignore_paths),
                ignore_files=data.get("ignore", {}).get("files", cls.ignore_files),
            )

        return cls(project_root=project_root)
