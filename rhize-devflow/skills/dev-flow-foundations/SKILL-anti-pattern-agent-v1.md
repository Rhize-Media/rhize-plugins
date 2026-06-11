# Anti-Pattern Detection Agent Skill

> **Status:** Foundation Draft v1
> **Last Updated:** 2024-12-01
> **Dependencies:** TypeScript/ESLint awareness, DEPRECATED.md, PATTERNS.md

---

## Overview

A specialized agent that actively scans proposed code and implementation plans for anti-patterns, deprecated approaches, and violations of project conventions. Unlike passive documentation, this agent **intervenes** when problematic code is about to be written.

## Core Philosophy

> "Prevent anti-patterns at write-time, not review-time."

The cost of catching an anti-pattern:
- At write-time: 30 seconds (immediate redirect)
- At PR review: 30 minutes (rework required)  
- In production: 3+ hours (debugging + hotfix)

---

## Trigger Conditions

### Automatic Activation
The agent activates whenever Claude is about to:
- Write new code (function, component, hook)
- Modify existing code
- Suggest an implementation approach

### Scan Targets
- Proposed code in Claude's response
- Implementation plans described in natural language
- File paths and import statements
- Function/variable names

---

## Part 1: Deprecated Word Detection

### Deprecated Triggers Configuration

```typescript
// .claude/config/deprecated-triggers.ts

export const DEPRECATED_TRIGGERS = {
  // ============================================
  // FUNCTIONS - Direct name matches
  // ============================================
  functions: {
    // Format: 'deprecated': { replacement: 'new', reason: 'why' }
    
    // Legacy API functions
    'fetchPlayer': { 
      replacement: 'getPlayerById', 
      reason: 'Old naming convention' 
    },
    'fetchTeam': { 
      replacement: 'getTeamById', 
      reason: 'Old naming convention' 
    },
    'fetchPlayers': { 
      replacement: 'getPlayers', 
      reason: 'Old naming convention' 
    },
    
    // Replaced utilities
    'formatDate': { 
      replacement: 'dayjs.format()', 
      reason: 'Use dayjs directly for consistency' 
    },
    'parseDate': { 
      replacement: 'dayjs()', 
      reason: 'Use dayjs directly for consistency' 
    },
    
    // Deprecated hooks
    'usePlayerData': { 
      replacement: 'usePlayer', 
      reason: 'Inconsistent hook naming' 
    },
    'useFetch': { 
      replacement: 'useQuery from react-query', 
      reason: 'Custom fetch hook deprecated' 
    },
  },

  // ============================================
  // IMPORTS - Package/module matches
  // ============================================
  imports: {
    'moment': { 
      replacement: 'dayjs', 
      reason: 'Bundle size - dayjs is 2KB vs 67KB' 
    },
    'axios': { 
      replacement: 'fetch or ky', 
      reason: 'Native fetch preferred, ky for convenience' 
    },
    'lodash': { 
      replacement: 'lodash-es or native methods', 
      reason: 'Tree-shaking - use lodash-es or native' 
    },
    '@/lib/api/legacy': { 
      replacement: '@/lib/api/*', 
      reason: 'Legacy API module scheduled for removal' 
    },
    '@/utils/old': { 
      replacement: '@/lib/utils', 
      reason: 'Consolidated utility location' 
    },
  },

  // ============================================
  // PATTERNS - Regex-based detection
  // ============================================
  patterns: {
    // useEffect for data fetching
    'useEffect-fetch': {
      regex: /useEffect\s*\(\s*(?:async\s*)?\(\)\s*=>\s*\{[^}]*(?:fetch|axios|api\.)/,
      replacement: 'useQuery from react-query',
      reason: 'React Query provides caching, loading states, error handling',
      example: {
        bad: `useEffect(() => { 
  fetch('/api/player').then(r => r.json()).then(setPlayer);
}, []);`,
        good: `const { data: player } = useQuery({
  queryKey: ['player', id],
  queryFn: () => getPlayerById(id),
});`
      }
    },
    
    // any type usage
    'any-type': {
      regex: /:\s*any\b/,
      replacement: 'Proper type or unknown',
      reason: 'Type safety - any defeats TypeScript benefits',
      example: {
        bad: `function process(data: any) { ... }`,
        good: `function process(data: PlayerData) { ... }
