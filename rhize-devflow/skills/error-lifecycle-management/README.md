# Error Lifecycle Management Skill

> Comprehensive error tracking, debugging, and performance monitoring for Next.js/TypeScript applications.

## Version 2.0.0 - Generalized Edition

This skill provides systematic error lifecycle management that works with any project structure, supporting monorepos, single-repo setups, and custom configurations.

## Quick Start

### 1. Add to Your Project

Copy the `error-lifecycle-management` folder to your project's skills directory:

```bash
cp -r error-lifecycle-management /path/to/your-project/skills/
```

### 2. Configure (Optional)

Create `.error-lifecycle.json` in your project root to customize paths:

**Monorepo:**
```json
{
  "project_type": "monorepo",
  "frontend": {
    "root": "apps/web",
    "scan_dirs": ["app", "lib", "components", "hooks", "src"]
  },
  "backend": {
    "root": "apps/api",
    "scan_dirs": ["src", "lib"]
  }
}
```

**Single Repo:**
```json
{
  "project_type": "single",
  "scan_dirs": ["app", "lib", "components", "src"]
}
```

If no config file exists, the skill auto-detects your project structure.

### 3. Run Validators

```bash
# From your project root
cd /path/to/your-project

# Run error coverage validation
python skills/error-lifecycle-management/scripts/validate_error_coverage.py

# Run server action validation
python skills/error-lifecycle-management/scripts/validate_server_action_errors.py

# Run React Query validation
python skills/error-lifecycle-management/scripts/validate_react_query_errors.py
```

## Features

### Validators

| Script | Purpose |
|--------|---------|
| `validate_error_coverage.py` | Scans for empty catch blocks, missing try/catch, Sentry coverage |
| `validate_server_action_errors.py` | Validates Next.js server action error handling |
| `validate_react_query_errors.py` | Checks React Query mutation/query error handling |
| `triage_error.py` | Emergency error triage tool |
| `analyze_performance.js` | Performance analysis tool |

### MCP Server Integration

This skill integrates with:
- **Sentry MCP** - Error tracking and correlation
- **Vercel MCP** - Deployment and build log analysis
- **GitHub MCP** - Change correlation and issue creation
- **Context7 MCP** - Best practices documentation

### Claude Code Triggers

The skill activates on keywords:
- `error`, `bug`, `crash`, `exception`
- `debug`, `troubleshoot`
- `performance`, `slow`, `timeout`
- `sentry`, `stack trace`

## CLI Options

All validators support:

| Flag | Description |
|------|-------------|
| `--strict` | Exit code 1 on errors (default, for CI) |
| `--warn` | Exit code 0, report only |
| `--json` | Output JSON report |
| `--md` | Output Markdown report |
| `--root PATH` | Specify project root (default: cwd) |

## File Structure

```
error-lifecycle-management/
├── SKILL.md                    # Main skill definition
├── README.md                   # This file
├── reference/
│   ├── error-patterns.md       # Common error patterns and fixes
│   ├── sentry-queries.md       # Sentry query patterns
│   └── performance-optimization.md
├── scripts/
│   ├── common/                 # Shared utilities
│   │   ├── __init__.py
│   │   ├── base_validator.py   # Base validator class
│   │   ├── cli.py              # CLI argument parsing
│   │   ├── config.py           # Project configuration
│   │   ├── models.py           # Data models
│   │   └── output.py           # Report generation
│   ├── validate_error_coverage.py
│   ├── validate_server_action_errors.py
│   ├── validate_react_query_errors.py
│   ├── triage_error.py
│   ├── analyze_performance.js
│   └── requirements.txt
├── templates/
│   └── incident-response.md
└── reports/                    # Generated reports
```

## Adding to User Scope

To make this skill available globally in Claude Code:

1. Copy to your global skills directory
2. Reference in your Claude Code settings

Or use the skill directly from any project by pointing to it:

```bash
python /path/to/global/skills/error-lifecycle-management/scripts/validate_error_coverage.py --root $(pwd)
```

## Changelog

### 2.0.0
- Generalized for any project structure
- Added auto-detection of monorepo vs single-repo
- Added configurable API patterns
- Removed hardcoded project paths
- Added `--root` CLI option

### 1.0.0
- Initial release (VBA-specific)

## License

MIT - Use freely in your projects.
