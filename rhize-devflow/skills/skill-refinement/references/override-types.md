# Override Types Reference

Detailed documentation of skill override types and when to use each.

---

## Overview

The Skill Refinement System supports six override types, each designed for specific modification scenarios:

| Type | File | Scope | Use Case |
|------|------|-------|----------|
| Section Patch | `SKILL.patch.md` | Targeted | Modify specific sections |
| Extension | `SKILL.extend.md` | Additive | Add new capabilities |
| Config Override | `skill-config.json` | Settings | Environment-specific values |
| Full Override | `SKILL.md` | Complete | Major skill divergence |
| Hook Override | `hooks/[name].sh` | Script | Hook behavior changes |
| Script Override | `scripts/[name].py` | Script | Script behavior changes |

---

## 1. Section Patch (`SKILL.patch.md`)

### Description
Modifies specific sections of a skill without replacing the entire file. Uses action syntax to precisely target changes.

### When to Use
- Fixing a bug in a specific section
- Adding items to a list (triggers, patterns, etc.)
- Modifying hook behavior with minimal changes
- Adjusting command steps

### File Location
```
.claude/skills/[skill-name]/SKILL.patch.md
```

### Format
```markdown
# SKILL.patch.md
# Patches for: [skill-name]
# Generated: [timestamp]

## PATCH: [target-section]
<!-- ACTION: [action-type] "[marker]" -->
[patch content]
```

### Example
```markdown
# SKILL.patch.md
# Patches for: context-engineering

## PATCH: hooks/duplicate-check
<!-- ACTION: insert-after "Only check paths" -->
# Exclude test directories
if echo "$FILE_PATH" | grep -qE "(__tests__|fixtures)"; then
  exit 0
fi
```

### Pros
- Minimal duplication
- Easy to track changes
- Non-destructive
- Composable (multiple patches can coexist)

### Cons
- Requires skill to have consistent structure
- Marker-based targeting can be fragile
- May conflict if base skill changes

---

## 2. Extension (`SKILL.extend.md`)

### Description
Adds new capabilities to an existing skill without modifying existing behavior. Purely additive.

### When to Use
- Adding new trigger phrases
- Adding new command variants
- Extending patterns or rules
- Adding new sections

### File Location
```
.claude/skills/[skill-name]/SKILL.extend.md
```

### Format
```markdown
# SKILL.extend.md
# Extensions for: [skill-name]

## EXTEND: [section-name]
<!-- ACTION: append -->
[new content]

## NEW SECTION: [section-name]
[entirely new section content]
```

### Example
```markdown
# SKILL.extend.md
# Extensions for: error-lifecycle-management

## EXTEND: triggers
<!-- ACTION: append -->
- "performance issue"
- "slow response"
- "latency problem"

## NEW SECTION: Performance Thresholds
### Response Time Alerts
- API calls > 2s: Warning
- API calls > 5s: Critical
- Page load > 3s: Warning
```

### Pros
- Safe - never removes existing functionality
- Clear separation of customizations
- Easy to review additions

### Cons
- Can only add, not modify
- May duplicate if extending similar content
- Base skill must support extension points

---

## 3. Config Override (`skill-config.json`)

### Description
Overrides configuration values without modifying skill logic. Ideal for environment-specific settings.

### When to Use
- Different thresholds per project
- Environment-specific paths or URLs
- Feature flags
- Tool-specific configurations

### File Location
```
.claude/skills/[skill-name]/skill-config.json
```

### Format
```json
{
  "skill": "[skill-name]",
  "version": "1.0.0",
  "config": {
    "[key]": "[value]"
  }
}
```

### Example
```json
{
  "skill": "error-lifecycle-management",
  "version": "1.0.0",
  "config": {
    "sentry_project": "my-custom-project",
    "error_threshold": 10,
    "exclude_patterns": ["__tests__", "fixtures"],
    "api_patterns": {
      "base_url": "/api/v2"
    }
  }
}
```

### Pros
- Clean separation of config from logic
- Easy to diff and review
- Machine-readable
- No risk of breaking skill logic

### Cons
- Limited to predefined config options
- Skill must explicitly support configuration
- Cannot add new behavior