// or if truly unknown:
function process(data: unknown) { ... }`
      }
    },
    
    // Type assertion with 'as'
    'type-assertion': {
      regex: /\bas\s+(?!const\b)\w+/,
      replacement: 'Type guard or proper typing',
      reason: 'Type assertions bypass safety checks',
      example: {
        bad: `const player = data as Player;`,
        good: `if (isPlayer(data)) { const player = data; }`
      }
    },
    
    // Inline styles
    'inline-styles': {
      regex: /style=\{\{/,
      replacement: 'Tailwind classes',
      reason: 'Consistency - use Tailwind for all styling',
      example: {
        bad: `<div style={{ marginTop: '10px' }}>`,
        good: `<div className="mt-2.5">`
      }
    },
    
    // .then() chains
    'then-chains': {
      regex: /\.then\s*\([^)]*\)\s*\.then/,
      replacement: 'async/await',
      reason: 'Readability - async/await is clearer',
      example: {
        bad: `fetch(url).then(r => r.json()).then(data => ...)`,
        good: `const response = await fetch(url);
const data = await response.json();`
      }
    },
    
    // Direct Supabase in components
    'direct-supabase': {
      regex: /import.*from\s+['"]@supabase\/.*['"]/,
      replacement: 'Functions from lib/api/',
      reason: 'All DB access should go through API layer',
      context: 'components/',
      example: {
        bad: `import { supabase } from '@supabase/client';
// in component:
const { data } = await supabase.from('players').select();`,
        good: `import { getPlayers } from '@/lib/api/players';
// in component:
const players = await getPlayers();`
      }
    },
    
    // Props drilling indicator
    'props-drilling': {
      regex: /(\w+)=\{\1\}/g,
      minMatches: 4, // Only flag if 4+ props passed through
      replacement: 'Context or composition',
      reason: 'Prop drilling >3 levels harms maintainability',
    },
  },

  // ============================================
  // FILES - Path pattern matches
  // ============================================
  files: {
    '/old/': { 
      replacement: 'Appropriate current location', 
      reason: 'Legacy directory scheduled for removal' 
    },
    '.legacy.': { 
      replacement: 'Remove .legacy from filename', 
      reason: 'Legacy file marker - should be migrated' 
    },
    '/deprecated/': { 
      replacement: 'N/A - should not import', 
      reason: 'Deprecated module directory' 
    },
  },

  // ============================================
  // FRAMEWORK SYNTAX - Version-specific
  // ============================================
  frameworkSyntax: {
    'getServerSideProps': {
      replacement: 'Server Components with direct fetch',
      reason: 'Next.js 13+ App Router pattern',
      framework: 'next.js',
      minVersion: '13.0.0'
    },
    'getStaticProps': {
      replacement: 'generateStaticParams + fetch in component',
      reason: 'Next.js 13+ App Router pattern',
      framework: 'next.js',
      minVersion: '13.0.0'
    },
    'getInitialProps': {
      replacement: 'Server Components',
      reason: 'Deprecated in favor of Server Components',
      framework: 'next.js',
      minVersion: '13.0.0'
    },
  }
};
```

---

## Part 2: Detection Algorithm

### Scan Process

```typescript
// Conceptual implementation of anti-pattern scanner

interface AntiPatternResult {
  type: 'function' | 'import' | 'pattern' | 'file' | 'framework';
  trigger: string;
  location: string;
  replacement: string;
  reason: string;
  severity: 'error' | 'warning' | 'info';
  example?: { bad: string; good: string };
}

function scanForAntiPatterns(code: string, filePath: string): AntiPatternResult[] {
  const results: AntiPatternResult[] = [];
  
  // 1. Scan for deprecated function names
  for (const [name, config] of Object.entries(DEPRECATED_TRIGGERS.functions)) {
    const regex = new RegExp(`\\b${name}\\s*\\(`, 'g');
    if (regex.test(code)) {
      results.push({
        type: 'function',
        trigger: name,
        location: findLocation(code, regex),
        replacement: config.replacement,
        reason: config.reason,
        severity: 'error'
      });
    }
  }
  
  // 2. Scan for deprecated imports
  for (const [pkg, config] of Object.entries(DEPRECATED_TRIGGERS.imports)) {
    const importRegex = new RegExp(`from\\s+['"]${pkg}['"]`, 'g');
    if (importRegex.test(code)) {
      results.push({
        type: 'import',
        trigger: pkg,
        location: 'import statement',
        replacement: config.replacement,
        reason: config.reason,
        severity: 'error'
      });
    }
  }
  
  // 3. Scan for anti-patterns
  for (const [name, config] of Object.entries(DEPRECATED_TRIGGERS.patterns)) {
    if (config.context && !filePath.includes(config.context)) {
      continue; // Pattern only applies in certain contexts
    }
    
    const matches = code.match(config.regex);
    if (matches) {
      if (config.minMatches && matches.length < config.minMatches) {
        continue; // Below threshold
      }
      
      results.push({
        type: 'pattern',
        trigger: name,
        location: findLocation(code, config.regex),
        replacement: config.replacement,
        reason: config.reason,
        severity: 'warning',
        example: config.example
      });
    }
  }
  
  // 4. Scan for deprecated file patterns
  for (const [pattern, config] of Object.entries(DEPRECATED_TRIGGERS.files)) {
    if (filePath.includes(pattern)) {
      results.push({
        type: 'file',
        trigger: pattern,
        location: filePath,
        replacement: config.replacement,
        reason: config.reason,
        severity: 'warning'
      });
    }
  }
  
  return results;
}
```

---

## Part 3: Agent Behavior

### Intervention Format

When anti-pattern detected, Claude should respond:

```markdown
⚠️ **ANTI-PATTERN DETECTED**

