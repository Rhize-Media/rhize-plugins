"""
Persistence layer for the Skill Refinement System.

Handles dual persistence: file-based (primary) and Zen MCP (secondary).
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import Pattern, PatternStatus, Refinement


# Constants
USER_REFINEMENTS_DIR = Path.home() / ".claude" / "skill-refinements"
SUGGESTED_REFINEMENTS_FILE = "suggested-refinements.md"
AGGREGATED_PATTERNS_FILE = "aggregated-patterns.md"
GENERALIZATION_QUEUE_FILE = "generalization-queue.md"
HISTORY_DIR = "refinement-history"
ZEN_SYNC_FILE = ".zen-sync"

GENERALIZATION_THRESHOLD = 2  # Auto-trigger at this count


def ensure_user_refinements_dir() -> Path:
    """Ensure the user refinements directory structure exists."""
    dirs_to_create = [
        USER_REFINEMENTS_DIR,
        USER_REFINEMENTS_DIR / HISTORY_DIR,
    ]

    for dir_path in dirs_to_create:
        dir_path.mkdir(parents=True, exist_ok=True)

    # Initialize files if they don't exist
    suggested_file = USER_REFINEMENTS_DIR / SUGGESTED_REFINEMENTS_FILE
    if not suggested_file.exists():
        suggested_file.write_text(_get_suggested_refinements_template())

    patterns_file = USER_REFINEMENTS_DIR / AGGREGATED_PATTERNS_FILE
    if not patterns_file.exists():
        patterns_file.write_text(_get_aggregated_patterns_template())

    queue_file = USER_REFINEMENTS_DIR / GENERALIZATION_QUEUE_FILE
    if not queue_file.exists():
        queue_file.write_text(_get_generalization_queue_template())

    return USER_REFINEMENTS_DIR


def get_refinement_id() -> str:
    """Generate a unique refinement ID: REF-YYYY-MMDD-NNN."""
    today = datetime.now()
    date_part = today.strftime("%Y-%m%d")

    # Count existing refinements for today
    history_dir = USER_REFINEMENTS_DIR / HISTORY_DIR
    if history_dir.exists():
        today_prefix = today.strftime("%Y-%m-%d")
        existing = list(history_dir.glob(f"{today_prefix}-*.md"))
        count = len(existing) + 1
    else:
        count = 1

    return f"REF-{date_part}-{count:03d}"


def get_pattern_id() -> str:
    """Generate a unique pattern ID: PATTERN-NNN."""
    patterns_file = USER_REFINEMENTS_DIR / AGGREGATED_PATTERNS_FILE
    if not patterns_file.exists():
        return "PATTERN-001"

    content = patterns_file.read_text()
    # Find all existing pattern IDs
    matches = re.findall(r"PATTERN-(\d+)", content)
    if matches:
        max_id = max(int(m) for m in matches)
        return f"PATTERN-{max_id + 1:03d}"

    return "PATTERN-001"


class RefinementPersistence:
    """Handles persistence for refinements and patterns."""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root) if project_root else None
        self.user_dir = ensure_user_refinements_dir()

    def save_refinement(self, refinement: Refinement) -> Tuple[bool, str]:
        """
        Save a refinement to user-scope files.

        Returns (success, message).
        """
        try:
            # 1. Add to suggested-refinements.md
            self._add_to_suggested_refinements(refinement)

            # 2. Create history entry
            self._create_history_entry(refinement)

            # 3. Update pattern tracking
            pattern = self._update_pattern_tracking(refinement)

            # 4. Check for generalization trigger
            if pattern and pattern.count >= GENERALIZATION_THRESHOLD:
                self._add_to_generalization_queue(pattern)
                return True, f"Saved {refinement.id}. Pattern {pattern.id} ready for generalization!"

            return True, f"Saved {refinement.id}"

        except Exception as e:
            return False, f"Failed to save refinement: {e}"

    def load_patterns(self, status: Optional[PatternStatus] = None) -> List[Pattern]:
        """Load patterns from aggregated-patterns.md."""
        patterns_file = self.user_dir / AGGREGATED_PATTERNS_FILE
        if not patterns_file.exists():
            return []

        content = patterns_file.read_text()
        patterns = self._parse_patterns_file(content)

        if status:
            patterns = [p for p in patterns if p.status == status]

        return patterns

    def load_refinements(self, skill: Optional[str] = None) -> List[Refinement]:
        """Load refinements from history directory."""
        history_dir = self.user_dir / HISTORY_DIR
        if not history_dir.exists():
            return []

        refinements = []
        for file_path in history_dir.glob("*.md"):
            try:
                content = file_path.read_text()
                refinement = self._parse_refinement_entry(content)
                if refinement:
                    if skill is None or refinement.skill == skill:
                        refinements.append(refinement)
            except Exception:
                continue

        return sorted(refinements, key=lambda r: r.created, reverse=True)

    def _add_to_suggested_refinements(self, refinement: Refinement) -> None:
        """Add refinement to suggested-refinements.md."""
        suggested_file = self.user_dir / SUGGESTED_REFINEMENTS_FILE
        content = suggested_file.read_text() if suggested_file.exists() else ""

        # Update timestamp
        content = re.sub(
            r"> Last updated: .*",
            f"> Last updated: {datetime.now().isoformat()}",
            content,
        )

        # Find "## Pending Review" section and add entry
        entry = self._format_suggested_entry(refinement)

        if "## Pending Review" in content:
            content = content.replace(
                "## Pending Review\n",
                f"## Pending Review\n\n{entry}\n",
            )
        else:
            content += f"\n## Pending Review\n\n{entry}\n"

        suggested_file.write_text(content)

    def _create_history_entry(self, refinement: Refinement) -> None:
        """Create individual history entry file."""
        history_dir = self.user_dir / HISTORY_DIR
        history_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{refinement.created.strftime('%Y-%m-%d')}-{refinement.skill}-{refinement.category.value}.md"
        file_path = history_dir / filename

        # Handle duplicates by adding suffix
        counter = 1
        while file_path.exists():
            filename = f"{refinement.created.strftime('%Y-%m-%d')}-{refinement.skill}-{refinement.category.value}-{counter}.md"
            file_path = history_dir / filename
            counter += 1

        content = self._format_history_entry(refinement)
        file_path.write_text(content)

    def _update_pattern_tracking(self, refinement: Refinement) -> Optional[Pattern]:
        """Update pattern tracking and return the pattern if found/created."""
        patterns = self.load_patterns()

        # Try to find matching pattern
        matching_pattern = self._find_matching_pattern(refinement, patterns)

        if matching_pattern:
            # Update existing pattern
            matching_pattern.count += 1
            matching_pattern.refinement_ids.append(refinement.id)
            if refinement.project not in matching_pattern.projects:
                matching_pattern.projects.append(refinement.project)
            matching_pattern.last_seen = datetime.now()

            if matching_pattern.count >= GENERALIZATION_THRESHOLD:
                matching_pattern.status = PatternStatus.READY

            refinement.pattern_id = matching_pattern.id
        else:
            # Create new pattern
            matching_pattern = Pattern(
                id=get_pattern_id(),
                name=self._generate_pattern_name(refinement),
                description=self._generate_pattern_description(refinement),
                affected_skills=[refinement.skill],
                refinement_ids=[refinement.id],
                projects=[refinement.project] if refinement.project else [],
                count=1,
                status=PatternStatus.TRACKING,
            )
            refinement.pattern_id = matching_pattern.id
            patterns.append(matching_pattern)

        # Save updated patterns
        self._save_patterns(patterns)

        return matching_pattern

    def _find_matching_pattern(self, refinement: Refinement, patterns: List[Pattern]) -> Optional[Pattern]:
        """Find an existing pattern that matches this refinement."""
        for pattern in patterns:
            # Match by skill + section
            if refinement.skill in pattern.affected_skills:
                # Check if target section matches any refinement in pattern
                if refinement.target_section in pattern.name.lower().replace(" ", "-"):
                    return pattern

            # Match by similar content (simplified)
            if refinement.patch_content and pattern.proposed_changes:
                for change in pattern.proposed_changes.values():
                    if self._content_similarity(refinement.patch_content, change) > 0.7:
                        return pattern

        return None

    def _content_similarity(self, content1: str, content2: str) -> float:
        """Simple content similarity check."""
        # Normalize
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union) if union else 0.0

    def _generate_pattern_name(self, refinement: Refinement) -> str:
        """Generate a descriptive pattern name."""
        parts = refinement.target_section.replace("/", " ").replace("-", " ").split()
        return " ".join(word.capitalize() for word in parts[-3:])

    def _generate_pattern_description(self, refinement: Refinement) -> str:
        """Generate pattern description from refinement."""
        return f"{refinement.category.value.capitalize()} modification for {refinement.skill}: {refinement.root_cause or refinement.expected_behavior}"

    def _save_patterns(self, patterns: List[Pattern]) -> None:
        """Save patterns to aggregated-patterns.md."""
        patterns_file = self.user_dir / AGGREGATED_PATTERNS_FILE

        ready = [p for p in patterns if p.status == PatternStatus.READY]
        tracking = [p for p in patterns if p.status == PatternStatus.TRACKING]
        generalized = [p for p in patterns if p.status == PatternStatus.GENERALIZED]

        content = f"""# Aggregated Refinement Patterns

