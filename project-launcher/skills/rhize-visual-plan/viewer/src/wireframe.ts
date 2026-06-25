/**
 * wireframe.ts — canonical --wf-* token CSS + the 8 surface presets, plus the
 * renderer-injected helper classes and the Tabler-style icon set used inside
 * <Wireframe>/<Screen> sandboxes.
 *
 * This is the VERBATIM canonical contract — it must match
 * references/wireframe.md exactly. The ONLY --wf-* tokens are semantic colors +
 * --wf-radius. There are NO spacing or font-size token scales: authors lay out
 * with ordinary CSS (flex, padding, margin) and the helper classes below.
 *
 * NOTE on rendering: the viewer renders wireframes INLINE (no iframe). The
 * `.rp-wf-doc` rules in styles.css are the live styling, and applyWireframeIcons()
 * swaps [data-icon] markers at runtime. WF_TOKEN_STYLE + buildIconScript below
 * remain the canonical token/icon contract — mirrored into styles.css `.rp-wf-doc`
 * and reused by the Next.js template's iframe sandbox (templates/mdx-components.tsx).
 */

export type WireframeSurface =
  | "browser"
  | "desktop"
  | "tablet"
  | "mobile"
  | "email"
  | "modal"
  | "panel"
  | "popover"
  | string; // allow custom/future presets

export const SURFACE_DIMENSIONS: Record<
  string,
  { width: number; minHeight: number; label: string }
> = {
  browser: { width: 1280, minHeight: 800, label: "Browser" },
  desktop: { width: 1280, minHeight: 800, label: "Desktop app" },
  tablet: { width: 834, minHeight: 1112, label: "Tablet" },
  mobile: { width: 390, minHeight: 844, label: "Mobile" },
  email: { width: 680, minHeight: 900, label: "Email" },
  modal: { width: 560, minHeight: 420, label: "Modal" },
  panel: { width: 420, minHeight: 880, label: "Side panel" },
  popover: { width: 320, minHeight: 360, label: "Popover" },
};

// Default surface used when a prop is omitted or an unknown name is passed.
export const DEFAULT_SURFACE: WireframeSurface = "browser";

// ---------------------------------------------------------------------------
// Token + base-element + helper-class CSS injected into every wireframe iframe.
// Includes a light/dark flip via prefers-color-scheme so wires stay correct in
// both themes (the tokens are the source of truth; only colors flip).
// ---------------------------------------------------------------------------
export const WF_TOKEN_STYLE = `:root{--wf-paper:#f6f7f9;--wf-card:#ffffff;--wf-ink:#1a1d23;--wf-muted:#6b7280;--wf-line:#e2e5ea;--wf-accent:#2563eb;--wf-accent-fg:#ffffff;--wf-accent-soft:#e8f0fe;--wf-ok:#16a34a;--wf-warn:#d97706;--wf-danger:#dc2626;--wf-radius:10px;}
@media (prefers-color-scheme: dark){:root{--wf-paper:#0f1115;--wf-card:#171a21;--wf-ink:#e6e8ec;--wf-muted:#9aa3af;--wf-line:#2a2f3a;--wf-accent:#3b82f6;--wf-accent-fg:#ffffff;--wf-accent-soft:#1d2740;--wf-ok:#22c55e;--wf-warn:#f59e0b;--wf-danger:#ef4444;}}
*{box-sizing:border-box}
html,body{margin:0}
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--wf-ink);background:var(--wf-paper);font-size:14px;line-height:1.45;padding:16px}
h1,h2,h3{margin:0 0 8px;font-weight:650;line-height:1.2}
h1{font-size:20px}h2{font-size:16px}h3{font-size:14px}
p{margin:0 0 8px}
small,.wf-muted{color:var(--wf-muted);font-size:12px}
.wf-card{background:var(--wf-card);border:1px solid var(--wf-line);border-radius:var(--wf-radius);padding:14px}
.wf-row{display:flex;align-items:center;gap:10px}
.wf-bar{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--wf-card);border-bottom:1px solid var(--wf-line)}
.wf-pill{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;background:var(--wf-accent-soft);color:var(--wf-accent);font-size:12px;font-weight:600}
button{font:inherit;padding:7px 12px;border:1px solid var(--wf-line);border-radius:8px;background:var(--wf-card);color:var(--wf-ink);cursor:pointer}
button.primary{background:var(--wf-accent);border-color:var(--wf-accent);color:var(--wf-accent-fg)}
input,textarea,select{font:inherit;padding:7px 10px;border:1px solid var(--wf-line);border-radius:8px;background:var(--wf-card);color:var(--wf-ink);width:100%}
input[type="checkbox"],input[type="radio"]{width:auto}
ul{margin:0 0 8px;padding-left:18px}
a{color:var(--wf-accent);text-decoration:none}
svg[data-wf-icon]{width:1em;height:1em;vertical-align:-0.125em;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}`;

