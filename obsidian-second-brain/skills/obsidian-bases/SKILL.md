---
name: obsidian-bases
description: >
  ALWAYS invoke this skill (via the Skill tool) for any Obsidian Bases or .base file request.
  Create and edit Obsidian Base files (.base) for database-like views, filters,
  formulas, and data summaries within your vault. Use this skill whenever someone
  asks about Obsidian Bases, creating database views, filtering notes by properties,
  building task trackers, reading lists, project dashboards, or any structured data
  view in Obsidian. Also triggers on ".base files", "Obsidian database", "note
  database", "vault database", or questions about filters, formulas, and summaries
  in the context of Obsidian.
---

# Obsidian Bases

Base files (`.base` extension) bring database-like functionality to Obsidian. They let you create filtered, sorted, and computed views of your notes — think of them as saved queries over your vault.

## File Format

Base files use valid YAML with these optional top-level sections:

```yaml
filters:
  # Define which notes appear
formulas:
  # Computed properties
properties:
  # Column visibility and ordering
summaries:
  # Aggregate calculations
views:
  # Display configurations (table, card, list, map)
```

## Filters

Filters determine which notes are included in the base. They support AND/OR/NOT logic.

```yaml
filters:
  - operator: and
    conditions:
      - field: tags
        operator: contains
        value: project
      - field: status
        operator: is not
        value: archived
```

**Filter operators:** is, is not, contains, does not contain, starts with, ends with, is empty, is not empty, greater than, less than, on or after, on or before

### Nested Logic

```yaml
filters:
  - operator: or
    conditions:
      - operator: and
        conditions:
          - field: tags
            operator: contains
            value: urgent
          - field: status
            operator: is
            value: active
      - field: priority
        operator: is
        value: high
```

## Formulas

Formulas create computed properties available across all views. They reference note properties and support arithmetic, conditionals, strings, and dates.

```yaml
formulas:
  days_since_created: '(now() - file.ctime).days'
  is_overdue: 'if(due < now(), "Yes", "No")'
  full_name: 'first_name + " " + last_name'
  progress_pct: 'round((completed / total) * 100, 1)'
```

### Formula Syntax

- **Arithmetic:** `+`, `-`, `*`, `/`, `round()`, `abs()`, `min()`, `max()`
- **Strings:** `+` (concat), `length()`, `lower()`, `upper()`, `contains()`
- **Dates:** `now()`, `.days`, `.hours` on duration results
- **Conditionals:** `if(condition, true_value, false_value)`
- **File metadata:** `file.ctime`, `file.mtime`, `file.name`, `file.path`, `file.size`

**Important:** Duration calculations require accessing numeric fields. Use `(now() - file.ctime).days` rather than direct operations on Duration types.

**Quoting rule:** Single quotes wrap the entire formula. If the formula itself contains double quotes (like string literals), this works naturally. If you need single quotes inside, escape carefully.

## Properties (Column Configuration)

Control which properties appear and their order in views:

```yaml
properties:
  - name: status
    visible: true
    width: 120
  - name: due
    visible: true
    width: 100
  - name: days_since_created
    visible: true
  - name: tags
    visible: false
```

## Summaries

Aggregate calculations shown at the bottom of table views:

```yaml
summaries:
  - field: amount
    function: sum
  - field: due
    function: earliest
  - field: rating
    function: average
  - field: status
    function: count_values
```

**Summary functions:** sum, average, min, max, count, count_values, earliest, latest, range, median, percent_empty, percent_not_empty

## Views

Configure how data is displayed:

```yaml
views:
  - type: table
    name: Active Projects
    sort:
      - field: due
        order: asc
    group_by: status

  - type: card
    name: Project Cards
    cover: thumbnail
    sort:
      - field: priority
        order: desc
```

**View types:** table, card, list, map

## Complete Examples

### Task Tracker

