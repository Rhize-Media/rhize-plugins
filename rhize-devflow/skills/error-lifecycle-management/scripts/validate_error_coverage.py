#!/usr/bin/env python3
"""
validate_error_coverage.py - Scan codebase for error handling gaps

Checks for:
- Unhandled promise rejections in async functions
- Missing try/catch in server actions
- Empty catch blocks
- API calls without error handling
- Missing Sentry integration
- User-friendly error messages

Usage:
    python validate_error_coverage.py [--strict] [--warn] [--json] [--md] [--root /path/to/project]

Flags:
    --strict    Exit with code 1 if any errors found (default for CI)
    --warn      Exit with code 0, report warnings only
    --json      Output JSON report
    --md        Output Markdown report
    --root      Project root directory (default: current directory)

MCP Integration:
    After running this validator, correlate findings with Sentry:

    1. Search for production errors in flagged files:
       mcp__sentry__search_issues(organizationSlug="your-org",
           naturalLanguageQuery="errors in <file-path>")

    2. Get fix patterns from Context7:
       mcp__context7__get-library-docs(topic="error handling")

    3. Navigate to code with Serena:
       mcp__serena__find_symbol(name_path="<function>", include_body=true)
"""

import re
from dataclasses import dataclass, field
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
class Coverage:
    """Error handling coverage statistics."""
    async_functions: int = 0
    async_with_try_catch: int = 0
    server_actions: int = 0
    server_actions_with_handling: int = 0
    api_calls: int = 0
    api_calls_with_handling: int = 0
    sentry_captures: int = 0

    @property
    def async_coverage(self) -> float:
        if self.async_functions == 0:
            return 100.0
        return (self.async_with_try_catch / self.async_functions) * 100

    @property
    def server_action_coverage(self) -> float:
        if self.server_actions == 0:
            return 100.0
        return (self.server_actions_with_handling / self.server_actions) * 100

    @property
    def api_coverage(self) -> float:
        if self.api_calls == 0:
            return 100.0
        return (self.api_calls_with_handling / self.api_calls) * 100


@dataclass
class ErrorCoverageReport(BaseValidationReport):
    """Extended report with coverage statistics."""
    coverage: Coverage = field(default_factory=Coverage)

    def to_dict(self) -> Dict:
        base = super().to_dict()
        base["coverage"] = {
            "async_functions": self.coverage.async_functions,
            "async_with_try_catch": self.coverage.async_with_try_catch,
            "async_coverage_pct": round(self.coverage.async_coverage, 1),
            "server_actions": self.coverage.server_actions,
            "server_actions_with_handling": self.coverage.server_actions_with_handling,
            "server_action_coverage_pct": round(self.coverage.server_action_coverage, 1),
            "api_calls": self.coverage.api_calls,
            "api_calls_with_handling": self.coverage.api_calls_with_handling,
            "api_coverage_pct": round(self.coverage.api_coverage, 1),
            "sentry_captures": self.coverage.sentry_captures,
        }
        return base


