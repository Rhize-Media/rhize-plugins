/**
 * MdxRenderer.tsx — MDX -> React pipeline, REUSING the viewer's renderer core.
 *
 * This is the Obsidian shell's only real glue. The CLI viewer compiles plan.mdx
 * at BUILD time via @mdx-js/rollup (the `virtual:rhize-plan` module). Obsidian
 * has no bundler at runtime, so we compile the SAME MDX IN-APP with
 * `@mdx-js/mdx`'s `evaluate()` and the live `react/jsx-runtime`. Everything after
 * compilation — the component map, the header chrome, the prose container — is
 * imported verbatim from ../../viewer/src so there is ONE implementation.
 *
 *   planComponents  <- ../../viewer/src/components.tsx   (the 12 components)
 *   PlanShell       <- ../../viewer/src/PlanShell.tsx    (header chip + body)
 *
 * gray-matter parses the YAML frontmatter for the header chip (robust against
 * the remark frontmatter plugins, which strip it from the body but expose it
 * less ergonomically). remarkFrontmatter + remarkMdxFrontmatter keep the `---`
 * block from leaking into the rendered body.
 */

import * as React from "react";
import { createElement, StrictMode, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import * as runtime from "react/jsx-runtime";
import { evaluate } from "@mdx-js/mdx";
import { MDXProvider } from "@mdx-js/react";
import remarkFrontmatter from "remark-frontmatter";
import remarkMdxFrontmatter from "remark-mdx-frontmatter";
import remarkGfm from "remark-gfm";
import matter from "gray-matter";

// --- REUSED renderer core (the whole point: one core, many shells) -----------
import { planComponents } from "../../viewer/src/components";
import { PlanShell, type PlanFrontmatter } from "../../viewer/src/PlanShell";

export interface MountedPlan {
  root: Root;
  unmount: () => void;
}

/** Friendly error surface when MDX fails to compile/evaluate. */
function PlanError({ message, source }: { message: string; source?: string }) {
  return createElement(
    "div",
    { className: "rvp-error" },
    createElement("div", { className: "rvp-error-title" }, "Could not render this plan.mdx"),
    createElement("pre", { className: "rvp-error-msg" }, message),
    source
      ? createElement(
          "details",
          { className: "rvp-error-src" },
          createElement("summary", null, "Show source"),
          createElement("pre", null, source),
        )
      : null,
  );
}

/**
 * Error boundary: a component that throws during React's ASYNC render (after
 * root.render() has already returned) is invisible to the sync try/catch in
 * mountPlan — without this the whole tree unmounts to a blank view. Here we
 * catch it, show a visible PlanError, and log to the console for devtools.
 */
class PlanErrorBoundary extends React.Component<
  { source?: string; children?: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    console.error("[rhize-visual-plan] plan render error:", error);
  }
  render() {
    if (this.state.error) {
      return createElement(PlanError, {
        message: `${this.state.error.name}: ${this.state.error.message}`,
        source: this.props.source,
      });
    }
    return this.props.children as ReactNode;
  }
}

/**
 * Compile + evaluate the MDX string into a React component, then render it
 * inside <MDXProvider> + <PlanShell> into `container` via createRoot.
 *
 * Returns a MountedPlan whose `unmount()` tears down the React root (call it on
 * view close / before re-render to avoid leaks).
 */
export async function mountPlan(container: HTMLElement, raw: string): Promise<MountedPlan> {
  const root = createRoot(container);

  // Frontmatter for the header chip. gray-matter is forgiving and returns {}
  // when there is no `---` block.
  let frontmatter: PlanFrontmatter = {};
  try {
    frontmatter = (matter(raw).data ?? {}) as PlanFrontmatter;
  } catch {
    frontmatter = {};
  }

  try {
    // evaluate() returns a module record; the compiled MDX body is `default`.
    // We pass the live `react/jsx-runtime` (jsx/jsxs/Fragment) so MDX can build
    // elements at runtime with no bundler. We deliberately do NOT set
    // `providerImportSource`: the evaluated body then accepts a `components`
    // prop, and we pass `planComponents` directly to it. This prop path is the
    // one verified by the headless SSR proof; relying solely on MDXProvider
    // context proved fragile for component resolution under evaluate(). We STILL
    // wrap in <MDXProvider> so any nested/markdown-level component overrides also
    // resolve to the same map.
    const mod = await evaluate(raw, {
      ...(runtime as Record<string, unknown>),
      baseUrl: import.meta.url,
      // remark-gfm enables GFM tables (the <DataModel> body), strikethrough,
      // task lists, and autolinks. Without it, `| a | b |` renders as literal
      // pipes instead of a <table>.
      remarkPlugins: [remarkFrontmatter, remarkMdxFrontmatter, remarkGfm],
    });

    const PlanBody = mod.default as (props: {
      components?: Record<string, React.ComponentType>;
    }) => ReactNode;

    const components = planComponents as unknown as Record<string, React.ComponentType>;

    root.render(
      createElement(
        StrictMode,
        null,
        createElement(
          PlanErrorBoundary,
          { source: raw },
          createElement(
            MDXProvider,
            { components },
            createElement(
              PlanShell,
              { frontmatter },
              createElement(PlanBody, { components }),
            ),
          ),
        ),
      ),
    );
  } catch (err) {
    const message = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
    root.render(createElement(PlanError, { message, source: raw }));
  }

  return {
    root,
    unmount: () => {
      try {
        root.unmount();
      } catch {
        /* already torn down */
      }
    },
  };
}

export type { PlanFrontmatter };
