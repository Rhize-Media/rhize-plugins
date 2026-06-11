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

### Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `/rhize-devflow:mutation-analyze` | `@analyze-mutations` | Full codebase mutation analysis |
| `/rhize-devflow:mutation-check [file]` | `@check-mutation` | Single file quick check |
| `/rhize-devflow:mutation-fix [priority]` | `@fix-mutations` | Generate fix plan for issues |

### Example Usage

```bash
# Full analysis with dashboard
@analyze-mutations --dashboard

# Check single file
@check-mutation app/actions/players.ts

# Generate fixes for warnings
@fix-mutations P1
```

## Features

### Scoring System
- **≥ 9.0**: Passing - no action needed
- **7.0 - 8.9**: Warning - TODO added, proceeds with warning
- **< 7.0**: Critical - immediate attention required

### Sub-Skills (Auto-Detected)
- **react-query-mutations**: TanStack Query / React Query patterns
- **payload-cms-hooks**: Payload CMS lifecycle hooks
- **redux-toolkit-mutations**: RTK Query (planned)
- **sanity-cms-hooks**: Sanity CMS (planned)

### Enforcement Mode
Advisory mode - warns and adds TODOs but doesn't block implementation.

## Directory Structure

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
│   ├── sentry_integration.py   # Sentry stale data detection
│   └── zen_memory.py           # Cross-session memory
├── hooks/
│   ├── mutation-detector.sh    # UserPromptSubmit hook
│   ├── prewrite-check.sh       # PreToolUse hook
│   └── sentry-stale-data.sh    # Sentry issue detection
├── commands/
│   ├── analyze-mutations.md
│   ├── check-mutation.md
│   └── fix-mutations.md
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
    ├── cross-layer-validation.md
    └── zen-memory-integration.md
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

### Zen MCP Memory
Stores analysis results for cross-session awareness and trend tracking.

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
