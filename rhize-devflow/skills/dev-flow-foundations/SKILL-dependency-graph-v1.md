# Dependency Graph & Impact Mapping Skill

> **Status:** Foundation Draft v1
> **Last Updated:** 2024-12-01
> **Dependencies:** TypeScript AST parsing, Git MCP, [TO-DO] Graphiti MCP

---

## Overview

This skill enforces mandatory impact analysis before any implementation begins. It creates a comprehensive dependency graph that tracks not just file imports, but **data flow** through the application - identifying what data types are consumed and produced at each point.

## Trigger Conditions

Activate this skill when:
- User requests a new feature implementation
- User requests modification to existing functionality
- User requests a bug fix that involves code changes
- Keywords: "implement", "add", "create", "modify", "fix", "refactor", "update"

## Core Workflow

### Phase 1: Static Dependency Analysis

```
1. Identify the entry point file(s) for the change
2. Run import/export analysis
3. Generate file dependency tree
4. Extract data type dependencies (see Phase 2)
5. Create IMPACT_MAP.md
6. Present map and get confirmation BEFORE writing code
```

### Phase 2: Data Dependency Extraction

**This is the key enhancement over simple file-based impact mapping.**

For each file in the dependency tree, extract:

```typescript
// Example analysis output for a page component

{
  "file": "app/players/[id]/page.tsx",
  "imports": {
    "functions": [
      {
        "name": "getPlayerById",
        "from": "@/lib/api/players",
        "returnType": "Promise<Player | null>",
        "params": ["id: string"]
      },
      {
        "name": "getPlayerStats",
        "from": "@/lib/api/stats", 
        "returnType": "Promise<PlayerStats[]>",
        "params": ["playerId: string", "seasonId?: string"]
      }
    ],
    "components": [
      {
        "name": "PlayerCard",
        "from": "@/components/players/PlayerCard",
        "props": "PlayerCardProps",
        "requiredData": ["Player"]
      }
    ],
    "types": ["Player", "PlayerStats", "PlayerCardProps"]
  },
  "dataFlow": {
    "fetches": ["Player", "PlayerStats[]"],
    "renders": ["PlayerCard(Player)", "StatsTable(PlayerStats[])"],
    "passes": {
      "PlayerCard": ["player: Player"],
      "StatsTable": ["stats: PlayerStats[]", "playerId: string"]
    }
  }
}
```

### Phase 3: Optimization Insights

Using the data dependency map, identify:

#### Fetch Optimization Opportunities
```markdown
## Fetch Analysis for app/players/[id]/page.tsx

### Current Data Requirements
- Player (single fetch by ID)
- PlayerStats[] (array fetch by playerId)

### Optimization Recommendations
1. **Parallel Fetching:** Both fetches are independent - use Promise.all()
2. **Waterfall Risk:** If PlayerStats depends on Player.id from fetch, 
   consider passing id directly from route params
3. **Overfetching:** Player type has 15 fields, PlayerCard only uses 5
   - Consider: PlayerSummary type for list views
```

#### Query Optimization Insights
```markdown
## Database Query Analysis

### Data Access Pattern
- getPlayerById: Single row lookup (indexed by PK) ✅
- getPlayerStats: Range query by playerId
  - Check: Is playerId indexed in stats table?
  - Check: Are we fetching all seasons when only current needed?

### Suggested Optimizations
- Add composite index on (playerId, seasonId) if filtering by season
- Consider select() to limit fields if full PlayerStats not needed
```

---

## Impact Map Format

Generate `IMPACT_MAP.md` in the working directory:

```markdown
# Impact Map: [Feature/Fix Name]
Generated: [timestamp]

## Change Summary
[Brief description of intended changes]

## Entry Points
- [ ] `app/players/[id]/page.tsx` - Primary modification target

## File Dependencies

### Direct Dependencies (imports from entry points)
| File | Type | Data Types | Modification Needed |
|------|------|------------|---------------------|
| `lib/api/players.ts` | API | `Player` | ⚠️ Yes - add field |
| `components/PlayerCard.tsx` | Component | `PlayerCardProps` | ⚠️ Yes - new prop |
| `types/player.ts` | Types | `Player`, `PlayerCardProps` | ⚠️ Yes - extend type |

### Indirect Dependencies (files that import the above)
| File | Imports | Risk Level |
|------|---------|------------|
| `app/teams/[id]/roster/page.tsx` | `PlayerCard` | 🟡 Medium - uses same component |
| `app/admin/players/page.tsx` | `getPlayerById` | 🟢 Low - different usage pattern |

## Data Flow Impact

### Types Being Modified
```typescript
// Current
interface Player {
  id: string;
  name: string;
  // ... existing fields
}

