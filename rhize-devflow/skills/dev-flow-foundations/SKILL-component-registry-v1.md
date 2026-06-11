# Component & Function Registry Skill

> **Status:** Foundation Draft v1
> **Last Updated:** 2024-12-01
> **Dependencies:** TypeScript compiler API, AST parsing

---

## Overview

A living, auto-generated registry of all reusable components, functions, hooks, and utilities in the codebase. Enhanced beyond simple listings to include **data fetching strategies**, **state management patterns**, and **type compatibility mapping** for intelligent duplicate prevention.

## Trigger Conditions

Activate this skill when:
- User is about to create a new component, function, or hook
- Keywords: "create", "new component", "add function", "write a hook"
- Before any implementation that might duplicate existing code

## Core Concept: Beyond File Listings

Traditional registries list names. This registry tracks **behavior and compatibility**:

```
Traditional: "PlayerCard component exists in /components/players/"
Enhanced: "PlayerCard component exists - accepts Player type, 
          uses client-side rendering, fetches additional data 
          via react-query usePlayerStats hook"
```

---

## Registry Schema

### Component Entry

```typescript
interface ComponentEntry {
  name: string;
  path: string;
  
  // Data Requirements
  props: {
    interface: string;           // "PlayerCardProps"
    requiredTypes: string[];     // ["Player", "TeamSummary"]
    optionalTypes: string[];     // ["PlayerStats"]
  };
  
  // Rendering Strategy
  rendering: {
    strategy: "server" | "client" | "hybrid";
    directive: "'use client'" | "'use server'" | null;
    suspenseBoundary: boolean;
  };
  
  // Data Fetching (if any internal fetching)
  dataFetching: {
    strategy: "none" | "server-fetch" | "react-query" | "swr" | "useEffect";
    hooks: string[];             // ["usePlayerStats", "useTeamData"]
    queries: string[];           // ["getPlayerById"]
  };
  
  // State Management
  stateManagement: {
    localState: string[];        // ["isExpanded", "selectedTab"]
    contextConsumers: string[];  // ["AuthContext", "ThemeContext"]
    externalState: string[];     // ["usePlayerStore (zustand)"]
  };
  
  // Composition
  childComponents: string[];     // Components rendered inside
  parentUsage: string[];         // Files that use this component
  
  // Metadata
  lastModified: string;
  testCoverage: boolean;
  storybook: boolean;
}
```

### Function Entry

```typescript
interface FunctionEntry {
  name: string;
  path: string;
  
  // Type Signature
  signature: {
    params: Array<{name: string; type: string; optional: boolean}>;
    returnType: string;
    async: boolean;
    generic: boolean;
  };
  
  // Categorization
  category: "api" | "utility" | "transformer" | "validator" | "formatter";
  
  // For API functions
  dataSource?: {
    type: "supabase" | "payload" | "external-api" | "computed";
    table?: string;           // For DB queries
    endpoint?: string;        // For API calls
    cachingStrategy?: "none" | "react-query" | "unstable_cache" | "revalidate";
  };
  
  // For transformers/utilities
  inputTypes: string[];       // Types this function accepts
  outputTypes: string[];      // Types this function produces
  
  // Usage tracking
  usedIn: string[];           // Files that import this function
  
  // Metadata
  pure: boolean;              // No side effects
  testCoverage: boolean;
}
```

### Hook Entry

```typescript
interface HookEntry {
  name: string;
  path: string;
  
  // Type Signature
  params: Array<{name: string; type: string}>;
  returns: {
    type: string;
    destructured: string[];   // ["data", "isLoading", "error"]
  };
  
  // Behavior
  pattern: "data-fetching" | "state-management" | "side-effect" | "utility";
  
  // For data-fetching hooks
  fetching?: {
    queryKey: string;
    queryFn: string;          // Function it wraps
    staleTime?: number;
    cacheTime?: number;
  };
  
  // Dependencies
  internalHooks: string[];    // Other hooks used inside
  
  // Usage
  usedIn: string[];
}
```

---

## Registry File Format

### COMPONENT_REGISTRY.md (Human-readable summary)