**Found:** [trigger name/pattern]
**Location:** [where in the proposed code]
**Severity:** [error/warning/info]

**Why this is problematic:**
[Clear explanation of the issue]

**Current approach (problematic):**
```typescript
[The problematic code]
```

**Recommended approach:**
```typescript
[The correct implementation]
```

**Documentation:** See DEPRECATED.md > [section] OR PATTERNS.md > [section]

---

Would you like me to implement this using the recommended pattern instead?
```

### Severity Levels

```markdown
## Severity Classification

### ERROR (Block Implementation)
- Deprecated functions that will break
- Security vulnerabilities
- Type safety violations (any type)
- Direct database access from components

### WARNING (Strong Recommendation)
- Suboptimal patterns (useEffect for fetching)
- Deprecated but working code
- Prop drilling
- Inline styles

### INFO (Suggestion)
- Newer syntax available
- Minor style inconsistencies
- Optimization opportunities
```

### Non-Blocking Mode

For rapid prototyping, allow override:

```markdown
## Override Protocol

If user explicitly requests:
- "Just use [deprecated pattern] for now"
- "I know, but let's prototype first"
- "Skip anti-pattern check"

Claude should:
1. Acknowledge the override
2. Add TODO comment in code: `// TODO: Migrate from [deprecated] to [replacement]`
3. Log to technical debt tracker if available
4. Proceed with implementation

Example response:
"Acknowledged - proceeding with [deprecated pattern] for prototyping. 
I've added a TODO comment. Remember to migrate to [replacement] before production."
```

---

## Part 4: Project Context Integration

### Project-Specific Rules

```markdown
## VBA LMS App Specific Rules

### Architecture Rules
1. **API Layer Separation**
   - All Supabase calls MUST go through `lib/api/`
   - Direct `supabase.from()` in components = ERROR
   - Payload CMS calls through typed collections only

2. **State Management**
   - Server state: react-query (useQuery/useMutation)
   - Form state: react-hook-form + zod
   - URL state: nuqs or searchParams
   - UI state only: useState

3. **Component Architecture**
   - Default to Server Components
   - 'use client' only when necessary
   - No prop drilling past 2 levels

### Naming Conventions
- API functions: `get*`, `create*`, `update*`, `delete*`
- Hooks: `use*` (camelCase, no redundant suffixes)
- Components: PascalCase matching file name
- Types: PascalCase, suffix with purpose (e.g., `PlayerFormData`)

### File Organization
- Components: `components/[domain]/[ComponentName].tsx`
- API: `lib/api/[domain].ts`
- Types: `types/[domain].ts` (shared) or colocated
- Hooks: `hooks/[domain]/use[Name].ts`
```

### Dynamic Rule Loading

```markdown
## Rule Sources (Priority Order)

1. **DEPRECATED.md** - Project deprecations
2. **PATTERNS.md** - Project patterns (inverse = anti-pattern)
3. **deprecated-triggers.ts** - Codified detection rules
4. **ESLint config** - Linting rules (for awareness)
5. **Framework docs** - Latest syntax (auto-update awareness)

## Keeping Rules Current

