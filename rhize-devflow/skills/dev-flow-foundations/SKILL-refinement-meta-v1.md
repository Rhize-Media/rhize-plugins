# Skill Refinement Meta-Skill

> **Status:** Foundation Draft v1
> **Last Updated:** 2024-12-01
> **Dependencies:** All other skills, Pattern observation system

---

## Overview

A "meta-skill" that creates and refines other skills. This skill captures the **insight → skill** workflow, enabling continuous improvement of the development process by:

1. Detecting successful patterns during development
2. Recording anti-patterns and deprecations
3. Converting observations into reusable skill content
4. Maintaining living documentation

## Core Philosophy

> "Every debugging session that takes more than 10 minutes should result in either a skill update or a pattern documentation."

---

## Part 1: Insight → Skill Workflow

### Trigger Conditions

Activate insight capture when:
- A complex problem is solved after investigation
- A new pattern is discovered that improves code quality
- An anti-pattern is identified and corrected
- A workaround is needed for framework/library limitations
- Keywords: "that worked", "figured it out", "the solution was", "remember to", "always do", "never do"

### Workflow Phases

```
Phase 1: OBSERVE
↓ Problem encountered, solution discovered
Phase 2: CAPTURE  
↓ Document the pattern/anti-pattern
Phase 3: VALIDATE
↓ Confirm pattern works across contexts
Phase 4: CODIFY
↓ Add to appropriate skill or create new one
Phase 5: INTEGRATE
↓ Update registry, architecture docs, deprecation lists
```

### Insight Capture Template

When a significant insight is discovered, generate:

```markdown
# Insight Capture: [Brief Title]
Captured: [timestamp]
Session Context: [what we were working on]

## The Problem
[What went wrong or what was unclear]

## The Discovery  
[What we learned / what fixed it]

## Root Cause
[Why this happened - not just symptoms]

## Pattern Classification
- [ ] Data Fetching Pattern
- [ ] State Management Pattern  
- [ ] Error Handling Pattern
- [ ] Performance Pattern
- [ ] Type Safety Pattern
- [ ] API Integration Pattern
- [ ] Component Architecture Pattern
- [ ] Testing Pattern
- [ ] Other: _______________

## Anti-Pattern Identified?
- [ ] Yes - add to deprecated list
- [ ] No - this is a positive pattern

## Skill Integration
Target skill: [which skill should this enhance]
Section: [where in the skill]

## Code Example
```typescript
// Before (problematic)
...

// After (correct)
...
```

## Validation Checklist
- [ ] Pattern works in similar contexts
- [ ] No unintended side effects identified
- [ ] Compatible with existing patterns
- [ ] Doesn't contradict other skills

## Action Items
- [ ] Update [skill name] with this pattern
- [ ] Add to PATTERNS.md
- [ ] Update COMPONENT_REGISTRY.md if applicable
- [ ] Add deprecated item to DEPRECATED.md if applicable
```

---

## Part 2: Pattern Detection System

### Pattern Categories

#### 1. Data Fetching Patterns