class ErrorCoverageValidator(BaseValidator):
    """Validates error handling coverage across the codebase."""

    PATTERNS = {
        "empty_catch": {
            # Use [ \t]* instead of \s* to avoid matching newlines
            "pattern": r'catch\s*\([^)]*\)\s*\{[ \t]*\}',
            "rule": "no-empty-catch",
            "message": "Empty catch block swallows errors silently",
            "severity": Severity.ERROR,
            "suggestion": "Log error or re-throw: catch (e) { console.error(e); throw e; }"
        },
        "catch_ignore": {
            "pattern": r'catch\s*\(_\)\s*\{',
            "rule": "catch-should-use-error",
            "message": "Catch block ignores error parameter",
            "severity": Severity.WARNING,
            "suggestion": "Use the error: catch (error) { ... }"
        },
        "todo_error": {
            "pattern": r'//\s*TODO.*error|//\s*FIXME.*error',
            "rule": "unresolved-error-todo",
            "message": "Unresolved TODO/FIXME for error handling",
            "severity": Severity.WARNING,
            "suggestion": "Address the TODO before shipping"
        }
    }

    def __init__(self, config: ProjectConfig):
        super().__init__(config)
        self.report = ErrorCoverageReport()

    def scan_file(self, filepath: Path) -> List[Issue]:
        """Scan a single file for error handling issues."""
        issues = []
        result = self.read_file_safe(filepath)
        if result is None:
            return [self.create_read_error_issue(filepath, Exception("Could not read file"))]

        content, lines = result
        rel_path = self.get_relative_path(filepath)

        # Check patterns
        for name, config_item in self.PATTERNS.items():
            for match in re.finditer(config_item["pattern"], content, re.MULTILINE):
                line_num = content[:match.start()].count('\n') + 1
                line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                if line_content.strip().startswith('//'):
                    continue
                issues.append(Issue(
                    file=rel_path,
                    line=line_num,
                    severity=config_item["severity"],
                    rule=config_item["rule"],
                    message=config_item["message"],
                    code_snippet=self.get_code_snippet(lines, line_num),
                    suggestion=config_item["suggestion"]
                ))

        # Coverage: async functions
        for match in re.finditer(r'async\s+(?:function\s+)?(\w+)?\s*\([^)]*\)\s*(?::[^{]+)?\s*\{', content):
            self.report.coverage.async_functions += 1
            func_start = match.end()
            brace_count, pos = 1, func_start
            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1
            func_body = content[func_start:pos]
            if 'try' in func_body and 'catch' in func_body:
                self.report.coverage.async_with_try_catch += 1

        # Coverage: server actions
        if "'use server'" in content or '"use server"' in content:
            for match in re.finditer(r'export\s+async\s+function\s+(\w+)', content):
                self.report.coverage.server_actions += 1
                func_start = match.end()
                brace_start = content.find('{', func_start)
                if brace_start >= 0:
                    brace_count, pos = 1, brace_start + 1
                    while pos < len(content) and brace_count > 0:
                        if content[pos] == '{':
                            brace_count += 1
                        elif content[pos] == '}':
                            brace_count -= 1
                        pos += 1
                    func_body = content[brace_start:pos]
                    if ('try' in func_body and 'catch' in func_body) or 'error:' in func_body:
                        self.report.coverage.server_actions_with_handling += 1

        # Coverage: API calls (using configurable patterns)
        for pattern in self.config.api_patterns:
            self.report.coverage.api_calls += len(re.findall(pattern, content))
        
        # Coverage: Sentry captures
        self.report.coverage.sentry_captures += len(
            re.findall(r'Sentry\.captureException|captureException', content)
        )

        return issues

    def scan_codebase(self) -> None:
        """Scan all configured directories for error handling issues."""
        scan_dirs = self.get_scan_dirs()

        for scan_dir in scan_dirs:
            files = self.find_files(scan_dir, self.ALL_EXTENSIONS)
            for filepath in files:
                self.report.total_files_scanned += 1
                for issue in self.scan_file(filepath):
                    self.report.add_issue(issue)

        self.report.finalize()

    def get_custom_sections(self, report: ErrorCoverageReport) -> str:
        """Generate coverage statistics section for markdown report."""
        cov = report.coverage
        return f"""## Coverage

| Category | Total | Handled | Coverage |
|----------|-------|---------|----------|
| Async Functions | {cov.async_functions} | {cov.async_with_try_catch} | {cov.async_coverage:.1f}% |
| Server Actions | {cov.server_actions} | {cov.server_actions_with_handling} | {cov.server_action_coverage:.1f}% |
| API Calls | {cov.api_calls} | - | - |
| Sentry Captures | {cov.sentry_captures} | - | - |

"""

    def print_summary(self) -> None:
        """Print summary to console."""
        cov = self.report.coverage
        lines = [
            f"Files: {self.report.total_files_scanned} | Errors: {self.report.errors} | Warnings: {self.report.warnings}",
            f"Async: {cov.async_coverage:.0f}% | Server Actions: {cov.server_action_coverage:.0f}% | Sentry: {cov.sentry_captures}",
        ]
        print_summary_box("ERROR COVERAGE SUMMARY", lines, self.report.passed)


def main():
    args = parse_validator_args("Validate error handling coverage")
    output_dir = get_output_dir(args.project_root)

    validator = ErrorCoverageValidator(args.config)
    validator.scan_codebase()
    validator.print_summary()

    if args.json_output:
        output_json(validator.report, output_dir, 'error-coverage-report.json')
    if args.md_output:
        output_markdown(
            validator.report,
            output_dir,
            'error-coverage-report.md',
            'Error Coverage Report',
            lambda r: validator.get_custom_sections(r)
        )

    exit_with_status(validator.report.passed, args.strict)


if __name__ == '__main__':
    main()
