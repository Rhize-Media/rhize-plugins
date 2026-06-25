/**
 * PlanShell.tsx — the document chrome around a rendered plan body.
 *
 * Renders the header chip from frontmatter: title + status badge (color by
 * draft/in-review/approved/superseded) + owner + created + repo. The body
 * (compiled MDX) is rendered as children inside the prose container.
 */

import { type ReactNode } from "react";
import { StatusBadge } from "./components";

export interface PlanFrontmatter {
  title?: string;
  status?: string;
  owner?: string;
  created?: string;
  repo?: string;
  related?: string[];
  tags?: string[];
  [key: string]: unknown;
}

export function PlanShell({
  frontmatter,
  children,
}: {
  frontmatter: PlanFrontmatter;
  children: ReactNode;
}) {
  const fm = frontmatter ?? {};
  const title = fm.title ?? "Untitled plan";
  const status = typeof fm.status === "string" ? fm.status : undefined;

  const meta: Array<{ label: string; value: string }> = [];
  if (fm.owner) meta.push({ label: "owner", value: String(fm.owner) });
  if (fm.created) meta.push({ label: "created", value: String(fm.created) });
  if (fm.repo && String(fm.repo).toLowerCase() !== "n/a")
    meta.push({ label: "repo", value: String(fm.repo) });

  return (
    <div className="rp-root">
      <header className="rp-header">
        <div className="rp-header-top">
          <h1 className="rp-header-title">{title}</h1>
          {status && <StatusBadge label={status} />}
        </div>
        {meta.length > 0 && (
          <div className="rp-header-meta">
            {meta.map((m) => (
              <span key={m.label} className="rp-header-meta-item">
                <span className="rp-muted">{m.label}:</span>{" "}
                <span className="rp-strong">{m.value}</span>
              </span>
            ))}
          </div>
        )}
      </header>
      <main className="rp-body rp-prose">{children}</main>
    </div>
  );
}