```markdown
## Data Fetching Pattern Registry

### Server Component Fetching (Recommended)
**When:** Data needed at render time, SEO important, no user interaction
**Implementation:**
```typescript
// app/players/[id]/page.tsx
async function PlayerPage({ params }: { params: { id: string } }) {
  const player = await getPlayerById(params.id); // Direct fetch
  return <PlayerView player={player} />;
}
```
**Benefits:** No loading states, better SEO, simpler code

### React Query Client Fetching (Recommended)
**When:** Data updates frequently, user interactions trigger refetch, need caching
**Implementation:**
```typescript
// components/PlayerStats.tsx
'use client';
function PlayerStats({ playerId }: { playerId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['player-stats', playerId],
    queryFn: () => getPlayerStats(playerId),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
  // ...
}
```
**Benefits:** Automatic caching, background refetch, optimistic updates

### Parallel Server Fetching (Optimization)
**When:** Multiple independent data requirements
**Implementation:**
```typescript
async function TeamPage({ params }: { params: { id: string } }) {
  // ✅ Parallel - both start immediately
  const [team, players, schedule] = await Promise.all([
    getTeamById(params.id),
    getPlayersByTeam(params.id),
    getTeamSchedule(params.id),
  ]);
  // ...
}
```
**Anti-pattern:** Sequential awaits for independent data

### [TO ADD MORE PATTERNS AS DISCOVERED]
```

#### 2. State Management Patterns

```markdown
## State Management Pattern Registry

### Form State with React Hook Form (Recommended)
**When:** Complex forms, validation needed
**Implementation:**
```typescript
const { register, handleSubmit, formState } = useForm<PlayerFormData>({
  resolver: zodResolver(playerSchema),
  defaultValues: player,
});
```

### Server State with React Query (Recommended)  
**When:** Caching server data, synchronization needed
**Implementation:** [see data fetching patterns]

### URL State for Filters (Recommended)
**When:** Shareable state, pagination, filters
**Implementation:**
```typescript
// Use nuqs or next/navigation searchParams
const [sort, setSort] = useQueryState('sort', { defaultValue: 'name' });
```

### Local UI State with useState (Appropriate Use)
**When:** Ephemeral UI state only
**Examples:** isOpen, isExpanded, activeTab
**Anti-pattern:** Using useState for data that should be URL state or server state
```

#### 3. Error Handling Patterns

```markdown
## Error Handling Pattern Registry

### API Error Boundaries
**When:** Page-level error handling
**Implementation:** error.tsx in app router

### Form Error Handling  
**When:** User input validation
**Pattern:** Zod schemas + React Hook Form

### Sentry Error Capture
**When:** Unexpected runtime errors
**Pattern:**
```typescript
try {
  // risky operation
} catch (error) {
  Sentry.captureException(error, {
    tags: { feature: 'player-registration' },
    extra: { playerId, formData }
  });
  throw error; // Re-throw for error boundary
}
```

### Toast Notifications for User Errors
**When:** User-recoverable errors
**Pattern:** sonner toast with actionable message
```

### Pattern Recording Workflow

During feature implementation, prompt for pattern documentation:

```markdown
## Pre-Implementation Pattern Check

Before implementing [feature], confirm patterns for:

### Data Fetching
- [ ] Server or client fetching? [Document decision]
- [ ] Caching strategy? [Document TTL and invalidation]
- [ ] Error handling approach? [Document]

### State Management  
- [ ] What state is needed? [List]
- [ ] Where should each piece live? [Document location per piece]

### Component Architecture
- [ ] Server or client component? [Document with reasoning]
- [ ] Existing components to reuse? [List from registry]
- [ ] New patterns introduced? [Document for later capture]
```

---

## Part 3: Anti-Pattern Detection

### Deprecated Items List

Maintain a `DEPRECATED.md` file:

```markdown
# Deprecated Patterns & Items
> This file triggers anti-pattern detection. Items listed here should NOT be used.

## Deprecated Functions
| Name | Replacement | Reason | Deprecated Since |
|------|-------------|--------|------------------|
| `fetchPlayer` | `getPlayerById` | Old naming convention | 2024-11-01 |
| `usePlayerData` | `usePlayer` | Inconsistent hook naming | 2024-11-15 |
| `formatDate` (utils/format.ts) | `dayjs.format()` | Use dayjs directly | 2024-10-20 |

## Deprecated Patterns
| Pattern | Replacement | Reason |
|---------|-------------|--------|
| `useEffect` for data fetching | React Query `useQuery` | Better caching, loading states |
| Prop drilling > 2 levels | Context or composition | Maintainability |
| `any` type | Proper typing or `unknown` | Type safety |
| Inline styles | Tailwind classes | Consistency |

## Deprecated Files
| File | Action | Reason |
|------|--------|--------|
| `lib/api/legacy-*.ts` | Remove after migration | Old API structure |
| `components/old/` | Delete entire directory | Unused legacy components |

## Deprecated Dependencies  
| Package | Replacement | Migration Guide |
|---------|-------------|-----------------|
| `moment` | `dayjs` | [link to guide] |
| `axios` | `fetch` or `ky` | Native fetch preferred |

## Framework Syntax Updates
| Old Syntax | New Syntax | Framework | Version |
|------------|------------|-----------|---------|
| `getServerSideProps` | App Router server components | Next.js | 13+ |
| `getStaticProps` | `generateStaticParams` + fetch | Next.js | 13+ |
```

### Anti-Pattern Detection Agent

```markdown
## Anti-Pattern Detection Agent Configuration

### Trigger Words
Scan for these patterns in proposed code:

```typescript
const DEPRECATED_TRIGGERS = {
  functions: [
    'fetchPlayer',      // → getPlayerById
    'usePlayerData',    // → usePlayer
    'formatDate',       // → dayjs
  ],
  
  patterns: [
    /useEffect\s*\(\s*\(\)\s*=>\s*\{[^}]*fetch/,  // useEffect + fetch
    /: any\b/,           // any type
    /style=\{\{/,        // inline styles
    /\.then\s*\(/,       // .then() instead of async/await
  ],
  
  imports: [
    'moment',            // → dayjs
    'axios',             // → fetch/ky
    '@/lib/api/legacy',  // deprecated API module
  ],
  
  files: [
    /\/old\//,           // old/ directories
    /\.legacy\./,        // .legacy. in filename
  ]
};
```

### Agent Behavior

When anti-pattern detected:

```
⚠️ ANTI-PATTERN DETECTED

Found: useEffect with fetch pattern
Location: components/PlayerStats.tsx

This pattern is deprecated. Use React Query instead.

Deprecated:
```typescript
useEffect(() => {
  fetch('/api/player-stats').then(...)
}, []);
```

Recommended:
```typescript
const { data, isLoading } = useQuery({
  queryKey: ['player-stats', playerId],
  queryFn: () => getPlayerStats(playerId),
});
```

Reason: React Query provides automatic caching, background refetching,
loading/error states, and prevents race conditions.

Documentation: See PATTERNS.md > Data Fetching > React Query
```

### Project Idiosyncrasies Context

The anti-pattern agent should understand project-specific conventions:

```markdown
## Project-Specific Rules (vba-lms-app)

### Naming Conventions
- API functions: `get*`, `create*`, `update*`, `delete*`
- Hooks: `use*` (camelCase after use)
- Components: PascalCase
- Files: kebab-case for utilities, PascalCase for components

### Architecture Rules
- All Supabase calls go through `lib/api/` - never direct in components
- All Payload CMS operations use typed collections from `vba-hoops/collections`
- Server components are default - only use 'use client' when necessary

### Type Conventions
- All API responses typed with generated Supabase types
- Form data uses Zod schemas, not raw interfaces
- Never use `as` type assertions - fix the actual type

### Error Handling
- API errors: Sentry capture + rethrow
- Form errors: react-hook-form + zod
- User errors: sonner toasts

### Testing
- Components: Vitest + Testing Library
- API: Integration tests with test database
- E2E: Playwright for critical flows
```

---

## Part 4: Documentation Integration

### Auto-Update Triggers

When a pattern is codified:

```
1. Pattern identified and validated
   ↓
2. Update PATTERNS.md with new entry
   ↓
3. If deprecated pattern identified:
   → Add to DEPRECATED.md
   → Update COMPONENT_REGISTRY.md (mark old items)
   ↓
4. If new component/function pattern:
   → Regenerate COMPONENT_REGISTRY.md
   ↓
5. If architectural change:
   → Update ARCHITECTURE.md
   ↓
6. Update skill that should contain this knowledge
```

### Living Documentation Structure

```
project-root/
├── CLAUDE.md              # Router (< 200 lines) - points to other docs
├── ARCHITECTURE.md        # System design, data flow, major decisions
├── PATTERNS.md            # Coding patterns registry
├── DEPRECATED.md          # Anti-patterns and deprecated items
├── CURRENT_SPRINT.md      # Active work context
├── COMPONENT_REGISTRY.md  # Auto-generated component/function index
│
└── .claude/
    └── skills/
        ├── dependency-graph/
        │   └── SKILL.md
        ├── component-registry/
        │   └── SKILL.md
        ├── error-triage/
        │   └── SKILL.md
        ├── regression-prevention/
        │   └── SKILL.md
        └── skill-refinement/
            └── SKILL.md   # This meta-skill
```

---

## Self-Improvement Loop

### Weekly Skill Review Prompt

```markdown
## Weekly Skill Effectiveness Review

Run this assessment weekly:

1. **Pattern Capture Rate**
   - How many insights were captured this week?
   - How many were converted to skill updates?
   - Gap: insights discussed but not documented

2. **Anti-Pattern Detection Rate**  
   - How many deprecated patterns were caught before commit?
   - How many slipped through to PR review?
   - Update trigger list if patterns were missed

3. **Skill Trigger Accuracy**
   - Are skills activating at the right times?
   - Any false negatives (should have triggered, didn't)?
   - Any false positives (triggered unnecessarily)?

4. **Documentation Currency**
   - Is PATTERNS.md up to date?
   - Is DEPRECATED.md complete?
   - Is COMPONENT_REGISTRY.md fresh?

5. **Context Window Efficiency**
   - Are we loading unnecessary context?
   - Can any skill content be split into on-demand files?
```

### Skill Improvement Capture

When Claude could have performed better:

```markdown
## Skill Improvement Capture

### What happened?
[Description of suboptimal outcome]

### What would have helped?
[Information or guidance that was missing]

### Which skill should be updated?
[Target skill]

### Proposed addition:
```
[New content to add to skill]
```

### Validation:
- [ ] This information is generalizable (not one-off)
- [ ] This doesn't contradict existing guidance
- [ ] This is appropriately scoped for the target skill
```

---

## Success Metrics

1. **Pattern Capture Rate**
   - Target: 90% of significant insights documented within session

2. **Anti-Pattern Prevention Rate**
   - Target: 95% of deprecated patterns caught before implementation

3. **Skill Activation Accuracy**
   - Target: <5% false negative rate

4. **Documentation Freshness**
   - Target: All docs updated within 1 week of relevant changes

---

## Open Questions

1. How to prioritize which insights become skills vs just documentation?
2. Should anti-pattern detection be blocking or advisory?
3. How to handle conflicting patterns (context-dependent best practices)?
4. Integration with git hooks for automated anti-pattern scanning?

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2024-12-01 | Initial foundation with pattern detection system |
