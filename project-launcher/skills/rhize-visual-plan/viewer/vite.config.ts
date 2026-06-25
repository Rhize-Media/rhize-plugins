import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import mdx from "@mdx-js/rollup";
import remarkFrontmatter from "remark-frontmatter";
import remarkMdxFrontmatter from "remark-mdx-frontmatter";
import remarkGfm from "remark-gfm";
import { viteSingleFile } from "vite-plugin-singlefile";
import { readFileSync } from "node:fs";
import { resolve, isAbsolute, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import matter from "gray-matter";

const VIEWER_ROOT = dirname(fileURLToPath(import.meta.url));
const NM = (pkg: string) => resolve(VIEWER_ROOT, "node_modules", pkg);

/**
 * The plan file to render is dynamic: the CLI (bin/rhize-plan.mjs) sets
 * RHIZE_PLAN_PATH to the absolute path of a plan.mdx before invoking Vite's JS
 * API. We expose two virtual modules so src/main.tsx can import fixed
 * specifiers while the real target stays dynamic:
 *
 *   virtual:rhize-plan          -> re-exports the compiled MDX default (the body)
 *                                  and `frontmatter` from the absolute plan path.
 *                                  @mdx-js/rollup compiles it because the
 *                                  re-exported file ends in .mdx.
 *   virtual:rhize-plan-meta     -> exports `frontmatter` parsed with gray-matter
 *                                  (raw YAML), used for the header chip even if
 *                                  remark-mdx-frontmatter changes shape.
 *
 * Using a virtual module that `export ... from "<abs path>"` keeps the MDX file
 * inside Rollup's module graph (so HMR works on edit) without copying it.
 */
function rhizePlanVirtual() {
  const VIRT_ID = "virtual:rhize-plan";
  const VIRT_META_ID = "virtual:rhize-plan-meta";
  const RESOLVED = "\0" + VIRT_ID;
  const RESOLVED_META = "\0" + VIRT_META_ID;

  function planPath(): string {
    const p = process.env.RHIZE_PLAN_PATH;
    if (!p) {
      throw new Error(
        "RHIZE_PLAN_PATH is not set. Launch the viewer via bin/rhize-plan.mjs."
      );
    }
    return isAbsolute(p) ? p : resolve(process.cwd(), p);
  }

  return {
    name: "rhize-plan-virtual",
    resolveId(id: string) {
      if (id === VIRT_ID) return RESOLVED;
      if (id === VIRT_META_ID) return RESOLVED_META;
      return null;
    },
    load(id: string) {
      if (id === RESOLVED) {
        const abs = planPath().replace(/\\/g, "/");
        // Re-export the MDX body (default) and its frontmatter export.
        return [
          `export { default } from ${JSON.stringify(abs)};`,
          `export { frontmatter } from ${JSON.stringify(abs)};`,
        ].join("\n");
      }
      if (id === RESOLVED_META) {
        const abs = planPath();
        let fm: Record<string, unknown> = {};
        try {
          const raw = readFileSync(abs, "utf8");
          fm = matter(raw).data ?? {};
        } catch (err) {
          fm = { title: "(could not read plan)", _error: String(err) };
        }
        return `export const frontmatter = ${JSON.stringify(fm)};`;
      }
      return null;
    },
    // Re-read frontmatter meta on plan edits so the header chip hot-reloads.
    handleHotUpdate(ctx: { file: string; server: any; modules: any[] }) {
      try {
        if (resolve(ctx.file) === planPath()) {
          const metaMod = ctx.server.moduleGraph.getModuleById(RESOLVED_META);
          if (metaMod) {
            ctx.server.moduleGraph.invalidateModule(metaMod);
            return [...ctx.modules, metaMod];
          }
        }
      } catch {
        /* noop */
      }
      return ctx.modules;
    },
  };
}

const isBuild = process.env.RHIZE_PLAN_MODE === "build";

export default defineConfig({
  // The plan path may live anywhere on disk (vault or any repo), so allow Vite's
  // dev server to serve files outside the viewer root.
  server: {
    fs: { strict: false, allow: ["/"] },
  },
  resolve: {
    // The compiled MDX file (which lives OUTSIDE the viewer root) injects bare
    // imports for the JSX runtime and the MDX provider. Those directories have no
    // node_modules, so we pin every runtime dependency to the viewer's own
    // installed copies via absolute-path aliases. This is what makes the viewer
    // project-agnostic: a plan.mdx anywhere on disk resolves React/MDX from here.
    // Order: longer/more-specific specifiers first.
    alias: [
      { find: "react/jsx-dev-runtime", replacement: NM("react/jsx-dev-runtime.js") },
      { find: "react/jsx-runtime", replacement: NM("react/jsx-runtime.js") },
      { find: "react-dom/client", replacement: NM("react-dom/client.js") },
      { find: "react-dom", replacement: NM("react-dom") },
      { find: "react", replacement: NM("react") },
      { find: "@mdx-js/react", replacement: NM("@mdx-js/react") },
    ],
    // Deduplicate so a single React instance is used across the viewer src and
    // the externally-located MDX module.
    dedupe: ["react", "react-dom", "@mdx-js/react"],
  },
  plugins: [
    rhizePlanVirtual(),
    {
      // Order matters: MDX must compile .mdx before the React plugin runs its
      // JSX/refresh transform over the output.
      enforce: "pre",
      ...mdx({
        remarkPlugins: [
          remarkFrontmatter,
          [remarkMdxFrontmatter, { name: "frontmatter" }],
          remarkGfm,
        ],
        providerImportSource: "@mdx-js/react",
      }),
    },
    react({ include: /\.(mdx|js|jsx|ts|tsx)$/ }),
    // Inline all JS + CSS into a single .html for the build command only.
    ...(isBuild ? [viteSingleFile()] : []),
  ],
  build: {
    // Keep everything inlinable: no code-splitting, no asset URLs.
    assetsInlineLimit: 100000000,
    chunkSizeWarningLimit: 100000,
    cssCodeSplit: false,
    target: "es2020",
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});