```markdown
# Component & Function Registry
> Auto-generated: [timestamp]
> Total: 45 components | 78 functions | 23 hooks

## Quick Lookup by Data Type

### Components accepting `Player`
| Component | Props | Rendering | Data Fetching |
|-----------|-------|-----------|---------------|
| PlayerCard | PlayerCardProps | client | react-query |
| PlayerListItem | PlayerListItemProps | server | none |
| PlayerAvatar | {player: Player} | server | none |

### Functions returning `Player`
| Function | Params | Async | Source |
|----------|--------|-------|--------|
| getPlayerById | (id: string) | ✅ | supabase.players |
| getPlayerBySlug | (slug: string) | ✅ | supabase.players |
| transformPlayerData | (raw: RawPlayer) | ❌ | computed |

### Hooks for `Player` data
| Hook | Returns | Cache Strategy |
|------|---------|----------------|
| usePlayer | {data: Player, ...} | react-query (5min) |
| usePlayerMutation | {mutate, ...} | react-query |

---

## By Category

### UI Components

#### Layout Components
- `PageWrapper` - server, accepts children
- `DashboardShell` - client, uses AuthContext
- `Sidebar` - client, zustand navigation state

#### Player Components  
- `PlayerCard` - client, react-query fetching
- `PlayerListItem` - server, no internal fetching
- `PlayerStats` - client, usePlayerStats hook

[... continues by category ...]

### API Functions (lib/api/)

#### Player API
- `getPlayerById(id)` → `Player | null` - supabase
- `getPlayersByTeam(teamId)` → `Player[]` - supabase
- `createPlayer(data)` → `Player` - supabase + revalidation

[... continues ...]

### Hooks (hooks/)

#### Data Fetching Hooks
- `usePlayer(id)` - wraps getPlayerById, 5min cache
- `useTeam(id)` - wraps getTeamById, 5min cache
- `usePlayers(filters)` - wraps getPlayers, 1min cache

#### State Hooks
- `useLocalStorage(key)` - generic localStorage sync
- `useDebounce(value, delay)` - debounced value

[... continues ...]
```

### component-registry.json (Machine-readable)

```json
{
  "generated": "2024-12-01T10:30:00Z",
  "components": {
    "PlayerCard": {
      "path": "components/players/PlayerCard.tsx",
      "props": {
        "interface": "PlayerCardProps",
        "requiredTypes": ["Player"],
        "optionalTypes": ["TeamSummary"]
      },
      "rendering": {
        "strategy": "client",
        "directive": "'use client'"
      },
      "dataFetching": {
        "strategy": "react-query",
        "hooks": ["usePlayerStats"]
      }
    }
  },
  "functions": {},
  "hooks": {},
  "typeIndex": {
    "Player": {
      "acceptedBy": ["PlayerCard", "PlayerListItem", "getPlayerById"],
      "returnedBy": ["getPlayerById", "usePlayer"],
      "transformedBy": ["transformPlayerData"]
    }
  }
}
```

---

## Duplicate Prevention System

### Type-Based Matching

When user requests: "Create a function to fetch player data"

```
1. Parse intent: function that returns Player-like data
2. Query registry for functions with:
   - returnType containing "Player"
   - category: "api"
   
3. Present matches:
   "Found 3 existing functions that return Player data:
   
   - getPlayerById(id: string) → Player | null
     Path: lib/api/players.ts
     Use when: fetching single player by ID
   
   - getPlayerBySlug(slug: string) → Player | null  
     Path: lib/api/players.ts
     Use when: fetching by URL-friendly slug
   
   - getPlayersByTeam(teamId: string) → Player[]
     Path: lib/api/players.ts
     Use when: fetching all players for a team
   
   Do any of these meet your needs, or do you need different functionality?"
```

### Prop Compatibility Matching

When user requests: "Create a component to display player info"

```
1. Parse intent: component accepting Player type
2. Query registry for components where:
   - props.requiredTypes includes "Player"
   
3. Present matches with compatibility analysis:
   "Found 3 components that accept Player data:
   
   - PlayerCard (full detail view)
     Props: player: Player, showStats?: boolean
     Rendering: client-side with react-query
     Best for: detailed player profiles
   
   - PlayerListItem (compact list view)
     Props: player: Player, onClick?: () => void
     Rendering: server-side, no fetching
     Best for: lists and search results
   
   - PlayerAvatar (minimal)
     Props: player: Pick<Player, 'name' | 'imageUrl'>
     Rendering: server-side
     Best for: avatars, mentions, tags
   
   Which matches your use case? Or describe what's different about your needs."
```

