/**
 * mermaid.tsx — the two browser rendering pieces, ported from the Next.js
 * renderer but stripped of all Next/server assumptions.
 *
 *   MermaidRenderer   — renders a fenced mermaid code string to SVG with
 *                       securityLevel: "strict".
 *   WireframeSandbox  — renders a wireframe HTML fragment INLINE in the plan
 *                       document (scoped under `.rp-wf-doc`). It does NOT use an
 *                       <iframe>: Obsidian applies its strict CSP to iframe
 *                       srcdoc/blob documents, which strips the inline <style>
 *                       and leaves the wireframe blank/unstyled. Rendering inline
 *                       means styling comes from the loaded plugin stylesheet
 *                       (`.rp-wf-doc` rules in styles.css, which Obsidian
 *                       permits), inline `style=""` attributes are re-applied via
 *                       the CSSOM (never CSP-blocked), and [data-icon] markers are
 *                       swapped via JS. Wide surfaces scale DOWN to fit the pane.
 */

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import mermaid from "mermaid";
import {
  SURFACE_DIMENSIONS,
  DEFAULT_SURFACE,
  applyWireframeIcons,
  type WireframeSurface,
} from "./wireframe";

let mermaidInitialized = false;
function ensureMermaid() {
  if (mermaidInitialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "neutral",
    securityLevel: "strict",
  });
  mermaidInitialized = true;
}

export function MermaidRenderer({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    ensureMermaid();
    const id = `mermaid-${Math.random().toString(36).slice(2)}`;
    mermaid
      .render(id, code)
      .then(({ svg }) => {
        if (ref.current && !cancelled) ref.current.innerHTML = svg;
      })
      .catch((err) => {
        if (ref.current && !cancelled) {
          ref.current.textContent = `Mermaid error: ${String(err)}`;
        }
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  return <div ref={ref} className="rp-mermaid" aria-label="Diagram" />;
}

/**
 * Wireframe "device", rendered INLINE — see the file header for why no iframe.
 *
 * The wireframe HTML is a semantic fragment using the `--wf-*` tokens + helper
 * classes defined under `.rp-wf-doc` in styles.css. We:
 *   1. set it via innerHTML inside a fixed-size `.rp-wf-doc` (the device screen),
 *   2. swap [data-icon] markers for inline SVGs,
 *   3. re-apply any inline `style=""` via `el.style.cssText` (CSP-safe), and
 *   4. scale the whole device DOWN to fit the host column (never upscale).
 */
export function WireframeSandbox({
  html,
  title,
  surface = DEFAULT_SURFACE,
}: {
  html: string;
  title: string;
  surface: WireframeSurface;
}) {
  const preset = SURFACE_DIMENSIONS[surface] ?? SURFACE_DIMENSIONS[DEFAULT_SURFACE];
  const outerRef = useRef<HTMLDivElement>(null);
  const docRef = useRef<HTMLDivElement>(null);

  // Host column width — wide surfaces (e.g. a 1280px desktop mock) scale to fit
  // whatever pane they live in: Obsidian's narrow reading column, the CLI prose
  // width, or a wide hosted page.
  const [avail, setAvail] = useState<number>(preset.width);
  useEffect(() => {
    const host = outerRef.current?.parentElement;
    if (!host || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const w = host.clientWidth;
      if (w > 0) setAvail(w);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(host);
    return () => ro.disconnect();
  }, []);

  // Post-mount DOM work, before paint: icon swap + CSP-safe inline-style re-apply.
  useLayoutEffect(() => {
    const el = docRef.current;
    if (!el) return;
    applyWireframeIcons(el);
    el.querySelectorAll<HTMLElement>("[style]").forEach((node) => {
      const css = node.getAttribute("style");
      if (css) node.style.cssText = css;
    });
  }, [html]);

  const scale = avail > 0 && preset.width > avail ? avail / preset.width : 1;
  const scaledWidth = Math.round(preset.width * scale);
  const scaledHeight = Math.round(preset.minHeight * scale);

  // The device renders at its true pixel size and is visually scaled to fit;
  // the outer frame is sized to the SCALED dimensions so siblings sit flush.
  const docStyle: CSSProperties = {
    width: preset.width,
    height: preset.minHeight,
    overflow: "hidden",
    transform: scale !== 1 ? `scale(${scale})` : undefined,
    transformOrigin: "top left",
  };

  return (
    <div
      ref={outerRef}
      className="rp-wf-frame"
      style={{ width: scaledWidth, maxWidth: "100%", height: scaledHeight, overflow: "hidden" }}
      role="img"
      aria-label={title}
    >
      <div
        ref={docRef}
        className="rp-wf-doc"
        style={docStyle}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}