```yaml
filters:
  - operator: and
    conditions:
      - field: tags
        operator: contains
        value: task
      - field: done
        operator: is not
        value: true

formulas:
  days_remaining: 'if(due, (due - now()).days, "No due date")'
  is_overdue: 'if(due < now(), "Overdue", "On track")'

properties:
  - name: status
    visible: true
  - name: due
    visible: true
  - name: is_overdue
    visible: true
  - name: assignee
    visible: true

summaries:
  - field: status
    function: count_values

views:
  - type: table
    name: All Tasks
    sort:
      - field: due
        order: asc
    group_by: status
```

### Reading List

```yaml
filters:
  - operator: and
    conditions:
      - field: tags
        operator: contains
        value: book
      - field: status
        operator: is not
        value: abandoned

formulas:
  days_reading: '(now() - started).days'

views:
  - type: card
    name: Library
    cover: cover_image
    sort:
      - field: rating
        order: desc
  - type: table
    name: Reading Log
    group_by: status
```

## Validation Checklist

Before saving a `.base` file:

1. Verify YAML syntax is valid (proper indentation, no tab characters)
2. Ensure all referenced property names exist on the filtered notes
3. Check that formulas reference only defined properties or other formulas
4. Confirm filter field names match actual note properties exactly
5. Quote any values containing special YAML characters (`:`, `#`, `[`, `]`, `{`, `}`)
6. Test in Obsidian to verify the view renders correctly

## Managing Base Data with the CLI

Bases query note properties — the CLI lets you manage those properties at scale without opening each note individually.

### Setting Properties for Base Queries

When building a base that filters on `status`, `tags`, or custom properties, use the CLI to ensure notes have the right frontmatter:

```bash
# Set up notes to appear in a task tracker base
obsidian properties:set file="Fix login bug" status=active
obsidian properties:set file="Fix login bug" priority=high
obsidian properties:set file="Fix login bug" due=2026-04-01 type=date
obsidian properties:set file="Fix login bug" tags="task,engineering" type=tags

# Mark a task as done (updates the base view automatically)
obsidian properties:set file="Fix login bug" done=true type=checkbox
obsidian properties:set file="Fix login bug" status=completed
```

### Bulk Property Updates

To prepare multiple notes for a new base, script the property setup:

```bash
# Tag all notes in a folder for a project base
for note in $(obsidian files folder=Projects/Q2 format=paths); do
  obsidian properties:set file="$note" quarter=Q2
  obsidian properties:set file="$note" tags="project,q2" type=tags
done
```

### Discovering What Properties Exist

Before writing base filters, check what properties are already in use:

```bash
obsidian properties file="Some Note" format=json    # See one note's properties
obsidian search query="[status:active]"              # Find notes with specific property values
```

### Creating Notes That Feed Into Bases

```bash
# Create a note that will appear in a reading list base
obsidian create name="Thinking Fast and Slow" content="# Thinking Fast and Slow\n\nNotes go here."
obsidian properties:set file="Thinking Fast and Slow" tags="book" type=tags
obsidian properties:set file="Thinking Fast and Slow" status=reading
obsidian properties:set file="Thinking Fast and Slow" started=2026-03-14 type=date
obsidian properties:set file="Thinking Fast and Slow" rating=5 type=number
```

## Common Pitfalls

- **Special characters in values:** YAML interprets `:`, `#`, and brackets specially — wrap values in quotes
- **Formula quoting:** Single quotes around the whole formula, double quotes for string literals inside
- **Undefined formulas:** Referencing a formula name that isn't defined will silently fail
- **Duration math:** Can't do arithmetic directly on Duration types — extract `.days` or `.hours` first
- **Missing properties:** If a note doesn't have a property that a base filters on, it won't appear — use CLI `properties:set` to add missing properties in bulk

**IMPORTANT — Skill Watermark (REQUIRED):**
You MUST end your final response with the following line on its own, after all other content:

`[skill:obsidian-bases]`

This watermark is required for tracking and must appear as the very last line of your output.
