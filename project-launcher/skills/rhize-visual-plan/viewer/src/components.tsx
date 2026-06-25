/**
 * components.tsx — the CANONICAL Rhize plan component map.
 *
 * Ported from templates/mdx-components.tsx (the former Next.js renderer) with
 * everything Next-specific removed: no next-mdx-remote, no next/*, no
 * "use client", no RSC assumptions. This standalone implementation is now the
 * source of truth for how a plan.mdx renders. The Tailwind utility classes from
 * the original were converted to semantic CSS classes (see styles.css); behavior
 * is preserved verbatim — FileMap leading-verb tinting, status/method/store
 * badges, the iframe wireframe sandbox, mermaid (strict), single-bottom
 * OpenQuestions.
 *
 * All components degrade gracefully: with props absent they still render their
 * children.
 */

import React, { type ReactNode } from "react";
import { MermaidRenderer, WireframeSandbox } from "./mermaid";
import { DEFAULT_SURFACE, SURFACE_DIMENSIONS, type WireframeSurface } from "./wireframe";

// ---------------------------------------------------------------------------
// Helper: extract raw text from React children (for MDX fenced-code blocks)
// ---------------------------------------------------------------------------
export function extractText(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
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
//
//   (a) inline HTML-as-JSX:   <Screen><div class="wf-bar">…</div></Screen>
//   (b) a fenced ```html block: <Screen>```html …raw html… ```</Screen>
//
// (a) MDX parses the body as JSX, so `children` arrives as a tree of React
//     elements with attributes preserved verbatim (`class`, string `style`,
//     `data-icon`, …). We serialize that tree BACK to an HTML string. This is
//     why `extractText` alone is wrong for Screen: it discards every tag, class,
//     and style and leaves bare run-together text.
// (b) MDX parses the fence as <pre><code> whose text IS the raw HTML; we take it
//     directly. Use a fence for HTML containing JSX-hostile characters (`{`,`}`).
//
// The result is fed to WireframeSandbox via dangerouslySetInnerHTML.
// ---------------------------------------------------------------------------

const VOID_ELEMENTS = new Set([
  "area", "base", "br", "col", "embed", "hr", "img", "input",
  "link", "meta", "param", "source", "track", "wbr",
]);

// Behavior-bearing elements have no place in a layout wireframe and carry an
// outsized injection blast radius — drop them (and their subtree) rather than
// emit them. Safe-by-construction: don't rely on MDX's compiler to reject them.
const BLOCKED_TAGS = new Set([
  "script", "iframe", "object", "embed", "base", "meta", "link", "noscript",
]);

// URL-bearing attributes whose value we vet for javascript:/vbscript: schemes.
const URL_ATTRS = new Set([
  "href", "src", "xlink:href", "formaction", "action", "poster", "background",
]);

function isUnsafeUrl(value: string): boolean {
  // Strip whitespace/control chars (a classic filter bypass) before testing the scheme.
  const v = value.replace(/[\s ]+/g, "").toLowerCase();
  return v.startsWith("javascript:") || v.startsWith("vbscript:") || v.startsWith("data:text/html");
}

// CSS properties whose numeric values are unitless — emitting `px` would make
// them invalid (e.g. `opacity:1px`). Mirrors React's own unitless allowlist.
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

// Map a React prop name back to its HTML attribute name.
function htmlAttrName(name: string): string {
  if (name === "className") return "class";
  if (name === "htmlFor") return "for";
  return name; // class, style, href, value, type, data-*, aria-*, … pass through
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
    // Fragments / nested components: emit only their children.
    if (typeof type !== "string") return serializeChildrenToHtml(props?.children as ReactNode);
    // Drop behavior-bearing elements (and their subtree) outright.
    if (BLOCKED_TAGS.has(type.toLowerCase())) return "";

    const attrs: string[] = [];
    for (const [key, value] of Object.entries(props)) {
      if (key === "children" || key === "key" || key === "ref") continue;
      if (value == null || value === false) continue;
      // Never emit inline event handlers (onClick, onError, …).
      if (/^on[a-z]/i.test(key)) continue;
      if (key === "style") {
        const css = typeof value === "string"
          ? value
          : styleObjectToString(value as Record<string, unknown>);
        if (css) attrs.push(`style="${escapeAttr(css)}"`);
        continue;
      }
      const name = htmlAttrName(key);
      // Neutralize javascript:/vbscript:/data:text-html in URL-bearing attributes.
      if (URL_ATTRS.has(name.toLowerCase()) && typeof value === "string" && isUnsafeUrl(value)) {
        continue;
      }
      if (value === true) { attrs.push(name); continue; }
      attrs.push(`${name}="${escapeAttr(String(value))}"`);
    }
    const attrStr = attrs.length ? ` ${attrs.join(" ")}` : "";
    if (VOID_ELEMENTS.has(type)) return `<${type}${attrStr} />`;
    return `<${type}${attrStr}>${serializeChildrenToHtml(props.children)}</${type}>`;
  }
  return "";
}

