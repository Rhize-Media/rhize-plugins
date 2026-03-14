---
name: json-canvas
description: >
  Create and edit Obsidian canvas files (.canvas) following the JSON Canvas Spec 1.0
  with nodes, edges, groups, and visual connections. Use this skill when someone asks
  about creating or editing Obsidian canvases, building visual knowledge maps, node
  diagrams, mind maps in Obsidian, connecting notes visually, or working with .canvas
  files. Also triggers on "JSON Canvas", "canvas file", "visual board", "Obsidian
  whiteboard", or requests to create visual note connections.
---

# JSON Canvas (Obsidian Canvas Files)

Canvas files (`.canvas`) let you create spatial, visual layouts of notes, text, links, and groups with connections between them. They follow the [JSON Canvas Spec 1.0](https://jsoncanvas.org).

## File Structure

A canvas file is JSON with two top-level arrays:

```json
{
  "nodes": [],
  "edges": []
}
```

## Node Types

### Text Node
Contains inline markdown content.

```json
{
  "id": "a1b2c3d4e5f6g7h8",
  "type": "text",
  "x": 0,
  "y": 0,
  "width": 400,
  "height": 200,
  "text": "# Heading\n\nMarkdown content here.\n\n- List item\n- Another item",
  "color": "1"
}
```

### File Node
References a file in the vault.

```json
{
  "id": "b2c3d4e5f6g7h8i9",
  "type": "file",
  "x": 500,
  "y": 0,
  "width": 400,
  "height": 400,
  "file": "path/to/note.md",
  "subpath": "#Specific Heading"
}
```

The optional `subpath` can target a heading (`#Heading`) or block (`#^block-id`).

### Link Node
Embeds an external URL.

```json
{
  "id": "c3d4e5f6g7h8i9j0",
  "type": "link",
  "x": 1000,
  "y": 0,
  "width": 400,
  "height": 300,
  "url": "https://example.com"
}
```

### Group Node
Visual container that groups other nodes.

```json
{
  "id": "d4e5f6g7h8i9j0k1",
  "type": "group",
  "x": -50,
  "y": -50,
  "width": 1100,
  "height": 500,
  "label": "Research Phase",
  "background": "path/to/background.png",
  "backgroundStyle": "cover"
}
```

`backgroundStyle` options: `cover`, `ratio`, `repeat`

## Node Properties

All nodes share these required properties:

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique 16-character hex identifier |
| `type` | string | `text`, `file`, `link`, or `group` |
| `x` | number | Horizontal position (px) |
| `y` | number | Vertical position (px) |
| `width` | number | Width in pixels |
| `height` | number | Height in pixels |

Optional on all nodes:

| Property | Type | Description |
|----------|------|-------------|
| `color` | string | Preset `"1"`-`"6"` or hex `"#FF0000"` |

## Edges (Connections)

Edges draw visual lines between nodes.

```json
{
  "id": "e5f6g7h8i9j0k1l2",
  "fromNode": "a1b2c3d4e5f6g7h8",
  "toNode": "b2c3d4e5f6g7h8i9",
  "fromSide": "right",
  "toSide": "left",
  "fromEnd": "none",
  "toEnd": "arrow",
  "color": "3",
  "label": "relates to"
}
```

| Property | Required | Description |
|----------|----------|-------------|
| `id` | yes | Unique 16-character hex |
| `fromNode` | yes | Source node ID |
| `toNode` | yes | Target node ID |
| `fromSide` | no | `top`, `right`, `bottom`, `left` |
| `toSide` | no | `top`, `right`, `bottom`, `left` |
| `fromEnd` | no | `none` or `arrow` |
| `toEnd` | no | `none` or `arrow` |
| `color` | no | Same as node colors |
| `label` | no | Text label on the edge |

## ID Generation

All IDs must be unique 16-character hexadecimal strings. Generate them randomly:

```
Example: "a1b2c3d4e5f6g7h8"
```

IDs must be unique across all nodes AND edges in the same canvas.

## Layout Guidelines

- Space nodes 50-100px apart to avoid visual overlap
- Use consistent widths for similar node types (e.g., all text nodes at 400px wide)
- Group related nodes using group nodes with appropriate padding (~50px around contained nodes)
- Position nodes left-to-right or top-to-bottom for logical flow
- Use `\n` for line breaks in JSON text fields (not literal newlines)

## Complete Example

```json
{
  "nodes": [
    {
      "id": "a1b2c3d4e5f6g7h8",
      "type": "text",
      "x": 0,
      "y": 0,
      "width": 300,
      "height": 150,
      "text": "# Project Kickoff\n\nDefine scope and timeline",
      "color": "4"
    },
    {
      "id": "b2c3d4e5f6g7h8i9",
      "type": "file",
      "x": 400,
      "y": -50,
      "width": 300,
      "height": 200,
      "file": "Projects/Requirements.md"
    },
    {
      "id": "c3d4e5f6g7h8i9j0",
      "type": "file",
      "x": 400,
      "y": 200,
      "width": 300,
      "height": 200,
      "file": "Projects/Timeline.md"
    },
    {
      "id": "d4e5f6g7h8i9j0k1",
      "type": "group",
      "x": -50,
      "y": -100,
      "width": 800,
      "height": 550,
      "label": "Planning Phase"
    }
  ],
  "edges": [
    {
      "id": "e5f6g7h8i9j0k1l2",
      "fromNode": "a1b2c3d4e5f6g7h8",
      "toNode": "b2c3d4e5f6g7h8i9",
      "fromSide": "right",
      "toSide": "left",
      "toEnd": "arrow",
      "label": "defines"
    },
    {
      "id": "f6g7h8i9j0k1l2m3",
      "fromNode": "a1b2c3d4e5f6g7h8",
      "toNode": "c3d4e5f6g7h8i9j0",
      "fromSide": "right",
      "toSide": "left",
      "toEnd": "arrow",
      "label": "schedules"
    }
  ]
}
```

## Validation Checklist

Before saving a `.canvas` file:

1. Valid JSON syntax (check with a linter)
2. All IDs are unique 16-character hex strings
3. All edge `fromNode`/`toNode` references point to existing node IDs
4. No overlapping nodes at the same position
5. Group nodes are large enough to visually contain their children
6. Text content uses `\n` for newlines, not literal line breaks in JSON
