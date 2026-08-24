# rhize-plan-viewer

A self-contained, **project-agnostic** local viewer and static exporter for the
Rhize `plan.mdx` format. It renders **any** `plan.mdx` from **any** path — a file
in your Obsidian vault, a client repo, anywhere on disk. It is not tied to any
single project.

- **Serve** a plan locally with hot-reload while you edit it.
- **Build** a single self-contained `.html` (all CSS + JS inlined) you can open
  offline and share via Jira, Slack, or email.

No Next.js, no hosted plan service, no `next-mdx-remote`. The renderer in
`src/components.tsx` is the canonical implementation of the 12 plan components and
is kept in lock-step with `../references/wireframe.md` (the `--wf-*` token and
surface-preset authority).

---

## Install

```bash
cd viewer
npm install
```

This pulls Vite, React 18, the MDX toolchain, and `mermaid` (mermaid is large —
the first install can take a minute).

## Usage

```bash
# Live viewer with HMR — opens your browser, live-reloads on edit:
node bin/rhize-plan.mjs serve /path/to/plan.mdx
node bin/rhize-plan.mjs serve /path/to/project-dir      # resolves <dir>/plan.mdx

# Build a single offline .html:
node bin/rhize-plan.mjs build /path/to/plan.mdx          # writes <slug>.html next to the source
node bin/rhize-plan.mjs build /path/to/plan.mdx -o ~/Desktop/plan.html
```

A directory argument resolves to `<dir>/plan.mdx`. For `build`, if `-o` is
omitted the output is written next to the source file, named from the plan's
frontmatter `title` (slugified), falling back to the source filename. The
absolute output path is printed.

### Flags

- `serve --port N` — choose the dev-server port.
- `serve --no-open` — don't auto-open the browser.
- `build -o <path>` — explicit output path (file or relative path).

## Global command (optional)

Link the package once to get a global `rhize-plan` you can run from anywhere:

```bash
cd viewer
npm link
rhize-plan build ~/vault/Projects/Foo/plan.mdx
rhize-plan serve ~/vault/Projects/Foo/plan.mdx
```

---

## How it works

The plan path is dynamic. The CLI sets `RHIZE_PLAN_PATH` to the absolute plan
path, and `vite.config.ts` exposes two virtual modules:

- `virtual:rhize-plan` — re-exports the compiled MDX default (the plan body) and
  its `frontmatter` from the absolute file. Because the re-exported file ends in
  `.mdx`, `@mdx-js/rollup` compiles it and it stays in Rollup's module graph, so
  edits hot-reload during `serve`.
- `virtual:rhize-plan-meta` — exports the frontmatter parsed with `gray-matter`
  (used for the header chip).

`src/main.tsx` imports both, wraps the body in `<MDXProvider>` with the component
map from `src/components.tsx`, and renders it inside `<PlanShell>` (the header
chip: title + status badge + owner + created + repo).

`build` runs Vite with `vite-plugin-singlefile`, which inlines all CSS and JS
into one `index.html`; the CLI copies that to the destination and prints the
path. The output references no external scripts or stylesheets — it opens fully
offline.

## Styling

The viewer ships a compact plain-CSS stylesheet (`src/styles.css`) that
reproduces the original Next.js component styling and supports light/dark via
`prefers-color-scheme`. Plain CSS (rather than Tailwind) keeps the single-file
build reliable and dependency-light. Wireframe `<Screen>`/`<Wireframe>` bodies
render in isolated `<iframe>` sandboxes using the canonical `--wf-*` tokens from
`src/wireframe.ts`, with the Tabler-style icon set and a postMessage
auto-resize bridge.

## Components rendered

`Diagram` (mermaid, `securityLevel: "strict"`), `FileMap` (leading add/edit/delete
verb tinting), `DataModel`, `ApiEndpoint`, `Wireframe`/`Screen` (sandboxed iframe,
8 surface presets, auto-resize), `Canvas`, `Annotation`, `Decision`, `Diff`,
`AnnotatedCode`, and a single bottom `OpenQuestions`.

## Dependency security posture (reviewed 2026-08-24)

`npm audit` on a fresh install reports **0 vulnerabilities**, down from **14 (9 moderate, 5 high)**.
The dependency tree also shrank from 334 packages to 299.

| Change | Why |
|---|---|
| `vite` 5.4.11 → **8.2.2** | Clears every remaining advisory, most of them `server.fs.deny` bypasses plus *"websites were able to send any requests to the development server and read the response"* — genuinely reachable, because `rhize-plan serve` **is** a dev server |
| `@vitejs/plugin-react` 4.3.4 → **6.1.0** | Required: 4.x peers `vite ^4 \|\| ^5`, so it was the single thing blocking vite 8. 6.x peers `vite ^8.0.0` |
| `mermaid` 11.4.1 → **11.17.1** | Clears the `lodash-es` code-injection / prototype-pollution chain reached via `chevrotain` |
| `vite-plugin-singlefile` 2.0.3 → **2.3.3** | Already peers `^8.0.0`; no further change needed |
| `@mdx-js/react`, `@mdx-js/rollup` 3.1.0 → **3.1.1**, `remark-mdx-frontmatter` 5.0.0 → **5.2.0** | Patch/minor housekeeping taken in the same pass |

`vite` 5 → 8 is a three-major jump and was trialled in an isolated copy first. It installs cleanly and
the build still verifies: a real `plan.mdx` renders to a 3.5 MB self-contained HTML with 58 mermaid/SVG
matches and **zero** external references.

**`react` stays at 18.3.1 deliberately** — no advisory requires 19, `@vitejs/plugin-react@6` works with
18, and React 19 carries real behavioral change for no security benefit here.

### Why the pins had to move at all

Dependencies are pinned to *exact* versions and `package-lock.json` is gitignored, so `npm audit fix`
only ever rewrites untracked files. It cleans the local tree and reaches **no installer**. For a skill
distributed through the marketplace, only a `package.json` bump actually propagates — which is why the
audit had to end in changed pins rather than a successful `audit fix`.

**Re-check on any future advisory** with `npm audit` after a *fresh* install (`rm -rf node_modules
package-lock.json && npm install`) — an existing tree understates the count a new user would see.
