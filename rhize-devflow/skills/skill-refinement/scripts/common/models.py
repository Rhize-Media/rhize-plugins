"""
Data models for the Skill Refinement System.

Defines all data structures used across the refinement workflow.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class OverrideType(Enum):
    """Types of skill overrides."""

    SECTION_PATCH = "patch"
    EXTENSION = "extend"
    CONFIG_OVERRIDE = "config"
    FULL_OVERRIDE = "full"
    HOOK_OVERRIDE = "hook"
    SCRIPT_OVERRIDE = "script"
    NEW_CAPABILITY = "new"


class RefinementCategory(Enum):
    """Categories of skill refinements."""

    TRIGGER = "trigger"
    CONTENT = "content"
    HOOK = "hook"
    TOOL = "tool"
    PATTERN = "pattern"
    CONFIG = "config"
    NEW = "new"


class PatchAction(Enum):
    """Actions for section-level patches."""

    APPEND = "append"
    PREPEND = "prepend"
    REPLACE_SECTION = "replace-section"
    INSERT_AFTER = "insert-after"
    INSERT_BEFORE = "insert-before"
    DELETE_SECTION = "delete-section"


class PatternStatus(Enum):
    """Status of tracked patterns."""

    TRACKING = "tracking"  # count = 1
    READY = "ready-for-generalization"  # count >= 2
    GENERALIZED = "generalized"  # applied to user-scope
    DISMISSED = "dismissed"  # manually dismissed


class GuidedModeReason(Enum):
    """Reasons for triggering guided mode."""

    AMBIGUOUS_TARGET = "Cannot determine which skill/section to modify"
    MULTIPLE_OPTIONS = "Multiple valid approaches available"
    BREAKING_CHANGE = "Proposed change may break existing behavior"
    CROSS_SKILL = "Refinement affects multiple skills"
    UNCLEAR_INTENT = "User intent not clear from context"


@dataclass
class RefinementContext:
    """Context gathered for refinement analysis."""

    # Session context
    recent_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    session_duration: Optional[float] = None
    files_touched: List[str] = field(default_factory=list)

    # Error context (from Sentry if available)
    recent_errors: List[Dict[str, Any]] = field(default_factory=list)

    # Skill context
    target_skill: Optional[str] = None
    current_skill_config: Dict[str, Any] = field(default_factory=dict)
    skill_files: List[str] = field(default_factory=list)

    # Git context
    git_status: str = ""
    recent_commits: List[str] = field(default_factory=list)
    current_diff: str = ""

    # Pattern context (from history)
    similar_refinements: List[Dict[str, Any]] = field(default_factory=list)
    pattern_matches: List[str] = field(default_factory=list)

    # Zen context (if available)
    zen_memories: Optional[List[Dict[str, Any]]] = None
    cross_project_patterns: Optional[List[Dict[str, Any]]] = None

    # Project context
    project_root: Optional[str] = None
    project_name: Optional[str] = None

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "recent_tool_calls": self.recent_tool_calls,
            "session_duration": self.session_duration,
            "files_touched": self.files_touched,
            "recent_errors": self.recent_errors,
            "target_skill": self.target_skill,
            "current_skill_config": self.current_skill_config,
            "skill_files": self.skill_files,
            "git_status": self.git_status,
            "recent_commits": self.recent_commits,
            "current_diff": self.current_diff,
            "similar_refinements": self.similar_refinements,
            "pattern_matches": self.pattern_matches,
            "zen_memories": self.zen_memories,
            "cross_project_patterns": self.cross_project_patterns,
            "project_root": self.project_root,
            "project_name": self.project_name,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class GapAnalysis:
    """Result of gap analysis between expected and actual behavior."""

    # Core analysis
    root_cause: str
    override_type: OverrideType
    target_section: str  # e.g., "hooks/duplicate-check" or "commands/start/Step 4"
    target_skill: str

    # Confidence & guidance
    confidence: float  # 0-1
    needs_guided_mode: bool
    guided_mode_reasons: List[GuidedModeReason] = field(default_factory=list)
    clarifying_questions: List[str] = field(default_factory=list)

    # Generalization
    generalization_potential: str = "medium"  # "high", "medium", "low"
    pattern_id: Optional[str] = None  # Existing pattern this matches
    similar_refinements: List[str] = field(default_factory=list)  # IDs

    # Impact
    affected_files: List[str] = field(default_factory=list)
    breaking_changes: List[str] = field(default_factory=list)

    # Patch details
    patch_action: Optional[PatchAction] = None
    patch_marker: Optional[str] = None  # For insert-after, replace-section, etc.
    patch_content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "root_cause": self.root_cause,
            "override_type": self.override_type.value,
            "target_section": self.target_section,
            "target_skill": self.target_skill,
            "confidence": self.confidence,
            "needs_guided_mode": self.needs_guided_mode,
            "guided_mode_reasons": [r.value for r in self.guided_mode_reasons],
            "clarifying_questions": self.clarifying_questions,
            "generalization_potential": self.generalization_potential,
            "pattern_id": self.pattern_id,
            "similar_refinements": self.similar_refinements,
            "affected_files": self.affected_files,
            "breaking_changes": self.breaking_changes,
            "patch_action": self.patch_action.value if self.patch_action else None,
            "patch_marker": self.patch_marker,
            "patch_content": self.patch_content,
        }


@dataclass
class GeneratedPatch:
    """Generated patch content and metadata."""

    files: Dict[str, str]  # path -> content
    preview: str  # Formatted diff preview
    description: str
    override_type: OverrideType
    target_skill: str
    target_section: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "files": self.files,
            "preview": self.preview,
            "description": self.description,
            "override_type": self.override_type.value,
            "target_skill": self.target_skill,
            "target_section": self.target_section,
        }


@dataclass
class Refinement:
    """A single skill refinement record."""

    id: str  # REF-YYYY-MMDD-NNN
    skill: str
    category: RefinementCategory
    override_type: OverrideType
    target_section: str

    # User input
    expected_behavior: str
    actual_behavior: str
    example: Optional[str] = None
    desired_outcome: str = ""

    # Analysis
    root_cause: str = ""
    confidence: float = 0.0

    # Location
    project: str = ""
    project_root: Optional[str] = None

    # Patch details
    patch_action: Optional[PatchAction] = None
    patch_marker: Optional[str] = None
    patch_content: str = ""

    # Pattern tracking
    pattern_id: Optional[str] = None
    generalization_potential: str = "medium"

    # Status
    status: str = "applied"  # "pending", "applied", "generalized"
    created: datetime = field(default_factory=datetime.now)
    applied: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "skill": self.skill,
            "category": self.category.value,
            "override_type": self.override_type.value,
            "target_section": self.target_section,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "example": self.example,
            "desired_outcome": self.desired_outcome,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "project": self.project,
            "project_root": self.project_root,
            "patch_action": self.patch_action.value if self.patch_action else None,
            "patch_marker": self.patch_marker,
            "patch_content": self.patch_content,
            "pattern_id": self.pattern_id,
            "generalization_potential": self.generalization_potential,
            "status": self.status,
            "created": self.created.isoformat(),
            "applied": self.applied.isoformat() if self.applied else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Refinement":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            skill=data["skill"],
            category=RefinementCategory(data["category"]),
            override_type=OverrideType(data["override_type"]),
            target_section=data["target_section"],
            expected_behavior=data["expected_behavior"],
            actual_behavior=data["actual_behavior"],
            example=data.get("example"),
            desired_outcome=data.get("desired_outcome", ""),
            root_cause=data.get("root_cause", ""),
            confidence=data.get("confidence", 0.0),
            project=data.get("project", ""),
            project_root=data.get("project_root"),
            patch_action=PatchAction(data["patch_action"]) if data.get("patch_action") else None,
            patch_marker=data.get("patch_marker"),
            patch_content=data.get("patch_content", ""),
            pattern_id=data.get("pattern_id"),
            generalization_potential=data.get("generalization_potential", "medium"),
            status=data.get("status", "applied"),
            created=datetime.fromisoformat(data["created"]) if data.get("created") else datetime.now(),
            applied=datetime.fromisoformat(data["applied"]) if data.get("applied") else None,
        )


@dataclass
class Pattern:
    """A tracked refinement pattern across projects."""

    id: str  # PATTERN-NNN
    name: str
    description: str
    affected_skills: List[str] = field(default_factory=list)
    refinement_ids: List[str] = field(default_factory=list)
    projects: List[str] = field(default_factory=list)
    count: int = 0
    status: PatternStatus = PatternStatus.TRACKING
    proposed_changes: Dict[str, str] = field(default_factory=dict)  # file -> change

    # Metadata
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    generalized_date: Optional[datetime] = None
    dismissed_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "affected_skills": self.affected_skills,
            "refinement_ids": self.refinement_ids,
            "projects": self.projects,
            "count": self.count,
            "status": self.status.value,
            "proposed_changes": self.proposed_changes,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "generalized_date": self.generalized_date.isoformat() if self.generalized_date else None,
            "dismissed_reason": self.dismissed_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pattern":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            affected_skills=data.get("affected_skills", []),
            refinement_ids=data.get("refinement_ids", []),
            projects=data.get("projects", []),
            count=data.get("count", 0),
            status=PatternStatus(data.get("status", "tracking")),
            proposed_changes=data.get("proposed_changes", {}),
            first_seen=datetime.fromisoformat(data["first_seen"]) if data.get("first_seen") else datetime.now(),
            last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else datetime.now(),
            generalized_date=datetime.fromisoformat(data["generalized_date"]) if data.get("generalized_date") else None,
            dismissed_reason=data.get("dismissed_reason"),
        )
