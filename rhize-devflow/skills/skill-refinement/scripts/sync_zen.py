#!/usr/bin/env python3
"""
Synchronize refinement data with Zen MCP server.

Provides dual persistence:
- Primary: File-based storage (always works)
- Secondary: Zen MCP (when available)

Features:
- Cross-project pattern queries
- Session context persistence
- Conflict resolution (file-based wins)

Usage:
    # Sync local files to Zen MCP
    python sync_zen.py --push

    # Pull patterns from Zen MCP
    python sync_zen.py --pull

    # Check sync status
    python sync_zen.py --status

    # Query cross-project patterns
    python sync_zen.py --query "test directory exclusion"
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

from common.models import Pattern, PatternStatus, Refinement
from common.persistence import (
    RefinementPersistence,
    USER_REFINEMENTS_DIR,
    ensure_user_refinements_dir,
)


# Zen MCP context key for refinements
ZEN_CONTEXT_KEY = "skill_refinements"


class ZenSyncManager:
    """Manage synchronization with Zen MCP server."""

    def __init__(self, refinements_dir: Optional[Path] = None):
        """
        Initialize Zen sync manager.

        Args:
            refinements_dir: User refinements directory.
        """
        self.refinements_dir = refinements_dir or USER_REFINEMENTS_DIR
        ensure_user_refinements_dir()
        self.persistence = RefinementPersistence(self.refinements_dir)
        self.sync_file = self.refinements_dir / ".zen-sync"
        self._zen_available = None

    def is_zen_available(self) -> bool:
        """
        Check if Zen MCP server is available.

        Note: This is a stub. In production, this would actually
        check if the Zen MCP server is connected.
        """
        if self._zen_available is not None:
            return self._zen_available

        # Stub: Check for Zen MCP availability
        # In a real implementation, this would:
        # 1. Try to connect to Zen MCP
        # 2. Check for authentication
        # 3. Verify server is responding
        self._zen_available = False  # Default to unavailable
        return self._zen_available

    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get current sync status.

        Returns:
            Dictionary with sync status information.
        """
        status = {
            "zen_available": self.is_zen_available(),
            "last_sync": None,
            "local_refinements": 0,
            "local_patterns": 0,
            "remote_patterns": 0,
            "pending_push": 0,
            "pending_pull": 0,
        }

        # Read sync timestamp
        if self.sync_file.exists():
            try:
                data = json.loads(self.sync_file.read_text())
                status["last_sync"] = data.get("last_sync")
            except json.JSONDecodeError:
                pass

        # Count local items
        refinements = self.persistence.load_refinements()
        patterns = self.persistence.load_patterns()
        status["local_refinements"] = len(refinements)
        status["local_patterns"] = len(patterns)

        # Count remote items (if available)
        if self.is_zen_available():
            remote_data = self._get_remote_context()
            if remote_data:
                status["remote_patterns"] = len(remote_data.get("patterns", {}))
                # Calculate pending sync
                status["pending_push"] = self._count_pending_push(patterns, remote_data)
                status["pending_pull"] = self._count_pending_pull(patterns, remote_data)

        return status

    def push_to_zen(self, force: bool = False) -> Dict[str, Any]:
        """
        Push local data to Zen MCP.

        Args:
            force: Force overwrite remote data.

        Returns:
            Result dictionary with sync outcome.
        """
        result = {
            "success": False,
            "pushed_refinements": 0,
            "pushed_patterns": 0,
            "errors": [],
        }

        if not self.is_zen_available():
            result["errors"].append("Zen MCP is not available")
            return result

        try:
            # Load local data
            refinements = self.persistence.load_refinements()
            patterns = self.persistence.load_patterns()

            # Convert to Zen format
            zen_context = self._to_zen_format(refinements, patterns)

            # Push to Zen (stub)
            success = self._save_to_zen(zen_context, force)

            if success:
                result["success"] = True
                result["pushed_refinements"] = len(refinements)
                result["pushed_patterns"] = len(patterns)
                self._update_sync_timestamp("push")
            else:
                result["errors"].append("Failed to save to Zen MCP")

        except Exception as e:
            result["errors"].append(str(e))

        return result

    def pull_from_zen(self, merge: bool = True) -> Dict[str, Any]:
        """
        Pull data from Zen MCP.

        Args:
            merge: Merge with local data (vs replace).

        Returns:
            Result dictionary with sync outcome.
        """
        result = {
            "success": False,
            "pulled_patterns": 0,
            "new_patterns": 0,
            "updated_patterns": 0,
            "errors": [],
        }

        if not self.is_zen_available():
            result["errors"].append("Zen MCP is not available")
            return result

        try:
            # Get remote data
            remote_data = self._get_remote_context()
            if not remote_data:
                result["errors"].append("No data found in Zen MCP")
                return result

            # Extract patterns
            remote_patterns = self._from_zen_format(remote_data)
            result["pulled_patterns"] = len(remote_patterns)

            if merge:
                # Merge with local patterns
                local_patterns = self.persistence.load_patterns()
                new_count, updated_count = self._merge_patterns(local_patterns, remote_patterns)
                result["new_patterns"] = new_count
                result["updated_patterns"] = updated_count
            else:
                # Replace local with remote
                self._save_patterns_to_file(remote_patterns)
                result["new_patterns"] = len(remote_patterns)

            result["success"] = True
            self._update_sync_timestamp("pull")

        except Exception as e:
            result["errors"].append(str(e))

        return result

    def query_cross_project_patterns(self, query: str) -> List[Dict[str, Any]]:
        """
        Query patterns across all projects via Zen MCP.

        Args:
            query: Search query string.

        Returns:
            List of matching patterns with project context.
        """
        if not self.is_zen_available():
            return []

        # Stub: Query Zen MCP for patterns matching query
        # In production, this would:
        # 1. Search Zen memories for refinement patterns
        # 2. Filter by query string
        # 3. Return cross-project matches
        return []

    def sync_bidirectional(self) -> Dict[str, Any]:
        """
        Perform bidirectional sync (push local changes, pull remote updates).

        Returns:
            Combined result from push and pull operations.
        """
        result = {
            "success": False,
            "push_result": None,
            "pull_result": None,
        }

        # First pull to get remote updates
        pull_result = self.pull_from_zen(merge=True)
        result["pull_result"] = pull_result

        # Then push local data
        push_result = self.push_to_zen()
        result["push_result"] = push_result

        result["success"] = pull_result.get("success", False) or push_result.get("success", False)
        return result

    # =========================================================================
    # Zen MCP Interface (Stubs)
    # =========================================================================

    def _get_remote_context(self) -> Optional[Dict[str, Any]]:
        """
        Get refinement context from Zen MCP.

        Note: This is a stub. In production, this would call:
        zen.restore_context(key=ZEN_CONTEXT_KEY)
        """
        # Stub - returns None without Zen MCP
        # TODO: Implement actual Zen MCP call
        return None

    def _save_to_zen(self, context: Dict[str, Any], force: bool = False) -> bool:
        """
        Save context to Zen MCP.

        Note: This is a stub. In production, this would call:
        zen.save_context(key=ZEN_CONTEXT_KEY, data=context)
        """
        # Stub - returns False without Zen MCP
        # TODO: Implement actual Zen MCP call
        return False

    def _search_zen(self, query: str) -> List[Dict[str, Any]]:
        """
        Search Zen MCP for patterns.

        Note: This is a stub. In production, this would call:
        zen.search(query=query, context_type="skill_refinements")
        """
        # Stub - returns empty list without Zen MCP
        # TODO: Implement actual Zen MCP call
        return []

    # =========================================================================
    # Data Conversion
    # =========================================================================

    def _to_zen_format(
        self, refinements: List[Refinement], patterns: List[Pattern]
    ) -> Dict[str, Any]:
        """Convert local data to Zen MCP format."""
        return {
            "active_refinements": [
                {
                    "id": r.id,
                    "skill": r.skill,
                    "category": r.category.value,
                    "status": r.status,
                    "project": r.project,
                    "created": r.created.isoformat() if r.created else None,
                    "pattern_id": r.pattern_id,
                }
                for r in refinements
            ],
            "patterns": {
                p.id: {
                    "name": p.name,
                    "description": p.description,
                    "count": p.count,
                    "projects": p.projects,
                    "status": p.status.value,
                    "affected_skills": p.affected_skills,
                }
                for p in patterns
            },
            "last_sync": datetime.now().isoformat(),
        }

    def _from_zen_format(self, data: Dict[str, Any]) -> List[Pattern]:
        """Convert Zen MCP data to local Pattern objects."""
        patterns = []
        for pattern_id, pattern_data in data.get("patterns", {}).items():
            patterns.append(
                Pattern(
                    id=pattern_id,
                    name=pattern_data.get("name", ""),
                    description=pattern_data.get("description", ""),
                    affected_skills=pattern_data.get("affected_skills", []),
                    refinement_ids=[],
                    projects=pattern_data.get("projects", []),
                    count=pattern_data.get("count", 0),
                    status=PatternStatus(pattern_data.get("status", "tracking")),
                    proposed_changes={},
                )
            )
        return patterns

    # =========================================================================
    # Merge Logic
    # =========================================================================

    def _merge_patterns(
        self, local: List[Pattern], remote: List[Pattern]
    ) -> tuple[int, int]:
        """
        Merge remote patterns into local, preserving local changes.

        Returns:
            Tuple of (new_count, updated_count).
        """
        local_by_id = {p.id: p for p in local}
        new_count = 0
        updated_count = 0

        for remote_pattern in remote:
            if remote_pattern.id in local_by_id:
                # Update existing if remote has higher count
                local_pattern = local_by_id[remote_pattern.id]
                if remote_pattern.count > local_pattern.count:
                    local_pattern.count = remote_pattern.count
                    # Merge projects
                    for proj in remote_pattern.projects:
                        if proj not in local_pattern.projects:
                            local_pattern.projects.append(proj)
                    updated_count += 1
            else:
                # Add new pattern from remote
                local.append(remote_pattern)
                new_count += 1

        # Save merged patterns
        self._save_patterns_to_file(local)
        return new_count, updated_count

    def _save_patterns_to_file(self, patterns: List[Pattern]) -> None:
        """Save patterns to local file."""
        # Use persistence layer to save
        # This is a simplified version - actual implementation would
        # use the full aggregated-patterns.md format
        from aggregate_patterns import PatternAggregator

        aggregator = PatternAggregator(self.refinements_dir)
        aggregator._save_patterns(patterns)

    def _count_pending_push(
        self, local: List[Pattern], remote_data: Dict[str, Any]
    ) -> int:
        """Count patterns that need to be pushed."""
        remote_ids = set(remote_data.get("patterns", {}).keys())
        return sum(1 for p in local if p.id not in remote_ids)

    def _count_pending_pull(
        self, local: List[Pattern], remote_data: Dict[str, Any]
    ) -> int:
        """Count patterns that need to be pulled."""
        local_ids = {p.id for p in local}
        return sum(1 for pid in remote_data.get("patterns", {}) if pid not in local_ids)

    def _update_sync_timestamp(self, operation: str) -> None:
        """Update the sync timestamp file."""
        data = {}
        if self.sync_file.exists():
            try:
                data = json.loads(self.sync_file.read_text())
            except json.JSONDecodeError:
                pass

        data["last_sync"] = datetime.now().isoformat()
        data["last_operation"] = operation
        self.sync_file.write_text(json.dumps(data, indent=2))

    # =========================================================================
    # Output Methods
    # =========================================================================

    def format_status(self, status: Dict[str, Any]) -> str:
        """Format sync status as human-readable output."""
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🔄 Zen MCP Sync Status",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]

        # Connection status
        if status["zen_available"]:
            lines.append("🟢 Zen MCP: Connected")
        else:
            lines.append("⚪ Zen MCP: Not available")

        # Last sync
        if status["last_sync"]:
            lines.append(f"📅 Last Sync: {status['last_sync']}")
        else:
            lines.append("📅 Last Sync: Never")

        lines.append("")

        # Local data
        lines.append("📁 Local Data:")
        lines.append(f"   • Refinements: {status['local_refinements']}")
        lines.append(f"   • Patterns: {status['local_patterns']}")

        # Remote data (if available)
        if status["zen_available"]:
            lines.append("")
            lines.append("☁️  Remote Data:")
            lines.append(f"   • Patterns: {status['remote_patterns']}")
            lines.append("")
            lines.append("🔄 Pending Sync:")
            lines.append(f"   • To push: {status['pending_push']}")
            lines.append(f"   • To pull: {status['pending_pull']}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Synchronize refinement data with Zen MCP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--push",
        action="store_true",
        help="Push local data to Zen MCP",
    )
    group.add_argument(
        "--pull",
        action="store_true",
        help="Pull data from Zen MCP",
    )
    group.add_argument(
        "--sync",
        action="store_true",
        help="Bidirectional sync (push + pull)",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="Show sync status",
    )
    group.add_argument(
        "--query",
        metavar="SEARCH",
        help="Query cross-project patterns",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite (with --push)",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Replace local data instead of merging (with --pull)",
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

    sync_manager = ZenSyncManager()

    # Status
    if args.status or not any([args.push, args.pull, args.sync, args.query]):
        status = sync_manager.get_sync_status()
        if args.json:
            print(json.dumps(status, indent=2, default=str))
        else:
            print(sync_manager.format_status(status))
        return 0

    # Push
    if args.push:
        result = sync_manager.push_to_zen(force=args.force)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result["success"]:
                print(f"✅ Pushed {result['pushed_patterns']} patterns to Zen MCP")
            else:
                print(f"❌ Push failed: {', '.join(result['errors'])}")
        return 0 if result["success"] else 1

    # Pull
    if args.pull:
        result = sync_manager.pull_from_zen(merge=not args.no_merge)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result["success"]:
                print(f"✅ Pulled {result['pulled_patterns']} patterns from Zen MCP")
                print(f"   New: {result['new_patterns']}, Updated: {result['updated_patterns']}")
            else:
                print(f"❌ Pull failed: {', '.join(result['errors'])}")
        return 0 if result["success"] else 1

    # Bidirectional sync
    if args.sync:
        result = sync_manager.sync_bidirectional()
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result["success"]:
                print("✅ Bidirectional sync completed")
                pr = result["push_result"]
                pl = result["pull_result"]
                if pr:
                    print(f"   Pushed: {pr.get('pushed_patterns', 0)} patterns")
                if pl:
                    print(f"   Pulled: {pl.get('new_patterns', 0)} new, {pl.get('updated_patterns', 0)} updated")
            else:
                print("❌ Sync failed")
        return 0 if result["success"] else 1

    # Query
    if args.query:
        patterns = sync_manager.query_cross_project_patterns(args.query)
        if args.json:
            print(json.dumps(patterns, indent=2, default=str))
        else:
            if patterns:
                print(f"Found {len(patterns)} matching patterns:")
                for p in patterns:
                    print(f"   • {p.get('id')}: {p.get('name')}")
            else:
                print("No matching patterns found (or Zen MCP not available)")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
