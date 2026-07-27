#!/usr/bin/env python3
"""
Session Manager Script

Automates session lifecycle: context saving/loading, handoff generation, documentation freshness.

Usage:
    python session_manager.py handoff --topic "Feature X" --status in_progress
    python session_manager.py check --freshness
    python session_manager.py list
"""

import argparse
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional


@dataclass
class SessionState:
    """Current session state."""
    topic: str
    status: str  # in_progress, blocked, complete
    started_at: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    files_modified: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)


class SessionManager:
    """Manages session lifecycle operations."""
    
    def __init__(self, project_dir: Path = None):
        self.project_dir = project_dir or Path.cwd()
        self.handoffs_dir = self.project_dir / "session-handoffs"
    
    def generate_handoff(self, state: SessionState) -> str:
        """Generate handoff document from session state."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        lines = [
            f"# Session Handoff: {state.topic}",
            f"",
            f"**Generated**: {timestamp}",
            f"**Status**: {state.status}",
            f"**Duration**: Started {state.started_at.strftime('%Y-%m-%d %H:%M')}",
            f"",
            f"---",
            f"",
            f"## Summary",
            f"",
        ]
        
        # Completed items
        if state.files_modified:
            lines.extend([f"### Files Modified", ""])
            for f in state.files_modified:
                lines.append(f"- `{f}`")
            lines.append("")
        
        # Decisions
        if state.decisions:
            lines.extend([f"### Key Decisions", ""])
            for d in state.decisions:
                lines.append(f"- {d}")
            lines.append("")
        
        # Blockers
        if state.blockers:
            lines.extend([f"### Blockers", ""])
            for b in state.blockers:
                lines.append(f"- ⚠️ {b}")
            lines.append("")
        
        # Next steps
        if state.next_steps:
            lines.extend([f"### Next Steps", ""])
            for i, step in enumerate(state.next_steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")
        
        # Context recovery
        lines.extend([
            f"---",
            f"",
            f"## Context Recovery",
            f"",
            f"To resume this work:",
            f"",
            f"1. Load this handoff document",
            f"2. Review files modified above",
            f"3. Address any blockers",
            f"4. Continue with next steps",
            f"",
        ])
        
        return "\n".join(lines)
    
    def save_handoff(self, state: SessionState) -> Path:
        """Save handoff to file."""
        self.handoffs_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        safe_topic = state.topic.lower().replace(" ", "-")[:30]
        filename = f"handoff-{safe_topic}-{timestamp}.md"
        
        filepath = self.handoffs_dir / filename
        content = self.generate_handoff(state)
        
        filepath.write_text(content)
        return filepath
    
    def check_freshness(self, doc_dir: Path = None) -> List[dict]:
        """Check freshness of documentation files."""
        doc_dir = doc_dir or self.project_dir
        
        # Files and their max age in days
        freshness_rules = {
            "CLAUDE.md": 14,
            "README.md": 30,
            "CURRENT_SPRINT.md": 3,
            "SESSION_CONTEXT.md": 1,
            "COMPONENT_REGISTRY.md": 7,
            "CHANGELOG.md": 14,
        }
        
        results = []
        now = datetime.now()
        
        for filename, max_days in freshness_rules.items():
            filepath = doc_dir / filename
            if filepath.exists():
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                age_days = (now - mtime).days
                is_stale = age_days > max_days
                
                results.append({
                    "file": filename,
                    "age_days": age_days,
                    "max_days": max_days,
                    "is_stale": is_stale,
                    "last_modified": mtime.strftime("%Y-%m-%d")
                })
        
        return results
    
    def print_freshness_report(self, results: List[dict]):
        """Print freshness report."""
        print("\n" + "=" * 60)
        print("DOCUMENTATION FRESHNESS REPORT")
        print("=" * 60)
        
        if not results:
            print("\nNo tracked documentation files found.")
            return
        
        stale_count = sum(1 for r in results if r["is_stale"])
        
        print(f"\n📁 Files checked: {len(results)}")
        print(f"⚠️  Stale files: {stale_count}")
        print("")
        
        for r in results:
            icon = "🔴" if r["is_stale"] else "🟢"
            status = "STALE" if r["is_stale"] else "OK"
            print(f"{icon} {r['file']}")
            print(f"   Last modified: {r['last_modified']} ({r['age_days']} days ago)")
            print(f"   Max age: {r['max_days']} days - {status}")
            print("")
        
        print("=" * 60)
    
    def list_handoffs(self, limit: int = 10) -> List[Path]:
        """List recent handoff files."""
        if not self.handoffs_dir.exists():
            return []
        
        handoffs = sorted(
            self.handoffs_dir.glob("handoff-*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        return handoffs[:limit]
    
    def print_handoffs(self, handoffs: List[Path]):
        """Print list of handoffs."""
        print("\n" + "=" * 60)
        print("RECENT SESSION HANDOFFS")
        print("=" * 60)
        
        if not handoffs:
            print("\nNo handoffs found.")
            return
        
        for h in handoffs:
            mtime = datetime.fromtimestamp(h.stat().st_mtime)
            print(f"\n📄 {h.name}")
            print(f"   Created: {mtime.strftime('%Y-%m-%d %H:%M')}")
        
        print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Session lifecycle management')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Handoff command
    handoff_parser = subparsers.add_parser('handoff', help='Generate session handoff')
    handoff_parser.add_argument('--topic', required=True, help='Session topic')
    handoff_parser.add_argument('--status', default='in_progress',
                                choices=['in_progress', 'blocked', 'complete'])
    handoff_parser.add_argument('--files', nargs='*', default=[], help='Files modified')
    handoff_parser.add_argument('--decisions', nargs='*', default=[], help='Key decisions')
    handoff_parser.add_argument('--blockers', nargs='*', default=[], help='Blockers')
    handoff_parser.add_argument('--next', nargs='*', default=[], dest='next_steps', help='Next steps')
    handoff_parser.add_argument('--save', action='store_true', help='Save to file')
    
    # Check command
    check_parser = subparsers.add_parser('check', help='Check documentation')
    check_parser.add_argument('--freshness', action='store_true', help='Check doc freshness')
    check_parser.add_argument('--dir', type=str, help='Directory to check')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List handoffs')
    list_parser.add_argument('--limit', type=int, default=10, help='Max handoffs to show')
    
    args = parser.parse_args()
    manager = SessionManager()
    
    if args.command == 'handoff':
        state = SessionState(
            topic=args.topic,
            status=args.status,
            files_modified=args.files,
            decisions=args.decisions,
            blockers=args.blockers,
            next_steps=args.next_steps
        )
        
        if args.save:
            filepath = manager.save_handoff(state)
            print(f"Handoff saved to: {filepath}")
        else:
            print(manager.generate_handoff(state))
    
    elif args.command == 'check':
        if args.freshness:
            doc_dir = Path(args.dir) if args.dir else None
            results = manager.check_freshness(doc_dir)
            manager.print_freshness_report(results)
    
    elif args.command == 'list':
        handoffs = manager.list_handoffs(args.limit)
        manager.print_handoffs(handoffs)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