// Proposed Addition
interface Player {
  // ... existing fields
  newField: string; // <- Adding this
}
```

### Cascade Effects
1. `PlayerCard` - Will receive new field via props ✅
2. `PlayerListItem` - Uses `Player` type, may need UI update ⚠️
3. `getPlayerById` - Return type changes, callers unaffected if typed ✅
4. Supabase query in `lib/api/players.ts` - Must include new field ⚠️

## Test Coverage
- [ ] `__tests__/api/players.test.ts` - Update mock data
- [ ] `__tests__/components/PlayerCard.test.tsx` - Add prop test

## Pre-Implementation Checklist
- [ ] All affected files identified
- [ ] Data type changes mapped
- [ ] Test files identified
- [ ] No circular dependency introduced
- [ ] Confirmed with user before proceeding
```

---

## [TO-DO] Graphiti MCP Integration

### Planned Enhancement
Use Graphiti MCP server to persist dependency graphs in a queryable format.

```python
# Conceptual integration

# Store dependency relationship
graphiti.add_edge(
    source="app/players/[id]/page.tsx",
    target="lib/api/players.ts",
    relationship="imports",
    properties={
        "functions": ["getPlayerById"],
        "types": ["Player"],
        "data_flow": "fetches"
    }
)

# Query for impact analysis
affected = graphiti.query("""
    MATCH (modified)-[:imports|:exports*1..3]-(affected)
    WHERE modified.path = 'lib/api/players.ts'
    RETURN affected.path, affected.type
""")
```

### Comparison: Graph vs Markdown Retrieval

| Aspect | Markdown (Current) | Graphiti (Planned) |
|--------|-------------------|-------------------|
| Query Speed | O(n) file scan | O(1) graph traversal |
| Relationship Depth | Manual tracking | Native multi-hop |
| Update Complexity | Regenerate file | Incremental updates |
| Context Window | Full file loaded | Query results only |
| Offline Use | ✅ Always available | Requires server |
| Setup Complexity | Low | Medium |

**Recommendation:** Start with markdown, migrate to Graphiti when:
- Project exceeds 200+ files
- Dependency queries become frequent (5+/session)
- Multi-hop analysis needed regularly

---

## Implementation Script (AST-based)

```typescript
// scripts/analyze-dependencies.ts
// Run: npx ts-node scripts/analyze-dependencies.ts <entry-file>

import * as ts from 'typescript';
import * as path from 'path';
import * as fs from 'fs';

interface FunctionImport {
  name: string;
  from: string;
  returnType: string | null;
  params: string[];
}

interface DataDependency {
  file: string;
  functions: FunctionImport[];
  types: string[];
  components: string[];
}

function analyzeFile(filePath: string): DataDependency {
  const sourceCode = fs.readFileSync(filePath, 'utf-8');
  const sourceFile = ts.createSourceFile(
    filePath,
    sourceCode,
    ts.ScriptTarget.Latest,
    true
  );

  const result: DataDependency = {
    file: filePath,
    functions: [],
    types: [],
    components: []
  };

  // Walk AST to extract imports and their types
  ts.forEachChild(sourceFile, (node) => {
    if (ts.isImportDeclaration(node)) {
      const moduleSpecifier = node.moduleSpecifier.getText().replace(/['"]/g, '');
      const importClause = node.importClause;
      
      if (importClause?.namedBindings && ts.isNamedImports(importClause.namedBindings)) {
        importClause.namedBindings.elements.forEach((element) => {
          const importName = element.name.getText();
          
          // Heuristic: PascalCase = Component/Type, camelCase = function
          if (/^[A-Z]/.test(importName)) {
            if (importName.endsWith('Props') || importName.endsWith('Type')) {
              result.types.push(importName);
            } else {
              result.components.push(importName);
            }
          } else {
            result.functions.push({
              name: importName,
              from: moduleSpecifier,
              returnType: null, // Requires type resolution
              params: []
            });
          }
        });
      }
    }
  });

  return result;
}

// Entry point
const entryFile = process.argv[2];
if (!entryFile) {
  console.error('Usage: npx ts-node analyze-dependencies.ts <file-path>');
  process.exit(1);
}

const analysis = analyzeFile(entryFile);
console.log(JSON.stringify(analysis, null, 2));
```

---

## Integration with Other Skills

### → Component Registry Skill
After generating impact map, cross-reference with component registry to:
- Verify no duplicate components being created
- Check if existing components can be extended

### → Regression Prevention Skill
Impact map feeds into regression analysis:
- Affected files = required test coverage
- Data type changes = type-checking priority

### ← Skill Refinement Skill
When impact mapping reveals new patterns:
- Document in PATTERNS.md
- Consider creating reusable analysis scripts

---

## Success Metrics

Track these to measure skill effectiveness:

1. **Implementation Completeness Rate**
   - Before skill: % of PRs requiring follow-up commits
   - After skill: Target <10% follow-up rate

2. **Cascade Bug Rate**
   - Changes in file A breaking file B unexpectedly
   - Target: 0 cascade bugs from mapped changes

3. **Time to Impact Analysis**
   - Target: <2 minutes for typical feature
   - Target: <5 minutes for cross-cutting changes

---

## Open Questions

1. Should impact maps be committed to git or treated as ephemeral?
2. How to handle dynamic imports and lazy-loaded components?
3. Integration with Payload CMS field dependencies?
4. Should we track CSS/style dependencies for UI changes?

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2024-12-01 | Initial foundation with data dependency concept |
