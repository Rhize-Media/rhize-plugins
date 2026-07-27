#!/usr/bin/env python3
"""
Memory Consolidator Script

Helps with memory consolidation by analyzing for duplicates, conflicts, and staleness.

Usage:
    python memory_consolidator.py --demo
    python memory_consolidator.py --memories-file /path/to/memories.json
"""

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Set
from pathlib import Path


@dataclass
class Memory:
    """A single memory entry."""
    id: str
    content: str
    memory_type: str  # declarative, procedural
    category: str
    confidence: float
    created_at: datetime
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    source_session: Optional[str] = None
    superseded_by: Optional[str] = None
    
    @property
    def age_days(self) -> int:
        return (datetime.now() - self.created_at).days
    
    @property
    def is_stale(self) -> bool:
        # Stale if: old + never accessed + low confidence
        if self.age_days > 90 and self.access_count == 0:
            return True
        if self.age_days > 180 and self.confidence < 0.5:
            return True
        return False


@dataclass
class ConsolidationCandidate:
    """A candidate for consolidation action."""
    operation: str  # merge, update, delete
    target_id: str
    related_ids: List[str] = field(default_factory=list)
    reason: str = ""
    confidence: float = 0.0
    suggested_content: Optional[str] = None


class MemoryConsolidator:
    """Analyzes and consolidates memories."""
    
    def __init__(self, memories: List[Memory]):
        self.memories = {m.id: m for m in memories}
    
    def find_potential_duplicates(self, similarity_threshold: float = 0.7) -> List[tuple]:
        """Find memories that might be duplicates."""
        duplicates = []
        memory_list = list(self.memories.values())
        
        for i, m1 in enumerate(memory_list):
            for m2 in memory_list[i+1:]:
                if m1.category != m2.category:
                    continue
                
                similarity = self._jaccard_similarity(
                    set(m1.content.lower().split()),
                    set(m2.content.lower().split())
                )
                
                if similarity >= similarity_threshold:
                    duplicates.append((m1.id, m2.id, similarity))
        
        return duplicates
    
    def _jaccard_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        """Calculate Jaccard similarity between two sets."""
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0
    
    def find_stale_memories(self, max_age_days: int = 90) -> List[Memory]:
        """Find memories that are stale and candidates for removal."""
        return [m for m in self.memories.values() if m.is_stale]
    
    def find_superseded(self) -> List[Memory]:
        """Find memories that have been superseded."""
        return [m for m in self.memories.values() if m.superseded_by]
    
    def apply_confidence_decay(self, decay_rate: float = 0.1, decay_days: int = 90):
        """Apply confidence decay to old memories."""
        now = datetime.now()
        
        for memory in self.memories.values():
            if memory.age_days > decay_days:
                decay_periods = memory.age_days // decay_days
                new_confidence = memory.confidence * ((1 - decay_rate) ** decay_periods)
                memory.confidence = max(0.1, new_confidence)
    
    def generate_report(self) -> str:
        """Generate consolidation report."""
        lines = [
            "=" * 60,
            "MEMORY CONSOLIDATION REPORT",
            "=" * 60,
            "",
            f"📊 STATISTICS",
            f"   Total memories: {len(self.memories)}",
        ]
        
        # By type
        by_type = {}
        for m in self.memories.values():
            by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
        
        for mtype, count in by_type.items():
            lines.append(f"   {mtype}: {count}")
        
        # Stale
        stale = self.find_stale_memories()
        lines.append(f"\n   Stale memories: {len(stale)}")
        
        # Superseded
        superseded = self.find_superseded()
        lines.append(f"   Superseded: {len(superseded)}")
        
        # Duplicates
        duplicates = self.find_potential_duplicates()
        lines.append(f"   Potential duplicates: {len(duplicates)}")
        
        # Consolidation candidates
        lines.extend([
            "",
            "🔧 CONSOLIDATION CANDIDATES",
            ""
        ])
        
        if stale:
            lines.append("   STALE (consider removal):")
            for m in stale[:5]:
                lines.append(f"   - {m.id}: {m.content[:50]}...")
        
        if duplicates:
            lines.append("\n   DUPLICATES (consider merging):")
            for id1, id2, sim in duplicates[:5]:
                lines.append(f"   - {id1} ↔ {id2} ({sim:.0%} similar)")
        
        if superseded:
            lines.append("\n   SUPERSEDED (safe to remove):")
            for m in superseded[:5]:
                lines.append(f"   - {m.id} → {m.superseded_by}")
        
        lines.extend(["", "=" * 60])
        
        return "\n".join(lines)


def create_demo_memories() -> List[Memory]:
    """Create demo memories for testing."""
    now = datetime.now()
    
    return [
        Memory(
            id="mem_001",
            content="User prefers TypeScript over JavaScript for all projects",
            memory_type="declarative",
            category="preference",
            confidence=0.95,
            created_at=now - timedelta(days=30),
            access_count=15
        ),
        Memory(
            id="mem_002",
            content="User prefers TypeScript for development",
            memory_type="declarative",
            category="preference",
            confidence=0.85,
            created_at=now - timedelta(days=60),
            access_count=3
        ),
        Memory(
            id="mem_003",
            content="Debug by checking Sentry errors first, then Vercel logs",
            memory_type="procedural",
            category="debug_workflow",
            confidence=0.90,
            created_at=now - timedelta(days=45),
            access_count=10
        ),
        Memory(
            id="mem_004",
            content="Old architecture decision about REST API",
            memory_type="declarative",
            category="architecture",
            confidence=0.70,
            created_at=now - timedelta(days=120),
            access_count=0,
            superseded_by="mem_005"
        ),
        Memory(
            id="mem_005",
            content="Current architecture uses GraphQL API",
            memory_type="declarative",
            category="architecture",
            confidence=0.95,
            created_at=now - timedelta(days=20),
            access_count=8
        ),
        Memory(
            id="mem_006",
            content="Some random note from long ago",
            memory_type="declarative",
            category="misc",
            confidence=0.40,
            created_at=now - timedelta(days=200),
            access_count=0
        ),
    ]


def main():
    parser = argparse.ArgumentParser(description='Memory consolidation helper')
    parser.add_argument('--memories-file', type=str, help='Path to memories JSON file')
    parser.add_argument('--output', type=str, help='Output file for report')
    parser.add_argument('--demo', action='store_true', help='Run with demo data')
    parser.add_argument('--apply-decay', action='store_true', help='Apply confidence decay')
    
    args = parser.parse_args()
    
    if args.demo or not args.memories_file:
        print("Running with demo data...")
        memories = create_demo_memories()
    else:
        with open(args.memories_file) as f:
            data = json.load(f)
        memories = [Memory(**m) for m in data]
    
    consolidator = MemoryConsolidator(memories)
    
    if args.apply_decay:
        consolidator.apply_confidence_decay()
        print("Applied confidence decay to old memories.")
    
    report = consolidator.generate_report()
    
    if args.output:
        Path(args.output).write_text(report)
        print(f"Report saved to: {args.output}")
    else:
        print(report)


if __name__ == '__main__':
    main()