/** If the body is a single fenced code block, return that <pre>/<code> element. */
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
    // Fenced ```html — MDX already consumed the ``` markers; the text is raw HTML.
    return extractText(block)
      .replace(/^```\w*\s*/i, "")
      .replace(/```\s*$/, "")
      .trim();
  }
  return serializeChildrenToHtml(children).trim();
}

// ---------------------------------------------------------------------------
// STATUS BADGE — shared across Diagram, Decision, DataModel, ApiEndpoint, header
// ---------------------------------------------------------------------------
const STATUS_CLASS: Record<string, string> = {
  draft: "rp-badge rp-badge-gray",
  "in-review": "rp-badge rp-badge-yellow",
  approved: "rp-badge rp-badge-green",
  superseded: "rp-badge rp-badge-red",
  decided: "rp-badge rp-badge-blue",
  open: "rp-badge rp-badge-orange",
};

export function StatusBadge({ label }: { label: string }) {
  const cls = STATUS_CLASS[label] ?? "rp-badge rp-badge-gray";
  return <span className={cls}>{label}</span>;
}

// ---------------------------------------------------------------------------
// METHOD BADGE — for ApiEndpoint
// ---------------------------------------------------------------------------
const METHOD_CLASS: Record<string, string> = {
  GET: "rp-method rp-badge-green",
  POST: "rp-method rp-badge-blue",
  PUT: "rp-method rp-badge-yellow",
  PATCH: "rp-method rp-badge-orange",
  DELETE: "rp-method rp-badge-red",
};

function MethodBadge({ method }: { method: string }) {
  const cls = METHOD_CLASS[method.toUpperCase()] ?? "rp-method rp-badge-gray";
  return <span className={cls}>{method.toUpperCase()}</span>;
}

// ---------------------------------------------------------------------------
// FILE-MAP verb tint classes
// ---------------------------------------------------------------------------
const FILE_ACTION_CLASS: Record<string, string> = {
  add: "rp-verb rp-verb-add",
  edit: "rp-verb rp-verb-edit",
  delete: "rp-verb rp-verb-delete",
};

// ---------------------------------------------------------------------------
// <Diagram title caption>```mermaid ... ```</Diagram>
// ---------------------------------------------------------------------------
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
  const code = raw
    .replace(/^```mermaid\s*/i, "")
    .replace(/```\s*$/, "")
    .trim();

  return (
    <figure className="rp-diagram">
      {title && <figcaption className="rp-diagram-title">{title}</figcaption>}
      <MermaidRenderer code={code} />
      {caption && <p className="rp-diagram-caption">{caption}</p>}
    </figure>
  );
}

// ---------------------------------------------------------------------------
// <FileMap root="app/">...</FileMap>
// ---------------------------------------------------------------------------
function FileMap({ root, children }: { root?: string; children?: ReactNode }) {
  return (
    <div className="rp-panel rp-filemap">
      {root && (
        <div className="rp-panel-head">
          <span className="rp-mono rp-muted">root:</span>
          <span className="rp-mono rp-strong">{root}</span>
        </div>
      )}
      <div className="rp-panel-body rp-filemap-body">{tintFileMapVerbs(children)}</div>
    </div>
  );
}

