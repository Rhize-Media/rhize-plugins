"""
Project configuration loader for error-lifecycle-management skill.

Supports multiple project structures:
- Monorepo (frontend + backend in separate directories)
- Single repo (all code in one directory)
- Custom configurations

Configuration is loaded from .error-lifecycle.json in the project root,
or falls back to auto-detection.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ProjectConfig:
    """Configuration for a project's error validation."""
    project_type: str = "single"  # "single", "monorepo", "custom"
    project_root: Path = field(default_factory=Path.cwd)
    
    # For single-repo projects
    scan_dirs: List[str] = field(default_factory=lambda: ["app", "lib", "components", "src"])
    
    # For monorepo projects
    frontend_root: Optional[str] = None
    frontend_scan_dirs: List[str] = field(default_factory=lambda: ["app", "lib", "components", "hooks", "providers", "src"])
    backend_root: Optional[str] = None
    backend_scan_dirs: List[str] = field(default_factory=lambda: ["src", "lib"])
    
    # Patterns
    api_patterns: List[str] = field(default_factory=lambda: [
        r'fetch\s*\(',
        r'axios\.',
        r'\.get\(',
        r'\.post\(',
        r'\.patch\(',
        r'\.delete\('
    ])
    exclude_patterns: List[str] = field(default_factory=lambda: [
        r'node_modules',
        r'\.next',
        r'dist',
        r'build',
        r'__tests__',
        r'\.test\.',
        r'\.spec\.',
        r'\.d\.ts$',
    ])


def load_config(project_root: Optional[Path] = None) -> ProjectConfig:
    """
    Load project configuration from .error-lifecycle.json or auto-detect.
    
    Args:
        project_root: Optional project root path. Defaults to cwd.
        
    Returns:
        ProjectConfig with loaded or default settings
    """
    if project_root is None:
        project_root = Path(os.getcwd())
    
    config = ProjectConfig(project_root=project_root)
    config_file = project_root / '.error-lifecycle.json'
    
    if config_file.exists():
        try:
            with open(config_file) as f:
                data = json.load(f)
            config = _parse_config(data, project_root)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse {config_file}: {e}")
            print("Falling back to auto-detection...")
            config = _auto_detect_config(project_root)
    else:
        config = _auto_detect_config(project_root)
    
    return config


def _parse_config(data: Dict, project_root: Path) -> ProjectConfig:
    """Parse configuration from JSON data."""
    config = ProjectConfig(project_root=project_root)
    
    config.project_type = data.get('project_type', 'single')
    
    if config.project_type == 'monorepo':
        frontend = data.get('frontend', {})
        config.frontend_root = frontend.get('root')
        config.frontend_scan_dirs = frontend.get('scan_dirs', config.frontend_scan_dirs)
        
        backend = data.get('backend', {})
        config.backend_root = backend.get('root')
        config.backend_scan_dirs = backend.get('scan_dirs', config.backend_scan_dirs)
    else:
        config.scan_dirs = data.get('scan_dirs', config.scan_dirs)
    
    if 'api_patterns' in data:
        config.api_patterns = data['api_patterns']
    if 'exclude_patterns' in data:
        config.exclude_patterns = data['exclude_patterns']
    
    return config


def _auto_detect_config(project_root: Path) -> ProjectConfig:
    """Auto-detect project structure."""
    config = ProjectConfig(project_root=project_root)
    
    # Check for common monorepo patterns
    monorepo_indicators = [
        ('apps', 'packages'),  # Turborepo style
        ('frontend', 'backend'),  # Simple monorepo
        ('web', 'api'),  # Another common pattern
        ('client', 'server'),  # Client/server pattern
    ]
    
    for frontend_dir, backend_dir in monorepo_indicators:
        frontend_path = project_root / frontend_dir
        backend_path = project_root / backend_dir
        if frontend_path.exists() and backend_path.exists():
            config.project_type = 'monorepo'
            config.frontend_root = frontend_dir
            config.backend_root = backend_dir
            return config
    
    # Check for Next.js apps directory in subdirectory (monorepo)
    for subdir in project_root.iterdir():
        if subdir.is_dir() and (subdir / 'app').exists() and (subdir / 'next.config.js').exists():
            # Found Next.js app in subdirectory
            for backend_check in ['api', 'backend', 'server']:
                if (project_root / backend_check).exists():
                    config.project_type = 'monorepo'
                    config.frontend_root = subdir.name
                    config.backend_root = backend_check
                    return config
    
    # Default to single repo
    config.project_type = 'single'
    return config


def get_scan_directories(config: ProjectConfig) -> List[Path]:
    """Get all directories to scan based on configuration."""
    dirs = []
    
    if config.project_type == 'monorepo':
        if config.frontend_root:
            frontend_base = config.project_root / config.frontend_root
            for d in config.frontend_scan_dirs:
                dir_path = frontend_base / d
                if dir_path.exists():
                    dirs.append(dir_path)
        
        if config.backend_root:
            backend_base = config.project_root / config.backend_root
            for d in config.backend_scan_dirs:
                dir_path = backend_base / d
                if dir_path.exists():
                    dirs.append(dir_path)
    else:
        for d in config.scan_dirs:
            dir_path = config.project_root / d
            if dir_path.exists():
                dirs.append(dir_path)
    
    return dirs
