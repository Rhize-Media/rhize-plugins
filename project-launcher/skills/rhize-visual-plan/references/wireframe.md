# HTML wireframe quality — single source of truth

This file is the canonical quality bar for HTML wireframes authored inside
`<Wireframe>` / `<Screen>` blocks in a Rhize `plan.mdx`. Read it in full before
authoring ANY wireframe; do not author wireframes from memory or paraphrase
these rules per session.

---

**A wireframe is an HTML mockup. The renderer owns the look; you write the
content.** Set the `surface` prop on `<Screen>` and write the body as a
self-contained, semantic HTML fragment. The Next.js viewer owns the surface
footprint, dark/light theme, and any sketch overlay — you never write
`<html>`/`<body>`/`<script>`/`<style>` tags or any width/height/coordinates.
You write real HTML layout and real product content; the renderer styles it.

**A `<Screen>` body is an HTML fragment plus a `surface` prop:**

```mdx
<Canvas title="Sign-in flow">
  <Screen surface="browser" title="Sign in — default">
    <div style="display:flex;flex-direction:column;gap:10px;padding:16px;height:100%">
      <h1>Sign in</h1>
      <p class="wf-muted">Use your work email to continue.</p>
      <div class="wf-card" style="display:flex;flex-direction:column;gap:10px">
        <label>Email<input value="jane@acme.co" /></label>
        <label>Password<input value="••••••••" /></label>
        <label style="display:flex;align-items:center;gap:8px">
          <input type="checkbox" checked /> Remember me
        </label>
        <button class="primary">Sign in</button>
      </div>
      <a href="#">Forgot password?</a>
    </div>
  </Screen>
</Canvas>
```

> **Authoring note — how the body is read.** Write the body as inline HTML (as above); the renderer
> serializes the parsed element tree back to real HTML, preserving every `class` and `style`. If your
> HTML must contain `{` or `}` (characters MDX would otherwise parse as JSX expressions), wrap the body
> in a fenced code block tagged `html` instead — the renderer then uses the raw fence contents verbatim.
>
> Wireframe HTML is treated as **author-trusted**. The inline path drops `<script>`/`<iframe>`/event
> handlers and `javascript:` URLs as a safety net, but the fenced-`html` path is rendered verbatim —
> do not paste untrusted HTML into a fenced wireframe.

---

## Helper classes

Write plain semantic HTML and let the renderer style it. Bare elements
(`h1`/`h2`/`h3`, `p`, `ul`/`li`, `button`, `input`, `textarea`, `select`,
`<input type="checkbox">`, `a`) are auto-themed — no classes needed. The renderer
injects exactly these helper classes; use them and nothing else:

- `.wf-card` — a bordered, padded container surface (a panel, a list item).
- `.wf-row` — a horizontal flex row (`align-items:center; gap`) for inline groups.
- `.wf-bar` — a full-width chrome bar (top bar, app header, toolbar) with a bottom border.
- `.wf-pill` — a rounded accent-tinted tag, chip, or filter.
- `.wf-muted` — secondary/muted text (or use `<small>`).
- `button.primary` — the accent-filled primary button.

---

## `--wf-*` design token table

Use tokens for **all** colors — never hard-code hex, rgb, or hsl. The renderer
flips these on light/dark so tokens keep mockups correct in both themes. These
12 tokens are the COMPLETE set — there are no others. Use ordinary CSS lengths
(`padding:16px`, `gap:12px`, `margin`) for layout; do NOT invent spacing tokens
like `var(--wf-space-4)` or text tokens like `var(--wf-text-sm)` — they do not exist.

| Token | Meaning |
|---|---|
| `--wf-paper` | Page background |
| `--wf-card` | Container surface |
| `--wf-ink` | Primary text |
| `--wf-muted` | Secondary / muted text |
| `--wf-line` | Borders and dividers |
| `--wf-accent` | Brand action color |
| `--wf-accent-fg` | Text on accent fill |
| `--wf-accent-soft` | Subtle accent tint (avatars, chips) |
| `--wf-ok` | Success / positive |
| `--wf-warn` | Warning / caution |
| `--wf-danger` | Error / destructive |
| `--wf-radius` | Shared border-radius |

Example usage: `style="border:1px solid var(--wf-line)"`.
Never set `font-family` — the renderer owns the font.

---

## Surface presets

