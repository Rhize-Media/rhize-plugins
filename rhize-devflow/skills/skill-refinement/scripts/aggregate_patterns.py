#!/usr/bin/env python3
"""
Aggregate refinement patterns across projects.

Tracks refinement frequency, auto-triggers generalization when count >= 2,
and maintains the generalization queue.

Usage:
    python aggregate_patterns.py --refinement REF-ID
    python aggregate_patterns.py --check-all
    python aggregate_patterns.py --list-ready

    # As module
    from aggregate_patterns import PatternAggregator
    aggregator = PatternAggregator()
    pattern = aggregator.process_new_refinement(refinement_data)
"""

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common.models import Pattern, PatternStatus, Refinement
from common.persistence import (
    RefinementPersistence,
    USER_REFINEMENTS_DIR,
    ensure_user_refinements_dir,
    get_pattern_id,
)

# Generalization threshold - auto-trigger when count >= this
GENERALIZATION_THRESHOLD = 2

# Similarity threshold for pattern matching (0-1)
SIMILARITY_THRESHOLD = 0.6


class PatternAggregator:
    """Track and aggregate refinement patterns across projects."""

    def __init__(self, refinements_dir: Optional[Path] = None):
        """
        Initialize pattern aggregator.

        Args:
            refinements_dir: User refinements directory. Defaults to ~/.claude/skill-refinements/
        """
        self.refinements_dir = refinements_dir or USER_REFINEMENTS_DIR
        ensure_user_refinements_dir()
        self.persistence = RefinementPersistence(self.refinements_dir)
        self.patterns_file = self.refinements_dir / "aggregated-patterns.md"
        self.queue_file = self.refinements_dir / "generalization-queue.md"

    def process_new_refinement(self, refinement: Refinement) -> Optional[Pattern]:
        """
        Process a new refinement and update pattern tracking.

        Args:
            refinement: The refinement to process.

        Returns:
            The matched or created pattern, or None if processing failed.
        """
        # Load existing patterns
        patterns = self._load_patterns()

        # Find matching pattern
        matching_pattern = self._find_matching_pattern(refinement, patterns)

        if matching_pattern:
            # Update existing pattern
            pattern = self._update_pattern(matching_pattern, refinement)
        else:
            # Create new pattern
            pattern = self._create_pattern(refinement)
            patterns.append(pattern)

        # Check if threshold met
        if pattern.count >= GENERALIZATION_THRESHOLD:
            if pattern.status != PatternStatus.GENERALIZED:
                pattern.status = PatternStatus.READY
                self._add_to_generalization_queue(pattern)

        # Save patterns
        self._save_patterns(patterns)

        return pattern

    def check_all_patterns(self) -> List[Pattern]:
        """
        Re-check all patterns and update their status.

        Returns:
            List of patterns that are ready for generalization.
        """
        patterns = self._load_patterns()
        ready_patterns = []

        for pattern in patterns:
            if pattern.count >= GENERALIZATION_THRESHOLD:
                if pattern.status not in [PatternStatus.READY, PatternStatus.GENERALIZED, PatternStatus.DISMISSED]:
                    pattern.status = PatternStatus.READY
                    self._add_to_generalization_queue(pattern)
                    ready_patterns.append(pattern)
            elif pattern.status == PatternStatus.READY:
                # Was ready but count dropped (rare edge case)
                pattern.status = PatternStatus.TRACKING

        self._save_patterns(patterns)
        return ready_patterns

    def get_ready_patterns(self) -> List[Pattern]:
        """Get all patterns ready for generalization."""
        patterns = self._load_patterns()
        return [p for p in patterns if p.status == PatternStatus.READY]

    def get_pattern_by_id(self, pattern_id: str) -> Optional[Pattern]:
        """Get a specific pattern by ID."""
        patterns = self._load_patterns()
        for p in patterns:
            if p.id == pattern_id:
                return p
        return None

    def mark_generalized(self, pattern_id: str) -> bool:
        """
        Mark a pattern as generalized.

        Args:
            pattern_id: The pattern ID to mark.

        Returns:
            True if successful, False if pattern not found.
        """
        patterns = self._load_patterns()
        for p in patterns:
            if p.id == pattern_id:
                p.status = PatternStatus.GENERALIZED
                self._save_patterns(patterns)
                self._remove_from_queue(pattern_id)
                return True
        return False

    def dismiss_pattern(self, pattern_id: str, reason: str) -> bool:
        """
        Dismiss a pattern (won't generalize).

        Args:
            pattern_id: The pattern ID to dismiss.
            reason: Reason for dismissal.

        Returns:
            True if successful, False if pattern not found.
        """
        patterns = self._load_patterns()
        for p in patterns:
            if p.id == pattern_id:
                p.status = PatternStatus.DISMISSED
                if not hasattr(p, 'notes') or p.notes is None:
                    p.notes = ""
                p.notes += f"\nDismissed: {reason}"
                self._save_patterns(patterns)
                self._remove_from_queue(pattern_id)
                return True
        return False

    # =========================================================================
    # Pattern Matching
    # =========================================================================

    def _find_matching_pattern(
        self, refinement: Refinement, patterns: List[Pattern]
    ) -> Optional[Pattern]:
        """
        Find existing pattern that matches this refinement.

        Matching criteria:
        1. Same skill + same target section
        2. Similar description/content
        3. Same override type + similar content
        """
        for pattern in patterns:
            # Skip generalized/dismissed patterns
            if pattern.status in [PatternStatus.GENERALIZED, PatternStatus.DISMISSED]:
                continue

            # Check skill match
            if refinement.skill not in pattern.affected_skills:
                # But could still match if similar section
                pass

            # Check section match
            if refinement.target_section in pattern.description:
                score = self._calculate_similarity(refinement, pattern)
                if score >= SIMILARITY_THRESHOLD:
                    return pattern

            # Check content similarity
            score = self._calculate_similarity(refinement, pattern)
            if score >= SIMILARITY_THRESHOLD:
                return pattern

        return None

    def _calculate_similarity(self, refinement: Refinement, pattern: Pattern) -> float:
        """
        Calculate similarity score between refinement and pattern.

        Returns:
            Score from 0-1 indicating similarity.
        """
        score = 0.0

        # Same skill: +0.3
        if refinement.skill in pattern.affected_skills:
            score += 0.3

        # Same target section: +0.3
        if refinement.target_section and refinement.target_section in pattern.description:
            score += 0.3

        # Same category: +0.2
        if hasattr(pattern, 'category') and refinement.category.value == pattern.category:
            score += 0.2

        # Similar keywords in description: +0.2
        ref_words = set(refinement.expected_behavior.lower().split() + refinement.actual_behavior.lower().split())
        pattern_words = set(pattern.description.lower().split())
        if ref_words & pattern_words:
            overlap = len(ref_words & pattern_words) / max(len(ref_words), len(pattern_words), 1)
            score += 0.2 * overlap

        return min(score, 1.0)

    # =========================================================================
    # Pattern CRUD
    # =========================================================================

    def _create_pattern(self, refinement: Refinement) -> Pattern:
        """Create a new pattern from a refinement."""
        pattern_id = get_pattern_id()

        # Generate pattern name from refinement
        name = self._generate_pattern_name(refinement)

        return Pattern(
            id=pattern_id,
            name=name,
            description=f"{refinement.target_section}: {refinement.expected_behavior[:100]}",
            affected_skills=[refinement.skill],
            refinement_ids=[refinement.id],
            projects=[refinement.project] if refinement.project else [],
            count=1,
            status=PatternStatus.TRACKING,
            proposed_changes={},
            first_seen=datetime.now(),
            last_seen=datetime.now(),
        )

    def _update_pattern(self, pattern: Pattern, refinement: Refinement) -> Pattern:
        """Update an existing pattern with a new refinement."""
        # Update count
        pattern.count += 1

        # Add refinement ID
        if refinement.id not in pattern.refinement_ids:
            pattern.refinement_ids.append(refinement.id)

        # Add skill if new
        if refinement.skill not in pattern.affected_skills:
            pattern.affected_skills.append(refinement.skill)

        # Add project if new
        if refinement.project and refinement.project not in pattern.projects:
            pattern.projects.append(refinement.project)

        # Update timestamp
        pattern.last_seen = datetime.now()

        return pattern

    def _generate_pattern_name(self, refinement: Refinement) -> str:
        """Generate a descriptive name for a pattern."""
        # Extract key words from expected/actual
        words = []

        # Add category
        words.append(refinement.category.value)

        # Add key terms from target
        if refinement.target_section:
            target_words = refinement.target_section.replace("/", " ").replace("-", " ").split()
            words.extend(target_words[:2])

        # Add key terms from expected (first 3 meaningful words)
        expected_words = [w for w in refinement.expected_behavior.split() if len(w) > 3][:3]
        words.extend(expected_words)

        # Create slug
        name = "-".join(words[:5]).lower()
        name = re.sub(r"[^a-z0-9-]", "", name)
        name = re.sub(r"-+", "-", name).strip("-")

        return name or f"pattern-{refinement.skill}"

    # =========================================================================
    # File Operations
    # =========================================================================

    def _load_patterns(self) -> List[Pattern]:
        """Load patterns from aggregated-patterns.md."""
        if not self.patterns_file.exists():
            return []

        patterns = []
        content = self.patterns_file.read_text()

        # Parse pattern blocks
        pattern_regex = r"### ([⚪🟡✅⛔]) (PATTERN-\d+): (.+?)\n(.+?)(?=### [⚪🟡✅⛔] PATTERN-|\Z)"
        matches = re.findall(pattern_regex, content, re.DOTALL)

        for status_icon, pattern_id, name, block in matches:
            # Parse status
            status_map = {
                "⚪": PatternStatus.TRACKING,
                "🟡": PatternStatus.READY,
                "✅": PatternStatus.GENERALIZED,
                "⛔": PatternStatus.DISMISSED,
            }
            status = status_map.get(status_icon, PatternStatus.TRACKING)

            # Parse count
            count_match = re.search(r"\*\*Count:\*\* (\d+)", block)
            count = int(count_match.group(1)) if count_match else 1

            # Parse affected skills
            skills_match = re.search(r"\*\*Affected Skills:\*\*\n((?:- .+\n)+)", block)
            skills = []
            if skills_match:
                skills = re.findall(r"- (.+?)(?:\n|$)", skills_match.group(1))

            # Parse refinement IDs
            refs_match = re.search(r"\*\*Refinement IDs:\*\* (.+)", block)
            refs = []
            if refs_match:
                refs = [r.strip() for r in refs_match.group(1).split(",")]

            # Parse projects
            projects_match = re.search(r"\*\*Projects:\*\* (.+)", block)
            projects = []
            if projects_match:
                projects = [p.strip() for p in projects_match.group(1).split(",")]

            # Parse description
            desc_match = re.search(r"\*\*Description:\*\*\n(.+?)(?=\*\*|$)", block, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else name

            # Parse first/last seen
            first_match = re.search(r"\*\*First seen:\*\* (.+)", block)
            last_match = re.search(r"\*\*Last seen:\*\* (.+)", block)

            first_seen = datetime.now()
            last_seen = datetime.now()
            if first_match:
                try:
                    first_seen = datetime.fromisoformat(first_match.group(1).strip())
                except ValueError:
                    pass
            if last_match:
                try:
                    last_seen = datetime.fromisoformat(last_match.group(1).strip())
                except ValueError:
                    pass

            pattern = Pattern(
                id=pattern_id,
                name=name.strip(),
                description=description,
                affected_skills=skills,
                refinement_ids=refs,
                projects=projects,
                count=count,
                status=status,
                proposed_changes={},
                first_seen=first_seen,
                last_seen=last_seen,
            )
            patterns.append(pattern)

        return patterns

    def _save_patterns(self, patterns: List[Pattern]) -> None:
        """Save patterns to aggregated-patterns.md."""
        ensure_user_refinements_dir()

        # Group patterns by status
        tracking = [p for p in patterns if p.status == PatternStatus.TRACKING]
        ready = [p for p in patterns if p.status == PatternStatus.READY]
        generalized = [p for p in patterns if p.status == PatternStatus.GENERALIZED]
        dismissed = [p for p in patterns if p.status == PatternStatus.DISMISSED]

        lines = [
            "# Aggregated Refinement Patterns",
            "",
            f"> Auto-updated when pattern count >= {GENERALIZATION_THRESHOLD}",
            f"> Last updated: {datetime.now().isoformat()}",
            "",
        ]

        # Ready for Generalization section
        lines.extend([
            "## Ready for Generalization",
            "",
        ])
        if ready:
            for p in ready:
                lines.extend(self._format_pattern(p))
        else:
            lines.append("*No patterns ready for generalization*")
            lines.append("")

        # Tracking section
        lines.extend([
            "---",
            "",
            "## Tracking (count < threshold)",
            "",
        ])
        if tracking:
            for p in tracking:
                lines.extend(self._format_pattern(p))
        else:
            lines.append("*No patterns currently tracking*")
            lines.append("")

        # Generalized section
        lines.extend([
            "---",
            "",
            "## Generalized (Applied)",
            "",
        ])
        if generalized:
            for p in generalized:
                lines.extend(self._format_pattern(p))
        else:
            lines.append("*No patterns generalized yet*")
            lines.append("")

        # Dismissed section
        if dismissed:
            lines.extend([
                "---",
                "",
                "## Dismissed",
                "",
            ])
            for p in dismissed:
                lines.extend(self._format_pattern(p))

        self.patterns_file.write_text("\n".join(lines))

    def _format_pattern(self, pattern: Pattern) -> List[str]:
        """Format a pattern for markdown output."""
        status_icons = {
            PatternStatus.TRACKING: "⚪",
            PatternStatus.READY: "🟡",
            PatternStatus.GENERALIZED: "✅",
            PatternStatus.DISMISSED: "⛔",
        }
        icon = status_icons.get(pattern.status, "⚪")

        lines = [
            f"### {icon} {pattern.id}: {pattern.name}",
            f"- **First seen:** {pattern.first_seen.isoformat() if pattern.first_seen else 'unknown'}",
            f"- **Last seen:** {pattern.last_seen.isoformat() if pattern.last_seen else 'unknown'}",
            f"- **Count:** {pattern.count}",
            f"- **Status:** {pattern.status.value}",
            "",
            "**Affected Skills:**",
        ]

        for skill in pattern.affected_skills:
            lines.append(f"- {skill}")

        lines.append("")
        lines.append("**Description:**")
        lines.append(pattern.description)
        lines.append("")

        if pattern.projects:
            lines.append(f"**Projects:** {', '.join(pattern.projects)}")
        if pattern.refinement_ids:
            lines.append(f"**Refinement IDs:** {', '.join(pattern.refinement_ids)}")

        lines.extend(["", "---", ""])
        return lines

    def _add_to_generalization_queue(self, pattern: Pattern) -> None:
        """Add a pattern to the generalization queue."""
        ensure_user_refinements_dir()

        # Read existing queue
        if self.queue_file.exists():
            content = self.queue_file.read_text()
        else:
            content = self._create_queue_header()

        # Check if already in queue
        if pattern.id in content:
            return

        # Add to queue
        entry = self._format_queue_entry(pattern)

        # Insert after "## Ready for Review" header
        if "## Ready for Review" in content:
            parts = content.split("## Ready for Review", 1)
            content = parts[0] + "## Ready for Review\n\n" + entry + parts[1].lstrip()
        else:
            content += "\n## Ready for Review\n\n" + entry

        self.queue_file.write_text(content)

    def _remove_from_queue(self, pattern_id: str) -> None:
        """Remove a pattern from the generalization queue."""
        if not self.queue_file.exists():
            return

        content = self.queue_file.read_text()

        # Remove pattern block
        pattern_regex = rf"### {pattern_id}: .+?(?=### PATTERN-|\Z)"
        content = re.sub(pattern_regex, "", content, flags=re.DOTALL)

        self.queue_file.write_text(content)

    def _create_queue_header(self) -> str:
        """Create the generalization queue header."""
        return """# Generalization Queue

> Refinements ready for user-scope skill updates
> Review and apply with: /apply-generalization [PATTERN-ID]

"""

    def _format_queue_entry(self, pattern: Pattern) -> str:
        """Format a pattern entry for the queue."""
        return f"""### {pattern.id}: {pattern.name}
- **Priority:** {'High' if pattern.count >= 3 else 'Medium'} ({pattern.count} occurrences)
- **Confidence:** {'High' if pattern.count >= 3 else 'Medium'} (consistent pattern)
- **Breaking Changes:** None (additive)

**Skills to Update:**
{chr(10).join(f'- {skill}' for skill in pattern.affected_skills)}

**To Apply:**
```bash
/apply-generalization {pattern.id}
```

---

"""

    # =========================================================================
    # Output Methods
    # =========================================================================

    def to_summary(self, patterns: List[Pattern]) -> str:
        """Format patterns as human-readable summary."""
        if not patterns:
            return "No patterns found."

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📊 Pattern Summary",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]

        status_icons = {
            PatternStatus.TRACKING: "⚪",
            PatternStatus.READY: "🟡",
            PatternStatus.GENERALIZED: "✅",
            PatternStatus.DISMISSED: "⛔",
        }

        for p in patterns:
            icon = status_icons.get(p.status, "⚪")
            lines.append(f"{icon} {p.id}: {p.name}")
            lines.append(f"   Count: {p.count} | Skills: {', '.join(p.affected_skills)}")
            lines.append(f"   Status: {p.status.value}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Aggregate refinement patterns across projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--refinement",
        help="Process a specific refinement by ID",
    )
    parser.add_argument(
        "--check-all",
        action="store_true",
        help="Re-check all patterns and update status",
    )
    parser.add_argument(
        "--list-ready",
        action="store_true",
        help="List patterns ready for generalization",
    )
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="List all tracked patterns",
    )
    parser.add_argument(
        "--mark-generalized",
        metavar="PATTERN-ID",
        help="Mark a pattern as generalized",
    )
    parser.add_argument(
        "--dismiss",
        metavar="PATTERN-ID",
        help="Dismiss a pattern",
    )
    parser.add_argument(
        "--reason",
        help="Reason for dismissal (use with --dismiss)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    aggregator = PatternAggregator()

    # Process specific refinement
    if args.refinement:
        persistence = RefinementPersistence()
        refinements = persistence.load_refinements()
        refinement = next((r for r in refinements if r.id == args.refinement), None)

        if not refinement:
            print(f"Error: Refinement {args.refinement} not found")
            return 1

        pattern = aggregator.process_new_refinement(refinement)
        if pattern:
            if args.json:
                print(json.dumps(asdict(pattern), indent=2, default=str))
            else:
                print(f"Processed refinement {args.refinement}")
                print(f"Pattern: {pattern.id} ({pattern.name})")
                print(f"Count: {pattern.count}")
                print(f"Status: {pattern.status.value}")
        return 0

    # Check all patterns
    if args.check_all:
        ready = aggregator.check_all_patterns()
        if args.json:
            print(json.dumps([asdict(p) for p in ready], indent=2, default=str))
        else:
            if ready:
                print(f"Found {len(ready)} patterns ready for generalization:")
                for p in ready:
                    print(f"  - {p.id}: {p.name} (count: {p.count})")
            else:
                print("No new patterns ready for generalization")
        return 0

    # List ready patterns
    if args.list_ready:
        ready = aggregator.get_ready_patterns()
        if args.json:
            print(json.dumps([asdict(p) for p in ready], indent=2, default=str))
        else:
            print(aggregator.to_summary(ready))
        return 0

    # List all patterns
    if args.list_all:
        patterns = aggregator._load_patterns()
        if args.json:
            print(json.dumps([asdict(p) for p in patterns], indent=2, default=str))
        else:
            print(aggregator.to_summary(patterns))
        return 0

    # Mark as generalized
    if args.mark_generalized:
        if aggregator.mark_generalized(args.mark_generalized):
            print(f"Marked {args.mark_generalized} as generalized")
            return 0
        else:
            print(f"Error: Pattern {args.mark_generalized} not found")
            return 1

    # Dismiss pattern
    if args.dismiss:
        reason = args.reason or "No reason provided"
        if aggregator.dismiss_pattern(args.dismiss, reason):
            print(f"Dismissed {args.dismiss}: {reason}")
            return 0
        else:
            print(f"Error: Pattern {args.dismiss} not found")
            return 1

    # Default: show help
    print("Usage: aggregate_patterns.py [--refinement ID | --check-all | --list-ready | --list-all]")
    print("Run with --help for more options")
    return 0


if __name__ == "__main__":
    sys.exit(main())