> Auto-updated when pattern count >= {GENERALIZATION_THRESHOLD}
> Last aggregation: {datetime.now().isoformat()}

## Ready for Generalization (count >= {GENERALIZATION_THRESHOLD})

"""
        for pattern in ready:
            content += self._format_pattern_entry(pattern) + "\n---\n\n"

        content += "## Tracking (count = 1)\n\n"
        for pattern in tracking:
            content += self._format_pattern_entry(pattern) + "\n---\n\n"

        content += "## Archived (Generalized)\n\n"
        for pattern in generalized:
            content += self._format_pattern_entry(pattern) + "\n---\n\n"

        patterns_file.write_text(content)

    def _add_to_generalization_queue(self, pattern: Pattern) -> None:
        """Add pattern to generalization queue."""
        queue_file = self.user_dir / GENERALIZATION_QUEUE_FILE
        content = queue_file.read_text() if queue_file.exists() else _get_generalization_queue_template()

        entry = self._format_queue_entry(pattern)

        if "## Ready for Review" in content:
            content = content.replace(
                "## Ready for Review\n",
                f"## Ready for Review\n\n{entry}\n",
            )
        else:
            content += f"\n## Ready for Review\n\n{entry}\n"

        queue_file.write_text(content)

    def _format_suggested_entry(self, refinement: Refinement) -> str:
        """Format refinement for suggested-refinements.md."""
        return f"""### {refinement.id} | {refinement.skill} / {refinement.target_section}
