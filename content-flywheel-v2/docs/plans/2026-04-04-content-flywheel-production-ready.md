# Content Flywheel — Production-Ready Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Take the content-flywheel-v2 from scaffolded-but-unrunnable to a working, secure, deployable dashboard with full CRUD and graph exploration.

**Architecture:** Next.js 16 App Router + Neo4j Aura + DataForSEO + Claude API + Gemini Embeddings.

**Tech Stack:** Next.js 16, React 19, TypeScript 5, Tailwind CSS 4, neo4j-driver 6, Vercel, DataForSEO API, Anthropic SDK, @google/genai

## Milestone Status (as of 2026-04-09)

| Milestone | Status | Notes |
|-----------|--------|-------|
| M0: Credentials & MCP Setup | ✅ Done | Neo4j Aura `ec4405e5`, all MCP servers configured |
| M0.5: POC Critical Path | ✅ Done | Seed, schema, smoke test all passing |
| M1: Build & Boot | ✅ Done | Turbopack root fix, lockfile, clean build |
| M2: Security | ✅ Done | Dedicated API endpoints replace raw Cypher proxy |
| M3: Create Content Flow | ✅ Done | Board + content creation modal |
| M4: App Shell & Error Handling | ✅ Done | Sidebar, error pages, loading states |
| M5: Graph Explorer | ✅ Done | Stats, funnel, clusters, workflow history |
| M6: Testing | ✅ Done | 111 tests across 15 files |
| M7: Deploy to Vercel | ✅ Done | Production at content-flywheel-nu.vercel.app |
| M8: AI Feature Parity | ✅ Done | Claude SDK, embeddings, clustering, article gen, brand voice, cost tracking |
| M9: SEO Utils Option B | ✅ Done | Dual-stack: DataForSEO (Vercel runtime) + SEO Utils MCP (local Claude sessions) |
| M10-M13: UI + Polish | ✅ Done | AI workflow UI, content CRUD, publish UI, Slack, webhook verification |
| M15: SEO Utils Option C | 🔮 Future | VPS-hosted SEO Utils for Vercel runtime access |

---

## Milestone 0: Credentials & MCP Setup

Provision a dedicated Neo4j instance, fill in all MCP server credentials, and wire up the SEO plugin.

### Task 0a: Create a dedicated Neo4j Aura instance

**MANUAL STEP** — Do NOT reuse the MSCI-MVP instance (`556853b2`). Content Flywheel has its own graph schema (`ContentPiece`, `PipelineStage`, `KeywordCluster`, etc.) that would collide with MSCI's data.