// Tint a leading **add** / **edit** / **delete** <strong> inside each <li>. Only
// touches a <strong> that is the first meaningful child of an <li> whose text is
// a known verb; all other markup passes through untouched.
function tintFileMapVerbs(children: ReactNode): ReactNode {
  function walk(node: ReactNode): ReactNode {
    if (!React.isValidElement(node)) return node;
    const el = node as React.ReactElement<{ children?: ReactNode; className?: string }>;

    if (el.type === "li") {
      const kids = React.Children.toArray(el.props.children);
      const firstIdx = kids.findIndex((k) => !(typeof k === "string" && k.trim() === ""));
      const first = kids[firstIdx];
      if (React.isValidElement(first) && (first.type === "strong" || first.type === "b")) {
        const strongEl = first as React.ReactElement<{
          children?: ReactNode;
          className?: string;
        }>;
        const verb = extractText(strongEl.props.children).trim().toLowerCase();
        const tint = FILE_ACTION_CLASS[verb];
        if (tint) {
          const tinted = React.cloneElement(strongEl, {
            className: `${tint} ${strongEl.props.className ?? ""}`.trim(),
          });
          const nextKids = kids.slice();
          nextKids[firstIdx] = tinted;
          return React.cloneElement(el, {}, nextKids);
        }
      }
      return node;
    }

    if (el.props.children) {
      return React.cloneElement(el, {}, React.Children.map(el.props.children, walk));
    }
    return node;
  }
  return <>{React.Children.map(children, walk)}</>;
}

// ---------------------------------------------------------------------------
// <DataModel name store>...</DataModel>
// ---------------------------------------------------------------------------
const STORE_CLASS: Record<string, string> = {
  sanity: "rp-badge rp-badge-orange",
  payload: "rp-badge rp-badge-purple",
  supabase: "rp-badge rp-badge-emerald",
  type: "rp-badge rp-badge-indigo",
};

function DataModel({
  name,
  store,
  children,
}: {
  name?: string;
  store?: string;
  children?: ReactNode;
}) {
  const badgeCls = store ? STORE_CLASS[store] ?? "rp-badge rp-badge-gray" : undefined;
  return (
    <div className="rp-panel rp-datamodel">
      <div className="rp-panel-head">
        {name && <span className="rp-strong">{name}</span>}
        {store && badgeCls && <span className={badgeCls}>{store}</span>}
      </div>
      <div className="rp-panel-body rp-prose">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// <ApiEndpoint method path auth>...</ApiEndpoint>
// ---------------------------------------------------------------------------
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
    <div className="rp-panel rp-api">
      <div className="rp-panel-head rp-api-head">
        <MethodBadge method={method} />
        {path && <code className="rp-mono rp-strong">{path}</code>}
        {auth && (
          <span className="rp-api-auth">
            auth: <span className="rp-strong">{auth}</span>
          </span>
        )}
      </div>
      <div className="rp-panel-body rp-prose">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// <Screen surface title state> — HTML wireframe fragment, rendered inline &
// scoped under .rp-wf-doc (see mermaid.tsx WireframeSandbox; NOT an iframe).
// ---------------------------------------------------------------------------
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
    <div className="rp-screen">
      {(title || stateLabel) && (
        <div className="rp-screen-head">
          {title && <span>{title}</span>}
          {stateLabel && <StatusBadge label={stateLabel} />}
          <span className="rp-screen-surface">{preset.label}</span>
        </div>
      )}
      <WireframeSandbox html={html} title={title ?? "Screen"} surface={surface} />
    </div>
  );
}

// <Wireframe> is an alias for <Screen>
const Wireframe = Screen;

// ---------------------------------------------------------------------------
// <Canvas title lanes> — lay out <Screen> children in horizontal lanes
// ---------------------------------------------------------------------------
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
    <section className="rp-canvas">
      {title && <h3 className="rp-canvas-title">{title}</h3>}
      {laneNames.length > 0 && (
        <div
          className="rp-canvas-lanes"
          style={{ gridTemplateColumns: `repeat(${laneNames.length}, 1fr)` }}
        >
          {laneNames.map((lane) => (
            <div key={lane} className="rp-canvas-lane">
              {lane}
            </div>
          ))}
        </div>
      )}
      <div className="rp-canvas-board">{children}</div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// <Annotation target placement>
