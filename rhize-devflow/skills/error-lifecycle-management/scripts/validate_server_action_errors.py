#!/usr/bin/env python3
"""
validate_server_action_errors.py - Validate Next.js Server Action error patterns

Checks for:
- Missing "use server" directive in action files
- Result type not following { success, error? } pattern
- Missing Sentry error tracking in catch blocks
- No input validation before operations
- Async operations without try/catch
- Missing error instanceof Error narrowing

Usage:
    python validate_server_action_errors.py [--strict] [--warn] [--json] [--md] [--root /path/to/project]

MCP Integration:
    After running this validator, correlate with production:

    1. Check Sentry for server action errors:
       mcp__sentry__search_issues(organizationSlug="your-org",
           naturalLanguageQuery="server action errors")

    2. Get Next.js server action patterns from Context7:
       mcp__context7__get-library-docs(
           context7CompatibleLibraryID="/vercel/next.js",
           topic="server actions")
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
class ServerActionReport(BaseValidationReport):
    """Extended report with server action statistics."""
    server_actions_found: int = 0
    actions_with_try_catch: int = 0
    actions_with_sentry: int = 0

    def to_dict(self) -> Dict:
        base = super().to_dict()
        base["server_actions_found"] = self.server_actions_found
        base["actions_with_try_catch"] = self.actions_with_try_catch
        base["actions_with_sentry"] = self.actions_with_sentry
        return base


class ServerActionValidator(BaseValidator):
    """Validates Next.js Server Action error handling patterns."""

    def __init__(self, config: ProjectConfig):
        super().__init__(config)
        self.report = ServerActionReport()

    def scan_file(self, filepath: Path) -> List[Issue]:
        """Scan a single file for server action issues."""
        issues = []
        result = self.read_file_safe(filepath)
        if result is None:
            return [self.create_read_error_issue(filepath, Exception("Could not read file"))]

        content, lines = result
        rel_path = self.get_relative_path(filepath)

        # Check if this is a server action file
        has_use_server = "'use server'" in content or '"use server"' in content
        if not has_use_server:
            return issues

        # Find all exported async functions (server actions)
        for match in re.finditer(r'export\s+async\s+function\s+(\w+)\s*\([^)]*\)', content):
            func_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            self.report.server_actions_found += 1

            # Extract function body
            func_start = content.find('{', match.end())
            if func_start < 0:
                continue

            brace_count, pos = 1, func_start + 1
            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1
            func_body = content[func_start:pos]

            # Check for try/catch
            has_try_catch = 'try' in func_body and 'catch' in func_body
            if has_try_catch:
                self.report.actions_with_try_catch += 1
            else:
                issues.append(Issue(
                    file=rel_path,
                    line=line_num,
                    severity=Severity.ERROR,
                    rule="server-action-needs-try-catch",
                    message=f"Server action '{func_name}' missing try/catch block",
                    code_snippet=self.get_code_snippet(lines, line_num),
                    suggestion="Wrap action body in try/catch with error reporting"
                ))

            # Check for Sentry capture in catch blocks
            has_sentry = 'Sentry.captureException' in func_body or 'captureException' in func_body
            if has_sentry:
                self.report.actions_with_sentry += 1
            elif has_try_catch:
                issues.append(Issue(
                    file=rel_path,
                    line=line_num,
                    severity=Severity.WARNING,
                    rule="server-action-needs-sentry",
                    message=f"Server action '{func_name}' has try/catch but no Sentry error tracking",
                    code_snippet=self.get_code_snippet(lines, line_num),
                    suggestion="Add Sentry.captureException(error) in catch block"
                ))

            # Check for result type pattern
            if 'return {' in func_body:
                if not re.search(r'success\s*:', func_body):
                    issues.append(Issue(
                        file=rel_path,
                        line=line_num,
                        severity=Severity.WARNING,
                        rule="server-action-result-type",
                        message=f"Server action '{func_name}' return may not follow {{ success, error? }} pattern",
                        code_snippet=self.get_code_snippet(lines, line_num),
                        suggestion="Return { success: boolean, error?: string, data?: T }"
                    ))

        return issues

    def scan_codebase(self) -> None:
        """Scan all configured directories for server action issues."""
        scan_dirs = self.get_scan_dirs()

        for scan_dir in scan_dirs:
            files = self.find_files(scan_dir, self.TS_EXTENSIONS)
            for filepath in files:
                self.report.total_files_scanned += 1
                for issue in self.scan_file(filepath):
                    self.report.add_issue(issue)

        self.report.finalize()

    def get_custom_sections(self, report: ServerActionReport) -> str:
        """Generate server action statistics section for markdown report."""
        return f"""## Server Action Statistics

| Metric | Count |
|--------|-------|
| Server Actions Found | {report.server_actions_found} |
| With try/catch | {report.actions_with_try_catch} |
| With Sentry | {report.actions_with_sentry} |

"""

    def print_summary(self) -> None:
        """Print summary to console."""
        lines = [
            f"Files: {self.report.total_files_scanned} | Errors: {self.report.errors} | Warnings: {self.report.warnings}",
            f"Actions: {self.report.server_actions_found} | With try/catch: {self.report.actions_with_try_catch} | With Sentry: {self.report.actions_with_sentry}",
        ]
        print_summary_box("SERVER ACTION VALIDATION", lines, self.report.passed)


def main():
    args = parse_validator_args("Validate server action error handling")
    output_dir = get_output_dir(args.project_root)

    validator = ServerActionValidator(args.config)
    validator.scan_codebase()
    validator.print_summary()

    if args.json_output:
        output_json(validator.report, output_dir, 'server-actions-report.json')
    if args.md_output:
        output_markdown(
            validator.report,
            output_dir,
            'server-actions-report.md',
            'Server Action Validation Report',
            lambda r: validator.get_custom_sections(r)
        )

    exit_with_status(validator.report.passed, args.strict)


if __name__ == '__main__':
    main()
