#!/usr/bin/env python3
"""
Analyze gap between expected and actual skill behavior.

Determines:
- Root cause of the issue
- Appropriate override type (patch, extend, config, etc.)
- Whether guided mode is needed for ambiguous cases
- Generalization potential

Usage:
    python analyze_gap.py --skill SKILL --category CATEGORY \
        --expected "expected behavior" --actual "actual behavior" \
        [--context-file FILE] [--json]

    # As module
    from analyze_gap import GapAnalyzer
    analyzer = GapAnalyzer()
    analysis = analyzer.analyze(context, user_input)
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common.models import (
    GapAnalysis,
    GuidedModeReason,
    OverrideType,
    PatchAction,
    RefinementCategory,
    RefinementContext,
)
from common.persistence import USER_REFINEMENTS_DIR


class GapAnalyzer:
    """Analyze skill gaps and determine refinement approach."""

    # Confidence threshold for guided mode
    CONFIDENCE_THRESHOLD = 0.7

    # Keywords that suggest specific categories
    CATEGORY_KEYWORDS = {
        RefinementCategory.TRIGGER: [
            "trigger", "activate", "detect", "recognize", "fire", "start",
            "keyword", "phrase", "pattern match",
        ],
        RefinementCategory.HOOK: [
            "hook", "pre-commit", "post-commit", "automation", "script",
            "shell", "bash", "block", "prevent", "validate",
        ],
        RefinementCategory.CONTENT: [
            "output", "response", "format", "message", "text", "display",
            "show", "print", "return",
        ],
        RefinementCategory.TOOL: [
            "mcp", "tool", "integration", "api", "service", "command",
            "desktop commander", "sentry", "zen",
        ],
        RefinementCategory.PATTERN: [
            "pattern", "regex", "match", "detect", "find", "search",
            "validation", "check", "verify",
        ],
        RefinementCategory.CONFIG: [
            "config", "setting", "option", "parameter", "threshold",
            "value", "environment", "variable",
        ],
    }

    # Keywords that suggest specific override types
    OVERRIDE_KEYWORDS = {
        OverrideType.SECTION_PATCH: [
            "fix", "modify", "change", "update", "adjust", "tweak",
            "small change", "minor",
        ],
        OverrideType.EXTENSION: [
            "add", "extend", "new", "include", "append", "extra",
            "additional", "more",
        ],
        OverrideType.CONFIG_OVERRIDE: [
            "config", "setting", "threshold", "value", "parameter",
            "environment",
        ],
        OverrideType.HOOK_OVERRIDE: [
            "hook", "script", "shell", "bash", "automation",
        ],
        OverrideType.FULL_OVERRIDE: [
            "replace", "rewrite", "complete", "entire", "whole",
            "fundamentally",
        ],
    }

    # Patterns that suggest high generalization potential
    GENERALIZABLE_PATTERNS = [
        r"__tests__",
        r"fixtures",
        r"__mocks__",
        r"\.test\.",
        r"\.spec\.",
        r"node_modules",
        r"\.env",
        r"timeout",
        r"threshold",
        r"exclude",
        r"ignore",
    ]

    def __init__(self):
        self.user_refinements_dir = USER_REFINEMENTS_DIR

    def analyze(
        self,
        context: RefinementContext,
        user_input: Dict[str, str],
    ) -> GapAnalysis:
        """
        Analyze the gap and determine refinement approach.

        Args:
            context: Gathered context from ContextGatherer
            user_input: Dict with keys: expected, actual, example, desired_outcome, category

        Returns:
            GapAnalysis with recommendations
        """
        # Determine category if not provided
        category = self._determine_category(user_input, context)

        # Determine override type
        override_type = self._determine_override_type(category, user_input, context)

        # Find target section
        target_section = self._find_target_section(category, user_input, context)

        # Calculate confidence
        confidence = self._calculate_confidence(
            category, override_type, target_section, user_input, context
        )

        # Check if guided mode needed
        needs_guided, reasons, questions = self._check_guided_mode(
            confidence, category, override_type, user_input, context
        )

        # Assess generalization potential
        gen_potential, pattern_id = self._assess_generalization(user_input, context)

        # Determine patch details
        patch_action, patch_marker = self._determine_patch_action(
            override_type, target_section, user_input
        )

        # Identify root cause
        root_cause = self._identify_root_cause(category, user_input, context)

        # List affected files
        affected_files = self._list_affected_files(
            context.target_skill or "", target_section, override_type
        )

        # Check for breaking changes
        breaking_changes = self._identify_breaking_changes(
            override_type, target_section, user_input
        )

        return GapAnalysis(
            root_cause=root_cause,
            override_type=override_type,
            target_section=target_section,
            target_skill=context.target_skill or "unknown",
            confidence=confidence,
            needs_guided_mode=needs_guided,
            guided_mode_reasons=reasons,
            clarifying_questions=questions,
            generalization_potential=gen_potential,
            pattern_id=pattern_id,
            similar_refinements=[r.get("id", "") for r in context.similar_refinements],
            affected_files=affected_files,
            breaking_changes=breaking_changes,
            patch_action=patch_action,
            patch_marker=patch_marker,
            patch_content=user_input.get("patch_content", ""),
        )

    def _determine_category(
        self,
        user_input: Dict[str, str],
        context: RefinementContext,
    ) -> RefinementCategory:
        """Determine the refinement category from input and context."""
        # Check if explicitly provided
        if "category" in user_input:
            try:
                return RefinementCategory(user_input["category"])
            except ValueError:
                pass

        # Analyze text for category keywords
        text = " ".join([
            user_input.get("expected", ""),
            user_input.get("actual", ""),
            user_input.get("example", ""),
        ]).lower()

        scores = {}
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[category] = score

        if scores:
            return max(scores, key=scores.get)

        # Default to content if can't determine
        return RefinementCategory.CONTENT

    def _determine_override_type(
        self,
        category: RefinementCategory,
        user_input: Dict[str, str],
        context: RefinementContext,
    ) -> OverrideType:
        """Determine the appropriate override type."""
        # Check if explicitly provided
        if "override_type" in user_input:
            try:
                return OverrideType(user_input["override_type"])
            except ValueError:
                pass

        # Map category to likely override type
        category_to_override = {
            RefinementCategory.HOOK: OverrideType.SECTION_PATCH,
            RefinementCategory.CONFIG: OverrideType.CONFIG_OVERRIDE,
            RefinementCategory.NEW: OverrideType.EXTENSION,
        }

        if category in category_to_override:
            return category_to_override[category]

        # Analyze text for override keywords
        text = " ".join([
            user_input.get("expected", ""),
            user_input.get("actual", ""),
            user_input.get("desired_outcome", ""),
        ]).lower()

        scores = {}
        for override_type, keywords in self.OVERRIDE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[override_type] = score

        if scores:
            return max(scores, key=scores.get)

        # Default to section patch for most cases
        return OverrideType.SECTION_PATCH

    def _find_target_section(
        self,
        category: RefinementCategory,
        user_input: Dict[str, str],
        context: RefinementContext,
    ) -> str:
        """Find the specific section to target."""
        # Check if explicitly provided
        if "target" in user_input:
            return user_input["target"]

        # Map category to default sections
        category_to_section = {
            RefinementCategory.TRIGGER: "triggers",
            RefinementCategory.HOOK: "hooks",
            RefinementCategory.CONTENT: "workflow",
            RefinementCategory.TOOL: "mcp-integration",
            RefinementCategory.PATTERN: "patterns",
            RefinementCategory.CONFIG: "config",
            RefinementCategory.NEW: "new-capability",
        }

        base_section = category_to_section.get(category, "content")

        # Try to be more specific based on context
        text = " ".join([
            user_input.get("expected", ""),
            user_input.get("actual", ""),
            user_input.get("example", ""),
        ]).lower()

        # Look for specific hook names
        hook_patterns = [
            r"duplicate[- ]?check",
            r"pre[- ]?commit",
            r"session[- ]?end",
            r"skill[- ]?suggester",
        ]
        for pattern in hook_patterns:
            if re.search(pattern, text):
                return f"hooks/{pattern.replace('[- ]?', '-')}"

        # Look for specific command references
        if "command" in text:
            command_match = re.search(r"(/\w+|start|done|refine)", text)
            if command_match:
                return f"commands/{command_match.group(1).strip('/')}"

        return base_section

    def _calculate_confidence(
        self,
        category: RefinementCategory,
        override_type: OverrideType,
        target_section: str,
        user_input: Dict[str, str],
        context: RefinementContext,
    ) -> float:
        """Calculate confidence score for the analysis."""
        confidence = 0.5  # Base confidence

        # Explicit inputs increase confidence
        if user_input.get("category"):
            confidence += 0.15
        if user_input.get("target"):
            confidence += 0.15
        if user_input.get("example"):
            confidence += 0.1

        # Context availability increases confidence
        if context.similar_refinements:
            confidence += 0.1
        if context.pattern_matches:
            confidence += 0.1
        if context.skill_files:
            confidence += 0.05

        # Specific target section increases confidence
        if "/" in target_section:  # More specific path
            confidence += 0.1

        # Cap at 1.0
        return min(confidence, 1.0)

    def _check_guided_mode(
        self,
        confidence: float,
        category: RefinementCategory,
        override_type: OverrideType,
        user_input: Dict[str, str],
        context: RefinementContext,
    ) -> Tuple[bool, List[GuidedModeReason], List[str]]:
        """Determine if guided mode is needed."""
        reasons = []
        questions = []

        # Low confidence triggers guided mode
        if confidence < self.CONFIDENCE_THRESHOLD:
            reasons.append(GuidedModeReason.AMBIGUOUS_TARGET)
            questions.append("Which specific part of the skill should be modified?")

        # Check for multiple valid approaches
        if self._has_multiple_approaches(category, user_input):
            reasons.append(GuidedModeReason.MULTIPLE_OPTIONS)
            questions.append(
                "Should this be a patch to existing behavior or a new capability?"
            )

        # Check for cross-skill impact
        if self._affects_multiple_skills(user_input, context):
            reasons.append(GuidedModeReason.CROSS_SKILL)
            questions.append(
                "This appears to affect multiple skills. Should all be updated?"
            )

        # Check for potential breaking changes
        if override_type == OverrideType.FULL_OVERRIDE:
            reasons.append(GuidedModeReason.BREAKING_CHANGE)
            questions.append(
                "A full override will replace the entire skill. Are you sure?"
            )

        # Check for unclear intent
        if not user_input.get("expected") or not user_input.get("actual"):
            reasons.append(GuidedModeReason.UNCLEAR_INTENT)
            questions.append("Can you describe the expected vs actual behavior?")

        return len(reasons) > 0, reasons, questions

    def _has_multiple_approaches(
        self,
        category: RefinementCategory,
        user_input: Dict[str, str],
    ) -> bool:
        """Check if multiple valid approaches exist."""
        # New capabilities could be extension or new section
        if category == RefinementCategory.NEW:
            return True

        # Vague descriptions suggest multiple approaches
        text = user_input.get("expected", "") + user_input.get("actual", "")
        vague_indicators = ["maybe", "could", "might", "possibly", "or"]
        return any(ind in text.lower() for ind in vague_indicators)

    def _affects_multiple_skills(
        self,
        user_input: Dict[str, str],
        context: RefinementContext,
    ) -> bool:
        """Check if refinement affects multiple skills."""
        text = " ".join([
            user_input.get("expected", ""),
            user_input.get("actual", ""),
            user_input.get("example", ""),
        ]).lower()

        # Look for multiple skill references
        skill_mentions = re.findall(
            r"(context-engineering|error-lifecycle|dev-flow|skill-refinement)",
            text,
        )
        return len(set(skill_mentions)) > 1

    def _assess_generalization(
        self,
        user_input: Dict[str, str],
        context: RefinementContext,
    ) -> Tuple[str, Optional[str]]:
        """Assess generalization potential and find matching patterns."""
        text = " ".join([
            user_input.get("expected", ""),
            user_input.get("actual", ""),
            user_input.get("example", ""),
            user_input.get("patch_content", ""),
        ]).lower()

        # Check for generalizable patterns
        matches = sum(
            1 for pattern in self.GENERALIZABLE_PATTERNS
            if re.search(pattern, text, re.IGNORECASE)
        )

        # Check for existing pattern matches
        pattern_id = None
        if context.pattern_matches:
            # Return first matching pattern
            pattern_id = context.pattern_matches[0].split(":")[0].strip()

        # Determine potential
        if matches >= 3 or pattern_id:
            return "high", pattern_id
        elif matches >= 1:
            return "medium", pattern_id
        else:
            return "low", pattern_id

    def _determine_patch_action(
        self,
        override_type: OverrideType,
        target_section: str,
        user_input: Dict[str, str],
    ) -> Tuple[Optional[PatchAction], Optional[str]]:
        """Determine the patch action and marker."""
        if override_type != OverrideType.SECTION_PATCH:
            return None, None

        text = " ".join([
            user_input.get("expected", ""),
            user_input.get("desired_outcome", ""),
        ]).lower()

        # Determine action based on keywords
        if any(kw in text for kw in ["add", "append", "include", "new"]):
            return PatchAction.APPEND, None
        elif any(kw in text for kw in ["before", "first", "start"]):
            return PatchAction.PREPEND, None
        elif any(kw in text for kw in ["replace", "change", "modify"]):
            return PatchAction.REPLACE_SECTION, target_section.split("/")[-1]
        elif any(kw in text for kw in ["after", "following"]):
            # Try to extract marker from example
            example = user_input.get("example", "")
            marker_match = re.search(r'"([^"]+)"', example)
            marker = marker_match.group(1) if marker_match else None
            return PatchAction.INSERT_AFTER, marker
        elif any(kw in text for kw in ["remove", "delete"]):
            return PatchAction.DELETE_SECTION, target_section.split("/")[-1]

        # Default to append for additions
        return PatchAction.APPEND, None

    def _identify_root_cause(
        self,
        category: RefinementCategory,
        user_input: Dict[str, str],
        context: RefinementContext,
    ) -> str:
        """Identify the root cause of the issue."""
        expected = user_input.get("expected", "")
        actual = user_input.get("actual", "")

        if not expected or not actual:
            return "Unable to determine root cause without expected/actual behavior"

        # Generate root cause description
        category_descriptions = {
            RefinementCategory.TRIGGER: "Skill trigger conditions don't match expected scenarios",
            RefinementCategory.HOOK: "Hook logic doesn't handle this case correctly",
            RefinementCategory.CONTENT: "Skill output doesn't match expected format/content",
            RefinementCategory.TOOL: "Tool integration not configured for this scenario",
            RefinementCategory.PATTERN: "Pattern matching logic missing required case",
            RefinementCategory.CONFIG: "Configuration values don't match environment needs",
            RefinementCategory.NEW: "Required capability doesn't exist in current skill",
        }

        base_cause = category_descriptions.get(
            category,
            "Skill behavior doesn't match expected outcome",
        )

        # Add specifics from input
        if "block" in actual.lower() or "prevent" in actual.lower():
            return f"{base_cause}. False positive: legitimate action being blocked."
        elif "miss" in actual.lower() or "ignore" in actual.lower():
            return f"{base_cause}. False negative: expected trigger not firing."
        elif "error" in actual.lower():
            return f"{base_cause}. Error in processing logic."

        return f"{base_cause}. Expected: {expected[:50]}... Actual: {actual[:50]}..."

    def _list_affected_files(
        self,
        skill: str,
        target_section: str,
        override_type: OverrideType,
    ) -> List[str]:
        """List files that will be affected by this refinement."""
        files = []

        base_path = f".claude/skills/{skill}"

        if override_type == OverrideType.SECTION_PATCH:
            files.append(f"{base_path}/SKILL.patch.md")
        elif override_type == OverrideType.EXTENSION:
            files.append(f"{base_path}/SKILL.extend.md")
        elif override_type == OverrideType.CONFIG_OVERRIDE:
            files.append(f"{base_path}/skill-config.json")
        elif override_type == OverrideType.FULL_OVERRIDE:
            files.append(f"{base_path}/SKILL.md")
        elif override_type == OverrideType.HOOK_OVERRIDE:
            hook_name = target_section.split("/")[-1] if "/" in target_section else "hook"
            files.append(f"{base_path}/hooks/{hook_name}.sh")
        elif override_type == OverrideType.SCRIPT_OVERRIDE:
            script_name = target_section.split("/")[-1] if "/" in target_section else "script"
            files.append(f"{base_path}/scripts/{script_name}.py")

        return files

    def _identify_breaking_changes(
        self,
        override_type: OverrideType,
        target_section: str,
        user_input: Dict[str, str],
    ) -> List[str]:
        """Identify potential breaking changes."""
        breaking = []

        # Full override is always potentially breaking
        if override_type == OverrideType.FULL_OVERRIDE:
            breaking.append("Full override replaces entire skill - all customizations lost")

        # Deletions are potentially breaking
        if "delete" in user_input.get("desired_outcome", "").lower():
            breaking.append(f"Deleting {target_section} may break dependent functionality")

        # Hook replacements may break CI/CD
        if override_type == OverrideType.HOOK_OVERRIDE:
            breaking.append("Hook override may affect CI/CD pipelines")

        return breaking


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze skill gap and determine refinement approach",
    )

    parser.add_argument(
        "--skill",
        required=True,
        help="Target skill name",
    )
    parser.add_argument(
        "--category",
        choices=["trigger", "content", "hook", "tool", "pattern", "config", "new"],
        help="Refinement category (auto-detected if not provided)",
    )
    parser.add_argument(
        "--expected",
        required=True,
        help="Expected behavior description",
    )
    parser.add_argument(
        "--actual",
        required=True,
        help="Actual behavior description",
    )
    parser.add_argument(
        "--example",
        help="Reproduction example",
    )
    parser.add_argument(
        "--desired-outcome",
        help="Desired outcome after refinement",
    )
    parser.add_argument(
        "--target",
        help="Target section (auto-detected if not provided)",
    )
    parser.add_argument(
        "--context-file",
        help="Path to context JSON file from gather_context.py",
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

    # Build user input
    user_input = {
        "expected": args.expected,
        "actual": args.actual,
    }
    if args.category:
        user_input["category"] = args.category
    if args.example:
        user_input["example"] = args.example
    if args.desired_outcome:
        user_input["desired_outcome"] = args.desired_outcome
    if args.target:
        user_input["target"] = args.target

    # Load or create context
    if args.context_file:
        with open(args.context_file) as f:
            context_data = json.load(f)
        context = RefinementContext(**context_data)
    else:
        context = RefinementContext(target_skill=args.skill)

    # Analyze
    analyzer = GapAnalyzer()
    analysis = analyzer.analyze(context, user_input)

    # Output
    if args.json:
        print(json.dumps(analysis.to_dict(), indent=2))
    else:
        print(_format_analysis(analysis))

    return 0


def _format_analysis(analysis: GapAnalysis) -> str:
    """Format analysis as human-readable output."""
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📊 Gap Analysis",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🎯 Target Skill: {analysis.target_skill}",
        f"📍 Target Section: {analysis.target_section}",
        f"📊 Override Type: {analysis.override_type.value}",
        f"🔒 Confidence: {analysis.confidence:.0%}",
        "",
        "📝 Root Cause:",
        f"   {analysis.root_cause}",
        "",
    ]

    if analysis.patch_action:
        lines.extend([
            "🔧 Patch Details:",
            f"   Action: {analysis.patch_action.value}",
        ])
        if analysis.patch_marker:
            lines.append(f"   Marker: \"{analysis.patch_marker}\"")
        lines.append("")

    lines.extend([
        f"🔮 Generalization Potential: {analysis.generalization_potential}",
    ])
    if analysis.pattern_id:
        lines.append(f"   Matches pattern: {analysis.pattern_id}")
    lines.append("")

    if analysis.needs_guided_mode:
        lines.extend([
            "⚠️ Guided Mode Recommended:",
        ])
        for reason in analysis.guided_mode_reasons:
            lines.append(f"   • {reason.value}")
        lines.append("")
        lines.append("❓ Clarifying Questions:")
        for q in analysis.clarifying_questions:
            lines.append(f"   • {q}")
        lines.append("")

    if analysis.affected_files:
        lines.extend([
            "📁 Affected Files:",
        ])
        for f in analysis.affected_files:
            lines.append(f"   • {f}")
        lines.append("")

    if analysis.breaking_changes:
        lines.extend([
            "⚠️ Breaking Changes:",
        ])
        for bc in analysis.breaking_changes:
            lines.append(f"   • {bc}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
