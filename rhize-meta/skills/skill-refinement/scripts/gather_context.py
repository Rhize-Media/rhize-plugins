#!/usr/bin/env python3
"""
Gather context for skill refinement analysis.

Collects context from multiple sources:
- Git: status, diff, recent commits
- File system: skill configs, project structure
- Session: tool calls, errors (via MCP when available)
- Pattern history: similar refinements, matched patterns

Usage:
    python gather_context.py --skill SKILL [--project-root PATH] [--json]

    # As module
    from gather_context import ContextGatherer
    gatherer = ContextGatherer("/path/to/project")
    context = gatherer.gather(target_skill="context-engineering")
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common.models import RefinementContext
from common.persistence import USER_REFINEMENTS_DIR


class ContextGatherer:
    """Gather context from multiple sources for refinement analysis."""

    # Known skills directory locations
    SKILL_LOCATIONS = [
        ".claude/skills",  # Project-local overrides
        "skills",  # Project-shared
        ".claude",  # Legacy location
    ]

    # User-scope skill location
    USER_SKILLS_DIR = Path.home() / "claude-skills"

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize context gatherer.

        Args:
            project_root: Project root path. If None, uses current directory.
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.user_refinements_dir = USER_REFINEMENTS_DIR

    def gather(self, target_skill: Optional[str] = None) -> RefinementContext:
        """
        Gather all context for refinement analysis.

        Args:
            target_skill: Specific skill to focus on, or None for general context.

        Returns:
            RefinementContext with all gathered information.
        """
        # Gather from all sources
        git_status, git_diff = self._get_git_context()
        recent_commits = self._get_recent_commits()

        context = RefinementContext(
            # Session context (stubs for MCP integration)
            recent_tool_calls=self._get_tool_calls(),
            session_duration=self._estimate_session_duration(),
            files_touched=self._get_files_touched(),
            # Error context (stub for Sentry MCP)
            recent_errors=self._get_recent_errors(),
            # Skill context
            target_skill=target_skill,
            current_skill_config=self._load_skill_config(target_skill),
            skill_files=self._list_skill_files(target_skill),
            # Git context
            git_status=git_status,
            recent_commits=recent_commits,
            current_diff=git_diff,
            # Pattern context
            similar_refinements=self._find_similar_refinements(target_skill),
            pattern_matches=self._find_pattern_matches(target_skill),
            # Zen context (stub for Zen MCP)
            zen_memories=self._get_zen_context(),
            cross_project_patterns=self._get_cross_project_patterns(),
            # Project context
            project_root=str(self.project_root),
            project_name=self._get_project_name(),
            # Metadata
            timestamp=datetime.now(),
        )

        return context

    # =========================================================================
    # Git Context
    # =========================================================================

    def _get_git_context(self) -> Tuple[str, str]:
        """Get git status and diff."""
        status = self._run_git_command(["status", "--short"])
        diff = self._run_git_command(["diff", "--stat"])

        # Also get staged diff
        staged_diff = self._run_git_command(["diff", "--cached", "--stat"])
        if staged_diff:
            diff = f"Unstaged:\n{diff}\n\nStaged:\n{staged_diff}"

        return status, diff

    def _get_recent_commits(self, count: int = 10) -> List[str]:
        """Get recent commit messages."""
        output = self._run_git_command([
            "log",
            f"-{count}",
            "--oneline",
            "--no-decorate",
        ])

        if not output:
            return []

        return [line.strip() for line in output.split("\n") if line.strip()]

    def _run_git_command(self, args: List[str]) -> str:
        """Run a git command and return output."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.project_root)] + args,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    # =========================================================================
    # Skill Context
    # =========================================================================

    def _load_skill_config(self, skill: Optional[str]) -> Dict[str, Any]:
        """Load skill configuration from various locations."""
        if not skill:
            return {}

        config = {}

        # Check project-local config
        for location in self.SKILL_LOCATIONS:
            config_path = self.project_root / location / skill / "skill-config.json"
            if config_path.exists():
                try:
                    config["project"] = json.loads(config_path.read_text())
                    config["project_path"] = str(config_path)
                    break
                except json.JSONDecodeError:
                    pass

        # Check user-scope config
        user_config_path = self.USER_SKILLS_DIR / skill / "skill-config.json"
        if user_config_path.exists():
            try:
                config["user"] = json.loads(user_config_path.read_text())
                config["user_path"] = str(user_config_path)
            except json.JSONDecodeError:
                pass

        return config

    def _list_skill_files(self, skill: Optional[str]) -> List[str]:
        """List all files for a skill (project overrides + user-scope)."""
        if not skill:
            return []

        files = []

        # Check project-local files
        for location in self.SKILL_LOCATIONS:
            skill_dir = self.project_root / location / skill
            if skill_dir.exists():
                for f in skill_dir.rglob("*"):
                    if f.is_file():
                        files.append(str(f))

        # Check user-scope files
        user_skill_dir = self.USER_SKILLS_DIR / skill
        if user_skill_dir.exists():
            for f in user_skill_dir.rglob("*"):
                if f.is_file():
                    files.append(str(f))

        return files

    def _get_available_skills(self) -> List[str]:
        """Get list of available skills."""
        skills = set()

        # Check project-local
        for location in self.SKILL_LOCATIONS:
            skills_dir = self.project_root / location
            if skills_dir.exists():
                for item in skills_dir.iterdir():
                    if item.is_dir() and (item / "SKILL.md").exists():
                        skills.add(item.name)

        # Check user-scope
        if self.USER_SKILLS_DIR.exists():
            for item in self.USER_SKILLS_DIR.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    skills.add(item.name)

        return sorted(skills)

    # =========================================================================
    # Session Context (MCP Integration Points)
    # =========================================================================

    def _get_tool_calls(self) -> List[Dict[str, Any]]:
        """
        Get recent tool calls from session.

        Note: This is a stub for MCP integration. When Desktop Commander
        MCP is available, this should call get_recent_tool_calls.
        """
        # Stub - returns empty list without MCP
        # TODO: Integrate with Desktop Commander MCP
        return []

    def _estimate_session_duration(self) -> Optional[float]:
        """
        Estimate session duration.

        Note: This is a stub. Actual implementation would track
        session start time or query from MCP.
        """
        # Stub - returns None without session tracking
        return None

    def _get_files_touched(self) -> List[str]:
        """
        Get files touched in current session.

        Falls back to git status if MCP not available.
        """
        # Try to get from git status as fallback
        status = self._run_git_command(["status", "--porcelain"])
        if not status:
            return []

        files = []
        for line in status.split("\n"):
            if line.strip():
                # Format is "XY filename" or "XY old -> new" for renames
                parts = line[3:].split(" -> ")
                files.append(parts[-1].strip())

        return files

    def _get_recent_errors(self) -> List[Dict[str, Any]]:
        """
        Get recent errors from Sentry.

        Note: This is a stub for Sentry MCP integration.
        """
        # Stub - returns empty list without Sentry MCP
        # TODO: Integrate with Sentry MCP
        return []

    # =========================================================================
    # Pattern Context
    # =========================================================================

    def _find_similar_refinements(self, skill: Optional[str]) -> List[Dict[str, Any]]:
        """Find similar past refinements from history."""
        if not skill:
            return []

        similar = []
        history_dir = self.user_refinements_dir / "refinement-history"

        if not history_dir.exists():
            return []

        # Search for refinements matching this skill
        for file_path in history_dir.glob("*.md"):
            try:
                content = file_path.read_text()
                if f"**Skill:** {skill}" in content:
                    # Extract key info
                    ref_id_match = re.search(r"# Refinement: (REF-[\d-]+)", content)
                    category_match = re.search(r"\*\*Category:\*\* (\w+)", content)
                    target_match = re.search(r"\*\*Target:\*\* (.+)", content)

                    similar.append({
                        "id": ref_id_match.group(1) if ref_id_match else "unknown",
                        "file": str(file_path),
                        "category": category_match.group(1) if category_match else "unknown",
                        "target": target_match.group(1).strip() if target_match else "unknown",
                    })
            except Exception:
                continue

        return similar[:10]  # Limit to 10 most recent

    def _find_pattern_matches(self, skill: Optional[str]) -> List[str]:
        """Find patterns that match this skill."""
        if not skill:
            return []

        patterns_file = self.user_refinements_dir / "aggregated-patterns.md"
        if not patterns_file.exists():
            return []

        matches = []
        try:
            content = patterns_file.read_text()

            # Find patterns mentioning this skill
            pattern_blocks = re.findall(
                r"### [⚪🟡✅⛔] (PATTERN-\d+): (.+?)\n(.+?)(?=### [⚪🟡✅⛔] PATTERN-|\Z)",
                content,
                re.DOTALL,
            )

            for pattern_id, name, block in pattern_blocks:
                if skill in block:
                    matches.append(f"{pattern_id}: {name.strip()}")

        except Exception:
            pass

        return matches

    # =========================================================================
    # Zen MCP Context (Stubs)
    # =========================================================================

    def _get_zen_context(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get saved context from Zen MCP.

        Note: This is a stub for Zen MCP integration.
        """
        # Stub - returns None without Zen MCP
        # TODO: Integrate with Zen MCP
        return None

    def _get_cross_project_patterns(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get patterns from other projects via Zen MCP.

        Note: This is a stub for Zen MCP integration.
        """
        # Stub - returns None without Zen MCP
        # TODO: Integrate with Zen MCP
        return None

    # =========================================================================
    # Project Context
    # =========================================================================

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

        # Try pyproject.toml
        pyproject = self.project_root / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                match = re.search(r'name\s*=\s*"([^"]+)"', content)
                if match:
                    return match.group(1)
            except Exception:
                pass

        # Fall back to directory name
        return self.project_root.name

    # =========================================================================
    # Output Methods
    # =========================================================================

    def to_summary(self, context: RefinementContext) -> str:
        """Format context as human-readable summary."""
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📋 Context Gathered",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"🎯 Target Skill: {context.target_skill or 'not specified'}",
            f"📁 Project: {context.project_name}",
            f"📍 Root: {context.project_root}",
            "",
        ]

        # Git context
        if context.git_status:
            changed_count = len([l for l in context.git_status.split("\n") if l.strip()])
            lines.append(f"📊 Git Status: {changed_count} changed files")
        else:
            lines.append("📊 Git Status: clean or not a git repo")

        if context.recent_commits:
            lines.append(f"📝 Recent Commits: {len(context.recent_commits)}")

        # Files touched
        if context.files_touched:
            lines.append(f"📄 Files Touched: {len(context.files_touched)}")

        # Skill context
        if context.skill_files:
            lines.append(f"🔧 Skill Files: {len(context.skill_files)}")

        # Pattern context
        if context.similar_refinements:
            lines.append(f"🔍 Similar Refinements: {len(context.similar_refinements)}")

        if context.pattern_matches:
            lines.append(f"🎯 Pattern Matches: {', '.join(context.pattern_matches)}")

        # MCP status
        lines.append("")
        lines.append("🔌 MCP Status:")
        lines.append(f"   Desktop Commander: {'connected' if context.recent_tool_calls else 'not available'}")
        lines.append(f"   Sentry: {'connected' if context.recent_errors else 'not available'}")
        lines.append(f"   Zen: {'connected' if context.zen_memories is not None else 'not available'}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Gather context for skill refinement analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--skill",
        help="Target skill to gather context for",
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
    parser.add_argument(
        "--list-skills",
        action="store_true",
        help="List available skills and exit",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    gatherer = ContextGatherer(args.project_root)

    # List skills mode
    if args.list_skills:
        skills = gatherer._get_available_skills()
        if args.json:
            print(json.dumps({"skills": skills}, indent=2))
        else:
            print("Available skills:")
            for skill in skills:
                print(f"  - {skill}")
        return 0

    # Gather context
    context = gatherer.gather(target_skill=args.skill)

    # Output
    if args.json:
        print(json.dumps(context.to_dict(), indent=2, default=str))
    else:
        print(gatherer.to_summary(context))

    return 0


if __name__ == "__main__":
    sys.exit(main())
