# Content Flywheel — Production-Ready Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Take the content-flywheel-v2 from scaffolded-but-unrunnable to a working, secure, deployable dashboard with full CRUD and graph exploration.

**Architecture:** Next.js 15 App Router + Neo4j Aura + DataForSEO. The core workflow engines and adapters are already implemented. This plan focuses on: getting the build working, closing security holes, adding missing UI flows, and deploying.

**Tech Stack:** Next.js 16, React 19, TypeScript 5, Tailwind CSS 4, neo4j-driver 6, Vercel, DataForSEO API

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
```

**Parallelizable:** M3 + M4 can run in parallel after M2. M6 can start after M1.
