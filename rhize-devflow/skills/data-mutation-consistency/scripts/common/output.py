"""
Output Formatting for Mutation Consistency Analysis

Generates reports in various formats with minimal context consumption.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import AnalysisResult, MutationScore, MutationIssue, Severity


class ReportGenerator:
    """Generates detailed analysis reports."""

    def __init__(self, result: AnalysisResult, template_dir: Optional[Path] = None):
        self.result = result
        self.template_dir = template_dir

    def generate_full_report(self) -> str:
        """Generate comprehensive markdown report for file output."""
        lines = [
            "# Mutation Consistency Report",
            "",
            f"Generated: {self.result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Project: {self.result.project_root.name}",
            f"Analyzed: {len(self.result.mutations)} mutations",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Overall Score | {self.result.overall_score}/10 {self.result.status_emoji} |",
            f"| Mutations Analyzed | {self.result.total_mutations} |",
            f"| Passing (≥9.0) | {self.result.passing_count} |",
            f"| Warnings (<9.0) | {self.result.warning_count} |",
            f"| Critical (<7.0) | {self.result.critical_count} |",
            "",
        ]

        # Score distribution visualization
        lines.extend(self._generate_score_distribution())

        # Sub-skills loaded
        if self.result.sub_skills_loaded:
            lines.extend([
                "## Sub-Skills Loaded",
                "",
            ])
            for skill in self.result.sub_skills_loaded:
                sub_result = self.result.sub_skill_results.get(skill)
                if sub_result:
                    lines.append(
                        f"- **{skill}**: {sub_result.mutations_found} mutations, "
                        f"avg score {sub_result.average_score:.1f}/10"
                    )
                else:
                    lines.append(f"- {skill}")
            lines.append("")

        # Issues by priority
        lines.extend(self._generate_issues_by_priority())

        # Detailed analysis by category
        lines.extend(self._generate_detailed_analysis())

        # Cross-layer validation
        if self.result.misaligned_tags:
            lines.extend(self._generate_cross_layer_section())

        # Recommendations
        lines.extend(self._generate_recommendations())

        # Files analyzed
        lines.extend([
            "## Files Analyzed",
            "",
        ])
        seen_files = set()
        for mutation in self.result.mutations:
            if str(mutation.file_path) not in seen_files:
                seen_files.add(str(mutation.file_path))
                lines.append(f"- `{mutation.file_path}`")

        return "\n".join(lines)

    def _generate_score_distribution(self) -> list[str]:
        """Generate ASCII score distribution chart."""
        lines = [
            "## Score Distribution",
            "",
            "```",
        ]

        # Count scores in buckets
        buckets = {10: 0, 9: 0, 8: 0, 7: 0, "below": 0}
        for score in self.result.scores:
            if score.final_score >= 10:
                buckets[10] += 1
            elif score.final_score >= 9:
                buckets[9] += 1
            elif score.final_score >= 8:
                buckets[8] += 1
            elif score.final_score >= 7:
                buckets[7] += 1
            else:
                buckets["below"] += 1

        max_count = max(buckets.values()) if buckets.values() else 1
        scale = 12 / max_count if max_count > 0 else 1

        for bucket, count in buckets.items():
            bar = "█" * int(count * scale)
            label = f"{bucket:>4}" if isinstance(bucket, int) else "<7.0"
            lines.append(f"{label} {bar} {count}")

        lines.extend(["```", ""])
        return lines

    def _generate_issues_by_priority(self) -> list[str]:
        """Generate issues grouped by priority."""
        lines = ["## Issues by Priority", ""]

        critical = [i for i in self.result.issues if i.severity == Severity.CRITICAL]
        warnings = [i for i in self.result.issues if i.severity == Severity.WARNING]
        info = [i for i in self.result.issues if i.severity == Severity.INFO]

        if critical:
            lines.extend([
                "### P0 - Critical (Score < 7.0)",
                "",
            ])
            for issue in critical[:10]:  # Limit to top 10
                lines.append(
                    f"- **{issue.mutation.file_path}:{issue.mutation.line_number}** - "
                    f"{issue.message}"
                )
            lines.append("")

        if warnings:
            lines.extend([
                "### P1 - Warning (Score < 9.0)",
                "",
            ])
            for issue in warnings[:10]:
                lines.append(
                    f"- **{issue.mutation.file_path}:{issue.mutation.line_number}** - "
                    f"{issue.message}"
                )
            lines.append("")

        if info:
            lines.extend([
                "### P2 - Improvement Opportunities",
                "",
            ])
            for issue in info[:5]:
                lines.append(
                    f"- {issue.mutation.file_path}:{issue.mutation.line_number} - "
                    f"{issue.message}"
                )
            lines.append("")

        return lines

    def _generate_detailed_analysis(self) -> list[str]:
        """Generate detailed analysis tables."""
        lines = ["## Detailed Analysis", ""]

        # Group by category
        from collections import defaultdict
        by_category = defaultdict(list)
        for score in self.result.scores:
            by_category[score.mutation.category.value].append(score)

        for category, scores in by_category.items():
            lines.extend([
                f"### {category.replace('_', ' ').title()}",
                "",
                "| File | Line | Entity | Score | Status | Missing |",
                "|------|------|--------|-------|--------|---------|",
            ])

            for score in sorted(scores, key=lambda s: s.final_score):
                missing = ", ".join(score.elements_missing[:3])
                if len(score.elements_missing) > 3:
                    missing += f" +{len(score.elements_missing) - 3}"

                lines.append(
                    f"| {score.mutation.file_path.name} | "
                    f"{score.mutation.line_number} | "
                    f"{score.mutation.table_or_entity} | "
                    f"{score.final_score}/10 | "
                    f"{score.status_emoji} | "
                    f"{missing} |"
                )

            lines.append("")

        return lines

    def _generate_cross_layer_section(self) -> list[str]:
        """Generate cross-layer validation section."""
        lines = [
            "## Cross-Layer Validation",
            "",
            "### Misaligned Cache Tags",
            "",
            "The following cache tags don't have matching frontend query keys:",
            "",
        ]

        for tag in self.result.misaligned_tags:
            lines.append(f"- `{tag}`")

        lines.extend([
            "",
            "**Recommendation:** Ensure backend cache tags align with frontend query key factories.",
            "",
        ])

        return lines

    def _generate_recommendations(self) -> list[str]:
        """Generate actionable recommendations."""
        lines = [
            "## Recommendations",
            "",
        ]

        # Quick wins (low-weight missing elements)
        quick_wins = []
        refactoring = []

        for issue in self.result.issues:
            if issue.severity == Severity.INFO:
                quick_wins.append(issue)
            else:
                refactoring.append(issue)

        if quick_wins:
            lines.extend([
                "### Quick Wins (< 5 min each)",
                "",
            ])
            for issue in quick_wins[:5]:
                lines.append(f"- {issue.fix_suggestion}")
            lines.append("")

        if refactoring:
            lines.extend([
                "### Refactoring Required",
                "",
            ])
            # Group by type
            seen = set()
            for issue in refactoring[:10]:
                key = issue.element
                if key not in seen:
                    seen.add(key)
                    lines.append(f"- **{key}**: {issue.fix_suggestion}")
            lines.append("")

        return lines

    def generate_fix_plan(self, priority: str = "P1") -> str:
        """Generate a fix plan document."""
        lines = [
            "# Mutation Fix Plan",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Priority: {priority}",
            "",
            "## Fixes to Apply",
            "",
        ]

        # Filter by priority
        target_severity = {
            "P0": Severity.CRITICAL,
            "P1": Severity.WARNING,
            "P2": Severity.INFO,
        }.get(priority, Severity.WARNING)

        relevant_issues = [
            i for i in self.result.issues
            if i.severity.value == target_severity.value
            or (priority == "P1" and i.severity == Severity.CRITICAL)
        ]

        for i, issue in enumerate(relevant_issues, 1):
            lines.extend([
                f"### Fix {i}: {issue.element}",
                "",
                f"**File:** `{issue.mutation.file_path}`",
                f"**Line:** {issue.mutation.line_number}",
                f"**Issue:** {issue.message}",
                "",
                "**Solution:**",
                issue.fix_suggestion,
                "",
            ])

            if issue.fix_code:
                lines.extend([
                    "```typescript",
                    issue.fix_code.strip(),
                    "```",
                    "",
                ])

        lines.extend([
            "---",
            "",
            "## Apply These Fixes",
            "",
            "Review each fix above, then apply manually or run:",
            "```",
            "@apply-fixes",
            "```",
        ])

        return "\n".join(lines)


def format_summary(result: AnalysisResult, max_lines: int = 10) -> str:
    """Format a concise summary for chat output (minimal context usage)."""
    lines = [
        f"## Mutation Analysis Complete",
        "",
        f"**Overall Score:** {result.overall_score}/10 {result.status_emoji}",
        "",
    ]

    # Sub-skills (if any)
    if result.sub_skills_loaded:
        lines.append("**Sub-Skills Loaded:**")
        for skill in result.sub_skills_loaded:
            sub = result.sub_skill_results.get(skill)
            if sub:
                lines.append(f"  - {skill}: {sub.average_score:.1f}/10")
            else:
                lines.append(f"  - {skill}")
        lines.append("")

    # Stats
    lines.append(
        f"**Stats:** {result.passing_count} passing, "
        f"{result.warning_count} warnings, "
        f"{result.critical_count} critical"
    )
    lines.append("")

    # Top issues
    top_issues = result.get_top_issues(3)
    if top_issues:
        lines.append("**Top Issues:**")
        for i, issue in enumerate(top_issues, 1):
            severity_icon = {
                Severity.CRITICAL: "🔴",
                Severity.WARNING: "🟡",
                Severity.INFO: "🔵",
            }.get(issue.severity, "")
            lines.append(f"{i}. {severity_icon} {issue.message} ({issue.mutation.file_path.name})")
        lines.append("")

    # Report path
    timestamp = result.timestamp.strftime("%Y%m%d")
    lines.append(f"📄 Full report: `.claude/analysis/mutation-report-{timestamp}.md`")

    return "\n".join(lines[:max_lines])


def format_single_file_result(score: MutationScore) -> str:
    """Format result for single file check."""
    lines = [
        f"**{score.mutation.file_path.name}** - Score: {score.final_score}/10 {score.status_emoji}",
        "",
    ]

    if score.elements_present:
        lines.append(f"✅ Present: {', '.join(score.elements_present)}")

    if score.elements_missing:
        lines.append(f"❌ Missing: {', '.join(score.elements_missing)}")

    if score.final_score < 9.0 and score.issues:
        lines.extend([
            "",
            "**Fixes needed:**",
        ])
        for issue in score.issues[:3]:
            lines.append(f"- {issue.fix_suggestion}")

    return "\n".join(lines)


def generate_dashboard(result: AnalysisResult) -> str:
    """Generate ASCII dashboard for visual overview."""
    # Calculate bar widths
    total = result.total_mutations or 1
    pass_width = int((result.passing_count / total) * 20)
    warn_width = int((result.warning_count / total) * 20)
    crit_width = int((result.critical_count / total) * 20)

    # Ensure at least 1 char for non-zero values
    if result.passing_count > 0 and pass_width == 0:
        pass_width = 1
    if result.warning_count > 0 and warn_width == 0:
        warn_width = 1
    if result.critical_count > 0 and crit_width == 0:
        crit_width = 1

    overall_bar_filled = int(result.overall_score * 2)
    overall_bar_empty = 20 - overall_bar_filled

    lines = [
        "```",
        f"Mutation Health: {'█' * overall_bar_filled}{'░' * overall_bar_empty} {result.overall_score}/10",
        "",
    ]

    # Category breakdown
    from collections import defaultdict
    by_cat = defaultdict(list)
    for score in result.scores:
        by_cat[score.mutation.category.value].append(score.final_score)

    for cat, scores in sorted(by_cat.items()):
        avg = sum(scores) / len(scores)
        bar_filled = int(avg * 2)
        bar_empty = 20 - bar_filled
        status = "⚠️" if avg < 9.0 else ""
        lines.append(
            f"{cat[:15]:<15}: {'█' * bar_filled}{'░' * bar_empty} {avg:.1f}/10 {status}"
        )

    lines.append("```")
    return "\n".join(lines)