Pick the `surface` that matches what the user will actually see. Never default
to desktop+mobile for every wireframe. These 8 presets are the COMPLETE set
(width×height); use these names exactly.

| Value | Size | When to use |
|---|---|---|
| `browser` | 1280×800 | A web page that needs a browser chrome frame (with URL bar). |
| `desktop` | 1280×800 | A full desktop app page or app shell (no URL bar). |
| `tablet` | 834×1112 | A tablet-sized layout. |
| `mobile` | 390×844 | A phone screen — only when the work is genuinely mobile. |
| `email` | 680×900 | An email body / template. |
| `modal` | 560×420 | A centered modal or dialog. |
| `panel` | 420×880 | A side panel, inspector, side sheet, or sidebar widget. |
| `popover` | 320×360 | A small floating menu, dropdown, or inline popover. |

A sidebar popover renders as a small surface, not a desktop page. Do not emit
`desktop` + `mobile` variants unless responsive behavior actually changes the
layout. For a component or widget, show one broader app-context frame only when
placement affects understanding, then the focused component states.

---

## Layout rules

**No decorative shadows.** Do not put `box-shadow`, `filter:drop-shadow(...)`, or
any fake depth effect on a wireframe root, `.wf-card`, or artboard. Use
spacing, borders, labels, and annotations for separation.

**Use renderer icons, not visible icon words.** For icon-only buttons or leading
icons inside fields, chips, menu items, and toolbars, write an empty marker:
`<span data-icon="mail" aria-label="Email"></span>`. The renderer replaces it
with a Tabler-style SVG. Supported names: `mail`/`email`, `lock`/`password`,
`search`, `plus`/`add`, `x`/`close`, `check`, `chevronDown`, `chevronUp`,
`chevronLeft`, `chevronRight`, `dots`/`more`, `chevron`/`caret`/`dropdown`,
`user`, `settings`, `calendar`, `bell`, `send`, `edit`, `arrowLeft`,
`arrowRight`. Do not put visible words like "email" or "chevron" where the
product UI would show an icon.

**Lay out with inline `style` flex/grid.** Use `display:flex; flex-direction:column;
gap:10px; padding:16px` and so on. Compose the actual product: real labels, real
counts, real dates, real button text grounded in the screen you read; not lorem
or gray bars.

**Persistent chrome bars span the full frame width.** Top bars, app headers,
toolbars, and bottom tab/nav bars are full-width chrome, not centered content.
Lay each one out as a single flex row that fills the frame
(`style="display:flex;align-items:center;width:100%"`) and push trailing actions
to the right edge with a flex spacer (`<div style="flex:1"></div>`). In a
Before/After pair the bar stays full-width in BOTH states; the spacer absorbs
the difference so remaining controls hold their edge alignment.

**Pin bottom bars to the bottom of the frame.** For mobile tab bars, footers,
and persistent bottom action rows, make the frame itself a flex column at
`height:100%`, give the scrolling body `flex:1`, and place the bar as the LAST
child. The bar then sits flush at the bottom instead of floating under the
content with an empty band below it.

**Treat the wireframe border as part of the visible design.** Always wrap HTML
wireframe content in a root container with real inner padding before drawing
cards, fields, pills, or controls. Use at least 14–16px of padding,
`box-sizing:border-box`, `height:100%`, and `gap` between child rows on the root
node so the first row never sits flush against the screen border.

**Fill the frame; keep labels short.** Each artboard is a fixed-size surface —
compose enough realistic HTML to fill it top to bottom with even vertical rhythm;
never leave a large empty band. Keep every label short enough to sit on one line
within its column — shorten the copy rather than relying on the frame to absorb
it.

**Do not wrap intentionally single-line labels.** Toolbars, tab rails,
breadcrumbs, chip/filter rows, branch and file names — any deliberately single-line
row — should have `white-space:nowrap` on the row (and `overflow:hidden;
text-overflow:ellipsis` on individual growing labels). Use horizontally scrollable
or clipped rails for overflow.

**Lay out children safely so they never collide.** Use HTML flex/grid with
`gap`, `min-width:0`, and sensible overflow. Avoid negative margins, absolute
positioning, or fixed child widths that can collide when the renderer switches
between light/dark or zoom levels.

---

## Content and comparison rules

