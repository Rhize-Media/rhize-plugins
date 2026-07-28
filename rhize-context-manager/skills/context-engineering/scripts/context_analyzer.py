#!/usr/bin/env python3
"""
Context Analyzer Script

Analyzes current context usage and provides optimization recommendations.

Usage:
    python context_analyzer.py --session-file /path/to/session.json
    python context_analyzer.py --doc-dir /path/to/project
"""

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class ContextMetrics:
    """Metrics about current context usage."""
    total_tokens: int
    conversation_tokens: int
    documentation_tokens: int
    memory_tokens: int
    tool_output_tokens: int
    estimated_usage_percent: float
    message_count: int
    session_duration_minutes: float


@dataclass 
class ContextRecommendation:
    """A recommendation for context optimization."""
    severity: str  # info, warning, critical
    category: str
    message: str
    action: str


class ContextAnalyzer:
    """Analyzes context usage and provides recommendations."""
    
    STANDARD_WINDOW = 200_000
    LARGE_WINDOW = 1_000_000

    # Last-resort limits keyed by model FAMILY. These are guesses, not facts —
    # see resolve_context_limit() for why a family name cannot size a window.
    FALLBACK_LIMITS = {
        "claude": STANDARD_WINDOW,
        "gpt4": 128_000,
        "default": 100_000
    }

    def __init__(self, model: str = "claude", observed_tokens: int = 0):
        self.model = model
        self.context_limit = self.resolve_context_limit(model, observed_tokens)

    @classmethod
    def resolve_context_limit(cls, model: str = "claude", observed_tokens: int = 0) -> int:
        """Resolve the usable context window, strongest signal first.

        A model FAMILY name cannot size the window: claude-opus-5 is 1M while
        older models share the same "claude" prefix. Dividing by the family
        guess reports ~5x the true usage percent and fires false compact
        warnings for the entire run below 200k. Order:
          1. explicit env override -- same vars ECC's suggest-compact hook
             reads, so the two never disagree about the same session
          2. the `[1m]` marker some model ids carry
          3. observed usage already past the standard window
          4. family fallback (may be wrong; prefer 1-3)
        """
        for var in ("ECC_CONTEXT_WINDOW_TOKENS", "CLAUDE_CODE_AUTO_COMPACT_WINDOW"):
            raw = (os.environ.get(var) or "").strip()
            if raw.isdigit() and int(raw) > 0:
                return int(raw)

        if isinstance(model, str) and "[1m]" in model.lower():
            return cls.LARGE_WINDOW

        if observed_tokens > cls.STANDARD_WINDOW:
            return cls.LARGE_WINDOW

        # Match the family by substring, not exact key: real ids look like
        # "claude-opus-5" / "gpt-4o", which an exact .get() would silently drop
        # to the 100k default -- understating the window instead of overstating
        # it, but just as wrong.
        family = "".join(ch for ch in (model or "").lower() if ch.isalnum())
        for key, limit in cls.FALLBACK_LIMITS.items():
            if key != "default" and key in family:
                return limit
        return cls.FALLBACK_LIMITS["default"]
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (roughly 4 chars per token)."""
        return len(text) // 4
    
    def analyze_file(self, file_path: Path) -> int:
        """Analyze a single file and return estimated tokens."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.estimate_tokens(content)
        except Exception:
            return 0
    
    def analyze_documentation(self, doc_dir: Path) -> dict:
        """Analyze documentation directory."""
        results = {
            "total_tokens": 0,
            "files": {}
        }
        
        doc_patterns = ["*.md", "*.txt", "*.json", "*.yaml", "*.yml"]
        
        for pattern in doc_patterns:
            for file_path in doc_dir.rglob(pattern):
                tokens = self.analyze_file(file_path)
                results["files"][str(file_path)] = tokens
                results["total_tokens"] += tokens
        
        return results
    
    def generate_recommendations(self, metrics: ContextMetrics) -> List[ContextRecommendation]:
        """Generate recommendations based on metrics."""
        recommendations = []
        
        # Check overall usage
        if metrics.estimated_usage_percent > 80:
            recommendations.append(ContextRecommendation(
                severity="critical",
                category="context_exhaustion",
                message=f"Context usage at {metrics.estimated_usage_percent:.1f}% - approaching limit",
                action="Start new session or aggressively compact current context"
            ))
        elif metrics.estimated_usage_percent > 60:
            recommendations.append(ContextRecommendation(
                severity="warning",
                category="context_pressure",
                message=f"Context usage at {metrics.estimated_usage_percent:.1f}%",
                action="Consider summarizing older conversation or offloading to files"
            ))
        
        # Check message count
        if metrics.message_count > 30:
            recommendations.append(ContextRecommendation(
                severity="warning",
                category="session_length",
                message=f"Session has {metrics.message_count} messages",
                action="Consider saving context and starting fresh session"
            ))
        
        # Check conversation ratio
        conversation_ratio = metrics.conversation_tokens / max(metrics.total_tokens, 1)
        if conversation_ratio > 0.5:
            recommendations.append(ContextRecommendation(
                severity="info",
                category="conversation_heavy",
                message=f"Conversation history is {conversation_ratio:.0%} of context",
                action="Summarize older messages to free up space for tools/docs"
            ))
        
        # Check tool output ratio
        tool_ratio = metrics.tool_output_tokens / max(metrics.total_tokens, 1)
        if tool_ratio > 0.3:
            recommendations.append(ContextRecommendation(
                severity="info",
                category="tool_heavy",
                message=f"Tool outputs are {tool_ratio:.0%} of context",
                action="Save large tool outputs to files, keep summaries in context"
            ))
        
        # Check session duration
        if metrics.session_duration_minutes > 120:
            recommendations.append(ContextRecommendation(
                severity="info",
                category="long_session",
                message=f"Session running for {metrics.session_duration_minutes:.0f} minutes",
                action="Consider periodic context saves to prevent loss"
            ))
        
        return recommendations
    
    def print_report(self, metrics: ContextMetrics, recommendations: List[ContextRecommendation]):
        """Print formatted analysis report."""
        print("\n" + "=" * 60)
        print("CONTEXT ANALYSIS REPORT")
        print("=" * 60)
        
        print(f"\n📊 METRICS")
        print(f"   Total tokens: {metrics.total_tokens:,}")
        print(f"   Context usage: {metrics.estimated_usage_percent:.1f}%")
        print(f"   Message count: {metrics.message_count}")
        print(f"   Session duration: {metrics.session_duration_minutes:.0f} min")
        
        print(f"\n📈 TOKEN BREAKDOWN")
        print(f"   Conversation: {metrics.conversation_tokens:,} ({metrics.conversation_tokens/max(metrics.total_tokens,1):.0%})")
        print(f"   Documentation: {metrics.documentation_tokens:,} ({metrics.documentation_tokens/max(metrics.total_tokens,1):.0%})")
        print(f"   Memory: {metrics.memory_tokens:,} ({metrics.memory_tokens/max(metrics.total_tokens,1):.0%})")
        print(f"   Tool outputs: {metrics.tool_output_tokens:,} ({metrics.tool_output_tokens/max(metrics.total_tokens,1):.0%})")
        
        if recommendations:
            print(f"\n💡 RECOMMENDATIONS")
            for rec in recommendations:
                icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[rec.severity]
                print(f"\n   {icon} [{rec.category}]")
                print(f"      {rec.message}")
                print(f"      → {rec.action}")
        else:
            print(f"\n✅ No issues detected")
        
        print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Analyze context usage')
    parser.add_argument('--session-file', type=str, help='Path to session JSON file')
    parser.add_argument('--doc-dir', type=str, help='Path to documentation directory')
    parser.add_argument('--model', type=str, default='claude', 
                        choices=['claude', 'gpt4'], help='Model for context limits')
    parser.add_argument('--threshold', type=float, default=0.6,
                        help='Warning threshold (0-1)')
    
    args = parser.parse_args()
    
    analyzer = ContextAnalyzer(model=args.model)
    
    # Demo metrics if no files provided
    if not args.session_file and not args.doc_dir:
        print("No input provided. Showing demo analysis...")
        
        metrics = ContextMetrics(
            total_tokens=85_000,
            conversation_tokens=45_000,
            documentation_tokens=15_000,
            memory_tokens=5_000,
            tool_output_tokens=20_000,
            estimated_usage_percent=42.5,
            message_count=28,
            session_duration_minutes=75
        )
        
        recommendations = analyzer.generate_recommendations(metrics)
        analyzer.print_report(metrics, recommendations)
        return
    
    # Analyze documentation if provided
    if args.doc_dir:
        doc_path = Path(args.doc_dir)
        if doc_path.exists():
            results = analyzer.analyze_documentation(doc_path)
            
            print(f"\n📁 Documentation Analysis: {doc_path}")
            print(f"   Total files: {len(results['files'])}")
            print(f"   Total tokens: {results['total_tokens']:,}")
            
            # Show largest files
            sorted_files = sorted(results['files'].items(), key=lambda x: x[1], reverse=True)
            print(f"\n   Largest files:")
            for path, tokens in sorted_files[:5]:
                print(f"      {tokens:,} tokens - {path}")


if __name__ == '__main__':
    main()
