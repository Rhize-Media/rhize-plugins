/**
 * plan-route.tsx — Starter Next.js 15 App Router page for rendering plan.mdx files
 *
 * COPY TO: app/plans/[slug]/page.tsx in your Next.js app.
 *
 * npm install next-mdx-remote gray-matter
 * (mermaid is already listed in mdx-components.tsx — add it once)
 *
 * ALSO COPY: templates/mdx-components.tsx → lib/plan-components.tsx
 *
 * HOW IT WORKS
 * 1. Slug resolves to a plan.mdx path via PLAN_ROOT (configurable below).
 * 2. gray-matter parses frontmatter; next-mdx-remote/rsc compiles the MDX body.
 * 3. A header chip renders the frontmatter status/owner/created.
 * 4. notFound() is called when the file doesn't exist — Next.js shows the 404 page.
 *
 * PATH OPTIONS — set PLAN_ROOT to one of:
 *   A) Vault path:  /Users/<you>/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/Projects/<Project>/Plans
 *   B) Repo path:   path.join(process.cwd(), "plans")          ← default (CI-friendly)
 *
 * Example resolution: slug "example-plan" → PLAN_ROOT/example-plan/plan.mdx
 *
 * VERCEL NOTE: If you're reading from an iCloud vault path in production, you need the file
 * accessible at build/runtime. For Vercel preview deploys, use the repo path and commit
 * plan.mdx files to source control. Use the vault path for local preview only.
 */

import { readFile } from "fs/promises";
import path from "path";
import { notFound } from "next/navigation";
import { compileMDX } from "next-mdx-remote/rsc";
import matter from "gray-matter";
import type { Metadata } from "next";
import { planComponents } from "@/lib/plan-components"; // adjust alias to match your tsconfig paths

// ---------------------------------------------------------------------------
// CONFIGURATION
// Set PLAN_ROOT in your .env.local:
//   PLAN_ROOT=/absolute/path/to/plans-directory
// Default: <repo-root>/plans  (slug dirs live here, each containing plan.mdx)
// ---------------------------------------------------------------------------
const PLAN_ROOT =
  process.env.PLAN_ROOT ?? path.join(process.cwd(), "plans");

// ---------------------------------------------------------------------------
// TYPES
// ---------------------------------------------------------------------------
type PlanStatus = "draft" | "in-review" | "approved" | "superseded";

interface PlanFrontmatter {
  title?: string;
  status?: PlanStatus;
  owner?: string;
  created?: string; // ISO date string e.g. "2026-06-25"
  repo?: string;
  related?: string[];
  tags?: string[];
}

// ---------------------------------------------------------------------------
// PATH RESOLUTION
// ---------------------------------------------------------------------------
function resolvePlanPath(slug: string): string {
  // Prevent path traversal: strip any segments starting with '..'
  const safe = slug.replace(/\.\./g, "").replace(/[^a-zA-Z0-9_\-]/g, "-");
  return path.join(PLAN_ROOT, safe, "plan.mdx");
}

// ---------------------------------------------------------------------------
// METADATA (Next.js generateMetadata — reads frontmatter title)
// ---------------------------------------------------------------------------
export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const filePath = resolvePlanPath(slug);

  try {
    const source = await readFile(filePath, "utf8");
    const { data } = matter(source) as { data: PlanFrontmatter };
    return {
      title: data.title ? `${data.title} — Rhize Plan` : "Rhize Plan",
      description: data.status
        ? `Status: ${data.status}. Owner: ${data.owner ?? "unknown"}.`
        : undefined,
    };
  } catch {
    return { title: "Plan not found" };
  }
}

// ---------------------------------------------------------------------------
// STATUS CHIP COLORS
// ---------------------------------------------------------------------------
const STATUS_CHIP: Record<PlanStatus | string, { bg: string; text: string; ring: string }> = {
  draft:       { bg: "bg-gray-100",   text: "text-gray-700",   ring: "ring-gray-300" },
  "in-review": { bg: "bg-yellow-100", text: "text-yellow-800", ring: "ring-yellow-400" },
  approved:    { bg: "bg-green-100",  text: "text-green-800",  ring: "ring-green-400" },
  superseded:  { bg: "bg-red-100",    text: "text-red-700",    ring: "ring-red-400" },
};