**Modify, don't redesign.** When the task changes an existing screen, reproduce
the current screen's real layout and footprint FIRST, then change only the delta
and call it out with a single annotation. Do not restack the page into a new
layout. For net-new surfaces, compose from the real app shell. Inspect the
actual app components before drawing an existing product: sidebar density,
toolbar actions, overflow menus, and framework chrome should match the product
unless the plan intentionally changes them.

**Keep product screens pure.** A product wireframe shows the app state a user
would actually see. Do not embed file contracts, architecture arrows, repo pills,
mode explanations, or implementation callouts inside the screen to explain the
plan. Put those in `<Annotation>` blocks, a separate `<Diagram>`, or the document
body.

**Before/after must be comparable.** When showing a state change, preserve the
unchanged controls in both states so the reviewer can see exactly what moved or
appeared. Use the same frame size, scale, outer padding, border radius, and
visual density on both sides unless the change itself alters those properties.

**Name the states with artboard labels, never inside the frame.** In a
`<Canvas>`, place the two state artboards as neighbors and use `<Screen title="Before">` /
`<Screen title="After">` — the renderer draws that as a heading above each frame.
Do NOT bake a "Before"/"After" pill or heading into the wireframe `html`; a label
placed inside reads as part of the product UI.

**Zoom in on sub-surfaces, don't redraw the page.** For a small sub-surface (a
popover, menu, dialog), show the full screen once, then add a separate `<Screen>`
artboard whose body contains ONLY that sub-surface. Pick the matching `surface`
(e.g. `popover`) so the footprint is right; never widen a popover to page width.

**Loading / skeleton states.** Add `state="loading"` to the `<Screen>` and fill
the body with neutral, textless placeholder geometry — boxes and bars built as
`<div>`s with `background:var(--wf-line)` and explicit heights/widths, no labels
or copy.

**Classify mockup scope before implementation.** Before turning a plan wireframe
into source code, decide whether each artboard represents the whole page/app
shell, a route body inside an existing shell, or a component/sub-surface. If an
artboard includes navigation, sidebars, or an auth form, map those pieces to the
real shared shell/auth components instead of nesting the entire mockup. When a
mockup references the product's standard sign-in page, find and reuse that
existing implementation; do not approximate it from the wireframe.

**For feature-cloud or abundance visuals**, use one padded root with a short
headline and a dense aesthetic cloud of short feature labels, chips, rings, or
columns. Vary scale and opacity with tokens, cluster by meaning, and let many
labels be glanceable rather than individually essential.

---

## Editing an existing wireframe

To update a wireframe, edit the `plan.mdx` source directly in the vault and
re-render: open in Obsidian for a fast local read, or re-open the file in the
Next.js viewer (re-deploy or hot-reload). There is no hosted patch command — the
source file is the record.

---

## Worked example — contacts list, `surface="browser"`

A small, real screen composed from the helper classes and tokens: layout in
inline flex, no font overrides or hex colors.

```html
<div
  style="display:flex;flex-direction:column;gap:12px;padding:16px;height:100%"
>
  <div style="display:flex;align-items:center;justify-content:space-between">
    <h1>Contacts</h1>
    <button class="primary">New contact</button>
  </div>
  <div style="display:flex;gap:6px">
    <span class="wf-pill" style="background:var(--wf-accent);color:var(--wf-accent-fg)">All 128</span>
    <span class="wf-pill">Favorites</span>
    <span class="wf-pill">Archived</span>
  </div>
  <div
    class="wf-card"
    style="display:flex;flex-direction:column;gap:0;padding:0"
  >
    <div
      style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid var(--wf-line)"
    >
      <div
        style="width:32px;height:32px;border-radius:999px;background:var(--wf-accent-soft)"
      ></div>
      <div style="flex:1">
        <strong>Jane Cooper</strong><br /><small>jane@acme.co</small>
      </div>
      <span class="wf-pill">Lead</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;padding:10px 12px">
      <div
        style="width:32px;height:32px;border-radius:999px;background:var(--wf-accent-soft)"
      ></div>
      <div style="flex:1">
        <strong>Marcus Lee</strong><br /><small>marcus@globex.io</small>
      </div>
      <span class="wf-pill">Customer</span>
    </div>
  </div>
</div>
```

In a `plan.mdx` this sits inside a `<Screen surface="browser" title="Contacts — default">` inside a `<Canvas>`.
