/**
 * mdx-components.tsx — Rhize plan component map for next-mdx-remote
 *
 * COPY TO: lib/plan-components.tsx (or app/plan-components.tsx) in your Next.js app.
 *
 * npm install next-mdx-remote gray-matter mermaid @tailwindcss/typography
 * (mermaid is imported dynamically on the client — no SSR bundle impact)
 *
 * Several components (DataModel, ApiEndpoint, Decision, OpenQuestions) wrap their
 * Markdown children in Tailwind `prose` classes, so this file requires the
 * @tailwindcss/typography plugin. Enable it in your Tailwind config:
 *   // tailwind.config.ts
 *   plugins: [require("@tailwindcss/typography")]
 * Without the plugin, the `prose` classes are no-ops and tables/lists render unstyled.
 *
 * Usage:
 *   import { planComponents } from "@/lib/plan-components";
 *   const { content } = await compileMDX({ source, components: planComponents, options: { parseFrontmatter: true } });
 *
 * All components degrade gracefully: if props are absent they still render their children.
 *
 * --wf-* wireframe design tokens:
 *   These tokens are defined in WF_TOKEN_STYLE (below) and injected into the <head> of every
 *   <Wireframe>/<Screen> iframe sandbox. They are the source of truth for all wireframe rendering.
 *   references/wireframe.md is the canonical contract for the token/surface/state vocabulary —
 *   keep this file and that document in lock-step.
 */

"use client"; // <-- the MermaidRenderer and WireframeSandbox components are client components; the rest are RSC-compatible.
// Next.js will hoist the "use client" boundary automatically when mixed in an MDX components map.
// If your setup requires pure RSC, extract MermaidRenderer + WireframeSandbox into their own
// 'use client' file and import them here without the directive on this file.

import React, { useEffect, useRef, useState, type ReactNode, type CSSProperties } from "react";

// ---------------------------------------------------------------------------
// Wireframe design tokens + base element styling — injected into the <head> of
// every sandboxed iframe. This is the verbatim canonical contract; it must match
// references/wireframe.md exactly. The ONLY --wf-* tokens are semantic colors +
// --wf-radius. There are NO spacing or font-size token scales: authors lay out
// with ordinary CSS (flex, padding, margin) and the helper classes below.
// ---------------------------------------------------------------------------
const WF_TOKEN_STYLE = `:root{--wf-paper:#f6f7f9;--wf-card:#ffffff;--wf-ink:#1a1d23;--wf-muted:#6b7280;--wf-line:#e2e5ea;--wf-accent:#2563eb;--wf-accent-fg:#ffffff;--wf-accent-soft:#e8f0fe;--wf-ok:#16a34a;--wf-warn:#d97706;--wf-danger:#dc2626;--wf-radius:10px;}
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
ul{margin:0 0 8px;padding-left:18px}
a{color:var(--wf-accent);text-decoration:none}`;

// ---------------------------------------------------------------------------
// Surface presets for <Wireframe>/<Screen> — the ONE canonical list. Names and
// dimensions must match references/wireframe.md exactly.
// ---------------------------------------------------------------------------
type WireframeSurface =
  | "browser"
  | "desktop"
  | "tablet"
  | "mobile"
  | "email"
  | "modal"
  | "panel"
  | "popover"
  | string; // allow custom/future presets

const SURFACE_DIMENSIONS: Record<WireframeSurface, { width: number; minHeight: number; label: string }> = {
  browser: { width: 1280, minHeight: 800, label: "Browser" },
  desktop: { width: 1280, minHeight: 800, label: "Desktop app" },
  tablet:  { width: 834,  minHeight: 1112, label: "Tablet" },
  mobile:  { width: 390,  minHeight: 844, label: "Mobile" },
  email:   { width: 680,  minHeight: 900, label: "Email" },
  modal:   { width: 560,  minHeight: 420, label: "Modal" },
  panel:   { width: 420,  minHeight: 880, label: "Side panel" },
  popover: { width: 320,  minHeight: 360, label: "Popover" },
};

