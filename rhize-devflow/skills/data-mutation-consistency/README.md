# Data Mutation Consistency Skill

Enforces consistent data mutation patterns across Next.js applications deployed on Vercel with Supabase backends.

## Version

**Current:** 2.0.0
**Platform:** Vercel + Next.js + Supabase

## Purpose

Prevents "mutation drift" where data mutation patterns become inconsistent across a codebase, leading to:
- Stale data in UI after mutations
- Missing error handling causing silent failures
- Cache invalidation gaps
- Inconsistent optimistic updates

## Quick Start

### Command

| Command | Mode | Description |
|---------|------|-------------|
| `/rhize-devflow:mutation-check PATH...` | scoped | One or more files, immediate inline result |
| `/rhize-devflow:mutation-check --all` | whole-codebase | Full analysis, written to `.claude/analysis/` |
| `/rhize-devflow:mutation-check --fix-plan` | fix-plan | Proposed changes only, never edits source |

`mutation-analyze` and `mutation-fix` are retired; `commands/mutation-analyze.md` and
`commands/mutation-fix.md` are deprecation adapters pointing back to `mutation-check`.

### Example Usage

```bash
# Full analysis, optionally scoped
/rhize-devflow:mutation-check --all --focus players

# Check single file
/rhize-devflow:mutation-check app/actions/players.ts

# Generate a fix plan (read-only report, no source edits)
/rhize-devflow:mutation-check --fix-plan --priority P1
```

## Features

### Scoring System
- **≥ 9.0**: Passing - no action needed
- **7.0 - 8.9**: Warning - reported in chat/report; run `--fix-plan` for proposed changes
- **< 7.0**: Critical - immediate attention required; run `--fix-plan` for proposed changes

### Sub-Skills (Auto-Detected)
- **react-query-mutations**: TanStack Query / React Query patterns
- **payload-cms-hooks**: Payload CMS lifecycle hooks
- **redux-toolkit-mutations**: RTK Query (planned)
- **sanity-cms-hooks**: Sanity CMS (planned)

### Enforcement Mode
Read-only, fail-closed - reports warnings and writes proposed-change reports, but never
edits source files and never blocks implementation on its own.

## Directory Structure

The command body lives at `rhize-devflow/commands/mutation-check.md`
(`/rhize-devflow:mutation-check`), not inside this skill directory.

```
data-mutation-consistency/
├── SKILL.md                    # Main router document
├── README.md                   # This file
├── sub-skills/
│   ├── react-query-mutations.md
│   └── payload-cms-hooks.md
├── scripts/
│   ├── common/                 # Shared Python modules
│   ├── analyze_mutations.py    # Full analysis
│   ├── check_single_file.py    # Single file check
│   ├── generate_fixes.py       # Fix generation
│   └── sentry_integration.py   # Sentry stale data detection
├── hooks/
│   ├── mutation-detector.sh    # UserPromptSubmit hook
│   ├── prewrite-check.sh       # PreToolUse hook
│   └── sentry-stale-data.sh    # Sentry issue detection
├── config/
│   ├── scoring-weights.yaml
│   └── detection-patterns.yaml
├── templates/
│   ├── mutation-report.md.template
│   ├── fix-plan.md.template
│   └── quick-summary.md.template
└── references/
    ├── IMPLEMENTATION-STRATEGY.md
    ├── platform-standards.md
    └── cross-layer-validation.md
```

## Installation

### Option 1: Symlink (Development)
```bash
ln -s /path/to/claude-skills/data-mutation-consistency ~/.claude/skills/
```

### Option 2: Reference in CLAUDE.md
```markdown
## Skills
@skills/data-mutation-consistency/SKILL.md
```

### Install Hooks
```bash
cp data-mutation-consistency/hooks/*.sh .claude/hooks/
chmod +x .claude/hooks/*.sh
```

Configure in `.claude/settings.json`:
```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "type": "command",
      "command": ".claude/hooks/mutation-detector.sh \"$PROMPT\"",
      "advisory": true
    }],
    "PreToolUse": [{
      "type": "command",
      "command": ".claude/hooks/prewrite-check.sh \"$FILE_PATH\"",
      "toolNames": ["Write", "Edit"],
      "advisory": true
    }]
  }
}
```

## Integration

### Sentry MCP
Detects stale data patterns in Sentry issues and suggests mutation analysis.

### Anti-Pattern Agent
Integrates with dev-flow-foundations anti-pattern detection for real-time enforcement.

## Platform Requirements

All mutations must include:
- ✅ Typed Supabase client (`@/lib/supabase`)
- ✅ Error handling (check `.error`, try/catch)
- ✅ Cache revalidation (`revalidateTag`/`revalidatePath`)
- ✅ Type-safe returns (`MutationResult<T>`)

## Related Skills

- [context-engineering](../context-engineering/) - Session management
- [error-lifecycle-management](../error-lifecycle-management/) - Error tracking
- [dev-flow-foundations](../dev-flow-foundations/) - Anti-pattern detection

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 2.0.0 | 2024-12-05 | Full implementation with scripts, hooks, commands |
| 1.0.0 | 2024-12-05 | Initial foundation |