- **Project:** {refinement.project or 'unknown'}
- **Category:** {refinement.category.value}
- **Date:** {refinement.created.strftime('%Y-%m-%d')}
- **Status:** {refinement.status}

**Observation:**
{refinement.actual_behavior}

**Expected Behavior:**
{refinement.expected_behavior}

**Reproduction:**
```
{refinement.example or 'N/A'}
```

**Proposed Change:**
```
{refinement.patch_content or 'See patch file'}
```

**Override Type:** {refinement.override_type.value}
**Generalization Potential:** {refinement.generalization_potential}
**Pattern ID:** {refinement.pattern_id or 'new pattern'}
"""

    def _format_history_entry(self, refinement: Refinement) -> str:
        """Format refinement for history file."""
        return f"""# Refinement: {refinement.id}

> Created: {refinement.created.isoformat()}
> Status: {refinement.status}

## Summary

- **Skill:** {refinement.skill}
- **Category:** {refinement.category.value}
- **Override Type:** {refinement.override_type.value}
- **Target:** {refinement.target_section}
- **Project:** {refinement.project or 'unknown'}

## Issue

**Expected:**
{refinement.expected_behavior}

**Actual:**
{refinement.actual_behavior}

**Example:**
```
{refinement.example or 'N/A'}
```

## Analysis

**Root Cause:**
{refinement.root_cause}

**Confidence:** {refinement.confidence:.0%}

## Resolution

**Patch Action:** {refinement.patch_action.value if refinement.patch_action else 'N/A'}
**Marker:** {refinement.patch_marker or 'N/A'}

**Content:**
```
{refinement.patch_content}
```

## Pattern Tracking

- **Pattern ID:** {refinement.pattern_id or 'new'}
- **Generalization Potential:** {refinement.generalization_potential}

---

> Applied: {refinement.applied.isoformat() if refinement.applied else 'pending'}
"""

    def _format_pattern_entry(self, pattern: Pattern) -> str:
        """Format pattern for aggregated-patterns.md."""
        status_emoji = {"tracking": "⚪", "ready-for-generalization": "🟡", "generalized": "✅", "dismissed": "⛔"}

        return f"""### {status_emoji.get(pattern.status.value, '⚪')} {pattern.id}: {pattern.name}
- **First seen:** {pattern.first_seen.strftime('%Y-%m-%d')} ({pattern.projects[0] if pattern.projects else 'unknown'})
- **Count:** {pattern.count}
- **Status:** {pattern.status.value}

**Affected Skills:**
{chr(10).join(f'- {s}' for s in pattern.affected_skills)}

**Description:**
{pattern.description}

