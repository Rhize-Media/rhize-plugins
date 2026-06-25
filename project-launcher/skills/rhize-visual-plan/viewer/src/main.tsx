/**
 * main.tsx — entry point.
 *
 * Imports the compiled MDX body (default export) from the dynamic virtual module
 * `virtual:rhize-plan` (resolved by vite.config.ts to whatever absolute plan.mdx
 * the CLI pointed at via RHIZE_PLAN_PATH), plus the frontmatter (parsed by
 * gray-matter in `virtual:rhize-plan-meta` so the header chip is robust). Wraps
 * the body in <MDXProvider> with our component map and renders inside
 * <PlanShell>.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MDXProvider } from "@mdx-js/react";

import "./styles.css";
import { planComponents } from "./components";
import { PlanShell, type PlanFrontmatter } from "./PlanShell";

// The MDX body. @mdx-js/rollup compiles the re-exported .mdx file to a React
// component (default export).
import Plan from "virtual:rhize-plan";
// Frontmatter parsed by gray-matter (raw YAML) for the header chip.
import { frontmatter as rawFrontmatter } from "virtual:rhize-plan-meta";

const frontmatter = (rawFrontmatter ?? {}) as PlanFrontmatter;

// Set the document title from the plan title for nicer tab/window labels and a
// sensible default when the single-file HTML is shared.
if (frontmatter.title) {
  document.title = `${frontmatter.title} — Rhize Plan`;
}

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("#root not found");

createRoot(rootEl).render(
  <StrictMode>
    <MDXProvider components={planComponents}>
      <PlanShell frontmatter={frontmatter}>
        <Plan />
      </PlanShell>
    </MDXProvider>
  </StrictMode>
);