// ---------------------------------------------------------------------------
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
    <aside className="rp-annotation">
      <span className="rp-annotation-mark">&uarr;</span>
      <div>
        {target && <span className="rp-strong rp-annotation-target">{target}</span>}
        <span className="rp-annotation-place">({placement})</span> {children}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// <Decision title status>
// ---------------------------------------------------------------------------
function Decision({
  title,
  status = "open",
  children,
}: {
  title?: string;
  status?: string;
  children?: ReactNode;
}) {
  const cls = status === "decided" ? "rp-decision rp-decision-decided" : "rp-decision rp-decision-open";
  return (
    <div className={cls}>
      <div className="rp-decision-head">
        <span className="rp-decision-label">Decision</span>
        {title && <span className="rp-decision-title">&mdash; {title}</span>}
        <StatusBadge label={status} />
      </div>
      <div className="rp-prose">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// <Diff file lang>```diff ... ```</Diff>  — wide surface (full-bleed)
// ---------------------------------------------------------------------------
function Diff({
  file,
  lang = "diff",
  children,
}: {
  file?: string;
  lang?: string;
  children?: ReactNode;
}) {
  const raw = extractText(children)
    .replace(/^```\w*\s*/i, "")
    .replace(/```\s*$/, "")
    .replace(/\n$/, "");

  const lines = raw.split("\n").map((line, i) => {
    let lineCls = "rp-diff-line";
    if (/^\+(?!\+\+)/.test(line)) lineCls += " rp-diff-add";
    else if (/^-(?!--)/.test(line)) lineCls += " rp-diff-remove";
    else if (/^@@/.test(line)) lineCls += " rp-diff-hunk";
    return (
      <div key={i} className={lineCls}>
        {line === "" ? " " : line}
      </div>
    );
  });

  return (
    <div className="rp-code rp-wide">
      {file && (
        <div className="rp-code-head">
          <span className="rp-mono rp-code-file">{file}</span>
          {lang && <span className="rp-code-lang">{lang}</span>}
        </div>
      )}
      <div className="rp-code-body rp-diff-body">{lines}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// <AnnotatedCode file lang>```ts ... // >> note```</AnnotatedCode>
// ---------------------------------------------------------------------------
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
    .replace(/\n$/, "");

  const lines = raw.split("\n").map((line, i) => {
    const annotationMatch = line.match(/^(.*?)\/\/\s*>>\s*(.+)$/);
    if (annotationMatch) {
      const [, code, note] = annotationMatch;
      return (
        <div key={i} className="rp-ac-line">
          <span className="rp-ac-code">{code === "" ? " " : code}</span>
          <span className="rp-ac-note">&#9664; {note}</span>
        </div>
      );
    }
    return (
      <div key={i} className="rp-ac-line">
        <span className="rp-ac-code">{line === "" ? " " : line}</span>
      </div>
    );
  });

  return (
    <div className="rp-code rp-wide">
      {file && (
        <div className="rp-code-head">
          <span className="rp-mono rp-code-file">{file}</span>
          {lang && <span className="rp-code-lang">{lang}</span>}
        </div>
      )}
      <div className="rp-code-body">{lines}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// <OpenQuestions> — exactly one per plan, at the bottom
// ---------------------------------------------------------------------------
function OpenQuestions({ children }: { children?: ReactNode }) {
  return (
    <section className="rp-panel rp-openq">
      <div className="rp-panel-head rp-openq-head">
        <span className="rp-strong rp-openq-title">Open Questions</span>
        <span className="rp-muted rp-openq-note">&mdash; resolve before approval</span>
      </div>
      <div className="rp-panel-body rp-openq-body rp-prose">{children}</div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// EXPORTED COMPONENT MAP — passed to <MDXProvider components={...}>
// ---------------------------------------------------------------------------
export const planComponents = {
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

export type PlanComponents = typeof planComponents;
