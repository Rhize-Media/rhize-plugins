# Patch Syntax Reference

Complete reference for section-level patch actions in `SKILL.patch.md` files.

---

## Overview

Patches use HTML comments with ACTION directives to specify how content should be applied:

```markdown
## PATCH: [target-section]
<!-- ACTION: [action-type] "[optional-marker]" -->
[patch content]
```

---

## Action Types

### 1. `append`

Adds content to the **end** of a section.

**Syntax:**
```markdown
<!-- ACTION: append -->
```

**Example:**
```markdown
## PATCH: triggers
<!-- ACTION: append -->
- "new trigger phrase"
- "another trigger"
```

**Before:**
```markdown
## Triggers
- "existing trigger"
- "another existing"
```

**After:**
```markdown
## Triggers
- "existing trigger"
- "another existing"
- "new trigger phrase"
- "another trigger"
```

---

### 2. `prepend`

Adds content to the **start** of a section.

**Syntax:**
```markdown
<!-- ACTION: prepend -->
```

**Example:**
```markdown
## PATCH: triggers
<!-- ACTION: prepend -->
- "high priority trigger"
```

**Before:**
```markdown
## Triggers
- "existing trigger"
```

**After:**
```markdown
## Triggers
- "high priority trigger"
- "existing trigger"
```

---

### 3. `replace-section`

Replaces an entire named subsection.

**Syntax:**
```markdown
<!-- ACTION: replace-section "SECTION NAME" -->
```

**Example:**
```markdown
## PATCH: hooks/duplicate-check
<!-- ACTION: replace-section "EXCLUDE PATTERNS" -->
# Exclude patterns (updated)
EXCLUDE_PATTERNS="${EXCLUDE_PATTERNS:-__tests__|fixtures|__mocks__|generated}"
```

**Before:**
```bash
# EXCLUDE PATTERNS
EXCLUDE_PATTERNS="node_modules"

# Other code...
```

**After:**
```bash
# Exclude patterns (updated)
EXCLUDE_PATTERNS="${EXCLUDE_PATTERNS:-__tests__|fixtures|__mocks__|generated}"

# Other code...
```

**Notes:**
- Section name matching is case-insensitive
- Replaces from the marker line to the next section marker or end of block

---

### 4. `insert-after`

Inserts content **after** a specific marker line.

**Syntax:**
```markdown
<!-- ACTION: insert-after "marker text" -->
```

**Example:**
```markdown
## PATCH: commands/start
<!-- ACTION: insert-after "Step 3:" -->

### Step 3.5: Additional Validation
Run project-specific checks:
```bash
./scripts/validate-project.sh
```
```

**Before:**
```markdown
### Step 3: Run Tests
Execute the test suite.

### Step 4: Build
Build the project.
```

**After:**
```markdown
### Step 3: Run Tests
Execute the test suite.

### Step 3.5: Additional Validation
Run project-specific checks:
```bash
./scripts/validate-project.sh
```

### Step 4: Build
Build the project.
```

**Notes:**
- Marker text must be unique within the section
- Matching is substring-based (marker can be partial line)
- Whitespace is normalized for matching

---

### 5. `insert-before`

Inserts content **before** a specific marker line.

**Syntax:**
```markdown
<!-- ACTION: insert-before "marker text" -->
```

**Example:**
```markdown
## PATCH: hooks/pre-commit-guard
<!-- ACTION: insert-before "exit 1" -->
# Log the failure reason
echo "Pre-commit check failed: $REASON" >> .claude/pre-commit.log
```

**Before:**
```bash
if [ "$CHECK_FAILED" = true ]; then
  exit 1
fi
```

**After:**
```bash
if [ "$CHECK_FAILED" = true ]; then
  # Log the failure reason
  echo "Pre-commit check failed: $REASON" >> .claude/pre-commit.log
  exit 1
fi
```

---

### 6. `delete-section`

Removes a named subsection entirely.

**Syntax:**
```markdown
<!-- ACTION: delete-section "SECTION NAME" -->
```

**Example:**
```markdown
## PATCH: config
<!-- ACTION: delete-section "DEPRECATED OPTIONS" -->
```

**Before:**
```markdown
## Config

### Current Options
- option_a: value
- option_b: value

### DEPRECATED OPTIONS
- old_option: don't use
- legacy_setting: removed

### New Options
- new_option: value
```