// Default surface used when a prop is omitted or an unknown name is passed.
const DEFAULT_SURFACE: WireframeSurface = "browser";

// ---------------------------------------------------------------------------
// Helper: extract raw text from React children (for MDX fenced-code blocks)
// ---------------------------------------------------------------------------
function extractText(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(extractText).join("");
  if (React.isValidElement(children)) {
    const el = children as React.ReactElement<{ children?: ReactNode }>;
    return extractText(el.props.children);
  }
  return "";
}

// ---------------------------------------------------------------------------
// Wireframe HTML extraction — the body of <Screen>/<Wireframe> is HTML, NOT a
// code string. Authors may write it two ways:
//   (a) inline HTML-as-JSX:    <Screen><div class="wf-bar">…</div></Screen>
//   (b) a fenced ```html block: <Screen>```html …raw html… ```</Screen>
// (a) MDX hands Screen a tree of React elements (attributes preserved: `class`,
//     string `style`, `data-icon`, …); we serialize it BACK to an HTML string.
//     `extractText` alone is wrong for Screen — it discards every tag/class/style
//     and leaves bare run-together text.
// (b) MDX parses the fence as <pre><code> whose text IS the raw HTML; take it
//     directly. Use a fence for HTML with JSX-hostile characters (`{`, `}`).
// The result is fed to WireframeSandbox.
// ---------------------------------------------------------------------------

const VOID_ELEMENTS = new Set([
  "area", "base", "br", "col", "embed", "hr", "img", "input",
  "link", "meta", "param", "source", "track", "wbr",
]);

// Behavior-bearing elements have no place in a layout wireframe — drop subtree.
const BLOCKED_TAGS = new Set([
  "script", "iframe", "object", "embed", "base", "meta", "link", "noscript",
]);
const URL_ATTRS = new Set([
  "href", "src", "xlink:href", "formaction", "action", "poster", "background",
]);
function isUnsafeUrl(value: string): boolean {
  const v = value.replace(/[\s ]+/g, "").toLowerCase();
  return v.startsWith("javascript:") || v.startsWith("vbscript:") || v.startsWith("data:text/html");
}
// Unitless CSS props — emitting px would invalidate them (e.g. opacity:1px).
const UNITLESS_PROPS = new Set([
  "opacity", "zIndex", "fontWeight", "lineHeight", "flex", "flexGrow",
  "flexShrink", "order", "gridColumn", "gridRow", "columnCount",
  "fillOpacity", "strokeOpacity", "aspectRatio",
]);

