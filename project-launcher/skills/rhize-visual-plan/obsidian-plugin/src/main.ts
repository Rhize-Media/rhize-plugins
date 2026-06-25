/**
 * main.ts — Rhize Visual Plan plugin entry point.
 *
 * Responsibilities:
 *   1. register the custom view (VIEW_TYPE_RHIZE_PLAN) and bind the `.mdx`
 *      extension to it (or to the built-in markdown editor when auto-render is
 *      off) — registerView + registerExtensions, the standard Obsidian pair.
 *   2. inject the REUSED viewer stylesheet (../../viewer/src/styles.css, bundled
 *      as a text import) so the rp-* components look identical to the CLI, plus a
 *      theme bridge mapping Obsidian's body.theme-dark to the viewer's dark
 *      tokens (the source CSS keys dark mode off prefers-color-scheme).
 *   3. a settings tab with the auto-render toggle.
 *   4. live reload: TextFileView re-calls setViewData on disk change; we ALSO
 *      re-render the active plan leaf on vault "modify" as a belt-and-suspenders.
 *
 * Obsidian wiring patterns (registerView/registerExtensions, the auto-open
 * setting gate, the settings tab shape, file-menu commands) are adapted from the
 * conventional Obsidian sample plugin and the MIT-licensed ddunnock/mdx-support
 * plugin. See SOURCES.md.
 */

import {
  Plugin,
  PluginSettingTab,
  Setting,
  TFile,
  WorkspaceLeaf,
  type App,
} from "obsidian";

import { MdxView, VIEW_TYPE_RHIZE_PLAN } from "./MdxView";

// The REUSED viewer stylesheet, inlined by esbuild's `.css` -> text loader.
import viewerStyles from "../../viewer/src/styles.css";

interface RhizeVisualPlanSettings {
  /** When true, clicking a .mdx file renders the visual plan; otherwise it
   *  opens in Obsidian's plain markdown editor and you preview on demand. */
  autoRender: boolean;
}

const DEFAULT_SETTINGS: RhizeVisualPlanSettings = {
  autoRender: true,
};

const STYLE_EL_ID = "rhize-visual-plan-styles";

/**
 * Theme bridge: the viewer's styles.css flips dark mode via
 * @media (prefers-color-scheme: dark). Obsidian's theme toggle sets
 * body.theme-dark / body.theme-light independent of the OS scheme. This block
 * re-applies the viewer's dark token values under body.theme-dark so the plugin
 * always tracks the Obsidian theme. (Values mirror styles.css :root dark block.)
 */
const THEME_BRIDGE = `
body.theme-dark .rhize-visual-plan-view {
  --rp-paper:#0f1115; --rp-ink:#e6e8ec; --rp-muted:#9aa3af; --rp-muted-2:#6b7280;
  --rp-line:#2a2f3a; --rp-line-soft:#20242d; --rp-surface:#171a21; --rp-surface-2:#14171d;
  --rp-accent:#60a5fa; --rp-code-bg:#0b0e13; --rp-code-bar:#11151c; --rp-code-fg:#e6edf3;
  --rp-gray-bg:#2a2f3a; --rp-gray-fg:#cbd5e1; --rp-yellow-bg:#422006; --rp-yellow-fg:#fde68a;
  --rp-green-bg:#052e16; --rp-green-fg:#86efac; --rp-red-bg:#450a0a; --rp-red-fg:#fca5a5;
  --rp-blue-bg:#172554; --rp-blue-fg:#93c5fd; --rp-orange-bg:#431407; --rp-orange-fg:#fdba74;
  --rp-purple-bg:#3b0764; --rp-purple-fg:#d8b4fe; --rp-emerald-bg:#022c22; --rp-emerald-fg:#6ee7b7;
  --rp-indigo-bg:#1e1b4b; --rp-indigo-fg:#a5b4fc;
  --rp-add-bg:#052e16; --rp-add-fg:#86efac; --rp-edit-bg:#172554; --rp-edit-fg:#93c5fd;
  --rp-delete-bg:#450a0a; --rp-delete-fg:#fca5a5;
  --rp-annotation-bg:#1f1a0a; --rp-annotation-line:#5c4813; --rp-annotation-fg:#fde68a;
  --rp-annotation-mark:#facc15;
}
body.theme-light .rhize-visual-plan-view {
  --rp-paper:#ffffff; --rp-ink:#1a1d23; --rp-muted:#6b7280; --rp-muted-2:#9aa3af;
  --rp-line:#e2e5ea; --rp-line-soft:#eef0f3; --rp-surface:#f6f7f9; --rp-surface-2:#f9fafb;
  --rp-accent:#2563eb; --rp-code-bg:#0d1117; --rp-code-bar:#161b22; --rp-code-fg:#e6edf3;
  --rp-gray-bg:#f3f4f6; --rp-gray-fg:#374151; --rp-yellow-bg:#fef9c3; --rp-yellow-fg:#854d0e;
  --rp-green-bg:#dcfce7; --rp-green-fg:#166534; --rp-red-bg:#fee2e2; --rp-red-fg:#b91c1c;
  --rp-blue-bg:#dbeafe; --rp-blue-fg:#1e40af; --rp-orange-bg:#ffedd5; --rp-orange-fg:#9a3412;
  --rp-purple-bg:#f3e8ff; --rp-purple-fg:#6b21a8; --rp-emerald-bg:#d1fae5; --rp-emerald-fg:#065f46;
  --rp-indigo-bg:#e0e7ff; --rp-indigo-fg:#3730a3;
  --rp-add-bg:#f0fdf4; --rp-add-fg:#15803d; --rp-edit-bg:#eff6ff; --rp-edit-fg:#1d4ed8;
  --rp-delete-bg:#fef2f2; --rp-delete-fg:#b91c1c;
  --rp-annotation-bg:#fefce8; --rp-annotation-line:#fde68a; --rp-annotation-fg:#713f12;
  --rp-annotation-mark:#ca8a04;
}
/* Scope the host: the viewer CSS sets html/body background; inside Obsidian we
   apply paper/ink to our view container and let .rp-root keep its max-width. */
.rhize-visual-plan-view {
  background: var(--rp-paper);
  color: var(--rp-ink);
  overflow: auto;
}
.rhize-visual-plan-view .rvp-host { height: 100%; }
.rhize-visual-plan-view .rp-root { margin: 0 auto; }
.rhize-visual-plan-view .rvp-error {
  max-width: 760px; margin: 32px auto; padding: 16px 20px;
  border: 1px solid var(--rp-red-fg); border-radius: var(--rp-radius);
  background: var(--rp-red-bg); color: var(--rp-red-fg);
}
.rhize-visual-plan-view .rvp-error-title { font-weight: 700; margin-bottom: 8px; }
.rhize-visual-plan-view .rvp-error-msg { white-space: pre-wrap; font-size: 13px; }
.rhize-visual-plan-view .rvp-error-src pre { white-space: pre-wrap; font-size: 12px; opacity: 0.8; }
`;

