#!/usr/bin/env python3
"""
Generate patch/override files based on gap analysis.

Supports:
- Section-level patches with actions (append, replace, insert, delete)
- Full file overrides
- Config-only overrides
- Hook and script overrides
- Extension files

Usage:
    python generate_patch.py --skill SKILL --section SECTION \
        --action append --content "new content" [--json]

    # From analysis file
    python generate_patch.py --analysis-file analysis.json

    # As module
    from generate_patch import PatchGenerator
    generator = PatchGenerator(project_root="/path/to/project")
    patch = generator.generate(analysis)
"""

import argparse
import json
import os
import sys
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
)
from common.persistence import get_refinement_id


class PatchGenerator:
    """Generate skill patches and overrides."""

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize patch generator.

        Args:
            project_root: Project root path. If None, uses current directory.
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()

    def generate(
        self,
        analysis: GapAnalysis,
        user_modifications: Optional[str] = None,
    ) -> GeneratedPatch:
        """
        Generate patch based on analysis.

        Args:
            analysis: Gap analysis results
            user_modifications: Optional user edits to the patch content

        Returns:
            GeneratedPatch with files, preview, and metadata
        """
        # Use user modifications if provided
        content = user_modifications or analysis.patch_content

        # Generate based on override type
        if analysis.override_type == OverrideType.SECTION_PATCH:
            return self._generate_section_patch(analysis, content)
        elif analysis.override_type == OverrideType.EXTENSION:
            return self._generate_extension(analysis, content)
        elif analysis.override_type == OverrideType.CONFIG_OVERRIDE:
            return self._generate_config_override(analysis, content)
        elif analysis.override_type == OverrideType.HOOK_OVERRIDE:
            return self._generate_hook_override(analysis, content)
        elif analysis.override_type == OverrideType.SCRIPT_OVERRIDE:
            return self._generate_script_override(analysis, content)
        else:
            return self._generate_full_override(analysis, content)

    def _generate_section_patch(
        self,
        analysis: GapAnalysis,
        content: str,
    ) -> GeneratedPatch:
        """Generate SKILL.patch.md with section-level changes."""
        refinement_id = get_refinement_id()
        timestamp = datetime.now().isoformat()

        # Build patch action comment
        action = analysis.patch_action or PatchAction.APPEND
        if analysis.patch_marker:
            action_comment = f'<!-- ACTION: {action.value} "{analysis.patch_marker}" -->'
        else:
            action_comment = f"<!-- ACTION: {action.value} -->"

        # Build patch content
        patch_content = f"""# SKILL.patch.md
# Patches for: {analysis.target_skill}
# Generated: {timestamp}
# Refinement: {refinement_id}

## PATCH: {analysis.target_section}
{action_comment}
{content}
"""

        # File path
        file_path = f".claude/skills/{analysis.target_skill}/SKILL.patch.md"

        # Generate preview
        preview = self._generate_diff_preview(
            file_path,
            content,
            action,
            analysis.patch_marker,
        )

        return GeneratedPatch(
            files={file_path: patch_content},
            preview=preview,
            description=f"Section patch for {analysis.target_section}",
            override_type=OverrideType.SECTION_PATCH,
            target_skill=analysis.target_skill,
            target_section=analysis.target_section,
        )

    def _generate_extension(
        self,
        analysis: GapAnalysis,
        content: str,
    ) -> GeneratedPatch:
        """Generate SKILL.extend.md with additive changes."""
        refinement_id = get_refinement_id()
        timestamp = datetime.now().isoformat()

        # Build extension content
        extension_content = f"""# SKILL.extend.md
# Extensions for: {analysis.target_skill}
# Generated: {timestamp}
# Refinement: {refinement_id}

## EXTEND: {analysis.target_section}
<!-- ACTION: append -->
{content}
"""

        file_path = f".claude/skills/{analysis.target_skill}/SKILL.extend.md"

        preview = self._generate_diff_preview(
            file_path,
            content,
            PatchAction.APPEND,
            None,
            is_extension=True,
        )

        return GeneratedPatch(
            files={file_path: extension_content},
            preview=preview,
            description=f"Extension for {analysis.target_section}",
            override_type=OverrideType.EXTENSION,
            target_skill=analysis.target_skill,
            target_section=analysis.target_section,
        )

    def _generate_config_override(
        self,
        analysis: GapAnalysis,
        content: str,
    ) -> GeneratedPatch:
        """Generate skill-config.json with config overrides."""
        # Parse content as JSON if possible, otherwise wrap in config
        try:
            config_data = json.loads(content)
        except json.JSONDecodeError:
            # Treat as key=value pairs
            config_data = {}
            for line in content.strip().split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    config_data[key.strip()] = value.strip()
                elif ":" in line:
                    key, value = line.split(":", 1)
                    config_data[key.strip()] = value.strip()

        # Build full config structure
        config_content = {
            "skill": analysis.target_skill,
            "version": "1.0.0",
            "generated": datetime.now().isoformat(),
            "config": config_data,
        }

        file_path = f".claude/skills/{analysis.target_skill}/skill-config.json"
        json_content = json.dumps(config_content, indent=2)

        preview = self._generate_config_preview(config_data)

        return GeneratedPatch(
            files={file_path: json_content},
            preview=preview,
            description=f"Config override for {analysis.target_skill}",
            override_type=OverrideType.CONFIG_OVERRIDE,
            target_skill=analysis.target_skill,
            target_section="config",
        )

    def _generate_hook_override(
        self,
        analysis: GapAnalysis,
        content: str,
    ) -> GeneratedPatch:
        """Generate hook override script."""
        # Extract hook name from target section
        hook_name = analysis.target_section.split("/")[-1]
        if not hook_name.endswith(".sh"):
            hook_name += ".sh"

        # Build hook content with header
        hook_content = f"""#!/bin/bash
# {hook_name} (Project Override)
# Generated: {datetime.now().isoformat()}
# Refinement: {get_refinement_id()}
# Overrides: {analysis.target_skill}/{analysis.target_section}

{content}
"""

        file_path = f".claude/skills/{analysis.target_skill}/hooks/{hook_name}"

        preview = self._generate_script_preview(hook_name, content, "bash")

        return GeneratedPatch(
            files={file_path: hook_content},
            preview=preview,
            description=f"Hook override: {hook_name}",
            override_type=OverrideType.HOOK_OVERRIDE,
            target_skill=analysis.target_skill,
            target_section=analysis.target_section,
        )

    def _generate_script_override(
        self,
        analysis: GapAnalysis,
        content: str,
    ) -> GeneratedPatch:
        """Generate script override."""
        # Extract script name from target section
        script_name = analysis.target_section.split("/")[-1]
        if not script_name.endswith(".py"):
            script_name += ".py"

        # Build script content with header
        script_content = f'''#!/usr/bin/env python3
"""
{script_name} (Project Override)
Generated: {datetime.now().isoformat()}
Refinement: {get_refinement_id()}
Overrides: {analysis.target_skill}/{analysis.target_section}
"""

{content}
'''

        file_path = f".claude/skills/{analysis.target_skill}/scripts/{script_name}"

        preview = self._generate_script_preview(script_name, content, "python")

        return GeneratedPatch(
            files={file_path: script_content},
            preview=preview,
            description=f"Script override: {script_name}",
            override_type=OverrideType.SCRIPT_OVERRIDE,
            target_skill=analysis.target_skill,
            target_section=analysis.target_section,
        )

    def _generate_full_override(
        self,
        analysis: GapAnalysis,
        content: str,
    ) -> GeneratedPatch:
        """Generate full SKILL.md override."""
        # Build full skill content
        skill_content = f"""# {analysis.target_skill.replace('-', ' ').title()} (Project Override)

> Generated: {datetime.now().isoformat()}
> Refinement: {get_refinement_id()}
> This is a full override - base skill is completely replaced.

{content}
"""

        file_path = f".claude/skills/{analysis.target_skill}/SKILL.md"

        preview = f"""┌─ {file_path} ─────────────────────────────────
│ ⚠️ FULL OVERRIDE - Replaces entire base skill
│
│ {content[:200]}{'...' if len(content) > 200 else ''}
└───────────────────────────────────────────────────"""

        return GeneratedPatch(
            files={file_path: skill_content},
            preview=preview,
            description=f"Full override for {analysis.target_skill}",
            override_type=OverrideType.FULL_OVERRIDE,
            target_skill=analysis.target_skill,
            target_section="entire-skill",
        )

    def _generate_diff_preview(
        self,
        file_path: str,
        content: str,
        action: PatchAction,
        marker: Optional[str],
        is_extension: bool = False,
    ) -> str:
        """Generate a diff-style preview of changes."""
        lines = [f"┌─ {file_path} ─────────────────────────────────"]

        # Action description
        if is_extension:
            lines.append("│ 📝 Extension (additive)")
        else:
            action_desc = {
                PatchAction.APPEND: "➕ Append to end of section",
                PatchAction.PREPEND: "➕ Prepend to start of section",
                PatchAction.REPLACE_SECTION: f"🔄 Replace section: {marker}",
                PatchAction.INSERT_AFTER: f"➕ Insert after: {marker}",
                PatchAction.INSERT_BEFORE: f"➕ Insert before: {marker}",
                PatchAction.DELETE_SECTION: f"➖ Delete section: {marker}",
            }
            lines.append(f"│ {action_desc.get(action, '📝 Modify')}")

        lines.append("│")

        # Content preview with + prefix for additions
        for line in content.split("\n")[:15]:  # Limit preview
            if action == PatchAction.DELETE_SECTION:
                lines.append(f"│ - {line}")
            else:
                lines.append(f"│ + {line}")

        if content.count("\n") > 15:
            lines.append(f"│ ... ({content.count(chr(10)) - 15} more lines)")

        lines.append("└───────────────────────────────────────────────────")

        return "\n".join(lines)

    def _generate_config_preview(self, config: Dict[str, Any]) -> str:
        """Generate preview for config changes."""
        lines = ["┌─ skill-config.json ─────────────────────────────────"]
        lines.append("│ 📝 Configuration Override")
        lines.append("│")

        for key, value in config.items():
            lines.append(f"│ + {key}: {json.dumps(value)}")

        lines.append("└───────────────────────────────────────────────────")

        return "\n".join(lines)

    def _generate_script_preview(
        self,
        filename: str,
        content: str,
        language: str,
    ) -> str:
        """Generate preview for script overrides."""
        lines = [f"┌─ {filename} ─────────────────────────────────"]
        lines.append(f"│ 📜 {language.title()} Script Override")
        lines.append("│")

        # Show first 10 lines
        for line in content.split("\n")[:10]:
            lines.append(f"│ {line}")

        if content.count("\n") > 10:
            lines.append(f"│ ... ({content.count(chr(10)) - 10} more lines)")

        lines.append("└───────────────────────────────────────────────────")

        return "\n".join(lines)

    def write_files(
        self,
        patch: GeneratedPatch,
        dry_run: bool = False,
    ) -> List[str]:
        """
        Write patch files to disk.

        Args:
            patch: Generated patch to write
            dry_run: If True, don't actually write files

        Returns:
            List of written file paths
        """
        written = []

        for rel_path, content in patch.files.items():
            full_path = self.project_root / rel_path

            if dry_run:
                written.append(f"[DRY RUN] {full_path}")
                continue

            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if file exists and should be merged
            if full_path.exists() and rel_path.endswith(".patch.md"):
                # Merge patches
                existing = full_path.read_text()
                content = self._merge_patches(existing, content)

            # Write file
            full_path.write_text(content)

            # Make scripts executable
            if rel_path.endswith(".sh"):
                os.chmod(full_path, 0o755)

            written.append(str(full_path))

        return written

    def _merge_patches(self, existing: str, new: str) -> str:
        """Merge new patch into existing patch file."""
        # Extract header from new patch
        new_lines = new.split("\n")
        new_patches = []
        current_patch = []
        in_patch = False

        for line in new_lines:
            if line.startswith("## PATCH:"):
                if current_patch:
                    new_patches.append("\n".join(current_patch))
                current_patch = [line]
                in_patch = True
            elif in_patch:
                current_patch.append(line)

        if current_patch:
            new_patches.append("\n".join(current_patch))

        # Append new patches to existing
        combined = existing.rstrip()
        for patch in new_patches:
            combined += f"\n\n{patch}"

        return combined


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate patch/override files",
    )

    # Either analysis file or manual specification
    parser.add_argument(
        "--analysis-file",
        help="Path to analysis JSON from analyze_gap.py",
    )

    # Manual specification
    parser.add_argument(
        "--skill",
        help="Target skill name",
    )
    parser.add_argument(
        "--section",
        help="Target section",
    )
    parser.add_argument(
        "--override-type",
        choices=["patch", "extend", "config", "full", "hook", "script"],
        default="patch",
        help="Override type",
    )
    parser.add_argument(
        "--action",
        choices=["append", "prepend", "replace-section", "insert-after", "insert-before", "delete-section"],
        default="append",
        help="Patch action",
    )
    parser.add_argument(
        "--marker",
        help="Marker text for positioned actions",
    )
    parser.add_argument(
        "--content",
        help="Patch content (or use --content-file)",
    )
    parser.add_argument(
        "--content-file",
        help="File containing patch content",
    )

    # Options
    parser.add_argument(
        "--project-root",
        help="Project root path",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write files to disk",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without writing",
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

    # Load analysis or build from args
    if args.analysis_file:
        with open(args.analysis_file) as f:
            analysis_data = json.load(f)
        analysis = GapAnalysis(
            root_cause=analysis_data.get("root_cause", ""),
            override_type=OverrideType(analysis_data["override_type"]),
            target_section=analysis_data["target_section"],
            target_skill=analysis_data["target_skill"],
            confidence=analysis_data.get("confidence", 0.8),
            needs_guided_mode=analysis_data.get("needs_guided_mode", False),
            patch_action=PatchAction(analysis_data["patch_action"]) if analysis_data.get("patch_action") else None,
            patch_marker=analysis_data.get("patch_marker"),
            patch_content=analysis_data.get("patch_content", ""),
        )
    else:
        # Validate required args
        if not args.skill or not args.section:
            print("Error: --skill and --section required when not using --analysis-file")
            return 1

        # Get content
        if args.content_file:
            content = Path(args.content_file).read_text()
        elif args.content:
            content = args.content
        else:
            print("Error: --content or --content-file required")
            return 1

        analysis = GapAnalysis(
            root_cause="Manual patch generation",
            override_type=OverrideType(args.override_type),
            target_section=args.section,
            target_skill=args.skill,
            confidence=1.0,
            needs_guided_mode=False,
            patch_action=PatchAction(args.action) if args.action else None,
            patch_marker=args.marker,
            patch_content=content,
        )

    # Generate patch
    generator = PatchGenerator(args.project_root)
    patch = generator.generate(analysis)

    # Output
    if args.json:
        print(json.dumps(patch.to_dict(), indent=2))
    else:
        print(_format_patch(patch))

    # Write if requested
    if args.write or args.dry_run:
        written = generator.write_files(patch, dry_run=args.dry_run)
        print("\n📁 Files:")
        for f in written:
            print(f"   {'✓' if not args.dry_run else '○'} {f}")

    return 0


def _format_patch(patch: GeneratedPatch) -> str:
    """Format patch as human-readable output."""
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📄 Generated Patch",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🎯 Skill: {patch.target_skill}",
        f"📍 Section: {patch.target_section}",
        f"📊 Type: {patch.override_type.value}",
        f"📝 Description: {patch.description}",
        "",
        "📄 Preview:",
        patch.preview,
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
