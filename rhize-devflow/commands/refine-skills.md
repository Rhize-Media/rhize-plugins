# /refine-skills Command

> Capture and apply skill refinements with semi-automated analysis

---

## Trigger Patterns

```
Primary:
/refine-skills, /refine-skill, /skill-refine

Auto-detected:
"skill doesn't work", "skill should have", "missing trigger"
"should have caught", "why didn't skill", "skill broke"
"improve skill", "extend skill", "add to skill"
"skill missed", "false positive", "false negative"
```

---

## Workflow

### Step 1: Identify Target

**Questions to resolve:**

1. **Which skill needs refinement?**
   - Auto-detect from recent context
   - User can specify explicitly
   - List available skills if unclear

2. **What category?**
   - `trigger` - When skill activates
   - `content` - What skill does/outputs
   - `hook` - Automation behavior
   - `tool` - MCP/tool integration
   - `pattern` - Detection/validation logic
   - `config` - Settings/options
   - `new` - Capability doesn't exist yet

**Output:**
```
🎯 Target Identified:
   Skill: [skill-name]
   Category: [category]
   Confidence: [high|medium|low]
```

---

### Step 2: Gather Context (Automated)

**Implementation:** `scripts/gather_context.py`

```bash
# CLI usage
python scripts/gather_context.py --skill context-engineering

# List available skills
python scripts/gather_context.py --list-skills

# JSON output for programmatic use
python scripts/gather_context.py --skill context-engineering --json
```

**Sources queried:**

1. **Git Context** (always available)
   - Current status and diff
   - Recent commits (last 10)
   - Changed files

2. **Skill Context** (always available)
   - Current skill configuration (project + user scope)
   - Existing overrides in `.claude/skills/[skill]/`
   - Skill file structure

3. **Pattern Context** (from `~/.claude/skill-refinements/`)
   - Similar past refinements for this skill
   - Matching patterns in aggregated-patterns.md

4. **Session Context** (when MCP available)
   - Recent tool calls via Desktop Commander
   - Files touched this session

5. **Error Context** (when Sentry MCP available)
   - Recent errors for this project
   - Related stack traces

6. **Cross-Project Context** (when Zen MCP available)
   - Patterns from other projects
   - Saved memories and context

**Output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Context Gathered
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Target Skill: context-engineering
📁 Project: vba-lms-app
📍 Root: /Users/james/projects/vba-lms-app

📊 Git Status: 5 changed files
📝 Recent Commits: 10
📄 Files Touched: 5
🔧 Skill Files: 8
🔍 Similar Refinements: 2
🎯 Pattern Matches: PATTERN-001: Test Directory Exclusion

🔌 MCP Status:
   Desktop Commander: not available
   Sentry: not available
   Zen: not available

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 3: Capture User Insight

**Questions to ask:**

1. **What behavior did you expect?**
   > Describe what should have happened

2. **What actually happened?**
   > Describe the actual behavior

3. **Can you provide a specific example?**
   > Command, file, or scenario that demonstrates the issue

4. **What's the desired outcome?**
   > What should happen after the refinement

**Guided Mode (triggered when):**
- Confidence < 70%
- Multiple valid approaches detected
- Cross-skill impact identified
- Unclear user intent

**Guided Mode provides:**
- Clarifying questions
- Example suggestions from similar refinements
- Option previews

---

### Step 4: Analyze & Propose

**Implementation:** `scripts/analyze_gap.py`

```bash
# CLI usage
python scripts/analyze_gap.py \
  --skill context-engineering \
  --category hook \
  --target hooks/duplicate-check \
  --expected "Test fixtures should be allowed" \
  --actual "Hook blocks all matching files"

# With example (for pattern matching)
python scripts/analyze_gap.py \
  --skill context-engineering \
  --expected "..." --actual "..." \
  --example "touch components/__tests__/fixtures/MockButton.tsx"

# JSON output for programmatic use
python scripts/analyze_gap.py --skill ... --expected ... --actual ... --json
```

**Analysis steps (automated):**

1. **Category Detection** (if not specified)
   - Analyzes keywords: "hook" → hook, "trigger" → trigger, etc.
   - Falls back to content category if ambiguous

2. **Override Type Selection**
   | Scenario | Recommended Type |
   |----------|-----------------|
   | Small section change | `patch` |
   | Adding new trigger/pattern | `extend` |
   | Environment-specific value | `config` |
   | Hook logic change | `hook` |
   | Major rewrite needed | `full` |

3. **Confidence Scoring**
   - Base: 0.5
   - +0.2 if category explicitly provided
   - +0.1 if target specified
   - +0.1 if example provided
   - **Guided mode triggers when < 0.7**

4. **Generalization Assessment**
   - `high` - Generic patterns (test exclusions, common configs)
   - `medium` - Reusable but context-dependent
   - `low` - Project-specific customizations

**Output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Gap Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Target: context-engineering
📋 Category: hook
📍 Section: hooks/duplicate-check

📝 Gap:
   Expected: Test fixtures should be allowed
   Actual: Hook blocks all matching files

📊 Analysis:
   Override Type: hook
   Confidence: 0.80 (high)
   Generalization: high

💡 Recommendation:
   Create hook override to add test directory exclusion

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 5: Generate & Preview Changes

**Implementation:** `scripts/generate_patch.py`