### Return Type → Prop Type Matching

For data flow validation:

```typescript
// Automatic compatibility check
function validateDataFlow(
  sourceFunction: string, 
  targetComponent: string
): CompatibilityResult {
  const fn = registry.functions[sourceFunction];
  const comp = registry.components[targetComponent];
  
  const returnType = fn.signature.returnType;  // "Player | null"
  const requiredProps = comp.props.requiredTypes;  // ["Player"]
  
  // Check if return type satisfies prop requirements
  // Account for: Promise unwrapping, null handling, array vs single
  
  return {
    compatible: true,
    warnings: ["Function returns Player | null, component expects Player - add null check"],
    suggestions: ["Use: player && <PlayerCard player={player} />"]
  };
}
```

---

## Data Fetching Strategy Tracking

### Server vs Client Classification

```typescript
// Analysis rules for classifying components

function classifyRenderingStrategy(filePath: string): RenderingStrategy {
  const content = readFile(filePath);
  
  // Explicit directives
  if (content.includes("'use client'")) return { strategy: "client", directive: "'use client'" };
  if (content.includes("'use server'")) return { strategy: "server", directive: "'use server'" };
  
  // Heuristic detection
  const clientIndicators = [
    /useState\s*\(/,
    /useEffect\s*\(/,
    /useQuery\s*\(/,
    /onClick\s*=/,
    /onChange\s*=/,
    /useRouter\s*\(\)/,  // next/navigation client hook
  ];
  
  const serverIndicators = [
    /async\s+function\s+\w+\s*\([^)]*\)\s*{/,  // async component
    /await\s+fetch/,
    /cookies\(\)/,
    /headers\(\)/,
  ];
  
  const clientScore = clientIndicators.filter(r => r.test(content)).length;
  const serverScore = serverIndicators.filter(r => r.test(content)).length;
  
  if (clientScore > serverScore) return { strategy: "client", directive: null };
  if (serverScore > clientScore) return { strategy: "server", directive: null };
  return { strategy: "hybrid", directive: null };
}
```

### State Management Classification

```typescript
function classifyStateManagement(filePath: string): StateManagement {
  const content = readFile(filePath);
  const result: StateManagement = {
    localState: [],
    contextConsumers: [],
    externalState: []
  };
  
  // Extract useState declarations
  const useStateMatches = content.matchAll(/const\s+\[(\w+),\s*set\w+\]\s*=\s*useState/g);
  for (const match of useStateMatches) {
    result.localState.push(match[1]);
  }
  
  // Extract useContext
  const contextMatches = content.matchAll(/useContext\((\w+)\)/g);
  for (const match of contextMatches) {
    result.contextConsumers.push(match[1]);
  }
  
  // Extract zustand/redux hooks
  const storeMatches = content.matchAll(/use(\w+Store)\(\)/g);
  for (const match of storeMatches) {
    result.externalState.push(match[1]);
  }
  
  return result;
}
```

---

## Generation Script

