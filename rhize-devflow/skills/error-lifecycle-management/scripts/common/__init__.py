"""
Common utilities for error-lifecycle-management validators.

This package provides shared infrastructure for all validation scripts.
"""

from .base_validator import BaseValidator
from .cli import (
    ValidatorArgs,
    exit_with_status,
    get_output_dir,
    parse_validator_args,
)
from .config import (
    ProjectConfig,
    get_scan_directories,
    load_config,
)
from .models import (
    BaseValidationReport,
    Issue,
    Severity,
)
from .output import (
    output_json,
    output_markdown,
    print_summary_box,
)

__all__ = [
    # Base classes
    'BaseValidator',
    'BaseValidationReport',
    # Models
    'Issue',
    'Severity',
    # Configuration
    'ProjectConfig',
    'load_config',
    'get_scan_directories',
    # CLI
    'ValidatorArgs',
    'parse_validator_args',
    'get_output_dir',
    'exit_with_status',
    # Output
    'output_json',
    'output_markdown',
    'print_summary_box',
]