---

## 4. Full Override (`SKILL.md`)

### Description
Completely replaces the base skill with a project-specific version. Nuclear option.

### When to Use
- Major divergence from base skill
- Project requires fundamentally different approach
- Base skill is deprecated and needs replacement
- Temporary fork for experimentation

### File Location
```
.claude/skills/[skill-name]/SKILL.md
```

### Format
Complete skill document following standard skill format.

### Example
```markdown
# Error Lifecycle Management (Project Override)

> This is a full override for the vba-lms-app project.
> Original skill: error-lifecycle-management

## Triggers
[Project-specific triggers]

## Workflow
[Project-specific workflow]

...
```

### Pros
- Complete control
- No dependency on base skill structure
- Can fundamentally change behavior

### Cons
- Loses all base skill updates
- High maintenance burden
- May diverge significantly over time
- Harder to generalize improvements

---

## 5. Hook Override (`hooks/[name].sh`)

### Description
Replaces a specific hook script with a project-customized version.

### When to Use
- Hook needs project-specific logic
- Different validation rules per project
- Custom integration requirements
- Performance optimizations

### File Location
```
.claude/skills/[skill-name]/hooks/[hook-name].sh
```

### Format
Complete shell script following hook conventions.

### Example
```bash
#!/bin/bash
# duplicate-check.sh (Project Override)
# Custom duplicate checking for vba-lms-app

# Project-specific exclusions
EXCLUDE_DIRS="__tests__|fixtures|migrations|generated"

# Custom component registry location
REGISTRY="./src/.component-registry.json"

# ... rest of hook logic
```

### Pros
- Full control over hook behavior
- Can add project-specific integrations
- Maintains hook interface

### Cons
- Must maintain entire hook
- Loses base hook updates
- May miss security/bug fixes

---

## 6. Script Override (`scripts/[name].py`)

### Description
Replaces a specific Python script with a project-customized version.

### When to Use
- Script needs project-specific logic
- Custom data processing requirements
- Different output formats needed
- Integration with project-specific tools

### File Location
```
.claude/skills/[skill-name]/scripts/[script-name].py
```

### Format
Complete Python script following script conventions.

### Example
```python
#!/usr/bin/env python3
"""
validate_error_coverage.py (Project Override)
Custom error validation for vba-lms-app
"""

from common.base_validator import BaseValidator

class ProjectValidator(BaseValidator):
    """Project-specific error validator."""

    # Custom patterns for this project
    ERROR_PATTERNS = [
        r"PayloadCMSError",
        r"LMSValidationError",
    ]

    def validate(self, file_path: str) -> bool:
        # Project-specific validation logic
        ...
```

### Pros
- Full control over script behavior
- Can integrate project-specific libraries
- Maintains script interface

### Cons
- Must maintain entire script
- Loses base script updates
- May miss improvements

---

## Priority Resolution

When multiple override types exist, they are resolved in this order:

```
1. Full Override (SKILL.md)        → If exists, use entirely
2. Hook/Script Overrides           → Replace specific components
3. Section Patches (SKILL.patch.md)→ Apply to base skill
4. Extensions (SKILL.extend.md)    → Add to patched skill
5. Config Override (skill-config.json) → Apply configuration
```

---

## Decision Matrix

| Scenario | Recommended Type |
|----------|-----------------|
| Add new trigger phrase | Extension |
| Fix hook false positive | Section Patch |
| Change API endpoint | Config Override |
| Add validation step | Section Patch or Extension |
| Replace entire hook | Hook Override |
| Different validation rules | Script Override |
| Fundamental skill redesign | Full Override |
| Environment-specific setting | Config Override |
| Add new command variant | Extension |
| Modify existing command step | Section Patch |

---

## Best Practices

1. **Start small** - Begin with patches/extensions before considering full overrides
2. **Document why** - Always note the reason for the override
3. **Track refinement IDs** - Link overrides to their source refinements
4. **Review regularly** - Check if overrides can be generalized or removed
5. **Test thoroughly** - Verify override doesn't break other functionality
6. **Consider generalization** - If override is useful, consider promoting to user-scope
