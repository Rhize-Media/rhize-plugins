"""
Base validator class with shared functionality.

Provides common infrastructure for all validation scripts including:
- File exclusion patterns
- Path construction for any project structure
- Code snippet extraction
- File scanning utilities
"""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from .config import ProjectConfig, get_scan_directories
from .models import Issue, Severity


class BaseValidator(ABC):
    """Abstract base class for all validators."""

    # File extensions to scan
    TS_EXTENSIONS: List[str] = ['.ts', '.tsx']
    JS_EXTENSIONS: List[str] = ['.js', '.jsx']
    ALL_EXTENSIONS: List[str] = ['.ts', '.tsx', '.js', '.jsx']

    def __init__(self, config: ProjectConfig):
        """Initialize validator with project configuration."""
        self.config = config
        self.project_root = config.project_root

    def should_skip_file(self, filepath: str) -> bool:
        """Check if file should be excluded from scanning."""
        return any(re.search(p, filepath) for p in self.config.exclude_patterns)

    def get_code_snippet(
        self,
        lines: List[str],
        line_num: int,
        context: int = 2
    ) -> str:
        """Extract code snippet around the issue with context lines."""
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)
        snippet_lines = []
        for i in range(start, end):
            prefix = ">>> " if i == line_num - 1 else "    "
            snippet_lines.append(f"{prefix}{i + 1}: {lines[i].rstrip()}")
        return "\n".join(snippet_lines)

    def read_file_safe(self, filepath: Path) -> Optional[tuple]:
        """Safely read a file and return (content, lines) or None on error."""
        try:
            content = filepath.read_text(encoding='utf-8')
            lines = content.split('\n')
            return content, lines
        except Exception:
            return None

    def create_read_error_issue(self, filepath: Path, error: Exception) -> Issue:
        """Create an issue for file read errors."""
        return Issue(
            file=str(filepath.relative_to(self.project_root)),
            line=0,
            severity=Severity.WARNING,
            rule="file-read-error",
            message=f"Could not read file: {error}"
        )

    def get_relative_path(self, filepath: Path) -> str:
        """Get path relative to project root."""
        return str(filepath.relative_to(self.project_root))

    def find_files(
        self,
        directory: Path,
        extensions: Optional[List[str]] = None
    ) -> List[Path]:
        """Find all files with given extensions in directory."""
        if extensions is None:
            extensions = self.ALL_EXTENSIONS

        files = []
        if not directory.exists():
            return files

        for ext in extensions:
            for filepath in directory.rglob(f'*{ext}'):
                if not self.should_skip_file(str(filepath)):
                    files.append(filepath)

        return files

    def get_scan_dirs(self) -> List[Path]:
        """Get directories to scan based on project configuration."""
        return get_scan_directories(self.config)

    @abstractmethod
    def scan_codebase(self) -> None:
        """Scan the codebase for issues. Must be implemented by subclasses."""
        pass