### On Package Update
When major dependency updates:
- Check for deprecated APIs
- Update deprecated-triggers.ts
- Add migration notes to DEPRECATED.md

### On Pattern Discovery
When new anti-pattern identified:
- Add to DEPRECATED.md
- Add trigger to deprecated-triggers.ts
- Link to Skill Refinement meta-skill
```

---

## Part 5: Framework/Package Awareness

### Auto-Update Awareness

```markdown
## Framework Syntax Tracking

The agent should be aware of deprecated syntax for:

### Next.js (Current: 14.x)
- ❌ `getServerSideProps` → ✅ Server Components
- ❌ `getStaticProps` → ✅ `generateStaticParams`
- ❌ `pages/` router → ✅ `app/` router
- ❌ `next/image` `layout` prop → ✅ `fill` prop

### React (Current: 18.x)
- ❌ Class components → ✅ Function components
- ❌ `componentDidMount` → ✅ `useEffect`
- ❌ `UNSAFE_*` lifecycle methods → ✅ Hooks

### React Query (Current: 5.x)
- ❌ `useQuery(key, fn)` → ✅ `useQuery({ queryKey, queryFn })`
- ❌ `cacheTime` → ✅ `gcTime`
- ❌ `isLoading` for mutations → ✅ `isPending`

### Tailwind (Current: 3.x)
- ❌ `@apply` overuse → ✅ Direct utility classes
- ❌ Custom CSS → ✅ Tailwind utilities

### TypeScript (Current: 5.x)
- ❌ `enum` → ✅ `const` objects or union types
- ❌ `namespace` → ✅ ES modules
```

### Update Detection Prompt

```markdown
## When User Mentions Package Updates

If user says: "I updated [package] to [version]"

Claude should:
1. Note the update
2. Offer to check for deprecated patterns:
   "With [package] [version], some patterns may have changed.
    Would you like me to scan for deprecated usage?"
3. If yes, focus scan on that package's patterns
4. Suggest updating DEPRECATED.md and deprecated-triggers.ts
```

---

## Integration Points

### → Component Registry Skill
Flag deprecated components in registry:
```json
{
  "PlayerCard": {
    "deprecated": false
  },
  "OldPlayerCard": {
    "deprecated": true,
    "replacement": "PlayerCard",
    "deprecatedSince": "2024-11-01"
  }
}
```

### → Regression Prevention Skill
Anti-pattern introduction should trigger:
- Additional review in RCA
- Pattern education in post-fix documentation

### → Skill Refinement Skill
When anti-pattern frequently caught:
- Consider adding linting rule
- Update team documentation
- Add to onboarding materials

---

## Metrics

1. **Detection Rate**
   - Target: 95% of anti-patterns caught at write-time
   - Measure: Anti-patterns found in PR review that weren't flagged

2. **False Positive Rate**
   - Target: <10% false positives
   - Measure: Times user overrides with valid reason

3. **Rule Currency**
   - Target: Rules updated within 1 week of package updates
   - Measure: Age of deprecated-triggers.ts entries

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────┐
│              ANTI-PATTERN DETECTION AGENT                   │
├─────────────────────────────────────────────────────────────┤
│  SCANS FOR:                                                 │
│  • Deprecated functions (fetchPlayer → getPlayerById)       │
│  • Banned imports (moment → dayjs)                          │
│  • Code patterns (useEffect+fetch → react-query)           │
│  • File paths (/old/, .legacy.)                            │
│  • Framework syntax (getServerSideProps → Server Component)│
├─────────────────────────────────────────────────────────────┤
│  SEVERITY:                                                  │
│  🔴 ERROR: Block and require fix                           │
│  🟡 WARNING: Strong recommendation to fix                   │
│  🔵 INFO: Suggestion for improvement                        │
├─────────────────────────────────────────────────────────────┤
│  SOURCES:                                                   │
│  1. DEPRECATED.md                                           │
│  2. deprecated-triggers.ts                                  │
│  3. PATTERNS.md (inverse)                                   │
│  4. Framework/package changelogs                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Open Questions

1. Should anti-pattern detection be synchronous (block) or async (report)?
2. How to handle legitimate exceptions (e.g., `any` for third-party lib compat)?
3. Integration with IDE/ESLint for real-time detection?
4. Automated deprecated-triggers.ts updates from package changelogs?

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2024-12-01 | Initial foundation with trigger system |