function styleObjectToString(style: Record<string, unknown>): string {
  return Object.entries(style)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => {
      const prop = k.startsWith("--") ? k : k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`);
      const val = typeof v === "number" && !UNITLESS_PROPS.has(k) ? `${v}px` : String(v);
      return `${prop}:${val}`;
    })
    .join(";");
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function escapeHtmlText(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function htmlAttrName(name: string): string {
  if (name === "className") return "class";
  if (name === "htmlFor") return "for";
  return name;
}

/** Serialize MDX-parsed React children (inline HTML-as-JSX) back to an HTML string. */
export function serializeChildrenToHtml(node: ReactNode): string {
  if (node == null || node === false || node === true) return "";
  if (typeof node === "string") return escapeHtmlText(node);
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(serializeChildrenToHtml).join("");
  if (React.isValidElement(node)) {
    const el = node as React.ReactElement<{ children?: ReactNode } & Record<string, unknown>>;
    const { type, props } = el;
    if (typeof type !== "string") return serializeChildrenToHtml(props?.children as ReactNode);
    if (BLOCKED_TAGS.has(type.toLowerCase())) return "";

    const attrs: string[] = [];
    for (const [key, value] of Object.entries(props)) {
      if (key === "children" || key === "key" || key === "ref") continue;
      if (value == null || value === false) continue;
      if (/^on[a-z]/i.test(key)) continue;
      if (key === "style") {
        const css = typeof value === "string"
          ? value
          : styleObjectToString(value as Record<string, unknown>);
        if (css) attrs.push(`style="${escapeAttr(css)}"`);
        continue;
      }
      const name = htmlAttrName(key);
      if (URL_ATTRS.has(name.toLowerCase()) && typeof value === "string" && isUnsafeUrl(value)) continue;
      if (value === true) { attrs.push(name); continue; }
      attrs.push(`${name}="${escapeAttr(String(value))}"`);
    }
    const attrStr = attrs.length ? ` ${attrs.join(" ")}` : "";
    if (VOID_ELEMENTS.has(type)) return `<${type}${attrStr} />`;
    return `<${type}${attrStr}>${serializeChildrenToHtml(props.children)}</${type}>`;
  }
  return "";
}

function soleCodeBlock(children: ReactNode): React.ReactElement | null {
  const arr = React.Children.toArray(children).filter(
    (c) => !(typeof c === "string" && c.trim() === ""),
  );
  if (arr.length === 1 && React.isValidElement(arr[0])) {
    const el = arr[0] as React.ReactElement;
    if (el.type === "pre" || el.type === "code") return el;
  }
  return null;
}

/** Resolve a <Screen> body to a raw HTML string (fenced path or inline-JSX path). */
export function wireframeHtml(children: ReactNode): string {
  const block = soleCodeBlock(children);
  if (block) {
    return extractText(block)
      .replace(/^```\w*\s*/i, "")
      .replace(/```\s*$/, "")
      .trim();
  }
  return serializeChildrenToHtml(children).trim();
}

// ---------------------------------------------------------------------------
// STATUS BADGE — shared across Diagram, Decision, DataModel, ApiEndpoint
// ---------------------------------------------------------------------------
const STATUS_COLORS: Record<string, string> = {
  draft:       "bg-gray-100 text-gray-700",
  "in-review": "bg-yellow-100 text-yellow-800",
  approved:    "bg-green-100 text-green-800",
  superseded:  "bg-red-100 text-red-700",
  decided:     "bg-blue-100 text-blue-800",
  open:        "bg-orange-100 text-orange-800",
};

function StatusBadge({ label }: { label: string }) {
  const cls = STATUS_COLORS[label] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${cls}`}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// METHOD BADGE — for ApiEndpoint
// ---------------------------------------------------------------------------
const METHOD_COLORS: Record<string, string> = {
  GET:    "bg-green-100 text-green-800",
  POST:   "bg-blue-100 text-blue-800",
  PUT:    "bg-yellow-100 text-yellow-800",
  PATCH:  "bg-orange-100 text-orange-800",
  DELETE: "bg-red-100 text-red-800",
};

function MethodBadge({ method }: { method: string }) {
  const cls = METHOD_COLORS[method.toUpperCase()] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-block px-2 py-1 rounded font-mono text-xs font-bold ${cls}`}>
      {method.toUpperCase()}
    </span>
  );
}

// ---------------------------------------------------------------------------
// FILE-MAP BADGE — for FileMap
// ---------------------------------------------------------------------------
const FILE_ACTION_STYLES: Record<string, string> = {
  add:    "text-green-700 bg-green-50",
  edit:   "text-blue-700 bg-blue-50",
  delete: "text-red-700 bg-red-50",
};

// ---------------------------------------------------------------------------
// MERMAID DIAGRAM (client component — dynamically imports mermaid)
// ---------------------------------------------------------------------------
// We isolate this into a separate component so the rest of the map is RSC-safe.
// mermaid calls `document` and `window`; it must run on the client only.
function MermaidRenderer({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    import("mermaid").then(({ default: mermaid }) => {
      if (cancelled || !ref.current) return;
      mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
      const id = `mermaid-${Math.random().toString(36).slice(2)}`;
      mermaid
        .render(id, code)
        .then(({ svg }) => {
          if (ref.current && !cancelled) {
            ref.current.innerHTML = svg;
          }
        })
        .catch((err) => {
          if (ref.current && !cancelled) {
            ref.current.textContent = `Mermaid error: ${String(err)}`;
          }
        });
    });
    return () => { cancelled = true; };
  }, [code]);

  return (
    <div
      ref={ref}
      className="overflow-x-auto py-2 [&_svg]:max-w-full [&_svg]:h-auto"
      aria-label="Diagram"
    />
  );
}

// ---------------------------------------------------------------------------
// WIREFRAME SANDBOX FRAME (client component — listens for the iframe's resize message)
// We use an <iframe srcdoc> here rather than dangerouslySetInnerHTML for two reasons:
//   1. Style isolation: the outer page's Tailwind utilities and CSS resets cannot bleed into
//      the wireframe HTML, which uses --wf-* tokens and the renderer-injected helper classes.
//   2. Script isolation: any inline script in the wireframe HTML fragment (e.g. a toggle button)
//      is sandboxed. We allow 'allow-same-origin' so token CSS vars resolve within the frame,
//      and 'allow-scripts' so interactive demos (and our auto-resize bridge) work. "allow-forms"
//      and "allow-popups" are intentionally omitted.
// An alternative (tightly-scoped wrapper div with CSS layers) avoids iframes but cannot
// reliably prevent Tailwind base/reset bleed without a Shadow DOM — which Next.js RSC
// doesn't support. The iframe approach is safer and more predictable for copy-paste wires.
//
// AUTO-RESIZE: the srcDoc embeds a tiny script that posts the document's scrollHeight back to
// the parent (on load + on resize). The parent listens for that message — matched by the frame's
// unique id — and sets the iframe height to the reported content height so nothing clips and no
// empty band is left below. For wide surfaces we still scale-to-fit, and the final rendered
// height is the SCALED content height so the layout reserves exactly the visible space.
// ---------------------------------------------------------------------------
function WireframeSandbox({
  html,
  title,
  surface = DEFAULT_SURFACE,
}: {
  html: string;
  title: string;
  surface: WireframeSurface;
}) {
  const preset = SURFACE_DIMENSIONS[surface] ?? SURFACE_DIMENSIONS[DEFAULT_SURFACE];

  // Scale wide surfaces down to the prose column (max 720px wide) without horizontal scroll.
  const MAX_DISPLAY_WIDTH = 720;
  const scale = preset.width > MAX_DISPLAY_WIDTH ? MAX_DISPLAY_WIDTH / preset.width : 1;

  // A stable, unique frame id so the parent only reacts to its own iframe's message.
  const frameId = useRef(`wf-${Math.random().toString(36).slice(2)}`).current;

  // contentHeight is the iframe's reported scrollHeight (unscaled). Seed with the preset
  // minHeight so the frame reserves sensible space before the first message arrives.
  const [contentHeight, setContentHeight] = useState(preset.minHeight);

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const data = e.data as { __wfFrame?: string; height?: number } | undefined;
      if (!data || data.__wfFrame !== frameId || typeof data.height !== "number") return;
      // Never collapse below the preset minHeight.
      setContentHeight(Math.max(data.height, preset.minHeight));
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [frameId, preset.minHeight]);

  // The resize bridge, injected at the end of <body>.
  const resizeScript =
    `<script>(function(){` +
    `var id=${JSON.stringify(frameId)};` +
    `function post(){parent.postMessage({__wfFrame:id,height:document.documentElement.scrollHeight},"*");}` +
    `window.addEventListener("load",post);` +
    `window.addEventListener("resize",post);` +
    `setTimeout(post,50);` +
    `})();<\/script>`;

  const srcDoc =
    `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">` +
    `<style>${WF_TOKEN_STYLE}</style></head><body>${html}${resizeScript}</body></html>`;

  // The iframe renders at full internal resolution, then we scale the whole element. The OUTER
  // wrapper is sized to the SCALED content (width and height) so the bordered box hugs the visible
  // frame and siblings sit flush — no overlap below, no empty band, no horizontal scroll.
  const scaledHeight = Math.round(contentHeight * scale);
  const scaledWidth = Math.round(preset.width * scale);

  const frameStyle: CSSProperties = {
    width: preset.width,
    height: contentHeight,
    transform: scale !== 1 ? `scale(${scale})` : undefined,
    transformOrigin: "top left",
    border: "none",
    display: "block",
  };

  return (
    <div
      className="border border-gray-200 rounded-lg overflow-hidden bg-white"
      style={{ width: scaledWidth, maxWidth: "100%", height: scaledHeight }}
    >
      <iframe
        title={title}
        srcDoc={srcDoc}
        sandbox="allow-same-origin allow-scripts"
        style={frameStyle}
        scrolling="no"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// COMPONENT IMPLEMENTATIONS
// ---------------------------------------------------------------------------

// <Diagram title="..." caption="...">```mermaid ... ```</Diagram>
function Diagram({
  title,
  caption,
  children,
}: {
  title?: string;
  caption?: string;
  children?: ReactNode;
}) {
  const raw = extractText(children);
  // Strip the wrapping ```mermaid ... ``` fence if present (MDX may pass it already stripped)
  const code = raw
    .replace(/^```mermaid\s*/i, "")
    .replace(/```\s*$/, "")
    .trim();

  return (
    <figure className="my-6 rounded-lg border border-gray-200 bg-gray-50 p-4 overflow-hidden">
      {title && (
        <figcaption className="text-sm font-semibold text-gray-700 mb-3">{title}</figcaption>
      )}
      <MermaidRenderer code={code} />
      {caption && (
        <p className="text-xs text-gray-500 mt-2">{caption}</p>
      )}
    </figure>
  );
}

// <FileMap root="app/">...</FileMap>
// Children: a Markdown list. Each item names a path and the verb, with the verb marked
// as a leading bold tag, e.g.:
//   - **add** `app/plans/[slug]/page.tsx` — server route, reads plan.mdx
// We render the child Markdown list as-is inside a styled container and tint any leading
// **add** / **edit** / **delete** <strong> if it is trivially the first child of an <li>.
// If the bold verb is absent we render the item unchanged — never break.
function FileMap({ root, children }: { root?: string; children?: ReactNode }) {
  return (
    <div className="my-6 rounded-lg border border-gray-200 overflow-hidden">
      {root && (
        <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex items-center gap-2">
          <span className="text-xs font-mono text-gray-500">root:</span>
          <span className="text-xs font-mono font-semibold text-gray-800">{root}</span>
        </div>
      )}
      {/* Render the authored Markdown list directly; tint the leading bold verb where present. */}
      <div
        className="px-4 py-3 text-sm
          [&_ul]:list-none [&_ul]:m-0 [&_ul]:p-0 [&_ul]:divide-y [&_ul]:divide-gray-100
          [&_li]:py-2 [&_li]:text-gray-700 [&_li]:font-mono [&_li]:leading-relaxed
          [&_code]:text-gray-800
          [&_.wf-verb]:inline-block [&_.wf-verb]:mr-2 [&_.wf-verb]:px-1.5 [&_.wf-verb]:py-0.5
          [&_.wf-verb]:rounded [&_.wf-verb]:text-xs [&_.wf-verb]:font-semibold [&_.wf-verb]:font-sans"
      >
        {tintFileMapVerbs(children)}
      </div>
    </div>
  );
}

// Tint a leading **add** / **edit** / **delete** <strong> inside each <li>. This only touches
// a <strong> that is the first meaningful child of an <li> and whose text is a known verb; any
// other markup passes through untouched. Robust by design: no flat-string regex, no <li> rewrite.
function tintFileMapVerbs(children: ReactNode): ReactNode {
  function walk(node: ReactNode): ReactNode {
    if (!React.isValidElement(node)) return node;
    const el = node as React.ReactElement<{ children?: ReactNode; className?: string }>;

    if (el.type === "li") {
      const kids = React.Children.toArray(el.props.children);
      const firstIdx = kids.findIndex((k) => !(typeof k === "string" && k.trim() === ""));
      const first = kids[firstIdx];
      if (React.isValidElement(first) && (first.type === "strong" || first.type === "b")) {
        const strongEl = first as React.ReactElement<{ children?: ReactNode; className?: string }>;
        const verb = extractText(strongEl.props.children).trim().toLowerCase();
        const tint = FILE_ACTION_STYLES[verb];
        if (tint) {
          const tinted = React.cloneElement(strongEl, {
            className: `wf-verb ${tint} ${strongEl.props.className ?? ""}`.trim(),
          });
          const nextKids = kids.slice();
          nextKids[firstIdx] = tinted;
          return React.cloneElement(el, {}, nextKids);
        }
      }
      return node; // verb absent or unrecognized — leave the item exactly as authored
    }

    if (el.props.children) {
      return React.cloneElement(el, {}, React.Children.map(el.props.children, walk));
    }
    return node;
  }
  return <>{React.Children.map(children, walk)}</>;
}

// <DataModel name="Plan" store="sanity|payload|supabase|type">...</DataModel>
function DataModel({
  name,
  store,
  children,
}: {
  name?: string;
  store?: string;
  children?: ReactNode;
}) {
  const storeBadgeColors: Record<string, string> = {
    sanity:  "bg-orange-100 text-orange-800",
    payload: "bg-purple-100 text-purple-800",
    supabase:"bg-emerald-100 text-emerald-800",
    type:    "bg-indigo-100 text-indigo-800",
  };
  const badgeCls = store ? (storeBadgeColors[store] ?? "bg-gray-100 text-gray-700") : undefined;

  return (
    <div className="my-6 rounded-lg border border-gray-200 overflow-hidden">
      <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex items-center gap-2">
        {name && <span className="text-sm font-semibold text-gray-800">{name}</span>}
        {store && badgeCls && (
          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${badgeCls}`}>{store}</span>
        )}
      </div>
      {/* Render the table/code children with Tailwind table overrides */}
      <div className="px-4 py-3 text-sm prose prose-sm max-w-none [&_table]:w-full [&_th]:text-left [&_th]:font-semibold [&_th]:text-gray-600 [&_td]:py-1 [&_tr]:border-b [&_tr]:border-gray-100">
        {children}
      </div>
    </div>
  );
}

// <ApiEndpoint method="GET" path="/api/plans/[slug]" auth="session">...</ApiEndpoint>
function ApiEndpoint({
  method = "GET",
  path,
  auth,
  children,
}: {
  method?: string;
  path?: string;
  auth?: string;
  children?: ReactNode;
}) {
  return (
    <div className="my-6 rounded-lg border border-gray-200 overflow-hidden">
      <div className="bg-gray-50 px-4 py-2.5 border-b border-gray-200 flex items-center gap-3 flex-wrap">
        <MethodBadge method={method} />
        {path && <code className="font-mono text-sm font-semibold text-gray-800">{path}</code>}
        {auth && (
          <span className="ml-auto text-xs text-gray-500">
            auth: <span className="font-semibold text-gray-700">{auth}</span>
          </span>
        )}
      </div>
      <div className="px-4 py-3 prose prose-sm max-w-none text-sm">{children}</div>
    </div>
  );
}

// <Screen surface="browser" title="..." state="default|empty|loading|error">
// HTML fragment body using --wf-* tokens + helper classes. Rendered via <WireframeSandbox>.
function Screen({
  surface = DEFAULT_SURFACE,
  title,
  state,
  children,
}: {
  surface?: WireframeSurface;
  title?: string;
  state?: string;
  children?: ReactNode;
}) {
  const html = wireframeHtml(children);
  const preset = SURFACE_DIMENSIONS[surface] ?? SURFACE_DIMENSIONS[DEFAULT_SURFACE];
  const stateLabel = state && state !== "default" ? state : undefined;

  return (
    <div className="my-4 flex flex-col gap-1">
      {(title || stateLabel) && (
        <div className="flex items-center gap-2 text-xs text-gray-500 font-medium mb-1">
          {title && <span>{title}</span>}
          {stateLabel && <StatusBadge label={stateLabel} />}
          <span className="ml-auto text-gray-400">{preset.label}</span>
        </div>
      )}
      <WireframeSandbox html={html} title={title ?? "Screen"} surface={surface} />
    </div>
  );
}

// <Wireframe ...> is an alias for <Screen> (same props)
const Wireframe = Screen;

// <Canvas title="..." lanes="auth,viewer">
// Lays out <Screen> children in a horizontal lane grid with an optional lanes header.
function Canvas({
  title,
  lanes,
  children,
}: {
  title?: string;
  lanes?: string;
  children?: ReactNode;
}) {
  const laneNames = lanes ? lanes.split(",").map((l) => l.trim()) : [];

  return (
    <section className="my-8">
      {title && (
        <h3 className="text-base font-semibold text-gray-800 mb-3">{title}</h3>
      )}
      {laneNames.length > 0 && (
        <div
          className="grid border-b border-gray-200 pb-2 mb-4"
          style={{ gridTemplateColumns: `repeat(${laneNames.length}, 1fr)` }}
        >
          {laneNames.map((lane) => (
            <div key={lane} className="text-xs font-medium text-gray-400 uppercase tracking-wider text-center">
              {lane}
            </div>
          ))}
        </div>
      )}
      {/* Artboards scroll horizontally on overflow */}
      <div className="flex gap-6 overflow-x-auto pb-4">{children}</div>
    </section>
  );
}

// <Annotation target="Screen title" placement="right|below|above">
function Annotation({
  target,
  placement = "right",
  children,
}: {
  target?: string;
  placement?: string;
  children?: ReactNode;
}) {
  return (
    <aside className="my-2 flex gap-2 items-start text-sm text-gray-600 bg-yellow-50 border border-yellow-200 rounded px-3 py-2">
      <span className="text-yellow-500 mt-0.5 shrink-0">↑</span>
      <div>
        {target && (
          <span className="font-semibold text-gray-700 mr-1">{target}</span>
        )}
        <span className="text-gray-500 text-xs mr-1">({placement})</span>
        {children}
      </div>
    </aside>
  );
}

// <Decision title="..." status="decided|open">
function Decision({
  title,
  status = "open",
  children,
}: {
  title?: string;
  status?: string;
  children?: ReactNode;
}) {
  const borderColor = status === "decided" ? "border-blue-400" : "border-orange-400";
  const bgColor    = status === "decided" ? "bg-blue-50"    : "bg-orange-50";

  return (
    <div className={`my-6 rounded-lg border-l-4 ${borderColor} ${bgColor} px-5 py-4`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-bold text-gray-800">Decision</span>
        {title && <span className="text-sm font-semibold text-gray-700">— {title}</span>}
        <StatusBadge label={status} />
      </div>
      <div className="prose prose-sm max-w-none text-sm text-gray-700">{children}</div>
    </div>
  );
}

// <Diff file="path/to/file.tsx" lang="tsx">```diff ... ```</Diff>
// Wide surface — allowed to exceed prose width (use full-bleed wrapper class in your layout).
function Diff({
  file,
  lang = "diff",
  children,
}: {
  file?: string;
  lang?: string;
  children?: ReactNode;
}) {
  return (
    <div className="my-6 rounded-lg border border-gray-200 overflow-hidden w-full">
      {file && (
        <div className="bg-gray-900 px-4 py-2 flex items-center gap-2">
          <span className="text-xs font-mono text-gray-300">{file}</span>
          {lang && <span className="ml-auto text-xs text-gray-500">{lang}</span>}
        </div>
      )}
      {/* Syntax highlight is intentionally omitted here to keep the dep count minimal.
          To add it: install `shiki` or `react-syntax-highlighter` and wrap the code string.
          The raw <pre><code> from MDX will still be readable. */}
      <div className="overflow-x-auto bg-gray-950 text-gray-100 text-sm font-mono
        [&_pre]:m-0 [&_pre]:p-4 [&_pre]:overflow-x-auto
        [&_.line-add]:bg-green-900/40 [&_.line-remove]:bg-red-900/40">
        {children}
      </div>
    </div>
  );
}

// <AnnotatedCode file="..." lang="...">```ts ... // >> note```</AnnotatedCode>
// Renders trailing `// >> annotation` comments as gutter callouts.
function AnnotatedCode({
  file,
  lang,
  children,
}: {
  file?: string;
  lang?: string;
  children?: ReactNode;
}) {
  const raw = extractText(children)
    .replace(/^```\w*\s*/i, "")
    .replace(/```\s*$/, "")
    .trim();

  const lines = raw.split("\n").map((line, i) => {
    const annotationMatch = line.match(/^(.*?)\/\/\s*>>\s*(.+)$/);
    if (annotationMatch) {
      const [, code, note] = annotationMatch;
      return (
        <div key={i} className="flex gap-0">
          <span className="flex-1 whitespace-pre">{code}</span>
          <span className="text-yellow-400 text-xs ml-4 flex items-center shrink-0">◀ {note}</span>
        </div>
      );
    }
    return (
      <div key={i} className="whitespace-pre">{line}</div>
    );
  });

  return (
    <div className="my-6 rounded-lg border border-gray-200 overflow-hidden w-full">
      {file && (
        <div className="bg-gray-900 px-4 py-2 flex items-center gap-2">
          <span className="text-xs font-mono text-gray-300">{file}</span>
          {lang && <span className="ml-auto text-xs text-gray-500">{lang}</span>}
        </div>
      )}
      <div className="overflow-x-auto bg-gray-950 text-gray-100 text-sm font-mono p-4">
        {lines}
      </div>
    </div>
  );
}

// <OpenQuestions> — exactly one per plan, at the bottom
function OpenQuestions({ children }: { children?: ReactNode }) {
  return (
    <section className="my-8 rounded-lg border border-gray-200 bg-gray-50 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-200 flex items-center gap-2">
        <span className="text-base font-semibold text-gray-800">Open Questions</span>
        <span className="text-xs text-gray-400 ml-1">— resolve before approval</span>
      </div>
      <div className="px-5 py-4 prose prose-sm max-w-none text-sm
        [&_ul]:list-none [&_ul]:space-y-3 [&_ul]:p-0
        [&_li]:border-l-2 [&_li]:border-gray-300 [&_li]:pl-3 [&_li]:py-0.5
        [&_strong]:text-gray-800">
        {children}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// EXPORTED COMPONENT MAP
// Pass this as the `components` argument to compileMDX / MDXRemote.
// ---------------------------------------------------------------------------
export const planComponents = {
  // Plan-specific components
  Diagram,
  FileMap,
  DataModel,
  ApiEndpoint,
  Screen,
  Wireframe,
  Canvas,
  Annotation,
  Decision,
  Diff,
  AnnotatedCode,
  OpenQuestions,
} as const;

// Type export so plan-route.tsx can reference it without re-importing all components
export type PlanComponents = typeof planComponents;