**Refinement IDs:** {', '.join(pattern.refinement_ids)}
"""

    def _format_queue_entry(self, pattern: Pattern) -> str:
        """Format pattern for generalization-queue.md."""
        return f"""### {pattern.id}: {pattern.name}
- **Priority:** {'High' if pattern.count >= 3 else 'Medium'} ({pattern.count} occurrences)
- **Confidence:** High (consistent pattern)
- **Breaking Changes:** None (additive)

**Skills to Update:**
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(pattern.affected_skills))}

**To Apply:**
```bash
/apply-generalization {pattern.id}
```
"""

    def _parse_patterns_file(self, content: str) -> List[Pattern]:
        """Parse patterns from aggregated-patterns.md content."""
        patterns = []

        # Simple regex-based parsing
        pattern_blocks = re.findall(
            r"### [⚪🟡✅⛔] (PATTERN-\d+): (.+?)\n(.+?)(?=### [⚪🟡✅⛔] PATTERN-|\Z)",
            content,
            re.DOTALL,
        )

        for pattern_id, name, block in pattern_blocks:
            try:
                # Extract fields
                count_match = re.search(r"\*\*Count:\*\* (\d+)", block)
                status_match = re.search(r"\*\*Status:\*\* ([\w-]+)", block)
                skills_match = re.findall(r"- (\S+)", block.split("**Affected Skills:**")[1].split("**")[0] if "**Affected Skills:**" in block else "")
                desc_match = re.search(r"\*\*Description:\*\*\n(.+?)(?=\*\*|$)", block, re.DOTALL)
                refs_match = re.search(r"\*\*Refinement IDs:\*\* (.+)", block)

                pattern = Pattern(
                    id=pattern_id,
                    name=name.strip(),
                    description=desc_match.group(1).strip() if desc_match else "",
                    affected_skills=skills_match,
                    refinement_ids=refs_match.group(1).split(", ") if refs_match else [],
                    count=int(count_match.group(1)) if count_match else 1,
                    status=PatternStatus(status_match.group(1)) if status_match else PatternStatus.TRACKING,
                )
                patterns.append(pattern)
            except Exception:
                continue

        return patterns

    def _parse_refinement_entry(self, content: str) -> Optional[Refinement]:
        """Parse a refinement from history file content."""
        try:
            # Extract ID
            id_match = re.search(r"# Refinement: (REF-[\d-]+)", content)
            if not id_match:
                return None

            # Extract other fields (simplified)
            skill_match = re.search(r"\*\*Skill:\*\* (.+)", content)
            category_match = re.search(r"\*\*Category:\*\* (.+)", content)
            override_match = re.search(r"\*\*Override Type:\*\* (.+)", content)
            target_match = re.search(r"\*\*Target:\*\* (.+)", content)

            from .models import OverrideType, RefinementCategory

            return Refinement(
                id=id_match.group(1),
                skill=skill_match.group(1).strip() if skill_match else "unknown",
                category=RefinementCategory(category_match.group(1).strip()) if category_match else RefinementCategory.CONTENT,
                override_type=OverrideType(override_match.group(1).strip()) if override_match else OverrideType.SECTION_PATCH,
                target_section=target_match.group(1).strip() if target_match else "",
                expected_behavior="",
                actual_behavior="",
            )
        except Exception:
            return None


# Template functions
def _get_suggested_refinements_template() -> str:
    return f"""# Suggested Skill Refinements

> Last updated: {datetime.now().isoformat()}
> Sync status: ⚪ Local only

## Pending Review

<!-- New refinements will be added here -->

---

## Recently Applied

<!-- Applied refinements move here -->
"""


def _get_aggregated_patterns_template() -> str:
    return f"""# Aggregated Refinement Patterns

> Auto-updated when pattern count >= {GENERALIZATION_THRESHOLD}
> Last aggregation: {datetime.now().isoformat()}

## Ready for Generalization (count >= {GENERALIZATION_THRESHOLD})

<!-- Patterns ready for user-scope application -->

## Tracking (count = 1)

<!-- Patterns being tracked for future generalization -->

## Archived (Generalized)

<!-- Patterns already applied to user-scope skills -->
"""


def _get_generalization_queue_template() -> str:
    return """# Generalization Queue

> Refinements ready for user-scope skill updates
> Review and apply with: /apply-generalization [PATTERN-ID]

## Ready for Review

<!-- Patterns ready for generalization -->

---

## Pending More Data

<!-- Patterns with count = 1, awaiting second occurrence -->
"""