```bash
# Generate a patch with preview (dry-run by default)
python scripts/generate_patch.py \
  --skill context-engineering \
  --section hooks/duplicate-check \
  --action insert-after \
  --marker "Only check paths" \
  --content "# Exclude test dirs\nif [[ \$FILE =~ test ]]; then exit 0; fi"

# Write the patch files
python scripts/generate_patch.py \
  --skill context-engineering \
  --section hooks/duplicate-check \
  --action insert-after \
  --marker "Only check paths" \
  --content "..." \
  --write

# Preview without writing (explicit)
python scripts/generate_patch.py --skill ... --dry-run
```

**Supported Patch Actions:**
| Action | Syntax | Behavior |
|--------|--------|----------|
| `append` | `<!-- ACTION: append -->` | Add to end of section |
| `prepend` | `<!-- ACTION: prepend -->` | Add to start of section |
| `replace-section` | `<!-- ACTION: replace-section "NAME" -->` | Replace subsection |
| `insert-after` | `<!-- ACTION: insert-after "MARKER" -->` | Insert after marker |
| `insert-before` | `<!-- ACTION: insert-before "MARKER" -->` | Insert before marker |
| `delete-section` | `<!-- ACTION: delete-section "NAME" -->` | Remove subsection |

**Preview Format:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 Generated Patch
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Skill: context-engineering
📋 Section: hooks/duplicate-check
⚙️ Action: insert-after
🔍 Marker: "Only check paths"

📄 Diff Preview:
┌─────────────────────────────────────────────────────
│   Only check paths
│ + # Exclude test directories
│ + EXCLUDE_PATTERNS="${EXCLUDE_PATTERNS:-__tests__|fixtures|__mocks__}"
│ + if echo "$FILE_PATH" | grep -qE "($EXCLUDE_PATTERNS)"; then
│ +   exit 0
│ + fi
└─────────────────────────────────────────────────────

📁 Output: .claude/skills/context-engineering/SKILL.patch.md

[DRY RUN - use --write to create files]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 6: User Confirmation

**Options presented:**

1. **Apply as proposed** - Create files and log refinement
2. **Modify before applying** - Edit the proposed changes
3. **Apply to project only** - Skip user-scope logging
4. **Cancel** - Abort refinement

---

### Step 7: Apply Refinement

**Project Scope Actions:**
1. Create `.claude/skills/[skill]/` directory if needed
2. Write override file (patch, extend, config, etc.)
3. Update project refinement log

**User Scope Actions:**
1. Generate refinement ID: `REF-YYYY-MMDD-NNN`
2. Log to `~/.claude/skill-refinements/suggested-refinements.md`
3. Create history entry in `refinement-history/`
4. Update `aggregated-patterns.md`
5. Check pattern count → trigger generalization if ≥2
6. Sync to Zen MCP (if available)

**Output:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Refinement Applied: REF-2024-1204-001
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📁 Created:
  .claude/skills/[skill]/SKILL.patch.md

📝 Logged to:
  ~/.claude/skill-refinements/suggested-refinements.md
  ~/.claude/skill-refinements/refinement-history/[date]-[skill]-[type].md

🔮 Pattern Tracking:
  [New pattern created / Existing pattern updated]
  Count: [N] occurrences
  [Auto-generalization triggered / Threshold: N more needed]

💡 Next Steps:
  1. Test: [specific test scenario]
  2. Verify the change works as expected
  3. Run /done to validate before committing

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Examples

### Example 1: Hook Modification

```
User: "The duplicate-check hook keeps blocking my test fixtures"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 Skill Refinement Detected
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Target Identified:
   Skill: context-engineering
   Category: hook
   Confidence: high

📋 Context Gathered:
   • Tool calls: 47 recent operations
   • Files touched: components/__tests__/fixtures/
   • Errors: 3 blocked file creations
   • Pattern matches: none (new pattern)

📝 Capturing Issue:

Expected: Test fixtures should be allowed
Actual: Hook blocks any file matching component names
Example: touch components/__tests__/fixtures/MockButton.tsx

📊 Analysis:
   Root cause: No exclusion for test directories
   Override type: patch (hook modification)
   Generalization: high (common pattern)

Apply refinement? [yes/modify/cancel]
```

### Example 2: Trigger Addition

```
User: "The error-lifecycle skill should also trigger for 'performance issue'"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 Skill Refinement
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Target Identified:
   Skill: error-lifecycle-management
   Category: trigger
   Confidence: high

📊 Proposed:
   Override type: extend
   Action: Append to triggers section

📄 Changes:
┌─ .claude/skills/error-lifecycle-management/SKILL.extend.md ─
│ ## EXTEND: triggers
│ <!-- ACTION: append -->
│ - "performance issue"
│ - "slow response"
│ - "latency problem"
└─────────────────────────────────────────────────────────────

Apply refinement? [yes/modify/cancel]
```

---

## Error Handling

### Skill Not Found
```
⚠️ Could not identify target skill

Available skills:
  • context-engineering
  • error-lifecycle-management
  • dev-flow-foundations

Please specify: /refine-skills [skill-name]
```

### Ambiguous Category
```
⚠️ Multiple categories could apply

This refinement could be:
  1. trigger - Change when skill activates
  2. content - Change what skill outputs

Which category fits better? [1/2]
```

### Low Confidence
```
⚠️ Entering Guided Mode (confidence: 45%)

I need more information to proceed:

1. Can you show me the exact error or unexpected behavior?
2. What file or command triggered this issue?
3. Have you seen this in other projects?
```

---

## Related Commands

- `/apply-generalization` - Apply patterns to user-scope skills
- `/review-patterns` - View tracked patterns
- `/done` - Validate changes before committing
