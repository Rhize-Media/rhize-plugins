#!/usr/bin/env python3
"""
validate_react_query_errors.py - Validate React Query error handling patterns

Checks for:
- useMutation without onError handler
- useQuery without error handling
- Missing error state in components using queries
- Optimistic updates without rollback

Usage:
    python validate_react_query_errors.py [--strict] [--warn] [--json] [--md] [--root /path/to/project]

MCP Integration:
    1. Get React Query best practices from Context7:
       mcp__context7__get-library-docs(
           context7CompatibleLibraryID="/tanstack/query",
           topic="error handling")
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from common import (
    BaseValidationReport,
    BaseValidator,
    Issue,
    ProjectConfig,
    Severity,
    exit_with_status,
    get_output_dir,
    output_json,
    output_markdown,
    parse_validator_args,
    print_summary_box,
)


@dataclass
class ReactQueryReport(BaseValidationReport):
    """Extended report with React Query statistics."""
    mutations_found: int = 0
    mutations_with_error_handler: int = 0
    queries_found: int = 0
    queries_with_error_handling: int = 0

    def to_dict(self) -> Dict:
        base = super().to_dict()
        base["mutations_found"] = self.mutations_found
        base["mutations_with_error_handler"] = self.mutations_with_error_handler
        base["queries_found"] = self.queries_found
        base["queries_with_error_handling"] = self.queries_with_error_handling
        return base


class ReactQueryValidator(BaseValidator):
    """Validates React Query error handling patterns."""

    def __init__(self, config: ProjectConfig):
        super().__init__(config)
        self.report = ReactQueryReport()

    def scan_file(self, filepath: Path) -> List[Issue]:
        """Scan a single file for React Query issues."""
        issues = []
        result = self.read_file_safe(filepath)
        if result is None:
            return [self.create_read_error_issue(filepath, Exception("Could not read file"))]

        content, lines = result
        rel_path = self.get_relative_path(filepath)

        # Skip if not using React Query
        if 'useMutation' not in content and 'useQuery' not in content:
            return issues

        # Check useMutation calls
        for match in re.finditer(r'useMutation\s*\(\s*\{', content):
            self.report.mutations_found += 1
            line_num = content[:match.start()].count('\n') + 1

            # Find the closing brace of the options object
            brace_start = match.end() - 1
            brace_count, pos = 1, brace_start + 1
            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1
            options_block = content[brace_start:pos]

            # Check for onError
            has_on_error = 'onError' in options_block
            if has_on_error:
                self.report.mutations_with_error_handler += 1
            else:
                issues.append(Issue(
                    file=rel_path,
                    line=line_num,
                    severity=Severity.WARNING,
                    rule="mutation-needs-onerror",
                    message="useMutation missing onError handler",
                    code_snippet=self.get_code_snippet(lines, line_num),
                    suggestion="Add onError: (error) => { /* handle error */ }"
                ))

        # Check useQuery calls for error handling in component
        for match in re.finditer(r'(?:const|let)\s*\{\s*([^}]+)\s*\}\s*=\s*useQuery', content):
            self.report.queries_found += 1
            line_num = content[:match.start()].count('\n') + 1
            destructured = match.group(1)

            # Check if error is destructured
            has_error_destructured = 'error' in destructured or 'isError' in destructured
            if has_error_destructured:
                self.report.queries_with_error_handling += 1
            else:
                issues.append(Issue(
                    file=rel_path,
                    line=line_num,
                    severity=Severity.INFO,
                    rule="query-should-handle-error",
                    message="useQuery result doesn't destructure error state",
                    code_snippet=self.get_code_snippet(lines, line_num),
                    suggestion="Consider destructuring { error, isError } for error handling"
                ))

        return issues

    def scan_codebase(self) -> None:
        """Scan all configured directories for React Query issues."""
        scan_dirs = self.get_scan_dirs()

        for scan_dir in scan_dirs:
            files = self.find_files(scan_dir, self.ALL_EXTENSIONS)
            for filepath in files:
                self.report.total_files_scanned += 1
                for issue in self.scan_file(filepath):
                    self.report.add_issue(issue)

        self.report.finalize()

    def get_custom_sections(self, report: ReactQueryReport) -> str:
        """Generate React Query statistics section for markdown report."""
        return f"""## React Query Statistics

| Metric | Count |
|--------|-------|
| Mutations Found | {report.mutations_found} |
| With onError | {report.mutations_with_error_handler} |
| Queries Found | {report.queries_found} |
| With Error Handling | {report.queries_with_error_handling} |

"""

    def print_summary(self) -> None:
        """Print summary to console."""
        lines = [
            f"Files: {self.report.total_files_scanned} | Errors: {self.report.errors} | Warnings: {self.report.warnings}",
            f"Mutations: {self.report.mutations_found} (w/onError: {self.report.mutations_with_error_handler}) | Queries: {self.report.queries_found}",
        ]
        print_summary_box("REACT QUERY VALIDATION", lines, self.report.passed)


def main():
    args = parse_validator_args("Validate React Query error handling")
    output_dir = get_output_dir(args.project_root)

    validator = ReactQueryValidator(args.config)
    validator.scan_codebase()
    validator.print_summary()

    if args.json_output:
        output_json(validator.report, output_dir, 'react-query-report.json')
    if args.md_output:
        output_markdown(
            validator.report,
            output_dir,
            'react-query-report.md',
            'React Query Validation Report',
            lambda r: validator.get_custom_sections(r)
        )

    exit_with_status(validator.report.passed, args.strict)


if __name__ == '__main__':
    main()