**After:**
```markdown
## Config

### Current Options
- option_a: value
- option_b: value

### New Options
- new_option: value
```

**Notes:**
- Use with caution - ensures deprecated content is fully removed
- Section boundaries detected by markdown headers or code block markers

---

## Target Section Paths

The `## PATCH:` header specifies which part of the skill to modify:

### File-Level Targets
```markdown
## PATCH: triggers          # The triggers section
## PATCH: workflow          # The workflow section
## PATCH: output-format     # The output format section
```

### Component-Level Targets
```markdown
## PATCH: hooks/duplicate-check     # Specific hook
## PATCH: hooks/pre-commit-guard    # Another hook
## PATCH: scripts/validate_errors   # Specific script
## PATCH: commands/start            # Specific command
## PATCH: commands/done/Step 4      # Specific step in a command
```

### Nested Targets
```markdown
## PATCH: workflow/Step 3/Validation    # Nested subsection
## PATCH: references/patterns/api       # Nested reference
```

---

## Multiple Patches

A single `SKILL.patch.md` can contain multiple patches:

```markdown
# SKILL.patch.md
# Patches for: context-engineering
# Refinements: REF-2024-1204-001, REF-2024-1204-002

## PATCH: triggers
<!-- ACTION: append -->
- "test fixture"
- "mock component"

## PATCH: hooks/duplicate-check
<!-- ACTION: insert-after "Only check paths" -->
# Exclude test directories
if echo "$FILE_PATH" | grep -qE "(__tests__|fixtures)"; then
  exit 0
fi

## PATCH: commands/done
<!-- ACTION: replace-section "Validation Steps" -->
### Validation Steps
1. Run tests: `npm test`
2. Run lint: `npm run lint`
3. Run build: `npm run build`
```

---

## Marker Matching Rules

### Exact Match
```markdown
<!-- ACTION: insert-after "Step 3:" -->
```
Matches line containing exactly "Step 3:"

### Substring Match
```markdown
<!-- ACTION: insert-after "Step 3" -->
```
Matches any line containing "Step 3" (including "Step 3:", "Step 3 -", etc.)

### Case Sensitivity
- Markers are **case-sensitive** by default
- Use lowercase markers if case varies

### Whitespace Handling
- Leading/trailing whitespace is trimmed
- Internal whitespace is preserved
- Multiple spaces are normalized to single space

### Special Characters
Escape special regex characters in markers:
```markdown
<!-- ACTION: insert-after "function() {" -->     # Works
<!-- ACTION: insert-after "array[0]" -->         # May need escaping
```

---

## Patch Ordering

When multiple patches target the same section, they're applied in file order:

```markdown
## PATCH: triggers
<!-- ACTION: prepend -->
- "first"

## PATCH: triggers
<!-- ACTION: append -->
- "last"
```

Result: "first" at top, "last" at bottom.

---

## Error Handling

### Marker Not Found
If a marker isn't found, the patch fails with an error:
```
⚠️ Patch failed: Marker "Step 3:" not found in hooks/duplicate-check
```

### Multiple Matches
If a marker matches multiple lines:
```
⚠️ Patch warning: Marker "exit" matched 3 lines. Using first match.
```

### Section Not Found
If the target section doesn't exist:
```
⚠️ Patch failed: Section "hooks/unknown-hook" not found in skill
```

---

## Best Practices

1. **Use unique markers**
   - Bad: `<!-- ACTION: insert-after "if" -->`
   - Good: `<!-- ACTION: insert-after "if [ -z \"$COMPONENT\" ]" -->`

2. **Include context in markers**
   - Bad: `"exit 1"`
   - Good: `"# Exit on validation failure"` followed by `exit 1`

3. **Comment your patches**
   ```markdown
   ## PATCH: hooks/duplicate-check
   # REF-2024-1204-001: Exclude test directories from duplicate checking
   <!-- ACTION: insert-after "Only check paths" -->
   ```

4. **Test incrementally**
   - Apply one patch at a time
   - Verify each patch before adding more

5. **Document refinement IDs**
   - Track which refinement created each patch
   - Makes it easier to review/remove later

6. **Prefer targeted patches**
   - Use `insert-after` over `replace-section` when possible
   - Smaller changes are easier to maintain