export default class RhizeVisualPlanPlugin extends Plugin {
  settings: RhizeVisualPlanSettings = DEFAULT_SETTINGS;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.injectStyles();

    // 1) Register the view factory.
    this.registerView(VIEW_TYPE_RHIZE_PLAN, (leaf: WorkspaceLeaf) => new MdxView(leaf));

    // 2) Bind the .mdx extension. registerExtensions throws if the extension is
    // already owned (e.g. another MDX plugin); guard so we degrade gracefully.
    try {
      if (this.settings.autoRender) {
        this.registerExtensions(["mdx"], VIEW_TYPE_RHIZE_PLAN);
      } else {
        this.registerExtensions(["mdx"], "markdown");
      }
    } catch (e) {
      console.warn("[rhize-visual-plan] could not register .mdx extension:", e);
    }

    // 3) Command: render the active .mdx as a plan (useful when auto-render off,
    //    or to force a re-open into the plan view).
    this.addCommand({
      id: "open-as-rhize-plan",
      name: "Open current file as Rhize plan",
      checkCallback: (checking: boolean) => {
        const file = this.app.workspace.getActiveFile();
        const ok = !!file && file.extension === "mdx";
        if (ok && !checking) void this.openAsPlan(file as TFile);
        return ok;
      },
    });

    // 4) Live reload (belt-and-suspenders): when a .mdx that is open in a plan
    //    leaf changes on disk, re-render that leaf. TextFileView already handles
    //    the common case; this covers external edits while the leaf is in the
    //    background.
    this.registerEvent(
      this.app.vault.on("modify", (file) => {
        if (!(file instanceof TFile) || file.extension !== "mdx") return;
        for (const leaf of this.app.workspace.getLeavesOfType(VIEW_TYPE_RHIZE_PLAN)) {
          const view = leaf.view;
          if (view instanceof MdxView && view.file?.path === file.path) {
            void view.renderPlan();
          }
        }
      }),
    );

    this.addSettingTab(new RhizeVisualPlanSettingTab(this.app, this));
  }

  onunload(): void {
    document.getElementById(STYLE_EL_ID)?.remove();
    // Obsidian auto-detaches registered views/extensions on unload.
  }

  /** Open a .mdx file in a fresh leaf using the plan view. */
  async openAsPlan(file: TFile): Promise<void> {
    const leaf = this.app.workspace.getLeaf(false);
    await leaf.setViewState({
      type: VIEW_TYPE_RHIZE_PLAN,
      state: { file: file.path },
      active: true,
    });
  }

  private injectStyles(): void {
    document.getElementById(STYLE_EL_ID)?.remove();
    const style = document.createElement("style");
    style.id = STYLE_EL_ID;
    // Bundled viewer stylesheet (rp-* classes) + the Obsidian theme bridge.
    style.textContent = `${viewerStyles}\n${THEME_BRIDGE}`;
    document.head.appendChild(style);
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }
}

class RhizeVisualPlanSettingTab extends PluginSettingTab {
  plugin: RhizeVisualPlanPlugin;

  constructor(app: App, plugin: RhizeVisualPlanPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl).setName("Rendering").setHeading();

    new Setting(containerEl)
      .setName("Auto-render .mdx files")
      .setDesc(
        "Render .mdx files as visual plans when opened. When off, .mdx opens in the " +
          "plain markdown editor and you can render on demand via the command " +
          '"Open current file as Rhize plan". Restart Obsidian (or disable/enable the ' +
          "plugin) after changing this so the file-extension binding updates.",
      )
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.autoRender).onChange(async (value) => {
          this.plugin.settings.autoRender = value;
          await this.plugin.saveSettings();
        }),
      );
  }
}
