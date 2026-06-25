# Rhize Visual Plan — Obsidian plugin

Render the Rhize **`plan.mdx`** format natively inside Obsidian. This is the
**Obsidian shell** of the `rhize-visual-plan` skill: it does **not** re-implement
the components — it imports the one canonical renderer core from the CLI viewer
(`../viewer/src/components.tsx`, `PlanShell.tsx`, `mermaid.tsx`, `wireframe.ts`,
`styles.css`). One renderer core, many shells.

Clicking a `.mdx` file opens it as a fully rendered plan — Mermaid diagrams,
sandboxed wireframe iframes, decision / file-map / data-model / API-endpoint
cards, diffs, annotated code, and the frontmatter header chip — identical to the
Next.js/Vite viewer.

> **Desktop only.** The renderer uses an Electron-class browser environment
> (in-app MDX compilation, Mermaid, and `<iframe srcDoc>` sandboxes). `isDesktopOnly`
> is set in the manifest.

---

## How it works

- **`.mdx` → custom view.** `registerView(VIEW_TYPE, …)` +
  `registerExtensions(["mdx"], VIEW_TYPE)`. A `TextFileView` subclass
  (`src/MdxView.tsx`) reads the file and mounts React into `contentEl`.
- **Runtime MDX.** Unlike the CLI (which compiles at build time via
  `@mdx-js/rollup`), Obsidian has no bundler at runtime, so we compile in-app with
  `@mdx-js/mdx` `evaluate()` using the live `react/jsx-runtime` and
  `remarkFrontmatter` + `remarkMdxFrontmatter`. Components are provided through
  `MDXProvider` (`@mdx-js/react`) using the imported `planComponents` map; the body
  renders inside the imported `PlanShell`. See `src/MdxRenderer.tsx`.
- **Theme-aware.** The viewer stylesheet (`rp-*` classes) is bundled in and
  injected as a `<style>`; a theme bridge maps Obsidian's `body.theme-dark` /
  `body.theme-light` to the viewer's dark/light tokens. The wireframe `--wf-*`
  tokens stay inside each wireframe `<iframe srcDoc>`, exactly as the core
  implements them.
- **Live reload.** `TextFileView` re-renders on disk change; the plugin also
  re-renders the active plan leaf on vault `modify`.

---

## Build

Requires Node ≥ 18.

```bash
cd project-launcher/skills/rhize-visual-plan/obsidian-plugin
npm install
npm run build      # esbuild → main.js (+ refreshes styles.css from the viewer)
```

`npm run build` bundles `src/main.ts` → `main.js` (CJS) with React, react-dom,
`@mdx-js/mdx`, `@mdx-js/react`, mermaid, gray-matter and the remark plugins all
bundled in (`obsidian`, `electron`, and Node builtins are external). It also
writes `styles.css` next to `main.js` from the **same** viewer stylesheet, so the
two never diverge.

## Install into a vault

Copy the three runtime files into a plugin folder in your vault and enable it:

```bash
VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault"
DEST="$VAULT/.obsidian/plugins/rhize-visual-plan"
mkdir -p "$DEST"
cp manifest.json main.js styles.css "$DEST/"
```

Then: **Settings → Community plugins → Reload** (or restart Obsidian) →
enable **Rhize Visual Plan**. Open any `.mdx` plan to render it.

### Dev install (symlink)

Point the vault's plugin folder at this directory so rebuilds are picked up on
reload (run `npm run dev` for an esbuild watch):

```bash
ln -s "$(pwd)" "$VAULT/.obsidian/plugins/rhize-visual-plan"
```

(`main.js` and `styles.css` are produced by the build; with a symlink the vault
sees them directly.)

### BRAT

For beta distribution, [BRAT](https://github.com/TfTHacker/obsidian42-brat) can
install the plugin from a GitHub repo that contains `manifest.json`, `main.js`,
and `styles.css` at the release root. Add the repo in BRAT → *Add beta plugin*.

---

## Settings

- **Auto-render .mdx files** (default on): render `.mdx` as a visual plan on open.
  When off, `.mdx` opens in the plain markdown editor and you render on demand via
  the command **"Open current file as Rhize plan"**. Toggle the plugin off/on (or
  restart) after changing this so the file-extension binding updates.

---

## Reuse boundary

This shell owns only: the Obsidian view/extension registration, the in-app MDX
`evaluate()` call, the `<style>` injection + theme bridge, and the settings tab.
**Every visual component, the header chip, the wireframe sandbox, the Mermaid
renderer, and the stylesheet are imported from `../viewer/src` — not copied.**
Change a component once, in the viewer, and both the CLI and this plugin update.

See `SOURCES.md` (skill root) for provenance and the MIT attribution for the
Obsidian wiring patterns adapted from `ddunnock/mdx-support`.
