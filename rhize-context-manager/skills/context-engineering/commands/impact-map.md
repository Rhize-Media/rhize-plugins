# Impact Map

Map dependencies before implementing new features or making changes.

## Triggers
**Keywords:** implement, create new, add feature, build, new component, what files, dependencies

## What This Does

1. **Identify Target Files** - What needs to be created/modified
2. **Map Dependencies** - What imports/uses these files
3. **Find Related Patterns** - Similar existing implementations
4. **Check Registry** - Existing components to reuse
5. **Generate Implementation Plan** - Ordered steps

## Automatic Actions

### Step 1: Understand the Requirement
Clarify:
- What is being built?
- What existing features is it similar to?
- What data/state does it need?

### Step 2: Search for Existing Patterns
```bash
# Find similar implementations
grep -r "similar_pattern" --include="*.ts" --include="*.tsx"
```

Check COMPONENT_REGISTRY.md for:
- Reusable components
- Existing hooks
- Utility functions

### Step 3: Map the Dependency Graph
For the target location:
- What will import this?
- What will this import?
- What types are needed?
- What API endpoints involved?

### Step 4: Identify All Touchpoints
Files that will need changes:
- [ ] New files to create
- [ ] Existing files to modify
- [ ] Type definitions to update
- [ ] Tests to add/update
- [ ] Documentation to update

### Step 5: Generate Implementation Order
Sequence matters - build from foundation up:
1. Types/interfaces first
2. Utility functions
3. Data fetching hooks
4. Core component
5. Integration points
6. Tests

## Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🗺️ Impact Map: [Feature Name]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 Reusable Components Found:
  - [component]: [how to use]

📁 Files to Create:
  1. [path] - [purpose]

📝 Files to Modify:
  1. [path] - [what changes]

🔗 Dependency Chain:
  [visual or list of dependencies]

📋 Implementation Order:
  1. [first step]
  2. [second step]
  ...

⚠️ Risks/Considerations:
  - [potential issues]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Benefits

- **Prevents Duplication**: Find existing code to reuse
- **Complete Implementation**: Don't miss related files
- **Correct Order**: Build dependencies first
- **Better Estimates**: Know full scope upfront

## Related Commands
- `/done` - Validate after implementation
- `/context-hygiene` - If mapping takes long
