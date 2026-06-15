"""
Skill Refinement System - Common Modules

Provides shared data models, persistence layer, and utilities
for the skill refinement workflow.
"""

from .models import (
    RefinementContext,
    GapAnalysis,
    GeneratedPatch,
    Pattern,
    Refinement,
    OverrideType,
    RefinementCategory,
    PatchAction,
    PatternStatus,
)

from .persistence import (
    RefinementPersistence,
    ensure_user_refinements_dir,
    get_refinement_id,
    get_pattern_id,
    USER_REFINEMENTS_DIR,
)

__all__ = [
    # Models
    "RefinementContext",
    "GapAnalysis",
    "GeneratedPatch",
    "Pattern",
    "Refinement",
    "OverrideType",
    "RefinementCategory",
    "PatchAction",
    "PatternStatus",
    # Persistence
    "RefinementPersistence",
    "ensure_user_refinements_dir",
    "get_refinement_id",
    "get_pattern_id",
    "USER_REFINEMENTS_DIR",
]
