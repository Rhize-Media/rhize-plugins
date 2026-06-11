#!/usr/bin/env python3
"""
Log skill refinements to user-scope tracking files.

This script handles the file-based logging of refinements, updating:
- suggested-refinements.md (active suggestions)
- refinement-history/ (individual refinement records)
- aggregated-patterns.md (pattern tracking)
- generalization-queue.md (patterns ready for merge)

Usage:
    python log_refinement.py --skill SKILL --category CATEGORY --target TARGET \
        --expected "expected behavior" --actual "actual behavior" \
        [--example "reproduction steps"] [--patch-content "patch content"] \
        [--project PROJECT] [--project-root PATH]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common.models import (
    OverrideType,
    PatchAction,
    Refinement,
    RefinementCategory,
)
from common.persistence import (
    RefinementPersistence,
    ensure_user_refinements_dir,
    get_refinement_id,
)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Log a skill refinement to user-scope tracking files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Log a hook refinement
    python log_refinement.py \\
        --skill context-engineering \\
        --category hook \\
        --target hooks/duplicate-check \\
        --expected "Test fixtures should be allowed" \\
        --actual "Hook blocks all files matching component names" \\
        --patch-content "Add EXCLUDE_PATTERNS check"

    # Log with full details
    python log_refinement.py \\
        --skill error-lifecycle-management \\
        --category trigger \\
        --target triggers \\
        --expected "Should trigger on performance issues" \\
        --actual "Only triggers on explicit errors" \\
        --example "User says 'slow API response'" \\
        --override-type extend \\
        --patch-action append \\
        --patch-content "- performance issue\\n- slow response" \\
        --project vba-lms-app \\
        --generalization high
        """,
    )

    # Required arguments
    parser.add_argument(
        "--skill",
        required=True,
        help="Name of the skill being refined",
    )
    parser.add_argument(
        "--category",
        required=True,
        choices=["trigger", "content", "hook", "tool", "pattern", "config", "new"],
        help="Category of refinement",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Target section or file (e.g., 'hooks/duplicate-check')",
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

    # Optional arguments
    parser.add_argument(
        "--example",
        help="Reproduction example or scenario",
    )
    parser.add_argument(
        "--desired-outcome",
        help="Desired outcome after refinement",
    )
    parser.add_argument(
        "--root-cause",
        help="Root cause analysis",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.8,
        help="Confidence level 0-1 (default: 0.8)",
    )
    parser.add_argument(
        "--override-type",
        choices=["patch", "extend", "config", "full", "hook", "script", "new"],
        default="patch",
        help="Type of override (default: patch)",
    )
    parser.add_argument(
        "--patch-action",
        choices=["append", "prepend", "replace-section", "insert-after", "insert-before", "delete-section"],
        help="Patch action type",
    )
    parser.add_argument(
        "--patch-marker",
        help="Marker text for insert-after, replace-section, etc.",
    )
    parser.add_argument(
        "--patch-content",
        help="Content of the patch",
    )
    parser.add_argument(
        "--project",
        help="Project name",
    )
    parser.add_argument(
        "--project-root",
        help="Project root path",
    )
    parser.add_argument(
        "--generalization",
        choices=["high", "medium", "low"],
        default="medium",
        help="Generalization potential (default: medium)",
    )

    # Output options
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output except errors",
    )

    return parser.parse_args()


def create_refinement(args: argparse.Namespace) -> Refinement:
    """Create a Refinement object from command line arguments."""
    return Refinement(
        id=get_refinement_id(),
        skill=args.skill,
        category=RefinementCategory(args.category),
        override_type=OverrideType(args.override_type),
        target_section=args.target,
        expected_behavior=args.expected,
        actual_behavior=args.actual,
        example=args.example,
        desired_outcome=args.desired_outcome or "",
        root_cause=args.root_cause or "",
        confidence=args.confidence,
        project=args.project or "",
        project_root=args.project_root,
        patch_action=PatchAction(args.patch_action) if args.patch_action else None,
        patch_marker=args.patch_marker,
        patch_content=args.patch_content or "",
        generalization_potential=args.generalization,
        status="applied",
        created=datetime.now(),
        applied=datetime.now(),
    )


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Ensure user refinements directory exists
    ensure_user_refinements_dir()

    # Create refinement
    refinement = create_refinement(args)

    # Save refinement
    persistence = RefinementPersistence(args.project_root)
    success, message = persistence.save_refinement(refinement)

    if args.json:
        result = {
            "success": success,
            "message": message,
            "refinement_id": refinement.id,
            "pattern_id": refinement.pattern_id,
        }
        print(json.dumps(result, indent=2))
    elif not args.quiet:
        if success:
            print(f"✅ {message}")
            print(f"   Refinement ID: {refinement.id}")
            if refinement.pattern_id:
                print(f"   Pattern ID: {refinement.pattern_id}")
        else:
            print(f"❌ {message}", file=sys.stderr)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
