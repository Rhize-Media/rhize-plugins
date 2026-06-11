"""
CLI argument parsing utilities for validators.

Provides consistent command-line interface across all validation scripts.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import ProjectConfig, load_config


@dataclass
class ValidatorArgs:
    """Parsed command-line arguments for validators."""
    strict: bool
    warn: bool
    json_output: bool
    md_output: bool
    project_root: Path
    config: ProjectConfig


def parse_validator_args(description: str = "Validate codebase") -> ValidatorArgs:
    """
    Parse standard validator command-line arguments.

    Standard flags:
        --strict    Exit with code 1 if any errors found (default for CI)
        --warn      Exit with code 0, report warnings only
        --json      Output JSON report
        --md        Output Markdown report
        --root      Project root directory (default: current directory)

    Returns:
        ValidatorArgs with parsed options and loaded config
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Exit with code 1 if any errors found (default for CI)'
    )
    parser.add_argument(
        '--warn',
        action='store_true',
        help='Exit with code 0, report warnings only'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        dest='json_output',
        help='Output JSON report'
    )
    parser.add_argument(
        '--md',
        action='store_true',
        dest='md_output',
        help='Output Markdown report'
    )
    parser.add_argument(
        '--root',
        type=str,
        default=None,
        help='Project root directory (default: current directory)'
    )
    args = parser.parse_args()

    # Default to both outputs if neither specified
    if not args.json_output and not args.md_output:
        args.json_output = True
        args.md_output = True

    # Default to strict if neither specified
    if not args.strict and not args.warn:
        args.strict = True

    # Determine project root
    project_root = Path(args.root) if args.root else Path(os.getcwd())
    
    # Load configuration
    config = load_config(project_root)

    return ValidatorArgs(
        strict=args.strict,
        warn=args.warn,
        json_output=args.json_output,
        md_output=args.md_output,
        project_root=project_root,
        config=config
    )


def get_output_dir(project_root: Optional[Path] = None, skill_dir: str = 'skills') -> Path:
    """
    Get the output directory for validation reports.

    Args:
        project_root: Optional project root path. Defaults to cwd.
        skill_dir: Directory name for skills (default: 'skills')

    Returns:
        Path to reports directory (creates if not exists)
    """
    if project_root is None:
        project_root = Path(os.getcwd())

    output_dir = project_root / skill_dir / 'error-lifecycle-management' / 'reports'
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def exit_with_status(passed: bool, strict: bool) -> None:
    """
    Exit with appropriate status code.

    Args:
        passed: Whether validation passed
        strict: Whether to use strict mode (exit 1 on failure)
    """
    if strict and not passed:
        sys.exit(1)
    sys.exit(0)