// ---------------------------------------------------------------------------
// HEADER CHIP — rendered from frontmatter above the MDX body
// ---------------------------------------------------------------------------
function PlanHeader({ fm }: { fm: PlanFrontmatter }) {
  const chip = fm.status ? (STATUS_CHIP[fm.status] ?? STATUS_CHIP["draft"]) : STATUS_CHIP["draft"];

  return (
    <header className="mb-8 pb-6 border-b border-gray-200">
      {fm.title && (
        <h1 className="text-2xl font-bold text-gray-900 mb-3">{fm.title}</h1>
      )}

      <div className="flex flex-wrap items-center gap-3 text-sm">
        {fm.status && (
          <span
            className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ring-1 ring-inset
              ${chip.bg} ${chip.text} ${chip.ring}`}
          >
            {fm.status}
          </span>
        )}

        {fm.owner && (
          <span className="text-gray-500">
            <span className="font-medium text-gray-700">Owner:</span> {fm.owner}
          </span>
        )}

        {fm.created && (
          <span className="text-gray-500">
            <span className="font-medium text-gray-700">Created:</span> {fm.created}
          </span>
        )}

        {fm.repo && fm.repo !== "n/a" && (
          <a
            href={`https://github.com/${fm.repo}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline text-xs font-mono"
          >
            {fm.repo}
          </a>
        )}

        {fm.tags && fm.tags.length > 0 && (
          <div className="flex gap-1 ml-auto">
            {fm.tags.map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-mono"
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Superseded warning */}
      {fm.status === "superseded" && (
        <p className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
          This plan has been superseded. Do not use it as the current source of truth.
        </p>
      )}
    </header>
  );
}

// ---------------------------------------------------------------------------
// PAGE (Server Component)
// ---------------------------------------------------------------------------
export default async function PlanPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const filePath = resolvePlanPath(slug);

  // Read the file — return 404 if not found
  let source: string;
  try {
    source = await readFile(filePath, "utf8");
  } catch {
    notFound();
  }

  // Parse frontmatter separately with gray-matter so we can render the header chip
  // without waiting for compileMDX (gray-matter is synchronous and much faster).
  const { data: frontmatter, content: mdxBody } = matter(source) as {
    data: PlanFrontmatter;
    content: string;
  };

  // Compile the MDX body (without frontmatter — gray-matter already stripped it).
  // We pass `parseFrontmatter: false` here because we've already parsed it above.
  // If you prefer to let compileMDX parse it, pass `parseFrontmatter: true` and
  // use `compileMDX`'s returned `frontmatter` object instead.
  const { content } = await compileMDX<PlanFrontmatter>({
    source: mdxBody,
    components: planComponents,
    options: {
      parseFrontmatter: false,
      mdxOptions: {
        // remarkPlugins / rehypePlugins can be added here if needed (e.g. rehype-pretty-code)
      },
    },
  });

  return (
    // Outer layout: centered prose column. Adjust max-width to match your app's shell.
    <div className="min-h-screen bg-white">
      <main className="mx-auto max-w-3xl px-6 py-10">
        <PlanHeader fm={frontmatter} />

        {/*
          MDX body. Prose classes style standard Markdown elements (h2, p, ul, table, code, etc.).
          Plan components (<Diagram>, <FileMap>, etc.) render their own Tailwind styles and
          deliberately escape the prose container where they need wider layout (Diff, AnnotatedCode).
        */}
        <article className="prose prose-gray prose-sm sm:prose-base max-w-none
          prose-headings:font-semibold prose-headings:text-gray-900
          prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline
          prose-code:text-sm prose-code:bg-gray-100 prose-code:px-1 prose-code:rounded
          prose-pre:bg-gray-950 prose-pre:text-gray-100">
          {content}
        </article>

        {/* Back link — remove or replace with your actual navigation */}
        <footer className="mt-16 pt-6 border-t border-gray-100">
          <a href="/plans" className="text-sm text-gray-400 hover:text-gray-600">
            ← All plans
          </a>
        </footer>
      </main>
    </div>
  );
}
