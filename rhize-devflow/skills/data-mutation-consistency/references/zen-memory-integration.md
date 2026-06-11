# Zen MCP Memory Integration

## Purpose

Maintain cross-session awareness of mutation analysis results using Zen MCP's memory capabilities. This allows Claude to:

1. Remember previous analysis findings between sessions
2. Track improvement trends over time
3. Provide context-aware suggestions based on known issues
4. Reduce redundant re-analysis

## Integration Points

### After Running @analyze-mutations

```
┌─────────────────────────────────────────────────────────────────┐
│  @analyze-mutations                                              │
│        │                                                         │
│        ▼                                                         │
│  ┌──────────────┐     ┌──────────────────────────────────────┐  │
│  │ Generate     │     │ Extract Key Metrics:                  │  │
│  │ Full Report  │────▶│ • Overall score                       │  │
│  │ (.claude/    │     │ • Issue counts                        │  │
│  │  analysis/)  │     │ • Top issues                          │  │
│  └──────────────┘     │ • Affected files                      │  │
│                       └───────────────┬──────────────────────┘  │
│                                       │                          │
│                                       ▼                          │
│                       ┌──────────────────────────────────────┐  │
│                       │ mcp__zen__chat(                       │  │
│                       │   prompt="Store mutation analysis...",│  │
│                       │   model="gemini-2.5-flash"            │  │
│                       │ )                                     │  │
│                       └──────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### At Session Start / When Investigating Issues

```
┌─────────────────────────────────────────────────────────────────┐
│  User mentions "stale data" or "mutation" issues                │
│        │                                                         │
│        ▼                                                         │
│  ┌──────────────────────────────────────┐                       │
│  │ mcp__zen__chat(                       │                       │
│  │   prompt="Recall mutation analysis...",│                      │
│  │   model="gemini-2.5-flash"            │                       │
│  │ )                                     │                       │
│  └───────────────┬──────────────────────┘                       │
│                  │                                               │
│                  ▼                                               │
│  ┌──────────────────────────────────────┐                       │
│  │ Returns previous findings:            │                       │
│  │ • Last score: 8.2/10                  │                       │
│  │ • 4 warnings in player mutations     │                       │
│  │ • Missing cache revalidation pattern  │                       │
│  └───────────────┬──────────────────────┘                       │
│                  │                                               │
│                  ▼                                               │
│  ┌──────────────────────────────────────┐                       │
│  │ Claude provides context-aware         │                       │
│  │ suggestions based on known issues     │                       │
│  └──────────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

## Memory Schema

```json
{
  "timestamp": "2024-12-05T14:30:00",
  "overall_score": 8.2,
  "total_mutations": 25,
  "passing_count": 18,
  "warning_count": 5,
  "critical_count": 2,
  "top_issues": [
    {
      "description": "Missing error handling",
      "location": "app/actions/players.ts"
    },
    {
      "description": "No cache revalidation",
      "location": "app/actions/games.ts"
    }
  ],
  "affected_files": [
    "app/actions/players.ts",
    "hooks/useUpdateTeam.ts"
  ],
  "sub_skills_active": ["react-query-mutations"],
  "report_path": ".claude/analysis/mutation-report-2024-12-05.md"
}
```

## Storage Prompt Template

```
Store mutation analysis results for cross-session awareness:

**Analysis Date:** 2024-12-05T14:30:00
**Overall Score:** 8.2/10
**Status:** ⚠️ Needs attention

**Mutation Counts:**
  - Total: 25
  - Passing: 18
  - Warnings: 5
  - Critical: 2

**Top Issues:**
  1. Missing error handling (app/actions/players.ts)
  2. No cache revalidation (app/actions/games.ts)
  3. Query key mismatch (hooks/useUpdateTeam.ts)

**Key Files Needing Attention:**
  - app/actions/players.ts
  - app/actions/games.ts
  - hooks/useUpdateTeam.ts

**Active Sub-Skills:** react-query-mutations

**Full Report:** .claude/analysis/mutation-report-2024-12-05.md
```

## Recall Prompt Template

```
Recall previous mutation analysis results for this project.

What were the findings from the last mutation consistency analysis?
Include:
- Overall score
- Number of issues found
- Top issues that need attention
- Any patterns or recurring problems

If no previous analysis exists, indicate that this would be the first run.
```

## Trend Analysis Prompt Template

```
Analyze mutation consistency trends for this project.

Based on stored analysis results:
1. Has the overall score improved or declined?
2. Are there recurring issues that keep appearing?
3. Which files have the most persistent problems?
4. What patterns emerge in the issues found?

Provide a brief trend summary with recommendations.
```

## Usage in Skill Workflow

### Automatic Storage (After Analysis)

The analyze_mutations.py script should trigger Zen storage:

```python
# After generating report
from zen_memory import parse_report_for_memory, format_for_zen_chat

memory = parse_report_for_memory(report_path)
if memory:
    zen_prompt = format_for_zen_chat(memory)
    # Claude then calls mcp__zen__chat with this prompt
    print(f"\n💾 Store in Zen memory:\n{zen_prompt}")
```

### Recall Trigger (Hook Integration)

The mutation-detector.sh hook can suggest recalling memory:

```bash
# If investigation-related keywords detected
echo "💭 Consider recalling previous analysis:"
echo "   Use Zen MCP to check for known mutation issues"
```

### Manual Recall (Slash Command)

Add to @analyze-mutations command:

```markdown
## Options

- `--recall` : First recall previous findings before new analysis
- `--trends` : Show improvement trends over multiple analyses
```

## Benefits

### 1. Cross-Session Continuity
- Don't lose context between sessions
- Remember which files had issues
- Track what was previously fixed

### 2. Trend Awareness
- See if score is improving over time
- Identify persistently problematic files
- Recognize recurring patterns

### 3. Proactive Suggestions
- When user mentions related topics, recall known issues
- Suggest re-checking previously problematic areas
- Warn about files with history of issues

### 4. Reduced Re-Analysis
- Reference previous findings instead of full re-run
- Quick "what changed?" comparisons
- Avoid redundant full-codebase scans

## Configuration

In project's `.claude/mutation-patterns.yaml`:

```yaml
zen_integration:
  enabled: true
  auto_store: true          # Store after each analysis
  recall_on_keywords: true  # Recall when stale data mentioned
  trend_window: 30          # Days to consider for trends
```
