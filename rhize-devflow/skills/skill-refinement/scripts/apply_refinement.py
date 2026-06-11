#!/usr/bin/env python3
"""
Apply refinements to project and user scope.

Orchestrates the full refinement application workflow:
1. Write patch/override files to project scope
2. Log to user scope tracking
3. Update pattern aggregation
4. Trigger generalization if threshold met

Usage:
    python apply_refinement.py \
        --skill context-engineering \
        --category hook \
        --target hooks/duplicate-check \
        --expected "Test fixtures should be allowed" \
        --actual "Hook blocks all files" \
        --patch-action insert-after \
        --patch-marker "Only check paths" \
        --patch-content "# Exclude tests..."

    # From analysis JSON
    python apply_refinement.py --from-analysis analysis.json

    # Dry run (preview only)
    python apply_refinement.py --skill ... --dry-run
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common.models import (
    GapAnalysis,
    GeneratedPatch,
    OverrideType,
    PatchAction,
    Pattern,
    Refinement,
    RefinementCategory,
    RefinementContext,
)
from common.persistence import (
    RefinementPersistence,
    USER_REFINEMENTS_DIR,
    ensure_user_refinements_dir,
    get_refinement_id,
)

from aggregate_patterns import PatternAggregator
from analyze_gap import GapAnalyzer
from gather_context import ContextGatherer
from generate_patch import PatchGenerator


class RefinementApplicator:
    """Orchestrates full refinement application workflow."""

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize refinement applicator.

        Args:
            project_root: Project root path. If None, uses current directory.
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.persistence = RefinementPersistence()
        self.aggregator = PatternAggregator()
        self.context_gatherer = ContextGatherer(str(self.project_root))
        self.analyzer = GapAnalyzer(str(self.project_root))
        self.patch_generator = PatchGenerator(str(self.project_root))

    def apply_from_user_input(
        self,
        skill: str,
        category: str,
        target: str,
        expected: str,
        actual: str,
        example: Optional[str] = None,
        patch_action: Optional[str] = None,
        patch_marker: Optional[str] = None,
        patch_content: Optional[str] = None,
        override_type: Optional[str] = None,
        project_name: Optional[str] = None,
        generalization: str = "medium",
        skip_user_scope: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Apply a refinement from user-provided parameters.

        Args:
            skill: Target skill name
            category: Refinement category
            target: Target section path
            expected: Expected behavior
            actual: Actual behavior
            example: Reproduction example
            patch_action: Patch action (append, prepend, etc.)
            patch_marker: Marker text for positioned actions
            patch_content: Content to insert
            override_type: Override type (patch, extend, etc.)
            project_name: Project name for tracking
            generalization: Generalization potential (high/medium/low)
            skip_user_scope: Skip user-scope logging
            dry_run: Preview only, don't write files

        Returns:
            Dictionary with results including refinement ID, files created, pattern info
        """
        result = {
            "success": False,
            "refinement_id": None,
            "files_created": [],
            "pattern": None,
            "generalization_triggered": False,
            "errors": [],
        }

        try:
            # Step 1: Gather context
            context = self.context_gatherer.gather(target_skill=skill)

            # Step 2: Analyze gap
            user_input = {
                "expected": expected,
                "actual": actual,
                "example": example,
                "category": category,
                "target": target,
            }
            analysis = self.analyzer.analyze(context, user_input)

            # Override analysis values if explicitly provided
            if override_type:
                analysis.override_type = OverrideType(override_type)
            if patch_action:
                analysis.patch_action = PatchAction(patch_action)
            if patch_marker:
                analysis.patch_marker = patch_marker
            if patch_content:
                analysis.patch_content = patch_content

            # Step 3: Generate patch
            patch = self.patch_generator.generate(analysis)

            if dry_run:
                result["success"] = True
                result["preview"] = patch.preview
                result["files_to_create"] = list(patch.files.keys())
                result["analysis"] = {
                    "override_type": analysis.override_type.value,
                    "confidence": analysis.confidence,
                    "generalization": analysis.generalization_potential,
                }
                return result

            # Step 4: Write patch files
            files_written = self.patch_generator.write_files(patch, dry_run=False)
            result["files_created"] = files_written

            # Step 5: Create refinement record
            refinement_id = get_refinement_id()
            refinement = Refinement(
                id=refinement_id,
                skill=skill,
                category=RefinementCategory(category),
                override_type=analysis.override_type,
                target_section=target,
                expected_behavior=expected,
                actual_behavior=actual,
                example=example,
                root_cause=analysis.root_cause,
                confidence=analysis.confidence,
                project=project_name or self._get_project_name(),
                project_root=str(self.project_root),
                patch_action=analysis.patch_action,
                patch_marker=analysis.patch_marker,
                patch_content=analysis.patch_content or "",
                generalization_potential=generalization,
                status="applied",
                created=datetime.now(),
                applied=datetime.now(),
            )
            result["refinement_id"] = refinement_id

            # Step 6: Log to user scope (unless skipped)
            if not skip_user_scope:
                self.persistence.save_refinement(refinement)

                # Step 7: Update pattern aggregation
                pattern = self.aggregator.process_new_refinement(refinement)
                if pattern:
                    result["pattern"] = {
                        "id": pattern.id,
                        "name": pattern.name,
                        "count": pattern.count,
                        "status": pattern.status.value,
                    }
                    if pattern.count >= 2:
                        result["generalization_triggered"] = True

            result["success"] = True

        except Exception as e:
            result["errors"].append(str(e))

        return result

    def apply_from_analysis(
        self,
        analysis_file: str,
        dry_run: bool = False,
        skip_user_scope: bool = False,
    ) -> Dict[str, Any]:
        """
        Apply a refinement from a saved analysis JSON file.

        Args:
            analysis_file: Path to analysis JSON file
            dry_run: Preview only
            skip_user_scope: Skip user-scope logging

        Returns:
            Results dictionary
        """
        try:
            with open(analysis_file) as f:
                data = json.load(f)

            return self.apply_from_user_input(
                skill=data.get("target_skill", data.get("skill")),
                category=data.get("category", "content"),
                target=data.get("target_section", data.get("target", "")),
                expected=data.get("expected", ""),
                actual=data.get("actual", ""),
                example=data.get("example"),
                patch_action=data.get("patch_action"),
                patch_marker=data.get("patch_marker"),
                patch_content=data.get("patch_content"),
                override_type=data.get("override_type"),
                project_name=data.get("project"),
                generalization=data.get("generalization_potential", "medium"),
                skip_user_scope=skip_user_scope,
                dry_run=dry_run,
            )
        except Exception as e:
            return {
                "success": False,
                "errors": [f"Failed to load analysis file: {e}"],
            }

    def _get_project_name(self) -> str:
        """Get project name from directory or package.json."""
        # Try package.json
        package_json = self.project_root / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                if "name" in data:
                    return data["name"]
            except json.JSONDecodeError:
                pass

        # Fall back to directory name
        return self.project_root.name

    # =========================================================================
    # Output Methods
    # =========================================================================

    def format_result(self, result: Dict[str, Any]) -> str:
        """Format result as human-readable output."""
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if result.get("success"):
            if result.get("preview"):
                # Dry run result
                lines.append("🔍 Refinement Preview (Dry Run)")
                lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                lines.append("")
                lines.append(result["preview"])
                lines.append("")
                lines.append("📁 Files to create:")
                for f in result.get("files_to_create", []):
                    lines.append(f"   • {f}")
                lines.append("")
                lines.append("[DRY RUN - use without --dry-run to apply]")
            else:
                # Applied result
                lines.append(f"✅ Refinement Applied: {result.get('refinement_id', 'unknown')}")
                lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                lines.append("")

                # Files created
                lines.append("📁 Created:")
                for f in result.get("files_created", []):
                    lines.append(f"   {f}")
                lines.append("")

                # Pattern info
                pattern = result.get("pattern")
                if pattern:
                    lines.append("🔮 Pattern Tracking:")
                    lines.append(f"   Pattern: {pattern['id']} ({pattern['name']})")
                    lines.append(f"   Count: {pattern['count']}")
                    lines.append(f"   Status: {pattern['status']}")
                    if result.get("generalization_triggered"):
                        lines.append("   ⚡ Auto-generalization triggered!")
                    lines.append("")

                # Next steps
                lines.append("💡 Next Steps:")
                lines.append("   1. Test the refinement")
                lines.append("   2. Run /done to validate before committing")
        else:
            lines.append("❌ Refinement Failed")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("")
            for error in result.get("errors", ["Unknown error"]):
                lines.append(f"   Error: {error}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Apply refinements to project and user scope",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required arguments (unless using --from-analysis)
    parser.add_argument(
        "--skill",
        help="Target skill name",
    )
    parser.add_argument(
        "--category",
        choices=["trigger", "content", "hook", "tool", "pattern", "config", "new"],
        help="Refinement category",
    )
    parser.add_argument(
        "--target",
        help="Target section path (e.g., hooks/duplicate-check)",
    )
    parser.add_argument(
        "--expected",
        help="Expected behavior",
    )
    parser.add_argument(
        "--actual",
        help="Actual behavior",
    )

    # Optional arguments
    parser.add_argument(
        "--example",
        help="Reproduction example",
    )
    parser.add_argument(
        "--patch-action",
        choices=["append", "prepend", "replace-section", "insert-after", "insert-before", "delete-section"],
        help="Patch action",
    )
    parser.add_argument(
        "--patch-marker",
        help="Marker text for positioned actions",
    )
    parser.add_argument(
        "--patch-content",
        help="Content to insert",
    )
    parser.add_argument(
        "--override-type",
        choices=["patch", "extend", "config", "full", "hook", "script", "new"],
        help="Override type",
    )
    parser.add_argument(
        "--project",
        help="Project name for tracking",
    )
    parser.add_argument(
        "--generalization",
        choices=["high", "medium", "low"],
        default="medium",
        help="Generalization potential",
    )

    # Alternative input
    parser.add_argument(
        "--from-analysis",
        metavar="FILE",
        help="Load from analysis JSON file",
    )

    # Control flags
    parser.add_argument(
        "--skip-user-scope",
        action="store_true",
        help="Skip user-scope logging (project only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't write files",
    )
    parser.add_argument(
        "--project-root",
        help="Project root path (default: current directory)",
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

    applicator = RefinementApplicator(args.project_root)

    # Apply from analysis file
    if args.from_analysis:
        result = applicator.apply_from_analysis(
            args.from_analysis,
            dry_run=args.dry_run,
            skip_user_scope=args.skip_user_scope,
        )
    else:
        # Validate required arguments
        if not all([args.skill, args.category, args.target, args.expected, args.actual]):
            print("Error: --skill, --category, --target, --expected, and --actual are required")
            print("Or use --from-analysis to load from a file")
            return 1

        result = applicator.apply_from_user_input(
            skill=args.skill,
            category=args.category,
            target=args.target,
            expected=args.expected,
            actual=args.actual,
            example=args.example,
            patch_action=args.patch_action,
            patch_marker=args.patch_marker,
            patch_content=args.patch_content,
            override_type=args.override_type,
            project_name=args.project,
            generalization=args.generalization,
            skip_user_scope=args.skip_user_scope,
            dry_run=args.dry_run,
        )

    # Output
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(applicator.format_result(result))

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
