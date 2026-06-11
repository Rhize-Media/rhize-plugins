#!/usr/bin/env python3
"""
Mutation Consistency Analyzer

Full codebase analysis for mutation patterns.
Outputs detailed report to file, summary to stdout.

Usage:
    python3 scripts/analyze_mutations.py --root /path/to/project
    python3 scripts/analyze_mutations.py --root . --output-dir .claude/analysis
    python3 scripts/analyze_mutations.py --root . --sub-skills react-query-mutations,payload-cms-hooks
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
    AnalysisResult,
    ProjectConfig,
    SubSkillResult,
    MutationCategory,
)
from common.patterns import PatternMatcher, detect_sub_skills
from common.scoring import ScoreCalculator
from common.output import ReportGenerator, format_summary, generate_dashboard


def find_files(
    root: Path,
    patterns: list[str],
    ignore_paths: list[str],
    ignore_files: list[str],
) -> list[Path]:
    """Find files matching patterns, excluding ignored paths."""
    files = []

    for pattern in patterns:
        for file_path in root.rglob(pattern):
            # Check ignore patterns
            path_str = str(file_path)

            if any(ignore in path_str for ignore in ignore_paths):
                continue

            if any(file_path.match(ignore) for ignore in ignore_files):
                continue

            if file_path.is_file():
                files.append(file_path)

    return list(set(files))  # Deduplicate


def analyze_project(
    root: Path,
    config: ProjectConfig,
    sub_skills: Optional[list[str]] = None,
) -> AnalysisResult:
    """Run full mutation analysis on a project."""
    timestamp = datetime.now()

    # Detect or use specified sub-skills
    if sub_skills is None and config.auto_detect_sub_skills:
        sub_skills = detect_sub_skills(root)
    elif sub_skills is None:
        sub_skills = config.enabled_sub_skills

    # Initialize result
    result = AnalysisResult(
        project_root=root,
        timestamp=timestamp,
        sub_skills_loaded=sub_skills,
    )

    # Initialize pattern matcher with sub-skills
    matcher = PatternMatcher(sub_skills)

    # Load scoring weights
    scoring_config = root / ".claude" / "config" / "scoring-weights.yaml"
    scorer = ScoreCalculator(scoring_config if scoring_config.exists() else None)

    # Find relevant files
    file_patterns = [
        "*.ts",
        "*.tsx",
    ]

    files = find_files(
        root,
        file_patterns,
        config.ignore_paths,
        config.ignore_files,
    )

    # Analyze each file
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)
            continue

        # Find platform mutations (Supabase)
        mutations = matcher.find_mutations(file_path, content)

        # Find React Query mutations if sub-skill loaded
        if "react-query-mutations" in sub_skills:
            rq_mutations = matcher.find_react_query_mutations(file_path, content)
            mutations.extend(rq_mutations)

        # Find Payload collections if sub-skill loaded
        if "payload-cms-hooks" in sub_skills:
            payload_mutations = matcher.find_payload_collections(file_path, content)
            mutations.extend(payload_mutations)

        result.mutations.extend(mutations)

    # Score all mutations
    for mutation in result.mutations:
        score = scorer.score_mutation(mutation)
        result.scores.append(score)
        result.issues.extend(score.issues)

    # Calculate aggregate metrics
    result.total_mutations = len(result.mutations)

    for score in result.scores:
        if score.final_score >= 9.0:
            result.passing_count += 1
        elif score.final_score >= 7.0:
            result.warning_count += 1
        else:
            result.critical_count += 1

    result.overall_score = scorer.calculate_overall_score(result.scores)

    # Build sub-skill results
    for skill in sub_skills:
        category_map = {
            "react-query-mutations": MutationCategory.REACT_QUERY,
            "payload-cms-hooks": MutationCategory.PAYLOAD_HOOK,
        }

        target_category = category_map.get(skill)
        if not target_category:
            continue

        skill_scores = [
            s for s in result.scores
            if s.mutation.category == target_category
        ]

        if skill_scores:
            avg_score = sum(s.final_score for s in skill_scores) / len(skill_scores)
            skill_issues = [
                i for i in result.issues
                if i.mutation.category == target_category
            ]

            result.sub_skill_results[skill] = SubSkillResult(
                name=skill,
                mutations_found=len(skill_scores),
                average_score=round(avg_score, 1),
                issues=skill_issues,
                scores=skill_scores,
            )

    # Cross-layer validation (cache tags vs query keys)
    result.cache_tag_alignment, result.misaligned_tags = validate_cross_layer(
        root, result.mutations
    )

    return result


def validate_cross_layer(root: Path, mutations: list) -> tuple[dict, list]:
    """Validate that backend cache tags align with frontend query keys."""
    alignment = {}
    misaligned = []

    # Extract cache tags from mutations
    cache_tags = set()
    for mutation in mutations:
        if mutation.has_cache_revalidation and mutation.table_or_entity != "unknown":
            cache_tags.add(mutation.table_or_entity)

    # Look for query key factories
    query_key_files = list(root.rglob("*-keys.ts")) + list(root.rglob("*Keys.ts"))
    found_keys = set()

    for key_file in query_key_files:
        try:
            content = key_file.read_text()
            # Extract key names (e.g., playerKeys, gameKeys)
            import re
            matches = re.findall(r"export\s+const\s+(\w+)Keys\s*=", content)
            for match in matches:
                found_keys.add(match.lower())
        except Exception:
            pass

    # Check alignment
    for tag in cache_tags:
        tag_lower = tag.lower().rstrip('s')  # players -> player
        aligned = any(
            tag_lower in key or key in tag_lower
            for key in found_keys
        )
        alignment[tag] = aligned
        if not aligned:
            misaligned.append(tag)

    return alignment, misaligned


def main():
    parser = argparse.ArgumentParser(
        description="Analyze mutation patterns for consistency"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for reports (default: .claude/analysis)",
    )
    parser.add_argument(
        "--sub-skills",
        type=str,
        default=None,
        help="Comma-separated list of sub-skills to load",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary as JSON instead of markdown",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Include ASCII dashboard in output",
    )
    parser.add_argument(
        "--no-file-output",
        action="store_true",
        help="Don't write report file, only print summary",
    )

    args = parser.parse_args()

    # Load project config
    config = ProjectConfig.load_from_file(args.root)

    # Parse sub-skills
    sub_skills = None
    if args.sub_skills:
        sub_skills = [s.strip() for s in args.sub_skills.split(",")]

    # Set output directory
    output_dir = args.output_dir or (args.root / config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run analysis
    print("Analyzing mutations...", file=sys.stderr)
    result = analyze_project(args.root, config, sub_skills)

    # Generate and write full report
    if not args.no_file_output:
        report_generator = ReportGenerator(result)
        full_report = report_generator.generate_full_report()

        timestamp_str = result.timestamp.strftime("%Y%m%d")
        report_path = output_dir / f"mutation-report-{timestamp_str}.md"
        report_path.write_text(full_report)
        print(f"Report written to: {report_path}", file=sys.stderr)

        # Also write pending fixes
        if result.issues:
            pending_path = output_dir / "pending-fixes.md"
            fix_content = generate_pending_fixes(result)
            pending_path.write_text(fix_content)

    # Output summary
    if args.json:
        print(json.dumps(result.to_summary_dict(), indent=2))
    else:
        if args.dashboard:
            print(generate_dashboard(result))
            print()
        print(format_summary(result))


def generate_pending_fixes(result: AnalysisResult) -> str:
    """Generate pending fixes markdown."""
    lines = [
        "# Pending Mutation Fixes",
        "",
        f"Generated: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Outstanding Issues",
        "",
    ]

    for issue in sorted(result.issues, key=lambda i: (i.severity.value, str(i.mutation.file_path))):
        lines.append(
            f"- [{issue.severity.value.upper()}] "
            f"`{issue.mutation.file_path}:{issue.mutation.line_number}` - "
            f"{issue.element}: {issue.message}"
        )

    lines.extend([
        "",
        "---",
        "",
        "Run `@fix-mutations P0` to generate fix plan for critical issues.",
        "Run `@fix-mutations P1` to include warnings.",
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    main()