1. Go to [console.neo4j.io](https://console.neo4j.io)
2. Create a new free-tier AuraDB instance
3. Save the connection URI, username, and password
4. Run `cypher/schema.cypher` against the new instance to seed constraints, indexes, and pipeline stages

### Task 0b: Fill in .mcp.json credentials

**Files:**
- Modify: `.mcp.json`

Once the Neo4j instance is created, update the `neo4j-cypher` and `neo4j-memory` entries in `.mcp.json` with the real URI and password. The following are already filled in:
- **DataForSEO**: `info@rhize.media` / `d5f4d7f19c1aef29`
- **Firecrawl**: `fc-848f2a2eef1e4751982f36ae6bd6852e`
- **Exa Web Search**: `8058af33-776b-4e95-9e69-25573d4af8bc` (newly added)

Still using env var references (fill via `.env.local` or shell):
- **Neo4j**: `${NEO4J_URI}`, `${NEO4J_USERNAME}`, `${NEO4J_PASSWORD}` — pending new instance
- **Obsidian MCP**: `${OBSIDIAN_API_KEY}` — local Obsidian REST API key
- **Slack**: `${SLACK_BOT_TOKEN}` — optional, for notifications

### Task 0c: Fill in .env.local for Next.js runtime

**Files:**
- Modify: `.env.local`

Update Neo4j credentials once the new instance is provisioned. The following are already set:
- DataForSEO, Firecrawl, Exa — filled in
- Sanity, GHL, Slack — leave blank until those integrations are activated

### Task 0d: Verify SEO-AEO-GEO plugin availability

The `seo-aeo-geo` plugin from rhize-plugins is already installed globally (visible in this session's startup hooks). No project-level config needed — it's auto-loaded when DataForSEO env vars or SEO signals are detected.

Verify by running `/seo-audit` or `/keyword-research` in a Claude session within this project.

### Task 0e: Commit MCP config updates

```bash
git add .mcp.json
git commit -m "chore: fill MCP server credentials and add exa-web-search"
```

Note: `.env.local` is gitignored — only `.mcp.json` gets committed. All secret values live in `.env.local`; `.mcp.json` uses `${VAR}` references.

---

## Milestone 0.5: POC Critical Path

Minimum viable steps to get a working demo loop: sample content → workflow run → data appears in UI. Skips security hardening, polish, and tests.

### Task 0.5.1: Seed Neo4j schema

**Files:**
- Run: `cypher/schema.cypher` against the new Aura instance

**Step 1: Install Neo4j Cypher shell (or use Aura Workspace)**

Option A: Open [workspace.neo4j.io](https://workspace.neo4j.io), connect to instance `ec4405e5`, paste `cypher/schema.cypher` contents into the query editor, run it.

Option B: Use `cypher-shell` CLI if installed locally.

**Step 2: Verify schema was applied**

Run in the Aura workspace:
```cypher
MATCH (s:PipelineStage) RETURN s.name, s.order ORDER BY s.order
```
Expected: 8 rows (inspiration → refresh)

```cypher
SHOW CONSTRAINTS
```
Expected: ~14 uniqueness constraints (content_id, keyword_id, etc.)

**Step 3: No commit needed** (schema lives in the database, file is already committed)

### Task 0.5.2: Verify MCP env var resolution

**Files:**
- Verify: `.mcp.json` env var references resolve correctly after session restart

**Step 1: Test MCP Neo4j connection**

After the next Claude Code session restart, call an MCP neo4j tool:
```
mcp__neo4j-cypher__read_cypher → MATCH (s:PipelineStage) RETURN s.name
```
Expected: Returns 8 pipeline stages.

**Step 2: If env vars don't resolve, fall back to hardcoded values**

If the MCP server comes up with empty NEO4J_URI, hardcode the credentials directly in `.mcp.json` (this is an internal repo — acceptable trade-off for POC).

### Task 0.5.3: Create sample data seed script

**Files:**
- Create: `scripts/seed.ts`
- Modify: `package.json` (add seed script)

**Step 1: Write the seed script**

```typescript
// scripts/seed.ts
import { getDriver, closeDriver } from "../src/lib/neo4j/driver";
import { createContent } from "../src/lib/neo4j/queries";

async function seed() {
  const samples = [
    { title: "The Ultimate Guide to Content Flywheels", slug: "ultimate-guide-content-flywheels", author: "Jim Deola", stage: "inspiration" as const, url: "https://rhize.media/guides/content-flywheels" },
    { title: "How Neo4j Powers Our Content Graph", slug: "neo4j-content-graph", author: "Jim Deola", stage: "research" as const },
    { title: "AEO vs SEO: What's Changing in 2026", slug: "aeo-vs-seo-2026", author: "Jim Deola", stage: "draft" as const },
    { title: "DataForSEO API: Complete Integration Guide", slug: "dataforseo-integration-guide", author: "Jim Deola", stage: "optimize" as const, url: "https://rhize.media/guides/dataforseo" },
    { title: "The State of AI Search Optimization", slug: "state-of-ai-search", author: "Jim Deola", stage: "published" as const, url: "https://rhize.media/blog/ai-search" },
  ];

  for (const sample of samples) {
    const piece = await createContent(sample);
    console.log(`Created: ${piece.title} (${sample.stage})`);
  }

  await closeDriver();
}

seed().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

**Step 2: Add tsx to devDependencies and add seed script**

```bash
npm install -D tsx dotenv
```

Then add to `package.json` scripts:
```json
"seed": "tsx --env-file=.env.local scripts/seed.ts"
```

**Step 3: Run the seed script**

Run: `npm run seed`
Expected: 5 "Created: ..." log lines, no errors

**Step 4: Verify in Neo4j**

In Aura Workspace:
```cypher
MATCH (c:ContentPiece)-[:IN_STAGE]->(s:PipelineStage)
RETURN s.name, collect(c.title) ORDER BY s.order
```
Expected: Content pieces grouped by stage

**Step 5: Commit**

```bash
git add scripts/seed.ts package.json package-lock.json
git commit -m "feat: add Neo4j seed script with sample content pieces"
```

### Task 0.5.4: Add maxDuration to workflow routes

Vercel serverless functions default to 10s (Hobby) or 15s (Pro). DataForSEO live endpoints can take 30–60s.

**Files:**
- Modify: `src/app/api/workflows/keyword-research/route.ts`
- Modify: `src/app/api/workflows/content-optimize/route.ts`
- Modify: `src/app/api/workflows/serp-analysis/route.ts`
- Modify: `src/app/api/workflows/backlink-analysis/route.ts`
- Modify: `src/app/api/workflows/ai-visibility/route.ts`
- Modify: `src/app/api/workflows/site-audit/route.ts`

**Step 1: Add `export const maxDuration = 300;` to each workflow route**

At the top of each file (after imports), add:
```typescript
export const maxDuration = 300; // 5 min — DataForSEO calls can be slow
```

Note: 300 seconds requires Vercel Pro. For Hobby, use `60`. For local dev it has no effect.

**Step 2: Verify build still passes**

Run: `npm run build`
Expected: Clean build

**Step 3: Commit**

```bash
git add src/app/api/workflows
git commit -m "perf: extend workflow route timeouts for DataForSEO calls"
```

### Task 0.5.5: Smoke test the full POC loop

**Manual verification** — no code changes.

**Step 1: Start dev server**

Run: `npm run dev`

**Step 2: Board loads with sample data**

Navigate to `http://localhost:3000/board`
Expected: 5 cards distributed across inspiration/research/draft/optimize/published columns.

**Step 3: Drag-and-drop persists**

Drag a card from "Draft" to "Review". Refresh the page.
Expected: Card stays in the new column.

**Step 4: Content detail page renders**

Click any card.
Expected: Detail page loads with title, stage badge, empty keyword/SERP/backlink sections, and workflow action buttons.

**Step 5: Keyword research workflow runs end-to-end**

On a content detail page, click "Research Keywords".
Expected: Button shows "Running...", within ~30–60s returns, keywords table populates with DataForSEO results.

**Step 6: Mark POC complete**

If all 5 steps pass, the proof of concept is functional. Move to M1+ for production hardening.

---

## Milestone 1: Build & Boot

Get the project to install, build, and run `npm run dev` successfully.

### Task 1: Install dependencies and generate lockfile

**Files:**
- Modify: `package.json` (if needed)
- Create: `package-lock.json` (auto-generated)

**Step 1: Install npm dependencies**

Run: `npm install`
Expected: Clean install with lockfile generated

**Step 2: Verify lockfile created**

Run: `ls package-lock.json`
Expected: File exists

**Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: install dependencies and generate lockfile"
```

### Task 2: Fix Turbopack root resolution for monorepo

The build fails because this project lives inside `rhize-plugins/content-flywheel-v2/` — Turbopack can't resolve `next/package.json` from the nested directory.

**Files:**
- Modify: `next.config.ts`

**Step 1: Add turbopack root config**

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: ".",
  },
};

export default nextConfig;
```

**Step 2: Verify build passes**

Run: `npm run build`
Expected: Build completes without Turbopack root error

**Step 3: Verify dev server starts**

Run: `npm run dev` (start, verify page loads at localhost:3000, then stop)
Expected: Redirects to `/board`, board page renders (will show empty state without Neo4j connection)

**Step 4: Commit**

```bash
git add next.config.ts
git commit -m "fix: configure turbopack root for monorepo structure"
```

---

## Milestone 2: Security — Replace Raw Cypher Proxy

**CRITICAL:** The `/api/graph/query` endpoint accepts arbitrary Cypher from the client. This is a Cypher injection vector. Replace it with dedicated, parameterized API endpoints.

### Task 3: Create dedicated board API endpoint

**Files:**
- Create: `src/app/api/board/route.ts`
- Test: manual via `curl` or browser

**Step 1: Write the board API route**

```typescript
import { NextResponse } from "next/server";
import { getContentByStage } from "@/lib/neo4j/queries";

export async function GET() {
  try {
    const board = await getContentByStage();
    return NextResponse.json({ board });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
```

**Step 2: Commit**

```bash
git add src/app/api/board/route.ts
git commit -m "feat: add dedicated board API endpoint"
```

### Task 4: Create dedicated stage-move API endpoint

**Files:**
- Create: `src/app/api/board/move/route.ts`

**Step 1: Write the move route**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { moveContentToStage } from "@/lib/neo4j/queries";
import type { PipelineStage } from "@/types";

export async function POST(req: NextRequest) {
  try {
    const { contentId, newStage } = await req.json();
    if (!contentId || !newStage) {
      return NextResponse.json(
        { error: "Missing contentId or newStage" },
        { status: 400 }
      );
    }
    await moveContentToStage(contentId, newStage as PipelineStage);
    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
```

**Step 2: Commit**

```bash
git add src/app/api/board/move/route.ts
git commit -m "feat: add dedicated stage-move API endpoint"
```

### Task 5: Create dedicated content detail API endpoint

**Files:**
- Modify: `src/lib/neo4j/queries.ts` (add `getContentDetailById` function)
- Create: `src/app/api/content/[id]/route.ts`

**Step 1: Add a detail query to queries.ts**

Add this function to `src/lib/neo4j/queries.ts`:

```typescript
export async function getContentDetailById(id: string) {
  const driver = getDriver();
  const session = driver.session();
  try {
    const result = await session.run(
      `MATCH (c:ContentPiece {id: $id})-[:IN_STAGE]->(s:PipelineStage)
       OPTIONAL MATCH (c)-[:TARGETS]->(k:Keyword)
       OPTIONAL MATCH (c)-[:RANKS_FOR]->(snap:SERPSnapshot)
       OPTIONAL MATCH (c)-[:HAS_BACKLINK_FROM]->(b:BacklinkSource)
       OPTIONAL MATCH (c)-[:LINKS_TO]->(linked:ContentPiece)
       OPTIONAL MATCH (c)-[:HAS_SCORE]->(seo:SEOScore)
       WITH c, s, k, snap, b, linked, seo ORDER BY seo.date DESC
       RETURN c { .*, stage: s.name } AS content,
              collect(DISTINCT k { .* }) AS keywords,
              collect(DISTINCT snap { .* }) AS serpSnapshots,
              collect(DISTINCT b { .domain, .authorityRank, .anchorText }) AS backlinks,
              collect(DISTINCT linked { targetTitle: linked.title, targetSlug: linked.slug }) AS internalLinks,
              head(collect(DISTINCT seo { .* })) AS seoScore`,
      { id }
    );
    if (result.records.length === 0) return null;
    const row = result.records[0];
    return {
      ...row.get("content"),
      keywords: row.get("keywords") ?? [],
      serpSnapshots: row.get("serpSnapshots") ?? [],
      backlinks: row.get("backlinks") ?? [],
      internalLinks: row.get("internalLinks") ?? [],
      seoScore: row.get("seoScore") ?? null,
    };
  } finally {
    await session.close();
  }
}
```

**Step 2: Write the API route**

```typescript
// src/app/api/content/[id]/route.ts
import { NextRequest, NextResponse } from "next/server";
import { getContentDetailById } from "@/lib/neo4j/queries";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const detail = await getContentDetailById(id);
    if (!detail) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json(detail);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
```

**Step 3: Commit**

```bash
git add src/lib/neo4j/queries.ts src/app/api/content/\[id\]/route.ts
git commit -m "feat: add dedicated content detail API endpoint"
```

### Task 6: Update board page to use dedicated endpoints

**Files:**
- Modify: `src/app/board/page.tsx`

**Step 1: Replace raw Cypher calls with dedicated API endpoints**

In `fetchBoard`: replace the `/api/graph/query` POST with `GET /api/board`.
In `handleDrop`: replace the raw Cypher POST with `POST /api/board/move`.

The `fetchBoard` function becomes:
```typescript
const fetchBoard = useCallback(async () => {
  try {
    const res = await fetch("/api/board");
    const data = await res.json();
    const grouped: BoardData = {};
    for (const stage of PIPELINE_STAGES) {
      grouped[stage.name] = [];
    }
    for (const [stage, pieces] of Object.entries(data.board ?? {})) {
      grouped[stage] = pieces as ContentPiece[];
    }
    setBoard(grouped);
  } catch (err) {
    console.error("Failed to fetch board:", err);
  } finally {
    setLoading(false);
  }
}, []);
```

The `handleDrop` persist call becomes:
```typescript
await fetch("/api/board/move", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ contentId: draggedItem.id, newStage: targetStage }),
});
```

**Step 2: Verify board still loads in dev**

Run: `npm run dev`, navigate to `/board`
Expected: Board renders, drag-and-drop still works

**Step 3: Commit**

```bash
git add src/app/board/page.tsx
git commit -m "security: replace raw Cypher calls with dedicated board endpoints"
```

### Task 7: Update content detail page to use dedicated endpoint

**Files:**
- Modify: `src/app/content/[id]/page.tsx`

**Step 1: Replace the `fetchContentDetail` function**

```typescript
async function fetchContentDetail(id: string): Promise<ContentDetail | null> {
  const res = await fetch(`/api/content/${id}`);
  if (!res.ok) return null;
  return res.json();
}
```

**Step 2: Verify content detail page still loads**

Run: `npm run dev`, navigate to `/content/<some-id>`
Expected: Detail page renders (or shows "not found" if no data)

**Step 3: Commit**

```bash
git add src/app/content/\[id\]/page.tsx
git commit -m "security: replace raw Cypher calls with dedicated content endpoint"
```

### Task 8: Remove the generic Cypher proxy (or restrict to server-only)

**Files:**
- Modify: `src/app/api/graph/query/route.ts`

**Step 1: Add authorization guard**

Add a check for a `GRAPH_QUERY_SECRET` header so the endpoint can only be used by server-side cron jobs, not the browser:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { runCypher } from "@/lib/neo4j/queries";

export async function POST(req: NextRequest) {
  try {
    const secret = req.headers.get("x-graph-secret");
    if (secret !== process.env.GRAPH_QUERY_SECRET) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { query, params } = await req.json();
    if (!query || typeof query !== "string") {
      return NextResponse.json(
        { error: "Missing or invalid 'query' field" },
        { status: 400 }
      );
    }

    const results = await runCypher(query, params ?? {});
    return NextResponse.json({ results });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
```

**Step 2: Add `GRAPH_QUERY_SECRET` to `.env.example`**

Append: `GRAPH_QUERY_SECRET=` to `.env.example`

**Step 3: Verify build passes**

Run: `npm run build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add src/app/api/graph/query/route.ts .env.example
git commit -m "security: restrict generic Cypher proxy with secret header"
```

---

## Milestone 3: Create Content Flow

Users need to create content pieces from the UI.

### Task 9: Create content API endpoint

**Files:**
- Create: `src/app/api/content/route.ts`

**Step 1: Write the create-content route**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { createContent } from "@/lib/neo4j/queries";
import type { PipelineStage } from "@/types";

export async function POST(req: NextRequest) {
  try {
    const { title, slug, author, url, stage } = await req.json();

    if (!title || !slug || !author) {
      return NextResponse.json(
        { error: "Missing required fields: title, slug, author" },
        { status: 400 }
      );
    }

    const content = await createContent({
      title,
      slug,
      author,
      url: url ?? null,
      stage: (stage as PipelineStage) ?? "inspiration",
    });

    return NextResponse.json(content, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
```

**Step 2: Commit**

```bash
git add src/app/api/content/route.ts
git commit -m "feat: add create-content API endpoint"
```

### Task 10: Add "New Content" modal to the board page

**Files:**
- Modify: `src/app/board/page.tsx`

**Step 1: Add state and modal markup**

Add a `showCreate` state and a form modal to the board page. The form collects `title`, `slug`, `author`, `url` (optional), and `stage` (defaults to "inspiration"). On submit, POST to `/api/content`, close the modal, and re-fetch the board.

Key additions:
- `const [showCreate, setShowCreate] = useState(false);` in state declarations
- A "New Content" button next to existing header buttons
- A modal overlay with a form containing the fields above
- Auto-generate slug from title on blur (lowercase, hyphenated)
- On successful create, call `fetchBoard()` to refresh

**Step 2: Verify create flow works**

Run: `npm run dev`, click "New Content", fill in form, submit
Expected: New card appears in the "Inspiration" column (requires Neo4j connection)

**Step 3: Commit**

```bash
git add src/app/board/page.tsx
git commit -m "feat: add create-content modal to board page"
```

---

## Milestone 4: App Shell & Error Handling

### Task 11: Add a sidebar navigation component

**Files:**
- Create: `src/components/sidebar.tsx`
- Modify: `src/app/layout.tsx`

**Step 1: Create sidebar component**

A vertical sidebar with links to:
- `/board` — Pipeline Board
- (future: `/graph` — Graph Explorer)

Plus a small "Content Flywheel" branding header.

**Step 2: Update root layout to include sidebar**

Wrap `{children}` in a flex layout with the sidebar on the left and main content on the right.

**Step 3: Verify layout renders**

Run: `npm run dev`
Expected: Sidebar appears on all pages, links work

**Step 4: Commit**

```bash
git add src/components/sidebar.tsx src/app/layout.tsx
git commit -m "feat: add sidebar navigation component"
```

### Task 12: Add error boundary component

**Files:**
- Create: `src/components/error-boundary.tsx`
- Create: `src/app/board/error.tsx`
- Create: `src/app/content/[id]/error.tsx`

**Step 1: Create a reusable error UI component**

```typescript
"use client";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4">
      <h2 className="text-lg font-semibold text-zinc-800 dark:text-zinc-200">
        Something went wrong
      </h2>
      <p className="text-sm text-zinc-500">{error.message}</p>
      <button
        onClick={reset}
        className="rounded-md bg-zinc-900 px-4 py-2 text-sm text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900"
      >
        Try again
      </button>
    </div>
  );
}
```

**Step 2: Create error.tsx for board and content detail**

Both files re-export the shared error component.

**Step 3: Verify build passes**

Run: `npm run build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add src/components/error-boundary.tsx src/app/board/error.tsx src/app/content/\[id\]/error.tsx
git commit -m "feat: add error boundary components for board and content pages"
```

### Task 13: Add loading skeletons

**Files:**
- Create: `src/app/board/loading.tsx`
- Create: `src/app/content/[id]/loading.tsx`

**Step 1: Create skeleton loading states**

Board loading: 8 columns of gray skeleton cards.
Content loading: Skeleton blocks for title, keywords table, SERP table.

**Step 2: Commit**

```bash
git add src/app/board/loading.tsx src/app/content/\[id\]/loading.tsx
git commit -m "feat: add loading skeleton states"
```

---

## Milestone 5: Graph Explorer Page

### Task 14: Add graph statistics query

**Files:**
- Modify: `src/lib/neo4j/queries.ts`
- Create: `src/app/api/graph/stats/route.ts`

**Step 1: Add `getGraphStats` to queries.ts**

Returns counts of each node type, relationship type, and recent activity.

**Step 2: Write the stats API route**

GET endpoint that returns graph statistics.

**Step 3: Commit**

```bash
git add src/lib/neo4j/queries.ts src/app/api/graph/stats/route.ts
git commit -m "feat: add graph statistics query and API endpoint"
```

### Task 15: Create graph explorer page

**Files:**
- Create: `src/app/graph/page.tsx`
- Modify: `src/components/sidebar.tsx` (add nav link)

**Step 1: Build the graph explorer page**

A page showing:
- Node type counts (ContentPiece, Keyword, KeywordCluster, etc.) as stat cards
- Recent workflow runs table
- Keyword clusters with content piece counts
- A "pipeline funnel" view showing count per stage

This is a read-only dashboard — no graph visualization library needed (keeps deps minimal).

**Step 2: Add to sidebar nav**

Add `/graph` link to the sidebar component.

**Step 3: Verify page renders**

Run: `npm run dev`, navigate to `/graph`
Expected: Page renders with stats (empty state if no Neo4j connection)

**Step 4: Commit**

```bash
git add src/app/graph/page.tsx src/components/sidebar.tsx
git commit -m "feat: add graph explorer dashboard page"
```

---

## Milestone 6: Testing

### Task 16: Set up test infrastructure

**Files:**
- Modify: `package.json` (add vitest, @testing-library/react)
- Create: `vitest.config.ts`

**Step 1: Install test dependencies**

```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

**Step 2: Create vitest config**

```typescript
import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
```

**Step 3: Create test setup file**

```typescript
// tests/setup.ts
import "@testing-library/jest-dom";
```

**Step 4: Add test script to package.json**

Add `"test": "vitest run"` and `"test:watch": "vitest"` to scripts.

**Step 5: Commit**

```bash
git add package.json package-lock.json vitest.config.ts tests/setup.ts
git commit -m "chore: set up vitest test infrastructure"
```

### Task 17: Add unit tests for Neo4j query functions

**Files:**
- Create: `tests/lib/neo4j/queries.test.ts`

**Step 1: Write tests**

Mock the neo4j-driver and test:
- `createContent` — calls session.run with correct Cypher and returns mapped result
- `moveContentToStage` — calls session.run with DELETE/CREATE pattern
- `getContentByStage` — returns grouped record by stage
- `getContentById` — returns null for missing content, returns mapped result for existing

**Step 2: Run tests to verify they pass**

Run: `npm test`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/lib/neo4j/queries.test.ts
git commit -m "test: add unit tests for Neo4j query functions"
```

### Task 18: Add unit tests for DataForSEO client

**Files:**
- Create: `tests/lib/dataforseo/client.test.ts`

**Step 1: Write tests**

Mock global `fetch` and test:
- `keywordSuggestions` — sends correct URL and payload
- `serpLive` — sends correct URL and payload
- `backlinksSummary` — sends correct URL
- Error handling — throws on non-OK response
- Auth — constructs correct Basic auth header

**Step 2: Run tests**

Run: `npm test`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/lib/dataforseo/client.test.ts
git commit -m "test: add unit tests for DataForSEO client"
```

### Task 19: Add tests for API route handlers

**Files:**
- Create: `tests/app/api/board.test.ts`
- Create: `tests/app/api/content.test.ts`

**Step 1: Write route handler tests**

Test the board GET endpoint, move POST endpoint, and content create POST endpoint.
Mock the neo4j query functions and verify correct responses, status codes, and error handling.

**Step 2: Run tests**

Run: `npm test`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/app/api/board.test.ts tests/app/api/content.test.ts
git commit -m "test: add API route handler tests"
```

---

## Milestone 7: Deploy to Vercel

### Task 20: Verify Vercel configuration

**Files:**
- Verify: `vercel.json` (already has cron config)
- Modify: `.env.example` (ensure all vars documented)

**Step 1: Review vercel.json**

Verify cron schedules are correct:
- `/api/cron/seo-pull` — daily at 6am UTC
- `/api/cron/serp-snapshot` — weekly Monday at 7am UTC

**Step 2: Ensure .env.example is complete**

Verify all environment variables are documented:
- Neo4j: URI, USERNAME, PASSWORD
- DataForSEO: USERNAME, PASSWORD
- Sanity: PROJECT_ID, DATASET, API_TOKEN
- GHL: API_KEY, LOCATION_ID
- GRAPH_QUERY_SECRET (new from Task 8)

**Step 3: Run final build**

Run: `npm run build`
Expected: Clean build with no errors

**Step 4: Run tests**

Run: `npm test`
Expected: All tests pass

**Step 5: Commit**

```bash
git add .env.example vercel.json
git commit -m "chore: finalize Vercel config and env documentation"
```

### Task 21: Deploy

**Step 1: Deploy to Vercel**

Use Vercel CLI or dashboard to deploy. Set environment variables in Vercel project settings.

**Step 2: Verify deployment**

- Board loads at production URL
- Cron jobs are scheduled in Vercel dashboard
- API endpoints respond correctly

---

## Milestone 8: AI Feature Parity + Cost Optimization

Bring back the AI capabilities from the old n8n version (article generation, theme extraction, semantic clustering, brand voice scoring) — but rebuilt with modern models, prompt caching, and Neo4j-backed memoization for dramatic cost reduction.

**Old version pipeline** (expensive, ~$3–5 per article):
- Claude Haiku → theme extraction
- Claude Sonnet → article outline
- **Claude Opus → full article draft** (main cost)
- Claude Sonnet → self-review + brand voice pass
- Gemini embeddings → keyword clustering

**New v2 target pipeline** (~$0.20–0.50 per article):
- Haiku 4.5 → theme extraction, intent classification, quality screening
- **Sonnet 4.6 → outline + full draft** (Opus-tier quality at ~1/5 cost)
- Haiku 4.5 → brand voice validation pass
- Gemini gemini-embedding-001 → semantic embeddings (256-dim, cheap, high-quality)
- Neo4j caching — if keywords/embeddings/outlines already exist, reuse

### Task 22: Install AI SDK dependencies

**Files:**
- Modify: `package.json`

**Step 1: Install dependencies**

Run: `npm install @anthropic-ai/sdk@latest`

Optional (pick one for embeddings):

- `@google/genai` — Gemini gemini-embedding-001 (cheapest, 256-dim) ✅ **CHOSEN**

Note: `@google/generative-ai` is deprecated. Use `@google/genai` with `GoogleGenAI` class.
Model `text-embedding-004` is retired — use `gemini-embedding-001`.

**Step 2: Add env vars**

Add to `.env.local` and Vercel production:
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY` (or chosen embedding provider)

**Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add Anthropic SDK and embeddings client"
```

### Task 23: Add Claude client with prompt caching

**Files:**
- Create: `src/lib/ai/claude.ts`

**Step 1: Write client wrapper**

Build a thin wrapper around `@anthropic-ai/sdk` that:

- Configures the client with API key from env
- Exposes `generateText(params)` with built-in prompt caching (`cache_control: { type: "ephemeral" }` on system prompts)
- Exposes `generateStructured<T>(params, schema)` using tool-use for guaranteed JSON output
- Records token usage and cost to Neo4j as `(:AIUsage)` nodes for cost tracking
- Defaults to `claude-haiku-4-5-20251001` for cheap operations, `claude-sonnet-4-6` for generation
- Implements exponential backoff on 429/overload errors

**Why prompt caching matters:** System prompts for article generation are long (brand voice guidelines, examples, format specs). Caching them reduces input cost by 90% on repeated calls within 5 min, 50% within 1 hour.

**Step 2: Commit**

```bash
git add src/lib/ai/claude.ts
git commit -m "feat: add Claude SDK wrapper with prompt caching"
```

### Task 24: Add embeddings client

**Files:**
- Create: `src/lib/ai/embeddings.ts`

**Step 1: Write embeddings helper**

Single function `embedBatch(texts: string[]): Promise<number[][]>` that:

- Uses Gemini gemini-embedding-001 via `@google/genai` GoogleGenAI class
- Batches up to 100 texts per API call
- Returns arrays of 256-dim vectors (configurable via `outputDimensionality`)
- Caches embeddings in Neo4j: `MERGE (k:Keyword {term: $term}) SET k.embedding = $vector`
- Skips re-embedding keywords that already have an `embedding` property

**Step 2: Commit**

```bash
git add src/lib/ai/embeddings.ts
git commit -m "feat: add batched embeddings client with Neo4j cache"
```

### Task 25: Semantic keyword clustering (replace regex classifier)

**Files:**
- Modify: `src/lib/workflows/keyword-research.ts`
- Create: `src/lib/ai/clustering.ts`

**Step 1: Write clustering module**

Implement k-means or HDBSCAN clustering on keyword embeddings:

- Input: array of keywords with their embedding vectors from Neo4j
- Output: cluster assignments (cluster id per keyword)
- Use `ml-kmeans` package (~10KB, no heavy deps) with auto-selected k via elbow method
- Each cluster gets a Claude Haiku call to generate a descriptive name + pillar topic

**Step 2: Replace `classifyIntent` regex**

In `keyword-research.ts`, the current `classifyIntent()` uses regex patterns. Replace with a Haiku call that batch-classifies up to 50 keywords at once into `informational | navigational | commercial | transactional`. Cost: ~$0.0003 per 50 keywords vs. $0 for regex, but dramatically more accurate.

Keep regex as fallback if Haiku API fails.

**Step 3: Update workflow to use clustering**

When `runKeywordResearch` creates `KeywordCluster` nodes, use semantic clustering instead of "contains seed string" matching. This produces better clusters and enables finding related keywords that don't share exact substrings.

**Step 4: Commit**

```bash
git add src/lib/ai/clustering.ts src/lib/workflows/keyword-research.ts
git commit -m "feat: semantic keyword clustering via embeddings"
```

### Task 26: Content ingestion workflow (theme extraction)

**Files:**
- Create: `src/lib/workflows/content-ingest.ts`
- Create: `src/app/api/workflows/content-ingest/route.ts`

**Step 1: Write ingestion workflow**

Takes a URL, does:

1. Fetch page content via Firecrawl (`firecrawl` npm package, `Firecrawl` class, `.scrape(url, { formats: ["markdown"] })`)
2. Extract main article content + metadata (title, description, published date, author)
3. Claude Haiku call: extract 5–8 themes and a 2-sentence summary
4. Create `ContentPiece` in `inspiration` stage with extracted metadata
5. Create `Theme` nodes linked via `HAS_THEME` relationship
6. Embed the summary and store on the ContentPiece for later similarity search

Add `(:Theme)` node to schema via a new `cypher/migrations/001-add-themes.cypher` file.

**Step 2: Write API route**

`POST /api/workflows/content-ingest` — accepts `{ url }`, returns created content.

**Step 3: Add "Ingest URL" button to board header**

Replace the current `prompt("Enter domain to audit")` flow with a proper modal that accepts a URL and runs content-ingest.

**Step 4: Commit**

```bash
git add src/lib/workflows/content-ingest.ts src/app/api/workflows/content-ingest/route.ts cypher/migrations/ src/app/board/page.tsx
git commit -m "feat: content ingestion workflow with theme extraction"
```

### Task 27: AI outline generation workflow

**Files:**
- Create: `src/lib/workflows/article-outline.ts`
- Create: `src/app/api/workflows/article-outline/route.ts`

**Step 1: Write outline workflow**

Takes a `contentId` (must be in `research` stage with linked keywords), generates:

1. Gather context from Neo4j: target keywords, competitor SERP pages (from SERPSnapshots), internal linking opportunities
2. Claude Sonnet call with prompt-cached system prompt containing Rhize brand voice guide
3. Structured output: `{ title, metaDescription, h2Sections: [{ heading, bullets, targetWordCount }], faqTopics, internalLinks }`
4. Store as `(:Outline)` node linked to `ContentPiece` via `HAS_OUTLINE`
5. Move content to `draft` stage automatically

**Step 2: Write API route + content detail button**

Button on content detail page: "Generate Outline" (visible when in research/draft stage).

**Step 3: Commit**

```bash
git add src/lib/workflows/article-outline.ts src/app/api/workflows/article-outline/ src/app/content/\[id\]/page.tsx
git commit -m "feat: AI article outline generation workflow"
```

### Task 28: AI article draft generation workflow

**Files:**
- Create: `src/lib/workflows/article-draft.ts`
- Create: `src/app/api/workflows/article-draft/route.ts`

**Step 1: Write draft workflow**

Takes a `contentId` with an outline attached:

1. Load the outline from Neo4j
2. For each H2 section, call Claude Sonnet to generate section content (parallelized with `Promise.all`, rate-limited to 3 concurrent)
3. Assemble sections into full article markdown
4. Store as `(:Draft)` node with content, word count, generation metadata
5. Calculate approximate cost from usage tokens, log to `(:AIUsage)`
6. Move to `optimize` stage

Uses prompt caching extensively — the brand voice guide + outline gets cached once, then reused across all H2 generation calls.

**Step 2: Write API route + UI**

Button on content detail: "Generate Draft" (visible when outline exists).
Show generation progress: "Writing section 3 of 7..." via streaming or polling.

**Step 3: Commit**

```bash
git add src/lib/workflows/article-draft.ts src/app/api/workflows/article-draft/ src/app/content/\[id\]/page.tsx
git commit -m "feat: AI article draft generation with parallel section writing"
```

### Task 29: Brand voice scoring pass

**Files:**
- Create: `src/lib/workflows/brand-voice-check.ts`
- Create: `src/app/api/workflows/brand-voice-check/route.ts`

**Step 1: Write brand voice check**

Takes a `contentId` with a draft:

1. Haiku call with draft + brand voice reference
2. Returns `{ score: 0-100, issues: [{ section, issue, suggestion }] }`
3. Store as `(:BrandVoiceScore)` node

**Step 2: Show in UI**

Add brand voice score card to content detail page below SEO score. Red/yellow/green based on score thresholds.

**Step 3: Commit**

```bash
git add src/lib/workflows/brand-voice-check.ts src/app/api/workflows/brand-voice-check/ src/app/content/\[id\]/page.tsx
git commit -m "feat: brand voice scoring via Claude Haiku"
```

### Task 30: Cost tracking dashboard panel

**Files:**
- Modify: `src/lib/neo4j/queries.ts` (add `getCostStats`)
- Modify: `src/app/api/graph/stats/route.ts`
- Modify: `src/app/graph/page.tsx`

**Step 1: Add cost aggregation query**

Query total AIUsage cost grouped by: model, workflow type, last 7/30 days.

**Step 2: Add cost panel to graph explorer page**

Show: total cost last 30 days, cost per article, cost by model, tokens saved via prompt caching.

**Step 3: Commit**

```bash
git add src/lib/neo4j/queries.ts src/app/api/graph/stats/route.ts src/app/graph/page.tsx
git commit -m "feat: AI cost tracking dashboard panel"
```

### Task 31: Tests for AI workflows

**Files:**
- Create: `tests/lib/ai/claude.test.ts`
- Create: `tests/lib/ai/embeddings.test.ts`
- Create: `tests/lib/ai/clustering.test.ts`

Mock the Anthropic SDK and embeddings provider. Test: prompt cache headers are set, token usage is logged, structured output parsing works, clustering produces reasonable groups for synthetic data.

**Step 1: Write tests + run**

```bash
npm test
```

**Step 2: Commit**

```bash
git add tests/lib/ai/
git commit -m "test: AI workflow unit tests"
```

---

## Milestone 9: Replace DataForSEO with SEO Utils

**CRITICAL ARCHITECTURAL NOTE:** SEO Utils operates as a **local HTTP server** (`http://localhost:19515/mcp`) bundled with the SEO Utils desktop app. Two distinct questions:

1. **MCP integration** (for Claude local dev tools) — straightforward swap in `.mcp.json`
2. **Runtime integration** (for deployed Vercel serverless functions) — blocked unless SEO Utils exposes a public cloud API

**SEO Utils MCP wraps DataForSEO internally** — it holds the DataForSEO credentials itself, then adds GSC, GA4, local GMB, LLM rank tracking, content briefs, NLP entity analysis, indexing status checks, and keyword cannibalization detection on top.

### Task 32: Purchase SEO Utils MCP access

**MANUAL STEP** — `$1 one-time fee` per the docs.

1. Purchase "MCP Access" via SEO Utils Settings → Services
2. Generate Bearer token in Settings → MCP Server → Manual Config
3. Save token for next task

### Task 33: Add SEO Utils MCP server to .mcp.json

**Files:**
- Modify: `.mcp.json`

**Step 1: Add the new entry**

```json
"seo-utils": {
  "url": "http://localhost:19515/mcp",
  "headers": {
    "Authorization": "Bearer ${SEO_UTILS_TOKEN}"
  }
}
```

**Step 2: Add `SEO_UTILS_TOKEN` to `.env.local`**

(Not added to Vercel — this is local-dev MCP only.)

**Step 3: Commit**

```bash
git add .mcp.json
git commit -m "chore: add seo-utils MCP server alongside dataforseo"
```

### Task 34: Verify SEO Utils tools work in Claude

After next Claude Code session restart, verify the new MCP server loads and tools are available (`mcp__seo-utils__*`). Test one tool end-to-end (e.g., keyword suggestions, GSC query, or LLM rank tracker).

### Task 35: Evaluate SEO Utils cloud/REST API for runtime use

**Research task — no code changes unless viable.**

Investigate whether SEO Utils offers any of:

1. A public REST API separate from the MCP server
2. A self-hosted server mode (run SEO Utils headless on a VPS/Railway box, expose the port to Vercel via a secure tunnel)
3. A webhook/relay pattern (SEO Utils pushes data to a Vercel endpoint on schedule)

**Outcome options:**

- **Option A — Public REST API exists:** proceed to Task 36 (rewrite `src/lib/dataforseo/client.ts` to call SEO Utils)
- **Option B — Only local MCP:** keep DataForSEO for Vercel runtime, use SEO Utils for local dev/research. This is acceptable: the MCP gives us better ad-hoc analysis in Claude Code sessions, while runtime workflows still use the direct DataForSEO API (which SEO Utils wraps anyway).
- **Option C — Self-hosted server:** more complex, defer to a future phase. Requires running SEO Utils on Railway/fly.io, exposing auth-protected HTTP endpoint, updating Vercel env vars to point at it.

### Task 36: (Conditional on Option A) Migrate runtime client

**Only proceed if Task 35 confirms SEO Utils has a usable cloud API.**

**Files:**
- Create: `src/lib/seo-utils/client.ts`
- Modify: all workflow files in `src/lib/workflows/`

**Step 1: Port DataForSEO function signatures**

Build a new client with equivalent functions (`keywordSuggestions`, `serpLive`, `backlinksSummary`, etc.) that calls SEO Utils endpoints. Keep the same TypeScript shapes so workflow files don't need heavy changes.

**Step 2: Dual-run both clients side-by-side for 1 week**

Add a feature flag `USE_SEO_UTILS=true/false`. Run the same workflow through both; compare results; validate equivalence.

**Step 3: Remove DataForSEO client after validation**

```bash
git rm src/lib/dataforseo/client.ts
# update all imports to seo-utils client
```

**Step 4: Remove DataForSEO env vars from Vercel**

```bash
vercel env rm DATAFORSEO_USERNAME production
vercel env rm DATAFORSEO_PASSWORD production
```

**Step 5: Commit**

```bash
git commit -m "feat: migrate runtime from DataForSEO to SEO Utils"
```

### Task 37: Add SEO Utils-exclusive features as new workflows

**Only applicable if Option A or C from Task 35.**

SEO Utils exposes capabilities DataForSEO doesn't:

1. **GSC integration** — pull actual Rhize Media search console data (clicks, impressions, positions, queries). Create `src/lib/workflows/gsc-sync.ts`.
2. **LLM rank tracker** — monitor brand mentions across ChatGPT/Perplexity/Gemini. Create `src/lib/workflows/llm-rank-sync.ts`.
3. **Keyword cannibalization detection** — find pages competing for the same query. Create `src/lib/workflows/cannibalization-check.ts`.
4. **Content briefs via NLP** — automatic entity/topic extraction for article outlines (could feed into M8 Task 27).

Each becomes its own task with outline → workflow file → API route → UI surface.

---

## Task Dependency Graph

```
M1: Build & Boot
  Task 1 (npm install) → Task 2 (fix turbopack)

M2: Security
  Task 3 (board API) ─┐
  Task 4 (move API)  ─┤→ Task 6 (update board page) ─┐
  Task 5 (detail API) ─→ Task 7 (update detail page) ─┤→ Task 8 (restrict proxy)
                                                       │
M3: Create Content                                     │
  Task 9 (create API) → Task 10 (create modal) ←──────┘

M4: App Shell
  Task 11 (sidebar) → Task 12 (error boundaries) → Task 13 (loading skeletons)

M5: Graph Explorer
  Task 14 (graph stats) → Task 15 (explorer page) ← Task 11 (sidebar)

M6: Testing
  Task 16 (vitest setup) → Task 17 (neo4j tests) → Task 18 (dataforseo tests) → Task 19 (API tests)

M7: Deploy
  All milestones complete → Task 20 (verify config) → Task 21 (deploy)

M8: AI Feature Parity (post-deploy)
  Task 22 (SDK install) → Task 23 (Claude client) → Task 24 (embeddings)
                                                       ↓
                                                  Task 25 (clustering)
                                                       ↓
  Task 26 (ingest) → Task 27 (outline) → Task 28 (draft) → Task 29 (brand voice)
                                                               ↓
                                                        Task 30 (cost dashboard)
                                                               ↓
                                                        Task 31 (AI tests)

M9: SEO Utils Migration (research + conditional)
  Task 32 (purchase) → Task 33 (MCP config) → Task 34 (verify tools)
                                                     ↓
                                              Task 35 (evaluate cloud API)
                                                ↓              ↓
                                          Option A/C      Option B (stop)
                                                ↓
                                          Task 36 (migrate client)
                                                ↓
                                          Task 37 (new features)
```

**Parallelizable:** M3 + M4 can run in parallel after M2. M6 can start after M1. M8 and M9 are independent — can run concurrently after M7. Within M8, Tasks 27/28/29 depend sequentially (draft needs outline, brand voice needs draft), but Tasks 22–25 can all run before Task 26.

**Cost expectations for M8:**

Per article generation, target costs with prompt caching + Sonnet 4.6:
- Theme extraction (Haiku): ~$0.001
- Keyword classification (Haiku batch): ~$0.001
- Clustering + naming (Haiku): ~$0.003
- Outline generation (Sonnet): ~$0.05
- Full draft generation (Sonnet, 7 sections parallel): ~$0.25
- Brand voice check (Haiku): ~$0.002
- Embeddings (Gemini, one-time per keyword): ~$0.0001

**Total per article: ~$0.31** vs. old n8n pipeline at $3–5 = **~90% cost reduction** with comparable quality.
