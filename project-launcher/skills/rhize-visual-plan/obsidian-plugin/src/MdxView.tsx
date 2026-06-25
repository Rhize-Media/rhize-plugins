/**
 * MdxView.tsx — the FileView that renders a .mdx file as a Rhize visual plan.
 *
 * Extends TextFileView (not the lower-level FileView) because a plan.mdx is a
 * text file: TextFileView owns reading the file into `data`, and — crucially —
 * Obsidian calls setViewData() again whenever the file changes on disk, which
 * gives us LIVE RELOAD for free (no manual vault.on("modify") wiring needed; the
 * plugin also registers a modify listener as a belt-and-suspenders re-render for
 * the active leaf).
 *
 * React is mounted into a child of contentEl. We tear the previous root down
 * before each re-render so Mermaid effects and the wireframe postMessage
 * listeners don't leak across reloads.
 *
 * Obsidian plumbing patterns (registerView signature, TextFileView lifecycle,
 * the contentEl mount point) follow the conventional Obsidian sample-plugin and
 * the MIT-licensed ddunnock/mdx-support plugin — see SOURCES.md.
 */

import { TextFileView, WorkspaceLeaf } from "obsidian";
import { mountPlan, type MountedPlan } from "./MdxRenderer";

export const VIEW_TYPE_RHIZE_PLAN = "rhize-visual-plan-view";

export class MdxView extends TextFileView {
  /** Raw .mdx text, owned by TextFileView's read/write lifecycle. */
  private mdxData = "";
  private mounted: MountedPlan | null = null;
  private host: HTMLElement | null = null;

  constructor(leaf: WorkspaceLeaf) {
    super(leaf);
  }

  getViewType(): string {
    return VIEW_TYPE_RHIZE_PLAN;
  }

  getDisplayText(): string {
    return this.file?.basename ?? "Plan";
  }

  getIcon(): string {
    return "layout-dashboard";
  }

  // ----- TextFileView data contract -----------------------------------------

  /** Called by Obsidian when the file is loaded AND whenever it changes on disk. */
  setViewData(data: string, _clear: boolean): void {
    this.mdxData = data;
    void this.renderPlan();
  }

  /** We render read-only, so the on-disk content is the source of truth. */
  getViewData(): string {
    return this.mdxData;
  }

  clear(): void {
    this.mdxData = "";
    this.teardown();
    if (this.host) this.host.empty();
  }

  // ----- lifecycle -----------------------------------------------------------

  async onOpen(): Promise<void> {
    this.contentEl.addClass("rhize-visual-plan-view");
    // A dedicated scroll host so we control padding/scroll independent of
    // Obsidian's view chrome.
    this.host = this.contentEl.createDiv({ cls: "rvp-host" });
  }

  async onClose(): Promise<void> {
    this.teardown();
    this.host = null;
    this.contentEl.empty();
  }

  // ----- rendering ------------------------------------------------------------

  /** Re-mount the React tree from the current mdxData. */
  async renderPlan(): Promise<void> {
    if (!this.host) return;
    this.teardown();
    this.host.empty();
    const mountTarget = this.host.createDiv({ cls: "rvp-mount" });
    this.mounted = await mountPlan(mountTarget, this.mdxData);
  }

  private teardown(): void {
    if (this.mounted) {
      this.mounted.unmount();
      this.mounted = null;
    }
  }
}