```typescript
// scripts/generate-registry.ts
// Run: npx ts-node scripts/generate-registry.ts

import * as ts from 'typescript';
import * as fs from 'fs';
import * as path from 'path';
import glob from 'fast-glob';

interface Registry {
  generated: string;
  components: Record<string, ComponentEntry>;
  functions: Record<string, FunctionEntry>;
  hooks: Record<string, HookEntry>;
  typeIndex: Record<string, TypeUsage>;
}

async function generateRegistry(rootDir: string): Promise<Registry> {
  const registry: Registry = {
    generated: new Date().toISOString(),
    components: {},
    functions: {},
    hooks: {},
    typeIndex: {}
  };

  // Find all TypeScript/TSX files
  const files = await glob([
    `${rootDir}/components/**/*.tsx`,
    `${rootDir}/lib/**/*.ts`,
    `${rootDir}/hooks/**/*.ts`,
    `${rootDir}/app/**/page.tsx`,
  ], { ignore: ['**/*.test.*', '**/*.spec.*', '**/node_modules/**'] });

  for (const file of files) {
    await analyzeFile(file, registry);
  }

  // Build type index
  buildTypeIndex(registry);

  return registry;
}

async function analyzeFile(filePath: string, registry: Registry) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const sourceFile = ts.createSourceFile(
    filePath,
    content,
    ts.ScriptTarget.Latest,
    true,
    filePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  );

  // Determine file type and analyze accordingly
  if (filePath.includes('/components/')) {
    analyzeComponent(sourceFile, filePath, registry);
  } else if (filePath.includes('/hooks/')) {
    analyzeHook(sourceFile, filePath, registry);
  } else if (filePath.includes('/lib/')) {
    analyzeFunctions(sourceFile, filePath, registry);
  }
}

function buildTypeIndex(registry: Registry) {
  // Index which types are accepted/returned by what
  // ... implementation
}

// Entry point
const rootDir = process.argv[2] || '.';
generateRegistry(rootDir).then(registry => {
  // Write JSON
  fs.writeFileSync(
    'component-registry.json',
    JSON.stringify(registry, null, 2)
  );
  
  // Generate markdown
  const markdown = generateMarkdown(registry);
  fs.writeFileSync('COMPONENT_REGISTRY.md', markdown);
  
  console.log(`Registry generated: ${Object.keys(registry.components).length} components, ${Object.keys(registry.functions).length} functions, ${Object.keys(registry.hooks).length} hooks`);
});
```

---

## Integration Points

### → Dependency Graph Skill
Registry provides data for impact analysis:
- "What components use this type?"
- "What functions return this type?"

### → Skill Refinement Skill
When new patterns are identified:
- Add to registry with pattern classification
- Flag as "recommended pattern" in registry

### → Anti-Pattern Detection Skill
Registry serves as source of truth:
- "Is this function in deprecated list?"
- "Does this pattern match anti-pattern signatures?"

---

## Diff-Based Prop Matching Enhancement

```typescript
// Enhanced duplicate detection using type diffing

import { diff } from 'deep-diff';

function findCompatibleExisting(
  desiredReturnType: string,
  desiredParams: string[]
): FunctionMatch[] {
  const matches: FunctionMatch[] = [];
  
  for (const [name, fn] of Object.entries(registry.functions)) {
    // Parse types for structural comparison
    const existingReturn = parseType(fn.signature.returnType);
    const desiredReturn = parseType(desiredReturnType);
    
    const typeDiff = diff(existingReturn, desiredReturn);
    
    if (!typeDiff) {
      // Exact match
      matches.push({ name, fn, matchType: 'exact', diff: null });
    } else if (isSubset(existingReturn, desiredReturn)) {
      // Existing returns MORE than needed - can use with destructuring
      matches.push({ name, fn, matchType: 'superset', diff: typeDiff });
    } else if (isSubset(desiredReturn, existingReturn)) {
      // Existing returns LESS than needed - might extend
      matches.push({ name, fn, matchType: 'subset', diff: typeDiff });
    }
  }
  
  return matches.sort((a, b) => matchScore(b) - matchScore(a));
}

// Example output:
// "You want a function returning { id, name, email, avatar }
//  
//  Exact match: None
//  
//  Superset (returns more than you need):
//  - getFullPlayer() returns { id, name, email, avatar, stats, team, ... }
//    → Use: const { id, name, email, avatar } = await getFullPlayer(id)
//  
//  Subset (returns less - could extend):
//  - getPlayerSummary() returns { id, name, avatar }
//    → Missing: email
//    → Consider: extend getPlayerSummary or use getFullPlayer"
```

---

## Success Metrics

1. **Duplicate Code Reduction**
   - Track: New utility files created vs existing ones discovered
   - Target: 50% reduction in new utility creation

2. **Component Reuse Rate**
   - Track: Times existing component suggested and used
   - Target: 80% reuse for common patterns

3. **Registry Accuracy**
   - Track: False negatives (existing code not found)
   - Target: <5% miss rate

---

## Open Questions

1. How to handle components with many variants (via props)?
2. Should we track CSS-in-JS / Tailwind patterns?
3. Integration with Storybook for visual component discovery?
4. How to handle third-party component wrappers?

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2024-12-01 | Initial foundation with data fetching tracking |