// ---------------------------------------------------------------------------
// Tabler-style icon paths. Authors write <span data-icon="mail"></span> in the
// wireframe HTML; the injected script (below) swaps each marker for the SVG.
// Names match references/wireframe.md.
// ---------------------------------------------------------------------------
const ICON_PATHS: Record<string, string> = {
  mail: '<path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="m3 7 9 6 9-6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="m5 12 5 5L20 7"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  chevronUp: '<path d="m6 15 6-6 6 6"/>',
  chevronLeft: '<path d="m15 6-6 6 6 6"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  dots: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  settings:
    '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  calendar:
    '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  arrowLeft: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
  arrowRight: '<path d="M5 12h14M12 5l7 7-7 7"/>',
};

// Aliases from references/wireframe.md
const ICON_ALIASES: Record<string, string> = {
  email: "mail",
  password: "lock",
  add: "plus",
  close: "x",
  more: "dots",
  chevron: "chevronDown",
  caret: "chevronDown",
  dropdown: "chevronDown",
};

function resolveIconName(name: string): string {
  return ICON_ALIASES[name] ?? name;
}

/**
 * Build the icon-replacement script injected into each wireframe iframe.
 * It walks for [data-icon] markers and replaces each with an inline SVG.
 * Serialized as a JSON map so the script stays self-contained (offline-safe).
 */
export function buildIconScript(): string {
  const merged: Record<string, string> = {};
  for (const [k, v] of Object.entries(ICON_PATHS)) merged[k] = v;
  // Pre-resolve aliases into the same map so the runtime lookup is a single hit.
  for (const [alias, target] of Object.entries(ICON_ALIASES)) {
    if (ICON_PATHS[target]) merged[alias] = ICON_PATHS[target];
  }
  const json = JSON.stringify(merged);
  return (
    `<script>(function(){var P=${json};` +
    `function svg(name){var p=P[name];if(!p)return null;` +
    `return '<svg data-wf-icon viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'+p+'</svg>';}` +
    `document.querySelectorAll('[data-icon]').forEach(function(el){` +
    `var n=el.getAttribute('data-icon');var s=svg(n);if(s){el.innerHTML=s;}});` +
    `})();<\/script>`
  );
}

/**
 * Inline-render equivalent of buildIconScript: swap every [data-icon="name"]
 * marker inside a live wireframe root for an inline Tabler SVG. Used by the
 * inline WireframeSandbox (the iframe path is retired — see mermaid.tsx).
 */
export function applyWireframeIcons(root: ParentNode): void {
  const merged: Record<string, string> = {};
  for (const [k, v] of Object.entries(ICON_PATHS)) merged[k] = v;
  for (const [alias, target] of Object.entries(ICON_ALIASES)) {
    if (ICON_PATHS[target]) merged[alias] = ICON_PATHS[target];
  }
  root.querySelectorAll("[data-icon]").forEach((el) => {
    const name = el.getAttribute("data-icon") || "";
    const path = merged[name];
    if (path) {
      el.innerHTML =
        `<svg data-wf-icon viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${path}</svg>`;
    }
  });
}

// Re-export so callers don't need to know about the alias table.
export { resolveIconName };
